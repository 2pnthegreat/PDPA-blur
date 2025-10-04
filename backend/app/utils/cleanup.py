"""Utility helpers for scheduling temporary file cleanup."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.face import FaceRegistry

logger = logging.getLogger(__name__)


def schedule_file_expiration(path: Path, delay_seconds: int, label: str) -> None:
    """Schedule automatic deletion of a file after `delay_seconds`."""

    def _remove() -> None:
        try:
            path.unlink(missing_ok=True)
            logger.info("Expired %s removed: %s", label, path)
        except PermissionError as exc:
            logger.warning("Permission error removing %s %s: %s", label, path, exc)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.warning("Failed to remove %s %s: %s", label, path, exc)

    threading.Timer(delay_seconds, _remove).start()


def schedule_profile_expiration(
    user_id: str,
    registry: "FaceRegistry",
    delay_seconds: int,
) -> None:
    """Schedule removal of a face profile after `delay_seconds` if still expired."""

    def _expire() -> None:
        profile = registry.get(user_id)
        if profile is None:
            return
        if profile.expires_at and profile.expires_at <= time.time():
            registry.remove(user_id)
            logger.info("Expired face profile removed for user '%s'", user_id)

    threading.Timer(delay_seconds, _expire).start()


def prune_expired_files(path: Path, max_age_seconds: int, label: str) -> None:
    """Remove files older than ``max_age_seconds`` in ``path``."""

    if not path.exists():
        return

    threshold = time.time() - max_age_seconds
    for entry in path.iterdir():
        try:
            if not entry.is_file():
                continue
            if entry.stat().st_mtime <= threshold:
                entry.unlink(missing_ok=True)
                logger.info("Pruned expired %s: %s", label, entry)
        except FileNotFoundError:
            continue
        except PermissionError as exc:  # pragma: no cover - best effort cleanup
            logger.warning("Permission error pruning %s %s: %s", label, entry, exc)
