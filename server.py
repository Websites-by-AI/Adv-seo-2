#!/usr/bin/env python3
"""Clinic Signal — dependency-free local server and safe public-site SEO auditor."""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import secrets
import smtplib
import socket

import requests
from bs4 import BeautifulSoup
import ssl
import threading
import time
from collections import defaultdict, deque
from email.message import EmailMessage
from html.parser import HTMLParser
from io import BytesIO, StringIO
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parent
MAX_BODY = 2_000_000
USER_AGENT = "ClinicSignalAudit/1.1 (+public-business-seo-audit)"
SEND_ENABLED = os.getenv("SEND_ENABLED", "false").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "true").lower() != "false"
SEND_LOG: deque[dict] = deque(maxlen=100)
RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
PDF_LINKS: dict[str, dict] = {}
PDF_LINK_TTL = max(300, min(int(os.getenv("PDF_LINK_TTL_SECONDS", "86400")), 604800))
PDF_LINK_LIMIT = max(10, min(int(os.getenv("PDF_LINK_LIMIT", "100")), 500))
ALLOWED_CHANNELS = {"whatsapp", "telegram", "bale", "rubika", "soroush", "eitaa", "email", "sms", "divar"}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def integration_auth_error(headers, path: str) -> tuple[int, str] | None:
    """Validate Next.js → Python calls without exposing the shared token to a browser.

    X-Clinic-Signal-Internal makes verification mandatory for the Next.js gateway.
    CLINIC_SIGNAL_REQUIRE_AUTH=true optionally protects every /api route except signed PDF reads.
    The standalone Clinic Signal browser UI needs the latter left false unless a separate login
    or hosting-level access guard is configured.
    """
    if not path.startswith("/api/"):
        return None
    internal_call = str(headers.get("X-Clinic-Signal-Internal", "")).strip() == "1"
    globally_required = env_flag("CLINIC_SIGNAL_REQUIRE_AUTH", False)
    if not internal_call and not globally_required:
        return None
    # Signed PDF reads must stay link-accessible, and Bale's servers cannot
    # present the integration token — the bot webhook carries its own secret.
    if path in {"/api/shared-pdf", "/api/bale/webhook"} and not internal_call:
        return None

    expected = os.getenv("CLINIC_SIGNAL_API_TOKEN", "").strip()
    if len(expected) < 24:
        return 503, "CLINIC_SIGNAL_API_TOKEN is missing or shorter than 24 characters."
    authorization = str(headers.get("Authorization", ""))
    provided = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
    if not provided or not hmac.compare_digest(provided, expected):
        return 401, "Invalid Clinic Signal integration token."
    return None


try:
    from PIL import Image, ImageDraw, ImageFont, features as pil_features
    PILLOW_AVAILABLE = True
    RAQM_AVAILABLE = bool(pil_features.check("raqm"))
except Exception:
    PILLOW_AVAILABLE = False
    RAQM_AVAILABLE = False

try:
    import arabic_reshaper
    from bidi.algorithm import get_display as bidi_get_display
    BIDI_FALLBACK_AVAILABLE = True
except Exception:
    BIDI_FALLBACK_AVAILABLE = False

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    OPENPYXL_AVAILABLE = True
except Exception:
    OPENPYXL_AVAILABLE = False


def public_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False, "Only public http/https URLs are allowed."
        if parsed.username or parsed.password:
            return False, "Credentials in URLs are not allowed."
        host = parsed.hostname.lower().rstrip(".")
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return False, "Local hosts are blocked."
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                return False, "Private, loopback and link-local destinations are blocked."
        return True, ""
    except Exception as exc:
        return False, f"Could not validate host: {type(exc).__name__}"


DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
EMAIL_PATTERN = re.compile(r"(?i)(?<![\w.+-])([a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9.-]+\.[a-z]{2,24})(?![\w.-])")
PHONE_CANDIDATE_PATTERN = re.compile(r"(?<!\d)(?:\+|00)?[\d۰-۹٠-٩][\d۰-۹٠-٩\s().-]{6,20}[\d۰-۹٠-٩](?!\d)")
CONTACT_PATH_PATTERN = re.compile(r"(?i)(contact|about|location|branch|clinic|office|support|تماس|درباره|شعب|آدرس)")
SOCIAL_HOSTS = ("instagram.com", "linkedin.com", "facebook.com", "youtube.com", "aparat.com", "t.me", "eitaa.com", "rubika.ir", "splus.ir", "bale.ai")
WHATSAPP_HOSTS = ("wa.me", "api.whatsapp.com", "web.whatsapp.com")


def normalize_public_phone(value: str) -> str:
    raw = str(value or "").translate(DIGIT_TRANSLATION).strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0098"):
        digits = digits[2:]
    if digits.startswith("98") and 11 <= len(digits) <= 12:
        return "+" + digits
    if digits.startswith("0") and 10 <= len(digits) <= 11:
        return "+98" + digits[1:]
    if 8 <= len(digits) <= 15:
        return ("+" if raw.startswith("+") else "") + digits
    return ""


def extract_public_phones(text: str) -> list[str]:
    found = []
    seen = set()
    for match in PHONE_CANDIDATE_PATTERN.finditer(str(text or "")):
        phone = normalize_public_phone(match.group(0))
        digits = re.sub(r"\D", "", phone)
        # Reject obvious dates and repeated placeholders while retaining public landlines/mobiles.
        if not phone or len(set(digits)) < 3 or digits.startswith(("139", "140")) and len(digits) <= 8:
            continue
        if phone not in seen:
            seen.add(phone)
            found.append(phone)
    return found[:20]


def extract_public_contact_signals(html: str, base_url: str) -> dict:
    """Extract public business contact signals only; never submit forms or access private pages."""
    soup = BeautifulSoup(html or "", "html.parser")
    phones, emails, whatsapp_links, social_links, contact_pages, tags = set(), set(), set(), set(), set(), set()
    base = urlparse(base_url)
    base_host = (base.hostname or "").lower().removeprefix("www.")

    for anchor in soup.find_all("a", href=True):
        raw_href = str(anchor.get("href", "")).strip()
        lower = raw_href.lower()
        if lower.startswith("tel:"):
            phone = normalize_public_phone(raw_href[4:].split("?", 1)[0])
            if phone:
                phones.add(phone)
            continue
        if lower.startswith("mailto:"):
            email = raw_href[7:].split("?", 1)[0].strip().lower()
            if EMAIL_PATTERN.fullmatch(email):
                emails.add(email)
            continue
        absolute = urljoin(base_url, raw_href)
        parsed = urlparse(absolute)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        if host in WHATSAPP_HOSTS or host.endswith(".whatsapp.com"):
            whatsapp_links.add(absolute.split("#", 1)[0])
            query = parse_qs(parsed.query)
            candidate = parsed.path.strip("/").split("/", 1)[0] if host == "wa.me" else (query.get("phone") or [""])[0]
            phone = normalize_public_phone(candidate)
            if phone:
                phones.add(phone)
            continue
        if any(host == item or host.endswith("." + item) for item in SOCIAL_HOSTS):
            social_links.add(absolute.split("#", 1)[0])
        if host == base_host and CONTACT_PATH_PATTERN.search(unquote(parsed.path)):
            contact_pages.add(absolute.split("#", 1)[0])

    visible_text = soup.get_text(" ", strip=True)
    phones.update(extract_public_phones(visible_text))
    emails.update(x.group(1).lower() for x in EMAIL_PATTERN.finditer(visible_text))

    for meta in soup.find_all("meta"):
        key = str(meta.get("name") or meta.get("property") or "").lower()
        value = str(meta.get("content", "")).strip()
        if key in {"keywords", "news_keywords", "article:tag"}:
            tags.update(x.strip()[:80] for x in re.split(r"[,،|]", value) if x.strip())

    addresses = []
    address_tag = soup.find("address")
    if address_tag:
        value = " ".join(address_tag.get_text(" ", strip=True).split())
        if value:
            addresses.append(value[:500])

    def walk_json(value):
        if isinstance(value, list):
            for item in value:
                walk_json(item)
        elif isinstance(value, dict):
            telephone = value.get("telephone")
            if telephone:
                phone = normalize_public_phone(str(telephone))
                if phone:
                    phones.add(phone)
            email = str(value.get("email", "")).removeprefix("mailto:").strip().lower()
            if email and EMAIL_PATTERN.fullmatch(email):
                emails.add(email)
            for key in ("keywords", "medicalSpecialty", "serviceType", "knowsAbout"):
                values = value.get(key, [])
                if not isinstance(values, list):
                    values = re.split(r"[,،|]", str(values))
                tags.update(str(x).strip()[:80] for x in values if str(x).strip())
            address = value.get("address")
            if isinstance(address, dict):
                rendered = "، ".join(str(address.get(k, "")).strip() for k in ("addressCountry", "addressRegion", "addressLocality", "streetAddress", "postalCode") if address.get(k))
                if rendered:
                    addresses.append(rendered[:500])
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk_json(child)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            walk_json(json.loads(script.get_text(strip=True) or "{}"))
        except Exception:
            continue

    whatsapp_number = ""
    for link in sorted(whatsapp_links):
        parsed = urlparse(link)
        query = parse_qs(parsed.query)
        candidate = parsed.path.strip("/").split("/", 1)[0] if (parsed.hostname or "").lower() == "wa.me" else (query.get("phone") or [""])[0]
        whatsapp_number = normalize_public_phone(candidate)
        if whatsapp_number:
            break

    return {
        "phoneNumbers": sorted(phones)[:20],
        "emails": sorted(emails)[:20],
        "whatsappLinks": sorted(whatsapp_links)[:10],
        "whatsappNumber": whatsapp_number,
        "socialLinks": sorted(social_links)[:20],
        "contactPageCandidates": sorted(contact_pages)[:10],
        "tags": sorted(tags, key=str.casefold)[:40],
        "addresses": list(dict.fromkeys(addresses))[:8],
    }


def enrich_public_business_contacts(url: str, max_pages: int = 3) -> dict:
    """Crawl a few same-origin public contact/about pages, respecting robots.txt."""
    if not urlparse(url).scheme:
        url = "https://" + url.strip()
    ok, reason = public_url(url)
    if not ok:
        raise ValueError(reason)
    max_pages = max(1, min(int(max_pages or 3), 5))
    status, final_url, html, content_type, elapsed = fetch(url, timeout=15, limit=1_500_000)
    if status >= 400 or ("html" not in content_type.lower() and "<html" not in html[:1000].lower()):
        raise ValueError(f"Website returned HTTP {status} or non-HTML content.")

    base_host = (urlparse(final_url).hostname or "").lower().removeprefix("www.")
    aggregate = extract_public_contact_signals(html, final_url)
    pages = [{"url": final_url, "status": status, "title": ""}]
    parser = AuditParser(final_url)
    parser.feed(html)
    pages[0]["title"] = parser.title

    candidates = list(aggregate.pop("contactPageCandidates", []))
    for page_url in candidates:
        if len(pages) >= max_pages:
            break
        host = (urlparse(page_url).hostname or "").lower().removeprefix("www.")
        if host != base_host or not robots_allows(page_url):
            continue
        try:
            page_status, page_final, page_html, page_type, _ = fetch(page_url, timeout=12, limit=1_000_000)
            if page_status >= 400 or ("html" not in page_type.lower() and "<html" not in page_html[:1000].lower()):
                continue
            signals = extract_public_contact_signals(page_html, page_final)
            for key in ("phoneNumbers", "emails", "whatsappLinks", "socialLinks", "tags", "addresses"):
                aggregate[key] = list(dict.fromkeys([*aggregate.get(key, []), *signals.get(key, [])]))[:40]
            if not aggregate.get("whatsappNumber") and signals.get("whatsappNumber"):
                aggregate["whatsappNumber"] = signals["whatsappNumber"]
            page_parser = AuditParser(page_final)
            page_parser.feed(page_html)
            pages.append({"url": page_final, "status": page_status, "title": page_parser.title})
        except Exception:
            continue

    phones = aggregate.get("phoneNumbers", [])
    emails = aggregate.get("emails", [])
    return {
        "ok": True,
        "requestedUrl": url,
        "finalUrl": final_url,
        "status": status,
        "elapsedSeconds": elapsed,
        "primaryPhone": phones[0] if phones else "",
        "primaryEmail": emails[0] if emails else "",
        **aggregate,
        "pagesChecked": pages,
        "disclaimer": "Public business contact signals only. Verify ownership and recipient consent before outreach; no forms, accounts or patient data were accessed.",
    }


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urljoin(req.full_url, newurl)
        ok, reason = public_url(absolute)
        if not ok:
            raise URLError(f"Unsafe redirect blocked: {reason}")
        return super().redirect_request(req, fp, code, msg, headers, absolute)


class AuditParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.description = ""
        self.h1: list[str] = []
        self.canonical = ""
        self.lang = ""
        self.viewport = False
        self.og_title = False
        self.schema_blocks = 0
        self.schema_types: set[str] = set()
        self.links: set[str] = set()
        self.social_links: set[str] = set()
        self.phone_links: set[str] = set()
        self.email_links: set[str] = set()
        self.text_chars = 0
        self.text_words = 0
        self.phone_signal = False
        self.address_signal = False
        self.map_or_social_signal = False
        self._in_title = False
        self._in_h1 = False
        self._in_schema = False
        self._buf: list[str] = []

    @staticmethod
    def attrs_dict(attrs):
        return {str(k).lower(): (v or "") for k, v in attrs}

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = self.attrs_dict(attrs)
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title":
            self._in_title = True
            self._buf = []
        elif tag == "h1":
            self._in_h1 = True
            self._buf = []
        elif tag == "meta":
            name = a.get("name", "").lower()
            prop = a.get("property", "").lower()
            if name == "description" and not self.description:
                self.description = a.get("content", "").strip()
            if name == "viewport":
                self.viewport = True
            if prop == "og:title":
                self.og_title = True
        elif tag == "link" and "canonical" in a.get("rel", "").lower():
            self.canonical = a.get("href", "").strip()
        elif tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in_schema = True
            self._buf = []
            self.schema_blocks += 1
        elif tag == "a" and a.get("href"):
            raw_href = a["href"].strip()
            raw = raw_href.lower()
            if raw.startswith("tel:"):
                self.phone_links.add(raw_href[4:].strip())
                self.phone_signal = True
                return
            if raw.startswith("mailto:"):
                self.email_links.add(raw_href[7:].split("?", 1)[0].strip())
                return
            href = urljoin(self.base_url, raw_href)
            parsed = urlparse(href)
            if parsed.scheme in {"http", "https"}:
                clean_href = href.split("#", 1)[0]
                self.links.add(clean_href)
                if any(x in parsed.netloc.lower() for x in ("instagram.com", "linkedin.com", "facebook.com", "youtube.com", "aparat.com", "t.me", "wa.me", "eitaa.com", "rubika.ir", "splus.ir", "bale.ai")):
                    self.social_links.add(clean_href)
            if any(x in raw for x in ("instagram.com", "maps.google", "goo.gl/maps", "wa.me", "t.me", "eitaa.com", "rubika.ir", "splus.ir", "bale.ai")):
                self.map_or_social_signal = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        text = " ".join("".join(self._buf).split())
        if tag == "title" and self._in_title:
            self.title = text
            self._in_title = False
        elif tag == "h1" and self._in_h1:
            if text:
                self.h1.append(text)
            self._in_h1 = False
        elif tag == "script" and self._in_schema:
            for typ in re.findall(r'"@type"\s*:\s*"([^"]+)"', text):
                self.schema_types.add(typ)
            self._in_schema = False
        self._buf = []

    def handle_data(self, data):
        clean = " ".join(data.split())
        if clean:
            self.text_chars += len(clean)
            self.text_words += len(clean.split())
            low = clean.lower()
            if re.search(r'(?:\+?98|0)?21[-\s]?\d{5,8}', clean) or re.search(r'09\d{9}', clean):
                self.phone_signal = True
            if any(x in low for x in ("تهران", "آدرس", "address", "خیابان", "street")):
                self.address_signal = True
        if self._in_title or self._in_h1 or self._in_schema:
            self._buf.append(data)


def fetch(url: str, timeout: int = 14, limit: int = MAX_BODY):
    ok, reason = public_url(url)
    if not ok:
        raise ValueError(reason)
    opener = build_opener(SafeRedirect())
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    started = time.monotonic()
    try:
        with opener.open(req, timeout=timeout) as response:
            final_url = response.geturl()
            ok, reason = public_url(final_url)
            if not ok:
                raise ValueError(f"Unsafe final URL: {reason}")
            body = response.read(limit + 1)
            if len(body) > limit:
                body = body[:limit]
            content_type = response.headers.get("Content-Type", "")
            charset = response.headers.get_content_charset() or "utf-8"
            text = body.decode(charset, errors="replace")
            return int(response.status), final_url, text, content_type, round(time.monotonic() - started, 2)
    except HTTPError as exc:
        try:
            body = exc.read(min(limit, 200_000)).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return int(exc.code), exc.geturl(), body, exc.headers.get("Content-Type", ""), round(time.monotonic() - started, 2)


def endpoint_exists(url: str, endpoint: str) -> bool:
    try:
        status, _, text, content_type, _ = fetch(urljoin(url, endpoint), timeout=7, limit=400_000)
        if status != 200:
            return False
        head = text[:2000].lower()
        if endpoint == "robots.txt":
            return "user-agent" in head or "sitemap:" in head
        return "<urlset" in head or "<sitemapindex" in head
    except Exception:
        return False


def score_audit(status: int, final_url: str, p: AuditParser, robots: bool, sitemap: bool):
    score = 0
    issues: list[str] = []
    wins: list[str] = []

    if status == 200:
        score += 25
        wins.append("Homepage is reachable with HTTP 200")
    else:
        issues.append(f"Homepage returned HTTP {status}")

    if 20 <= len(p.title) <= 65:
        score += 5
    else:
        issues.append("Title is missing or outside the useful 20–65 character range")
    if 70 <= len(p.description) <= 170:
        score += 5
    else:
        issues.append("Meta description is missing or outside the useful range")
    if len(p.h1) == 1:
        score += 5
    else:
        issues.append(f"Expected one H1; found {len(p.h1)}")
    if p.canonical:
        score += 4
    else:
        issues.append("Canonical tag was not found")
    if p.viewport:
        score += 3
    else:
        issues.append("Mobile viewport tag was not found")
    if p.schema_blocks:
        score += 4
        wins.append("Structured data was detected")
    else:
        issues.append("No JSON-LD structured data was detected")
    if p.og_title:
        score += 2

    if p.text_chars >= 1800:
        score += 10
    elif p.text_chars >= 700:
        score += 6
    else:
        issues.append("Homepage has little crawlable text")
    if len(p.links) >= 20:
        score += 10
    elif len(p.links) >= 8:
        score += 6
    else:
        issues.append("Internal linking appears thin")

    if robots:
        score += 6
    else:
        issues.append("A valid robots.txt was not confirmed")
    if sitemap:
        score += 6
    else:
        issues.append("A valid sitemap.xml was not confirmed")
    if final_url.startswith("https://"):
        score += 3
    else:
        issues.append("Final page is not HTTPS")

    medical = any(x.lower() in {"medicalclinic", "medicalbusiness", "physician", "dermatology"} for x in p.schema_types)
    if p.phone_signal:
        score += 5
    else:
        issues.append("Public phone signal was not detected on the homepage")
    if p.address_signal:
        score += 5
    else:
        issues.append("Address/location signal was not detected")
    if medical or p.map_or_social_signal:
        score += 5
    else:
        issues.append("Medical entity or map/social identity signal is weak")

    return min(100, score), issues[:8], wins[:5]


def audit(url: str):
    if not urlparse(url).scheme:
        url = "https://" + url.strip()
    started = time.monotonic()
    try:
        status, final_url, html, content_type, elapsed = fetch(url)
    except (URLError, ssl.SSLCertVerificationError) as exc:
        message = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" not in message and "certificate" not in message.lower() and "ssl" not in message.lower():
            raise
        return {"ok": True, "requestedUrl": url, "status": 0, "finalUrl": url,
                "elapsedSeconds": round(time.monotonic()-started, 2), "totalSeconds": round(time.monotonic()-started, 2),
                "title": "", "titleLength": 0, "description": "", "descriptionLength": 0,
                "h1Count": 0, "h1": [], "canonical": "", "lang": "", "viewport": False,
                "schemaBlocks": 0, "schemaTypes": [], "wordCount": 0,
                "internalLinks": 0, "externalLinks": 0, "internalLinkSamples": [], "externalLinkSamples": [],
                "socialLinks": [], "phoneLinks": [], "emailLinks": [], "whatsappLinks": [],
                "whatsappNumber": "", "tags": [], "publicAddresses": [], "contactPageCandidates": [], "textCharacters": 0,
                "robots": False, "sitemap": False, "seoScore": 5, "sslError": True,
                "issues": ["SSL certificate validation failed or the certificate has expired", message[:300]],
                "wins": [], "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "disclaimer": "SSL failure is a measured critical availability issue. Confirm from the target market before outreach."}
    if "html" not in content_type.lower() and "<html" not in html[:1000].lower():
        raise ValueError("The URL did not return an HTML page.")
    parser = AuditParser(final_url)
    parser.feed(html)
    contacts = extract_public_contact_signals(html, final_url)
    robots = endpoint_exists(final_url, "robots.txt")
    sitemap = endpoint_exists(final_url, "sitemap.xml")
    score, issues, wins = score_audit(status, final_url, parser, robots, sitemap)
    base_host = (urlparse(final_url).hostname or "").lower().removeprefix("www.")
    internal_urls, external_urls = [], []
    for link in sorted(parser.links):
        host = (urlparse(link).hostname or "").lower().removeprefix("www.")
        if host == base_host:
            internal_urls.append(link)
        else:
            external_urls.append(link)
    return {
        "ok": True,
        "requestedUrl": url,
        "status": status,
        "finalUrl": final_url,
        "elapsedSeconds": elapsed,
        "totalSeconds": round(time.monotonic() - started, 2),
        "title": parser.title,
        "titleLength": len(parser.title),
        "description": parser.description,
        "descriptionLength": len(parser.description),
        "h1Count": len(parser.h1),
        "h1": parser.h1[:3],
        "canonical": parser.canonical,
        "lang": parser.lang,
        "viewport": parser.viewport,
        "schemaBlocks": parser.schema_blocks,
        "schemaTypes": sorted(parser.schema_types),
        "wordCount": parser.text_words,
        "internalLinks": len(internal_urls),
        "externalLinks": len(external_urls),
        "internalLinkSamples": internal_urls[:24],
        "externalLinkSamples": external_urls[:16],
        "socialLinks": list(dict.fromkeys([*sorted(parser.social_links), *contacts["socialLinks"]]))[:20],
        "phoneLinks": list(dict.fromkeys([*sorted(parser.phone_links), *contacts["phoneNumbers"]]))[:20],
        "emailLinks": list(dict.fromkeys([*sorted(parser.email_links), *contacts["emails"]]))[:20],
        "whatsappLinks": contacts["whatsappLinks"],
        "whatsappNumber": contacts["whatsappNumber"],
        "tags": contacts["tags"],
        "publicAddresses": contacts["addresses"],
        "contactPageCandidates": contacts["contactPageCandidates"],
        "textCharacters": parser.text_chars,
        "robots": robots,
        "sitemap": sitemap,
        "seoScore": score,
        "issues": issues,
        "wins": wins,
        "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "disclaimer": "Single-route public audit. Recheck timeouts and availability from the target market."
    }


def provider_status():
    """Return configuration state without exposing credentials."""
    providers = {
        "whatsapp": bool(os.getenv("WHATSAPP_TOKEN") and os.getenv("WHATSAPP_PHONE_NUMBER_ID")),
        "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        "bale": bool(os.getenv("BALE_BOT_TOKEN")),
        "rubika": bool(os.getenv("RUBIKA_BOT_TOKEN")),
        "soroush": bool(os.getenv("SOROUSH_PARTNER_WEBHOOK_URL")),
        "eitaa": bool(os.getenv("EITAA_APP_TOKEN")),
        "email": bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM")),
        "sms": bool(os.getenv("SMS_WEBHOOK_URL") or twilio_sms_configured()),
        "divar": bool(os.getenv("DIVAR_PARTNER_WEBHOOK_URL")),
    }
    divar_slug = re.sub(r"[^a-zA-Z0-9_-]", "", os.getenv("DIVAR_APP_SLUG", ""))
    database = supabase_settings()
    webhook_database = bool(os.getenv("LEAD_DATABASE_WEBHOOK_URL") or os.getenv("LEAD_INGEST_WEBHOOK_URL"))
    return {
        "ok": True,
        "sendEnabled": SEND_ENABLED,
        "dryRun": DRY_RUN,
        "providers": providers,
        "smsProvider": "twilio" if twilio_sms_configured() else "webhook" if os.getenv("SMS_WEBHOOK_URL") else "none",
        "smsNorthAmericaA2PRegistered": env_flag("SMS_US_A2P_REGISTERED", False),
        "vendorSearchConfigured": bool(os.getenv("VENDOR_SEARCH_WEBHOOK_URL")),
        "clinicSearchConfigured": bool(os.getenv("CLINIC_SEARCH_WEBHOOK_URL") or os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")),
        "clinicSearchProviders": {
            "webhook": bool(os.getenv("CLINIC_SEARCH_WEBHOOK_URL")),
            "googlePlaces": bool(os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")),
            "brave": bool(os.getenv("BRAVE_SEARCH_API_KEY")),
        },
        "geminiConfigured": bool(get_gemini_keys()),
        "scraperConfigured": bool(scraper_allowed_domains()),
        "contactEnrichmentEnabled": True,
        "contactEnrichmentMaxPages": max(1, min(int(os.getenv("CONTACT_ENRICH_MAX_PAGES", "3")), 5)),
        "video": {
            "provider": os.getenv("VIDEO_PROVIDER", "adapter"),
            "scriptAiConfigured": bool(get_gemini_keys()),
            "renderConfigured": bool(os.getenv("VIDEO_RENDER_WEBHOOK_URL")),
            "statusConfigured": bool(os.getenv("VIDEO_RENDER_STATUS_WEBHOOK_URL")),
            "mode": "async-provider-adapter",
        },
        "leadDatabaseConfigured": bool(database["configured"] or webhook_database),
        "leadDatabaseProvider": "supabase" if database["configured"] else "webhook" if webhook_database else "none",
        "leadDatabaseTable": database["table"],
        "leadDatabaseDetectedVariables": {"url": database["urlVariable"], "key": database["keyVariable"]},
        "geminiModel": os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"),
        "proposalPdfMode": "direct-download" if PILLOW_AVAILABLE else "browser-print",
        "pdfTextEngine": "raqm" if RAQM_AVAILABLE else "arabic-reshaper+bidi" if BIDI_FALLBACK_AVAILABLE else "basic",
        "pdfLinkTtlSeconds": PDF_LINK_TTL,
        "pdfLinksEphemeral": True,
        "baleBot": {
            "mode": BALE_BOT_MODE,
            "tokenConfigured": bool(os.getenv("BALE_BOT_TOKEN", "").strip()),
            "webhookSecretConfigured": bool(BALE_WEBHOOK_SECRET),
            "stateFilePersistent": _bale_state_path() is not None,
        },
        "webApps": {
            "bale": "https://web.bale.ai",
            "rubika": "https://web.rubika.ir",
            "soroush": "https://web.splus.ir",
            "eitaa": "https://web.eitaa.com",
            "divar": f"https://divar.ir/chat/addon_{divar_slug}" if divar_slug else "https://divar.ir/",
        },
        "notes": {
            "whatsapp": "Official Meta Cloud API; opt-in and template/session rules apply.",
            "telegram": "The user must start the bot first, or the bot must have channel/group permission.",
            "bale": "Official Bale Bot API; the user must start the bot or authorize the conversation.",
            "rubika": "Official Rubika Bot API v3; chat_id and bot authorization are required.",
            "soroush": "Uses an operator-authorized Soroush Plus partner webhook.",
            "eitaa": "Uses the Eitaa application sendMessage API; token and permitted chat_id are required.",
            "email": "SMTP credentials remain server-side.",
            "sms": "Uses Twilio or an approved provider webhook. North American application-to-person messaging requires consent, sender registration and opt-out handling; Google Voice automation is not supported.",
            "divar": "Automatic sending is available only through an authorized Divar partner webhook; no scraping or browser automation.",
        },
    }


def rate_limit(channel: str, recipient: str):
    """Small-process safety limit: 5 sends/minute per channel+recipient, 30/minute total."""
    now = time.monotonic()
    keys = [f"recipient:{channel}:{hashlib.sha256(recipient.encode()).hexdigest()[:16]}", "global"]
    limits = [5, 30]
    for key, limit in zip(keys, limits):
        bucket = RATE_BUCKETS[key]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= limit:
            raise ValueError("Rate limit reached. Wait before sending again.")
    for key in keys:
        RATE_BUCKETS[key].append(now)


def get_gemini_keys():
    keys = []
    for index in range(1, 4):
        value = os.getenv(f"GEMINI_API_KEY{index}", "").strip()
        if value and value not in keys:
            keys.append(value)
    fallback = os.getenv("GEMINI_API_KEY", "").strip()
    if fallback and fallback not in keys:
        keys.append(fallback)
    return keys


def call_gemini(prompt: str, temperature: float = 0.65, max_tokens: int = 12000):
    keys = get_gemini_keys()
    if not keys:
        raise ValueError("No Gemini API key is configured. Add GEMINI_API_KEY1 or GEMINI_API_KEY.")
    model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    config = {"maxOutputTokens": max(1000, min(max_tokens, 16000)), "temperature": temperature}
    if os.getenv("GEMINI_USE_THINKING", "false").lower() == "true":
        config["thinkingConfig"] = {"thinkingLevel": "low"}
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}
    errors = []
    for number, key in enumerate(keys, 1):
        try:
            response = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                     json=payload, timeout=120)
            data = response.json() if response.text else {}
            if not response.ok:
                error = data.get("error", {}) if isinstance(data, dict) else {}
                status = str(error.get("status", ""))
                message = str(error.get("message", response.text or "Unknown Gemini error"))
                if response.status_code == 429 or status == "RESOURCE_EXHAUSTED" or "quota" in message.lower():
                    errors.append(f"key {number}: quota exhausted")
                    continue
                raise ValueError(f"Gemini API: {message[:500]}")
            candidates = data.get("candidates") or []
            if not candidates:
                raise ValueError("Gemini returned no candidate.")
            parts = ((candidates[0].get("content") or {}).get("parts") or [])
            text = "\n".join(str(part.get("text", "")) for part in parts
                             if isinstance(part, dict) and not part.get("thought") and part.get("text"))
            if not text.strip():
                raise ValueError("Gemini returned an empty article.")
            return text.strip(), number, model
        except requests.RequestException as exc:
            errors.append(f"key {number}: {type(exc).__name__}")
            continue
    raise ValueError("All Gemini keys failed or reached quota: " + "; ".join(errors))


def split_seo_keywords(raw: str):
    return [item.strip() for item in re.split(r"،|,|\s+-\s+", raw or "") if item.strip()][:12]


def keyword_occurrences(text: str, keyword: str):
    if not keyword:
        return 0
    return len(re.findall(re.escape(keyword), text, flags=re.IGNORECASE))


def build_article_prompt(data: dict, target: int, secondary: list[str], min_primary: int, max_primary: int,
                         min_secondary: int):
    language = data["language"]
    title = data["title"]
    outline = data["outline"]
    primary = data["primaryKeyword"]
    secondary_text = "، ".join(secondary) if secondary else "ندارد"
    rewrite = data.get("isRewrite") is True
    notes = str(data.get("rewriteNotes", "")).strip()[:1000]
    if language == "en":
        prompt = f"""You are a senior human SEO editor. Write a useful, natural, publication-ready article in English.

Title: {title}
Primary keyword: {primary}
Secondary keywords: {', '.join(secondary) if secondary else 'none'}
Required H2 outline (use every line exactly, in this exact order, without adding or rewriting headings):
{outline}

Requirements:
- Target {target} words, tolerance ±30 words.
- Use the exact primary keyword {min_primary} to {max_primary} times, naturally distributed, including once in the first 100 words.
- Use each secondary keyword at least {min_secondary} times when contextually relevant; never stuff keywords.
- After the introduction, add an H2 named exactly “Quick overview 👀”, two short sentences and a bullet list.
- For each supplied H2: a short introduction, useful main content, and a natural transition. Use H3 only where the H2 contains multiple distinct ideas.
- Prefer active voice, direct reader address, specific examples and practical guidance.
- Do not invent statistics, medical claims, certifications, prices, testimonials or sources.
- For medical topics, provide general educational information, avoid diagnosis or treatment promises, and add a short “Medical review required” note.
- Do not output an SEO report, analysis, preface, or code fence. Output only the article in Markdown.
"""
    else:
        prompt = f"""تو یک ویراستار حرفه‌ای و انسانی سئو هستی. یک مقاله کاربردی، طبیعی و آماده انتشار به زبان فارسی معیار بنویس.

عنوان: {title}
کلمه کلیدی اصلی: {primary}
کلمات کلیدی فرعی: {secondary_text}
Outline اجباری H2 (هر خط را دقیقاً با همین متن و همین ترتیب استفاده کن و عنوانی را تغییر نده):
{outline}

قواعد:
- طول هدف {target} کلمه با تلورانس حداکثر ±۳۰ کلمه.
- عبارت دقیق «{primary}» را بین {min_primary} تا {max_primary} بار، طبیعی و توزیع‌شده استفاده کن و یک بار در ۱۰۰ کلمه اول بیاور.
- هر کلمه فرعی مرتبط را حداقل {min_secondary} بار طبیعی استفاده کن؛ حشو کلمه ممنوع است.
- بعد از مقدمه یک H2 با عنوان دقیق «نگاه سریع 👀» شامل دو جمله کوتاه و یک فهرست نقطه‌ای اضافه کن.
- برای هر H2 داده‌شده: مقدمه کوتاه، محتوای ارزشمند و گذار طبیعی. فقط برای چند ایده مستقل H3 بساز.
- از لحن مستقیم، فعل معلوم، مثال مشخص و راهکار عملی استفاده کن.
- آمار، ادعای پزشکی، مجوز، قیمت، رضایت مشتری یا منبع ساختگی تولید نکن.
- در موضوعات پزشکی فقط اطلاعات آموزشی عمومی بده، تشخیص یا وعده درمان ارائه نکن و در پایان یادداشت کوتاه «نیازمند بازبینی پزشک» اضافه کن.
- گزارش سئو، توضیح فرایند، مقدمه خارج از مقاله یا code fence تولید نکن. فقط مقاله Markdown را برگردان.
"""
    if rewrite:
        prompt += (f"\nRewrite the article from scratch with a substantially different expression. Address this note: {notes or 'Improve clarity and naturalness'}.\n"
                   if language == "en" else
                   f"\nمقاله را از ابتدا با بیان کاملاً متفاوت بازنویسی کن و این ملاحظه را اعمال کن: {notes or 'شفافیت و طبیعی‌بودن متن بهتر شود'}.\n")
    return prompt


def article_report(article: str, data: dict, target: int, secondary: list[str]):
    words = [word for word in article.split() if word]
    word_count = len(words)
    primary = data["primaryKeyword"]
    primary_count = keyword_occurrences(article, primary)
    min_primary = math.ceil(max(word_count, 1) * 0.01)
    max_primary = max(min_primary, math.floor(max(word_count, 1) * 0.015))
    first_100 = " ".join(words[:100])
    report = {
        "wordCount": word_count,
        "targetWordCount": target,
        "wordCountPass": abs(word_count - target) <= 30,
        "primaryKeyword": primary,
        "primaryCount": primary_count,
        "primaryMin": min_primary,
        "primaryMax": max_primary,
        "density": round(primary_count / max(word_count, 1) * 100, 2),
        "primaryInFirst100": keyword_occurrences(first_100, primary) > 0,
        "secondary": [{"keyword": keyword, "count": keyword_occurrences(article, keyword)} for keyword in secondary],
    }
    return report


def generate_seo_article(payload: dict):
    language = str(payload.get("language", "fa")).lower()
    language = "en" if language == "en" else "fa"
    data = {
        "language": language,
        "title": str(payload.get("title", "")).strip()[:300],
        "outline": str(payload.get("outline", "")).strip()[:5000],
        "primaryKeyword": str(payload.get("primaryKeyword", "")).strip()[:250],
        "isRewrite": payload.get("isRewrite") is True,
        "rewriteNotes": str(payload.get("rewriteNotes", "")).strip()[:1000],
    }
    if not data["title"] or not data["outline"] or not data["primaryKeyword"]:
        raise ValueError("Title, outline and primary keyword are required.")
    try:
        target = int(payload.get("targetWordCount", 900))
    except (TypeError, ValueError):
        target = 900
    target = max(800, min(target, 1500))
    secondary = split_seo_keywords(str(payload.get("secondaryKeywords", "")))
    min_primary = math.ceil(target * 0.01)
    max_primary = max(min_primary, math.floor(target * 0.015))
    min_secondary = max(2, round(target / 900 * 3))
    prompt = build_article_prompt(data, target, secondary, min_primary, max_primary, min_secondary)
    article, key_number, model = call_gemini(prompt)
    article = re.sub(r"\n\s*\*\*\*\s*\n\s*#{2,3}\s*(SEO|سئو).*$", "", article, flags=re.IGNORECASE | re.DOTALL).strip()
    report = article_report(article, data, target, secondary)
    needs_correction = (abs(report["wordCount"] - target) > 70 or
                        report["primaryCount"] < report["primaryMin"] or
                        report["primaryCount"] > report["primaryMax"])
    corrected = False
    if needs_correction and os.getenv("GEMINI_AUTO_CORRECT", "true").lower() != "false":
        if language == "en":
            correction = f"""Revise the Markdown article below. Keep every existing H2 heading exactly unchanged. Reach {target} words ±30. Use the exact primary keyword “{data['primaryKeyword']}” between {min_primary} and {max_primary} times, naturally, and once in the first 100 words. Preserve factual caution and do not add fabricated claims. Return only the complete revised article.\n\n{article}"""
        else:
            correction = f"""مقاله Markdown زیر را اصلاح کن. تمام H2های موجود را دقیقاً بدون تغییر نگه دار. متن را به {target} کلمه با تلورانس ±۳۰ برسان. عبارت دقیق «{data['primaryKeyword']}» را بین {min_primary} تا {max_primary} بار طبیعی و یک بار در ۱۰۰ کلمه اول استفاده کن. احتیاط علمی را حفظ کن و ادعای ساختگی نساز. فقط متن کامل اصلاح‌شده را برگردان.\n\n{article}"""
        try:
            article, key_number, model = call_gemini(correction, temperature=0.45)
            report = article_report(article, data, target, secondary)
            corrected = True
        except Exception:
            corrected = False
    return {"ok": True, "article": article, "report": report, "language": language,
            "model": model, "keyNumber": key_number, "autoCorrected": corrected,
            "disclaimer": "AI-generated content requires human editorial review; medical content also requires qualified medical review."}


def parse_ai_json(text: str):
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Gemini did not return a JSON object.")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gemini returned invalid JSON: {exc.msg}") from exc


def deterministic_company_video_plan(company: dict, language: str, duration: int, objective: str) -> dict:
    name = str(company.get("name", "Business")).strip()[:180] or "Business"
    category = str(company.get("category", company.get("specialty", "business"))).strip()[:180]
    website = str(company.get("website", "")).strip()[:500]
    address = str(company.get("address", "")).strip()[:300]
    tags = company.get("tags", []) if isinstance(company.get("tags"), list) else []
    services = "، ".join(str(tag)[:60] for tag in tags[:5]) or category or ("خدمات عمومی" if language == "fa" else "public services")
    shot_count = 5
    base_duration, remainder = divmod(duration, shot_count)
    durations = [base_duration + (1 if index < remainder else 0) for index in range(shot_count)]
    if language == "en":
        narration = [
            f"Meet {name}.",
            f"The company publicly presents its work in {services}.",
            f"Its public business information is available through {website or 'its verified contact channels'}.",
            f"This introduction is based only on reviewed company information for the objective: {objective}.",
            f"To learn more, visit the official website or contact {name} through a verified business channel.",
        ]
        on_screen = [name, services, website or address or "Verified business information", "Human-reviewed company introduction", "Learn more"]
    else:
        narration = [
            f"با {name} آشنا شوید.",
            f"این مجموعه در اطلاعات عمومی خود، در حوزه {services} فعالیت می‌کند.",
            f"اطلاعات رسمی کسب‌وکار از طریق {website or 'کانال‌های تماس تأییدشده'} در دسترس است.",
            f"این معرفی فقط بر پایه اطلاعات بازبینی‌شده شرکت و با هدف «{objective}» تهیه شده است.",
            f"برای اطلاعات بیشتر، وب‌سایت رسمی یا کانال تماس تأییدشده {name} را بررسی کنید.",
        ]
        on_screen = [name, services, website or address or "اطلاعات عمومی تأییدشده", "معرفی بازبینی‌شده شرکت", "اطلاعات بیشتر"]
    visual_templates = [
        "Authorized logo or clean typographic company-name reveal; no invented logo",
        "Professional abstract service montage based only on the supplied categories and authorized assets",
        "Clean website and public-contact presentation; do not fabricate interfaces, awards or reviews",
        "Human-centered business operations montage without unverifiable performance or outcome claims",
        "Company name, official website/contact call-to-action and legal brand-safe closing frame",
    ]
    shots = []
    for index in range(shot_count):
        shots.append({
            "id": index + 1,
            "durationSeconds": durations[index],
            "visualPrompt": f"16:9 professional company introduction for {name}. {visual_templates[index]}. Consistent brand-neutral lighting, no text artifacts.",
            "narration": narration[index],
            "onScreenText": on_screen[index],
            "evidence": [value for value in (name, category, website, address) if value][:4],
        })
    return {
        "title": f"{name} — {'Company Introduction' if language == 'en' else 'ویدیوی معرفی شرکت'}",
        "language": language,
        "aspectRatio": "16:9",
        "durationSeconds": duration,
        "objective": objective,
        "narration": " ".join(narration),
        "shots": shots,
        "cta": narration[-1],
        "factualConstraints": [
            "Use only supplied public company facts and operator-authorized assets.",
            "Do not invent rankings, revenue, customers, awards, licenses, reviews or medical outcomes.",
            "Human approval and brand/media rights confirmation are required before rendering.",
        ],
    }


def normalize_company_video_plan(plan: dict, company: dict, language: str, duration: int, objective: str) -> dict:
    fallback = deterministic_company_video_plan(company, language, duration, objective)
    if not isinstance(plan, dict):
        return fallback
    shots = plan.get("shots") if isinstance(plan.get("shots"), list) else []
    clean_shots = []
    for index, shot in enumerate(shots[:8]):
        if not isinstance(shot, dict):
            continue
        try:
            shot_duration = max(3, min(15, int(shot.get("durationSeconds", 6))))
        except (TypeError, ValueError):
            shot_duration = 6
        clean_shots.append({
            "id": index + 1,
            "durationSeconds": shot_duration,
            "visualPrompt": str(shot.get("visualPrompt", ""))[:1200],
            "narration": str(shot.get("narration", ""))[:800],
            "onScreenText": str(shot.get("onScreenText", ""))[:180],
            "evidence": [str(x)[:300] for x in shot.get("evidence", [])[:6]] if isinstance(shot.get("evidence"), list) else [],
        })
    if not clean_shots:
        clean_shots = fallback["shots"]
    result = {
        **fallback,
        "title": str(plan.get("title", fallback["title"]))[:250],
        "narration": str(plan.get("narration", fallback["narration"]))[:5000],
        "shots": clean_shots,
        "cta": str(plan.get("cta", fallback["cta"]))[:800],
    }
    return result


def generate_company_video_plan(payload: dict):
    company = payload.get("company") if isinstance(payload.get("company"), dict) else {}
    if not str(company.get("name", "")).strip():
        raise ValueError("Company name is required for a video plan.")
    language = "en" if str(payload.get("language", "fa")).lower() == "en" else "fa"
    try:
        duration = max(30, min(60, int(payload.get("durationSeconds", 45))))
    except (TypeError, ValueError):
        duration = 45
    objective = str(payload.get("objective", "company introduction")).strip()[:500] or "company introduction"
    fallback = deterministic_company_video_plan(company, language, duration, objective)
    if not get_gemini_keys():
        return {
            "ok": True,
            "configured": False,
            "generator": "deterministic-draft",
            "plan": fallback,
            "disclaimer": "Gemini is not configured. This factual draft must be reviewed and can be regenerated with Gemini later.",
        }
    prompt = f"""Create a factual 30–60 second horizontal company-introduction video plan. Return JSON only.
Output language: {'English' if language == 'en' else 'Persian'}
Duration: {duration} seconds
Aspect ratio: 16:9
Objective: {objective}
Reviewed company data:
{json.dumps(company, ensure_ascii=False, indent=2)[:10000]}

Rules:
- Use only supplied facts. Never invent rankings, revenue, customer counts, awards, certifications, reviews, medical licenses, treatment outcomes or guarantees.
- For medical businesses, describe only public services and require qualified medical/brand review.
- Do not use patient information or imply endorsement.
- Assume logos, images and people may be used only after the operator confirms rights.
- Produce 4–8 shots whose durations total approximately {duration} seconds.
- Keep on-screen text short and avoid text inside generated imagery; text will be overlaid later.

Schema:
{{
  "title":"string",
  "narration":"string",
  "cta":"string",
  "shots":[{{
    "durationSeconds":6,
    "visualPrompt":"string",
    "narration":"string",
    "onScreenText":"string",
    "evidence":["exact supplied fact"]
  }}]
}}
"""
    raw, key_number, model = call_gemini(prompt, temperature=0.35, max_tokens=5000)
    plan = normalize_company_video_plan(parse_ai_json(raw), company, language, duration, objective)
    return {
        "ok": True,
        "configured": True,
        "generator": "gemini",
        "model": model,
        "keyNumber": key_number,
        "plan": plan,
        "disclaimer": "AI-generated script and prompts require factual, legal and brand-rights review before rendering.",
    }


def safe_public_media_url(value: str) -> str:
    candidate = str(value or "").strip()[:1000]
    try:
        parsed = urlparse(candidate)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return candidate
    except Exception:
        pass
    return ""


def submit_company_video_render(payload: dict):
    if payload.get("humanApproved") is not True:
        raise ValueError("Human approval of the script and storyboard is required.")
    if payload.get("brandRightsConfirmed") is not True:
        raise ValueError("Authorization for the company name, logo, people and uploaded media must be confirmed.")
    plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else None
    if not plan or not isinstance(plan.get("shots"), list):
        raise ValueError("An approved video plan with shots is required.")
    webhook = os.getenv("VIDEO_RENDER_WEBHOOK_URL", "").strip()
    provider = os.getenv("VIDEO_PROVIDER", "adapter").strip() or "adapter"
    if not webhook:
        return {
            "ok": True,
            "configured": False,
            "provider": provider,
            "status": "approved",
            "dryRun": True,
            "jobId": "",
            "outputUrl": "",
            "message": "Video plan approved. Configure VIDEO_RENDER_WEBHOOK_URL to submit it to Veo, fal.ai/Kling, Runway or another authorized renderer.",
        }
    token = os.getenv("VIDEO_RENDER_WEBHOOK_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status_code, response = post_json(webhook, {
        "source": "clinic-signal-company-video",
        "provider": provider,
        "company": payload.get("company", {}),
        "plan": plan,
        "referenceAssets": payload.get("referenceAssets", []),
        "callbackUrl": str(payload.get("callbackUrl", ""))[:500],
    }, headers, timeout=30)
    data = response if isinstance(response, dict) else {}
    return {
        "ok": True,
        "configured": True,
        "provider": provider,
        "providerStatus": status_code,
        "status": str(data.get("status", "queued"))[:40],
        "jobId": str(data.get("jobId", data.get("request_id", data.get("id", ""))))[:300],
        "outputUrl": safe_public_media_url(data.get("outputUrl", data.get("video_url", ""))),
        "providerResponse": data,
        "message": "Video render job submitted to the configured adapter.",
    }


def company_video_render_status(payload: dict):
    job_id = str(payload.get("jobId", "")).strip()[:300]
    if not job_id:
        raise ValueError("Video render jobId is required.")
    webhook = os.getenv("VIDEO_RENDER_STATUS_WEBHOOK_URL", "").strip()
    if not webhook:
        return {"ok": True, "configured": False, "status": "unknown", "jobId": job_id,
                "message": "Configure VIDEO_RENDER_STATUS_WEBHOOK_URL to refresh provider jobs."}
    token = os.getenv("VIDEO_RENDER_WEBHOOK_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status_code, response = post_json(webhook, {"jobId": job_id}, headers, timeout=25)
    data = response if isinstance(response, dict) else {}
    return {
        "ok": True,
        "configured": True,
        "providerStatus": status_code,
        "jobId": job_id,
        "status": str(data.get("status", "unknown"))[:40],
        "outputUrl": safe_public_media_url(data.get("outputUrl", data.get("video_url", ""))),
        "error": str(data.get("error", ""))[:1000],
        "providerResponse": data,
    }


def generate_ai_seo_review(payload: dict):
    language = "en" if str(payload.get("language", "fa")).lower() == "en" else "fa"
    lead = payload.get("lead") if isinstance(payload.get("lead"), dict) else {}
    supplied_audit = payload.get("audit") if isinstance(payload.get("audit"), dict) else None
    url = str(payload.get("url", "")).strip()
    if supplied_audit:
        measured = supplied_audit
    elif url:
        measured = audit(url)
    else:
        raise ValueError("A public URL or measured audit object is required.")

    evidence = {
        "requestedUrl": str(measured.get("requestedUrl", url))[:500],
        "finalUrl": str(measured.get("finalUrl", ""))[:500],
        "httpStatus": measured.get("status"),
        "measuredSeoScore": measured.get("seoScore"),
        "elapsedSeconds": measured.get("elapsedSeconds"),
        "title": str(measured.get("title", ""))[:300],
        "titleLength": measured.get("titleLength"),
        "description": str(measured.get("description", ""))[:600],
        "descriptionLength": measured.get("descriptionLength"),
        "h1Count": measured.get("h1Count"),
        "h1": measured.get("h1", [])[:5] if isinstance(measured.get("h1"), list) else [],
        "canonical": str(measured.get("canonical", ""))[:500],
        "schemaTypes": measured.get("schemaTypes", [])[:30] if isinstance(measured.get("schemaTypes"), list) else [],
        "internalLinks": measured.get("internalLinks"),
        "externalLinks": measured.get("externalLinks"),
        "internalLinkSamples": measured.get("internalLinkSamples", [])[:12] if isinstance(measured.get("internalLinkSamples"), list) else [],
        "socialLinks": measured.get("socialLinks", [])[:10] if isinstance(measured.get("socialLinks"), list) else [],
        "phoneLinks": measured.get("phoneLinks", [])[:8] if isinstance(measured.get("phoneLinks"), list) else [],
        "emailLinks": measured.get("emailLinks", [])[:8] if isinstance(measured.get("emailLinks"), list) else [],
        "textCharacters": measured.get("textCharacters"),
        "robots": measured.get("robots"),
        "sitemap": measured.get("sitemap"),
        "issues": measured.get("issues", [])[:12] if isinstance(measured.get("issues"), list) else [],
        "wins": measured.get("wins", [])[:10] if isinstance(measured.get("wins"), list) else [],
    }
    lead_context = {
        "name": str(lead.get("name", ""))[:180],
        "publicScale": str(lead.get("scale", ""))[:30],
        "area": str(lead.get("area", ""))[:300],
        "services": str(lead.get("services", ""))[:500],
        "existingOpportunityScore": lead.get("opportunity"),
    }
    output_language = "English" if language == "en" else "Persian"
    prompt = f"""You are a senior technical SEO strategist for medical-clinic websites. Analyze only the measured evidence below and return valid JSON, with every human-readable value in {output_language}.

MEASURED AUDIT EVIDENCE:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

PUBLIC LEAD CONTEXT (may be incomplete and must not be treated as verified revenue data):
{json.dumps(lead_context, ensure_ascii=False, indent=2)}

Rules:
- Separate measured facts from AI interpretation.
- Never invent Google positions, traffic, backlinks, revenue, patient numbers, licenses, reviews or medical outcomes.
- Never guarantee rank 1 or a treatment result.
- Treat publicScale as a rough sales segmentation label, not income.
- Medical content recommendations require qualified medical review.
- Prioritize fixes by evidence, impact and effort.
- opportunityScore is an advisory sales-fit score, not a factual business valuation.
- Budget ranges are editable planning estimates in Iranian toman.
- Outreach must be respectful, mention one evidence-based observation, ask permission to send a report and include a no-more-messages option.
- Return JSON only, with no Markdown fence.

Required JSON schema:
{{
  "executiveSummary": "string",
  "aiSeoScore": 0,
  "opportunityScore": 0,
  "confidence": "low|medium|high",
  "measuredFacts": ["string"],
  "issues": [{{"title":"string","severity":"critical|high|medium|low","evidence":"string","impact":"string","fix":"string","effort":"small|medium|large"}}],
  "quickWins": ["string"],
  "contentGaps": [{{"cluster":"string","intent":"commercial|informational|local","recommendedAssets":["string"]}}],
  "roadmap": {{"days1to30":["string"],"days31to60":["string"],"days61to90":["string"]}},
  "package": {{"name":"string","setupBudget":"string","monthlyFee":"string","mediaBudget":"string","duration":"string","reason":"string"}},
  "kpis": ["string"],
  "risksAndAssumptions": ["string"],
  "outreach": {{"whatsapp":"string","emailSubject":"string","emailBody":"string"}}
}}
"""
    raw, key_number, model = call_gemini(prompt, temperature=0.25, max_tokens=9000)
    analysis = parse_ai_json(raw)
    for score_key in ("aiSeoScore", "opportunityScore"):
        try:
            analysis[score_key] = max(0, min(100, int(analysis.get(score_key, 0))))
        except (TypeError, ValueError):
            analysis[score_key] = 0
    if analysis.get("confidence") not in {"low", "medium", "high"}:
        analysis["confidence"] = "low"
    return {
        "ok": True,
        "language": language,
        "measuredAudit": measured,
        "aiAnalysis": analysis,
        "model": model,
        "keyNumber": key_number,
        "disclaimer": "Measured audit fields are deterministic observations. AI scores and recommendations are advisory and require human validation."
    }


def analyze_clinic_candidates_ai(payload: dict):
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    if not items:
        raise ValueError("Select at least one clinic candidate for AI analysis.")
    language = "en" if str(payload.get("language", "fa")).lower() == "en" else "fa"
    compact = []
    for index, item in enumerate(items[:20]):
        if not isinstance(item, dict):
            continue
        compact.append({"index": index, "name": str(item.get("name", ""))[:220],
                        "website": str(item.get("website", ""))[:500],
                        "summary": str(item.get("summary", ""))[:700],
                        "currentType": str(item.get("resultType", "web-result"))[:80],
                        "specialty": str(item.get("specialty", ""))[:150],
                        "phone": str(item.get("phone", ""))[:100],
                        "address": str(item.get("address", ""))[:300]})
    output_language = "English" if language == "en" else "Persian"
    prompt = f"""You classify public web-search results for a medical-clinic lead database. Return JSON only. Write all explanatory strings in {output_language}.

Candidates:
{json.dumps(compact, ensure_ascii=False, indent=2)}

Rules:
- Do not claim a result is licensed, active or official without evidence.
- Distinguish an actual clinic/physician profile from a list article, price article, directory page or unrelated page.
- Normalize the display name by removing domains, URLs, breadcrumbs, year labels, marketing symbols and generic list prefixes.
- Do not infer patient traits, health conditions, income or medical outcomes.
- confidence is advisory based only on supplied title/URL/snippet.
- priority is for verification workflow, not medical quality.
- Return one result for every input index.

Schema:
{{"items":[{{"index":0,"normalizedName":"string","isLikelyMedicalClinic":true,"resultType":"official-clinic|physician-profile|directory-profile|list-article|price-article|unrelated|uncertain","specialty":"string","confidence":0,"priority":"high|medium|low","reason":"string","recommendedNextStep":"string"}}]}}
"""
    raw, key_number, model = call_gemini(prompt, temperature=0.15, max_tokens=7000)
    parsed = parse_ai_json(raw)
    results = parsed.get("items") if isinstance(parsed.get("items"), list) else []
    output = []
    valid_types = {"official-clinic", "physician-profile", "directory-profile", "list-article", "price-article", "unrelated", "uncertain"}
    for result in results[:20]:
        if not isinstance(result, dict):
            continue
        try:
            index = int(result.get("index"))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(compact):
            continue
        try:
            confidence = max(0, min(100, int(result.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0
        result_type = str(result.get("resultType", "uncertain"))
        if result_type not in valid_types:
            result_type = "uncertain"
        output.append({"index": index, "normalizedName": str(result.get("normalizedName", compact[index]["name"]))[:180],
                       "isLikelyMedicalClinic": bool(result.get("isLikelyMedicalClinic", False)),
                       "resultType": result_type, "specialty": str(result.get("specialty", compact[index]["specialty"]))[:150],
                       "confidence": confidence, "priority": str(result.get("priority", "medium"))[:20],
                       "reason": str(result.get("reason", ""))[:500],
                       "recommendedNextStep": str(result.get("recommendedNextStep", ""))[:500]})
    return {"ok": True, "items": output, "model": model, "keyNumber": key_number,
            "disclaimer": "AI classification is advisory. Verify identity, medical license, official ownership and contact data independently."}


def post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 20):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    hdr = {"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        hdr.update(headers)
    req = Request(url, data=body, headers=hdr, method="POST")
    opener = build_opener(SafeRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(500_000).decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw[:1000]}
            return int(response.status), data
    except HTTPError as exc:
        raw = exc.read(200_000).decode("utf-8", errors="replace")
        raise ValueError(f"Provider HTTP {exc.code}: {raw[:500]}")


def get_json(url: str, headers: dict | None = None, timeout: int = 20):
    hdr = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdr.update(headers)
    req = Request(url, headers=hdr, method="GET")
    opener = build_opener(SafeRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(1_000_000).decode("utf-8", errors="replace")
            return int(response.status), json.loads(raw)
    except HTTPError as exc:
        raw = exc.read(200_000).decode("utf-8", errors="replace")
        raise ValueError(f"Search provider HTTP {exc.code}: {raw[:500]}")


def post_multipart(url: str, fields: dict, file_field: str, filename: str, content_type: str,
                   file_bytes: bytes, headers: dict | None = None, timeout: int = 30):
    boundary = "----ClinicSignal" + hashlib.sha256(os.urandom(16)).hexdigest()[:24]
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend([f"--{boundary}\r\n".encode(),
                       f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                       str(value).encode("utf-8"), b"\r\n"])
    chunks.extend([f"--{boundary}\r\n".encode(),
                   f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(),
                   f"Content-Type: {content_type}\r\n\r\n".encode(), file_bytes, b"\r\n",
                   f"--{boundary}--\r\n".encode()])
    body = b"".join(chunks)
    hdr = {"User-Agent": USER_AGENT, "Accept": "application/json",
           "Content-Type": f"multipart/form-data; boundary={boundary}"}
    if headers:
        hdr.update(headers)
    req = Request(url, data=body, headers=hdr, method="POST")
    opener = build_opener(SafeRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(500_000).decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw[:1000]}
            return int(response.status), data
    except HTTPError as exc:
        raw = exc.read(200_000).decode("utf-8", errors="replace")
        raise ValueError(f"Provider HTTP {exc.code}: {raw[:500]}")


def send_email(recipient: str, message: str, subject: str, attachment: bytes | None = None,
               attachment_name: str = "proposal.pdf"): 
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM")
    if not host or not sender:
        raise ValueError("Email provider is not configured.")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    use_ssl = os.getenv("SMTP_SSL", "false").lower() == "true"
    email = EmailMessage()
    email["From"] = sender
    email["To"] = recipient
    email["Subject"] = subject or "Clinic Signal message"
    email.set_content(message)
    if attachment:
        email.add_attachment(attachment, maintype="application", subtype="pdf", filename=attachment_name)
    if use_ssl:
        smtp = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
    else:
        smtp = smtplib.SMTP(host, port, timeout=20)
        if os.getenv("SMTP_STARTTLS", "true").lower() != "false":
            smtp.starttls(context=ssl.create_default_context())
    try:
        if user:
            smtp.login(user, password)
        smtp.send_message(email)
    finally:
        smtp.quit()
    return {"accepted": True}


def twilio_sms_configured() -> bool:
    return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN") and
                (os.getenv("TWILIO_FROM_NUMBER") or os.getenv("TWILIO_MESSAGING_SERVICE_SID")))


def send_twilio_sms(recipient: str, message: str):
    sid = os.environ["TWILIO_ACCOUNT_SID"].strip()
    token = os.environ["TWILIO_AUTH_TOKEN"].strip()
    data = {"To": recipient, "Body": message}
    messaging_service = os.getenv("TWILIO_MESSAGING_SERVICE_SID", "").strip()
    if messaging_service:
        data["MessagingServiceSid"] = messaging_service
    else:
        data["From"] = os.environ["TWILIO_FROM_NUMBER"].strip()
    response = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                             data=data, auth=(sid, token), timeout=25)
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text[:1000]}
    if not response.ok:
        raise ValueError(f"Twilio SMS HTTP {response.status_code}: {str(body)[:500]}")
    return response.status_code, body


def send_message(payload: dict):
    channel = str(payload.get("channel", "")).lower().strip()
    recipient = str(payload.get("recipient", "")).strip()
    message = str(payload.get("message", "")).strip()
    subject = str(payload.get("subject", "")).strip()
    if channel not in ALLOWED_CHANNELS:
        raise ValueError("Unsupported channel.")
    if not recipient or not message:
        raise ValueError("Recipient and message are required.")
    if len(message) > 4000:
        raise ValueError("Message is longer than 4000 characters.")
    if payload.get("approved") is not True:
        raise ValueError("Human approval is required before sending.")
    if payload.get("consent") is not True:
        raise ValueError("Documented recipient consent or an existing service conversation is required.")
    if payload.get("senderAuthorized") is not True:
        raise ValueError("Authorization to represent the selected sender company is required.")
    if payload.get("doNotContact") is True:
        raise ValueError("Recipient is on the do-not-contact list.")
    if channel == "bale" and bale_is_opted_out(recipient):
        raise ValueError("Recipient is on the Bale do-not-contact list (they sent STOP to the bot).")
    if channel == "sms":
        normalized_recipient = "+" + re.sub(r"\D", "", recipient) if recipient.strip().startswith("+") else re.sub(r"\D", "", recipient)
        if len(re.sub(r"\D", "", normalized_recipient)) < 10:
            raise ValueError("SMS recipient must be a valid E.164-style business contact number.")
        recipient = normalized_recipient
        if recipient.startswith("+1") and "STOP" not in message.upper():
            message = message.rstrip() + "\n\n" + os.getenv("SMS_OPT_OUT_TEXT", "Reply STOP to opt out.")
    rate_limit(channel, recipient)

    recipient_hash = hashlib.sha256(recipient.encode("utf-8")).hexdigest()[:16]
    log = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "channel": channel,
           "recipientHash": recipient_hash, "leadId": str(payload.get("leadId", ""))[:80]}
    pdf_bytes = None
    pdf_filename = "proposal.pdf"
    requested_attachment = payload.get("attachProposalPdf") is True
    attach_pdf = requested_attachment and channel in {"whatsapp", "telegram", "bale", "email"}
    manual_attachment_required = requested_attachment and not attach_pdf
    if attach_pdf:
        proposal = payload.get("proposal") if isinstance(payload.get("proposal"), dict) else None
        if not proposal:
            raise ValueError("Proposal data is required for a PDF attachment.")
        pdf_bytes, pdf_filename = make_proposal_pdf(proposal)

    if DRY_RUN or not SEND_ENABLED:
        log.update(status="simulated", attachment=bool(pdf_bytes))
        SEND_LOG.appendleft(log)
        return {"ok": True, "sent": False, "dryRun": True, "status": "simulated",
                "attachmentReady": bool(pdf_bytes), "manualAttachmentRequired": manual_attachment_required,
                "validatedMessage": message,
                "message": "Validated successfully. Sending is disabled or DRY_RUN is active."}

    if manual_attachment_required:
        raise ValueError("Automatic PDF attachment is not configured for this channel. Download the PDF and use the official web app handoff.")
    configured = provider_status()["providers"]
    if not configured[channel]:
        raise ValueError(f"{channel.title()} provider is not configured.")

    if channel == "whatsapp":
        token = os.environ["WHATSAPP_TOKEN"]
        phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
        version = os.getenv("WHATSAPP_API_VERSION", "v23.0")
        url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
        auth = {"Authorization": f"Bearer {token}"}
        status, text_response = post_json(url, {"messaging_product": "whatsapp", "to": re.sub(r"\D", "", recipient),
                    "type": "text", "text": {"preview_url": False, "body": message}}, auth)
        response = {"text": text_response}
        if pdf_bytes:
            media_url = f"https://graph.facebook.com/{version}/{phone_id}/media"
            _, media_response = post_multipart(media_url, {"messaging_product": "whatsapp"}, "file",
                                                pdf_filename, "application/pdf", pdf_bytes, auth)
            media_id = media_response.get("id") if isinstance(media_response, dict) else None
            if not media_id:
                raise ValueError("WhatsApp media upload did not return a media id.")
            doc_status, doc_response = post_json(url, {"messaging_product": "whatsapp",
                "to": re.sub(r"\D", "", recipient), "type": "document",
                "document": {"id": media_id, "filename": pdf_filename}}, auth)
            status = doc_status
            response["document"] = doc_response
    elif channel == "telegram":
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        status, text_response = post_json(url, {"chat_id": recipient, "text": message, "disable_web_page_preview": True})
        response = {"text": text_response}
        if pdf_bytes:
            doc_url = f"https://api.telegram.org/bot{token}/sendDocument"
            doc_status, doc_response = post_multipart(doc_url, {"chat_id": recipient}, "document",
                                                       pdf_filename, "application/pdf", pdf_bytes)
            status = doc_status
            response["document"] = doc_response
    elif channel == "bale":
        token = os.environ["BALE_BOT_TOKEN"]
        base = f"https://tapi.bale.ai/bot{token}"
        status, text_response = post_json(base + "/sendMessage", {"chat_id": recipient, "text": message})
        response = {"text": text_response}
        if pdf_bytes:
            doc_status, doc_response = post_multipart(base + "/sendDocument", {"chat_id": recipient},
                                                       "document", pdf_filename, "application/pdf", pdf_bytes)
            status = doc_status
            response["document"] = doc_response
    elif channel == "rubika":
        token = os.environ["RUBIKA_BOT_TOKEN"]
        url = f"https://botapi.rubika.ir/v3/{token}/sendMessage"
        status, response = post_json(url, {"chat_id": recipient, "text": message})
    elif channel == "soroush":
        url = os.environ["SOROUSH_PARTNER_WEBHOOK_URL"]
        token = os.getenv("SOROUSH_PARTNER_TOKEN", "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        status, response = post_json(url, {"recipient": recipient, "message": message}, headers)
    elif channel == "eitaa":
        status, response = post_json("https://eitaayar.ir/api/app/sendMessage", {
            "token": os.environ["EITAA_APP_TOKEN"], "chat_id": recipient, "text": message})
    elif channel == "email":
        response = send_email(recipient, message, subject, pdf_bytes, pdf_filename)
        status = 200
    elif channel == "sms":
        if recipient.startswith("+1") and not env_flag("SMS_US_A2P_REGISTERED", False):
            raise ValueError("North American SMS sending is disabled until SMS_US_A2P_REGISTERED=true and the sender campaign is approved.")
        provider = os.getenv("SMS_PROVIDER", "twilio" if twilio_sms_configured() else "webhook").strip().lower()
        if provider == "twilio":
            if not twilio_sms_configured():
                raise ValueError("Twilio SMS is not fully configured.")
            status, response = send_twilio_sms(recipient, message)
        else:
            url = os.environ["SMS_WEBHOOK_URL"]
            headers = {"Authorization": f"Bearer {os.getenv('SMS_WEBHOOK_TOKEN', '')}"} if os.getenv("SMS_WEBHOOK_TOKEN") else {}
            status, response = post_json(url, {"to": recipient, "message": message,
                                                "sender": os.getenv("SMS_SENDER", "")}, headers)
    elif channel == "divar":  # Authorized Kenar-e-Divar middleware only
        url = os.environ["DIVAR_PARTNER_WEBHOOK_URL"]
        headers = {"Authorization": f"Bearer {os.getenv('DIVAR_PARTNER_TOKEN', '')}"} if os.getenv("DIVAR_PARTNER_TOKEN") else {}
        status, response = post_json(url, {"conversation_id": recipient, "message": message,
                                           "app_slug": os.getenv("DIVAR_APP_SLUG", "")}, headers)
    else:
        raise ValueError("Channel adapter is not implemented.")

    log.update(status="sent", providerStatus=status)
    SEND_LOG.appendleft(log)
    return {"ok": True, "sent": True, "dryRun": False, "status": "sent", "providerStatus": status,
            "providerResponse": response}


# ---------------------------------------------------------------------------
# Interactive Bale bot
#
# Receives messages via /api/bale/webhook (recommended) or optional long polling
# (BALE_BOT_MODE=polling on long-running hosts only, e.g. the HF Space Docker image).
# Bot replies answer a user-initiated service conversation, so they do NOT require
# the /api/send outreach approval gates — but they still respect DRY_RUN /
# SEND_ENABLED, per-chat rate limits, and the do-not-contact (STOP) list.
# The bot never initiates contact and throttled/silent behaviours are deliberate.
# ---------------------------------------------------------------------------

BALE_BOT_MODE = os.getenv("BALE_BOT_MODE", "webhook").strip().lower() or "webhook"
BALE_WEBHOOK_SECRET = os.getenv("BALE_WEBHOOK_SECRET", "").strip()
BALE_STATE_FILE = os.getenv("BALE_BOT_STATE_FILE", str(ROOT / "data" / "bale_bot_state.json")).strip()
BALE_STATE_LIMIT = 10_000
_BALE_STATE: dict = {"optedIn": {}, "optedOut": {}, "updateOffset": 0}
_BALE_STATE_LOADED = False
_BALE_STATE_LOCK = threading.Lock()
BALE_INBOX: deque[dict] = deque(maxlen=200)  # operator view of inbound bot messages

BALE_STOP_WORDS = {"stop", "/stop", "unsubscribe", "cancel", "توقف", "لغو", "لغو پیام", "لغوپیام", "پایان"}
BALE_START_WORDS = {"/start", "start", "شروع"}
BALE_HELP_WORDS = {"/help", "help", "راهنما", "کمک"}
BALE_STATUS_WORDS = {"/status", "وضعیت"}
BALE_PROPOSAL_WORDS = {"پروپوزال", "پیشنهاد", "قیمت", "pdf", "/proposal"}
BALE_TURKEY_WORDS = {"ترکیه", "تورکیه", "تورکيه", "istanbul", "استانبول", "/turkey"}
BALE_TURKEY_BIDS_WORDS = {"فراخوان", "فراخوانها", "بید", "بیدها", "مناقصه", "/bids", "/turkey-bids"}
BALE_TURKEY_SUPPLY_WORDS = {"تأمین", "تامین", "سود تامین", "سود تأمین", "/supply"}
BALE_URL_PATTERN = re.compile(
    r"(?i)(?:https?://[^\s<>\"'\u200c]+|(?:www\.)?[a-z0-9][a-z0-9-]{0,62}(?:\.[a-z0-9][a-z0-9-]{0,62})+(?:/[^\s<>\"'\u200c]*)?)")


def bale_bot_enabled() -> bool:
    return BALE_BOT_MODE in {"webhook", "polling"}


def bale_bot_state_summary() -> dict:
    _bale_load_state()
    return {"optedIn": len(_BALE_STATE["optedIn"]), "optedOut": len(_BALE_STATE["optedOut"]),
            "mode": BALE_BOT_MODE, "updateOffset": int(_BALE_STATE.get("updateOffset") or 0)}


def _bale_state_path() -> Path | None:
    if not BALE_STATE_FILE:
        return None
    try:
        path = Path(BALE_STATE_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        return None


def _bale_load_state():
    global _BALE_STATE_LOADED
    with _BALE_STATE_LOCK:
        if _BALE_STATE_LOADED:
            return
        _BALE_STATE_LOADED = True
        path = _bale_state_path()
        if path and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for key in ("optedIn", "optedOut"):
                        if isinstance(data.get(key), dict):
                            _BALE_STATE[key] = {str(k): v for k, v in data[key].items()
                                                if isinstance(v, dict)}
                    _BALE_STATE["updateOffset"] = int(data.get("updateOffset", 0) or 0)
            except Exception:
                pass  # A corrupt state file must never take the bot down.


def _bale_save_state():
    path = _bale_state_path()
    if not path:
        return
    try:
        payload = {**_BALE_STATE, "savedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass  # Read-only filesystems (serverless) simply keep in-memory state.


def _bale_state_set(map_name: str, chat_id: str, record: dict | None):
    _bale_load_state()
    with _BALE_STATE_LOCK:
        bucket = _BALE_STATE[map_name]
        if record is None:
            bucket.pop(chat_id, None)
        else:
            if len(bucket) >= BALE_STATE_LIMIT:
                oldest = sorted(bucket, key=lambda k: str(bucket[k].get("at", "")))[:512]
                for key in oldest:
                    bucket.pop(key, None)
            bucket[chat_id] = record
        _bale_save_state()


def bale_is_opted_out(chat_id) -> bool:
    _bale_load_state()
    return str(chat_id).strip() in _BALE_STATE["optedOut"]


def bale_opt_in(chat_id, name: str = "", username: str = "") -> dict:
    chat_id = str(chat_id).strip()
    _bale_load_state()
    returning = chat_id in _BALE_STATE["optedIn"] or chat_id in _BALE_STATE["optedOut"]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _bale_state_set("optedOut", chat_id, None)
    _bale_state_set("optedIn", chat_id, {"at": now, "name": str(name)[:80], "username": str(username)[:80]})
    return {"optedIn": True, "returning": returning}


def bale_opt_out(chat_id) -> dict:
    chat_id = str(chat_id).strip()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _bale_state_set("optedIn", chat_id, None)
    _bale_state_set("optedOut", chat_id, {"at": now})
    return {"optedOut": True}


def bale_api(method: str, payload: dict | None = None, timeout: int = 20):
    token = os.getenv("BALE_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BALE_BOT_TOKEN is not configured. Create the bot inside Bale and store the token as a hosting secret.")
    return post_json(f"https://tapi.bale.ai/bot{token}/{method}", payload or {}, timeout=timeout)


def bale_reply(chat_id, text: str) -> dict:
    """Reply to a user-initiated bot conversation. Respects STOP list, rate limits
    and the global DRY_RUN/SEND_ENABLED safety switches."""
    chat_id = str(chat_id).strip()
    if not re.fullmatch(r"-?\d{3,20}", chat_id):
        raise ValueError("Invalid Bale chat id.")
    if bale_is_opted_out(chat_id):
        return {"ok": False, "sent": False, "skipped": "opted-out"}
    rate_limit("bale", chat_id)
    recipient_hash = hashlib.sha256(chat_id.encode("utf-8")).hexdigest()[:16]
    log = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "channel": "bale",
           "recipientHash": recipient_hash, "leadId": "", "via": "bot-reply", "attachment": False}
    if DRY_RUN or not SEND_ENABLED:
        log["status"] = "simulated"
        SEND_LOG.appendleft(log)
        return {"ok": True, "sent": False, "dryRun": True, "status": "simulated"}
    status, response = bale_api("sendMessage", {"chat_id": int(chat_id), "text": text[:4000]}, timeout=20)
    log["status"] = "sent" if status < 400 else f"http-{status}"
    SEND_LOG.appendleft(log)
    return {"ok": status < 400, "sent": status < 400, "dryRun": False,
            "status": "sent" if status < 400 else "failed", "providerStatus": status, "providerResponse": response}


def _bale_normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(DIGIT_TRANSLATION)).strip().lower().replace("ي", "ی").replace("ك", "ک")


def _bale_extract_phone(text: str) -> str | None:
    for candidate in re.findall(r"(?:\+?98|0)?[\d\s\-()]{9,16}", text):
        digits = re.sub(r"\D", "", candidate)
        if re.fullmatch(r"9\d{9}", digits):
            return "0" + digits
        if re.fullmatch(r"989\d{9}", digits):
            return "0" + digits[2:]
        if re.fullmatch(r"0\d{10}", digits):
            return digits
    return None


def _bale_extract_url(text: str) -> str | None:
    match = BALE_URL_PATTERN.search(text)
    if not match:
        return None
    candidate = match.group(0).rstrip(").،؛!؟")
    host = urlparse(candidate if "://" in candidate else "https://" + candidate).hostname or ""
    return candidate if "." in host else None


def bale_set_webhook(base_url: str):
    base = base_url.strip().rstrip("/")
    if not base.startswith(("https://", "http://")):
        raise ValueError("A public base URL is required (set PUBLIC_BASE_URL or pass an explicit url).")
    payload = {"url": f"{base}/api/bale/webhook", "allowed_updates": ["message"]}
    if BALE_WEBHOOK_SECRET:
        # Telegram-compatible: Bale echoes this back via the X-Bale-Bot-Api-Secret-Token header.
        payload["secret_token"] = BALE_WEBHOOK_SECRET
    return bale_api("setWebhook", payload, timeout=30)


def bale_webhook_secret_ok(raw_target: str, headers) -> bool:
    if not BALE_WEBHOOK_SECRET:
        return True
    provided = parse_qs(urlparse(raw_target).query).get("s", [""])[0]
    candidates = [provided]
    if headers is not None:
        candidates.append(str(headers.get("X-Bale-Bot-Api-Secret-Token", "")))
        candidates.append(str(headers.get("X-Telegram-Bot-Api-Secret-Token", "")))
    return any(c and hmac.compare_digest(c, BALE_WEBHOOK_SECRET) for c in candidates)


BALE_WELCOME_BODY = (
    "این ربات برای پاسخ‌گویی سریع به صاحبان کسب‌وکار فعال است.\n\n"
    "دستورهای موجود:\n"
    "• ارسال آدرس وب‌سایت ← ممیزی فوری سئو و دریافت امتیاز\n"
    "• ارسال شماره تماس ← ثبت درخواست تماس کارشناس\n"
    "• «پروپوزال» ← نحوه دریافت پیشنهاد همکاری\n"
    "• «ترکیه» ← فرصت‌های تأمین کلینیک‌های ترکیه\n"
    "• /status ← وضعیت اشتراک شما\n"
    "• /stop ← توقف کامل دریافت پیام\n\n"
    "پیام شما فقط برای پاسخ به همین گفت‌وگو استفاده می‌شود و بدون رضایت شما هیچ پیام تبلیغاتی ارسال نمی‌کنیم.")
BALE_HELP_BODY = ("کافی است آدرس وب‌سایت کسب‌وکارتان را بفرستید تا امتیاز و مهم‌ترین مشکلات سئوی آن را همین‌جا ببینید. "
                  "برای درخواست تماس کارشناس، شماره موبایل یا تلفن ثابت خود را بفرستید. "
                  "بازار ترکیه: «ترکیه» — مقایسه قیمت تأمین‌کنندگان: «قیمت مرغ» — برنامه خرید هوشمند: «سبد خرید: مرغ 200، روغن 40». "
                  "برای توقف دریافت پیام: /stop")
BALE_PROPOSAL_BODY = ("پیشنهادهای همکاری پس از بررسی انسانی، ثبت رضایت و تأیید نهایی توسط کارشناس ما ارسال می‌شود؛ "
                      "ربات به‌تنهایی پیشنهاد قیمت صادر نمی‌کند. اگر وب‌سایت یا شماره تماس خود را بفرستید وارد فرایند بررسی می‌شوید. "
                      "لینک PDF پیشنهادها موقت، امضاشده و غیرقابل پیش‌بینی است.")


def bale_process_update(update: dict):
    """Handle one Bale Bot API update object. Returns an action summary; the same
    summary is the webhook HTTP response body."""
    if not isinstance(update, dict):
        raise ValueError("Invalid update payload.")
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict) or not message:
        return {"ok": True, "ignored": True, "reason": "no-message"}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = str(chat.get("id", "")).strip()
    if not chat_id:
        return {"ok": True, "ignored": True, "reason": "no-chat"}
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    name = " ".join(x for x in [str(sender.get("first_name", "")).strip(), str(sender.get("last_name", "")).strip()] if x).strip()
    name = name[:80] or str(sender.get("username", ""))[:80] or "کاربر"
    username = str(sender.get("username", ""))[:80]
    text = str(message.get("text", "") or "").strip()
    normalized = _bale_normalize(text)
    actions: list[dict] = []
    kind = "text"

    def record():
        BALE_INBOX.appendleft({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "chatId": chat_id, "name": name, "username": username,
                               "text": text[:300], "kind": kind})

    def reply(body: str):
        result = bale_reply(chat_id, body)
        actions.append({"type": "reply", "status": result.get("status") or result.get("skipped", "?"),
                        "dryRun": result.get("dryRun", False), "chars": len(body),
                        "preview": body[:160]})  # bot-generated text; lets operators verify behaviour
        return result

    if not text:
        return {"ok": True, "ignored": True, "reason": "empty-text"}

    # STOP always works — even when already opted out or the bot is disabled.
    if normalized in BALE_STOP_WORDS:
        kind = "stop"
        record()
        reply("✅ دریافت پیام برای شما غیرفعال شد؛ دیگر هیچ پیامی از این ربات نمی‌گیرید. برای شروع دوباره کافی است /start را بفرستید.")
        bale_opt_out(chat_id)  # opt out AFTER the confirmation reply, or it would be self-blocked
        return {"ok": True, "actions": actions, "optedOut": True}

    # /start re-activates a previously stopped conversation.
    if normalized in BALE_START_WORDS:
        kind = "start"
        if not bale_bot_enabled():
            return {"ok": False, "error": "Bale bot is disabled (BALE_BOT_MODE=off)."}
        state = bale_opt_in(chat_id, name, username)
        record()
        reply(f"سلام {name} عزیز 👋 به ربات «سیگنال کلینیک» خوش آمدید.\n\n" + BALE_WELCOME_BODY)
        return {"ok": True, "actions": actions, "optedIn": True, "returning": state.get("returning", False)}

    # Opted-out conversations stay silent (compliance: no messaging after STOP).
    if bale_is_opted_out(chat_id):
        record()
        return {"ok": True, "actions": [{"type": "silenced", "reason": "opted-out"}], "optedOut": True}

    if not bale_bot_enabled():
        return {"ok": False, "error": "Bale bot is disabled (BALE_BOT_MODE=off)."}

    try:
        if normalized in BALE_HELP_WORDS:
            kind = "help"
            record()
            reply(BALE_HELP_BODY)
            return {"ok": True, "actions": actions}

        if normalized in BALE_STATUS_WORDS:
            kind = "status"
            summary = bale_bot_state_summary()
            send_state = "فعال (ارسال واقعی)" if (SEND_ENABLED and not DRY_RUN) else "شبیه‌سازی (Dry Run)"
            _bale_load_state()
            sub_state = "مشترک ✅" if chat_id in _BALE_STATE["optedIn"] else "ثبت‌نام نشده (برای شروع: /start)"
            record()
            reply(f"وضعیت اشتراک شما: {sub_state}\nحالت ارسال سرویس: {send_state}\nکاربران متصل: {summary['optedIn']} · لغوشده: {summary['optedOut']}")
            return {"ok": True, "actions": actions}

        if normalized in BALE_PROPOSAL_WORDS:
            kind = "proposal"
            record()
            reply(BALE_PROPOSAL_BODY)
            return {"ok": True, "actions": actions}

        if normalized in BALE_TURKEY_WORDS:
            kind = "turkey"
            record()
            clinics = turkey_opportunities("clinics")
            resto = turkey_opportunities("restaurants")
            reply("🇹🇷 نقشه فرصت‌های تأمین ترکیه (استانبول)\n"
                  f"🏥 کلینیک‌ها: {clinics['summary']['regionCount']} منطقه · {clinics['summary']['consumableCategories']} دسته ملزومات · {clinics['summary']['activeBids']} بید\n"
                  f"🍽 رستوران‌ها: {resto['summary']['regionCount']} منطقه (باغجیلار و...) · {resto['summary']['consumableCategories']} ماده اولیه · {resto['summary']['activeBids']} بید (نمونه آموزشی)\n\n"
                  "دستورها:\n"
                  "• «فراخوانها» ← بیدهای کلینیک‌ها · «بید رستوران» ← بیدهای رستوران‌ها\n"
                  "• «تأمین» ← پیشنهاد تأمین کلینیک · «تأمین رستوران» ← پیشنهاد مواد اولیه رستوران\n"
                  "• «رستوران ترکیه» ← نمای کلی بازار غذا · «تأمین‌کنندگان» ← پنل تأمین‌کننده‌ها\n"
                  "• «قیمت مرغ» ← مقایسه قیمت · «سبد خرید: مرغ 200، روغن 40» ← برنامه خرید هوشمند")
            return {"ok": True, "actions": actions}

        # Turkey B2B supplier marketplace: directory, price compare, smart cart.
        if any(k in normalized for k in ("تامین‌کن", "تأمین‌کن", "تامین کن", "تأمین کن", "supplier", "/suppliers")):
            kind = "turkey-suppliers"
            record()
            data = turkey_suppliers_list("restaurants")
            rows = sorted(data["suppliers"], key=lambda s: (-(s["ratingAvg"] or 0), -s["productCount"]))[:6]
            lines = []
            for i, s in enumerate(rows, 1):
                stars = f"⭐ {s['ratingAvg']}/۵ ({s['ratingCount']} رأی)" if s["ratingAvg"] else "بدون امتیاز"
                lines.append(f"{i}) {s['name'][:34]} · {s['regionFa']}\n{s['productCount']} محصول · {stars} · 📞 {s['phone'] or '—'}")
            note = " (شامل نمونه‌های آموزشی با تماس ساختگی)" if data.get("samplesNote") else ""
            reply("🏪 تأمین‌کنندگان مواد غذایی رستوران‌های استانبول:\n\n" + "\n".join(lines) +
                  f"\n\nمجموع {data['count']} تأمین‌کننده{note} — فهرست کامل: GET /api/turkey/suppliers\n"
                  "💲 مقایسه قیمت: «قیمت مرغ» · 🛒 برنامه خرید: «سبد خرید: مرغ 200، روغن 40»")
            return {"ok": True, "actions": actions}

        if normalized.startswith(("قیمت ", "/price")) and len(normalized) >= 6:
            kind = "turkey-compare"
            record()
            cat_text = (normalized[5:] if normalized.startswith("قیمت ") else normalized[6:]).strip(" :،,")
            try:
                cmp_data = turkey_compare_prices(cat_text, "restaurants")
            except ValueError:
                reply(f"دسته‌ای مطابق «{cat_text[:30]}» پیدا نشد. مثال: «قیمت مرغ»، «قیمت روغن»، «قیمت برنج»، «قیمت گوشت»، «قیمت سبزیجات».")
                return {"ok": True, "actions": actions}
            if not cmp_data["offers"]:
                reply(f"برای «{cmp_data['category']['fa']}» هنوز تأمین‌کننده‌ای قیمت ثبت نکرده است.")
                return {"ok": True, "actions": actions}
            lines = []
            for i, o in enumerate(cmp_data["offers"][:4], 1):
                stars = f" · ⭐{o['ratingAvg']}" if o["ratingAvg"] else ""
                zone = "" if o["deliversHere"] else " · ⛔ محدوده تحویل محدود"
                lines.append(f"{i}) {o['supplier'][:30]} — {o['priceTry']:,.1f} لیر/{o['unit']} · حداقل {o['minOrder']} · تحویل {o['deliveryDays']} روز{stars}{zone}")
            st = cmp_data["stats"]
            reco = cmp_data.get("recommendation")
            reco_line = f"\n⭐ پیشنهاد: {reco['supplier'][:30]} ({reco['reason']})" if reco else ""
            reply(f"💲 مقایسه قیمت «{cmp_data['category']['fa'].split(' (')[0]}» بین {st['offerCount']} تأمین‌کننده:\n\n" + "\n".join(lines) +
                  f"\n\nکف {st['min']:,.0f} · سقف {st['max']:,.0f} · میانگین {st['avg']:,.0f} لیر (پراکندگی {st['spreadPct']}٪)" + reco_line +
                  "\n\nقیمت‌ها اعلامی تأمین‌کنندگان‌اند و ممکن است نمونه آموزشی باشند؛ قبل از سفارش تأیید کنید. جزئیات: GET /api/turkey/compare?category=" + cmp_data["category"]["id"])
            return {"ok": True, "actions": actions}

        if normalized.startswith(("سبد خرید", "خرید هوشمند", "/cart", "سبد")):
            kind = "turkey-cart"
            record()
            rest = normalized
            for prefix in ("سبد خرید", "خرید هوشمند", "/cart", "سبد"):
                if rest.startswith(prefix):
                    rest = rest[len(prefix):].strip(" :،,")
                    break
            try:
                plan = turkey_smart_plan({"market": "restaurants", "text": rest})
            except ValueError:
                reply("لیست خرید را با مقدار بنویسید؛ مثلاً:\n«سبد خرید: مرغ 200، روغن 40، برنج 150»\nربات برای هر قلم ارزان‌ترین تأمین‌کننده مناسب را پیشنهاد می‌دهد.")
                return {"ok": True, "actions": actions}
            lines = []
            for line in plan["lines"][:6]:
                for p in line["picks"][:2]:
                    note = f" ⚠️{p['note']}" if p.get("note") else ""
                    lines.append(f"• {line['categoryFa'].split(' (')[0]}: {p['qty']} {p['unit']} از {p['supplier'][:28]} — {p['lineTotal']:,.0f} لیر{note}")
            t = plan["totals"]
            saving = t["estimatedSavingsVsAvg"]
            saving_txt = (f"صرفه‌جویی ~{abs(saving):,.0f} لیر نسبت به میانگین بازار" if saving >= 0
                          else f"~{abs(saving):,.0f} لیر بالاتر از میانگین (به‌خاطر حداقل سفارش)")
            warn = ("\n⚠️ " + "\n⚠️ ".join(plan["warnings"][:2])) if plan["warnings"] else ""
            reply("🛒 برنامه خرید هوشمند (ارزان‌ترین تأمین‌کننده برای هر قلم):\n\n" + "\n".join(lines) +
                  f"\n\nجمع کل: {t['grandTotal']:,.0f} لیر · میانگین بازار: {t['avgMarketTotal']:,.0f} لیر · {saving_txt}" + warn +
                  "\n\nاین پیشنهاد برنامه‌ریزی بر اساس قیمت‌های اعلامی (شامل نمونه آموزشی با تماس ساختگی) است، نه سفارش قطعاتی. API: POST /api/turkey/smart-plan")
            return {"ok": True, "actions": actions}

        is_restaurant = "رستوران" in normalized
        has_bid_key = any(k in normalized for k in ("فراخوان", "بید", "مناقصه"))
        has_supply_key = any(k in normalized for k in ("تأمین", "تامین"))

        if is_restaurant and has_supply_key:
            kind = "turkey-restaurant-supply"
            record()
            opp = turkey_opportunities("restaurants")
            lines = []
            for i, c in enumerate(opp["topPicks"][:6], 1):
                flag = f" ⚠️{c['certNote']}" if c.get("certNote") else ""
                pull = f" · {c['activeBids']} بید فعال" if c["activeBids"] else ""
                lines.append(f"{i}) {c['fa']} — مصرف {c['consumption']}/۵ · حاشیه ~{c['margin'][0]}-{c['margin'][1]}٪{pull}{flag}")
            reply("🧭 پیشنهاد تأمین مواد اولیه رستوران‌های استانبول (مصرف × سود):\n\n" + "\n".join(lines) +
                  "\n\nتوضیح: ارقام تقریبی برای اولویت‌بندی‌اند؛ برای گوشت/مرغ/لبنیات گواهی حلال و زنجیره سرد را لحاظ کنید.")
            return {"ok": True, "actions": actions}

        if is_restaurant and has_bid_key:
            kind = "turkey-restaurant-bids"
            record()
            scored = sorted((turkey_score_bid(b) for b in TURKEY_BIDS if b["market"] == "restaurants"),
                            key=lambda b: -b["opportunityScore"])[:3]
            if not scored:
                reply("بیدی برای رستوران‌ها ثبت نشده است. با POST /api/turkey/bids/seed-samples صد بید نمونه بارگذاری کنید یا با POST /api/turkey/bids/import وارد کنید.")
            else:
                blocks = []
                for i, b in enumerate(scored, 1):
                    blocks.append(f"{i}) 🍽 {b['clinic'][:40]} · {b['regionFa']}\nنیاز: {b['need'][:80]}\n"
                                  f"امتیاز: {b['opportunityScore']}/۱۰۰ ({b['grade']}) · تعداد {b.get('quantity') or '—'} · بودجه ~{int(b.get('budgetTry') or 0):,} لیر · ددلاین {b.get('deadline') or '—'}\n"
                                  f"📞 {b.get('contact') or '—'}")
                reply("📋 داغ‌ترین بیدهای رستوران‌های استانبول:\n\n" + "\n\n".join(blocks) +
                      f"\n\nمجموع {sum(1 for b in TURKEY_BIDS if b['market']=='restaurants')} بید (نمونه آموزشی با تماس ساختگی) — فهرست کامل: GET /api/turkey/opportunities?market=restaurants")
            return {"ok": True, "actions": actions}

        if is_restaurant:
            kind = "turkey-restaurant"
            record()
            opp = turkey_opportunities("restaurants")
            top_regions = "، ".join(r["fa"] for r in opp["regions"][:5])
            reply("🍽 بازار رستوران‌های استانبول در ۱۰ منطقه\n"
                  f"• مناطق داغ: {top_regions} و...\n"
                  f"• ۱۰ ماده اولیه اصلی از روغن و مرغ تا بسته‌بندی تحلیل می‌شود\n"
                  f"• بیدهای ثبت‌شده: {opp['summary']['activeBids']} (نمونه آموزشی با تماس ساختگی)\n\n"
                  "دستورها: «بید رستوران» ← داغ‌ترین بیدها با تماس · «تأمین رستوران» ← اولویت تأمین بر اساس مصرف × سود")
            return {"ok": True, "actions": actions}

        if normalized in BALE_TURKEY_BIDS_WORDS:
            kind = "turkey-bids"
            record()
            scored = sorted((turkey_score_bid(b) for b in TURKEY_BIDS if b["market"] == "clinics"),
                            key=lambda b: -b["opportunityScore"])[:3]
            if not scored:
                reply("هنوز فراخوانی ثبت نشده است. اپراتور می‌تواند از طریق POST /api/turkey/bids/import (آیتم یا متن پایپ‌جدا) یا وب‌هوک رسمی TURKEY_BIDS_WEBHOOK_URL بیدها را وارد کند； "
                      "لینک‌های کشف (EKAP و ...) در GET /api/turkey/opportunities موجود است.")
            else:
                blocks = []
                for i, b in enumerate(scored, 1):
                    extra = []
                    if b.get("quantity"):
                        extra.append(f"تعداد {b['quantity']}")
                    if b.get("budgetTry"):
                        extra.append(f"بودجه ~{int(b['budgetTry']):,} لیر")
                    if b.get("deadline"):
                        extra.append(f"ددلاین {b['deadline'][:10]}")
                    blocks.append(f"{i}) 🏥 {b['clinic']} · {b['regionFa']}\nنیاز: {b['need'][:90]}\n"
                                  f"امتیاز فرصت: {b['opportunityScore']}/۱۰۰ (درجه {b['grade']}) · مصرف {b['consumptionLevel']}/۵ · حاشیه ~{b['marginRange'][0]}-{b['marginRange'][1]}٪"
                                  + ("\n" + " · ".join(extra) if extra else ""))
                reply("📋 مهم‌ترین بیدهای کلینیک‌های ترکیه:\n\n" + "\n\n".join(blocks) +
                      f"\n\nمجموع {sum(1 for b in TURKEY_BIDS if b['market']=='clinics')} بید کلینیکی در سیستم — فهرست کامل: GET /api/turkey/opportunities · برای رستوران‌ها: «بید رستوران»")
            return {"ok": True, "actions": actions}

        if normalized in BALE_TURKEY_SUPPLY_WORDS:
            kind = "turkey-supply"
            record()
            opp = turkey_opportunities()
            picks = opp["topPicks"][:6]
            lines = []
            for i, c in enumerate(picks, 1):
                flag = " ⚠️نیازمند مجوز TİTCK/ÜTS" if c["regulated"] else ""
                pull = f" · {c['activeBids']} بید فعال" if c["activeBids"] else ""
                lines.append(f"{i}) {c['fa']} — مصرف {c['consumption']}/۵ · حاشیه ~{c['margin'][0]}-{c['margin'][1]}٪{pull}{flag}")
            reply("🧭 پیشنهاد تأمین بر اساس مصرف × سود (ترکیه/استانبول):\n\n" + "\n".join(lines) +
                  "\n\nتوضیح: ارقام حاشیه تقریبی و صرفاً برای اولویت‌بندی است، نه قیمت قطعاتی. قبل از عرضه اقلام نظارتی، ثبت رسمی در ترکیه الزامی است.")
            return {"ok": True, "actions": actions}

        ascii_text = text.translate(DIGIT_TRANSLATION)
        url = _bale_extract_url(ascii_text)
        if url:
            kind = "audit"
            record()  # inbox sees the request even if the audit itself fails
            try:
                report = audit(url)
                host = urlparse(str(report.get("finalUrl", url))).hostname or url
                score = int(report.get("seoScore", 0) or 0)
                issues = [str(x)[:120] for x in (report.get("issues") or [])[:4]]
                issue_lines = "\n".join(f"{i}. {issue}" for i, issue in enumerate(issues, 1)) or "—"
                title = str(report.get("title", "") or "").strip()[:80] or "—"
                body = (f"🔎 ممیزی فوری وب‌سایت: {host}\n"
                        f"────────────\n"
                        f"امتیاز سئو: {score} از ۱۰۰\n"
                        f"پاسخ سرور: {report.get('status', '—')} · زمان بارگذاری: {report.get('elapsedSeconds', '—')} ثانیه\n"
                        f"عنوان صفحه: {title}\n\n"
                        f"مهم‌ترین موارد قابل بهبود:\n{issue_lines}\n\n"
                        f"این یک بررسی خودکار تک‌صفحه‌ای از داده عمومی است. برای تحلیل کامل و دریافت پیشنهاد رسمی، شماره تماس خود را بفرستید.")
                reply(body)
                return {"ok": True, "actions": actions,
                        "audit": {"url": report.get("finalUrl", url), "score": score, "status": report.get("status", 0)}}
            except (ValueError, URLError, HTTPError, socket.timeout, TimeoutError) as exc:
                reply(f"متأسفانه بررسی این آدرس ممکن نشد: {str(exc)[:200]}\nلطفاً آدرس کامل وب‌سایت را (مثلاً https://example.ir) بفرستید.")
                return {"ok": True, "actions": actions, "auditError": str(exc)[:200]}

        phone = _bale_extract_phone(ascii_text)
        if phone:
            kind = "phone"
            saved = False
            try:
                persist_leads_database([{"name": f"کاربر بله — {name}", "phone": phone,
                                         "source": "Bale bot inbound", "status": "callback-requested",
                                         "resultType": "callback", "tags": ["bale-bot"]}])
                saved = True
            except ValueError:
                saved = False
            record()
            if saved:
                reply("✅ شماره تماس شما ثبت شد؛ کارشناس ما برای هماهنگی با شما تماس می‌گیرد. شماره شما فقط برای همین هماهنگی استفاده می‌شود. (توقف پیام‌ها: /stop)")
            else:
                reply("✅ درخواست تماس شما دریافت شد و در صندوق ورودی اپراتور ثبت می‌شود؛ کارشناس ما پیگیری می‌کند. (توقف پیام‌ها: /stop)")
            return {"ok": True, "actions": actions, "lead": {"phone": phone, "saved": saved}}

        kind = "fallback"
        record()
        reply("پیام شما دریافت شد 🙌\nآدرس وب‌سایت را برای ممیزی فوری سئو، یا شماره تماس را برای درخواست تماس کارشناس بفرستید. راهنما: /help")
        return {"ok": True, "actions": actions}
    except ValueError as exc:
        # Rate limiting and validation land here — stay quiet on flood, visible on misuse.
        if "Rate limit" in str(exc):
            return {"ok": False, "actions": [{"type": "rate-limited"}], "error": str(exc)}
        raise


def bale_polling_loop():
    try:
        _, me = bale_api("getMe", timeout=15)
        username = (me.get("result") or {}).get("username", "?") if isinstance(me, dict) else "?"
        print(f"[bale-bot] long-polling as @{username}")
    except Exception as exc:
        print(f"[bale-bot] getMe failed ({type(exc).__name__}: {exc}); polling continues with retries")
    backoff = 2
    while True:
        _bale_load_state()
        offset = int(_BALE_STATE.get("updateOffset") or 0)
        try:
            _, data = bale_api("getUpdates",
                               {"timeout": 25, "offset": offset, "allowed_updates": ["message"]},
                               timeout=40)
            updates = data.get("result") if isinstance(data, dict) and data.get("ok") else []
            if not isinstance(updates, list):
                updates = []
            for upd in updates:
                try:
                    bale_process_update(upd)
                except Exception as exc:
                    print(f"[bale-bot] update failed: {type(exc).__name__}: {exc}")
                offset = max(offset, int(upd.get("update_id", offset - 1)) + 1)
            if updates:
                with _BALE_STATE_LOCK:
                    _BALE_STATE["updateOffset"] = offset
                    _bale_save_state()
            backoff = 2
        except Exception as exc:
            print(f"[bale-bot] poll error: {type(exc).__name__}: {exc}; retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


def start_bale_polling_if_enabled() -> bool:
    if BALE_BOT_MODE != "polling" or not os.getenv("BALE_BOT_TOKEN", "").strip():
        return False
    try:  # getUpdates and webhooks are mutually exclusive
        bale_api("deleteWebhook", {"drop_pending_updates": False}, timeout=10)
    except Exception:
        pass
    thread = threading.Thread(target=bale_polling_loop, name="bale-bot-polling", daemon=True)
    thread.start()
    print("[bale-bot] long-polling enabled (BALE_BOT_MODE=polling)")
    return True


# ---------------------------------------------------------------------------
# Turkey clinic procurement assistant
#
# Maps consumable demand of Turkish clinics/medical centers (focus: Istanbul),
# ingests their bids/RFQs ("فراخوان") through operator import or an official
# operator-approved webhook (never scraping), and ranks supply opportunities
# by consumption volume × indicative margin. Figures are advisory estimates,
# not guarantees; regulated goods need TİTCK/ÜTS registration.
# ---------------------------------------------------------------------------

TURKEY_REGIONS = [
    {"id": "sisli", "fa": "شیشلی", "tr": "Şişli", "demand": 5,
     "note": "قطب بیمارستان‌ها و کلینیک‌های خصوصی؛ قلب گردشگری سلامت"},
    {"id": "kadikoy", "fa": "کادیکوی", "tr": "Kadıköy", "demand": 4,
     "note": "بخش آسیایی؛ تراکم بالای کلینیک‌های زیبایی و دندان‌پزشکی"},
    {"id": "bakirkoy", "fa": "باکیرکوی", "tr": "Bakırköy", "demand": 4,
     "note": "نزدیک فرودگاه؛ بیمارستان‌های بزرگ و مراجعه بیماران خارجی"},
    {"id": "besiktas", "fa": "بشیکتاش", "tr": "Beşiktaş", "demand": 4,
     "note": "کلینیک‌های پریمیوم زیبایی و VIP"},
    {"id": "atasehir", "fa": "آتاشهیر", "tr": "Ataşehir", "demand": 3,
     "note": "مراکز پزشکی نوین بخش آسیایی؛ رشد سریع"},
    {"id": "beyoglu", "fa": "بی‌اوغلو", "tr": "Beyoğlu", "demand": 3,
     "note": "منطقه توریستی مرکزی؛ کلینیک‌های شهری"},
    {"id": "uskudar", "fa": "اوسکودار", "tr": "Üsküdar", "demand": 3,
     "note": "بازار داخلی بخش آسیایی؛ بیمارستان‌های دولتی و خصوصی"},
    {"id": "bahcelievler", "fa": "باغچلی‌اولر", "tr": "Bahçelievler", "demand": 3,
     "note": "مسطح مسکونی پرجمعیت؛ کلینیک‌های خانوادگی"},
    {"id": "fatih", "fa": "فاتح", "tr": "Fatih", "demand": 3,
     "note": "مرکز قدیمی؛ مراکز درمانی سنتی و پایتخت‌گردشگری"},
    {"id": "beylikduzu", "fa": "بیلیکدوزو", "tr": "Beylikdüzü", "demand": 3,
     "note": "غرب استانبول؛ رشد جمعیت و کلینیک‌های جدید"},
]

# Regional alias → region id (fa/tr/ascii spellings)
TURKEY_REGION_ALIASES = {}
for _r in TURKEY_REGIONS:
    TURKEY_REGION_ALIASES[_r["tr"].lower()] = _r["id"]
    TURKEY_REGION_ALIASES[_r["fa"]] = _r["id"]
    TURKEY_REGION_ALIASES[_r["id"]] = _r["id"]
TURKEY_REGION_ALIASES.update({
    "sisli": "sisli", "şişli": "sisli", "kadikoy": "kadikoy", "kadıköy": "kadikoy",
    "bakirkoy": "bakirkoy", "bakırköy": "bakirkoy", "besiktas": "besiktas", "beşiktaş": "besiktas",
    "atasehir": "atasehir", "ataşehir": "atasehir", "beyoglu": "beyoglu", "beyoğlu": "beyoglu",
    "uskudar": "uskudar", "üsküdar": "uskudar", "bahcelievler": "bahcelievler", "bahçelievler": "bahcelievler",
    "fatih": "fatih", "beylikduzu": "beylikduzu", "beylikdüzü": "beylikduzu",
    "istanbul": "istanbul", "استانبول": "istanbul",
})

# ~10+ consumable categories for Turkish clinics: consumption 1-5, indicative
# gross-margin range (%), regulatory flag. Advisory estimates, not quotes.
TURKEY_CONSUMABLES = [
    {"id": "exam-gloves", "fa": "دستکش معاینه (نیتریل/لاتکس)", "consumption": 5, "margin": [5, 12],
     "regulated": False, "keywords": ["glove", "gloves", "eldiven", "دستکش"]},
    {"id": "syringes-needles", "fa": "سرنگ، سوزن و ست‌های تزریق", "consumption": 5, "margin": [6, 14],
     "regulated": False, "keywords": ["syringe", "needle", "şırınga", "sirnga", "enjektör", "enjektor", "سرنگ", "سوزن"]},
    {"id": "sterile-dressings", "fa": "گاز استریل، پانسمان و بخیه", "consumption": 4, "margin": [8, 16],
     "regulated": False, "keywords": ["gauze", "dressing", "suture", "pansuman", "gazlı", "gazli", "sütür", "پانسمان", "بخیه", "گاز استریل"]},
    {"id": "masks-respirators", "fa": "ماسک جراحی و N95/FFP2", "consumption": 4, "margin": [6, 12],
     "regulated": False, "keywords": ["mask", "maske", "ماسک", "n95", "ffp2", "respirator"]},
    {"id": "disinfectants", "fa": "محلول‌های ضدعفونی سطوح و دست", "consumption": 4, "margin": [10, 20],
     "regulated": False, "keywords": ["disinfect", "dezenfekt", "antisep", "ضدعفونی", "الکل", "گندزدا"]},
    {"id": "dental-composites", "fa": "مواد ترمیمی و قالب‌گیری دندان", "consumption": 3, "margin": [15, 30],
     "regulated": False, "keywords": ["composite", "kompozit", "dental", "diş ", "dis ", "کامپوزیت", "دندان", "amalgam", "bonding"]},
    {"id": "dental-implants", "fa": "ایمپلنت و اجزای پروتز دندان", "consumption": 3, "margin": [20, 45],
     "regulated": True, "keywords": ["implant", "ایمپلنت", "abutment", "پیشرفته ایمپلنت"]},
    {"id": "dermal-fillers", "fa": "فیلرهای پوستی (زیبایی)", "consumption": 2, "margin": [25, 50],
     "regulated": True, "keywords": ["filler", "dolgu", "فیلر", "hyaluron", "هیالورونیک", "dermal"]},
    {"id": "botulinum-toxin", "fa": "توکسین بوتولینوم (بوتاکس)", "consumption": 2, "margin": [30, 55],
     "regulated": True, "keywords": ["botox", "botoks", "toxin", "toksin", "بوتاکس", "توکسین"]},
    {"id": "pdo-threads", "fa": "نخ‌های لیفت PDO/PLLA", "consumption": 2, "margin": [20, 40],
     "regulated": True, "keywords": ["thread", "pdo", "plla", "نخ", "لیفت", "iplik"]},
    {"id": "prp-microneedling", "fa": "کیت‌های PRP و کارتریج میکرونیدلینگ", "consumption": 2, "margin": [25, 45],
     "regulated": False, "keywords": ["prp", "microneed", "mikroiğne", "kit ", "کیت", "میکرونیدل"]},
]

TURKEY_BIDS: deque[dict] = deque(maxlen=500)

TURKEY_DISCOVERY_LINKS = {
    "ekap": "https://ekap.kik.gov.tr/EKAP/Ortak/IhaleArama/index.html",
    "ekapEnglish": "https://www.kik.gov.tr/",
    "timExporters": "https://www.tim.org.tr/en",
    "medicalistanbulFair": "https://www.google.com/search?q=Istanbul+medical+consumables+fair+exhibitors",
}


# --- Market 2: Istanbul restaurants (with Bağcılar and 9 more districts) ---
TURKEY_RESTAURANT_REGIONS = [
    {"id": "bagcilar", "fa": "باغجیلار", "tr": "Bağcılar", "demand": 5,
     "note": "متراکم‌ترین منطقه مسکونی؛ رستوران‌های محلی و بیرون‌بر فراوان"},
    {"id": "esenler", "fa": "اسنلر", "tr": "Esenler", "demand": 4,
     "note": "تراکم بالای غذاخوری‌های قیمت‌مناسب و عبوری"},
    {"id": "gungoren", "fa": "گونگورن", "tr": "Güngören", "demand": 4,
     "note": "بازار محلی پرتردد؛ تقاضای پایدار مواد اولیه"},
    {"id": "kucukcekmece", "fa": "کوچوک‌چکمجه", "tr": "Küçükçekmece", "demand": 4,
     "note": "رشد جمعیت و رستوران‌های خانوادگی"},
    {"id": "esenyurt", "fa": "اسنیورت", "tr": "Esenyurt", "demand": 4,
     "note": "حجم بالای بیرون‌بر؛ حساس به قیمت"},
    {"id": "umraniye", "fa": "عمرانیه", "tr": "Ümraniye", "demand": 4,
     "note": "بخش آسیایی؛ رستوران‌های اداری و کارگری"},
    {"id": "pendik", "fa": "پندیک", "tr": "Pendik", "demand": 3,
     "note": "کنار فرودگاه صبیحا؛ غذاخوری‌های ساحلی و عبوری"},
    {"id": "kartal", "fa": "کارتال", "tr": "Kartal", "demand": 3,
     "note": "ساحل آسیایی؛ رستوران‌های ماهی و محلی"},
    {"id": "sultanbeyli", "fa": "سلطان‌بیلی", "tr": "Sultanbeyli", "demand": 3,
     "note": "منطقه در حال رشد؛ قیمت‌محور"},
    {"id": "gaziosmanpasa", "fa": "غازی‌عثمان‌پاشا", "tr": "Gaziosmanpaşa", "demand": 3,
     "note": "بازار سنتی و فروشگاه‌های مواد غذایی متمرکز"},
]

TURKEY_RESTAURANT_REGION_ALIASES = {}
for _r in TURKEY_RESTAURANT_REGIONS:
    TURKEY_RESTAURANT_REGION_ALIASES[_r["tr"].lower()] = _r["id"]
    TURKEY_RESTAURANT_REGION_ALIASES[_r["fa"]] = _r["id"]
    TURKEY_RESTAURANT_REGION_ALIASES[_r["id"]] = _r["id"]
TURKEY_RESTAURANT_REGION_ALIASES.update({
    "bagcilar": "bagcilar", "bağcılar": "bagcilar", "bagcılar": "bagcilar",
    "esenler": "esenler", "gungoren": "gungoren", "güngören": "gungoren",
    "kucukcekmece": "kucukcekmece", "küçükçekmece": "kucukcekmece",
    "esenyurt": "esenyurt", "umraniye": "umraniye", "ümraniye": "umraniye",
    "pendik": "pendik", "kartal": "kartal", "sultanbeyli": "sultanbeyli",
    "gaziosmanpasa": "gaziosmanpasa", "gaziosmanpaşa": "gaziosmanpasa",
    "istanbul": "istanbul", "استانبول": "istanbul",
})

# 10 staple restaurant raw materials: consumption 1-5, indicative gross-margin
# range (%), regulatory/certification notes. Advisory estimates, not quotes.
TURKEY_RESTAURANT_CONSUMABLES = [
    {"id": "frying-oil", "fa": "روغن سرخ‌کردنی و مایع (تن/لیتر)", "consumption": 5, "margin": [5, 10],
     "regulated": False, "keywords": ["oil", "yağ", "yag", "روغن", "frying"]},
    {"id": "rice", "fa": "برنج (ایرانی/بالدو/اوسمانجیک)", "consumption": 5, "margin": [6, 12],
     "regulated": False, "keywords": ["rice", "pirinç", "pirinc", "برنج"]},
    {"id": "chicken", "fa": "مرغ تازه/منجمد", "consumption": 5, "margin": [7, 13],
     "regulated": False, "certNote": "گواهی حلال و زنجیره سرد توصیه می‌شود",
     "keywords": ["chicken", "tavuk", "مرغ", "جوجه"]},
    {"id": "beef", "fa": "گوشت قرمز (گوساله/گوسفندی)", "consumption": 4, "margin": [8, 15],
     "regulated": False, "certNote": "گواهی حلال و زنجیره سرد توصیه می‌شود",
     "keywords": ["beef", "meat", "kırmızı et", "kirmizi et", "dana", "et ", "گوشت", "قصابی"]},
    {"id": "vegetables", "fa": "سبزیجات و صیفی‌جات تازه", "consumption": 5, "margin": [8, 18],
     "regulated": False, "certNote": "فسادپذیر — لجستیک سریع/سرد",
     "keywords": ["vegetable", "sebze", "سبزیجات", "صیفی", "میوه", "salata"]},
    {"id": "flour-bakery", "fa": "آرد و مواد نانوایی", "consumption": 4, "margin": [6, 12],
     "regulated": False, "keywords": ["flour", "un ", "آرد", "نان", "ekmek"]},
    {"id": "dairy", "fa": "لبنیات (پنیر، ماست، کره)", "consumption": 4, "margin": [8, 15],
     "regulated": False, "certNote": "زنجیره سرد الزامی",
     "keywords": ["dairy", "cheese", "peynir", "yoğurt", "yogurt", "لبنیات", "پنیر", "ماست", "کره"]},
    {"id": "packaging", "fa": "ظروف بیرون‌بر و بسته‌بندی", "consumption": 4, "margin": [10, 20],
     "regulated": False, "keywords": ["packag", "paket", "ظرف", "بسته‌بندی", "بیرون‌بر", "kutu"]},
    {"id": "legumes-spices", "fa": "حبوبات و ادویه‌جات", "consumption": 3, "margin": [12, 25],
     "regulated": False, "keywords": ["bakliyat", "baharat", "legume", "spice", "حبوبات", "ادویه", "پولکی"]},
    {"id": "beverages", "fa": "نوشیدنی و آب معدنی", "consumption": 4, "margin": [5, 10],
     "regulated": False, "keywords": ["beverage", "içecek", "icecek", "su ", "نوشیدنی", "آب معدنی", "نوشابه"]},
]

RESTAURANT_DISCOVERY_LINKS = {
    "istanbulWholesaleMarkets": "https://www.google.com/search?q=Istanbul+wholesale+food+market+restaurant+suppliers",
    "timFoodExporters": "https://www.tim.org.tr/en",
    "restaurantSupplyFairs": "https://www.google.com/search?q=Istanbul+HORECA+fair+food+beverage+exhibitors",
}

TURKEY_MARKETS = {
    "clinics": {
        "fa": "کلینیک‌ها و مراکز پزشکی ترکیه",
        "regions": TURKEY_REGIONS,
        "aliases": TURKEY_REGION_ALIASES,
        "consumables": TURKEY_CONSUMABLES,
        "links": TURKEY_DISCOVERY_LINKS,
        "regulatory": "Regulated goods (implants, fillers, toxin, threads) require TİTCK/ÜTS registration and licensed local distribution before supply.",
    },
    "restaurants": {
        "fa": "رستوران‌های استانبول",
        "regions": TURKEY_RESTAURANT_REGIONS,
        "aliases": TURKEY_RESTAURANT_REGION_ALIASES,
        "consumables": TURKEY_RESTAURANT_CONSUMABLES,
        "links": RESTAURANT_DISCOVERY_LINKS,
        "regulatory": "Food supply should follow halal certification and cold-chain rules for meat, poultry and dairy.",
    },
}


def _turkey_consumable_score(item: dict) -> float:
    margin_mid = (item["margin"][0] + item["margin"][1]) / 2
    return round(item["consumption"] * margin_mid, 1)


def turkey_consumables_ranked(market: str = "clinics") -> list[dict]:
    ranked = []
    for item in TURKEY_MARKETS.get(market, TURKEY_MARKETS["clinics"])["consumables"]:
        ranked.append({**item, "score": _turkey_consumable_score(item)})
    ranked.sort(key=lambda x: (-x["score"], -x["consumption"]))
    return ranked


def turkey_match_region(text: str, market: str = "clinics") -> str | None:
    normalized = _bale_normalize(text) if text else ""
    if not normalized:
        return None
    aliases = TURKEY_MARKETS.get(market, TURKEY_MARKETS["clinics"])["aliases"]
    for alias, region_id in aliases.items():
        if alias in normalized:
            return region_id
    return None


def turkey_match_category(text: str, market: str = "clinics") -> dict | None:
    normalized = (text or "").lower()
    if not normalized.strip():
        return None
    best = None
    for item in TURKEY_MARKETS.get(market, TURKEY_MARKETS["clinics"])["consumables"]:
        matched = [kw for kw in item["keywords"] if kw.lower() in normalized]
        if matched:
            # more keyword hits wins; ties go to the more specific (longer) keyword
            rank = (len(matched), max(len(kw) for kw in matched))
            if best is None or rank > best[0]:
                best = (rank, item)
    return best[1] if best else None


def _turkey_budget_factor(budget_try: float | None) -> float:
    if not budget_try or budget_try <= 0:
        return 1.0
    if budget_try < 50_000:
        return 1.0
    if budget_try < 250_000:
        return 1.15
    if budget_try < 1_000_000:
        return 1.3
    return 1.45


def _turkey_deadline_factor(deadline: str) -> float:
    if not deadline:
        return 1.0
    try:
        dt = time.strptime(deadline.strip()[:10], "%Y-%m-%d")
        days = (time.mktime(dt) - time.time()) / 86400
        if 0 <= days <= 30:
            return 1.15
    except Exception:
        pass
    return 1.0


def normalize_turkey_bid(item: dict, market: str = "clinics") -> dict | None:
    if market not in TURKEY_MARKETS:
        raise ValueError(f"Unknown market '{market}'. Use one of: {', '.join(TURKEY_MARKETS)}")
    market_obj = TURKEY_MARKETS[market]
    clinic = str(item.get("clinic", item.get("name", item.get("buyer", "")))).strip()[:160]
    need = str(item.get("need", item.get("text", item.get("description", item.get("category", ""))))).strip()[:400]
    if not clinic and not need:
        return None
    region_raw = str(item.get("region", item.get("district", item.get("city", "")))).strip()[:80]
    region_id = item.get("regionId") if str(item.get("regionId", "")).strip() in {r["id"] for r in market_obj["regions"]} else None
    if not region_id:
        region_id = turkey_match_region(f"{region_raw} {clinic} {need}", market) or "istanbul"
    category = turkey_match_category(f"{item.get('category', '')} {need}", market) or {}
    try:
        quantity = int(float(item.get("quantity", 0) or 0)) or None
    except Exception:
        quantity = None
    try:
        budget = float(str(item.get("budgetTry", item.get("budget", ""))).replace(",", "") or 0) or None
    except Exception:
        budget = None
    deadline = str(item.get("deadline", item.get("due", ""))).strip()[:24]
    contact = str(item.get("contact", item.get("phone", item.get("email", "")))).strip()[:200]
    source = str(item.get("source", item.get("sourceUrl", ""))).strip()[:400]
    category_id = category.get("id", "uncategorized")
    default_need = "نیاز عمومی کلینیک" if market == "clinics" else "تأمین مواد اولیه رستوران"
    return {
        "id": hashlib.sha256(f"{market}|{clinic}|{need}|{deadline}".encode("utf-8")).hexdigest()[:14],
        "market": market,
        "clinic": clinic or "—",
        "need": need or category.get("fa", default_need),
        "regionId": region_id,
        "regionFa": next((r["fa"] for r in market_obj["regions"] if r["id"] == region_id), "استانبول (سایر)"),
        "categoryId": category_id,
        "categoryFa": category.get("fa", "متفرقه / نامشخص"),
        "quantity": quantity,
        "budgetTry": budget,
        "deadline": deadline,
        "contact": contact,
        "source": source or "operator-import",
        "sample": item.get("sample") is True,
        "importedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def turkey_score_bid(bid: dict) -> dict:
    market_obj = TURKEY_MARKETS.get(bid.get("market") or "clinics", TURKEY_MARKETS["clinics"])
    category = next((c for c in market_obj["consumables"] if c["id"] == bid.get("categoryId")), None)
    consumption = category["consumption"] if category else 2
    margin = category["margin"] if category else [8, 18]
    margin_mid = (margin[0] + margin[1]) / 2
    base = min(100.0, consumption * margin_mid)
    size_f = _turkey_budget_factor(bid.get("budgetTry"))
    urgent_f = _turkey_deadline_factor(bid.get("deadline", ""))
    score = max(5, min(100, round(base * size_f * urgent_f)))
    grade = "A" if score >= 70 else "B" if score >= 45 else "C"
    return {
        **bid,
        "consumptionLevel": consumption,
        "marginRange": margin,
        "regulated": bool(category and category.get("regulated")),
        "certNote": (category or {}).get("certNote"),
        "opportunityScore": score,
        "grade": grade,
        "factors": {"base": round(base, 1), "budgetFactor": size_f, "deadlineFactor": urgent_f},
    }


def turkey_bids_import(payload: dict) -> dict:
    market = str(payload.get("market", "clinics")).strip().lower()
    if market not in TURKEY_MARKETS:
        raise ValueError(f"Unknown market '{market}'. Use one of: {', '.join(TURKEY_MARKETS)}")
    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []
    text = str(payload.get("text", payload.get("csv", ""))).strip()
    parsed = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("clinic", "نام")):
            continue
        parts = [p.strip() for p in line.split("|")]
        while len(parts) < 3:
            parts.append("")
        parsed.append({"clinic": parts[0], "region": parts[1], "need": parts[2],
                       "quantity": parts[3] if len(parts) > 3 else "",
                       "budgetTry": parts[4] if len(parts) > 4 else "",
                       "deadline": parts[5] if len(parts) > 5 else ""})
    for item in raw_items[:200]:
        if isinstance(item, dict):
            parsed.append({**item, "market": item.get("market", market)})
    bids = [b for b in (normalize_turkey_bid(x, x.get("market", market)) for x in parsed[:200]) if b]
    if not bids:
        raise ValueError("No valid Turkey bid rows found. Send items[] or pipe-separated text: کلینیک | منطقه | نیاز | تعداد | بودجه(لیر) | ددلاین")
    existing = {b["id"] for b in TURKEY_BIDS}
    fresh = [b for b in bids if b["id"] not in existing]
    for bid in reversed(fresh):
        TURKEY_BIDS.appendleft(bid)
    saved_db = False
    if fresh and supabase_settings()["configured"]:
        try:  # best-effort mirror into the lead database; the in-memory feed remains primary
            persist_leads_database([{**b, "name": b["clinic"], "status": f"turkey-bid-{b['market']}",
                                     "resultType": "turkey-bid", "tags": ["turkey", b["market"], b["categoryId"]]}
                                    for b in fresh])
            saved_db = True
        except ValueError:
            saved_db = False
    return {"ok": True, "market": market, "imported": len(fresh), "skippedDuplicates": len(bids) - len(fresh),
            "total": sum(1 for b in TURKEY_BIDS if b["market"] == market), "mirroredToDb": saved_db}


def turkey_bids_sync() -> dict:
    webhook = os.getenv("TURKEY_BIDS_WEBHOOK_URL", "").strip()
    if not webhook:
        return {"ok": True, "configured": False, "imported": 0,
                "message": "No official webhook is configured. Use POST /api/turkey/bids/import (file/paste) or the discovery links."}
    token = os.getenv("TURKEY_BIDS_WEBHOOK_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status, data = post_json(webhook, {"mode": "clinic-bids", "market": "TR-istanbul"}, headers, timeout=30)
    items = data.get("items", []) if isinstance(data, dict) else []
    result = turkey_bids_import({"items": items, "source": "official-webhook"})
    return {"ok": True, "configured": True, "providerStatus": status, **result}


def turkey_opportunities(market: str = "clinics") -> dict:
    if market == "all":
        markets = list(TURKEY_MARKETS)
    elif market in TURKEY_MARKETS:
        markets = [market]
    else:
        raise ValueError(f"Unknown market '{market}'. Use one of: {', '.join(TURKEY_MARKETS)} or 'all'")
    primary = TURKEY_MARKETS[markets[0]]
    consumables: list[dict] = []
    regions: list[dict] = []
    for mid in markets:
        consumables.extend(turkey_consumables_ranked(mid))
        regions.extend(TURKEY_MARKETS[mid]["regions"])
    scored = sorted((turkey_score_bid(b) for b in TURKEY_BIDS if b["market"] in markets),
                    key=lambda b: -b["opportunityScore"])
    category_pull: dict[str, int] = {}
    for b in scored:
        category_pull[b["categoryId"]] = category_pull.get(b["categoryId"], 0) + 1
    region_rows = []
    for region in regions:
        region_bids = [b for b in scored if b["regionId"] == region["id"]]
        region_rows.append({**region, "activeBids": len(region_bids),
                            "opportunity": min(100, region["demand"] * 20 + len(region_bids) * 5)})
    region_rows.sort(key=lambda r: -r["opportunity"])
    top_picks = []
    for c in consumables:
        pull = category_pull.get(c["id"], 0)
        # gentle market-pull boost: keeps separation even when every category has many live bids
        top_picks.append({**c, "activeBids": pull,
                          "recommendationScore": min(100, round(c["score"] * (1 + 0.05 * pull), 1))})
    top_picks.sort(key=lambda c: -c["recommendationScore"])
    sample_count = sum(1 for b in scored if b.get("sample"))
    title = "Turkey — " + " + ".join(TURKEY_MARKETS[m]["fa"] for m in markets) + " (Istanbul focus)"
    return {
        "ok": True,
        "market": title,
        "marketId": market,
        "summary": {"regionCount": len(regions), "consumableCategories": len(consumables),
                    "activeBids": len(scored), "sampleBids": sample_count,
                    "webhookConfigured": bool(os.getenv("TURKEY_BIDS_WEBHOOK_URL", "").strip())},
        "consumables": consumables,
        "topPicks": top_picks[:10],
        "regions": region_rows,
        "bids": scored[:100],
        "discoveryLinks": {m: TURKEY_MARKETS[m]["links"] for m in markets} if len(markets) > 1 else primary["links"],
        "samplesNote": ("Rows marked sample:true are deterministic educational examples with fictional "
                        "contacts — not real RFQs. Disable with TURKEY_SEED_SAMPLE_BIDS=false.") if sample_count else None,
        "disclaimer": ("Consumption (1-5) and margin ranges are advisory market estimates for prioritization — "
                       "not quotes or guarantees. " + " ".join(TURKEY_MARKETS[m]["regulatory"] for m in markets)),
    }


# --- Deterministic sample bids: 100 Istanbul restaurant RFQs (educational) ---
_RESTAURANT_SAMPLE_TEMPLATES = [
    {"categoryId": "frying-oil", "need": "روغن سرخ‌کردنی (yağ) تأمین ماهانه", "qty": (500, 3000), "budget": (30_000, 140_000)},
    {"categoryId": "rice", "need": "برنج بالدو/ایرانی (pirinç) تناژ ماهانه", "qty": (800, 3000), "budget": (25_000, 180_000)},
    {"categoryId": "chicken", "need": "مرغ تازه (tavuk) تأمین هفتگی — کیلوگرم", "qty": (300, 1500), "budget": (60_000, 350_000)},
    {"categoryId": "beef", "need": "گوشت گوساله (dana eti) هفتگی — کیلوگرم", "qty": (100, 600), "budget": (70_000, 450_000)},
    {"categoryId": "vegetables", "need": "سبزیجات و صیفی‌جات تازه (sebze) روزانه", "qty": (200, 1000), "budget": (15_000, 90_000)},
    {"categoryId": "flour-bakery", "need": "آرد نانوایی (un) ماهانه — کیلوگرم", "qty": (1000, 5000), "budget": (15_000, 100_000)},
    {"categoryId": "dairy", "need": "پنیر و ماست (peynir/yoğurt) ماهانه", "qty": (100, 500), "budget": (20_000, 120_000)},
    {"categoryId": "packaging", "need": "ظرف بیرون‌بر و بسته‌بندی (paket) — عدد", "qty": (5000, 85000), "budget": (10_000, 120_000)},
    {"categoryId": "legumes-spices", "need": "حبوبات و ادویه (bakliyat/baharat) فصلی", "qty": (50, 400), "budget": (10_000, 80_000)},
    {"categoryId": "beverages", "need": "نوشیدنی و آب معدنی (içecek/su) ماهانه", "qty": (300, 2000), "budget": (8_000, 60_000)},
]

_RESTAURANT_NAMES = ["Anadolu", "Boğaz", "Hünkar", "Lezzet", "Saray", "Marmara", "Ege", "Kervan",
                     "İstanbul", "Dostlar", "Şehzade", "Pera", "Tarihi", "Yıldız", "Anka"]
_RESTAURANT_SUFFIXES = ["Sofrası", "Lokantası", "Kebap Evi", "Restoranı", "Ocakbaşı", "Pide Evi"]


def _sample_det(seed_text: str, low: int, high: int) -> int:
    span = max(1, high - low + 1)
    return low + (int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:12], 16) % span)


def _turkey_restaurant_sample_bids(count: int = 100) -> list[dict]:
    regions = TURKEY_RESTAURANT_REGIONS
    bids = []
    base_epoch = time.mktime(time.strptime("2026-08-08", "%Y-%m-%d"))
    for i in range(max(1, min(count, 500))):
        region = regions[i % len(regions)]
        template = _RESTAURANT_SAMPLE_TEMPLATES[i % len(_RESTAURANT_SAMPLE_TEMPLATES)]
        head = _RESTAURANT_NAMES[(i * 7 + 3) % len(_RESTAURANT_NAMES)]
        tail = _RESTAURANT_SUFFIXES[(i * 5 + 1) % len(_RESTAURANT_SUFFIXES)]
        seed = f"{region['id']}-{i}"
        qty = _sample_det(seed + "-q", *template["qty"])
        budget = _sample_det(seed + "-b", *template["budget"])
        deadline = time.strftime("%Y-%m-%d", time.localtime(base_epoch + ((i * 3) % 40) * 86400))
        phone = "+90 53" + str(_sample_det(seed + "-p1", 0, 9)) + " " + \
            f"{_sample_det(seed + '-p2', 100, 999)} {_sample_det(seed + '-p3', 1000, 9999)}"
        item = {
            "clinic": f"رستوران {head} {tail}", "name": f"رستوران {head} {tail}",
            "region": region["tr"], "regionId": region["id"],
            "need": template["need"], "quantity": qty, "budgetTry": budget,
            "deadline": deadline, "contact": phone, "source": "seed-sample",
            "sample": True,
        }
        bid = normalize_turkey_bid(item, "restaurants")
        if bid:
            bids.append(bid)
    return bids


def turkey_seed_sample_bids(count: int = 100) -> dict:
    existing = {b["id"] for b in TURKEY_BIDS}
    generated = _turkey_restaurant_sample_bids(count)
    fresh = [b for b in generated if b["id"] not in existing]
    TURKEY_BIDS.extend(fresh)
    return {"ok": True, "imported": len(fresh), "skippedDuplicates": len(generated) - len(fresh),
            "total": sum(1 for b in TURKEY_BIDS if b["market"] == "restaurants"),
            "note": "Educational sample bids (sample:true) with fictional contacts."}


if env_flag("TURKEY_SEED_SAMPLE_BIDS", True):
    try:
        turkey_seed_sample_bids(max(1, min(int(os.getenv("TURKEY_SEED_SAMPLE_COUNT", "100")), 500)))
    except Exception:
        pass  # sample seeding must never block startup


def _turkey_brief_lines(consumables: list[dict], limit: int) -> str:
    lines = []
    for i, c in enumerate(consumables[:limit], 1):
        flag = " ⚠️نظارتی" if c["regulated"] else ""
        lines.append(f"{i}) {c['fa']} — مصرف {c['consumption']}/۵ · حاشیه ~{c['margin'][0]} تا {c['margin'][1]}٪{flag}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Turkey B2B supplier marketplace (Istanbul restaurants + clinics).
# Buyers publish needs as bids; suppliers register products with unit price,
# stock, minimum order and delivery zones. The engine then compares offers
# for one product category across suppliers and builds a cheapest-reliable
# purchase plan ("smart cart") for a list of needs. Seeded directory rows are
# educational samples (sample:true) and can be disabled in production.

TURKEY_SUPPLIERS: deque[dict] = deque(maxlen=500)

_SUPPLIER_ASPECTS = ("price", "quality", "delivery", "satisfaction")


def _supplier_product_category_id(p: dict, market: str) -> str | None:
    category_raw = str(p.get("categoryId") or p.get("category") or "").strip()[:60]
    if category_raw and category_raw in {c["id"] for c in TURKEY_MARKETS[market]["consumables"]}:
        return category_raw
    name = str(p.get("name") or p.get("product") or "").strip()[:160]
    matched = turkey_match_category(f"{category_raw} {name}", market)
    return matched["id"] if matched else None


def normalize_supplier_product(p: dict, market: str) -> dict | None:
    if not isinstance(p, dict):
        return None
    category_id = _supplier_product_category_id(p, market)
    if not category_id:
        return None
    try:
        price = round(float(str(p.get("priceTry", p.get("price", ""))).replace(",", "")), 2)
    except Exception:
        return None
    if price <= 0 or price > 10_000_000:
        return None
    name = str(p.get("name") or p.get("product") or "").strip()[:160]
    category_fa = next((c["fa"] for c in TURKEY_MARKETS[market]["consumables"] if c["id"] == category_id), category_id)

    def _int_field(key: str, default: int, low: int, high: int) -> int:
        try:
            return max(low, min(int(float(str(p.get(key, default)).replace(",", ""))), high))
        except Exception:
            return default

    stock_raw = p.get("stock", None)
    try:
        stock = max(0, min(int(float(str(stock_raw).replace(",", ""))), 100_000_000)) if stock_raw not in (None, "") else None
    except Exception:
        stock = None
    return {
        "categoryId": category_id,
        "categoryFa": category_fa,
        "name": name or category_fa,
        "unit": str(p.get("unit") or "کیلوگرم").strip()[:24] or "کیلوگرم",
        "priceTry": price,
        "stock": stock,  # None means "availability not declared" (treated as available)
        "minOrder": _int_field("minOrder", 1, 1, 10_000_000),
        "deliveryDays": _int_field("deliveryDays", 2, 0, 30),
    }


def normalize_turkey_supplier(item: dict, market: str = "restaurants") -> dict | None:
    if market not in TURKEY_MARKETS:
        raise ValueError(f"Unknown market '{market}'. Use one of: {', '.join(TURKEY_MARKETS)}")
    market_obj = TURKEY_MARKETS[market]
    name = str(item.get("name") or item.get("company") or "").strip()[:160]
    if not name:
        return None
    region_raw = str(item.get("region") or item.get("district") or item.get("regionId") or "").strip()[:80]
    region_id = item.get("regionId") if str(item.get("regionId", "")).strip() in {r["id"] for r in market_obj["regions"]} else None
    if not region_id:
        region_id = turkey_match_region(f"{region_raw} {name}", market) or "istanbul"
    region_entry = next((r for r in market_obj["regions"] if r["id"] == region_id), None)
    zones: list[str] = []
    for z in list(item.get("deliveryZones") or item.get("zones") or [])[:15]:
        zone = turkey_match_region(str(z), market)
        if zone and zone != "istanbul" and zone not in zones:
            zones.append(zone)
    products = []
    seen_categories: set[str] = set()
    for p in list(item.get("products") or [])[:50]:
        product = normalize_supplier_product(p, market)
        if not product:
            continue
        key = f"{product['categoryId']}|{product['name']}|{product['priceTry']}"
        if key not in seen_categories:
            seen_categories.add(key)
            products.append(product)
    if not products:
        return None
    return {
        "id": hashlib.sha256(f"supplier|{market}|{name}|{region_id}".encode("utf-8")).hexdigest()[:14],
        "market": market,
        "name": name,
        "regionId": region_id,
        "regionFa": region_entry["fa"] if region_entry else "استانبول (سایر)",
        "regionTr": region_entry["tr"] if region_entry else "İstanbul",
        "phone": str(item.get("phone") or item.get("contact") or "").strip()[:60],
        "deliveryZones": zones,  # empty list = delivers everywhere in Istanbul
        "products": products,
        "rating": {"count": 0, "avg": None, "aspects": {}},
        "source": str(item.get("source") or "api")[:60],
        "sample": bool(item.get("sample", False)),
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _supplier_public(s: dict, with_products: bool = True) -> dict:
    rating = s.get("rating") or {}
    out = {k: v for k, v in s.items() if k not in {"rating", "products"}}
    out["productCount"] = len(s.get("products") or [])
    out["categories"] = sorted({p["categoryId"] for p in s.get("products") or []})
    out["ratingAvg"] = rating.get("avg")
    out["ratingCount"] = rating.get("count", 0)
    out["ratingAspects"] = {k: round(v["sum"] / v["n"], 2) for k, v in (rating.get("aspects") or {}).items() if v.get("n")}
    if with_products:
        out["products"] = s.get("products") or []
    return out


def turkey_suppliers_register(payload: dict) -> dict:
    market = str(payload.get("market") or "restaurants").strip().lower() or "restaurants"
    if market not in TURKEY_MARKETS:
        raise ValueError(f"Unknown market '{market}'. Use one of: {', '.join(TURKEY_MARKETS)}")
    raw_items = payload.get("suppliers") if isinstance(payload.get("suppliers"), list) else [payload]
    upserted = []
    for raw in raw_items[:20]:
        if not isinstance(raw, dict):
            continue
        raw = {**raw, "market": raw.get("market") or market}
        try:
            supplier = normalize_turkey_supplier(raw, str(raw["market"]).strip().lower())
        except ValueError:
            continue
        if not supplier:
            continue
        existing = next((s for s in TURKEY_SUPPLIERS if s["id"] == supplier["id"]), None)
        if existing:  # upsert keeps the accumulated rating and the first-seen timestamp
            supplier["rating"] = existing.get("rating") or supplier["rating"]
            supplier["createdAt"] = existing.get("createdAt") or supplier["createdAt"]
            TURKEY_SUPPLIERS.remove(existing)
        TURKEY_SUPPLIERS.appendleft(supplier)
        upserted.append({"id": supplier["id"], "name": supplier["name"],
                         "regionId": supplier["regionId"], "productCount": len(supplier["products"])})
    if not upserted:
        raise ValueError("No valid supplier found. Each supplier needs a name and at least one product "
                         "with a known category and a positive priceTry.")
    return {"ok": True, "upserted": len(upserted), "suppliers": upserted,
            "total": sum(1 for s in TURKEY_SUPPLIERS if s["market"] == market)}


def turkey_suppliers_list(market: str = "restaurants") -> dict:
    market = str(market or "restaurants").strip().lower() or "restaurants"
    if market not in TURKEY_MARKETS:
        raise ValueError(f"Unknown market '{market}'. Use one of: {', '.join(TURKEY_MARKETS)}")
    rows = [s for s in TURKEY_SUPPLIERS if s["market"] == market]
    sample_count = sum(1 for s in rows if s.get("sample"))
    return {
        "ok": True,
        "market": market,
        "count": len(rows),
        "suppliers": [_supplier_public(s, with_products=False) for s in rows],
        "samplesNote": (f"{sample_count} of these suppliers are educational samples with fictional "
                        "contacts. Disable with TURKEY_SEED_SAMPLE_SUPPLIERS=false.") if sample_count else None,
        "disclaimer": "Listings are self-reported by suppliers; verify licenses, halal certificates and prices before contracting.",
    }


def turkey_supplier_rate(payload: dict) -> dict:
    supplier_id = str(payload.get("supplierId") or payload.get("id") or "").strip()[:20]
    supplier = next((s for s in TURKEY_SUPPLIERS if s["id"] == supplier_id), None)
    if not supplier:
        raise ValueError(f"Supplier '{supplier_id or '?'}' not found. List ids via GET /api/turkey/suppliers.")
    scores: dict[str, float] = {}
    for aspect in _SUPPLIER_ASPECTS:
        raw = payload.get(aspect, None)
        if raw in (None, ""):
            continue
        try:
            value = float(str(raw).replace(",", "."))
        except Exception:
            raise ValueError(f"Rating '{aspect}' must be a number between 1 and 5.")
        if not 1 <= value <= 5:
            raise ValueError(f"Rating '{aspect}' must be between 1 and 5 (got {value}).")
        scores[aspect] = value
    if not scores:
        raise ValueError(f"Provide at least one of: {', '.join(_SUPPLIER_ASPECTS)} (each 1..5).")
    rating = supplier.setdefault("rating", {"count": 0, "avg": None, "aspects": {}})
    rating["count"] = int(rating.get("count", 0)) + 1
    aspects = rating.setdefault("aspects", {})
    for aspect, value in scores.items():
        cell = aspects.setdefault(aspect, {"sum": 0.0, "n": 0})
        cell["sum"] += value
        cell["n"] += 1
    aspect_avgs = [cell["sum"] / cell["n"] for cell in aspects.values() if cell.get("n")]
    rating["avg"] = round(sum(aspect_avgs) / len(aspect_avgs), 2) if aspect_avgs else None
    return {"ok": True, "supplierId": supplier["id"], "supplier": supplier["name"],
            "rated": sorted(scores), "rating": {"count": rating["count"], "avg": rating["avg"],
            "aspects": {k: round(v["sum"] / v["n"], 2) for k, v in aspects.items() if v.get("n")}}}


def _supplier_offers_for_category(category_id: str, market: str, region_id: str | None) -> list[dict]:
    offers = []
    for s in TURKEY_SUPPLIERS:
        if s["market"] != market:
            continue
        delivers_here = (not region_id) or (not s["deliveryZones"]) or (region_id in s["deliveryZones"])
        for p in s["products"]:
            if p["categoryId"] != category_id:
                continue
            offers.append({
                "supplierId": s["id"], "supplier": s["name"], "regionId": s["regionId"],
                "regionFa": s["regionFa"], "phone": s["phone"],
                "product": p["name"], "unit": p["unit"], "priceTry": p["priceTry"],
                "stock": p["stock"], "minOrder": p["minOrder"], "deliveryDays": p["deliveryDays"],
                "ratingAvg": (s.get("rating") or {}).get("avg"),
                "ratingCount": (s.get("rating") or {}).get("count", 0),
                "deliversHere": delivers_here, "sample": s.get("sample", False),
            })
    offers.sort(key=lambda o: (o["priceTry"], o["deliveryDays"]))
    return offers


def _best_offer(offers: list[dict], only_in_zone: bool = True) -> dict | None:
    """Cheapest offer, preferring a high-rated supplier when its price is within 8% of the cheapest."""
    pool = [o for o in offers if o["deliversHere"]] if only_in_zone else list(offers)
    if not pool and only_in_zone:
        pool = list(offers)
    if not pool:
        return None
    cheapest = min(o["priceTry"] for o in pool)
    rated = [o for o in pool if (o["ratingAvg"] or 0) >= 4.5]
    near = [o for o in rated if o["priceTry"] <= cheapest * 1.08]
    if near:
        return sorted(near, key=lambda o: (-(o["ratingAvg"] or 0), o["priceTry"]))[0]
    return next(o for o in pool if o["priceTry"] == cheapest)


def turkey_compare_prices(category_text: str, market: str = "restaurants", region: str | None = None) -> dict:
    market = str(market or "restaurants").strip().lower() or "restaurants"
    if market not in TURKEY_MARKETS:
        raise ValueError(f"Unknown market '{market}'. Use one of: {', '.join(TURKEY_MARKETS)}")
    category = turkey_match_category(str(category_text or ""), market)
    if not category:
        known = "، ".join(c["fa"].split(" (")[0] for c in TURKEY_MARKETS[market]["consumables"][:5])
        raise ValueError(f"No product category matched '{str(category_text or '')[:40]}'. Try e.g.: {known} …")
    region_id = None
    if region:
        region_id = turkey_match_region(str(region), market)
        if not region_id:
            raise ValueError(f"Unknown region '{str(region)[:40]}' for market '{market}'.")
    offers = _supplier_offers_for_category(category["id"], market, region_id)
    sample_present = any(o["sample"] for o in offers)
    stats = None
    recommendation = None
    if offers:
        prices = [o["priceTry"] for o in offers]
        lowest, highest = min(prices), max(prices)
        stats = {"min": lowest, "max": highest, "avg": round(sum(prices) / len(prices), 2),
                 "spreadPct": round((highest - lowest) / lowest * 100, 1) if lowest else 0.0,
                 "offerCount": len(offers), "inZoneCount": sum(1 for o in offers if o["deliversHere"])}
        best = _best_offer(offers)
        if best:
            recommendation = {"supplierId": best["supplierId"], "supplier": best["supplier"],
                              "priceTry": best["priceTry"], "unit": best["unit"],
                              "reason": "قیمت مناسب در محدوده شما" if best["priceTry"] == stats["min"] and best["deliversHere"]
                                        else ("امتیاز بالا (≥۴.۵) با قیمت نزدیک به ارزان‌ترین" if (best["ratingAvg"] or 0) >= 4.5
                                              else "ارزان‌ترین پیشنهاد موجود")}
    return {
        "ok": True, "market": market,
        "category": {"id": category["id"], "fa": category["fa"],
                     "certNote": category.get("certNote")},
        "regionId": region_id,
        "offers": offers[:50],
        "stats": stats,
        "recommendation": recommendation,
        "samplesNote": ("Some offers are from educational sample suppliers with fictional contacts. "
                        "Disable with TURKEY_SEED_SAMPLE_SUPPLIERS=false.") if sample_present else None,
        "message": "هیچ تأمین‌کننده‌ای برای این دسته ثبت نشده است. با POST /api/turkey/suppliers/register اضافه کنید." if not offers else None,
        "disclaimer": "Prices are snapshots reported by suppliers; confirm before ordering.",
    }


def turkey_parse_needs_text(text: str, market: str = "restaurants") -> list[dict]:
    """Parse free text like «مرغ 300، روغن 40 لیتر» into [{category, qty}] needs."""
    needs: list[dict] = []
    ascii_text = str(text or "").translate(DIGIT_TRANSLATION)
    for chunk in re.split(r"[,،;؛\n]+", ascii_text)[:30]:
        chunk = chunk.strip()
        if not chunk:
            continue
        category = turkey_match_category(chunk, market)
        numbers = [float(n.replace(",", "")) for n in re.findall(r"\d+(?:[.,]\d+)?", chunk)]
        qty = int(numbers[0]) if numbers else 0
        if category and qty > 0:
            needs.append({"category": category["id"], "qty": qty})
    merged: dict[str, int] = {}
    for n in needs:
        merged[n["category"]] = merged.get(n["category"], 0) + n["qty"]
    return [{"category": cid, "qty": q} for cid, q in merged.items()][:20]


def turkey_smart_plan(payload: dict) -> dict:
    market = str(payload.get("market") or "restaurants").strip().lower() or "restaurants"
    if market not in TURKEY_MARKETS:
        raise ValueError(f"Unknown market '{market}'. Use one of: {', '.join(TURKEY_MARKETS)}")
    region = str(payload.get("region") or payload.get("regionId") or "").strip()
    region_id = None
    if region:
        region_id = turkey_match_region(region, market)
        if not region_id:
            raise ValueError(f"Unknown region '{region[:40]}' for market '{market}'.")
    needs: list[dict] = []
    dropped: list[str] = []
    warnings: list[str] = []
    if isinstance(payload.get("needs"), list):
        for raw in payload["needs"][:20]:
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("category") or raw.get("categoryId") or raw.get("name") or "")[:40]
            category = turkey_match_category(label, market)
            try:
                qty = int(float(str(raw.get("qty", raw.get("quantity", 0))).replace(",", "")))
            except Exception:
                qty = 0
            if category and qty > 0:
                needs.append({"category": category["id"], "qty": qty})
            elif label:
                dropped.append(label)
    text = str(payload.get("text") or "").strip()[:600]
    if not needs and text:
        needs = turkey_parse_needs_text(text, market)
    if not needs:
        raise ValueError("Provide needs like {\"needs\": [{\"category\": \"مرغ\", \"qty\": 200}]} or text: «مرغ 200، روغن 40».")
    merged: dict[str, int] = {}
    for n in needs:
        merged[n["category"]] = merged.get(n["category"], 0) + n["qty"]

    if dropped:
        warnings.append("این اقلام شناسایی نشدند و از سبد کنار گذاشته شدند: " + "، ".join(dropped))
    lines = []
    grand_total = 0.0
    baseline_total = 0.0
    samples_used = False
    for category_id, qty in merged.items():
        category_fa = next((c["fa"] for c in TURKEY_MARKETS[market]["consumables"] if c["id"] == category_id), category_id)
        offers = _supplier_offers_for_category(category_id, market, region_id)
        in_zone = [o for o in offers if o["deliversHere"]]
        pool = in_zone or offers
        if not pool:
            warnings.append(f"برای «{category_fa}» هیچ پیشنهادی ثبت نشده است.")
            continue
        avg_price = round(sum(o["priceTry"] for o in pool) / len(pool), 2)
        baseline_total += avg_price * qty
        best = _best_offer(pool, only_in_zone=False)  # pool is already zone-filtered
        remaining = float(qty)
        picks = []
        ordered = ([best] + [o for o in pool if o is not best]) if best else pool
        for offer in ordered:
            if remaining <= 0:
                break
            if offer.get("stock") is not None and offer["stock"] <= 0:
                continue
            cap = float(offer["stock"]) if offer.get("stock") is not None else remaining
            take = min(remaining, cap)
            note = None
            if take < offer["minOrder"]:
                take = min(max(float(offer["minOrder"]), qty if remaining == qty else take), cap)
                note = f"به حداقل سفارش {offer['minOrder']} {offer['unit']} افزایش یافت"
            if take <= 0:
                continue
            line_total = round(take * offer["priceTry"], 2)
            grand_total += line_total
            samples_used = samples_used or offer.get("sample", False)
            reason = ""
            if offer is best and (offer["ratingAvg"] or 0) >= 4.5 and offer["priceTry"] > min(o["priceTry"] for o in pool):
                reason = " · انتخاب به‌خاطر امتیاز بالا با قیمت نزدیک"
            picks.append({"supplierId": offer["supplierId"], "supplier": offer["supplier"],
                          "qty": int(take) if take == int(take) else take, "unit": offer["unit"],
                          "priceTry": offer["priceTry"], "lineTotal": line_total,
                          "deliveryDays": offer["deliveryDays"], "phone": offer["phone"],
                          "note": note, "reason": reason.strip(" ·") or None})
            remaining -= take
        if remaining > 0.001:
            warnings.append(f"موجودی اعلام‌شده برای «{category_fa}» کافی نیست؛ {int(remaining)} واحد تأمین نشد.")
        lines.append({"categoryId": category_id, "categoryFa": category_fa, "requestedQty": qty,
                      "avgMarketPrice": avg_price, "offersConsidered": len(pool),
                      "inZoneOffers": len(in_zone), "picks": picks})
    grand_total = round(grand_total, 2)
    baseline_total = round(baseline_total, 2)
    return {
        "ok": True, "market": market, "regionId": region_id,
        "lines": lines,
        "totals": {"grandTotal": grand_total, "avgMarketTotal": baseline_total,
                   "estimatedSavingsVsAvg": round(baseline_total - grand_total, 2)},
        "warnings": warnings,
        "samplesNote": ("Plan uses educational sample suppliers with fictional contacts; it shows the mechanics, "
                        "not real quotes. Disable samples with TURKEY_SEED_SAMPLE_SUPPLIERS=false.") if samples_used else None,
        "disclaimer": "This is a planning suggestion computed from supplier-reported prices, not a binding order.",
    }


_RESTAURANT_SAMPLE_SUPPLIERS = [
    {"name": "عمده‌فروشی Anadolu Gıda", "region": "باغجیلار", "zones": [],
     "products": [{"categoryId": "chicken", "name": "مرغ کامل منجمد", "unit": "کیلوگرم", "priceTry": 128, "stock": 4000, "minOrder": 100, "deliveryDays": 1},
                  {"categoryId": "frying-oil", "name": "روغن آفتابگردان ۱۸ لیتری", "unit": "لیتر", "priceTry": 58, "stock": 8000, "minOrder": 200, "deliveryDays": 1},
                  {"categoryId": "rice", "name": "برنج بالدو ترک", "unit": "کیلوگرم", "priceTry": 46, "stock": 6000, "minOrder": 250, "deliveryDays": 2}]},
    {"name": "تدارکات Marmara Et", "region": "اسنلر", "zones": ["bagcilar", "esenler", "kucukcekmece", "esenyurt"],
     "products": [{"categoryId": "beef", "name": "گوشت گوساله بی‌استخوان", "unit": "کیلوگرم", "priceTry": 289, "stock": 2500, "minOrder": 50, "deliveryDays": 1},
                  {"categoryId": "chicken", "name": "مرغ تازه تک‌تکه", "unit": "کیلوگرم", "priceTry": 134, "stock": 3000, "minOrder": 150, "deliveryDays": 1}]},
    {"name": "سبزیدار Boğaz Sebze", "region": "گونگورن", "zones": [],
     "products": [{"categoryId": "vegetables", "name": "سبد سبزیجات و صیفی رستورانی", "unit": "کیلوگرم", "priceTry": 32, "stock": 5000, "minOrder": 100, "deliveryDays": 0},
                  {"categoryId": "dairy", "name": "پنیر سفید رستورانی", "unit": "کیلوگرم", "priceTry": 118, "stock": 1200, "minOrder": 40, "deliveryDays": 1}]},
    {"name": "توزیع Ege Unlu", "region": "کوچوک‌چکمجه", "zones": [],
     "products": [{"categoryId": "flour-bakery", "name": "آرد نانوایی نوع ۱", "unit": "کیلوگرم", "priceTry": 24, "stock": 10000, "minOrder": 300, "deliveryDays": 2},
                  {"categoryId": "packaging", "name": "ظرف بیرون‌بر کرافت", "unit": "عدد", "priceTry": 2.1, "stock": 200000, "minOrder": 5000, "deliveryDays": 2}]},
    {"name": "لبنیات Karadeniz Süt", "region": "اسنیورت", "zones": [],
     "products": [{"categoryId": "dairy", "name": "ماست صبحانه ده‌کیلویی", "unit": "کیلوگرم", "priceTry": 112, "stock": 2000, "minOrder": 50, "deliveryDays": 1},
                  {"categoryId": "beverages", "name": "آب معدنی ۱.۵ لیتری", "unit": "عدد", "priceTry": 9, "stock": 20000, "minOrder": 500, "deliveryDays": 1}]},
    {"name": "عمده Hünkar Baharat", "region": "عمرانیه", "zones": ["umraniye", "pendik", "kartal", "sultanbeyli"],
     "products": [{"categoryId": "legumes-spices", "name": "عدس و لوبیا فله", "unit": "کیلوگرم", "priceTry": 68, "stock": 1500, "minOrder": 25, "deliveryDays": 2},
                  {"categoryId": "rice", "name": "برنج اوسمانجیک", "unit": "کیلوگرم", "priceTry": 49, "stock": 4000, "minOrder": 200, "deliveryDays": 2}]},
    {"name": "تازه‌رسان Pera Tavukçuluk", "region": "پندیک", "zones": [],
     "products": [{"categoryId": "chicken", "name": "مرغ تازه روزانه", "unit": "کیلوگرم", "priceTry": 142, "stock": 2000, "minOrder": 80, "deliveryDays": 0}]},
    {"name": "روغن‌پخش Tarihi Yağ", "region": "کارتال", "zones": [],
     "products": [{"categoryId": "frying-oil", "name": "روغن سرخ‌کردنی حرفه‌ای", "unit": "لیتر", "priceTry": 61, "stock": 6000, "minOrder": 150, "deliveryDays": 2},
                  {"categoryId": "beverages", "name": "نوشابه قوطی ۲۴ تایی", "unit": "عدد", "priceTry": 11, "stock": 15000, "minOrder": 480, "deliveryDays": 2}]},
    {"name": "قصابی Şehzade Kasap", "region": "سلطان‌بیلی", "zones": ["sultanbeyli", "umraniye", "kartal", "pendik"],
     "products": [{"categoryId": "beef", "name": "گوشت گوسفندی تازه", "unit": "کیلوگرم", "priceTry": 315, "stock": 1800, "minOrder": 40, "deliveryDays": 1}]},
    {"name": "بسته‌بان İstanbul Paket", "region": "غازی‌عثمان‌پاشا", "zones": [],
     "products": [{"categoryId": "packaging", "name": "جعبه پیتزا و پک سلفونی", "unit": "عدد", "priceTry": 1.9, "stock": 150000, "minOrder": 3000, "deliveryDays": 3}]},
    {"name": "پخش Dostlar Gıda", "region": "باغجیلار", "zones": [],
     "products": [{"categoryId": "rice", "name": "برنج ایرانی دم‌سیاه", "unit": "کیلوگرم", "priceTry": 52, "stock": 3500, "minOrder": 150, "deliveryDays": 2},
                  {"categoryId": "frying-oil", "name": "روغن مایع کم‌اشباع", "unit": "لیتر", "priceTry": 64, "stock": 4000, "minOrder": 100, "deliveryDays": 2},
                  {"categoryId": "legumes-spices", "name": "ادویه ترکیبی رستورانی", "unit": "کیلوگرم", "priceTry": 74, "stock": 1200, "minOrder": 30, "deliveryDays": 2}]},
    {"name": "سبزه‌فروش Yıldız Meyve", "region": "اسنلر", "zones": [],
     "products": [{"categoryId": "vegetables", "name": "گوجه، خیار و سبزی روزانه", "unit": "کیلوگرم", "priceTry": 35, "stock": 4000, "minOrder": 120, "deliveryDays": 0}]},
    {"name": "نان‌ساز Saray Un", "region": "گونگورن", "zones": [],
     "products": [{"categoryId": "flour-bakery", "name": "آرد سوپر لوکس پیتزا", "unit": "کیلوگرم", "priceTry": 26, "stock": 9000, "minOrder": 250, "deliveryDays": 2}]},
    {"name": "گوشت‌بر Kervan Et", "region": "کوچوک‌چکمجه", "zones": [],
     "products": [{"categoryId": "beef", "name": "دنباله و سردست گوساله", "unit": "کیلوگرم", "priceTry": 342, "stock": 1500, "minOrder": 60, "deliveryDays": 1},
                  {"categoryId": "chicken", "name": "فیله مرغ", "unit": "کیلوگرم", "priceTry": 149, "stock": 2500, "minOrder": 200, "deliveryDays": 1}]},
    {"name": "لبنی‌سان Lezzet Süt", "region": "اسنیورت", "zones": [],
     "products": [{"categoryId": "dairy", "name": "کره و خامه رستورانی", "unit": "کیلوگرم", "priceTry": 125, "stock": 1500, "minOrder": 60, "deliveryDays": 1},
                  {"categoryId": "vegetables", "name": "سیب‌زمینی و پیاز مصرفی", "unit": "کیلوگرم", "priceTry": 38, "stock": 2500, "minOrder": 150, "deliveryDays": 1}]},
]


def _turkey_restaurant_sample_suppliers() -> list[dict]:
    suppliers = []
    for i, item in enumerate(_RESTAURANT_SAMPLE_SUPPLIERS):
        seed = f"sample-supplier-{i}"
        raw = {
            "name": item["name"], "region": item["region"], "deliveryZones": item["zones"],
            "phone": "+90 53" + str(_sample_det(seed + "-t1", 0, 9)) + " " +
                     f"{_sample_det(seed + '-t2', 100, 999)} {_sample_det(seed + '-t3', 1000, 9999)}",
            "products": item["products"],
            "source": "seed-sample", "sample": True,
        }
        supplier = normalize_turkey_supplier(raw, "restaurants")
        if supplier:
            suppliers.append(supplier)
    return suppliers


def turkey_seed_sample_suppliers() -> dict:
    generated = _turkey_restaurant_sample_suppliers()
    existing = {s["id"] for s in TURKEY_SUPPLIERS}
    fresh = [s for s in generated if s["id"] not in existing]
    TURKEY_SUPPLIERS.extend(fresh)
    return {"ok": True, "imported": len(fresh), "skippedDuplicates": len(generated) - len(fresh),
            "total": sum(1 for s in TURKEY_SUPPLIERS if s["market"] == "restaurants"),
            "note": "Educational sample suppliers (sample:true) with fictional contacts."}


if env_flag("TURKEY_SEED_SAMPLE_SUPPLIERS", True):
    try:
        turkey_seed_sample_suppliers()
    except Exception:
        pass  # sample seeding must never block startup


def search_vendors(payload: dict):
    """Use an operator-configured public-search adapter; never scrape search engines directly."""
    query = str(payload.get("query", "")).strip()[:300]
    location = str(payload.get("location", "Tehran")).strip()[:100]
    categories = payload.get("categories") or []
    if not query:
        raise ValueError("Search query is required.")
    if not isinstance(categories, list):
        categories = []
    categories = [str(x)[:80] for x in categories[:8]]
    webhook = os.getenv("VENDOR_SEARCH_WEBHOOK_URL", "")
    token = os.getenv("VENDOR_SEARCH_WEBHOOK_TOKEN", "")
    if webhook:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        status, response = post_json(webhook, {"query": query, "location": location,
                                               "categories": categories, "limit": 12}, headers)
        items = response.get("items", []) if isinstance(response, dict) else []
        clean = []
        for item in items[:12]:
            if not isinstance(item, dict):
                continue
            clean.append({
                "name": str(item.get("name", ""))[:160],
                "website": str(item.get("website", ""))[:500],
                "category": str(item.get("category", ""))[:100],
                "location": str(item.get("location", ""))[:120],
                "evidence": str(item.get("evidence", item.get("source", "")))[:500],
                "phone": str(item.get("phone", ""))[:80],
                "summary": str(item.get("summary", ""))[:500],
                "verified": bool(item.get("verified", False)),
            })
        return {"ok": True, "configured": True, "providerStatus": status, "items": clean,
                "disclaimer": "Search results are candidates, not endorsements. Verify scope, references and credentials."}
    text = f"{query} {location}".strip()
    return {
        "ok": True,
        "configured": False,
        "items": [],
        "searchLinks": {
            "google": "https://www.google.com/search?q=" + quote_plus(text),
            "linkedin": "https://www.linkedin.com/search/results/companies/?keywords=" + quote_plus(text),
        },
        "disclaimer": "No search adapter is configured. Use the generated public-search links or add candidates manually.",
    }


def search_clinics(payload: dict):
    """Search adapter for public medical-clinic discovery; never collects patient data."""
    query = str(payload.get("query", "")).strip()[:350]
    location = str(payload.get("location", "Tehran")).strip()[:120]
    specialty = str(payload.get("specialty", "medical clinic")).strip()[:120]
    engines = payload.get("engines") if isinstance(payload.get("engines"), list) else []
    engines = [str(x).lower()[:30] for x in engines[:8]]
    if not query:
        query = f"{specialty} {location} official website contact"
    combined = f"{query} {location}".strip()
    webhook = os.getenv("CLINIC_SEARCH_WEBHOOK_URL", "")
    token = os.getenv("CLINIC_SEARCH_WEBHOOK_TOKEN", "")
    if webhook:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        status, response = post_json(webhook, {
            "query": query, "location": location, "specialty": specialty,
            "engines": engines, "limit": 20, "publicBusinessOnly": True,
        }, headers)
        source_items = response.get("items", []) if isinstance(response, dict) else []
        items = []
        for item in source_items[:20]:
            if not isinstance(item, dict):
                continue
            items.append({
                "name": str(item.get("name", ""))[:180],
                "website": str(item.get("website", ""))[:500],
                "phone": normalize_public_phone(str(item.get("phone", "")))[:100],
                "email": str(item.get("email", ""))[:180],
                "whatsapp": normalize_public_phone(str(item.get("whatsapp", "")))[:100],
                "whatsappLinks": [str(x)[:500] for x in item.get("whatsappLinks", [])[:10]] if isinstance(item.get("whatsappLinks"), list) else [],
                "address": str(item.get("address", ""))[:500],
                "specialty": str(item.get("specialty", specialty))[:150],
                "tags": [str(x)[:80] for x in item.get("tags", [])[:30]] if isinstance(item.get("tags"), list) else [],
                "source": str(item.get("source", item.get("evidence", "")))[:500],
                "summary": str(item.get("summary", ""))[:600],
                "verified": bool(item.get("verified", False)),
            })
        return {"ok": True, "configured": True, "mode": "api", "provider": "webhook", "providerStatus": status, "items": items,
                "disclaimer": "Candidates only. Verify medical license, identity, public contact details and active status independently."}
    google_places_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip() or os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if google_places_key and (not engines or "google" in engines):
        field_mask = ",".join([
            "places.id", "places.displayName", "places.formattedAddress",
            "places.nationalPhoneNumber", "places.internationalPhoneNumber",
            "places.websiteUri", "places.googleMapsUri", "places.primaryTypeDisplayName",
            "places.businessStatus",
        ])
        status, response = post_json(
            "https://places.googleapis.com/v1/places:searchText",
            {"textQuery": combined, "languageCode": "fa", "pageSize": 20},
            {"X-Goog-Api-Key": google_places_key, "X-Goog-FieldMask": field_mask},
            timeout=25,
        )
        places = response.get("places", []) if isinstance(response, dict) else []
        items = []
        for place in places[:20]:
            if not isinstance(place, dict):
                continue
            display = place.get("displayName") if isinstance(place.get("displayName"), dict) else {}
            primary_type = place.get("primaryTypeDisplayName") if isinstance(place.get("primaryTypeDisplayName"), dict) else {}
            website = str(place.get("websiteUri", ""))[:500]
            maps_url = str(place.get("googleMapsUri", ""))[:500]
            business_status = str(place.get("businessStatus", ""))[:60]
            no_site = not bool(website)
            items.append({
                "name": str(display.get("text", ""))[:180],
                "website": website,
                "phone": normalize_public_phone(str(place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber") or ""))[:100],
                "email": "", "whatsapp": "", "whatsappLinks": [],
                "address": str(place.get("formattedAddress", ""))[:500],
                "specialty": str(primary_type.get("text") or specialty)[:150],
                "tags": [str(primary_type.get("text") or specialty)[:80]],
                "source": maps_url,
                "summary": f"Google Places public business result. Status: {business_status or 'not provided'}",
                "verified": False,
                "resultType": "structured-medical-entity",
                "placeId": str(place.get("id", ""))[:200],
                "websiteStatus": "no-website-found" if no_site else "official-website-provided",
                "seoScore": 0 if no_site else 45,
                "opportunityScore": 94 if no_site else 65,
                "recommendedPackage": "Website Launch + Local SEO" if no_site else "SEO Audit + Web Design Review",
            })
        return {
            "ok": True, "configured": True, "mode": "api", "provider": "google-places",
            "providerStatus": status, "items": items,
            "disclaimer": "Google Places results are public business candidates, not medical-quality rankings. Verify identity, license, official website and contact details independently.",
        }

    brave_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if brave_key:
        params = urlencode({"q": combined, "count": 20, "search_lang": "fa", "safesearch": "strict"})
        status, response = get_json("https://api.search.brave.com/res/v1/web/search?" + params,
                                    {"X-Subscription-Token": brave_key})
        results = ((response.get("web") or {}).get("results") or []) if isinstance(response, dict) else []
        items = []
        for result in results[:20]:
            if not isinstance(result, dict):
                continue
            items.append({"name": str(result.get("title", ""))[:180],
                          "website": str(result.get("url", ""))[:500],
                          "phone": "", "email": "", "whatsapp": "", "whatsappLinks": [],
                          "address": "", "specialty": specialty, "tags": [],
                          "source": str(result.get("url", ""))[:500],
                          "summary": str(result.get("description", ""))[:600],
                          "verified": False})
        return {"ok": True, "configured": True, "mode": "api", "provider": "brave", "providerStatus": status,
                "items": items,
                "disclaimer": "Brave web results are discovery candidates, not verified medical providers. Confirm license, identity and public contact information."}
    encoded = quote_plus(combined)
    directory_query = quote_plus(f"site:paziresh24.com OR site:nobat.ir {combined}")
    return {
        "ok": True,
        "configured": False,
        "mode": "links",
        "items": [],
        "requiredConfiguration": ["GOOGLE_PLACES_API_KEY", "BRAVE_SEARCH_API_KEY", "CLINIC_SEARCH_WEBHOOK_URL"],
        "searchLinks": {
            "duckduckgo": "https://duckduckgo.com/?q=" + encoded,
            "google": "https://www.google.com/search?q=" + encoded,
            "bing": "https://www.bing.com/search?q=" + encoded,
            "brave": "https://search.brave.com/search?q=" + encoded,
            "medicalDirectories": "https://www.google.com/search?q=" + directory_query,
        },
        "disclaimer": "No clinic-search adapter is configured. Links search public business information only; do not collect patient data or infer sensitive traits.",
    }


def normalize_search_result_url(href: str, base_url: str = ""):
    if not href:
        return ""
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    query = parse_qs(parsed.query)
    if parsed.path == "/url" and query.get("q"):
        absolute = query["q"][0]
    elif query.get("uddg"):
        absolute = unquote(query["uddg"][0])
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    blocked = {"google.com", "www.google.com", "bing.com", "www.bing.com",
               "duckduckgo.com", "www.duckduckgo.com", "search.brave.com"}
    if parsed.netloc.lower() in blocked:
        return ""
    return absolute.split("#", 1)[0]


def clean_search_result_title(anchor):
    heading = anchor.find(["h1", "h2", "h3"]) if hasattr(anchor, "find") else None
    title = " ".join((heading or anchor).get_text(" ", strip=True).split())
    title = re.sub(r"https?://\S+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\b(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*[›»|]\s*.*$", "", title)
    title = re.sub(r"\s{2,}", " ", title).strip(" -–—|›")
    return title


def classify_search_candidate(title: str, url: str):
    combined = f"{title} {url}".lower()
    list_terms = ("بهترین", "لیست", "معرفی", "10 ", "۱۰ ", "راهنما", "قیمت", "هزینه", "best-", "top-", "list-")
    directory_terms = ("profile", "clinicdetail", "jobsearch", "/doctor", "/dr/", "directory")
    medical_terms = ("کلینیک", "درمانگاه", "مرکز پزشکی", "دکتر", "پزشک", "clinic", "medical", "dermatology", "dental")
    if any(term in combined for term in list_terms):
        return "list-article", "Extract clinics from article before adding as leads"
    if any(term in combined for term in directory_terms):
        return "directory-profile", "Verify profile identity and resolve official website"
    if any(term in combined for term in medical_terms):
        return "clinic-candidate", "Verify license, address and public contact details"
    return "web-result", "Review before adding as a clinic lead"


def parse_search_html(payload: dict):
    html = str(payload.get("html", ""))
    if not html.strip():
        raise ValueError("HTML content is required.")
    if len(html.encode("utf-8")) > 1_500_000:
        raise ValueError("HTML input is larger than 1.5 MB.")
    engine = str(payload.get("engine", "generic")).lower()[:30]
    source_url = str(payload.get("sourceUrl", ""))[:500]
    specialty = str(payload.get("specialty", "medical clinic"))[:150]
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()

    selector_map = {
        "google": ["a:has(h3)", "div.MjjYud a[href]"],
        "bing": ["li.b_algo h2 a", "h2 a[href]"],
        "duckduckgo": ["a.result__a", ".result__title a"],
        "brave": ["a.result-header", "a[href]:has(h3)"],
        "generic": ["h2 a[href]", "h3 a[href]", "a[href]"],
    }
    selectors = selector_map.get(engine, selector_map["generic"])
    anchors = []
    for selector in selectors:
        try:
            anchors.extend(soup.select(selector))
        except Exception:
            continue
    for anchor in anchors:
        if anchor.name != "a":
            anchor = anchor.find("a", href=True)
        if not anchor or not anchor.get("href"):
            continue
        url = normalize_search_result_url(anchor.get("href", ""), source_url)
        if not url or url in seen:
            continue
        title = clean_search_result_title(anchor)
        if len(title) < 3:
            continue
        seen.add(url)
        container = anchor.find_parent(["article", "li", "div"]) or anchor.parent
        text = " ".join(container.get_text(" ", strip=True).split()) if container else title
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        phone_match = re.search(r"(?:\+?98|0)?(?:21[-\s]?\d{5,8}|9\d{9})", text)
        signals = extract_public_contact_signals(str(container or anchor), source_url or url)
        result_type, action = classify_search_candidate(title, url)
        items.append({"name": title[:180], "website": url[:500],
                      "domain": (urlparse(url).hostname or "")[:200],
                      "phone": (signals["phoneNumbers"][0] if signals["phoneNumbers"] else phone_match.group(0) if phone_match else ""),
                      "email": signals["emails"][0] if signals["emails"] else "",
                      "whatsapp": signals["whatsappNumber"], "whatsappLinks": signals["whatsappLinks"],
                      "tags": signals["tags"], "address": signals["addresses"][0] if signals["addresses"] else "",
                      "specialty": specialty, "source": source_url or url[:500],
                      "summary": text[:600], "resultType": result_type,
                      "recommendedAction": action, "verified": False})
        if len(items) >= 50:
            break

    # Add structured medical entities from directory pages when available.
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.get_text(strip=True) or "{}")
        except Exception:
            continue
        queue = data if isinstance(data, list) else [data]
        while queue:
            node = queue.pop(0)
            if isinstance(node, list):
                queue.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            queue.extend(v for v in node.values() if isinstance(v, (dict, list)))
            node_type = node.get("@type", "")
            types = node_type if isinstance(node_type, list) else [node_type]
            if not any(str(t) in {"MedicalClinic", "MedicalBusiness", "Physician", "Dentist", "LocalBusiness"} for t in types):
                continue
            name = str(node.get("name", "")).strip()
            url = normalize_search_result_url(str(node.get("url", "")), source_url)
            key = url or name
            if not name or key in seen:
                continue
            address = node.get("address", "")
            if isinstance(address, dict):
                address = "، ".join(str(address.get(k, "")) for k in ("addressLocality", "streetAddress") if address.get(k))
            seen.add(key)
            same_as = node.get("sameAs", [])
            if not isinstance(same_as, list):
                same_as = [same_as]
            whatsapp_links = [str(x)[:500] for x in same_as if any(h in str(x).lower() for h in WHATSAPP_HOSTS)]
            whatsapp_number = ""
            if whatsapp_links:
                whatsapp_number = extract_public_contact_signals(f'<a href="{whatsapp_links[0]}">WhatsApp</a>', url or source_url)["whatsappNumber"]
            node_tags = node.get("keywords", [])
            if not isinstance(node_tags, list):
                node_tags = [x.strip() for x in re.split(r"[,،|]", str(node_tags)) if x.strip()]
            items.append({"name": name[:180], "website": url[:500],
                          "domain": (urlparse(url).hostname or "")[:200],
                          "phone": normalize_public_phone(str(node.get("telephone", "")))[:100],
                          "email": str(node.get("email", "")).removeprefix("mailto:")[:180],
                          "whatsapp": whatsapp_number, "whatsappLinks": whatsapp_links,
                          "tags": [str(x)[:80] for x in node_tags[:20]], "address": str(address)[:500],
                          "specialty": specialty, "source": source_url or url,
                          "summary": str(node.get("description", ""))[:600],
                          "resultType": "structured-medical-entity",
                          "recommendedAction": "Verify license and official ownership", "verified": False})
            if len(items) >= 50:
                break
    return {"ok": True, "engine": engine, "items": items,
            "count": len(items),
            "disclaimer": "Imported search results are unverified candidates. Confirm identity, medical license and active public contact details."}


def enrich_clinic_candidates(payload: dict):
    candidates = payload.get("items") if isinstance(payload.get("items"), list) else []
    specialty = str(payload.get("specialty", "medical clinic"))[:150]
    if not candidates:
        raise ValueError("At least one candidate is required for enrichment.")
    enriched, errors, seen = [], [], set()
    for candidate in candidates[:6]:
        if not isinstance(candidate, dict):
            continue
        url = str(candidate.get("website", "")).strip()
        if not url:
            continue
        ok, reason = public_url(url)
        if not ok:
            errors.append({"url": url[:500], "error": reason})
            continue
        if os.getenv("ENRICH_REQUIRE_ROBOTS", "false").lower() == "true" and not robots_allows(url):
            errors.append({"url": url[:500], "error": "robots.txt did not allow enrichment"})
            continue
        try:
            status, final_url, html, content_type, _ = fetch(url, timeout=15, limit=1_500_000)
            if status != 200 or ("html" not in content_type.lower() and "<html" not in html[:1000].lower()):
                raise ValueError(f"HTTP {status} or non-HTML response")
            contact_signals = extract_public_contact_signals(html, final_url)
            parsed = parse_search_html({"html": html, "engine": "generic", "sourceUrl": final_url,
                                        "specialty": specialty}).get("items", [])
            useful = []
            for item in parsed:
                kind = item.get("resultType")
                if kind in {"clinic-candidate", "directory-profile", "structured-medical-entity"}:
                    useful.append(item)
            if useful:
                for item in useful[:15]:
                    key = item.get("website") or item.get("name")
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    item["parentSource"] = final_url
                    item["enriched"] = True
                    enriched.append(item)
            else:
                parser = AuditParser(final_url)
                parser.feed(html)
                name = str(candidate.get("name", "")).strip() or parser.title or (urlparse(final_url).hostname or "Clinic")
                kind, action = classify_search_candidate(name, final_url)
                key = final_url
                if key not in seen:
                    seen.add(key)
                    enriched.append({"name": name[:180], "website": final_url[:500],
                                     "domain": (urlparse(final_url).hostname or "")[:200],
                                     "phone": (contact_signals["phoneNumbers"][0] if contact_signals["phoneNumbers"] else str(candidate.get("phone", "")))[:100],
                                     "email": (contact_signals["emails"][0] if contact_signals["emails"] else str(candidate.get("email", "")))[:180],
                                     "whatsapp": contact_signals["whatsappNumber"] or str(candidate.get("whatsapp", ""))[:100],
                                     "whatsappLinks": contact_signals["whatsappLinks"], "tags": contact_signals["tags"],
                                     "address": (contact_signals["addresses"][0] if contact_signals["addresses"] else str(candidate.get("address", "")))[:500],
                                     "specialty": specialty, "source": final_url,
                                     "summary": parser.description[:600], "resultType": kind,
                                     "recommendedAction": action, "verified": False, "enriched": True})
        except Exception as exc:
            errors.append({"url": url[:500], "error": str(exc)[:300]})
    return {"ok": True, "items": enriched[:60], "count": len(enriched[:60]), "errors": errors,
            "disclaimer": "Enrichment resolves public pages into unverified clinic candidates. Verify license, identity and public contact details before outreach."}


def scraper_allowed_domains():
    return {item.strip().lower().lstrip(".") for item in
            re.split(r"[,\n]", os.getenv("SCRAPER_ALLOWED_DOMAINS", "")) if item.strip()}


def domain_is_allowed(host: str, allowed: set[str]):
    host = host.lower().rstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in allowed)


def robots_allows(url: str):
    if os.getenv("SCRAPER_IGNORE_ROBOTS", "false").lower() == "true":
        return True
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        status, _, text, _, _ = fetch(robots_url, timeout=8, limit=300_000)
        if status != 200:
            return False
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(text.splitlines())
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return False


def scrape_clinic_directory(payload: dict):
    url = str(payload.get("url", "")).strip()
    specialty = str(payload.get("specialty", "medical clinic"))[:150]
    if not url:
        raise ValueError("Directory URL is required.")
    ok, reason = public_url(url)
    if not ok:
        raise ValueError(reason)
    allowed = scraper_allowed_domains()
    host = urlparse(url).hostname or ""
    if not allowed:
        raise ValueError("SCRAPER_ALLOWED_DOMAINS is empty. Add approved public directory domains before server-side scraping.")
    if not domain_is_allowed(host, allowed):
        raise ValueError("This domain is not in SCRAPER_ALLOWED_DOMAINS.")
    forbidden = {"google.com", "bing.com", "duckduckgo.com", "search.brave.com"}
    if any(host == item or host.endswith("." + item) for item in forbidden):
        raise ValueError("Automatic scraping of search-engine result pages is disabled. Use HTML import or an approved search API.")
    if not robots_allows(url):
        raise ValueError("robots.txt does not allow this scraper or could not be verified.")
    status, final_url, html, content_type, elapsed = fetch(url, timeout=20, limit=1_500_000)
    if status != 200 or ("html" not in content_type.lower() and "<html" not in html[:1000].lower()):
        raise ValueError(f"Directory returned HTTP {status} or non-HTML content.")
    result = parse_search_html({"html": html, "engine": "generic", "sourceUrl": final_url,
                                "specialty": specialty})
    result.update({"url": final_url, "elapsedSeconds": elapsed, "robotsAllowed": True})
    return result


def run_configured_discovery():
    raw_urls = os.getenv("CLINIC_DISCOVERY_URLS", "")
    urls = [item.strip() for item in re.split(r"[,\n]", raw_urls) if item.strip()][:5]
    if not urls:
        return {"ok": True, "skipped": True, "message": "CLINIC_DISCOVERY_URLS is empty.", "items": []}
    all_items, errors = [], []
    seen = set()
    for url in urls:
        try:
            result = scrape_clinic_directory({"url": url, "specialty": "medical clinic"})
            for item in result.get("items", []):
                key = item.get("website") or item.get("name")
                if key and key not in seen:
                    seen.add(key)
                    all_items.append(item)
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)[:300]})
    delivered = False
    persistence = None
    if all_items and (os.getenv("SUPABASE_URL") or os.getenv("LEAD_DATABASE_WEBHOOK_URL") or os.getenv("LEAD_INGEST_WEBHOOK_URL")):
        try:
            persistence = persist_leads_database(all_items)
            delivered = True
        except Exception as exc:
            errors.append({"url": "database", "error": str(exc)[:300]})
    return {"ok": True, "skipped": False, "count": len(all_items), "items": all_items[:100],
            "errors": errors, "persisted": delivered, "persistence": persistence,
            "warning": "Without Supabase or a lead database webhook, serverless cron results are not persisted."}


def clinic_export_rows(items: list[dict]):
    rows = []
    for item in items[:500]:
        if not isinstance(item, dict):
            continue
        ai = item.get("aiAnalysis") if isinstance(item.get("aiAnalysis"), dict) else {}
        rows.append({
            "name": str(ai.get("normalizedName") or item.get("name", ""))[:250],
            "website": str(item.get("website", ""))[:500],
            "phone": str(item.get("phone", ""))[:100],
            "address": str(item.get("address", ""))[:500],
            "specialty": str(ai.get("specialty") or item.get("specialty", ""))[:180],
            "result_type": str(ai.get("resultType") or item.get("resultType", "candidate"))[:80],
            "ai_confidence": ai.get("confidence", ""),
            "ai_priority": str(ai.get("priority", ""))[:30],
            "ai_reason": str(ai.get("reason", ""))[:500],
            "recommended_next_step": str(ai.get("recommendedNextStep") or item.get("recommendedAction", ""))[:500],
            "source": str(item.get("source", ""))[:500],
            "verified": bool(item.get("verified", False)),
        })
    return rows


def export_clinic_candidates(payload: dict):
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    rows = clinic_export_rows(items)
    if not rows:
        raise ValueError("No clinic candidates were supplied for export.")
    fmt = str(payload.get("format", "csv")).lower()
    title = str(payload.get("title", "Clinic Discovery Results"))[:150]
    columns = ["name", "website", "phone", "address", "specialty", "result_type", "ai_confidence", "ai_priority", "ai_reason", "recommended_next_step", "source", "verified"]
    if fmt == "csv":
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
        return ("\ufeff" + stream.getvalue()).encode("utf-8"), "clinic-discovery.csv", "text/csv; charset=utf-8"
    if fmt == "xlsx":
        if not OPENPYXL_AVAILABLE:
            raise ValueError("Excel export requires openpyxl.")
        wb = Workbook()
        ws = wb.active
        ws.title = "Clinic Leads"
        ws.sheet_view.rightToLeft = True
        ws.freeze_panes = "A2"
        header_fill = PatternFill("solid", fgColor="17324D")
        for col, name in enumerate(columns, 1):
            cell = ws.cell(1, col, name)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        for row_index, row in enumerate(rows, 2):
            for col, name in enumerate(columns, 1):
                cell = ws.cell(row_index, col, row.get(name, ""))
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        widths = [28, 42, 18, 38, 25, 22, 14, 14, 45, 45, 42, 12]
        for index, width in enumerate(widths, 1):
            ws.column_dimensions[chr(64 + index)].width = width
        output = BytesIO()
        wb.save(output)
        return output.getvalue(), "clinic-discovery.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if fmt == "pdf":
        if not PILLOW_AVAILABLE:
            raise ValueError("PDF export requires Pillow.")
        width, height = 1654, 1169
        margin = 65
        bundled = ROOT / "assets" / "fonts"
        regular_path = str(bundled / "DejaVuSans.ttf")
        bold_path = str(bundled / "DejaVuSans-Bold.ttf")
        layout = ImageFont.Layout.RAQM if hasattr(ImageFont, "Layout") and RAQM_AVAILABLE else ImageFont.Layout.BASIC if hasattr(ImageFont, "Layout") else None
        regular = ImageFont.truetype(regular_path, 20, layout_engine=layout)
        small = ImageFont.truetype(regular_path, 15, layout_engine=layout)
        bold_font = ImageFont.truetype(bold_path, 27, layout_engine=layout)
        row_font = ImageFont.truetype(bold_path, 18, layout_engine=layout)
        def shape(value):
            value = str(value)
            if RAQM_AVAILABLE or not re.search(r"[\u0600-\u06FF]", value):
                return value
            if BIDI_FALLBACK_AVAILABLE:
                try:
                    return bidi_get_display(arabic_reshaper.reshape(value))
                except Exception:
                    return value
            return value
        def draw_text(draw, xy, value, font, fill, anchor="ra"):
            if RAQM_AVAILABLE:
                try:
                    draw.text(xy, str(value), font=font, fill=fill, anchor=anchor, direction="rtl", language="fa")
                    return
                except (ValueError, TypeError, KeyError):
                    pass
            draw.text(xy, shape(value), font=font, fill=fill, anchor=anchor)
        pages = []
        per_page = 10
        for offset in range(0, len(rows), per_page):
            page = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(page)
            draw.rectangle((0, 0, width, 105), fill="#17324D")
            draw_text(draw, (width-margin, 34), title, bold_font, "white")
            draw_text(draw, (margin, 42), f"{offset+1}-{min(offset+per_page,len(rows))} / {len(rows)}", regular, "#C6D7E4", anchor="la")
            y = 130
            for number, row in enumerate(rows[offset:offset+per_page], offset+1):
                draw.rounded_rectangle((margin, y, width-margin, y+86), radius=12, fill="#F4F7F9", outline="#DCE6EE")
                draw_text(draw, (width-margin-18, y+12), f"{number}. {row['name']}", row_font, "#17324D")
                details = f"{row['specialty']} | {row['result_type']} | AI: {row['ai_confidence'] or '—'} | {row['phone'] or '—'}"
                draw_text(draw, (width-margin-18, y+43), details[:150], small, "#526B7C")
                draw.text((margin+18, y+60), row['website'][:110], font=small, fill="#246BFD", anchor="ls")
                y += 94
            pages.append(page)
        output = BytesIO()
        pages[0].save(output, format="PDF", save_all=True, append_images=pages[1:], resolution=150.0, title=title)
        return output.getvalue(), "clinic-discovery.pdf", "application/pdf"
    raise ValueError("Export format must be csv, xlsx or pdf.")


def first_environment_value(*names):
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value, name
    return "", ""


def supabase_settings():
    url, url_name = first_environment_value("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL", "VITE_SUPABASE_URL", "PUBLIC_SUPABASE_URL")
    key, key_name = first_environment_value("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_KEY")
    table = re.sub(r"[^a-zA-Z0-9_]", "", os.getenv("SUPABASE_LEADS_TABLE", "clinic_leads")) or "clinic_leads"
    return {"url": url.rstrip("/"), "key": key, "table": table, "urlVariable": url_name, "keyVariable": key_name,
            "configured": bool(url and key)}


def lead_dedupe_key(item: dict, website: str) -> str:
    if website:
        try:
            parsed = urlparse(website if urlparse(website).scheme else "https://" + website)
            host = (parsed.hostname or "").lower().removeprefix("www.")
            if host:
                return "website:" + host[:220]
        except Exception:
            pass
    identity = "|".join([
        str(item.get("placeId", "")), str(item.get("name", "")),
        str(item.get("phone", "")), str(item.get("address", item.get("area", ""))),
        str(item.get("source", "")),
    ]).strip("|").lower()
    return "entity:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def normalize_lead_row(item: dict):
    website = str(item.get("website", "")).strip()[:500]
    return {
        "dedupe_key": lead_dedupe_key(item, website),
        "name": str(item.get("name", "Clinic candidate"))[:180],
        "website": website,
        "phone": str(item.get("phone", ""))[:100],
        "email": str(item.get("email", ""))[:180],
        "whatsapp": str(item.get("whatsapp", item.get("whatsappNumber", "")))[:100],
        "tags": [str(x)[:80] for x in item.get("tags", [])[:40]] if isinstance(item.get("tags"), list) else [],
        "address": str(item.get("address", item.get("area", "")))[:500],
        "specialty": str(item.get("specialty", item.get("services", "")))[:180],
        "source": str(item.get("source", ""))[:500],
        "result_type": str(item.get("resultType", "candidate"))[:80],
        "status": str(item.get("status", "new"))[:50],
        "seo_score": int(item.get("seo", item.get("seoScore", 0)) or 0),
        "opportunity_score": int(item.get("opportunity", item.get("opportunityScore", 0)) or 0),
        "raw": item,
    }


def persist_leads_database(items: list[dict]):
    rows = [normalize_lead_row(item) for item in items[:100] if isinstance(item, dict)]
    rows = [row for row in rows if row["name"] and (row["website"] or row["phone"] or row["email"] or row["whatsapp"] or row["address"] or row["source"])]
    if not rows:
        raise ValueError("No valid lead rows were supplied. A name plus website, phone, address or source is required.")
    settings = supabase_settings()
    supabase_url, supabase_key, table = settings["url"], settings["key"], settings["table"]
    if settings["configured"]:
        endpoint = f"{supabase_url}/rest/v1/{table}?on_conflict=dedupe_key"
        response = requests.post(endpoint, headers={"apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}", "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation"}, json=rows, timeout=30)
        if not response.ok:
            raise ValueError(f"Supabase HTTP {response.status_code}: {response.text[:500]}")
        data = response.json() if response.text else []
        return {"ok": True, "provider": "supabase", "saved": len(rows), "items": data,
                "detectedVariables": {"url": settings["urlVariable"], "key": settings["keyVariable"]},
                "table": table}
    webhook = os.getenv("LEAD_DATABASE_WEBHOOK_URL", "") or os.getenv("LEAD_INGEST_WEBHOOK_URL", "")
    if webhook:
        token = os.getenv("LEAD_DATABASE_WEBHOOK_TOKEN", "") or os.getenv("LEAD_INGEST_WEBHOOK_TOKEN", "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        status, data = post_json(webhook, {"source": "clinic-signal", "items": rows}, headers)
        return {"ok": True, "provider": "webhook", "providerStatus": status, "saved": len(rows), "response": data}
    raise ValueError("No lead database is configured. Add Supabase variables or LEAD_DATABASE_WEBHOOK_URL.")


def fetch_leads_database(limit: int = 100):
    settings = supabase_settings()
    supabase_url, supabase_key, table = settings["url"], settings["key"], settings["table"]
    if not settings["configured"]:
        raise ValueError("Supabase lead database is not configured. Expected URL: SUPABASE_URL or NEXT_PUBLIC_SUPABASE_URL; expected server key: SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY.")
    endpoint = f"{supabase_url}/rest/v1/{table}?select=*&order=created_at.desc&limit={max(1,min(limit,500))}"
    response = requests.get(endpoint, headers={"apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}"}, timeout=30)
    if not response.ok:
        raise ValueError(f"Supabase HTTP {response.status_code}: {response.text[:500]}")
    return {"ok": True, "provider": "supabase", "items": response.json(), "table": table,
            "detectedVariables": {"url": settings["urlVariable"], "key": settings["keyVariable"]}}


EXHIBITION_FIELD_ALIASES = {
    "company": {"company", "company name", "exhibitor", "name", "شرکت", "نام شرکت", "مشارکت کننده", "غرفه دار"},
    "booth": {"booth", "stand", "hall/booth", "غرفه", "شماره غرفه", "سالن و غرفه"},
    "category": {"category", "industry", "sector", "محصول", "گروه", "حوزه فعالیت", "صنعت"},
    "phone": {"phone", "telephone", "mobile", "tel", "تلفن", "شماره تماس", "موبایل"},
    "website": {"website", "site", "url", "وب سایت", "وب‌سایت", "سایت"},
    "email": {"email", "e-mail", "ایمیل", "پست الکترونیک"},
    "city": {"city", "location", "شهر", "استان", "موقعیت"},
}


def map_exhibition_header(value: str):
    normalized = re.sub(r"\s+", " ", str(value).strip().lower())
    for field, aliases in EXHIBITION_FIELD_ALIASES.items():
        if normalized in aliases:
            return field
    return normalized


def normalize_exhibitor(row: dict, event: dict):
    mapped = {}
    for key, value in row.items():
        mapped[map_exhibition_header(key)] = " ".join(str(value or "").split())
    company = mapped.get("company") or mapped.get("نام") or next((v for v in mapped.values() if v), "")
    website = mapped.get("website", "").strip()
    if website and not website.startswith(("http://", "https://")):
        website = "https://" + website
    return {"name": company[:220], "website": website[:500], "phone": mapped.get("phone", "")[:100],
            "email": mapped.get("email", "")[:180], "city": mapped.get("city", "")[:150],
            "booth": mapped.get("booth", "")[:100], "category": mapped.get("category", "")[:180],
            "eventName": str(event.get("name", ""))[:220], "eventDate": str(event.get("date", ""))[:100],
            "eventLocation": str(event.get("location", ""))[:220], "eventSource": str(event.get("source", ""))[:500],
            "source": "exhibition-import", "resultType": "exhibitor", "verified": False, "raw": mapped}


def international_exhibition_sources():
    path = ROOT / "data" / "international_window_exhibition_sources.json"
    if not path.exists():
        raise ValueError("International exhibition source registry is missing.")
    items = json.loads(path.read_text(encoding="utf-8"))
    return {"ok": True, "items": items, "count": len(items),
            "disclaimer": "Source registry only. Import and verify public exhibitor evidence; do not infer contacts or send messages without consent."}


def load_exhibition_candidate_seed(payload: dict):
    if payload.get("acknowledgeNotCurrentExhibitors") is not True:
        raise ValueError("Confirm that this historical industry dataset is NOT the official 1405 exhibitor list.")
    dataset = str(payload.get("dataset", "dowintech-industry-200"))
    if dataset != "dowintech-industry-200":
        raise ValueError("Unknown exhibition candidate dataset.")
    path = ROOT / "data" / "dowintech_industry_candidates_200.csv"
    if not path.exists():
        raise ValueError("The candidate seed file is not included in this deployment.")
    items = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            items.append({
                "name": str(row.get("name", ""))[:220],
                "category": str(row.get("category", ""))[:180],
                "phone": str(row.get("phone_public", ""))[:100],
                "phoneSourceStatus": str(row.get("phone_status", ""))[:120],
                "email": str(row.get("email_public", ""))[:180],
                "website": "",
                "websiteVerified": False,
                "websiteStatus": "not-searched",
                "websiteMatchScore": 0,
                "whatsapp": "",
                "contactConsent": False,
                "currentExhibitorStatus": "not-confirmed-1405",
                "participationConfirmed": False,
                "sourcePeriod": str(row.get("source_period", ""))[:300],
                "eventName": "هجدهمین نمایشگاه بین‌المللی در و پنجره و صنایع وابسته — هدف تحقیق",
                "eventDate": "۳۰ تیر تا ۲ مرداد ۱۴۰۵ / 21–24 July 2026",
                "eventLocation": "محل دائمی نمایشگاه‌های بین‌المللی تهران",
                "eventSource": "https://titexgroup.com/fa-IR/exhibitions-details/id/5",
                "source": str(row.get("source_url", ""))[:500],
                "resultType": "historical-industry-candidate",
                "verified": False,
                "recommendedAction": "Confirm 1405 participation, official website and consent before outreach",
            })
    for item in items:
        item["websiteSearchLinks"] = exhibition_company_search_links(item)
    return {"ok": True, "dataset": dataset, "items": items[:200], "count": min(200, len(items)),
            "currentExhibitorsConfirmed": False,
            "disclaimer": "These are 200 public historical/related industry candidates, NOT the official Do-WinTech 1405 exhibitor list. Public landlines are not WhatsApp consent. Verify current participation, website ownership and recipient consent."}


def parse_exhibition_data(payload: dict):
    raw = str(payload.get("data", ""))
    if not raw.strip():
        raise ValueError("Exhibition list data is required.")
    if len(raw.encode("utf-8")) > 2_000_000:
        raise ValueError("Exhibition import is larger than 2 MB.")
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    fmt = str(payload.get("format", "auto")).lower()
    items = []
    if fmt == "html" or (fmt == "auto" and re.search(r"<table|<tr|<td", raw, re.IGNORECASE)):
        soup = BeautifulSoup(raw, "html.parser")
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            header_cells = rows[0].find_all(["th", "td"])
            headers = [cell.get_text(" ", strip=True) or f"column_{i+1}" for i, cell in enumerate(header_cells)]
            for tr in rows[1:]:
                cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"])]
                if not cells:
                    continue
                row = {headers[i] if i < len(headers) else f"column_{i+1}": value for i, value in enumerate(cells)}
                item = normalize_exhibitor(row, event)
                if item["name"]:
                    items.append(item)
    else:
        sample = raw[:5000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            dialect, has_header = csv.excel, False
        stream = StringIO(raw)
        if has_header:
            reader = csv.DictReader(stream, dialect=dialect)
            for row in reader:
                item = normalize_exhibitor(dict(row), event)
                if item["name"]:
                    items.append(item)
        else:
            reader = csv.reader(stream, dialect=dialect)
            for cells in reader:
                cells = [" ".join(str(cell).split()) for cell in cells]
                if not any(cells):
                    continue
                row = {"company": cells[0]}
                if len(cells) > 1:
                    row["booth"] = cells[1]
                if len(cells) > 2:
                    row["category"] = cells[2]
                if len(cells) > 3:
                    row["phone"] = cells[3]
                if len(cells) > 4:
                    row["website"] = cells[4]
                item = normalize_exhibitor(row, event)
                if item["name"]:
                    items.append(item)
    deduped, seen = [], set()
    for item in items[:1000]:
        key = re.sub(r"\W+", "", item["name"].lower())
        if key and key not in seen:
            seen.add(key)
            item["websiteSearchLinks"] = exhibition_company_search_links(item)
            item["websiteStatus"] = "provided-unverified" if item.get("website") else "not-searched"
            item["websiteVerified"] = False
            item["websiteMatchScore"] = 0
            deduped.append(item)
    return {"ok": True, "items": deduped, "count": len(deduped), "event": event,
            "disclaimer": "Exhibitor data is imported as unverified public-business leads. Confirm identity and contact details before outreach."}


GENERIC_COMPANY_TOKENS = {
    "شرکت", "گروه", "صنایع", "تولیدی", "بازرگانی", "مجموعه", "بین", "المللی", "نمایشگاه",
    "company", "group", "international", "industry", "industries", "official", "website", "co", "ltd",
}
EXHIBITION_FAMILIES = {
    "medical": {"پزشکی", "سلامت", "درمان", "دارو", "بیمارستان", "کلینیک", "medical", "health", "pharma", "clinic", "hospital"},
    "technology": {"فناوری", "نرم", "افزار", "دیجیتال", "هوش", "رایانه", "technology", "software", "digital", "ai", "it"},
    "construction": {"ساختمان", "معماری", "پنجره", "درب", "آلومینیوم", "شیشه", "construction", "building", "architecture", "window", "door"},
    "beauty": {"زیبایی", "پوست", "مو", "آرایشی", "beauty", "aesthetic", "cosmetic", "skin"},
    "food": {"غذا", "کشاورزی", "بسته", "رستوران", "food", "agriculture", "restaurant", "packaging"},
    "education": {"آموزش", "دانشگاه", "مدرسه", "education", "university", "school", "training"},
}


def normalize_identity_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u0600-\u06FF]+", " ", str(value or "").lower().translate(DIGIT_TRANSLATION)).strip()


def identity_tokens(value: str) -> set[str]:
    return {token for token in normalize_identity_text(value).split() if len(token) >= 2 and token not in GENERIC_COMPANY_TOKENS}


def exhibition_families(value: str) -> set[str]:
    tokens = identity_tokens(value)
    normalized = normalize_identity_text(value)
    return {family for family, words in EXHIBITION_FAMILIES.items()
            if any(word in tokens or (len(word) > 3 and word in normalized) for word in words)}


def exhibition_company_search_links(item: dict) -> dict:
    name = str(item.get("name", "")).strip()
    category = str(item.get("category", "")).strip()
    city = str(item.get("city") or item.get("eventLocation") or "").strip()
    phone = str(item.get("phone", "")).strip()
    query = f'"{name}" {category} {city} official website وب سایت رسمی'.strip()
    links = {
        "Google": "https://www.google.com/search?q=" + quote_plus(query),
        "Google Maps": "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{name} {city}"),
        "DuckDuckGo": "https://duckduckgo.com/?q=" + quote_plus(query),
        "Bing": "https://www.bing.com/search?q=" + quote_plus(query),
        "Brave": "https://search.brave.com/search?q=" + quote_plus(query),
        "LinkedIn": "https://www.linkedin.com/search/results/companies/?keywords=" + quote_plus(name),
    }
    if phone:
        links["Google phone"] = "https://www.google.com/search?q=" + quote_plus(f'"{phone}" "{name}"')
    return links


def score_exhibition_website_candidate(item: dict, candidate: dict, html: str = "") -> tuple[int, list[str]]:
    name = str(item.get("name", ""))
    category = str(item.get("category", ""))
    city = str(item.get("city") or item.get("eventLocation") or "")
    expected_phone = re.sub(r"\D", "", normalize_public_phone(str(item.get("phone", ""))))
    url = str(candidate.get("website") or candidate.get("url") or "")
    title = str(candidate.get("name") or candidate.get("title") or "")
    summary = str(candidate.get("summary") or candidate.get("description") or "")
    haystack = normalize_identity_text(" ".join((urlparse(url).hostname or "", title, summary, html[:120000])))
    name_tokens = identity_tokens(name)
    matched_name = sorted(token for token in name_tokens if token in haystack)
    evidence = []
    score = 0
    if name_tokens:
        ratio = len(matched_name) / len(name_tokens)
        score += round(ratio * 50)
        if matched_name:
            evidence.append("Name tokens matched: " + ", ".join(matched_name[:8]))
    candidate_phone = re.sub(r"\D", "", normalize_public_phone(str(candidate.get("phone", ""))))
    visible_phones = {re.sub(r"\D", "", value) for value in extract_public_phones(html)} if html else set()
    if expected_phone and (expected_phone == candidate_phone or expected_phone in visible_phones):
        score += 35
        evidence.append("Public phone matched exactly")
    category_tokens = identity_tokens(category)
    matched_category = sorted(token for token in category_tokens if token in haystack)
    if category_tokens:
        score += round(len(matched_category) / len(category_tokens) * 10)
        if matched_category:
            evidence.append("Category evidence matched")
    city_tokens = identity_tokens(city)
    if city_tokens and any(token in haystack for token in city_tokens):
        score += 5
        evidence.append("Location signal matched")
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if host in {"example.com", "example.org", "example.net"} or host.endswith(".example"):
        score -= 80
        evidence.append("Example/test domain rejected")
    if any(host == blocked or host.endswith("." + blocked) for blocked in
           ("instagram.com", "linkedin.com", "facebook.com", "wikipedia.org", "paziresh24.com", "nobat.ir")):
        score -= 35
        evidence.append("Directory/social profile is not accepted as the official website")
    return max(0, min(100, score)), evidence


def google_places_exhibition_candidates(item: dict) -> list[dict]:
    key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip() or os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        return []
    query = " ".join(str(item.get(field, "")) for field in ("name", "category", "city", "eventLocation")).strip()
    fields = ",".join(["places.id", "places.displayName", "places.formattedAddress",
                       "places.nationalPhoneNumber", "places.internationalPhoneNumber",
                       "places.websiteUri", "places.googleMapsUri", "places.businessStatus"])
    _, response = post_json("https://places.googleapis.com/v1/places:searchText",
                            {"textQuery": query, "pageSize": 8, "languageCode": "fa"},
                            {"X-Goog-Api-Key": key, "X-Goog-FieldMask": fields}, timeout=25)
    candidates = []
    for place in (response.get("places", []) if isinstance(response, dict) else [])[:8]:
        if not isinstance(place, dict) or not place.get("websiteUri"):
            continue
        display = place.get("displayName") if isinstance(place.get("displayName"), dict) else {}
        candidates.append({
            "name": str(display.get("text", ""))[:180],
            "website": str(place.get("websiteUri", ""))[:500],
            "phone": str(place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber") or "")[:100],
            "address": str(place.get("formattedAddress", ""))[:500],
            "source": str(place.get("googleMapsUri", ""))[:500],
            "provider": "google-places",
        })
    return candidates


def brave_exhibition_candidates(item: dict) -> list[dict]:
    key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not key:
        return []
    query = f'"{item.get("name", "")}" {item.get("phone", "")} {item.get("category", "")} official website'.strip()
    params = urlencode({"q": query, "count": 10, "search_lang": "fa", "safesearch": "strict"})
    _, response = get_json("https://api.search.brave.com/res/v1/web/search?" + params,
                           {"X-Subscription-Token": key})
    results = ((response.get("web") or {}).get("results") or []) if isinstance(response, dict) else []
    return [{"name": str(result.get("title", ""))[:180],
             "website": str(result.get("url", ""))[:500],
             "summary": str(result.get("description", ""))[:600],
             "source": str(result.get("url", ""))[:500], "provider": "brave"}
            for result in results[:10] if isinstance(result, dict) and str(result.get("url", "")).startswith("http")]


def rank_exhibition_website_candidates(item: dict, candidates: list[dict], verify_top: int = 2) -> list[dict]:
    unique, seen = [], set()
    for candidate in candidates:
        url = str(candidate.get("website") or candidate.get("url") or "").strip()
        if not url:
            continue
        if not urlparse(url).scheme:
            url = "https://" + url
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if not host or host in seen:
            continue
        seen.add(host)
        candidate = {**candidate, "website": url}
        score, evidence = score_exhibition_website_candidate(item, candidate)
        candidate.update({"matchScore": score, "evidence": evidence, "verified": False})
        unique.append(candidate)
    unique.sort(key=lambda candidate: candidate["matchScore"], reverse=True)
    for candidate in unique[:max(0, min(verify_top, 3))]:
        try:
            status, final_url, html, content_type, _ = fetch(candidate["website"], timeout=12, limit=1_000_000)
            if status >= 400 or ("html" not in content_type.lower() and "<html" not in html[:1000].lower()):
                candidate["evidence"].append(f"Website returned HTTP {status}")
                continue
            candidate["website"] = final_url
            score, evidence = score_exhibition_website_candidate(item, candidate, html)
            candidate.update({"matchScore": score, "evidence": evidence, "verified": score >= 55})
            signals = extract_public_contact_signals(html, final_url)
            candidate["publicPhone"] = signals["phoneNumbers"][0] if signals["phoneNumbers"] else ""
            candidate["publicEmail"] = signals["emails"][0] if signals["emails"] else ""
        except Exception as exc:
            candidate["evidence"].append(f"Website verification failed: {type(exc).__name__}")
    unique.sort(key=lambda candidate: (candidate.get("verified", False), candidate.get("matchScore", 0)), reverse=True)
    return unique[:10]


def import_exhibition_search_html(payload: dict):
    company = payload.get("company") if isinstance(payload.get("company"), dict) else {}
    html = str(payload.get("html", ""))
    if not company.get("name"):
        raise ValueError("Target exhibition company is required.")
    if not html.strip():
        raise ValueError("Saved search-result HTML is required.")
    parsed = parse_search_html({"html": html, "engine": payload.get("engine", "generic"),
                                "sourceUrl": payload.get("sourceUrl", ""),
                                "specialty": company.get("category", "exhibitor")})
    candidates = [{"name": item.get("name", ""), "website": item.get("website", ""),
                   "phone": item.get("phone", ""), "summary": item.get("summary", ""),
                   "source": item.get("source", ""), "provider": "saved-search-html"}
                  for item in parsed.get("items", [])]
    ranked = rank_exhibition_website_candidates(company, candidates, verify_top=1)
    return {"ok": True, "company": company.get("name"), "candidates": ranked,
            "count": len(ranked), "searchLinks": exhibition_company_search_links(company),
            "disclaimer": "Saved search HTML is user-supplied evidence. Candidate websites remain unverified unless identity/phone evidence reaches the verification threshold."}


def deterministic_exhibition_validation(event: dict, item: dict, index: int) -> dict:
    event_text = " ".join(str(event.get(key, "")) for key in ("name", "category", "description", "location"))
    company_text = " ".join(str(item.get(key, "")) for key in ("name", "category", "tags", "summary"))
    event_groups = exhibition_families(event_text)
    company_groups = exhibition_families(company_text)
    category_tokens = identity_tokens(str(item.get("category", "")))
    event_tokens = identity_tokens(event_text)
    lexical_overlap = len(category_tokens & event_tokens)
    if event_groups and company_groups:
        related = bool(event_groups & company_groups)
        relation_score = 88 if related else 20
        relation_reason = ("Industry family matched: " + ", ".join(sorted(event_groups & company_groups))
                           if related else "Company industry family does not match the exhibition family")
    elif lexical_overlap:
        related = True
        relation_score = min(85, 55 + lexical_overlap * 10)
        relation_reason = "Category terms overlap with the exhibition description"
    else:
        related = None
        relation_score = 50
        relation_reason = "Insufficient category evidence; manual or AI review required"
    website_score = int(item.get("websiteMatchScore", 0) or 0)
    website_verified = bool(item.get("websiteVerified", False))
    return {"index": index, "related": related, "relationScore": relation_score,
            "relationConfidence": "high" if relation_score >= 80 or relation_score <= 25 else "low",
            "relationReason": relation_reason, "websiteOfficial": website_verified,
            "websiteMatchScore": website_score,
            "websiteReason": "Verified by name/phone/category evidence" if website_verified else
                             "Website is missing, mismatched or not sufficiently verified",
            "recommendedAction": "keep" if related is True else "exclude" if related is False else "manual-review"}


def analyze_exhibition_relevance(payload: dict):
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    if not items:
        raise ValueError("Exhibition companies are required for validation.")
    deterministic = [deterministic_exhibition_validation(event, item, index)
                     for index, item in enumerate(items[:40]) if isinstance(item, dict)]
    if not get_gemini_keys():
        return {"ok": True, "configured": False, "provider": "deterministic",
                "items": deterministic,
                "disclaimer": "Gemini is not configured. Relationship and website decisions are conservative deterministic checks and require human review."}
    evidence = []
    for index, item in enumerate(items[:40]):
        if not isinstance(item, dict):
            continue
        evidence.append({
            "index": index, "name": str(item.get("name", ""))[:180],
            "category": str(item.get("category", ""))[:180], "booth": str(item.get("booth", ""))[:100],
            "phone": str(item.get("phone", ""))[:100], "website": str(item.get("website", ""))[:500],
            "websiteMatchScore": item.get("websiteMatchScore"),
            "websiteVerified": bool(item.get("websiteVerified", False)),
            "websiteEvidence": item.get("websiteEvidence", [])[:8] if isinstance(item.get("websiteEvidence"), list) else [],
            "deterministic": deterministic[index] if index < len(deterministic) else {},
        })
    prompt = f"""You are validating exhibitors for an exhibition lead database. Return JSON only.
Event evidence:
{json.dumps(event, ensure_ascii=False, indent=2)[:5000]}
Companies and website evidence:
{json.dumps(evidence, ensure_ascii=False, indent=2)[:20000]}

Rules:
- Decide relation only from event name/category and company category/name evidence.
- Never invent products, licenses, revenue, rankings or ownership.
- A website is official only when the supplied deterministic name/phone/category evidence supports it; do not override a low match merely because the site exists.
- Mark uncertain cases for manual review.
- Preserve each index exactly.

Schema:
{{"items":[{{"index":0,"related":true,"relationScore":0,"relationConfidence":"low|medium|high","relationReason":"string","websiteOfficial":false,"websiteMatchScore":0,"websiteReason":"string","recommendedAction":"keep|exclude|manual-review|find-website"}}]}}
"""
    raw, key_number, model = call_gemini(prompt, temperature=0.15, max_tokens=7000)
    result = parse_ai_json(raw)
    ai_items = result.get("items") if isinstance(result.get("items"), list) else []
    clean = []
    for position, fallback in enumerate(deterministic):
        result_item = next((value for value in ai_items if isinstance(value, dict) and value.get("index") == fallback["index"]), {})
        relation_score = max(0, min(100, int(result_item.get("relationScore", fallback["relationScore"]) or 0)))
        website_score = max(0, min(100, int(result_item.get("websiteMatchScore", fallback["websiteMatchScore"]) or 0)))
        clean.append({**fallback, **{key: result_item.get(key, fallback.get(key)) for key in
                     ("related", "relationConfidence", "relationReason", "websiteOfficial", "websiteReason", "recommendedAction")},
                      "relationScore": relation_score, "websiteMatchScore": website_score, "index": position})
    return {"ok": True, "configured": True, "provider": "gemini", "model": model,
            "keyNumber": key_number, "items": clean,
            "disclaimer": "AI validation is advisory. Human verification of exhibition relevance and official website ownership is required."}


def enrich_exhibition_companies(payload: dict):
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    run_audit = payload.get("audit") is not False
    if not items:
        raise ValueError("Select exhibition companies for enrichment.")
    output = []
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        enriched = dict(item)
        enriched["websiteSearchLinks"] = exhibition_company_search_links(enriched)
        candidates = []
        provided = str(enriched.get("website", "")).strip()
        if provided:
            candidates.append({"name": "", "website": provided,
                               "phone": "", "provider": "provided-import"})
        if isinstance(enriched.get("websiteCandidates"), list):
            candidates.extend(value for value in enriched["websiteCandidates"] if isinstance(value, dict))
        provider_errors = []
        try:
            candidates.extend(google_places_exhibition_candidates(enriched))
        except Exception as exc:
            provider_errors.append(f"Google Places: {type(exc).__name__}")
        try:
            candidates.extend(brave_exhibition_candidates(enriched))
        except Exception as exc:
            provider_errors.append(f"Brave: {type(exc).__name__}")
        ranked = rank_exhibition_website_candidates(enriched, candidates, verify_top=2)
        enriched["websiteCandidates"] = ranked
        enriched["websiteProviderErrors"] = provider_errors
        best = ranked[0] if ranked else None
        if best and best.get("verified"):
            website = str(best.get("website", ""))
            enriched["website"] = website
            enriched["websiteVerified"] = True
            enriched["websiteMatchScore"] = int(best.get("matchScore", 0))
            enriched["websiteEvidence"] = best.get("evidence", [])
            enriched["websiteDiscoveryMode"] = best.get("provider", "candidate")
            if best.get("publicPhone") and not enriched.get("phone"):
                enriched["phone"] = best["publicPhone"]
            if best.get("publicEmail") and not enriched.get("email"):
                enriched["email"] = best["publicEmail"]
        else:
            if provided:
                enriched["rejectedWebsite"] = provided
            enriched["website"] = ""
            enriched["websiteVerified"] = False
            enriched["websiteMatchScore"] = int(best.get("matchScore", 0)) if best else 0
            enriched["websiteEvidence"] = best.get("evidence", []) if best else ["No website candidate found"]
            enriched["websiteDiscoveryMode"] = best.get("provider", "links") if best else "links"
        website = str(enriched.get("website", ""))
        if website and run_audit:
            try:
                report = audit(website)
                enriched["audit"] = report
                score = int(report.get("seoScore", 0) or 0)
                enriched["seoScore"] = score
                enriched["websiteStatus"] = "verified-working" if report.get("status") == 200 else "verified-error"
                enriched["opportunityScore"] = max(20, min(95, round((100-score) * 0.75 + 25)))
                enriched["recommendedPackage"] = "Technical SEO Recovery" if score < 50 else "SEO Growth 90 Days" if score < 80 else "Content & CRO Growth"
            except Exception as exc:
                enriched["websiteStatus"] = "verified-audit-error"
                enriched["auditError"] = str(exc)[:300]
                enriched["opportunityScore"] = 82
                enriched["recommendedPackage"] = "Website Technical Recovery"
        else:
            enriched["websiteStatus"] = "provided-website-mismatch" if provided else "no-verified-website"
            enriched["seoScore"] = 0
            enriched["opportunityScore"] = 94
            enriched["recommendedPackage"] = "Website Verification / Launch + SEO"
        output.append(enriched)
    return {"ok": True, "items": output, "count": len(output),
            "searchProviders": {"googlePlaces": bool(os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")),
                                "brave": bool(os.getenv("BRAVE_SEARCH_API_KEY"))},
            "disclaimer": "Only websites supported by company-name, category and/or exact public-phone evidence are accepted. Low-confidence or example domains are rejected and require human review."}


def make_proposal_pdf(payload: dict) -> tuple[bytes, str]:
    """Create a real A4 PDF with Pillow/RAQM; browser print remains the fallback."""
    if not PILLOW_AVAILABLE:
        raise ValueError("Direct PDF rendering is unavailable; use browser Print / Save as PDF.")
    lead = payload.get("lead") if isinstance(payload.get("lead"), dict) else {}
    def val(source, key, default="", limit=1500):
        return str(source.get(key, default))[:limit]
    name = val(lead, "name", "Clinic")
    agency_profile = payload.get("agencyProfile") if isinstance(payload.get("agencyProfile"), dict) else {}
    agency = val(agency_profile, "name", val(payload, "agency", "Clinic Signal Partner", 160), 160)
    agency_phone = val(agency_profile, "phone", "", 80)
    agency_website = val(agency_profile, "website", "", 300)
    agency_email = val(agency_profile, "email", "", 200)
    agency_address = val(agency_profile, "address", "", 500)
    agency_hours = val(agency_profile, "hours", "", 200)
    logo_data = val(agency_profile, "logoData", "", 900_000)
    issue = val(lead, "issue", "Technical and organic growth opportunity")
    tech = val(lead, "tech", "Public technical audit pending")
    plan = val(lead, "plan", "Technical remediation, local landing pages and conversion tracking")
    target = val(lead, "target", "Service + location search clusters")
    package = val(lead, "package", "Growth package", 160)
    priority = val(lead, "priority", "P2", 10)
    validity = val(payload, "validity", "14 days", 80)
    setup = val(payload, "setup", "—", 120)
    monthly = val(payload, "monthly", "—", 120)
    media = val(payload, "media", "—", 120)
    duration = val(payload, "duration", "—", 120)
    try:
        seo = max(0, min(100, int(lead.get("seo", 0))))
        opportunity = max(0, min(100, int(lead.get("opportunity", 0))))
    except Exception:
        seo = opportunity = 0

    W, H = 1240, 1754
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)
    bundled_fonts = ROOT / "assets" / "fonts"
    regular_path = str(bundled_fonts / "DejaVuSans.ttf") if (bundled_fonts / "DejaVuSans.ttf").exists() else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = str(bundled_fonts / "DejaVuSans-Bold.ttf") if (bundled_fonts / "DejaVuSans-Bold.ttf").exists() else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if hasattr(ImageFont, "Layout"):
        layout = ImageFont.Layout.RAQM if RAQM_AVAILABLE else ImageFont.Layout.BASIC
    else:
        layout = None
    def regular(size):
        return ImageFont.truetype(regular_path, size, layout_engine=layout)

    def bold(size):
        return ImageFont.truetype(bold_path, size, layout_engine=layout)

    f_small, f_body, f_bold, f_h2, f_title = regular(19), regular(23), bold(23), bold(30), bold(40)
    ink, muted, teal, pale, amber = "#183247", "#64748b", "#00a69c", "#f2f7f9", "#fff7e2"
    left, right = 82, W - 82

    def prepare_text(text):
        value = str(text)
        if RAQM_AVAILABLE or not re.search(r"[\u0600-\u06FF]", value):
            return value
        if BIDI_FALLBACK_AVAILABLE:
            try:
                return bidi_get_display(arabic_reshaper.reshape(value))
            except Exception:
                return value
        return value

    def text_rtl(x, y, text, font, fill=ink, anchor="ra"):
        kwargs = {"font": font, "fill": fill, "anchor": anchor}
        if RAQM_AVAILABLE:
            try:
                draw.text((x, y), str(text), direction="rtl", language="fa", **kwargs)
                return
            except (TypeError, ValueError, KeyError):
                pass
        draw.text((x, y), prepare_text(text), **kwargs)

    def measure(text, font):
        if RAQM_AVAILABLE:
            try:
                return draw.textlength(str(text), font=font, direction="rtl", language="fa")
            except (TypeError, ValueError, KeyError):
                pass
        return draw.textlength(prepare_text(text), font=font)

    def paragraph(text, y, font=f_body, fill=muted, max_width=None, line_height=37, max_lines=5):
        max_width = max_width or (right-left)
        words = str(text).split()
        lines, line = [], ""
        for word in words:
            candidate = (line + " " + word).strip()
            if measure(candidate, font) <= max_width:
                line = candidate
            else:
                if line:
                    lines.append(line)
                line = word
                if len(lines) >= max_lines:
                    break
        if line and len(lines) < max_lines:
            lines.append(line)
        if len(lines) == max_lines and len(words) > sum(len(x.split()) for x in lines):
            lines[-1] = lines[-1].rstrip("…") + "…"
        for line in lines:
            text_rtl(right, y, line, font, fill)
            y += line_height
        return y

    def heading(text, y):
        draw.rectangle((right-7, y-4, right, y+33), fill=teal)
        text_rtl(right-18, y, text, f_h2, ink)
        return y + 52

    # Header and sender logo
    logo_box = (right-92, 58, right, 142)
    logo_drawn = False
    if logo_data.startswith("data:image/") and ";base64," in logo_data:
        try:
            raw = base64.b64decode(logo_data.split(",", 1)[1], validate=True)
            logo_img = Image.open(BytesIO(raw)).convert("RGBA")
            logo_img.thumbnail((88, 78))
            px = right - 46 - logo_img.width//2
            py = 100 - logo_img.height//2
            image.paste(logo_img, (px, py), logo_img)
            logo_drawn = True
        except Exception:
            logo_drawn = False
    if not logo_drawn:
        draw.rounded_rectangle(logo_box, radius=16, fill="#12364d")
        text_rtl(right-46, 87, agency[:3], f_bold, "white", anchor="mm")
    text_rtl(right-112, 67, agency, f_h2, ink)
    text_rtl(right-112, 107, "پیشنهاد رشد ارگانیک و زیرساخت دیجیتال", f_small, muted)
    contact_line = " · ".join(x for x in (agency_phone, agency_website) if x)
    if contact_line:
        text_rtl(right-112, 137, contact_line, regular(15), muted)
    text_rtl(left, 78, time.strftime("%Y-%m-%d"), f_small, muted, anchor="la")
    text_rtl(left, 110, f"اعتبار: {validity}", f_small, muted, anchor="la")
    draw.rectangle((left, 158, right, 163), fill=teal)

    y = 190
    text_rtl(right, y, f"پیشنهاد اختصاصی برای {name}", f_title, ink)
    y += 68
    y = paragraph("این سند براساس بررسی عمومی حضور دیجیتال و وضعیت فنی مشاهده‌شده تهیه شده است. برآورد مقیاس به معنی درآمد واقعی یا توان پرداخت قطعی نیست.", y, f_body, muted, max_lines=3)
    y += 20

    # Score cards
    gap = 18
    box_w = (right-left-2*gap)//3
    cards = [("بلوغ SEO", f"{seo}/100"), ("فرصت", f"{opportunity}/100"), ("پکیج", package)]
    for i, (label, value) in enumerate(cards):
        x1 = right - (i+1)*box_w - i*gap
        x2 = x1 + box_w
        draw.rounded_rectangle((x1, y, x2, y+112), radius=16, fill=pale)
        text_rtl(x2-18, y+20, label, f_small, muted)
        text_rtl(x2-18, y+56, value, f_bold if i<2 else f_small, ink)
    text_rtl(left+16, y+17, priority, f_bold, "#a52d2d", anchor="la")
    y += 145

    y = heading("یافته و فرصت اصلی", y)
    y = paragraph("مشاهده فنی: " + tech, y, max_lines=3)
    y = paragraph("فرصت: " + issue, y+5, max_lines=3)
    y = paragraph("خوشه هدف: " + target, y+5, max_lines=2)
    y += 12

    y = heading("راهکار و برنامه ۹۰روزه", y)
    y = paragraph(plan, y, max_lines=3)
    phases = [
        ("روز ۱–۳۰", "Baseline، دسترسی‌ها و رفع ریسک فنی"),
        ("روز ۳۱–۶۰", "صفحات پول‌ساز، Schema و محتوای پزشکی"),
        ("روز ۶۱–۹۰", "CRO، Digital PR و گزارش لید"),
    ]
    phase_y = y + 10
    for i, (title, desc) in enumerate(phases):
        x1 = right - (i+1)*box_w - i*gap
        x2 = x1 + box_w
        draw.rounded_rectangle((x1, phase_y, x2, phase_y+105), radius=14, outline="#dce6ee", width=2)
        text_rtl(x2-14, phase_y+14, title, f_bold, ink)
        paragraph(desc, phase_y+50, f_small, muted, max_width=box_w-28, line_height=28, max_lines=2)
    y = phase_y + 130

    y = heading("سرمایه‌گذاری پیشنهادی", y)
    prices = [("راه‌اندازی", setup), ("حق‌الزحمه ماهانه", monthly), ("رسانه مستقیم", media), ("دوره", duration)]
    for label, value in prices:
        draw.line((left, y+35, right, y+35), fill="#dce6ee", width=1)
        text_rtl(right, y, label, f_body, muted)
        text_rtl(left, y, value, f_bold, ink, anchor="la")
        y += 43
    y += 12

    y = heading("KPI و شرایط حقوقی", y)
    y = paragraph("KPIها: دسترس‌پذیری، Core Web Vitals، رشد صفحات هدف، سهم Top 10، تماس و فرم واجدشرایط، نرخ تبدیل و در صورت اتصال CRM درآمد منتسب.", y, f_small, muted, line_height=31, max_lines=3)
    draw.rounded_rectangle((left, y+8, right, min(H-92, y+160)), radius=14, fill=amber, outline="#f0dfa8")
    paragraph("هیچ رتبه مطلق یا جایگاه ۱ تضمین نمی‌شود. تعهد مجری بر Deliverable، SLA، کیفیت فنی و KPIهای قابل‌اندازه‌گیری است. ادعاهای پزشکی فقط پس از تأیید پزشک مسئول منتشر می‌شود و جبران خدمت صرفاً طبق قرارداد خواهد بود.", y+24, f_small, "#725a20", max_width=right-left-34, line_height=30, max_lines=4)
    sender_footer = " · ".join(x for x in (agency, agency_phone, agency_email, agency_website) if x)
    address_footer = " · ".join(x for x in (agency_address, agency_hours) if x)
    if address_footer:
        text_rtl(right, H-112, address_footer, regular(13), muted)
    if sender_footer:
        text_rtl(right, H-86, sender_footer, regular(14), muted)
    text_rtl(right, H-58, "پیش‌نویس تجاری — نیازمند قرارداد و تأیید نهایی طرفین", regular(15), muted)

    output = BytesIO()
    image.save(output, format="PDF", resolution=150.0, title=f"Proposal for {name}", author=agency)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", val(lead, "id", "clinic", 80)).strip("-") or "clinic"
    return output.getvalue(), f"proposal-{safe_name}.pdf"


def cleanup_pdf_links():
    now = time.time()
    for token in [k for k, v in PDF_LINKS.items() if v.get("expires", 0) <= now]:
        PDF_LINKS.pop(token, None)
    if len(PDF_LINKS) >= PDF_LINK_LIMIT:
        oldest = sorted(PDF_LINKS, key=lambda key: PDF_LINKS[key].get("created", 0))
        for token in oldest[:len(PDF_LINKS) - PDF_LINK_LIMIT + 1]:
            PDF_LINKS.pop(token, None)


def store_proposal_link(payload: dict):
    cleanup_pdf_links()
    pdf, filename = make_proposal_pdf(payload)
    token = secrets.token_urlsafe(24)
    now = time.time()
    PDF_LINKS[token] = {"pdf": pdf, "filename": filename, "created": now,
                        "expires": now + PDF_LINK_TTL, "downloads": 0}
    return token, filename, int(now + PDF_LINK_TTL)


class Handler(SimpleHTTPRequestHandler):
    server_version = "ClinicSignal/1.1"

    def translate_path(self, path):
        clean = urlparse(path).path.lstrip("/") or "app.html"
        target = (ROOT / clean).resolve()
        if ROOT not in target.parents and target != ROOT:
            return str(ROOT / "index.html")
        return str(target)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self' data: https:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https:; frame-ancestors 'self'")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def public_base_url(self):
        configured = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if configured:
            parsed = urlparse(configured)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return configured
        proto = self.headers.get("X-Forwarded-Proto", "http").split(",", 1)[0].strip()
        if proto not in {"http", "https"}:
            proto = "http"
        host = self.headers.get("X-Forwarded-Host", self.headers.get("Host", "127.0.0.1:8000")).split(",", 1)[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9.:[\]_-]+", host):
            host = "127.0.0.1:8000"
        return f"{proto}://{host}"

    def do_GET(self):
        path = urlparse(self.path).path
        auth_error = integration_auth_error(self.headers, path)
        if auth_error:
            status, message = auth_error
            return self.json_response({"ok": False, "error": message}, status)
        if path == "/api/health":
            verified = self.headers.get("X-Clinic-Signal-Internal", "") == "1"
            return self.json_response({"ok": True, "service": "Clinic Signal", "mode": "live-audit-and-messaging",
                                       "integrationAuth": "verified" if verified else "not-requested"})
        if path == "/api/integrations":
            return self.json_response(provider_status())
        if path == "/api/exhibition/international-sources":
            return self.json_response(international_exhibition_sources())
        if path == "/api/send-log":
            return self.json_response({"ok": True, "items": list(SEND_LOG)})
        if path == "/api/bale/webhook-info":
            try:
                status, data = bale_api("getWebhookInfo", {}, timeout=15)
                return self.json_response({"ok": status < 400, "providerStatus": status, "response": data,
                                           **bale_bot_state_summary(), "webhookSecretConfigured": bool(BALE_WEBHOOK_SECRET)})
            except Exception as exc:
                return self.json_response({"ok": False, "error": str(exc)}, 400)
        if path == "/api/bale/inbox":
            return self.json_response({"ok": True, "items": list(BALE_INBOX), **bale_bot_state_summary()})
        if path == "/api/turkey/opportunities":
            market = parse_qs(urlparse(self.path).query).get("market", ["clinics"])[0].strip().lower() or "clinics"
            try:
                return self.json_response(turkey_opportunities(market))
            except ValueError as exc:
                return self.json_response({"ok": False, "error": str(exc)}, 400)
        if path == "/api/turkey/suppliers":
            query = parse_qs(urlparse(self.path).query)
            market = query.get("market", ["restaurants"])[0].strip().lower() or "restaurants"
            try:
                return self.json_response(turkey_suppliers_list(market))
            except ValueError as exc:
                return self.json_response({"ok": False, "error": str(exc)}, 400)
        if path == "/api/turkey/compare":
            query = parse_qs(urlparse(self.path).query)
            category = query.get("category", query.get("q", [""]))[0]
            market = query.get("market", ["restaurants"])[0].strip().lower() or "restaurants"
            region = (query.get("region", [""])[0] or "").strip() or None
            try:
                return self.json_response(turkey_compare_prices(category, market, region))
            except ValueError as exc:
                return self.json_response({"ok": False, "error": str(exc)}, 400)
        if path == "/api/leads":
            try:
                return self.json_response(fetch_leads_database(int(parse_qs(urlparse(self.path).query).get("limit", ["100"])[0])))
            except Exception as exc:
                return self.json_response({"ok": False, "error": str(exc)}, 400)
        if path == "/api/run-discovery":
            secret = os.getenv("CRON_SECRET", "")
            if secret and self.headers.get("Authorization", "") != f"Bearer {secret}":
                return self.json_response({"ok": False, "error": "Unauthorized cron request"}, 401)
            try:
                return self.json_response(run_configured_discovery())
            except Exception as exc:
                return self.json_response({"ok": False, "error": str(exc)}, 400)
        match = re.fullmatch(r"/p/([A-Za-z0-9_-]{20,80})\.pdf", path)
        if match:
            cleanup_pdf_links()
            item = PDF_LINKS.get(match.group(1))
            if not item:
                return self.json_response({"ok": False, "error": "PDF link expired or not found"}, 404)
            item["downloads"] = int(item.get("downloads", 0)) + 1
            pdf = item["pdf"]
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'inline; filename="{item["filename"]}"')
            self.send_header("Content-Length", str(len(pdf)))
            self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
            self.end_headers()
            self.wfile.write(pdf)
            return
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        auth_error = integration_auth_error(self.headers, path)
        if auth_error:
            status, message = auth_error
            return self.json_response({"ok": False, "error": message}, status)
        if path not in {"/api/audit", "/api/ai-seo-review", "/api/analyze-clinic-candidates", "/api/send", "/api/vendor-search", "/api/clinic-search", "/api/import-search-html", "/api/enrich-clinics", "/api/scrape-directory", "/api/contact-enrich", "/api/video/script", "/api/video/render", "/api/video/status", "/api/exhibition/import", "/api/exhibition/seed-candidates", "/api/exhibition/enrich", "/api/exhibition/search-html", "/api/exhibition/ai-validate", "/api/leads/bulk", "/api/export-clinics", "/api/generate-article", "/api/proposal-pdf", "/api/proposal-link", "/api/bale/webhook", "/api/bale/webhook-setup", "/api/bale/webhook-delete", "/api/turkey/bids/import", "/api/turkey/bids/sync", "/api/turkey/bids/seed-samples", "/api/turkey/suppliers/register", "/api/turkey/suppliers/rate", "/api/turkey/smart-plan"}:
            return self.json_response({"ok": False, "error": "Not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request_limit = 100_000 if path == "/api/bale/webhook" else 2_000_000 if path in {"/api/proposal-pdf", "/api/proposal-link", "/api/send", "/api/import-search-html", "/api/enrich-clinics", "/api/exhibition/import", "/api/exhibition/enrich", "/api/leads/bulk", "/api/export-clinics", "/api/analyze-clinic-candidates", "/api/turkey/bids/import", "/api/turkey/suppliers/register"} else 30_000
            if length <= 0 or length > request_limit:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if path == "/api/export-clinics":
                content, filename, content_type = export_clinic_candidates(payload)
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            if path == "/api/proposal-link":
                token, filename, expires_at = store_proposal_link(payload)
                return self.json_response({"ok": True, "url": f"{self.public_base_url()}/p/{token}.pdf",
                                           "filename": filename, "expiresAt": expires_at,
                                           "ttlSeconds": PDF_LINK_TTL,
                                           "warning": "Temporary link; it expires and may be lost if a free container restarts."})
            if path == "/api/proposal-pdf":
                pdf, filename = make_proposal_pdf(payload)
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(pdf)))
                self.end_headers()
                self.wfile.write(pdf)
                return
            if path == "/api/ai-seo-review":
                return self.json_response(generate_ai_seo_review(payload))
            if path == "/api/analyze-clinic-candidates":
                return self.json_response(analyze_clinic_candidates_ai(payload))
            if path == "/api/send":
                return self.json_response(send_message(payload))
            if path == "/api/vendor-search":
                return self.json_response(search_vendors(payload))
            if path == "/api/clinic-search":
                return self.json_response(search_clinics(payload))
            if path == "/api/import-search-html":
                return self.json_response(parse_search_html(payload))
            if path == "/api/enrich-clinics":
                return self.json_response(enrich_clinic_candidates(payload))
            if path == "/api/scrape-directory":
                return self.json_response(scrape_clinic_directory(payload))
            if path == "/api/contact-enrich":
                return self.json_response(enrich_public_business_contacts(
                    str(payload.get("url", "")).strip(), int(payload.get("maxPages", 3) or 3)))
            if path == "/api/video/script":
                return self.json_response(generate_company_video_plan(payload))
            if path == "/api/video/render":
                return self.json_response(submit_company_video_render(payload))
            if path == "/api/video/status":
                return self.json_response(company_video_render_status(payload))
            if path == "/api/exhibition/import":
                return self.json_response(parse_exhibition_data(payload))
            if path == "/api/exhibition/seed-candidates":
                return self.json_response(load_exhibition_candidate_seed(payload))
            if path == "/api/exhibition/enrich":
                return self.json_response(enrich_exhibition_companies(payload))
            if path == "/api/exhibition/search-html":
                return self.json_response(import_exhibition_search_html(payload))
            if path == "/api/exhibition/ai-validate":
                return self.json_response(analyze_exhibition_relevance(payload))
            if path == "/api/leads/bulk":
                items = payload.get("items") if isinstance(payload.get("items"), list) else []
                return self.json_response(persist_leads_database(items))
            if path == "/api/generate-article":
                return self.json_response(generate_seo_article(payload))
            if path == "/api/bale/webhook":
                if not bale_bot_enabled():
                    return self.json_response({"ok": False, "error": "Bale bot is disabled (BALE_BOT_MODE=off)."}, 503)
                if not bale_webhook_secret_ok(self.path, self.headers):
                    return self.json_response({"ok": False, "error": "Invalid Bale webhook secret."}, 401)
                return self.json_response(bale_process_update(payload))
            if path == "/api/bale/webhook-setup":
                base = str(payload.get("url", "")).strip() or self.public_base_url()
                status, data = bale_set_webhook(base)
                return self.json_response({"ok": status < 400, "providerStatus": status, "response": data,
                                           "webhookUrl": f"{base.rstrip('/')}/api/bale/webhook",
                                           "webhookSecretConfigured": bool(BALE_WEBHOOK_SECRET)})
            if path == "/api/bale/webhook-delete":
                status, data = bale_api("deleteWebhook", {"drop_pending_updates": False}, timeout=15)
                return self.json_response({"ok": status < 400, "providerStatus": status, "response": data})
            if path == "/api/turkey/bids/import":
                return self.json_response(turkey_bids_import(payload))
            if path == "/api/turkey/bids/sync":
                return self.json_response(turkey_bids_sync())
            if path == "/api/turkey/bids/seed-samples":
                return self.json_response(turkey_seed_sample_bids(int(payload.get("count", 100) or 100)))
            if path == "/api/turkey/suppliers/register":
                return self.json_response(turkey_suppliers_register(payload))
            if path == "/api/turkey/suppliers/rate":
                return self.json_response(turkey_supplier_rate(payload))
            if path == "/api/turkey/smart-plan":
                return self.json_response(turkey_smart_plan(payload))
            url = str(payload.get("url", "")).strip()
            if not url:
                raise ValueError("URL is required")
            return self.json_response(audit(url))
        except (ValueError, URLError, HTTPError, socket.timeout, TimeoutError) as exc:
            return self.json_response({"ok": False, "error": str(exc), "type": type(exc).__name__}, 400)
        except Exception as exc:
            label = ("AI SEO review" if path == "/api/ai-seo-review" else
                     "AI clinic classification" if path == "/api/analyze-clinic-candidates" else
                     "Clinic export" if path == "/api/export-clinics" else
                     "Send" if path == "/api/send" else
                     "Vendor search" if path == "/api/vendor-search" else
                     "Clinic search" if path == "/api/clinic-search" else
                     "Search HTML import" if path == "/api/import-search-html" else
                     "Clinic enrichment" if path == "/api/enrich-clinics" else
                     "Directory scraper" if path == "/api/scrape-directory" else
                     "Public contact enrichment" if path == "/api/contact-enrich" else
                     "Company video workflow" if path.startswith("/api/video/") else
                     "Exhibition import" if path == "/api/exhibition/import" else
                     "Exhibition candidate seed" if path == "/api/exhibition/seed-candidates" else
                     "Exhibition enrichment" if path == "/api/exhibition/enrich" else
                     "Exhibition search HTML" if path == "/api/exhibition/search-html" else
                     "Exhibition AI validation" if path == "/api/exhibition/ai-validate" else
                     "Lead database" if path == "/api/leads/bulk" else
                     "Article generation" if path == "/api/generate-article" else
                     "Bale bot" if path.startswith("/api/bale/") else
                     "Turkey procurement" if path.startswith("/api/turkey/") else
                     "Proposal PDF" if path in {"/api/proposal-pdf", "/api/proposal-link"} else "Audit")
            return self.json_response({"ok": False, "error": f"{label} failed: {type(exc).__name__}: {exc}"}, 500)


def main():
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Clinic Signal running at http://{host}:{port}")
    if BALE_BOT_MODE == "polling" and not os.getenv("BALE_BOT_TOKEN", "").strip():
        print("[bale-bot] BALE_BOT_MODE=polling but BALE_BOT_TOKEN is missing; polling disabled")
    start_bale_polling_if_enabled()
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
