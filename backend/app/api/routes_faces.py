"""Endpoints related to reference face management."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..core.config import get_settings
from ..face import FaceProfile, face_registry
from ..utils.cleanup import (
    prune_expired_files,
    schedule_file_expiration,
    schedule_profile_expiration,
)
from ..utils.files import save_upload_file
from ..schemas.face import FaceRegistrationResponse
from ..services.face_service import compute_embedding

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/reference", response_model=FaceRegistrationResponse, status_code=201)
async def upload_reference_face(
    user_id: str = Form(...),
    images: List[UploadFile] = File(...),
) -> FaceRegistrationResponse:
    if not images:
        raise HTTPException(status_code=400, detail="At least one reference image is required")

    settings = get_settings()
    prune_expired_files(settings.reference_faces_dir, 300, "reference image")
    prune_expired_files(settings.uploads_dir, 300, "uploaded video")
    prune_expired_files(settings.processed_dir, 300, "processed video")
    stored_paths: List[Path] = []
    embeddings: List[List[float]] = []
    logger.info("Received %d reference images for user '%s'", len(images), user_id)

    failed_paths: List[Path] = []
    for index, image in enumerate(images):
        if not image.content_type or not image.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="All uploaded files must be images")

        suffix = Path(image.filename or "").suffix or ".jpg"
        filename = f"{user_id}_{index}_{uuid4().hex}{suffix}"
        stored_path = save_upload_file(
            image,
            destination_dir=settings.reference_faces_dir,
            filename=filename,
        )
        stored_paths.append(stored_path)
        try:
            embeddings.append(await compute_embedding(stored_path))
        except ValueError as exc:
            logger.warning("Failed to extract face from %s: %s", stored_path, exc)
            failed_paths.append(stored_path)
        finally:
            image.file.close()

    if not embeddings:
        for path in stored_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail="ไม่สามารถตรวจพบใบหน้าจากรูปที่อัปโหลด กรุณาเลือกรูปที่เห็นใบหน้าชัดเจน",
        )

    expiry = time.time() + 300
    profile = FaceProfile(
        label=user_id,
        embeddings=embeddings,
        image_paths=stored_paths,
        created_at=time.time(),
        expires_at=expiry,
    )
    face_registry.register(profile)

    logger.info(
        "Registered %d/%d reference images for user '%s'",
        len(embeddings),
        len(images),
        user_id,
    )

    for path in stored_paths:
        schedule_file_expiration(path, 300, f"reference image for user {user_id}")
    schedule_profile_expiration(user_id, face_registry, 300)

    return FaceRegistrationResponse(
        user_id=user_id,
        image_paths=[str(path) for path in stored_paths],
        count=len(stored_paths),
    )
