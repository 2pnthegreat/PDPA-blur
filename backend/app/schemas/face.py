"""Pydantic models for face-related responses."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel


class FaceRegistrationResponse(BaseModel):
    user_id: str
    image_paths: List[str]
    count: int
