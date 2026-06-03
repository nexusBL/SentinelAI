from __future__ import annotations

import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from auth.service import AuthService
from database.models import JobModel
from database.models import RunModel
from database.models import UserModel
from database.repositories import MetadataRepository
from database.session import create_session_factory
from database.session import initialize_database
from jobs.manager import JobManager
from jobs.models import JobRecord
from jobs.models import JobRequest


def make_request() -> JobRequest:
    return JobRequest(
        mode="phase6",
        url="https://example.com",
        instruction="Test homepage",
        model="llama3",
        max_retries=1,
        memory_enabled=True,
        mcp_enabled=True,
    )


def test_database_initializes_from_clean_environment(temp_settings):
    initialize_database(temp_settings)
    assert temp_settings.database.sqlite_path.exists()

    session_factory = create_session_factory(temp_settings)
    with session_factory() as session:
        assert session.query(UserModel).count() == 0
        assert session.query(JobModel).count() == 0
        assert session.query(RunModel).count() == 0


def test_alembic_upgrade_creates_metadata_tables(monkeypatch, tmp_path):
    db_path = tmp_path / "alembic" / "metadata.db"
    monkeypatch.setenv("SENTINELAI_DATABASE_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("SENTINELAI_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())

    assert {"users", "jobs", "runs", "alembic_version"}.issubset(tables)


def test_repository_persists_users_jobs_runs_and_relationships(temp_settings):
    initialize_database(temp_settings)
    repository = MetadataRepository(create_session_factory(temp_settings))
    auth = AuthService(temp_settings.auth, repository=repository)
    user = auth.create_user(
        username="alice",
        email="alice@example.com",
        password="password123",
    )
    job_manager_job = None
    job = repository.upsert_job(
        JobRecord(
            request=make_request(),
            owner_user_id=user.user_id,
            status="completed",
            run_id="20260604T120000000000Z",
            result_summary={"status": "passed", "run_id": "20260604T120000000000Z"},
        )
    )
    job_manager_job = job
    run = repository.upsert_run_from_summary(
        run_id="20260604T120000000000Z",
        owner_user_id=user.user_id,
        job_id=job.job_id,
        summary={
            "status": "passed",
            "phase": "phase6",
            "requested_url": "https://example.com",
            "instruction": "Test homepage",
            "retry_count": 1,
            "memory_hits": 2,
            "mcp_enabled": True,
            "tool_invocation_count": 4,
        },
        artifact_path=str(temp_settings.storage.runs_root / "20260604T120000000000Z"),
        metrics_summary={"total_workflow_duration_ms": 1234},
    )

    assert job_manager_job.owner_user_id == user.user_id
    assert run["owner_user_id"] == user.user_id
    assert repository.get_user_by_username_or_email("ALICE").user_id == user.user_id
    assert repository.list_jobs(owner_user_id=user.user_id, include_all=False)[0].job_id == job.job_id
    assert repository.list_run_summaries(owner_user_id=user.user_id, include_all=False)[0]["run_id"] == run["run_id"]

    with create_session_factory(temp_settings)() as session:
        stored_user = session.get(UserModel, user.user_id)
        assert stored_user is not None
        assert len(stored_user.jobs) == 1
        assert len(stored_user.runs) == 1


def test_repository_ownership_queries_filter_runs(temp_settings):
    initialize_database(temp_settings)
    repository = MetadataRepository(create_session_factory(temp_settings))
    auth = AuthService(temp_settings.auth, repository=repository)
    alice = auth.create_user(username="alice", email="alice@example.com", password="password123")
    bob = auth.create_user(username="bob", email="bob@example.com", password="password123", role="user")

    for run_id, owner_id in [
        ("20260604T120000000000Z", alice.user_id),
        ("20260604T120100000000Z", bob.user_id),
    ]:
        repository.upsert_run_from_summary(
            run_id=run_id,
            owner_user_id=owner_id,
            job_id=None,
            summary={"status": "passed", "phase": "phase6"},
            artifact_path=str(temp_settings.storage.runs_root / run_id),
        )

    alice_runs = repository.list_run_summaries(owner_user_id=alice.user_id, include_all=False)
    all_runs = repository.list_run_summaries(include_all=True)

    assert [run["run_id"] for run in alice_runs] == ["20260604T120000000000Z"]
    assert len(all_runs) == 2


@pytest.mark.asyncio
async def test_job_manager_persists_lifecycle_states(temp_settings):
    async def fake_executor(job):
        await asyncio.sleep(0.01)
        return {"status": "passed", "run_id": "20260604T121000000000Z"}

    manager = JobManager(temp_settings, executor=fake_executor)
    try:
        job = await manager.submit(make_request())
        assert manager.repository.get_job(job.job_id).status == "queued"

        await asyncio.wait_for(manager._queue.join(), timeout=2)
        stored = manager.repository.get_job(job.job_id)

        assert stored is not None
        assert stored.status == "completed"
        assert stored.run_id == "20260604T121000000000Z"
        assert manager.repository.get_run_summary("20260604T121000000000Z") is not None
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_job_manager_persists_failed_and_cancelled_states(temp_settings):
    release = asyncio.Event()

    async def blocking_executor(job):
        await release.wait()
        raise RuntimeError("planner offline")

    manager = JobManager(temp_settings, executor=blocking_executor)
    try:
        first = await manager.submit(make_request())
        second = await manager.submit(make_request())
        await asyncio.sleep(0.05)
        cancelled = await manager.cancel(second.job_id)

        assert cancelled is not None
        assert manager.repository.get_job(second.job_id).status == "cancelled"

        release.set()
        await asyncio.wait_for(manager._queue.join(), timeout=2)

        assert manager.repository.get_job(first.job_id).status == "failed"
        assert "planner offline" in manager.repository.get_job(first.job_id).failure_reason
    finally:
        release.set()
        await manager.stop()
