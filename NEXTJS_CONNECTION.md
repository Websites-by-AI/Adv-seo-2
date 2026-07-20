# Connect Clinic Signal Python to the Adv-seo Next.js app

The applications remain separate deployments, but the Next.js server calls Python automatically through an authenticated gateway.

## 1. Deploy Python first

Use `clinic-signal-vercel-connected.zip` for Vercel, or the Docker project for Hugging Face. Copy its public HTTPS URL.

## 2. Generate one shared secret

Run locally:

```bash
openssl rand -hex 32
```

Do not commit the result and do not put it in browser JavaScript.

## 3. Python deployment Secrets

```text
PUBLIC_BASE_URL=https://YOUR-PYTHON-PROJECT.vercel.app
CLINIC_SIGNAL_API_TOKEN=THE_GENERATED_SECRET
CLINIC_SIGNAL_REQUIRE_AUTH=false
DRY_RUN=true
SEND_ENABLED=false
```

`false` keeps the separate static Clinic Signal UI operational during testing. Requests carrying `X-Clinic-Signal-Internal: 1` are still required to present and validate the shared Bearer token.

If Next.js becomes the only UI, set `CLINIC_SIGNAL_REQUIRE_AUTH=true` to require the token on all Python API routes. The standalone static Python UI will then need a separate login/gateway and should not be used directly.

## 4. Next.js deployment Secrets

```text
CLINIC_SIGNAL_API_URL=https://YOUR-PYTHON-PROJECT.vercel.app
CLINIC_SIGNAL_API_TOKEN=THE_SAME_GENERATED_SECRET
CLINIC_SIGNAL_REQUEST_TIMEOUT_MS=55000
```

## 5. Redeploy both projects

Environment changes require a new deployment. Open:

```text
https://YOUR-NEXT-PROJECT.vercel.app/clinic-signal
```

It must show `token verified`. Then run the test audit.

## Request flow

```text
Browser -> /api/clinic-signal/audit on Next.js
Next.js server -> Authorization: Bearer *** -> /api/audit on Python
Python -> measured JSON -> Next.js -> Browser
```

The shared token never reaches browser code. The Next.js gateway uses an explicit route allowlist. The company pipeline also prefers the Python audit automatically and falls back to the built-in Next.js audit if Python is temporarily unavailable.
