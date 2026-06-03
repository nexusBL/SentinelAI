from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserModel(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    jobs: Mapped[list["JobModel"]] = relationship(back_populates="owner")
    runs: Mapped[list["RunModel"]] = relationship(back_populates="owner")


class JobModel(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    max_retries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mcp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    owner: Mapped[UserModel | None] = relationship(back_populates="jobs")
    run: Mapped["RunModel | None"] = relationship(back_populates="job", uselist=False)


class RunModel(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_user_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("jobs.job_id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    requested_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    memory_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mcp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tool_invocation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_from: Mapped[str] = mapped_column(String(80), nullable=False, default="dashboard")

    owner: Mapped[UserModel | None] = relationship(back_populates="runs")
    job: Mapped[JobModel | None] = relationship(back_populates="run", foreign_keys=[job_id])
