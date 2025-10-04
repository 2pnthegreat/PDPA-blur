"""Meta endpoints such as health checks."""
from __future__ import annotations

from fastapi import APIRouter

from ..core.config import get_settings

router = APIRouter()


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "media_root": str(settings.media_root)}
