"""In-process background jobs (pipeline runs, training, recalibration) with a single worker
so writes never interleave. Status is polled through /pipeline/jobs/{job_id}."""

from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from satsa.audit.hashing import new_id


@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "QUEUED"  # QUEUED | RUNNING | SUCCESS | FAILED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "kind": self.kind, "status": self.status, "started_at": self.started_at.isoformat(timespec="seconds") if self.started_at else None,
                "finished_at": self.finished_at.isoformat(timespec="seconds") if self.finished_at else None, "result": self.result, "error": self.error, "params": self.params}


class JobRunner:
    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="satsa-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._active: str | None = None

    @property
    def active(self) -> Job | None:
        with self._lock:
            return self._jobs.get(self._active) if self._active else None

    def submit(self, kind: str, fn: Callable[[], dict[str, Any]], params: dict[str, Any] | None = None) -> Job:
        job = Job(new_id("job_"), kind, params=params or {})
        with self._lock:
            self._jobs[job.job_id] = job

        def _run() -> None:
            with self._lock:
                self._active = job.job_id
            job.status, job.started_at = "RUNNING", datetime.now()
            try:
                job.result = fn() or {}
                job.status = "SUCCESS"
            except Exception as exc:  # noqa: BLE001
                job.status, job.error = "FAILED", f"{type(exc).__name__}: {exc}"
                job.result = {"trace": traceback.format_exc()[-2000:]}
            finally:
                job.finished_at = datetime.now()
                with self._lock:
                    if self._active == job.job_id:
                        self._active = None

        self._pool.submit(_run)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        return [j.as_dict() for j in sorted(jobs, key=lambda j: j.started_at or datetime.min, reverse=True)[:limit]]

    def busy(self) -> bool:
        with self._lock:
            return any(j.status in ("QUEUED", "RUNNING") for j in self._jobs.values())
