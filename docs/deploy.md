# Deployment

## Status (as of 2026-09-02)

Done, verified against the real accounts:

- **Supabase project created, schema fully migrated, seed data loaded** (273 countries,
  10 document types, 20 topics, 1 jurisdiction) — verified by pointing a real backend
  instance at it and confirming `/api/meta` and `/api/countries` respond correctly. No
  FARA data loaded yet (that's the ingest workflows' job, gated on object storage below).
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
- **`ingest-bulk` triggered for real** via `workflow_dispatch` once all the secrets were
  in place — see the Actions tab for the outcome; this is the first real run since two
  earlier *scheduled* runs failed outright (no secrets existed yet at that point).

Still blocked on one manual step only doable from your account: importing the single
Vercel project.

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
None of the three has been triggered yet — worth a manual `workflow_dispatch` run once
Supabase Storage is wired up, both to smoke-test it and to get real data into the
now-empty production database rather than waiting for the next scheduled run.

## Verifying it actually runs unattended

`workflow_dispatch` is enabled on all three so they can be triggered by hand from the
Actions tab for a first real-data test without waiting for the cron schedule. One week
after go-live, `/api/meta`'s `data_as_of` and `extraction_coverage` fields are the
concrete proof the weekly refresh requirement is actually being met, not just configured.
