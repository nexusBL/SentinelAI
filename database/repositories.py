from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.models import User
from jobs.models import JobRecord
from jobs.models import JobRequest
from database.models import JobModel
from database.models import RunModel
from database.models import UserModel


SessionFactory = Callable[[], Session]


def _as_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class MetadataRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def create_user(self, user: User) -> User:
        with self.session_factory() as session:
            model = UserModel(
                user_id=user.user_id,
                username=user.username,
                email=user.email,
                password_hash=user.password_hash,
                role=user.role,
                created_at=user.created_at,
            )
            session.add(model)
            session.commit()
            return self._user_from_model(model)

    def get_user_by_id(self, user_id: str) -> User | None:
        with self.session_factory() as session:
            model = session.get(UserModel, user_id)
            return self._user_from_model(model)

    def get_user_by_username_or_email(self, value: str) -> User | None:
        normalized = value.strip().lower()
        with self.session_factory() as session:
            model = session.execute(
                select(UserModel).where(
                    or_(
                        func.lower(UserModel.username) == normalized,
                        func.lower(UserModel.email) == normalized,
                    )
                )
            ).scalar_one_or_none()
            return self._user_from_model(model)

    def count_users(self) -> int:
        with self.session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(UserModel)) or 0)

    def upsert_job(self, job: JobRecord) -> JobRecord:
        with self.session_factory() as session:
            model = session.get(JobModel, job.job_id)
            if model is None:
                model = JobModel(job_id=job.job_id)
                session.add(model)
            self._apply_job(model, job)
            session.commit()
            return self._job_from_model(model)

    def get_job(self, job_id: str) -> JobRecord | None:
        with self.session_factory() as session:
            model = session.get(JobModel, job_id)
            return self._job_from_model(model)

    def list_jobs(
        self,
        *,
        owner_user_id: str | None = None,
        include_all: bool = True,
    ) -> list[JobRecord]:
        with self.session_factory() as session:
            statement = select(JobModel).order_by(JobModel.created_at.desc())
            if not include_all:
                statement = statement.where(JobModel.owner_user_id == owner_user_id)
            models = session.execute(statement).scalars().all()
            return [job for model in models if (job := self._job_from_model(model)) is not None]

    def upsert_run_from_summary(
        self,
        *,
        run_id: str,
        owner_user_id: str | None,
        job_id: str | None,
        summary: dict[str, Any],
        artifact_path: str | None,
        metrics_summary: dict[str, Any] | None = None,
        created_from: str = "dashboard",
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            model = session.get(RunModel, run_id)
            if model is None:
                model = RunModel(run_id=run_id)
                session.add(model)
            model.owner_user_id = owner_user_id
            model.job_id = job_id
            model.status = str(summary.get("status") or "unknown")
            model.phase = str(summary.get("phase") or "unknown")
            model.requested_url = summary.get("requested_url")
            model.final_url = summary.get("final_url")
            model.instruction = summary.get("instruction")
            model.page_title = summary.get("page_title")
            model.created_at = _as_datetime(summary.get("created_at"))
            model.duration_ms = _coerce_int(summary.get("duration_ms"))
            model.retry_count = _coerce_int(summary.get("retry_count")) or 0
            model.memory_hits = _coerce_int(summary.get("memory_hits")) or 0
            model.mcp_enabled = bool(summary.get("mcp_enabled"))
            model.tool_invocation_count = _coerce_int(summary.get("tool_invocation_count")) or 0
            model.failure_reason = summary.get("failure_reason")
            model.artifact_path = artifact_path
            model.metrics_summary = metrics_summary
            model.created_from = created_from
            session.commit()
            return self._run_summary_from_model(model)

    def get_run_summary(self, run_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            model = session.get(RunModel, run_id)
            return self._run_summary_from_model(model)

    def list_run_summaries(
        self,
        *,
        limit: int | None = None,
        owner_user_id: str | None = None,
        include_all: bool = True,
    ) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            statement = select(RunModel).order_by(RunModel.created_at.desc().nullslast(), RunModel.run_id.desc())
            if not include_all:
                statement = statement.where(RunModel.owner_user_id == owner_user_id)
            if limit is not None:
                statement = statement.limit(max(0, limit))
            models = session.execute(statement).scalars().all()
            return [
                summary
                for model in models
                if (summary := self._run_summary_from_model(model)) is not None
            ]

    def admin_counts(self) -> dict[str, int]:
        with self.session_factory() as session:
            total_users = int(session.scalar(select(func.count()).select_from(UserModel)) or 0)
            total_jobs = int(session.scalar(select(func.count()).select_from(JobModel)) or 0)
            total_runs = int(session.scalar(select(func.count()).select_from(RunModel)) or 0)
            failed_jobs = int(
                session.scalar(select(func.count()).select_from(JobModel).where(JobModel.status == "failed")) or 0
            )
            failed_runs = int(
                session.scalar(select(func.count()).select_from(RunModel).where(RunModel.status == "failed")) or 0
            )
            return {
                "total_users": total_users,
                "total_jobs": total_jobs,
                "total_runs": total_runs,
                "failed_jobs": failed_jobs,
                "failed_runs": failed_runs,
            }

    def _apply_job(self, model: JobModel, job: JobRecord) -> None:
        model.owner_user_id = job.owner_user_id
        model.run_id = job.run_id
        model.status = job.status
        model.mode = job.request.mode
        model.url = job.request.url
        model.instruction = job.request.instruction
        model.model = job.request.model
        model.max_retries = job.request.max_retries
        model.memory_enabled = job.request.memory_enabled
        model.mcp_enabled = job.request.mcp_enabled
        model.created_at = job.created_at
        model.started_at = job.started_at
        model.completed_at = job.completed_at
        model.failure_reason = job.failure_reason
        model.progress = job.progress
        model.result_summary = job.result_summary
        model.cancel_requested = job.cancel_requested

    def _user_from_model(self, model: UserModel | None) -> User | None:
        if model is None:
            return None
        return User(
            user_id=model.user_id,
            username=model.username,
            email=model.email,
            password_hash=model.password_hash,
            role=model.role,
            created_at=model.created_at,
        )

    def _job_from_model(self, model: JobModel | None) -> JobRecord | None:
        if model is None:
            return None
        return JobRecord(
            job_id=model.job_id,
            owner_user_id=model.owner_user_id,
            status=model.status,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            failure_reason=model.failure_reason,
            progress=model.progress or {},
            result_summary=model.result_summary,
            run_id=model.run_id,
            cancel_requested=model.cancel_requested,
            request=JobRequest(
                mode=model.mode,
                url=model.url,
                instruction=model.instruction,
                model=model.model,
                max_retries=model.max_retries,
                memory_enabled=model.memory_enabled,
                mcp_enabled=model.mcp_enabled,
            ),
        )

    def _run_summary_from_model(self, model: RunModel | None) -> dict[str, Any] | None:
        if model is None:
            return None
        return {
            "run_id": model.run_id,
            "owner_user_id": model.owner_user_id,
            "job_id": model.job_id,
            "phase": model.phase,
            "status": model.status,
            "requested_url": model.requested_url,
            "final_url": model.final_url,
            "instruction": model.instruction,
            "page_title": model.page_title,
            "created_at": _iso(model.created_at),
            "completed_at": _iso(model.completed_at),
            "duration_ms": model.duration_ms,
            "retry_count": model.retry_count,
            "memory_hits": model.memory_hits,
            "mcp_enabled": model.mcp_enabled,
            "tool_invocation_count": model.tool_invocation_count,
            "failure_reason": model.failure_reason,
            "artifact_path": model.artifact_path,
            "metrics_summary": model.metrics_summary,
            "created_from": model.created_from,
        }


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value))
    except ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")
