# Debug Report — Websites-by-AI/Adv-seo-2

**Date:** 2026-08-02 · **Repo:** `github.com/Websites-by-AI/Adv-seo-2` (branch `master`, HEAD `2148bc8` — the commit whose message was literally "failure")

The repo contains three deployables: a Python/Flask app (**Clinic Signal**, `server.py` + `api/index.py` for Vercel + Docker/HF Spaces), a Next.js 16 app (**leadfair** — exhibition lead/SEO marketplace, `src/`, deployed to Cloudflare Workers via OpenNext), and a static no-JS Arena preview (`index.html`).

---

## 🔴 Bug 1 (the deploy-killer): `npm install` / `npm ci` fails with ERESOLVE

Every fresh install — local, CI, Vercel, Cloudflare — died at the dependency-resolution step **before any build could even start**:

```
npm error ERESOLVE unable to resolve dependency tree
peer next@">=15.5.21 <16 || >=16.2.11" from @opennextjs/cloudflare@1.20.2
Found: next@16.2.6
```

`package.json` pinned `next@16.2.6`, but `@opennextjs/cloudflare@1.20.2` excludes everything `>=16 <16.2.11`. This is almost certainly the "failure" behind the last commit.

**Fix (applied):** bumped to the latest compatible release:
- `"next": "16.2.6"` → `"next": "16.2.12"`
- `"eslint-config-next": "16.2.6"` → `"eslint-config-next": "16.2.12"`

Verified: `npm ci` now completes (717 packages), `next build`, `tsc --noEmit`, and `opennextjs-cloudflare build` all pass.

> Note: the repo had **no `package-lock.json`** committed. One has now been generated — commit it, so `npm ci` works and this can't silently recur. Also consider pinning `@opennextjs/cloudflare` exactly instead of `^1.20.1`.

## 🟠 Bug 2: stale 12 MB `.open-next` build committed to the repo; `.gitignore` missing all Node entries

- `.gitignore` was Python-only. **202 files / ~12 MB of `.open-next` worker build output were tracked in git.**
- `wrangler.jsonc` points `main` at `.open-next/worker.js` — so anyone running `wrangler deploy` without rebuilding would ship the **stale worker built against the broken dependency set**. That alone can produce a failing production deploy.
- **Fix (applied):** added `node_modules/`, `.next/`, `.open-next/`, `out/`, `.wrangler/`, `.dev.vars`, `*.log` to `.gitignore`, and removed `.open-next` from the git index (`git rm -r --cached .open-next` — staged, needs your commit).

## 🟡 Bug 3: `npm run lint` failed — 3 × `react-hooks/set-state-in-effect`

`bids-market.tsx`, `dashboard.tsx`, and `market-compare.tsx` each called their data loader directly inside the mount effect:

```ts
useEffect(() => {
  load();            // ✖ lint error: setState call chain triggered synchronously in effect body
}, [load]);
```

**Fix (applied):** run the loader behind an explicit async boundary (identical runtime behavior — the promise was un-awaited before, too):

```ts
useEffect(() => {
  void (async () => {
    await load();
  })();
}, [load]);
```

`eslint .` is now clean with zero errors.

---

## ✅ Full verification after the fixes

| Check | Result |
|---|---|
| `npm ci` (was ☠️ ERESOLVE) | ✅ 717 packages installed |
| `npm run build` (Next 16.2.12, Turbopack) | ✅ all 17 routes compile & prerender |
| `npx tsc --noEmit` | ✅ clean |
| `npm run lint` | ✅ 0 errors (was 3) |
| `node scripts/patch-pg-cloudflare.mjs && npx opennextjs-cloudflare build` | ✅ `.open-next/worker.js` generated |
| `python smoke_test.py` (30 checks) | ✅ ALL SMOKE TESTS PASSED |
| `python vercel_smoke_test.py` (22 checks) | ✅ ALL VERCEL CONTRACT TESTS PASSED |
| `build_standalone.py` → `app.html` | ✅ deterministic, matches committed bundle |

### Runtime end-to-end test (Next.js app against an in-memory Postgres)

Since the sandbox has no Postgres server, the app was exercised end-to-end with the schema (`drizzle-kit generate` → `drizzle/0000_fine_ma_gnuci.sql`) applied to an in-memory Postgres. Every flow passed:

- `GET /api/health` → `{ok:true}` · `GET /api/agencies` → directory auto-seeds (10 agencies)
- `POST /api/import {mode:"sample"}` → 14 exhibitors imported
- `POST /api/companies/[id]/pipeline` → rank check → audit → proposal, incl. the "already on Google page 1 → not a lead → no proposal" guard
- `POST /api/serp` → **live scrape worked via the DuckDuckGo fallback** (Google blocked), 8 results, exhibitor cross-matching OK
- Blind bidding: `POST /api/bids` → anonymized brief (verified **no company identity leaks** pre-award) → quote submit → duplicate-quote replacement → `award` → 15% commission computed → identity revealed **only after award**
- Pages `/`, `/bids`, `/compare`, `/bid/[token]`, `/proposal/[id]` → all HTTP 200; `/api/logs` audit trail complete

## 📝 Non-blocking observations (worth knowing, not bugs)

1. **Next warns** `The static directory has been deprecated...` — Next sees the repo's top-level `static/` (the *Python* app's assets). Harmless, but rename it or move the Next app into a subfolder to silence deploy-log noise.
2. **Provision the database** before first real deploy: `npx drizzle-kit push` (uses `drizzle.config.json`) or apply `drizzle/0000_fine_ma_gnuci.sql` (generated during this debug session; commit it if you want migrations in-repo). On Cloudflare, raw TCP `pg` won't connect — use **Hyperdrive** as `wrangler.jsonc`'s own notes say.
3. `/api/health` returns `{ok:false}` + HTTP 500 when `DATABASE_URL` is missing/unreachable — intentional (it checks DB connectivity), don't alert on it during builds.
4. Cloudflare build command for CI should stay: `node scripts/patch-pg-cloudflare.mjs && npx opennextjs-cloudflare build` (the pg-cloudflare exports patch is still required).
5. `drizzle/meta/` + the generated SQL are new untracked artifacts from this session; keep or drop depending on your migration workflow.

## What you need to do

The fixes live in this workspace's clone (`/home/user/Adv-seo-2`). To land them:

```bash
git add .gitignore package.json package-lock.json src/components/
git commit -m "Fix ERESOLVE (next 16.2.12), clean lint, drop stale .open-next from VCS"
git push
```

The `.open-next` removal is already staged (`git rm --cached`) and will be included in that commit. After pushing, re-run your Vercel/Cloudflare deploy — the install step that previously hard-failed will now pass.
