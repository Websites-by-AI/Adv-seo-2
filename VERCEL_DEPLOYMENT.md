# Clinic Signal — Vercel Deployment and UI Standard

## Is the project Vercel-ready?

Yes, this version includes a Vercel-specific static frontend and Flask serverless API:

```text
public/index.html       self-contained responsive frontend
api/index.py            Flask/Vercel Function entrypoint
vercel.json             routing, headers and function limits
requirements.txt        Flask + Pillow
assets/fonts/           bundled Persian-compatible DejaVu fonts
```

The original `server.py` remains the local/Hugging Face server. Vercel loads `api/index.py` instead.

---

## Deploy from GitHub

1. Push the project directory to a GitHub repository.
2. In Vercel choose **Add New → Project**.
3. Import the repository.
4. Leave Framework Preset as **Other**.
5. Leave Build Command and Output Directory empty; Vercel serves `public/` and detects `api/index.py`.
6. Add environment variables before enabling production sends.
7. Deploy.

## Deploy with Vercel CLI

```bash
npm install -g vercel
cd clinic-lead-agent
python build_standalone.py
vercel
vercel --prod
```

## Required Vercel environment variables

Start safely:

```text
SEND_ENABLED=false
DRY_RUN=true
PDF_LINK_SECRET=generate-a-long-random-secret-at-least-32-characters
PUBLIC_BASE_URL=https://YOUR-PROJECT.vercel.app
PDF_LINK_TTL_SECONDS=86400
CLINIC_SEARCH_WEBHOOK_URL=https://YOUR-SEARCH-ADAPTER.example/clinics
CLINIC_SEARCH_WEBHOOK_TOKEN=SECRET
# Alternative direct provider:
BRAVE_SEARCH_API_KEY=SECRET
GEMINI_API_KEY1=SECRET
GEMINI_API_KEY2=OPTIONAL_SECOND_KEY
GEMINI_API_KEY3=OPTIONAL_THIRD_KEY
GEMINI_MODEL=gemini-flash-lite-latest
GEMINI_AUTO_CORRECT=true
SCRAPER_ALLOWED_DOMAINS=approved-directory.example
CLINIC_DISCOVERY_URLS=https://approved-directory.example/clinics
CRON_SECRET=LONG_RANDOM_SECRET
LEAD_INGEST_WEBHOOK_URL=https://your-storage-adapter.example/leads
LEAD_INGEST_WEBHOOK_TOKEN=SECRET
# The server auto-detects either URL name:
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
# or NEXT_PUBLIC_SUPABASE_URL from the Vercel integration

# The server auto-detects either server-only key name:
SUPABASE_SERVICE_ROLE_KEY=SECRET
# or SUPABASE_SECRET_KEY from the Vercel integration

# Optional; defaults automatically:
SUPABASE_LEADS_TABLE=clinic_leads
```

Run `SUPABASE_SETUP.sql` once in the Supabase SQL Editor before enabling database buttons.

Generate a secret locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Add messaging-provider credentials as Vercel **Environment Variables**. Never commit tokens.

After provider-specific sandbox tests:

```text
SEND_ENABLED=true
DRY_RUN=false
```

---

## PDF links on Vercel

Vercel Functions are stateless, so the Vercel adapter does not rely on in-memory PDF storage.

`POST /api/proposal-link` creates a compressed, signed, expiring token. The recipient URL looks like:

```text
https://YOUR-PROJECT.vercel.app/api/shared-pdf?t=SIGNED_TOKEN
```

The PDF is regenerated when opened. This works across cold starts and separate serverless instances as long as `PDF_LINK_SECRET` stays unchanged.

For URL-size safety, embedded custom logo image data is removed from stateless links; the PDF uses the sender monogram. Direct PDF downloads and API attachments can still include the uploaded raster logo. Use object storage if permanent branded links are required.

---

## UI/UX standard applied

### Responsive breakpoints

- Desktop: persistent sidebar and wide dashboard cards
- Tablet: compact icon sidebar and stacked work areas
- Phone ≤720px: bottom navigation, safe-area spacing and touch-first controls
- Small phone ≤380px: one-column cards
- Landscape phone: scrollable sidebar and compact hero

### Accessibility and usability

- Maximum zoom remains available (`maximum-scale=5`)
- `viewport-fit=cover` supports notches and safe areas
- Touch targets are at least 44px on phones
- Form inputs use 16px font size to prevent iOS auto-zoom
- Focus and error states are visible
- Runtime failures show an on-screen Persian error banner
- Repair-cache and full-reset actions recover incompatible LocalStorage
- Channel cards become horizontal snap-scrolling controls on phones
- Primary mobile tasks are available from a five-item bottom navigation

### Frontend build strategy

Maintainable source remains modular:

```text
index.source.html
static/app.js
static/styles.css
static/mobile-fixes.css
```

Run:

```bash
python build_standalone.py
```

This creates both full application bundles:

```text
app.html
public/index.html
```

`public/index.html` is deployed by Vercel. Root `index.html` is intentionally a JavaScript-free Arena preview. The full bundles embed validated CSS and JavaScript so Vercel and local/Docker execution do not depend on relative asset loading.

---

## Vercel limitations

- Python APIs run as serverless functions, not a persistent `python server.py` process.
- In-memory send logs and queues are not durable.
- Background scheduling requires an external queue/cron worker.
- Some Iranian domains may respond slowly from Vercel regions; audit timeouts should be treated as inconclusive.
- The free plan’s limits and maximum duration can change.
- For permanent history use PostgreSQL/Supabase/Neon.
- For permanent PDFs use Vercel Blob, Cloudflare R2, S3 or Supabase Storage.

---

## Verification

Run before deployment:

```bash
python build_standalone.py
python smoke_test.py
python vercel_smoke_test.py
node --check static/app.js
python -m py_compile server.py api/index.py
```

Expected final lines:

```text
ALL SMOKE TESTS PASSED
ALL VERCEL CONTRACT TESTS PASSED
```

After deployment verify:

```text
https://YOUR-PROJECT.vercel.app/
https://YOUR-PROJECT.vercel.app/api/health
```

The health endpoint should return `mode: vercel-serverless`.
