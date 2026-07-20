# Exhibition Leads Workflow

## Supported imports

- CSV/TSV with Persian or English headers
- HTML tables copied from exhibitor directories
- Plain text, one company per line
- Pipe/comma/tab-delimited lists

Recognized columns include company/exhibitor name, booth/stand, category/industry, phone, website, email and city.

## Workflow

1. Enter exhibition name, dates, venue and source URL.
2. Upload or paste the exhibitor list.
3. Parse and deduplicate company names.
4. Select companies.
5. Click **Find website + SEO audit**.
6. Existing websites are audited; companies without a website receive Google/DuckDuckGo/Bing search links.
7. Add selected companies to leads, the audit queue, Supabase, or export them as JSON/CSV/Excel/PDF.

## Automatic website finding

Set:

```text
BRAVE_SEARCH_API_KEY=SECRET
```

The enrichment endpoint searches for a likely official website and excludes common social networks and medical directories. A match is still unverified and must be confirmed before outreach.

## Endpoints

```text
POST /api/exhibition/import
POST /api/exhibition/enrich
```

The enrichment endpoint processes up to eight companies per request to remain compatible with serverless time limits.

## Opportunity logic

- No website found: Website Launch + Local SEO, opportunity around 94
- Website error/audit failure: Technical Recovery, high opportunity
- SEO score below 50: Technical SEO Recovery
- SEO score 50–79: SEO Growth 90 Days
- SEO score 80+: Content & CRO Growth

These are sales research estimates, not factual valuations.
