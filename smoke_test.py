#!/usr/bin/env python3
"""Dependency-free smoke tests for Clinic Signal."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


def get(path):
    with urlopen(BASE + path, timeout=10) as r:
        return r.status, r.read().decode("utf-8")


def get_raw(path):
    with urlopen(BASE + path, timeout=15) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def post(path, payload):
    body = json.dumps(payload).encode()
    req = Request(BASE + path, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=35) as r:
            return r.status, json.loads(r.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def post_raw(path, payload):
    body = json.dumps(payload).encode()
    req = Request(BASE + path, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=35) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def wait_ready():
    for _ in range(40):
        try:
            if get("/api/health")[0] == 200:
                return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("Server did not start")


def main():
    env = dict(os.environ, PORT=str(PORT), HOST="127.0.0.1")
    temp_dir = tempfile.mkdtemp(prefix="clinic-signal-smoke-")
    env["BALE_WEBHOOK_SECRET"] = "local-smoke-bale-secret-0123456789abcdef"
    env["BALE_BOT_STATE_FILE"] = str(Path(temp_dir) / "bale_bot_state.json")
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_ready()
        status, health = get("/api/health")
        assert status == 200 and json.loads(health)["ok"] is True
        print("PASS health endpoint")

        status, html = get("/")
        assert status == 200 and "Clinic Signal" in html and "ایجنت ممیزی" in html
        assert "WhatsApp Business" in html and "DIVAR_PARTNER_WEBHOOK_URL" in html
        assert "سازنده پیشنهاد PDF" in html and "یافتن شرکت مناسب" in html
        assert '<script>' in html and '<style>' in html and 'data:text/javascript' not in html
        assert 'function printProposal' in html and 'function renderPartners' in html
        assert "https://cdn" not in html and "fonts.googleapis" not in html
        js_status, js = get("/static/app.js")
        css_status, css = get("/static/styles.css")
        mobile_status, mobile_css = get("/static/mobile-fixes.css")
        assert js_status == 200 and "function printProposal" in js and "function renderPartners" in js
        assert "function initTurkey" in js and "function turkeyCompare" in js and "function turkeyPlan" in js
        assert "بازار تأمین ترکیه" in js  # panel title for go()/pageTitle
        assert css_status == 200 and ".proposal-page" in css and ".channel-card" in css
        assert mobile_status == 200 and "viewport" not in mobile_css and "safe-area-inset" in mobile_css and ".pdf-link-box" in mobile_css
        assert 'data-panel="turkey"' in html and 'id="turkey"' in html and "بازار ترکیه" in html and "سبد خرید هوشمند" in html
        public_html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        assert 'data-panel="turkey"' in public_html and "function turkeyCompare" in public_html  # Vercel-served bundle rebuilt
        print("PASS full application bundle plus modular source assets (incl. Turkey menu)")

        preview = (ROOT / "index.html").read_text(encoding="utf-8")
        assert "بدون JavaScript و بدون نمایش کد" in preview and "<script" not in preview
        assert 'class="side"' in preview and 'class="bottom"' in preview
        print("PASS Arena-safe static homepage without JavaScript leakage")

        status, integrations = get("/api/integrations")
        integrations = json.loads(integrations)
        assert status == 200 and integrations["dryRun"] is True
        assert set(integrations["providers"]) == {"whatsapp", "telegram", "bale", "rubika", "soroush", "eitaa", "email", "sms", "divar"}
        assert integrations["webApps"]["bale"] == "https://web.bale.ai" and integrations["webApps"]["eitaa"] == "https://web.eitaa.com"
        print("PASS server-side integration status")

        status, vendor_search = post("/api/vendor-search", {"query": "SEO and web security company", "location": "Tehran", "categories": ["seo", "security"]})
        assert status == 200 and vendor_search["ok"] is True
        assert vendor_search["configured"] is False and "google" in vendor_search["searchLinks"]
        print("PASS safe vendor-search fallback")

        status, clinic_search = post("/api/clinic-search", {"query": "کلینیک پزشکی سلامت جنسی سکسولوژی تهران سایت رسمی", "location": "تهران", "specialty": "sexual-health", "engines": ["duckduckgo", "google", "bing", "brave"]})
        assert status == 200 and clinic_search["ok"] is True and clinic_search["configured"] is False and clinic_search["mode"] == "links"
        assert "BRAVE_SEARCH_API_KEY" in clinic_search["requiredConfiguration"]
        assert {"duckduckgo", "google", "bing", "brave"}.issubset(clinic_search["searchLinks"])
        print("PASS multi-engine medical-clinic search fallback")

        sample_html = '<html><body><li class="b_algo"><h2><a href="https://clinic.example/">Sample Medical Clinic clinic.example https://clinic.example/ › services</a></h2><p>Tehran 02112345678</p></li></body></html>'
        status, imported = post("/api/import-search-html", {"html": sample_html, "engine": "bing", "sourceUrl": "https://www.bing.com/search?q=clinic", "specialty": "medical clinic"})
        assert status == 200 and imported["count"] == 1 and imported["items"][0]["website"] == "https://clinic.example/"
        assert imported["items"][0]["name"] == "Sample Medical Clinic" and imported["items"][0]["resultType"] == "clinic-candidate"
        print("PASS saved search-HTML importer")

        status, blocked_scraper = post("/api/scrape-directory", {"url": "https://example.com/clinics", "specialty": "medical clinic"})
        assert status == 400 and "SCRAPER_ALLOWED_DOMAINS" in blocked_scraper["error"]
        print("PASS allowlist and robots-aware scraper guard")

        status, no_database = post("/api/leads/bulk", {"items": imported["items"]})
        assert status == 400 and "database" in no_database["error"].lower()
        print("PASS optional lead-database configuration guard")

        status, no_candidate_ai = post("/api/analyze-clinic-candidates", {"language": "fa", "items": imported["items"]})
        assert status == 400 and "Gemini" in no_candidate_ai["error"]
        print("PASS clinic-candidate AI analysis secret protection")

        for export_format, expected_type, magic in (("csv", "text/csv", b"\xef\xbb\xbf"), ("xlsx", "spreadsheetml", b"PK"), ("pdf", "application/pdf", b"%PDF")):
            export_status, export_type, export_body = post_raw("/api/export-clinics", {"format": export_format, "items": imported["items"], "title": "Clinic Results"})
            assert export_status == 200 and expected_type in export_type and export_body.startswith(magic)
        print("PASS CSV, Excel and PDF clinic-result exports")

        status, cron_result = get("/api/run-discovery")
        cron_result = json.loads(cron_result)
        assert status == 200 and cron_result["skipped"] is True
        print("PASS automatic discovery cron safe no-op")

        exhibition_csv = "نام شرکت,غرفه,حوزه فعالیت,تلفن,وب‌سایت\nشرکت سلامت آریا,سالن ۳ غرفه ۲۱,تجهیزات پزشکی,02112345678,\nفناوران درمان,سالن ۵ غرفه ۱۲,نرم‌افزار سلامت,02187654321,example.com"
        status, exhibition = post("/api/exhibition/import", {"format": "csv", "data": exhibition_csv, "event": {"name": "نمایشگاه تجهیزات پزشکی", "date": "مهر ۱۴۰۵", "location": "تهران"}})
        assert status == 200 and exhibition["count"] == 2 and exhibition["items"][0]["booth"]
        print("PASS exhibition CSV import and event metadata")

        status, seed_denied = post("/api/exhibition/seed-candidates", {"dataset": "dowintech-industry-200"})
        assert status == 400 and seed_denied["ok"] is False
        status, seed = post("/api/exhibition/seed-candidates", {"dataset": "dowintech-industry-200", "acknowledgeNotCurrentExhibitors": True})
        assert status == 200 and seed["count"] == 200 and seed["currentExhibitorsConfirmed"] is False
        assert all(item["currentExhibitorStatus"] == "not-confirmed-1405" for item in seed["items"])
        print("PASS 200 historical industry candidates with explicit not-current-exhibitor labeling")

        status, exhibition_enriched = post("/api/exhibition/enrich", {"audit": False, "items": [exhibition["items"][0]]})
        assert status == 200 and exhibition_enriched["items"][0]["websiteStatus"] == "no-verified-website"
        assert "Google" in exhibition_enriched["items"][0]["websiteSearchLinks"]
        assert exhibition_enriched["items"][0]["websiteVerified"] is False
        print("PASS exhibition multi-engine search links and conservative no-site opportunity")

        status, fake_website = post("/api/exhibition/enrich", {"audit": False, "items": [{**exhibition["items"][0], "website": "https://example.com"}]})
        assert status == 200 and fake_website["items"][0]["websiteVerified"] is False
        assert fake_website["items"][0]["website"] == "" and fake_website["items"][0]["rejectedWebsite"] == "https://example.com"
        print("PASS exhibition example/mismatched website rejection")

        saved_html = '<html><body><a class="result__a" href="https://example.com/">Unrelated Example Domain</a></body></html>'
        status, exhibition_html = post("/api/exhibition/search-html", {"company": exhibition["items"][0], "engine": "duckduckgo", "html": saved_html, "sourceUrl": "https://duckduckgo.com/"})
        assert status == 200 and exhibition_html["count"] == 1 and exhibition_html["candidates"][0]["verified"] is False
        print("PASS exhibition saved-search HTML candidate ranking")

        status, exhibition_validation = post("/api/exhibition/ai-validate", {"event": {"name": "نمایشگاه تجهیزات پزشکی"}, "items": exhibition["items"]})
        assert status == 200 and exhibition_validation["items"][0]["related"] is True
        print("PASS exhibition relevance and website-evidence validation")

        status, no_gemini = post("/api/generate-article", {"language": "fa", "title": "عنوان تست", "outline": "بخش اول\nبخش دوم", "primaryKeyword": "کلمه تست", "targetWordCount": 900})
        assert status == 400 and no_gemini["ok"] is False and "Gemini" in no_gemini["error"]
        print("PASS Gemini article endpoint validation and secret protection")

        status, no_ai_review = post("/api/ai-seo-review", {"language": "fa", "audit": {"status": 200, "seoScore": 62, "title": "Clinic", "titleLength": 6, "description": "", "h1Count": 0, "schemaTypes": [], "internalLinks": 5, "robots": True, "sitemap": False, "issues": ["Missing H1"], "wins": ["HTTP 200"]}, "lead": {"name": "کلینیک تست", "scale": "B"}})
        assert status == 400 and "Gemini" in no_ai_review["error"]
        print("PASS AI SEO review evidence input and secret protection")

        status, video_plan = post("/api/video/script", {
            "company": {"name": "شرکت نمونه", "category": "خدمات دیجیتال", "website": "https://example.com", "tags": ["سئو", "طراحی سایت"]},
            "language": "fa", "durationSeconds": 45, "objective": "معرفی عمومی شرکت",
        })
        assert status == 200 and video_plan["ok"] is True and len(video_plan["plan"]["shots"]) >= 4
        assert video_plan["plan"]["aspectRatio"] == "16:9"
        print("PASS factual company-video script/storyboard")

        status, video_denied = post("/api/video/render", {"plan": video_plan["plan"]})
        assert status == 400 and "approval" in video_denied["error"].lower()
        status, video_dry_run = post("/api/video/render", {
            "company": {"name": "شرکت نمونه"}, "plan": video_plan["plan"],
            "humanApproved": True, "brandRightsConfirmed": True,
        })
        assert status == 200 and video_dry_run["configured"] is False and video_dry_run["dryRun"] is True
        print("PASS company-video approval/rights gate and provider dry run")

        if integrations.get("proposalPdfMode") == "direct-download":
            status, content_type, pdf = post_raw("/api/proposal-pdf", {
                "agency": "Clinic Signal Partner", "agencyProfile": {"name": "سئوف", "phone": "02166902605", "website": "https://seof.ir", "email": "info@seof.ir", "address": "تهران، خیابان جمالزاده جنوبی", "hours": "شنبه تا چهارشنبه", "logoData": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2n3sAAAAASUVORK5CYII="}, "validity": "14 days", "setup": "35M", "monthly": "45M", "media": "12M", "duration": "9 months",
                "lead": {"id": "test", "name": "کلینیک آزمایشی", "seo": 55, "opportunity": 70, "priority": "P1", "package": "رشد منطقه‌ای", "tech": "خطای فنی نمونه", "issue": "نیاز به اصلاح سئو و زیرساخت", "plan": "رفع فنی و ساخت صفحات محلی", "target": "کلینیک زیبایی تهران"}
            })
            assert status == 200 and "application/pdf" in content_type and pdf.startswith(b"%PDF") and len(pdf) > 5000
            print(f"PASS direct Persian proposal PDF ({len(pdf)} bytes)")

            link_payload = {"agency": "سئوف", "agencyProfile": {"name": "سئوف", "phone": "02166902605"},
                "lead": {"id": "share-test", "name": "کلینیک لینک آزمایشی", "seo": 50, "opportunity": 70, "priority": "P1", "package": "رشد", "tech": "بررسی فنی", "issue": "بهبود سئو", "plan": "برنامه ۹۰روزه", "target": "تهران"}}
            status, share = post("/api/proposal-link", link_payload)
            assert status == 200 and share["ok"] is True and share["url"].endswith(".pdf")
            pdf_path = urlparse(share["url"]).path
            link_status, link_type, linked_pdf = get_raw(pdf_path)
            assert link_status == 200 and "application/pdf" in link_type and linked_pdf.startswith(b"%PDF")
            print("PASS temporary shareable proposal PDF link")

        status, denied = post("/api/send", {"channel": "email", "recipient": "test@example.com", "message": "Hello"})
        assert status == 400 and denied["ok"] is False
        print("PASS consent and approval enforcement")

        status, simulated = post("/api/send", {"channel": "email", "recipient": "test@example.com", "message": "Hello", "subject": "Test", "consent": True, "approved": True, "senderAuthorized": True})
        assert status == 200 and simulated["ok"] is True and simulated["dryRun"] is True and simulated["sent"] is False
        print("PASS safe dry-run delivery")

        for channel in ("bale", "rubika", "soroush", "eitaa", "divar"):
            status, simulated_local = post("/api/send", {"channel": channel, "recipient": "test-chat-id", "message": "Approved local-channel test", "consent": True, "approved": True, "senderAuthorized": True})
            assert status == 200 and simulated_local["dryRun"] is True
        print("PASS Bale, Rubika, Soroush+, Eitaa and Divar dry-run adapters")

        # ---------- Interactive Bale bot ----------
        bale_update = lambda chat, text, uid: {"update_id": uid, "message": {"chat": {"id": chat}, "from": {"first_name": "Tala"}, "text": text}}
        secret_q = "?s=local-smoke-bale-secret-0123456789abcdef"

        status, denied = post("/api/bale/webhook", bale_update(97531, "/start", 201))
        assert status == 401 and "secret" in denied["error"]
        status, started = post("/api/bale/webhook" + secret_q, bale_update(97531, "/start", 202))
        assert status == 200 and started["optedIn"] is True
        assert started["actions"][0]["type"] == "reply" and started["actions"][0]["dryRun"] is True
        status, header_secret = post("/api/bale/webhook", bale_update(97532, "/start", 203))
        assert status == 401  # only the query/header secret is accepted, never a guessable URL
        print("PASS Bale bot webhook secret and opt-in welcome")

        status, audited = post("/api/bale/webhook" + secret_q, bale_update(97531, "https://example.com", 204))
        assert status == 200 and audited["audit"]["url"].startswith("https://example.com")
        assert 5 <= audited["audit"]["score"] <= 100
        print("PASS Bale bot live website audit reply")

        status, lead = post("/api/bale/webhook" + secret_q, bale_update(97531, "شماره من ۰۹۱۲۳۴۵۶۷۸۹ تماس بگیرید", 205))
        assert status == 200 and lead["lead"]["phone"] == "09123456789" and lead["lead"]["saved"] is False
        print("PASS Bale bot Persian-digit callback capture")

        # ---------- Turkey procurement assistant ----------
        status, market = get("/api/turkey/opportunities")
        market = json.loads(market)
        assert status == 200 and market["ok"] is True
        assert len(market["regions"]) == 10 and len(market["consumables"]) >= 10
        assert market["regions"][0]["fa"] == "شیشلی" and "TİTCK" in market["disclaimer"]
        scores = [c["score"] for c in market["consumables"]]
        assert scores == sorted(scores, reverse=True)
        print("PASS Turkey market map: 10 Istanbul regions and ranked consumables")

        status, imported_bids = post("/api/turkey/bids/import", {"items": [
            {"clinic": "کلینیک دندان مدیس کرای", "region": "Şişli", "need": "خرید ۲۰۰ ایمپلنت دندانی", "quantity": 200, "budgetTry": 380000, "deadline": "2099-01-01"},
            {"clinic": "Istanbul Estetik", "region": "بشیکتاش", "need": "botoks va filler", "quantity": 50},
        ]})
        assert status == 200 and imported_bids["imported"] == 2 and imported_bids["total"] == 2
        status, dup = post("/api/turkey/bids/import", {"items": [
            {"clinic": "کلینیک دندان مدیس کرای", "region": "Şişli", "need": "خرید ۲۰۰ ایمپلنت دندانی", "quantity": 200, "budgetTry": 380000, "deadline": "2099-01-01"}]})
        assert status == 200 and dup["skippedDuplicates"] == 1
        status, market = get("/api/turkey/opportunities")
        market = json.loads(market)
        assert market["summary"]["activeBids"] == 2
        top = market["bids"][0]
        assert top["categoryId"] == "dental-implants" and top["opportunityScore"] >= 70 and top["grade"] == "A"
        assert top["regionId"] == "sisli"
        status, no_webhook = post("/api/turkey/bids/sync", {})
        assert status == 200 and no_webhook["configured"] is False
        print("PASS Turkey bid import, dedupe, scoring and safe webhook fallback")

        # ---------- Turkey restaurants market (10 districts, 10 staples, ~100 sample bids) ----------
        status, resto = get("/api/turkey/opportunities?market=restaurants")
        resto = json.loads(resto)
        assert status == 200 and resto["ok"] is True
        assert len(resto["regions"]) == 10 and len(resto["consumables"]) == 10
        region_ids = {r["id"] for r in resto["regions"]}
        assert "bagcilar" in region_ids and "esenler" in region_ids
        assert resto["summary"]["activeBids"] == 100 and resto["summary"]["sampleBids"] == 100
        assert resto["samplesNote"] and "educational" in resto["samplesNote"]
        assert all(b["contact"].startswith("+90 ") for b in resto["bids"])
        assert all(b["sample"] is True for b in resto["bids"])
        assert all(0 < b["opportunityScore"] <= 100 for b in resto["bids"])
        recos = [p["recommendationScore"] for p in resto["topPicks"]]
        assert len(set(recos)) >= 5 and recos == sorted(recos, reverse=True)  # real gradient, no full-cap plateau
        category_ids = {b["categoryId"] for b in resto["bids"]}
        assert {"frying-oil", "chicken", "beef", "rice", "packaging"}.issubset(category_ids)
        print("PASS Turkey restaurants: 10 districts (Bağcılar…), 10 staples, 100 phoned sample bids")

        status, resto_import = post("/api/turkey/bids/import", {"market": "restaurants", "items": [
            {"clinic": "رستوران تست پاس", "region": "Bağcılar", "need": "تأمین هفتگی ۵۰۰ کیلو مرغ تازه (tavuk)", "budgetTry": 120000, "deadline": "2099-01-01", "contact": "+90 530 111 2233"}]})
        assert status == 200 and resto_import["imported"] == 1 and resto_import["total"] == 101
        status, resto = get("/api/turkey/opportunities?market=restaurants")
        resto = json.loads(resto)
        assert resto["summary"]["activeBids"] == 101
        seeded = post("/api/turkey/bids/seed-samples", {})
        assert seeded[1]["imported"] == 0 and seeded[1]["skippedDuplicates"] == 100
        chicken = [b for b in resto["bids"] if b["categoryId"] == "chicken" and b["clinic"].startswith("رستوران تست")]
        assert chicken and chicken[0]["regionId"] == "bagcilar"
        status, all_markets = get("/api/turkey/opportunities?market=all")
        all_markets = json.loads(all_markets)
        assert all_markets["summary"]["activeBids"] == 103 and len(all_markets["regions"]) == 20  # 101 resto + 2 clinic
        print("PASS Turkey restaurants import, seed idempotency and market filters")

        # ---------- Turkey B2B supplier marketplace (restaurants) ----------
        status, sup = get("/api/turkey/suppliers?market=restaurants")
        sup = json.loads(sup)
        assert status == 200 and sup["ok"] is True and sup["count"] == 15
        assert all(s["sample"] is True for s in sup["suppliers"])
        assert all(s["phone"].startswith("+90 ") for s in sup["suppliers"])
        assert sup["samplesNote"] and "educational" in sup["samplesNote"]
        chicken_sellers = [s for s in sup["suppliers"] if "chicken" in s["categories"]]
        assert len(chicken_sellers) >= 3
        assert all(s["ratingAvg"] is None and s["ratingCount"] == 0 for s in sup["suppliers"])
        print("PASS supplier marketplace: 15 seeded sample suppliers with stock, min-order and zones")

        status, cmp = get("/api/turkey/compare?market=restaurants&category=" + quote("مرغ"))
        cmp = json.loads(cmp)
        assert status == 200 and cmp["ok"] is True and cmp["category"]["id"] == "chicken"
        prices = [o["priceTry"] for o in cmp["offers"]]
        assert len(prices) == 4 and prices == sorted(prices)
        assert cmp["stats"]["min"] == 128 and cmp["stats"]["max"] == 149
        assert cmp["stats"]["avg"] == 138.25 and cmp["stats"]["spreadPct"] == 16.4
        assert cmp["recommendation"]["supplier"].startswith("عمده‌فروشی Anadolu")
        assert cmp["recommendation"]["priceTry"] == 128 and cmp["samplesNote"]
        status, cmp_zone = get("/api/turkey/compare?category=" + quote("گوشت") + "&region=" + quote("باغجیلار"))
        cmp_zone = json.loads(cmp_zone)
        assert cmp_zone["regionId"] == "bagcilar"
        assert cmp_zone["stats"]["offerCount"] == 3 and cmp_zone["stats"]["inZoneCount"] == 2
        assert all("deliversHere" in o and "minOrder" in o and "stock" in o for o in cmp_zone["offers"])
        print("PASS price comparison: sorted offers, min/avg/spread stats, zone flags, recommendation")

        status, plan = post("/api/turkey/smart-plan", {"market": "restaurants", "region": "باغجیلار", "needs": [
            {"category": "مرغ", "qty": 50}, {"category": "برنج", "qty": 200}]})
        assert status == 200 and plan["ok"] is True and len(plan["lines"]) == 2
        chicken_line = next(l for l in plan["lines"] if l["categoryId"] == "chicken")
        rice_line = next(l for l in plan["lines"] if l["categoryId"] == "rice")
        assert chicken_line["picks"][0]["qty"] == 100 and "حداقل سفارش" in chicken_line["picks"][0]["note"]
        assert rice_line["picks"][0]["qty"] == 250 and rice_line["avgMarketPrice"] == 49.0
        assert plan["totals"]["grandTotal"] == 24300 and plan["totals"]["avgMarketTotal"] == 16712.5
        assert plan["totals"]["estimatedSavingsVsAvg"] == -7587.5 and plan["warnings"] == []
        assert plan["samplesNote"] and "educational" in plan["samplesNote"]
        status, plan_text = post("/api/turkey/smart-plan", {"text": "مرغ 300، روغن 40 لیتر"})
        assert plan_text["ok"] is True and len(plan_text["lines"]) == 2
        oil_line = next(l for l in plan_text["lines"] if l["categoryId"] == "frying-oil")
        assert oil_line["picks"][0]["qty"] == 200 and "حداقل سفارش" in oil_line["picks"][0]["note"]
        status, plan_dropped = post("/api/turkey/smart-plan", {"needs": [
            {"category": "عسل", "qty": 5}, {"category": "مرغ", "qty": 300}]})
        assert any("عسل" in w for w in plan_dropped["warnings"])
        chicken300 = next(l for l in plan_dropped["lines"] if l["categoryId"] == "chicken")
        assert chicken300["picks"][0]["qty"] == 300 and chicken300["picks"][0]["note"] is None
        print("PASS smart cart: cheapest picks, min-order bump, text parsing, dropped-item warning")

        status, reg = post("/api/turkey/suppliers/register", {"market": "restaurants",
            "name": "تست فود عمده", "region": "باغجیلار", "phone": "+90 500 000 0000", "products": [
                {"categoryId": "chicken", "name": "مرغ تست", "unit": "کیلوگرم", "priceTry": 160, "stock": 900, "minOrder": 20, "deliveryDays": 1},
                {"name": "برنج عمده تست (pirinç)", "priceTry": "55", "unit": "کیلوگرم", "stock": 1000, "minOrder": 10}]})
        assert status == 200 and reg["ok"] is True and reg["upserted"] == 1 and reg["total"] == 16
        supplier_id = reg["suppliers"][0]["id"]
        status, relist = get("/api/turkey/suppliers")
        relist = json.loads(relist)
        new_row = next(s for s in relist["suppliers"] if s["name"] == "تست فود عمده")
        assert new_row["sample"] is False and set(new_row["categories"]) == {"chicken", "rice"}
        status, cmp_after = get("/api/turkey/compare?category=" + quote("مرغ"))
        cmp_after = json.loads(cmp_after)
        assert cmp_after["stats"]["offerCount"] == 5  # the new supplier joined the comparison
        status, re_reg = post("/api/turkey/suppliers/register", {"name": "تست فود عمده", "region": "باغجیلار", "products": [
            {"categoryId": "chicken", "name": "مرغ تست v2", "priceTry": 161, "minOrder": 25}]})
        assert re_reg["total"] == 16 and re_reg["upserted"] == 1  # upsert, not duplicate
        status, plan_after = post("/api/turkey/smart-plan", {"needs": [{"category": "مرغ", "qty": 300}]})
        total300 = sum(p["lineTotal"] for l in plan_after["lines"] for p in l["picks"])
        assert abs(total300 - 38400) < 0.01  # still cheapest: 300 × 128 despite the new entrant
        print("PASS supplier register, keyword category match and idempotent upsert")

        status, rate1 = post("/api/turkey/suppliers/rate", {"supplierId": supplier_id, "price": 5, "quality": 4})
        assert status == 200 and rate1["rating"]["avg"] == 4.5 and rate1["rating"]["count"] == 1
        status, rate2 = post("/api/turkey/suppliers/rate", {"supplierId": supplier_id, "delivery": 3, "satisfaction": 3})
        assert rate2["rating"]["count"] == 2 and rate2["rating"]["avg"] == 3.75
        assert rate2["rating"]["aspects"] == {"price": 5.0, "quality": 4.0, "delivery": 3.0, "satisfaction": 3.0}
        status, bad_rate = post("/api/turkey/suppliers/rate", {"supplierId": supplier_id, "price": 9})
        assert status == 400 and "between 1 and 5" in bad_rate["error"]
        status, missing = post("/api/turkey/suppliers/rate", {"supplierId": "does-not-exist", "price": 5})
        assert status == 400 and "not found" in missing["error"]
        status, rated_list = get("/api/turkey/suppliers")
        rated_list = json.loads(rated_list)
        rated_row = next(s for s in rated_list["suppliers"] if s["id"] == supplier_id)
        assert rated_row["ratingAvg"] == 3.75 and rated_row["ratingCount"] == 2
        print("PASS supplier rating: aspect averages, validation and directory aggregate")

        # ---------- Bale bot: supplier marketplace commands ----------
        status, s_dir = post("/api/bale/webhook" + secret_q, bale_update(97540, "تأمین‌کنندگان", 240))
        assert status == 200 and s_dir["actions"][0]["type"] == "reply"
        assert "مواد غذایی رستوران" in s_dir["actions"][0]["preview"]
        status, s_dir2 = post("/api/bale/webhook" + secret_q, bale_update(97544, "تأمین‌کنندگان رستوران", 241))
        assert status == 200 and s_dir2["actions"][0]["type"] == "reply"
        assert "مواد غذایی رستوران" in s_dir2["actions"][0]["preview"]
        status, inbox = get("/api/bale/inbox")
        inbox = json.loads(inbox)
        assert inbox["items"][0]["kind"] == "turkey-suppliers"
        status, s_price = post("/api/bale/webhook" + secret_q, bale_update(97541, "قیمت مرغ", 242))
        assert status == 200 and s_price["actions"][0]["type"] == "reply"
        assert "مقایسه قیمت" in s_price["actions"][0]["preview"] and "مرغ" in s_price["actions"][0]["preview"]
        status, s_price_bad = post("/api/bale/webhook" + secret_q, bale_update(97543, "قیمت بنزین", 243))
        assert status == 200 and s_price_bad["actions"][0]["type"] == "reply"  # friendly hint, no crash
        assert "پیدا نشد" in s_price_bad["actions"][0]["preview"]
        status, inbox = get("/api/bale/inbox")
        inbox = json.loads(inbox)
        assert inbox["items"][0]["kind"] == "turkey-compare"
        status, s_cart = post("/api/bale/webhook" + secret_q, bale_update(97542, "سبد خرید: مرغ 200، روغن 40", 245))
        assert status == 200 and s_cart["actions"][0]["type"] == "reply"
        assert "برنامه خرید هوشمند" in s_cart["actions"][0]["preview"]
        status, s_cart_empty = post("/api/bale/webhook" + secret_q, bale_update(97545, "سبد خرید", 246))
        assert status == 200 and s_cart_empty["actions"][0]["type"] == "reply"  # usage hint
        assert "لیست خرید" in s_cart_empty["actions"][0]["preview"]
        status, inbox = get("/api/bale/inbox")
        inbox = json.loads(inbox)
        assert inbox["items"][0]["kind"] == "turkey-cart"
        print("PASS Bale bot supplier commands: directory, price compare, smart cart, friendly fallbacks")

        status, r_overview = post("/api/bale/webhook" + secret_q, bale_update(97535, "رستوران ترکیه", 230))
        assert status == 200 and r_overview["actions"][0]["type"] == "reply"
        status, r_bids = post("/api/bale/webhook" + secret_q, bale_update(97535, "بید رستوران", 231))
        assert status == 200 and r_bids["actions"][0]["type"] == "reply"
        status, r_supply = post("/api/bale/webhook" + secret_q, bale_update(97535, "تأمین رستوران", 232))
        assert status == 200 and r_supply["actions"][0]["type"] == "reply"
        status, combined = post("/api/bale/webhook" + secret_q, bale_update(97536, "ترکیه", 233))
        assert status == 200 and combined["actions"][0]["type"] == "reply"
        print("PASS Bale bot restaurant overview, bids, supply and combined Turkey map")

        status, turkey_intro = post("/api/bale/webhook" + secret_q, bale_update(97533, "ترکیه", 206))
        assert status == 200 and turkey_intro["actions"][0]["type"] == "reply"
        status, turkey_bids = post("/api/bale/webhook" + secret_q, bale_update(97533, "فراخوانها", 207))
        assert status == 200 and turkey_bids["actions"][0]["type"] == "reply"
        status, turkey_supply = post("/api/bale/webhook" + secret_q, bale_update(97533, "تأمین", 208))
        assert status == 200 and turkey_supply["actions"][0]["type"] == "reply"
        print("PASS Bale bot Turkey overview, bids and supply recommendation replies")

        # the per-chat anti-flood limiter (5 replies/minute) must engage deterministically
        flood = [post("/api/bale/webhook" + secret_q, bale_update(97534, "/help", 220 + i)) for i in range(6)]
        assert [r[1]["actions"][0]["type"] for r in flood[:5]] == ["reply"] * 5
        assert flood[5][1]["ok"] is False and flood[5][1]["actions"][0]["type"] == "rate-limited"
        print("PASS Bale bot per-chat anti-flood rate limit")

        status, stopped = post("/api/bale/webhook" + secret_q, bale_update(97531, "توقف", 209))
        assert status == 200 and stopped["optedOut"] is True
        assert stopped["actions"][0]["status"] == "simulated"  # confirmation is delivered BEFORE blocking
        status, silenced = post("/api/bale/webhook" + secret_q, bale_update(97531, "سلام", 210))
        assert status == 200 and silenced["actions"][0]["type"] == "silenced"
        status, send_block = post("/api/send", {"channel": "bale", "recipient": "97531", "message": "x",
                                                "consent": True, "approved": True, "senderAuthorized": True})
        assert status == 400 and "do-not-contact" in send_block["error"]
        status, rejoined = post("/api/bale/webhook" + secret_q, bale_update(97531, "/start", 211))
        assert status == 200 and rejoined["optedIn"] is True and rejoined["returning"] is True
        status, inbox = get("/api/bale/inbox")
        inbox = json.loads(inbox)
        assert inbox["optedIn"] == 1 and any(i["kind"] == "stop" for i in inbox["items"])
        print("PASS Bale bot STOP silence, do-not-contact enforcement, rejoin and operator inbox")

        if integrations.get("proposalPdfMode") == "direct-download":
            status, simulated_pdf = post("/api/send", {"channel": "whatsapp", "recipient": "989121234567", "message": "Approved test", "consent": True, "approved": True, "senderAuthorized": True, "attachProposalPdf": True,
                "proposal": {"agency": "سئوف", "agencyProfile": {"name": "سئوف", "phone": "02166902605"}, "lead": {"id": "test-send", "name": "کلینیک آزمایشی", "seo": 50, "opportunity": 70, "priority": "P1", "package": "رشد", "tech": "خطای نمونه", "issue": "رفع فنی", "plan": "برنامه ۹۰روزه", "target": "تهران"}}})
            assert status == 200 and simulated_pdf["attachmentReady"] is True and simulated_pdf["dryRun"] is True
            print("PASS dry-run WhatsApp PDF attachment generation")

        status, blocked = post("/api/audit", {"url": "http://127.0.0.1:1/private"})
        assert status == 400 and blocked["ok"] is False
        print("PASS private-address protection")

        status, live = post("/api/audit", {"url": "https://example.com/"})
        assert status == 200 and live["ok"] is True
        assert live["status"] == 200 and 0 <= live["seoScore"] <= 100
        assert "issues" in live and "checkedAt" in live
        assert "internalLinkSamples" in live and "externalLinkSamples" in live and "socialLinks" in live
        assert "phoneLinks" in live and "emailLinks" in live
        print(f"PASS live public audit with scraped link/contact samples (score={live['seoScore']})")

        print("ALL SMOKE TESTS PASSED")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
        if proc.stdout:
            output = proc.stdout.read().strip()
            if output:
                print("\nServer log:\n" + output)


if __name__ == "__main__":
    main()
