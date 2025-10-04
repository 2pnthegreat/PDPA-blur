"""Endpoints for monitoring job progress."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..core.jobs import JobState, job_store
from ..schemas.jobs import JobStatusResponse

router = APIRouter()


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, request: Request) -> JobStatusResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    download_url = None
    if job.result_path and job.state == JobState.COMPLETED:
        download_url = str(request.url_for("download_processed_video", job_id=job_id))
    return JobStatusResponse(
        job_id=job.job_id,
        state=job.state,
        progress=job.progress,
        message=job.message,
        download_url=download_url,
    )
