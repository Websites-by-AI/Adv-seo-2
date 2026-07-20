#!/usr/bin/env python3
"""Local contract test for the Vercel Flask entrypoint."""
import os
from pathlib import Path

os.environ.setdefault("PDF_LINK_SECRET", "test-secret-that-is-longer-than-24-characters")
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("SEND_ENABLED", "false")

from api.index import app

client = app.test_client()

r = client.get("/api/health")
assert r.status_code == 200 and r.json["mode"] == "vercel-serverless"
print("PASS Vercel health")

r = client.get("/api/integrations")
assert r.status_code == 200 and r.json["deployment"] == "vercel"
print("PASS Vercel integrations")

r = client.post("/api/clinic-search", json={"query": "sexual health medical clinic Tehran", "location": "Tehran", "specialty": "sexual-health", "engines": ["duckduckgo", "google"]})
assert r.status_code == 200 and "duckduckgo" in r.json["searchLinks"]
print("PASS Vercel medical-clinic discovery fallback")

sample_html = '<html><body><a class="result__a" href="https://clinic.example/">Sample Clinic</a></body></html>'
r = client.post("/api/import-search-html", json={"html": sample_html, "engine": "duckduckgo", "sourceUrl": "https://duckduckgo.com/", "specialty": "medical clinic"})
assert r.status_code == 200 and r.json["count"] == 1
print("PASS Vercel saved search-HTML importer")

r = client.post("/api/leads/bulk", json={"items": r.json["items"]})
assert r.status_code == 400 and "database" in r.json["error"].lower()
print("PASS Vercel optional lead-database guard")

r = client.post("/api/analyze-clinic-candidates", json={"language": "fa", "items": [{"name": "Sample Clinic", "website": "https://clinic.example"}]})
assert r.status_code == 400 and "Gemini" in r.json["error"]
print("PASS Vercel clinic-candidate AI secret validation")

for export_format, magic in (("csv", b"\xef\xbb\xbf"), ("xlsx", b"PK"), ("pdf", b"%PDF")):
    r = client.post("/api/export-clinics", json={"format": export_format, "items": [{"name": "Sample Clinic", "website": "https://clinic.example", "specialty": "dermatology"}]})
    assert r.status_code == 200 and r.data.startswith(magic)
print("PASS Vercel CSV, Excel and PDF exports")

r = client.get("/api/run-discovery")
assert r.status_code == 200 and r.json["skipped"] is True
print("PASS Vercel discovery cron safe no-op")

r = client.post("/api/exhibition/import", json={"format": "csv", "data": "نام شرکت,غرفه,حوزه فعالیت\nشرکت نمونه,سالن ۱ غرفه ۲,تجهیزات پزشکی", "event": {"name": "نمایشگاه تست", "date": "۱۴۰۵"}})
assert r.status_code == 200 and r.json["count"] == 1 and r.json["items"][0]["booth"]
print("PASS Vercel exhibition-list import")

r = client.post("/api/exhibition/enrich", json={"audit": False, "items": r.json["items"]})
assert r.status_code == 200 and r.json["items"][0]["websiteStatus"] == "no-website-found"
print("PASS Vercel exhibition website-search fallback")

r = client.post("/api/generate-article", json={"language": "en", "title": "Test title", "outline": "First section\nSecond section", "primaryKeyword": "test keyword", "targetWordCount": 900})
assert r.status_code == 400 and "Gemini" in r.json["error"]
print("PASS Vercel Gemini endpoint secret validation")

r = client.post("/api/ai-seo-review", json={"language": "en", "audit": {"status": 200, "seoScore": 60, "title": "Clinic", "h1Count": 0, "issues": ["Missing H1"]}, "lead": {"name": "Test Clinic", "scale": "B"}})
assert r.status_code == 400 and "Gemini" in r.json["error"]
print("PASS Vercel AI SEO review evidence input and secret validation")

proposal = {
    "agency": "سئوف",
    "agencyProfile": {"name": "سئوف", "phone": "02166902605", "website": "https://seof.ir"},
    "lead": {"id": "vercel-test", "name": "کلینیک آزمایشی", "seo": 50, "opportunity": 70,
             "priority": "P1", "package": "رشد", "tech": "ممیزی فنی", "issue": "بهبود سئو",
             "plan": "برنامه ۹۰روزه", "target": "تهران"},
}
r = client.post("/api/proposal-pdf", json=proposal)
assert r.status_code == 200 and r.data.startswith(b"%PDF")
print("PASS Vercel direct PDF")

r = client.post("/api/proposal-link", json=proposal)
assert r.status_code == 200 and "/api/shared-pdf?t=" in r.json["url"]
token = r.json["url"].split("?t=", 1)[1]
r = client.get("/api/shared-pdf?t=" + token)
assert r.status_code == 200 and r.data.startswith(b"%PDF")
print("PASS Vercel stateless signed PDF link")

r = client.post("/api/send", json={"channel": "email", "recipient": "test@example.com", "message": "test",
                                    "consent": True, "approved": True, "senderAuthorized": True})
assert r.status_code == 200 and r.json["dryRun"] is True
print("PASS Vercel safe send Dry Run")

assert Path("public/index.html").exists() and Path("vercel.json").exists()
print("ALL VERCEL CONTRACT TESTS PASSED")
