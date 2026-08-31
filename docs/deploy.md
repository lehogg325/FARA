# Deployment

## Architecture

- **Postgres**: Supabase (hosted). **Correction from real testing (2026-08-31)**: Supabase's
  direct-connection host (`db.<ref>.supabase.co:5432`) resolves to an IPv6-only DNS
  record — confirmed via `dig` (`AAAA` present, no `A` record) and a real failed
  connection attempt. GitHub Actions runners have no IPv6 egress, so the direct
  connection is a non-starter for the scheduled workflows regardless of what works on
  any given local machine. Ingest/normalize/extract instead use Supabase's **session
  pooler** (IPv4-compatible, one dedicated backend connection per client session — full
  session/prepared-statement support, which Supabase itself recommends for scripts, CI,
  and tools making occasional connections). The backend API uses the separate
  **transaction-mode pooler** (port `6543`, also IPv4-compatible) with a read-only role,
  sized for a serverless function's many short-lived connections.
  `backend/src/fara_backend/db.py` sets `prepare_threshold=None` for exactly this reason:
  psycopg3's server-side prepared statements don't survive PgBouncer transaction pooling
  handing out a different backend connection per statement — without this, the API would
  intermittently fail with "prepared statement does not exist" under load. The session
  pooler doesn't have this problem (session-level, not transaction-level), so
  `fara-normalize`/`fara-extract` don't need the same workaround.
- **Object storage**: Cloudflare R2 (S3-compatible, no egress fees) holds the raw bulk
  CSVs (`fara/bulk/...`) and every downloaded filing PDF (`fara/docs/...`), plus the
  ingest manifest (`manifest/manifest.sqlite3`) so the GitHub Actions runners — which
  get a fresh filesystem every run — have somewhere durable to read/write kill-safe
  resumability state. `fara_ingest.archive_factory.get_archive()` picks `R2Archive`
  over `LocalArchive` automatically once `FARA_R2_BUCKET` is set; local dev needs no
  R2 credentials at all (see `ingest/src/fara_ingest/config.py`).
- **Scheduled jobs**: three GitHub Actions workflows (below), all unattended, none of
  them ever pass `--mode backfill` / `--backfill` — the ~154K pre-existing historical
  documents are never touched by the schedule (docs/api-notes.md, docs/extraction.md).
- **Backend**: FastAPI on Vercel (`backend/api/index.py`, `backend/vercel.json`).

## One-time manual provisioning

None of this can be scripted from here — it needs your accounts and API tokens.

### 1. Supabase

1. Create a project at supabase.com (pick a region close to where the GitHub Actions
   runners and Vercel functions will run — `us-east-1` is the safest default for both).
2. In Database → Roles, create two roles: a write-capable one for ingest (or just use
   the default `postgres` role) and a read-only role for the API
   (`GRANT SELECT ON ALL TABLES IN SCHEMA public TO fara_read;` after the first
   `fara-normalize migrate` has created the tables — re-run the grant after future
   migrations that add tables, or set a default-privilege grant so new tables inherit it).
3. Grab two connection strings from Database → Connect (**not** the plain "Direct
   connection" string — it's IPv6-only and won't work from GitHub Actions or most
   local networks, confirmed 2026-08-31):
   - **Session pooler** — becomes the `DATABASE_URL` secret for the ingest workflows
     (`ingest-bulk.yml`, `docs-and-extract.yml`).
   - **Transaction pooler** (port `6543`) — becomes the `DATABASE_URL` env var on Vercel,
     using the read-only role.
4. Postgres version: this project's local `docker-compose.yml` is pinned to 17 to match
   Supabase's current default for new projects — nothing else to reconcile.

### 2. Cloudflare R2

1. Create an R2 bucket (e.g. `fara-archive`).
2. Create an R2 API token (Account → R2 → Manage API Tokens) with read/write access
   scoped to that bucket. This gives you an access key ID, secret access key, and an
   account-specific S3 endpoint: `https://<account_id>.r2.cloudflarestorage.com`.
3. That's `FARA_R2_BUCKET`, `FARA_R2_ENDPOINT_URL`, `FARA_R2_ACCESS_KEY_ID`,
   `FARA_R2_SECRET_ACCESS_KEY`.

### 3. GitHub repository + secrets

Repo: [github.com/lehogg325/FARA](https://github.com/lehogg325/FARA) (public, pushed
2026-08-31). Repo Settings → Secrets and variables → Actions, add:
`DATABASE_URL` (Supabase **session pooler** connection string — not the plain "Direct
connection" one, see above), `FARA_R2_BUCKET`, `FARA_R2_ENDPOINT_URL`,
`FARA_R2_ACCESS_KEY_ID`, `FARA_R2_SECRET_ACCESS_KEY`, `ANTHROPIC_API_KEY`
(docs-and-extract.yml only).

### 4. Vercel

1. Import the repo, set the **root directory to `backend/`** (it has its own
   `vercel.json`/`requirements.txt`/`api/index.py`) so the rest of the uv workspace
   isn't part of the deployed function.
2. Project → Settings → Environment Variables: `DATABASE_URL` (Supabase **transaction
   pooler** connection string, read-only role).
3. Deploy. `GET /api/health` should return `{"status": "ok"}`.

## Local dev vs. production

Local dev (`docker-compose.yml`'s Postgres 17, `LocalArchive` writing to `data/raw/`) is
entirely separate from production — no shared state, no shared credentials. Nothing in
this repo talks to Supabase or R2 unless `DATABASE_URL`/`FARA_R2_*` are explicitly set.

## Scheduled workflows

| Workflow | Cadence | What it touches |
|---|---|---|
| `.github/workflows/ingest-bulk.yml` | daily, 05:00 UTC | 4 bulk CSVs → Postgres; cross-checks against a live JSON poll |
| `.github/workflows/ingest-poll.yml` | every 4h | diagnostic JSON poll, archived only — never loaded into Postgres |
| `.github/workflows/docs-and-extract.yml` | weekly, Monday 06:00 UTC | newly-filed PDFs only: download → text/OCR → rule fields → LLM fields |

Historical backfill (`fara-ingest docs --mode backfill`, `fara-extract ... --mode
backfill`) is never invoked by any of these — it's a manual, local (or
`workflow_dispatch`-triggered, if ever wanted) operation, decoupled from the schedule.

## Verifying it actually runs unattended

`workflow_dispatch` is enabled on all three so they can be triggered by hand from the
Actions tab for a first real-data test without waiting for the cron schedule. One week
after go-live, `/api/meta`'s `data_as_of` and `extraction_coverage` fields are the
concrete proof the weekly refresh requirement is actually being met, not just configured.
