# Exhibition Leads Workflow

## Supported imports

- CSV/TSV with Persian or English headers
- HTML tables copied from exhibitor directories
- Plain text, one company per line
- Pipe/comma/tab-delimited lists
- User-supplied saved Google/Bing/DuckDuckGo/Brave result HTML for a selected company

Recognized columns include company/exhibitor name, booth/stand, category/industry, phone, website, email and city.

## Workflow

1. Enter the real exhibition name, dates, venue and source URL.
2. Upload or paste the real exhibitor list. The UI supplies only an empty CSV template; it no longer inserts fake companies, phones or `example.com`.
3. Parse and deduplicate company names.
4. Open the per-company Google/Maps/DDG/Bing/Brave/LinkedIn/exact-phone links, or configure Google Places/Brave APIs.
5. Optionally save a search-result page and import its HTML for the target company.
6. Select companies and run **Find official website + identity match + SEO audit**.
7. Run **AI exhibition relation check** for the selected batch. Without Gemini, conservative deterministic validation is used.
8. Human-review uncertain cases, then add related companies to leads, the audit queue, Supabase, or exports.

## Website verification

Automatic candidates can use:

```text
GOOGLE_PLACES_API_KEY=SECRET
BRAVE_SEARCH_API_KEY=SECRET
```

A candidate receives a 0–100 match score from company-name tokens, category, location and exact public-phone evidence. The system rejects test/example domains, directory/social profiles and low-confidence matches. A reachable page is not automatically the official company website.

## Endpoints

```text
POST /api/exhibition/import
POST /api/exhibition/search-html
POST /api/exhibition/enrich
POST /api/exhibition/ai-validate
```

Enrichment processes up to eight companies per request for serverless limits; AI/deterministic relation validation supports up to 40 evidence rows.

## Opportunity logic

- No verified official website: Website Verification / Launch + SEO, opportunity around 94
- Verified website error/audit failure: Technical Recovery, high opportunity
- Verified SEO score below 50: Technical SEO Recovery
- Verified SEO score 50–79: SEO Growth 90 Days
- Verified SEO score 80+: Content & CRO Growth
- Explicitly unrelated exhibitor: excluded from lead/database import

Scores and AI classifications are advisory research—not official exhibitor status, ownership proof, company quality, revenue or ranking claims.
