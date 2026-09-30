"""Vercel-compatible Flask entrypoint for Clinic Signal."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import zlib
from pathlib import Path

from flask import Flask, Response, jsonify, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import (  # noqa: E402
    PILLOW_AVAILABLE,
    SEND_LOG,
    BALE_BOT_MODE,
    BALE_INBOX,
    BALE_WEBHOOK_SECRET,
    integration_auth_error,
    audit,
    bale_api,
    bale_bot_enabled,
    bale_bot_state_summary,
    bale_process_update,
    bale_set_webhook,
    bale_webhook_secret_ok,
    turkey_bids_import,
    turkey_bids_sync,
    turkey_compare_prices,
    turkey_opportunities,
    turkey_seed_sample_bids,
    turkey_smart_plan,
    turkey_supplier_rate,
    turkey_suppliers_list,
    turkey_suppliers_register,
    generate_seo_article,
    generate_ai_seo_review,
    analyze_clinic_candidates_ai,
    export_clinic_candidates,
    make_proposal_pdf,
    provider_status,
    search_vendors,
    search_clinics,
    parse_search_html,
    enrich_clinic_candidates,
    enrich_public_business_contacts,
    generate_company_video_plan,
    submit_company_video_render,
    company_video_render_status,
    scrape_clinic_directory,
    parse_exhibition_data,
    international_exhibition_sources,
    load_exhibition_candidate_seed,
    enrich_exhibition_companies,
    import_exhibition_search_html,
    analyze_exhibition_relevance,
    run_configured_discovery,
    persist_leads_database,
    fetch_leads_database,
    send_message,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2_000_000


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required.")
    return data


def public_base():
    configured = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured.startswith(("https://", "http://")):
        return configured
    forwarded = request.headers.get("X-Forwarded-Host") or request.host
    proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",", 1)[0]
    return f"{proto}://{forwarded}"


def signing_secret():
    value = os.getenv("PDF_LINK_SECRET", "").encode("utf-8")
    if len(value) < 24:
        raise ValueError("PDF_LINK_SECRET must be configured with at least 24 characters on Vercel.")
    return value


def compact_proposal(payload: dict):
    """Create a URL-safe proposal payload; large embedded logos are intentionally omitted."""
    clean = json.loads(json.dumps(payload, ensure_ascii=False))
    profile = clean.get("agencyProfile")
    if isinstance(profile, dict):
        profile["logoData"] = ""
        # Remote logos are not fetched by the server PDF renderer; it falls back to a monogram.
    clean["expires"] = int(time.time()) + max(300, min(int(os.getenv("PDF_LINK_TTL_SECONDS", "86400")), 604800))
    raw = json.dumps(clean, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    packed = zlib.compress(raw, 9)
    if len(packed) > 6000:
        raise ValueError("Proposal is too large for a stateless link. Remove large custom fields.")
    body = base64.urlsafe_b64encode(packed).rstrip(b"=").decode("ascii")
    signature = hmac.new(signing_secret(), body.encode("ascii"), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{body}.{sig}", clean["expires"]


def unpack_proposal(token: str):
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(signing_secret(), body.encode("ascii"), hashlib.sha256).digest()
        received = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        if not hmac.compare_digest(expected, received):
            raise ValueError("Invalid PDF link signature.")
        packed = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        data = json.loads(zlib.decompress(packed).decode("utf-8"))
        if int(data.get("expires", 0)) < int(time.time()):
            raise ValueError("PDF link has expired.")
        data.pop("expires", None)
        return data
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Invalid PDF link: {type(exc).__name__}") from exc


@app.before_request
def verify_integration_request():
    auth_error = integration_auth_error(request.headers, request.path)
    if auth_error:
        status, message = auth_error
        return jsonify(ok=False, error=message), status
    return None


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health():
    verified = request.headers.get("X-Clinic-Signal-Internal", "") == "1"
    return jsonify(
        ok=True,
        service="Clinic Signal",
        mode="vercel-serverless",
        integrationAuth="verified" if verified else "not-requested",
    )


@app.get("/api/integrations")
def integrations():
    result = provider_status()
    result["deployment"] = "vercel"
    result["pdfLinksEphemeral"] = False
    result["proposalPdfMode"] = "direct-download" if PILLOW_AVAILABLE else "browser-print"
    return jsonify(result)


@app.get("/api/send-log")
def send_log():
    return jsonify(ok=True, items=list(SEND_LOG), warning="Serverless memory is not durable.")


@app.post("/api/audit")
def audit_route():
    return jsonify(audit(str(json_body().get("url", "")).strip()))


@app.post("/api/ai-seo-review")
def ai_seo_review_route():
    return jsonify(generate_ai_seo_review(json_body()))


@app.post("/api/analyze-clinic-candidates")
def analyze_clinic_candidates_route():
    return jsonify(analyze_clinic_candidates_ai(json_body()))


@app.post("/api/export-clinics")
def export_clinics_route():
    content, filename, content_type = export_clinic_candidates(json_body())
    return Response(content, mimetype=content_type.split(";", 1)[0], headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })


@app.post("/api/vendor-search")
def vendor_route():
    return jsonify(search_vendors(json_body()))


@app.post("/api/clinic-search")
def clinic_search_route():
    return jsonify(search_clinics(json_body()))


@app.post("/api/import-search-html")
def import_search_html_route():
    return jsonify(parse_search_html(json_body()))


@app.post("/api/enrich-clinics")
def enrich_clinics_route():
    return jsonify(enrich_clinic_candidates(json_body()))


@app.post("/api/scrape-directory")
def scrape_directory_route():
    return jsonify(scrape_clinic_directory(json_body()))


@app.post("/api/contact-enrich")
def contact_enrich_route():
    data = json_body()
    return jsonify(enrich_public_business_contacts(
        str(data.get("url", "")).strip(),
        int(data.get("maxPages", 3) or 3),
    ))


@app.post("/api/video/script")
def video_script_route():
    return jsonify(generate_company_video_plan(json_body()))


@app.post("/api/video/render")
def video_render_route():
    return jsonify(submit_company_video_render(json_body()))


@app.post("/api/video/status")
def video_status_route():
    return jsonify(company_video_render_status(json_body()))


@app.post("/api/exhibition/import")
def exhibition_import_route():
    return jsonify(parse_exhibition_data(json_body()))


@app.post("/api/exhibition/seed-candidates")
def exhibition_seed_candidates_route():
    return jsonify(load_exhibition_candidate_seed(json_body()))


@app.post("/api/exhibition/enrich")
def exhibition_enrich_route():
    return jsonify(enrich_exhibition_companies(json_body()))


@app.post("/api/exhibition/search-html")
def exhibition_search_html_route():
    return jsonify(import_exhibition_search_html(json_body()))


@app.post("/api/exhibition/ai-validate")
def exhibition_ai_validate_route():
    return jsonify(analyze_exhibition_relevance(json_body()))


@app.post("/api/bale/webhook")
def bale_webhook_route():
    if not bale_bot_enabled():
        return jsonify(ok=False, error="Bale bot is disabled (BALE_BOT_MODE=off)."), 503
    if not bale_webhook_secret_ok(request.full_path, request.headers):
        return jsonify(ok=False, error="Invalid Bale webhook secret."), 401
    return jsonify(bale_process_update(json_body()))


@app.post("/api/bale/webhook-setup")
def bale_webhook_setup_route():
    data = json_body()
    base = str(data.get("url", "")).strip() or public_base()
    status, response = bale_set_webhook(base)
    return jsonify(ok=status < 400, providerStatus=status, response=response,
                   webhookUrl=f"{base.rstrip('/')}/api/bale/webhook",
                   webhookSecretConfigured=bool(BALE_WEBHOOK_SECRET))


@app.post("/api/bale/webhook-delete")
def bale_webhook_delete_route():
    status, response = bale_api("deleteWebhook", {"drop_pending_updates": False}, timeout=15)
    return jsonify(ok=status < 400, providerStatus=status, response=response)


@app.get("/api/bale/webhook-info")
def bale_webhook_info_route():
    status, response = bale_api("getWebhookInfo", {}, timeout=15)
    return jsonify(ok=status < 400, providerStatus=status, response=response,
                   **bale_bot_state_summary(), webhookSecretConfigured=bool(BALE_WEBHOOK_SECRET))


@app.get("/api/bale/inbox")
def bale_inbox_route():
    return jsonify(ok=True, items=list(BALE_INBOX), **bale_bot_state_summary())


@app.get("/api/turkey/opportunities")
def turkey_opportunities_route():
    market = request.args.get("market", "clinics").strip().lower() or "clinics"
    try:
        return jsonify(turkey_opportunities(market))
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400


@app.post("/api/turkey/bids/import")
def turkey_bids_import_route():
    return jsonify(turkey_bids_import(json_body()))


@app.post("/api/turkey/bids/sync")
def turkey_bids_sync_route():
    return jsonify(turkey_bids_sync())


@app.post("/api/turkey/bids/seed-samples")
def turkey_bids_seed_samples_route():
    data = json_body() if request.data else {}
    return jsonify(turkey_seed_sample_bids(int(data.get("count", 100) or 100)))


@app.get("/api/turkey/suppliers")
def turkey_suppliers_route():
    market = request.args.get("market", "restaurants").strip().lower() or "restaurants"
    try:
        return jsonify(turkey_suppliers_list(market))
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400


@app.get("/api/turkey/compare")
def turkey_compare_route():
    category = request.args.get("category", request.args.get("q", ""))
    market = request.args.get("market", "restaurants").strip().lower() or "restaurants"
    region = (request.args.get("region", "") or "").strip() or None
    try:
        return jsonify(turkey_compare_prices(category, market, region))
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400


@app.post("/api/turkey/suppliers/register")
def turkey_suppliers_register_route():
    return jsonify(turkey_suppliers_register(json_body()))


@app.post("/api/turkey/suppliers/rate")
def turkey_supplier_rate_route():
    return jsonify(turkey_supplier_rate(json_body()))


@app.post("/api/turkey/smart-plan")
def turkey_smart_plan_route():
    return jsonify(turkey_smart_plan(json_body()))


@app.get("/api/exhibition/international-sources")
def exhibition_international_sources_route():
    return jsonify(international_exhibition_sources())


@app.get("/api/leads")
def database_leads_route():
    return jsonify(fetch_leads_database(int(request.args.get("limit", "100"))))


@app.post("/api/leads/bulk")
def database_leads_bulk_route():
    data = json_body()
    items = data.get("items") if isinstance(data.get("items"), list) else []
    return jsonify(persist_leads_database(items))


@app.get("/api/run-discovery")
def run_discovery_route():
    secret = os.getenv("CRON_SECRET", "")
    if secret and request.headers.get("Authorization", "") != f"Bearer {secret}":
        return jsonify(ok=False, error="Unauthorized cron request"), 401
    return jsonify(run_configured_discovery())


@app.post("/api/generate-article")
def generate_article_route():
    return jsonify(generate_seo_article(json_body()))


@app.post("/api/send")
def send_route():
    return jsonify(send_message(json_body()))


@app.post("/api/proposal-pdf")
def proposal_pdf():
    pdf, filename = make_proposal_pdf(json_body())
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Robots-Tag": "noindex, nofollow, noarchive",
    })


@app.post("/api/proposal-link")
def proposal_link():
    token, expires = compact_proposal(json_body())
    return jsonify(ok=True, url=f"{public_base()}/api/shared-pdf?t={token}",
                   expiresAt=expires, ttlSeconds=expires-int(time.time()),
                   warning="Stateless signed link. Embedded custom logo data is omitted; sender monogram is used.")


@app.get("/api/shared-pdf")
def shared_pdf():
    payload = unpack_proposal(request.args.get("t", ""))
    pdf, filename = make_proposal_pdf(payload)
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{filename}"',
        "X-Robots-Tag": "noindex, nofollow, noarchive",
    })


@app.errorhandler(Exception)
def handle_error(exc):
    status = 400 if isinstance(exc, ValueError) else 500
    return jsonify(ok=False, error=str(exc), type=type(exc).__name__), status
