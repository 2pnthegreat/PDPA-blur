"""Endpoints for video processing."""
from __future__ import annotations

from mimetypes import guess_type
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..core.config import get_settings
from ..core.jobs import JobState, job_store
from ..schemas.jobs import JobCreatedResponse
from ..schemas.video import BlurMode, VideoBlurRequest
from ..services.video_service import enqueue_blur_job
from ..utils.files import save_upload_file

router = APIRouter()


@router.post("/blur", response_model=JobCreatedResponse, status_code=202)
async def blur_video(
    user_id: str = Form(...),
    mode: BlurMode = Form(...),
    blur_level: int = Form(...),
    video: UploadFile = File(...),
) -> JobCreatedResponse:
    if not video.content_type or not video.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a video")

    if blur_level < 1 or blur_level > 10:
        raise HTTPException(status_code=400, detail="Blur level must be between 1 and 10")

    settings = get_settings()
    stored_path = save_upload_file(
        video,
        destination_dir=settings.uploads_dir,
        filename=video.filename,
    )

    job = job_store.create()
    job_store.update(job.job_id, state=JobState.RUNNING, progress=1.0)

    payload = VideoBlurRequest(
        job_id=job.job_id,
        user_id=user_id,
        mode=mode,
        blur_level=blur_level,
        video_path=str(stored_path),
    )

    enqueue_blur_job(payload)

    return JobCreatedResponse(job_id=job.job_id, state=job.state)


@router.get("/{job_id}/download")
async def download_processed_video(job_id: str) -> FileResponse:
    job = job_store.get(job_id)
    if job is None or job.state != JobState.COMPLETED or not job.result_path:
        raise HTTPException(status_code=404, detail="Processed video not available")

    path = Path(job.result_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Processed file missing")

    media_type, _ = guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream", filename=path.name)
