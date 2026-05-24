from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Literal
from uuid import uuid4


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class JobRequest:
    mode: str
    url: str
    instruction: str
    model: str | None = None
    max_retries: int | None = None
    memory_enabled: bool = True
    mcp_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "url": self.url,
            "instruction": self.instruction,
            "model": self.model,
            "max_retries": self.max_retries,
            "memory_enabled": self.memory_enabled,
            "mcp_enabled": self.mcp_enabled,
        }


@dataclass(slots=True)
class JobRecord:
    request: JobRequest
    job_id: str = field(default_factory=lambda: uuid4().hex)
    status: JobStatus = "queued"
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    progress: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] | None = None
    run_id: str | None = None
    cancel_requested: bool = False

    def duration_ms(self) -> int | None:
        end = self.completed_at or (utc_now() if self.started_at else None)
        if self.started_at is None or end is None:
            return None
        return max(0, int((end - self.started_at).total_seconds() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "created_at": isoformat(self.created_at),
            "started_at": isoformat(self.started_at),
            "completed_at": isoformat(self.completed_at),
            "duration_ms": self.duration_ms(),
            "failure_reason": self.failure_reason,
            "progress": self.progress,
            "request": self.request.to_dict(),
            "result_summary": self.result_summary,
            "run_id": self.run_id,
            "cancel_requested": self.cancel_requested,
        }
