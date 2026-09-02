# Deployment

## Status (as of 2026-09-02)

**Vercel project imported and live** at `fara-ochre.vercel.app`. First real deploy
surfaced a build-time bug the earlier "verified locally" entries below didn't catch:
Vercel's Python builder prefers a root `pyproject.toml`/`uv.lock` (uv workspace) over
`requirements.txt` whenever both are present, running `uv sync` against the root project
instead of installing from `requirements.txt`. The root workspace project declared
`dependencies = []` (it's just an umbrella for the `ingest`/`pipeline`/`backend`
members), so the deployed `api/index.py` function's venv had no `fastapi` at all — every
`/api/*` route 500'd with `ModuleNotFoundError: No module named 'fastapi'`, not just
search. Fixed by mirroring `requirements.txt`'s runtime deps onto the root project so
`uv sync` actually installs them, then `uv lock` to regenerate. Re-verified against the
live deployment post-fix: `/api/meta`, `/api/search?q=Ballard` (`group_count: 2`), and
`/api/registrants/540` all return 200 with real data on `fara-ochre.vercel.app`.
Lesson: local `api/index.py` startup and even `vercel build` running end-to-end aren't
sufficient checks — always curl the actual deployed URL's `/api/*` routes after a Vercel
deploy, since the Python dependency-install path only diverges from local dev at
Vercel's build step.

Note also: the project's auto-generated `*-lehogg325s-projects.vercel.app` deployment
URLs sit behind Vercel's SSO/deployment-protection wall (redirect to
`vercel.com/sso-api`) — that's expected and unrelated to this bug. The public,
unprotected URL is the `fara-ochre.vercel.app` alias.

Done, verified against the real accounts:

- **Supabase project created, schema fully migrated, real data loaded.** The full bulk
  dataset is live: 7,078 registrants, 17,726 foreign principals, 44,597 short-form
  registrants, 153,266 registrant documents (plus 273 countries / 10 document types /
  20 topics reference data). Verified two ways: `/api/meta`'s `datasets` array reports
  all four loads `succeeded` with matching row counts, and `/api/search?q=Ballard`
  against the live database returns the real grouped "Ballard Partners" result
  (`group_count: 2`) the search-dedup work earlier in this conversation was built for.
- **GitHub Actions secrets `DATABASE_URL` (session pooler) and `ANTHROPIC_API_KEY`** are
  set on the repo.
- **One Vercel project, not two** — matching `github.com/lehogg325/LDA`'s proven setup:
  root `vercel.json` builds the frontend to static files and deploys the FastAPI app as
  a single Python serverless function (`api/index.py`) on the same domain, routed via
  rewrites (`/api/*` → the function, everything else → `index.html`). Verified locally:
  the root `api/index.py` entrypoint starts and serves `/api/meta` correctly against the
  live Supabase database.
- **Found and fixed a bad connection string.** The transaction-pooler string first
  pasted into this conversation (`db.<ref>.supabase.co:6543`) resolves to an
  **IPv6-only** address (checked via `dig` — no `A` record), same problem as the plain
  direct-connection string. The real transaction pooler lives on the same
  `aws-0-<region>.pooler.supabase.com` host as the already-working session pooler, just
  port `6543` instead of `5432` — constructed and connection-tested that instead.
- **Object storage is Supabase Storage, not Cloudflare.** `fara_ingest.r2_archive.R2Archive`
  was already a generic S3-compatible client (boto3 + a custom `endpoint_url`) with
  nothing R2-specific in it — renamed to `fara_ingest.object_store_archive.ObjectStoreArchive`
  and `FARA_R2_*` env vars to `FARA_STORAGE_*`. Bucket `FARA` on the same Supabase
  project, S3 endpoint `https://jpntfyaqoawdrlrqtavd.supabase.co/storage/v1/s3` —
  connection-tested for real: `list_buckets()` and a full write/read/delete round trip
  through the actual `ObjectStoreArchive` class both succeeded. All four
  `FARA_STORAGE_*` GitHub Actions secrets are set.
- **`ingest-bulk` triggered for real, twice.** Two earlier *scheduled* runs had failed
  outright (no secrets existed yet). The first `workflow_dispatch` run once secrets were
  in place got through `registrants` (3m42s) and `foreign_principals` (8m23s) before
  hitting the workflow's 30-minute timeout partway through `short_form_registrants` —
  see "Fixed a real production-scale performance bug" below. After that fix, a second
  run completed **all four datasets in 2m32s total**, including the cross-check against
  the live JSON poll.
- **Fixed a real production-scale performance bug the first run surfaced.**
  `registrants`/`foreign_principals`/`short_form_registrants` used a per-row
  SELECT-then-INSERT/UPDATE loop — fine against local Postgres, but ~30 rows/sec against
  Supabase's real session-pooler latency (2 round trips/row). `registrant_docs` had
  already hit and fixed this exact problem (migration 0003); the other three now use the
  same staging-table + bulk COPY + set-based-SQL pattern (migration 0006). Also found and
  fixed a real double-counting bug this surfaced in *all four* loaders, including the
  already-shipped `registrant_docs` one: the "touch unchanged" statement ran after
  "update changed", but "update changed" also overwrites `source_row_hash` to match the
  incoming row — making the row it just updated trivially match "touch unchanged"'s
  hash-equality condition too. Caught by a real test assertion, fixed by reordering.

Still blocked on one manual step only doable from your account: importing the single
Vercel project. `docs-and-extract.yml` (PDF download + OCR + LLM extraction) hasn't been
triggered yet — deliberately left for you to kick off explicitly, since it spends real
Anthropic API credit.

## Architecture

- **Postgres**: Supabase (hosted). The direct-connection host (`db.<ref>.supabase.co:5432`)
  is IPv6-only (confirmed via `dig` — `AAAA` present, no `A` record) — same problem
  applies to that host on *any* port, including 6543 (confirmed live, see Status above).
  GitHub Actions runners have no IPv6 egress, so ingest/normalize/extract use Supabase's
  **session pooler** instead (`aws-0-<region>.pooler.supabase.com:5432`, IPv4-compatible,
  one dedicated backend connection per client session). The backend API uses the same
  host's **transaction-mode pooler** (port `6543`), sized for a serverless function's
  many short-lived connections. `backend/src/fara_backend/db.py` sets
  `prepare_threshold=None` for exactly this reason: psycopg3's server-side prepared
  statements don't survive PgBouncer transaction pooling handing out a different backend
  connection per statement — without this, the API would intermittently fail with
  "prepared statement does not exist" under load. The session pooler doesn't have this
  problem, so `fara-normalize`/`fara-extract` don't need it.
- **Object storage**: any S3-compatible bucket (Supabase Storage — see Status above)
  holds the raw bulk CSVs (`fara/bulk/...`) and every downloaded filing PDF
  (`fara/docs/...`), plus the ingest manifest (`manifest/manifest.sqlite3`) so the
  GitHub Actions runners — which get a fresh filesystem every run — have somewhere
  durable to read/write kill-safe resumability state.
  `fara_ingest.archive_factory.get_archive()` picks `ObjectStoreArchive` over
  `LocalArchive` automatically once `FARA_STORAGE_BUCKET` is set; local dev needs no
  storage credentials at all. The backend API never touches object storage directly —
  it only serves what's already in Postgres.
- **Scheduled jobs**: three GitHub Actions workflows (below), all unattended, none of
  them ever pass `--mode backfill` / `--backfill` — the ~154K pre-existing historical
  documents are never touched by the schedule (docs/api-notes.md, docs/extraction.md).
- **App**: one Vercel project, repo root. `vercel.json`'s `buildCommand` builds
  `frontend/` to static files (`outputDirectory: frontend/dist`); `api/index.py` puts
  `backend/src` on `sys.path` and exposes the FastAPI app as the serverless function
  Vercel's Python runtime runs. Root `requirements.txt` is the function's dependency
  list — deliberately just `fastapi`/`psycopg`/`psycopg-pool`/`pydantic`, not the whole
  uv workspace (ingest/pipeline never run on Vercel). Same-origin frontend+API means no
  CORS configuration is load-bearing for production, even though the backend's
  `CORSMiddleware(allow_origins=["*"], allow_methods=["GET"])` stays in place — cheap
  and harmless to leave permissive for a read-only public API.

## One-time manual provisioning

None of this can be scripted from here — it needs your accounts and API tokens.

### 1. Supabase — done

The project, schema, and seed data are already live, and both the session pooler and
Supabase Storage credentials are already GitHub Actions secrets.

Optional hardening, skippable for now: Database → Roles → create a read-only role and
`GRANT SELECT ON ALL TABLES IN SCHEMA public TO <role>;` (re-run after future migrations,
or set a default-privilege grant so new tables inherit it), then use that role's
connection string for the Vercel `DATABASE_URL` instead of the default role. The API is
read-only by construction (no write endpoints exist), so this reduces blast radius but
isn't a hard blocker.

### 2. Supabase Storage — done

Bucket `FARA`, S3-compatible endpoint on the same project. Connection-tested (Status
above). All four `FARA_STORAGE_*` secrets are set on the repo.

### 3. GitHub repository secrets — done

Repo: [github.com/lehogg325/FARA](https://github.com/lehogg325/FARA). All six secrets
set: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `FARA_STORAGE_BUCKET`,
`FARA_STORAGE_ENDPOINT_URL`, `FARA_STORAGE_ACCESS_KEY_ID`, `FARA_STORAGE_SECRET_ACCESS_KEY`.

### 4. Vercel — one project, not imported yet

1. Import `github.com/lehogg325/FARA` in Vercel (or `npx vercel` from the repo root).
   **Leave the root directory as the repo root** — `vercel.json` at the top level
   supplies the build command, output directory, function config, and routing; no
   framework preset needed (same pattern as `github.com/lehogg325/LDA`).
2. Project → Settings → Environment Variables: `DATABASE_URL` = the transaction-pooler
   string (verified working):
   ```
   postgresql://postgres.jpntfyaqoawdrlrqtavd:0xkzMsQRuoqJmFRj@aws-0-us-west-2.pooler.supabase.com:6543/postgres
   ```
3. Deploy. `/` serves the frontend; `/api/meta` is a quick health check.

## Local dev vs. production

Local dev (`docker-compose.yml`'s Postgres 17, `LocalArchive` writing to `data/raw/`) is
entirely separate from production — no shared state, no shared credentials. Nothing in
this repo talks to Supabase or object storage unless `DATABASE_URL`/`FARA_STORAGE_*` are
explicitly set. Local dev also runs the frontend and backend as two separate processes
(Vite dev server on 5173 proxying `/api` to uvicorn on 8000, `frontend/vite.config.ts`)
even though production is one deployment — the dev proxy and Vercel's rewrites solve the
same same-origin problem two different ways, so `client.ts`'s API calls stay relative
(`/api/...`) in both.

## Scheduled workflows

| Workflow | Cadence | What it touches |
|---|---|---|
| `.github/workflows/ingest-bulk.yml` | daily, 05:00 UTC | 4 bulk CSVs → Postgres; cross-checks against a live JSON poll |
| `.github/workflows/ingest-poll.yml` | every 4h | diagnostic JSON poll, archived only — never loaded into Postgres |
| `.github/workflows/docs-and-extract.yml` | weekly, Monday 06:00 UTC | newly-filed PDFs only: download → text/OCR → rule fields → LLM fields |

Historical backfill (`fara-ingest docs --mode backfill`, `fara-extract ... --mode
backfill`) is never invoked by any of these — it's a manual, local (or
`workflow_dispatch`-triggered, if ever wanted) operation, decoupled from the schedule.
`ingest-bulk` has been run successfully (Status above) and the daily schedule will keep
it current from here. `ingest-poll` and `docs-and-extract` haven't been triggered yet —
the latter deliberately, since it spends real Anthropic API credit; worth a manual
`workflow_dispatch` run when you're ready rather than waiting for Monday.

## Verifying it actually runs unattended

`workflow_dispatch` is enabled on all three so they can be triggered by hand from the
Actions tab for a first real-data test without waiting for the cron schedule. One week
after go-live, `/api/meta`'s `data_as_of` and `extraction_coverage` fields are the
concrete proof the weekly refresh requirement is actually being met, not just configured.
