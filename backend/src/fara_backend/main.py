from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fara_backend.routers import documents, foreign_principals, meta, registrants, search

app = FastAPI(title="FARA Data Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(meta.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(registrants.router, prefix="/api")
app.include_router(foreign_principals.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
