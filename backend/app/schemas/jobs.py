"""Pydantic models for job management."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..core.jobs import JobState


class JobCreatedResponse(BaseModel):
    job_id: str
    state: JobState


class JobStatusResponse(BaseModel):
    job_id: str
    state: JobState
    progress: float
    message: Optional[str] = None
    download_url: Optional[str] = None
