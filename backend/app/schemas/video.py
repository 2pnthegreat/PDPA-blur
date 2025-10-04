"""Video related schemas."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class BlurMode(str, Enum):
    FAST = "fast"
    DETAILED = "detailed"


class VideoBlurRequest(BaseModel):
    job_id: str = Field(..., description="Identifier for the background processing job")
    user_id: str
    mode: BlurMode
    blur_level: int = Field(..., ge=1, le=10)
    video_path: str
