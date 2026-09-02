# Deployment

## Status (as of 2026-09-02)

Done, verified against the real accounts:

- **Supabase project created.** Schema fully migrated (`0001`–`0005`) and reference
  tables seeded (273 countries, 10 document types, 20 topics, 1 jurisdiction) — verified
  by pointing a real backend instance at it and confirming `/api/meta` and
  `/api/countries` respond correctly. No FARA data loaded yet (that's the ingest
  workflows' job, gated on R2 below).
- **GitHub Actions secrets `DATABASE_URL` (session pooler) and `ANTHROPIC_API_KEY`** are
  set on the repo.
- **Frontend is now deploy-ready**: `frontend/src/api/client.ts` reads an optional
  `VITE_API_BASE_URL` build-time env var and prefixes every API call with it (falls back
  to `""`, i.e. relative paths, so local dev via the Vite proxy is unaffected). The
  backend's CORS is already wide open for `GET` (`main.py`), so no backend change was
  needed to allow a separate frontend origin to call it.

Still blocked on manual steps only doable from your accounts (below): the Supabase
**transaction pooler** string for Vercel, the Cloudflare R2 bucket/token, and importing
both Vercel projects.

## Architecture

- **Postgres**: Supabase (hosted). The direct-connection host (`db.<ref>.supabase.co:5432`)
  is IPv6-only (confirmed via `dig` — `AAAA` present, no `A` record). GitHub Actions
  runners have no IPv6 egress, so ingest/normalize/extract use Supabase's **session
  pooler** instead (IPv4-compatible, one dedicated backend connection per client
  session — full session/prepared-statement support). The backend API uses the separate
  **transaction-mode pooler** (port `6543`, also IPv4-compatible), sized for a
  serverless function's many short-lived connections.
  `backend/src/fara_backend/db.py` sets `prepare_threshold=None` for exactly this reason:
  psycopg3's server-side prepared statements don't survive PgBouncer transaction pooling
  handing out a different backend connection per statement — without this, the API would
  intermittently fail with "prepared statement does not exist" under load. The session
  pooler doesn't have this problem, so `fara-normalize`/`fara-extract` don't need it.
- **Object storage**: Cloudflare R2 (S3-compatible, no egress fees) holds the raw bulk
  CSVs (`fara/bulk/...`) and every downloaded filing PDF (`fara/docs/...`), plus the
  ingest manifest (`manifest/manifest.sqlite3`) so the GitHub Actions runners — which
  get a fresh filesystem every run — have somewhere durable to read/write kill-safe
  resumability state. `fara_ingest.archive_factory.get_archive()` picks `R2Archive`
  over `LocalArchive` automatically once `FARA_R2_BUCKET` is set; local dev needs no
  R2 credentials at all. The backend API never touches R2 directly — it only serves
  what's already in Postgres.
- **Scheduled jobs**: three GitHub Actions workflows (below), all unattended, none of
  them ever pass `--mode backfill` / `--backfill` — the ~154K pre-existing historical
  documents are never touched by the schedule (docs/api-notes.md, docs/extraction.md).
- **Backend**: FastAPI on Vercel (`backend/api/index.py`, `backend/vercel.json`), its
  own Vercel project rooted at `backend/`.
- **Frontend**: static Vite build on Vercel, its own separate Vercel project rooted at
  `frontend/` — zero-config (Vercel auto-detects the Vite framework preset; no
  `vercel.json` needed there since the app has no client-side routing to fall back for,
  see `frontend/src/state/store.ts`). Calls the backend cross-origin via
  `VITE_API_BASE_URL`.

## One-time manual provisioning

None of this can be scripted from here — it needs your accounts and API tokens.

### 1. Supabase — one step left

The project, schema, and seed data are already live. The only remaining piece:

1. In the Supabase dashboard → Project Settings → Database → Connect, find the
   **Transaction pooler** string (port `6543`, *not* the session pooler already in use
   for GitHub Actions). Same password as the session pooler.
2. That becomes the `DATABASE_URL` environment variable on the **backend** Vercel
   project (step 4 below).
3. Optional hardening, skippable for now: Database → Roles → create a read-only role
   and `GRANT SELECT ON ALL TABLES IN SCHEMA public TO <role>;` (re-run after future
   migrations, or set a default-privilege grant so new tables inherit it), then use that
   role in the transaction-pooler string instead of the default role. The API is
   read-only by construction (`CORSMiddleware(allow_methods=["GET"])` plus no
   write endpoints exist), so this reduces blast radius but isn't a hard blocker.

### 2. Cloudflare R2 — not started, needed to unblock the scheduled workflows

1. Create an R2 bucket (e.g. `fara-archive`).
2. Create an R2 API token (Account → R2 → Manage API Tokens) with read/write access
   scoped to that bucket. This gives you an access key ID, secret access key, and an
   account-specific S3 endpoint: `https://<account_id>.r2.cloudflarestorage.com`.
3. Hand me the four values (`FARA_R2_BUCKET`, `FARA_R2_ENDPOINT_URL`,
   `FARA_R2_ACCESS_KEY_ID`, `FARA_R2_SECRET_ACCESS_KEY`) and I'll set them as GitHub
   Actions secrets directly (`gh secret set`) — no need to paste them anywhere yourself.
   Without these, `ingest-bulk`/`docs-and-extract` will still run but fall back to
   writing into the runner's throwaway filesystem, meaning no downloaded PDFs or
   resumability manifest survive between runs.

### 3. GitHub repository secrets — partially done

Repo: [github.com/lehogg325/FARA](https://github.com/lehogg325/FARA). Already set:
`DATABASE_URL` (session pooler), `ANTHROPIC_API_KEY`. Still needed: `FARA_R2_BUCKET`,
`FARA_R2_ENDPOINT_URL`, `FARA_R2_ACCESS_KEY_ID`, `FARA_R2_SECRET_ACCESS_KEY` (send me
the values from step 2 and I'll set them).

### 4. Vercel — two projects, neither imported yet

**Backend:**
1. Import the repo, set the **root directory to `backend/`** (it has its own
   `vercel.json`/`requirements.txt`/`api/index.py`) so the rest of the uv workspace
   isn't part of the deployed function.
2. Project → Settings → Environment Variables: `DATABASE_URL` = the transaction-pooler
   string from step 1 above.
3. Deploy. `GET /api/health` should return `{"status": "ok"}`. Note the deployed URL
   (e.g. `https://fara-backend.vercel.app`) — the frontend needs it next.

**Frontend:**
1. Import the repo again as a *second* Vercel project, root directory `frontend/`.
   Vercel should auto-detect the Vite framework preset (build command `npm run build`,
   output directory `dist`) with no further config.
2. Project → Settings → Environment Variables: `VITE_API_BASE_URL` = the backend
   project's URL from the previous step (no trailing slash).
3. Deploy.

## Local dev vs. production

Local dev (`docker-compose.yml`'s Postgres 17, `LocalArchive` writing to `data/raw/`) is
entirely separate from production — no shared state, no shared credentials. Nothing in
this repo talks to Supabase or R2 unless `DATABASE_URL`/`FARA_R2_*` are explicitly set,
and the frontend only calls a separate backend origin if `VITE_API_BASE_URL` is set.

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
R2 is wired up, both to smoke-test and to get real data into the now-empty Supabase
database rather than waiting for the next scheduled run.

## Verifying it actually runs unattended

`workflow_dispatch` is enabled on all three so they can be triggered by hand from the
Actions tab for a first real-data test without waiting for the cron schedule. One week
after go-live, `/api/meta`'s `data_as_of` and `extraction_coverage` fields are the
concrete proof the weekly refresh requirement is actually being met, not just configured.
