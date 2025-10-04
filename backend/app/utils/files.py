"""Helper utilities for handling file uploads."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, Optional

from fastapi import UploadFile


def save_upload_file(upload: UploadFile, destination_dir: Path, *, filename: Optional[str] = None) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    target_name = filename or upload.filename or "upload.bin"
    target_path = destination_dir / target_name
    with target_path.open("wb") as file_handle:
        shutil.copyfileobj(upload.file, file_handle)
    return target_path


def clean_directory(path: Path, *, keep: Optional[Iterable[Path]] = None) -> None:
    keep_set = {p.resolve() for p in keep} if keep else set()
    if not path.exists():
        return
    for entry in path.iterdir():
        if entry.resolve() in keep_set:
            continue
        if entry.is_file():
            entry.unlink(missing_ok=True)
        elif entry.is_dir():
            shutil.rmtree(entry)
