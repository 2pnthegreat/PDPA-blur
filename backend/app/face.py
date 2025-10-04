"""Domain models for face identification and registry management."""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional


@dataclass
class FaceProfile:
    label: str
    embeddings: List[List[float]] = field(default_factory=list)
    image_paths: List[Path] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: time.time())
    expires_at: float = field(default_factory=lambda: 0.0)

    def average_embedding(self) -> List[float]:
        if not self.embeddings:
            return []
        length = len(self.embeddings[0])
        valid_embeddings = [emb for emb in self.embeddings if len(emb) == length]
        if not valid_embeddings:
            return []
        summed = [0.0] * length
        for embedding in valid_embeddings:
            for index, value in enumerate(embedding):
                summed[index] += value
        count = len(valid_embeddings)
        return [value / count for value in summed]


class FaceRegistry:
    """In-memory registry storing the latest reference face for a user."""

    def __init__(self) -> None:
        self._profiles: Dict[str, FaceProfile] = {}
        self._lock = Lock()

    def register(self, profile: FaceProfile) -> None:
        with self._lock:
            self._profiles[profile.label] = profile

    def get(self, label: str) -> Optional[FaceProfile]:
        with self._lock:
            profile = self._profiles.get(label)
            if profile and profile.expires_at and profile.expires_at <= time.time():
                self._profiles.pop(label, None)
                return None
            return profile

    def remove(self, label: str) -> None:
        with self._lock:
            self._profiles.pop(label, None)

    def clear(self) -> None:
        with self._lock:
            self._profiles.clear()


face_registry = FaceRegistry()
