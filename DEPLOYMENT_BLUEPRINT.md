# Clinic Signal — Architecture and Free Deployment Blueprint

## 1. Purpose

Clinic Signal is a consent-controlled lead operations system for medical clinics. It combines public-business research, technical SEO auditing, deterministic lead scoring, proposal/PDF generation, solution-partner matching and approved multichannel messaging.

It is not a bulk-spam tool. Message delivery requires:

1. documented consent or an existing service conversation;
2. human approval of the recipient and text;
3. authorization to represent the selected sender company;
4. channel-specific API credentials and policy compliance.

---

## 2. Repaired frontend structure

The project has two entry experiences. `index.html` is a static, JavaScript-free Arena preview so code can never appear as page text. The maintainable full application is split into HTML, CSS and JavaScript; the build produces `app.html` for local/Docker use and `public/index.html` for Vercel.

```text
index.source.html + static/styles.css + static/mobile-fixes.css + static/app.js
                              │
                              ▼
                    build_standalone.py
                              │
                              ▼
       app.html + public/index.html (full application bundles)
```

The build embeds validated CSS and JavaScript into the full application bundles, so Vercel static hosting, local use and Docker do not depend on relative asset loading. The maintainable source files remain separate. The build verifies that there is exactly one script block and escapes any possible closing-script sequence. A visible fatal-error banner is shown if startup or an unhandled promise fails.

A **Repair local cache** action normalizes saved data. **Full reset** removes all `clinicSignal*` LocalStorage keys and reloads healthy seed data.

---

## 3. Runtime architecture

```text
                            ┌─────────────────────────┐
Candidate URLs / JSON ────► │ Browser operations UI   │
                            │ localStorage + approval  │
                            └────────────┬────────────┘
                                         │ same-origin JSON
                  ┌──────────────────────┼──────────────────────┐
                  ▼                      ▼                      ▼
             /api/audit          /api/proposal-pdf        /api/send
                  │                      │                      │
        safe public-URL check     Pillow + RAQM         policy gate
        redirect validation       RTL A4 rendering      rate limits
        metadata extraction       logo/contact block    provider adapter
                  │                      │                      │
                  └──────────────┬───────┴──────────────┬──────┘
                                 ▼                      ▼
                       deterministic score       approved external APIs
```

### API endpoints

| Endpoint | Method | Purpose |
|---|---:|---|
| `/api/health` | GET | Container and application health |
| `/api/integrations` | GET | Provider configuration state without secrets |
| `/api/audit` | POST | Safe public website audit |
| `/api/ai-seo-review` | POST | Gemini advisory SEO diagnosis, lead score, roadmap and outreach |
| `/api/proposal-pdf` | POST | Direct Persian PDF generation |
| `/api/proposal-link` | POST | Create a temporary shareable PDF URL |
| `/p/{token}.pdf` | GET | View/download a temporary proposal |
| `/api/vendor-search` | POST | Optional solution-provider search adapter/fallback links |
| `/api/clinic-search` | POST | Medical-specialty discovery and multi-engine fallback links |
| `/api/import-search-html` | POST | Parse saved search-result or directory HTML into candidates |
| `/api/enrich-clinics` | POST | Resolve selected list/profile pages into clinic entities |
| `/api/analyze-clinic-candidates` | POST | Gemini name/type/confidence classification for selected results |
| `/api/export-clinics` | POST | Generate CSV, Excel or PDF result files |
| `/api/scrape-directory` | POST | Allowlisted, robots-aware public-directory scraper |
| `/api/leads/bulk` | POST | Upsert selected leads into Supabase or database webhook |
| `/api/leads` | GET | Load persisted leads from Supabase |
| `/api/run-discovery` | GET | Scheduled discovery job and optional ingest webhook |
| `/api/exhibition/import` | POST | Parse CSV/text/HTML exhibitor lists with event metadata |
| `/api/exhibition/enrich` | POST | Find exhibitor websites, audit SEO and recommend packages |
| `/api/generate-article` | POST | Persian/English Gemini SEO article generation and report |
| `/api/send` | POST | Approved, consent-controlled delivery |
| `/api/send-log` | GET | Recent hashed delivery events |

---

## 4. Free Hugging Face Spaces deployment

### Recommended Space type

Use a **Docker Space** with the free CPU tier. Static Spaces cannot run the Python audit/PDF/API server.

### Step A — Create the Space

1. Sign in at `https://huggingface.co`.
2. Select **New Space**.
3. Name it, for example, `clinic-signal`.
4. Choose **Docker** as the SDK.
5. Choose the free CPU hardware.
6. Select Public or Private visibility according to your data policy.

### Step B — Upload with Git

Install Git and Git LFS, then:

```bash
git clone https://huggingface.co/spaces/YOUR_USERNAME/clinic-signal
cd clinic-signal
cp -R /path/to/clinic-lead-agent/. .
git add .
git commit -m "Deploy Clinic Signal"
git push
```

Hugging Face will read the YAML metadata at the top of `README.md`, build `Dockerfile`, expose port `7860`, and publish:

```text
https://YOUR_USERNAME-clinic-signal.hf.space
```

### Step C — Verify

Open:

```text
https://YOUR_USERNAME-clinic-signal.hf.space/api/health
```

Expected response:

```json
{"ok": true, "service": "Clinic Signal", "mode": "live-audit-and-messaging"}
```

Then load the root Space URL and use **Repair local cache** once if the browser previously opened an older build.

---

## 5. Hugging Face Variables and Secrets

Open the Space → **Settings** → **Variables and secrets**.

Keep sending disabled until every provider has been reviewed:

```text
SEND_ENABLED=false
DRY_RUN=true
PUBLIC_BASE_URL=https://YOUR_USERNAME-clinic-signal.hf.space
PDF_LINK_TTL_SECONDS=86400
PDF_LINK_LIMIT=100
```

`PUBLIC_BASE_URL` makes generated WhatsApp/PDF links use the public Space URL instead of an internal proxy hostname.

### Messaging secrets

| Channel | Required server secrets/variables |
|---|---|
| WhatsApp | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, optional `WHATSAPP_API_VERSION` |
| Telegram | `TELEGRAM_BOT_TOKEN` |
| Bale | `BALE_BOT_TOKEN` |
| Rubika | `RUBIKA_BOT_TOKEN` |
| Soroush Plus | `SOROUSH_PARTNER_WEBHOOK_URL`, optional `SOROUSH_PARTNER_TOKEN` |
| Eitaa | `EITAA_APP_TOKEN` |
| Email | `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASSWORD` |
| SMS | `SMS_WEBHOOK_URL`, optional `SMS_WEBHOOK_TOKEN`, `SMS_SENDER` |
| Divar Chat | `DIVAR_PARTNER_WEBHOOK_URL`, `DIVAR_PARTNER_TOKEN`, `DIVAR_APP_SLUG` |
| Vendor search | `VENDOR_SEARCH_WEBHOOK_URL`, optional `VENDOR_SEARCH_WEBHOOK_TOKEN` |
| Clinic discovery | `CLINIC_SEARCH_WEBHOOK_URL` + token, or `BRAVE_SEARCH_API_KEY` |
| Gemini Content Studio | `GEMINI_API_KEY1..3` or `GEMINI_API_KEY`; optional `GEMINI_MODEL`, `GEMINI_AUTO_CORRECT` |
| Directory scraper | `SCRAPER_ALLOWED_DOMAINS`, optional `CLINIC_DISCOVERY_URLS`, `CRON_SECRET` |
| Discovery persistence | `LEAD_INGEST_WEBHOOK_URL`, optional `LEAD_INGEST_WEBHOOK_TOKEN` |
| Supabase lead database | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, optional `SUPABASE_LEADS_TABLE` |

After testing each provider in its own sandbox, enable real delivery:

```text
SEND_ENABLED=true
DRY_RUN=false
```

Never place these values in `index.html`, `static/app.js`, Git commits or public Space variables. Use **Secrets**.

---

## 6. PDF and attachment behavior

- Direct PDF uses Pillow, DejaVu fonts and RAQM shaping for Persian text.
- Sender contact details and an authorized raster logo are included.
- WhatsApp Cloud API, Telegram, Bale and SMTP email can receive the generated document automatically.
- Rubika, Soroush Plus, Eitaa and manual web handoffs download the PDF first unless a reviewed file-upload adapter exists.
- Browser web links cannot silently attach a local file.
- **Build PDF link** creates an unguessable temporary URL and adds it to the WhatsApp message automatically.
- Temporary PDF URLs default to 24 hours, return `X-Robots-Tag: noindex`, and expire from memory.
- On a free Space, sleeping or rebuilding the container invalidates temporary links before their nominal expiry.

For durable proposal URLs, upload the generated file to private/object storage and return a signed expiring URL.

For best direct-PDF results, upload an authorized PNG, JPEG or WebP logo. SVG remains available in browser Print/PDF mode.

---

## 7. Free-tier limitations

Hugging Face free Spaces may sleep when inactive and the container filesystem is not durable.

### What survives

- Browser LocalStorage survives in that browser profile.
- Git-tracked seed data survives rebuilds.
- Provider secrets remain in Space settings.

### What does not reliably survive

- in-memory send logs;
- scheduled jobs after sleeping/restart;
- files written inside the running container;
- queues that exist only in a browser tab.

### Production persistence options

For a real deployment, add one of:

- PostgreSQL/Supabase/Neon for leads, suppression lists and audit history;
- a private Hugging Face Dataset repository for non-sensitive configuration;
- Redis/Upstash plus a worker for scheduled messages;
- object storage for approved PDF files.

Do not put medical-patient information or private credentials into a public Dataset repository.

---

## 8. Security hardening before public launch

The current server is suitable for a controlled demonstration. Before a public production launch, add:

1. user authentication and organization roles;
2. CSRF protection and a per-user API session;
3. a durable do-not-contact/suppression list;
4. encrypted database fields for sensitive business data;
5. signed audit logs;
6. provider-specific template and opt-in validation;
7. a durable background queue;
8. monitoring, alerting and backups;
9. an allowlist for sender-company profiles;
10. legal review of healthcare advertising and direct-marketing rules.

The audit endpoint already rejects private, loopback and link-local destinations, including unsafe redirects.

---

## 9. Local debugging and release checks

Run:

```bash
cd clinic-lead-agent
python build_standalone.py
python smoke_test.py
node --check static/app.js
python -m py_compile server.py smoke_test.py
```

Start the app:

```bash
python server.py
```

Open:

```text
http://127.0.0.1:8000
```

If an old browser build behaves incorrectly:

1. hard refresh (`Ctrl+Shift+R` or `Cmd+Shift+R`);
2. open **Settings → Repair local cache**;
3. if needed, choose **Full reset**;
4. inspect the visible fatal-error banner or browser console.

---

## 10. Alternative free hosting

| Platform | Suitable mode | Main limitation |
|---|---|---|
| Hugging Face Spaces | Docker, recommended | Sleeps; ephemeral filesystem |
| Render free web service | Python/Docker | Spins down; free-tier policy changes |
| Railway trial | Docker | Limited monthly credits |
| Fly.io | Container | Requires billing setup in many regions |
| GitHub Pages | Frontend only | No Python audit, PDF or messaging APIs |
| Cloudflare Pages | Frontend + Workers rewrite | Python server must be ported |

For the current codebase, Hugging Face Docker Spaces requires the fewest changes.
