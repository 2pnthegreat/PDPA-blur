"""Schemas describing job progress responses."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.core.jobs import JobState


class JobStatusResponse(BaseModel):
    job_id: str = Field(..., description="Identifier of the job being queried")
    state: JobState = Field(..., description="Current state of the job")
    progress: float = Field(..., description="Completion percentage")
    message: Optional[str] = Field(None, description="Human readable status message")
    created_at: float = Field(..., description="Unix timestamp when the job was created")
    updated_at: float = Field(..., description="Unix timestamp when the job was last updated")
    result_path: Optional[str] = Field(None, description="Absolute path to the generated asset")
