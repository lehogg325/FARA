"""Vercel serverless entrypoint: exposes the FastAPI app as an ASGI function.

Vercel routes /api/* here (see vercel.json rewrites); the static frontend build
is served by Vercel's CDN from the same deployment/domain, so the API and the
UI are one Vercel project rather than two.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))

from fara_backend.main import app  # noqa: E402

__all__ = ["app"]
