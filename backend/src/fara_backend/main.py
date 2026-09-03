from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from fara_backend.routers import countries, documents, foreign_principals, meta, registrants, search

app = FastAPI(title="FARA Data Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Every route in routers/ is read-only (data changes only via the scheduled
    ingest/extract workflows, docs/deploy.md), so successful GET responses are safe
    to cache at Vercel's edge. /api/meta is exempt — it's the freshness/status-check
    endpoint (data_as_of, extraction_coverage) and caching it would make that check
    lie for up to the TTL window."""
    response = await call_next(request)
    if request.method == "GET" and response.status_code == 200 and request.url.path != "/api/meta":
        response.headers["Cache-Control"] = "public, s-maxage=3600, stale-while-revalidate=86400"
    return response


app.include_router(meta.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(registrants.router, prefix="/api")
app.include_router(foreign_principals.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(countries.router, prefix="/api")
