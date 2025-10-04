"""Utility helpers for face detection and blurring (placeholder implementations)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple


BoundingBox = Tuple[int, int, int, int]


def detect_faces(image_path: Path) -> List[BoundingBox]:
    """Return dummy bounding boxes.

    Later this will call an actual face detector. Right now we just provide a
    stub so other modules can be developed in parallel.
    """

    return []


def blur_regions(
    frame_path: Path,
    regions: Iterable[BoundingBox],
    *,
    blur_level: int,
) -> Path:
    """Pretend to blur requested regions and return the resulting path."""

    return frame_path
