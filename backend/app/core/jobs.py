"""In-memory job tracking used during early development."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobProgress:
    job_id: str
    state: JobState = JobState.PENDING
    progress: float = 0.0
    message: Optional[str] = None
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())
    result_path: Optional[str] = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "job_id": self.job_id,
            "state": self.state,
            "progress": round(self.progress, 2),
            "message": self.message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result_path": self.result_path,
        }


class JobStore:
    """Thread-safe in-memory registry for jobs."""

    def __init__(self) -> None:
        self._jobs: Dict[str, JobProgress] = {}
        self._lock = threading.Lock()

    def create(self) -> JobProgress:
        job_id = uuid.uuid4().hex
        job = JobProgress(job_id=job_id)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[JobProgress]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        progress: Optional[float] = None,
        state: Optional[JobState] = None,
        message: Optional[str] = None,
        result_path: Optional[str] = None,
    ) -> Optional[JobProgress]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if progress is not None:
                job.progress = max(0.0, min(progress, 100.0))
            if state is not None:
                job.state = state
            if message is not None:
                job.message = message
            if result_path is not None:
                job.result_path = result_path
            job.updated_at = time.time()
            return job

    def all(self) -> Dict[str, JobProgress]:
        with self._lock:
            return dict(self._jobs)


job_store = JobStore()
