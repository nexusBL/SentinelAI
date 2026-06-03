from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any

from config.settings import AppSettings
from database.repositories import MetadataRepository
from database.session import create_session_factory
from database.session import initialize_database
from jobs.models import JobRecord
from jobs.models import JobRequest
from jobs.models import utc_now
from jobs.worker import JobWorker

Executor = Callable[[JobRecord], Awaitable[dict[str, Any]]]


class JobManager:
    def __init__(
        self,
        settings: AppSettings,
        *,
        executor: Executor | None = None,
        repository: MetadataRepository | None = None,
    ) -> None:
        self.settings = settings
        self._jobs: dict[str, JobRecord] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._worker_task: asyncio.Task | None = None
        self._executor = executor or JobWorker(settings).execute
        if repository is None:
            initialize_database(settings)
            repository = MetadataRepository(create_session_factory(settings))
        self.repository = repository

    async def start(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        self._worker_task = None

    async def submit(self, request: JobRequest, *, owner_user_id: str | None = None) -> JobRecord:
        await self.start()
        job = JobRecord(
            request=request,
            owner_user_id=owner_user_id,
            progress={
                "message": "Queued for execution",
                "stage": "queued",
                "percent": 0,
            },
        )
        async with self._lock:
            self._jobs[job.job_id] = job
            self.repository.upsert_job(job)
        await self._queue.put(job.job_id)
        return job

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            job = self._jobs.get(job_id)
        return job or self.repository.get_job(job_id)

    async def list_jobs(
        self,
        *,
        owner_user_id: str | None = None,
        include_all: bool = True,
    ) -> list[JobRecord]:
        jobs = self.repository.list_jobs(owner_user_id=owner_user_id, include_all=include_all)
        return sorted(jobs, key=lambda item: item.created_at, reverse=True)

    async def active_jobs(
        self,
        *,
        owner_user_id: str | None = None,
        include_all: bool = True,
    ) -> list[JobRecord]:
        jobs = await self.list_jobs(owner_user_id=owner_user_id, include_all=include_all)
        return [job for job in jobs if job.status in {"queued", "running"}]

    async def cancel(
        self,
        job_id: str,
        *,
        owner_user_id: str | None = None,
        include_all: bool = True,
    ) -> JobRecord | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                job = self.repository.get_job(job_id)
            if job is None:
                return None
            if not include_all and job.owner_user_id != owner_user_id:
                return None
            if job.status == "queued":
                job.status = "cancelled"
                job.completed_at = utc_now()
                job.failure_reason = "Cancelled before execution started."
                job.cancel_requested = True
                job.progress = {
                    "message": "Cancelled before execution started",
                    "stage": "cancelled",
                    "percent": 100,
                }
            elif job.status == "running":
                job.cancel_requested = True
                job.progress = {
                    **job.progress,
                    "message": "Cancellation requested; current workflow will finish best-effort.",
                }
            self._jobs[job.job_id] = job
            self.repository.upsert_job(job)
            return job

    async def metrics(self) -> dict[str, Any]:
        jobs = await self.list_jobs()
        completed = [job for job in jobs if job.status == "completed"]
        failed = [job for job in jobs if job.status == "failed"]
        cancelled = [job for job in jobs if job.status == "cancelled"]
        running = [job for job in jobs if job.status == "running"]
        queued = [job for job in jobs if job.status == "queued"]
        durations = [
            job.duration_ms()
            for job in jobs
            if job.status in {"completed", "failed", "cancelled"} and job.duration_ms() is not None
        ]
        average_duration_ms = round(sum(durations) / len(durations), 2) if durations else 0.0
        return {
            "total_jobs": len(jobs),
            "queued_jobs": len(queued),
            "running_jobs": len(running),
            "completed_jobs": len(completed),
            "failed_jobs": len(failed),
            "cancelled_jobs": len(cancelled),
            "queue_length": self._queue.qsize(),
            "average_execution_ms": average_duration_ms,
            "worker_running": self._worker_task is not None and not self._worker_task.done(),
        }

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                job = await self.get(job_id)
                if job is None or job.status == "cancelled":
                    continue
                await self._run_job(job)
            finally:
                self._queue.task_done()

    async def _run_job(self, job: JobRecord) -> None:
        async with self._lock:
            if job.status == "cancelled":
                return
            job.status = "running"
            job.started_at = utc_now()
            job.progress = {
                "message": "Workflow execution started",
                "stage": "running",
                "percent": 20,
            }
            self.repository.upsert_job(job)

        try:
            summary = await self._executor(job)
        except Exception as exc:
            async with self._lock:
                if job.status != "cancelled":
                    job.status = "failed"
                    job.completed_at = utc_now()
                    job.failure_reason = f"{type(exc).__name__}: {exc}"
                    job.progress = {
                        "message": "Workflow execution failed",
                        "stage": "failed",
                        "percent": 100,
                    }
                    self.repository.upsert_job(job)
            return

        async with self._lock:
            if job.status == "cancelled":
                return
            job.result_summary = summary
            run_id = summary.get("run_id") if isinstance(summary, dict) else None
            job.run_id = run_id if isinstance(run_id, str) else None
            if job.run_id and job.owner_user_id:
                self._write_run_owner(job)
            job.completed_at = utc_now()
            status = str(summary.get("status", "")).lower() if isinstance(summary, dict) else ""
            if status in {"failed", "error"}:
                job.status = "failed"
                job.failure_reason = (
                    str(summary.get("failure_reason"))
                    if isinstance(summary, dict) and summary.get("failure_reason")
                    else "Workflow completed with failed status."
                )
                stage = "failed"
                message = "Workflow completed with failures"
            else:
                job.status = "completed"
                stage = "completed"
                message = "Workflow completed"
            job.progress = {
                "message": message,
                "stage": stage,
                "percent": 100,
            }
            self.repository.upsert_job(job)
            if job.run_id:
                self._persist_run_metadata(job)

    def _write_run_owner(self, job: JobRecord) -> None:
        if not job.run_id or not job.owner_user_id:
            return
        metadata_dir = self.settings.storage.runs_root / job.run_id / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        (metadata_dir / "owner.json").write_text(
            json.dumps(
                {
                    "owner_user_id": job.owner_user_id,
                    "job_id": job.job_id,
                    "created_by": "dashboard",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _persist_run_metadata(self, job: JobRecord) -> None:
        if not job.run_id:
            return
        run_dir = self.settings.storage.runs_root / job.run_id
        report_payload = self._load_json(run_dir / "reports" / "report.json")
        metrics_payload = self._load_json(run_dir / "metrics" / "execution_metrics.json")
        summary = self._summary_from_job(job, report_payload, metrics_payload)
        self.repository.upsert_run_from_summary(
            run_id=job.run_id,
            owner_user_id=job.owner_user_id,
            job_id=job.job_id,
            summary=summary,
            artifact_path=str(run_dir),
            metrics_summary=metrics_payload if isinstance(metrics_payload, dict) else None,
        )

    def _summary_from_job(
        self,
        job: JobRecord,
        report_payload: dict[str, Any] | None,
        metrics_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        report_payload = report_payload or {}
        workflow = report_payload.get("workflow", {}) if isinstance(report_payload, dict) else {}
        return {
            "run_id": job.run_id,
            "phase": report_payload.get("phase") or job.request.mode,
            "status": report_payload.get("status") or job.status,
            "requested_url": report_payload.get("requested_url") or job.request.url,
            "final_url": report_payload.get("final_url") or (job.result_summary or {}).get("final_url"),
            "instruction": report_payload.get("instruction") or job.request.instruction,
            "page_title": report_payload.get("page_title"),
            "created_at": report_payload.get("created_at") or job.created_at.isoformat().replace("+00:00", "Z"),
            "duration_ms": (job.result_summary or {}).get("duration_ms"),
            "retry_count": workflow.get("retry_count", (job.result_summary or {}).get("retry_count", 0)),
            "memory_hits": workflow.get("memory_hits", (job.result_summary or {}).get("memory_hits", 0)),
            "mcp_enabled": workflow.get("mcp_enabled", job.request.mcp_enabled),
            "tool_invocation_count": workflow.get(
                "tool_invocation_count",
                (job.result_summary or {}).get("tool_invocation_count", 0),
            ),
            "failure_reason": report_payload.get("failure_reason") or job.failure_reason,
        }

    def _load_json(self, path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None
