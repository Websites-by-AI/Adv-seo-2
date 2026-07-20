#!/usr/bin/env python3
"""Local contract test for the Vercel Flask entrypoint."""
import os
from pathlib import Path

os.environ.setdefault("PDF_LINK_SECRET", "test-secret-that-is-longer-than-24-characters")
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("SEND_ENABLED", "false")
os.environ.setdefault("CLINIC_SIGNAL_API_TOKEN", "contract-test-token-that-is-long-enough")

from api.index import app

client = app.test_client()

r = client.get("/api/health")
assert r.status_code == 200 and r.json["mode"] == "vercel-serverless"
print("PASS Vercel health")

r = client.get("/api/health", headers={"X-Clinic-Signal-Internal": "1", "Authorization": "Bearer wrong-token-value-that-is-long"})
assert r.status_code == 401
r = client.get("/api/health", headers={"X-Clinic-Signal-Internal": "1", "Authorization": "Bearer contract-test-token-that-is-long-enough"})
assert r.status_code == 200 and r.json["integrationAuth"] == "verified"
print("PASS Vercel service-to-service token validation")

r = client.post("/api/contact-enrich", json={"url": "http://127.0.0.1/private", "maxPages": 2})
assert r.status_code == 400 and "blocked" in r.json["error"].lower()
print("PASS Vercel contact-enrichment private-address block")

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

r = client.post("/api/exhibition/seed-candidates", json={"dataset": "dowintech-industry-200"})
assert r.status_code == 400
r = client.post("/api/exhibition/seed-candidates", json={"dataset": "dowintech-industry-200", "acknowledgeNotCurrentExhibitors": True})
assert r.status_code == 200 and r.json["count"] == 200 and r.json["currentExhibitorsConfirmed"] is False
print("PASS Vercel 200 historical industry candidates with explicit status")

# Continue contract checks with the parsed exhibition rows, not the historical seed.
r = client.post("/api/exhibition/import", json={"format": "csv", "data": "نام شرکت,غرفه,حوزه فعالیت\nشرکت نمونه,سالن ۱ غرفه ۲,تجهیزات پزشکی", "event": {"name": "نمایشگاه تست", "date": "۱۴۰۵"}})
exhibition_items = r.json["items"]
r = client.post("/api/exhibition/enrich", json={"audit": False, "items": exhibition_items})
assert r.status_code == 200 and r.json["items"][0]["websiteStatus"] == "no-verified-website"
assert r.json["items"][0]["websiteVerified"] is False and "Google" in r.json["items"][0]["websiteSearchLinks"]
print("PASS Vercel exhibition multi-engine search and conservative website verification")

r = client.post("/api/exhibition/enrich", json={"audit": False, "items": [{**exhibition_items[0], "website": "https://example.com"}]})
assert r.status_code == 200 and r.json["items"][0]["website"] == "" and r.json["items"][0]["rejectedWebsite"]
print("PASS Vercel exhibition mismatched website rejection")

r = client.post("/api/exhibition/search-html", json={"company": exhibition_items[0], "engine": "duckduckgo", "html": '<a class="result__a" href="https://example.com">Unrelated Example</a>', "sourceUrl": "https://duckduckgo.com/"})
assert r.status_code == 200 and r.json["count"] == 1 and r.json["candidates"][0]["verified"] is False
print("PASS Vercel exhibition saved-search HTML ranking")

r = client.post("/api/exhibition/ai-validate", json={"event": {"name": "نمایشگاه تجهیزات پزشکی"}, "items": exhibition_items})
assert r.status_code == 200 and r.json["items"][0]["related"] is True
print("PASS Vercel exhibition relevance validation")

r = client.post("/api/generate-article", json={"language": "en", "title": "Test title", "outline": "First section\nSecond section", "primaryKeyword": "test keyword", "targetWordCount": 900})
assert r.status_code == 400 and "Gemini" in r.json["error"]
print("PASS Vercel Gemini endpoint secret validation")

r = client.post("/api/ai-seo-review", json={"language": "en", "audit": {"status": 200, "seoScore": 60, "title": "Clinic", "h1Count": 0, "issues": ["Missing H1"]}, "lead": {"name": "Test Clinic", "scale": "B"}})
assert r.status_code == 400 and "Gemini" in r.json["error"]
print("PASS Vercel AI SEO review evidence input and secret validation")

r = client.post("/api/video/script", json={
    "company": {"name": "Test Company", "category": "Digital services", "website": "https://example.com"},
    "language": "en", "durationSeconds": 45, "objective": "factual company introduction",
})
assert r.status_code == 200 and r.json["ok"] is True and len(r.json["plan"]["shots"]) >= 4
video_plan = r.json["plan"]
r = client.post("/api/video/render", json={"plan": video_plan})
assert r.status_code == 400 and "approval" in r.json["error"].lower()
r = client.post("/api/video/render", json={
    "company": {"name": "Test Company"}, "plan": video_plan,
    "humanApproved": True, "brandRightsConfirmed": True,
})
assert r.status_code == 200 and r.json["configured"] is False and r.json["dryRun"] is True
print("PASS Vercel company-video plan, approval gate and adapter dry run")

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
