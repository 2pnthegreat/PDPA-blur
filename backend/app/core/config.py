"""Application configuration and path helpers."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    api_prefix: str = Field("/api", description="Root prefix for API routes")
    media_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "media",
        description="Base directory for all uploaded and generated assets.",
    )
    reference_faces_dirname: str = Field("reference_faces", description="Subdir for user face samples")
    uploads_dirname: str = Field("uploads", description="Subdir for raw user uploads")
    processed_dirname: str = Field("processed", description="Subdir for processed outputs")
    redis_url: str = Field("redis://localhost:6379/0", description="Redis URL for task progress storage")
    allow_insecure_cors: bool = Field(
        True,
        description="When true, enables CORS for all origins (development convenience).",
    )
    log_level: str = Field(
        "INFO",
        description="Logging level for application output",
        validation_alias=AliasChoices("PDPA_LOG_LEVEL", "LOG_LEVEL"),
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def reference_faces_dir(self) -> Path:
        return self.media_root / self.reference_faces_dirname

    @property
    def uploads_dir(self) -> Path:
        return self.media_root / self.uploads_dirname

    @property
    def processed_dir(self) -> Path:
        return self.media_root / self.processed_dirname


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    for path in (
        settings.media_root,
        settings.reference_faces_dir,
        settings.uploads_dir,
        settings.processed_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings
