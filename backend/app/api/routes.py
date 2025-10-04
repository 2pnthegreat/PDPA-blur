"""Root API router."""
from __future__ import annotations

from fastapi import APIRouter

from . import routes_faces, routes_jobs, routes_meta, routes_videos

router = APIRouter()
router.include_router(routes_faces.router, prefix="/faces", tags=["faces"])
router.include_router(routes_videos.router, prefix="/videos", tags=["videos"])
router.include_router(routes_jobs.router, prefix="/jobs", tags=["jobs"])
router.include_router(routes_meta.router, tags=["meta"])
