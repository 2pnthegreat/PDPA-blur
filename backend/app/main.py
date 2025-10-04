"""FastAPI entrypoint for the PDPA blur backend."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.core.config import get_settings


def _configure_logging(level_name: str | None = None) -> None:
    env_override = os.getenv("PDPA_LOG_LEVEL")
    if env_override:
        level_name = env_override
    if not level_name:
        level_name = "INFO"
    level_str = str(level_name).upper()
    level = getattr(logging, level_str, logging.INFO)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    else:
        root_logger.setLevel(level)


settings = get_settings()
_configure_logging(settings.log_level)

app = FastAPI(title="PDPA Blur API", version="0.1.0")

if settings.allow_insecure_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "PDPA blur backend is running"}
