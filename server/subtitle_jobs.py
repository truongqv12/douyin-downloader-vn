from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SubtitleJob:
    def __init__(self, job_id: str, job_type: str, payload: Dict[str, Any]):
        self.job_id = job_id
        self.type = job_type
        self.payload = payload
        self.status = "pending"
        self.stage = "pending"
        self.progress = {"current": 0, "total": 0, "message": ""}
        self.outputs: Dict[str, str] = {}
        self.error: Optional[str] = None
        self.created_at = _now_iso()
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.finished_monotonic: Optional[float] = None
        self._task: Optional[asyncio.Task] = None

    def set_progress(self, stage: str, current: int, total: int, message: str) -> None:
        self.stage = stage
        self.progress = {"current": current, "total": total, "message": message}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "type": self.type,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "outputs": self.outputs,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class SubtitleJobManager:
    DEFAULT_MAX_JOBS = 500
    DEFAULT_JOB_TTL_SECONDS = 24 * 3600

    def __init__(
        self,
        executor: Callable[[SubtitleJob], Dict[str, Any]],
        *,
        max_concurrency: int = 2,
        max_jobs: int = DEFAULT_MAX_JOBS,
        job_ttl_seconds: float = DEFAULT_JOB_TTL_SECONDS,
    ):
        self.executor = executor
        self._jobs: Dict[str, SubtitleJob] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self.max_jobs = max(1, int(max_jobs))
        self.job_ttl_seconds = max(0.0, float(job_ttl_seconds))

    async def submit(self, job_type: str, payload: Dict[str, Any]) -> SubtitleJob:
        job = SubtitleJob(uuid.uuid4().hex[:12], job_type, payload)
        async with self._lock:
            self._prune_locked()
            self._jobs[job.job_id] = job
        job._task = asyncio.create_task(self._run(job))
        return job

    async def _run(self, job: SubtitleJob) -> None:
        async with self._semaphore:
            job.status = "running"
            job.started_at = _now_iso()
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, self.executor, job)
                job.outputs = {
                    str(k): str(v) for k, v in (result.get("outputs") or {}).items()
                }
                job.stage = str(result.get("stage") or "done")
                job.status = str(result.get("status") or "success")
                if result.get("error"):
                    job.error = str(result["error"])
            except Exception as exc:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
            finally:
                job.finished_at = _now_iso()
                job.finished_monotonic = time.monotonic()

    async def get(self, job_id: str) -> Optional[SubtitleJob]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_jobs(self) -> List[SubtitleJob]:
        async with self._lock:
            return list(self._jobs.values())

    async def shutdown(self) -> None:
        tasks = [j._task for j in self._jobs.values() if j._task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _prune_locked(self) -> None:
        now = time.monotonic()
        expired = [
            jid
            for jid, job in self._jobs.items()
            if job.status in {"success", "failed"}
            and job.finished_monotonic is not None
            and self.job_ttl_seconds > 0
            and (now - job.finished_monotonic) > self.job_ttl_seconds
        ]
        for jid in expired:
            self._jobs.pop(jid, None)
        if len(self._jobs) < self.max_jobs:
            return
        terminal = [
            (job.finished_monotonic or 0.0, jid)
            for jid, job in self._jobs.items()
            if job.status in {"success", "failed"}
        ]
        terminal.sort()
        overflow = len(self._jobs) - self.max_jobs + 1
        for _, jid in terminal[:overflow]:
            self._jobs.pop(jid, None)
