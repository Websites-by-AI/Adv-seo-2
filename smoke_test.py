#!/usr/bin/env python3
"""Dependency-free smoke tests for Clinic Signal."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
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
        assert css_status == 200 and ".proposal-page" in css and ".channel-card" in css
        assert mobile_status == 200 and "viewport" not in mobile_css and "safe-area-inset" in mobile_css and ".pdf-link-box" in mobile_css
        print("PASS full application bundle plus modular source assets")

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
