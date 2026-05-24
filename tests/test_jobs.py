from __future__ import annotations

import asyncio

import pytest

from jobs.manager import JobManager
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


@pytest.mark.asyncio
async def test_job_manager_completes_queued_job(temp_settings):
    async def fake_executor(job):
        await asyncio.sleep(0.01)
        return {"status": "passed", "run_id": "20260524T120000000000Z"}

    manager = JobManager(temp_settings, executor=fake_executor)
    try:
        job = await manager.submit(make_request())
        await asyncio.wait_for(manager._queue.join(), timeout=2)
        stored = await manager.get(job.job_id)
        assert stored is not None
        assert stored.status == "completed"
        assert stored.run_id == "20260524T120000000000Z"
        assert stored.progress["percent"] == 100
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_job_manager_queues_sequentially_and_cancels_waiting_job(temp_settings):
    release = asyncio.Event()

    async def fake_executor(job):
        await release.wait()
        return {"status": "passed", "run_id": "20260524T120100000000Z"}

    manager = JobManager(temp_settings, executor=fake_executor)
    try:
        first = await manager.submit(make_request())
        second = await manager.submit(make_request())
        await asyncio.sleep(0.05)
        cancelled = await manager.cancel(second.job_id)
        assert cancelled is not None
        assert cancelled.status == "cancelled"
        active = await manager.active_jobs()
        assert [job.job_id for job in active] == [first.job_id]
        release.set()
        await asyncio.wait_for(manager._queue.join(), timeout=2)
        metrics = await manager.metrics()
        assert metrics["completed_jobs"] == 1
        assert metrics["cancelled_jobs"] == 1
    finally:
        release.set()
        await manager.stop()


@pytest.mark.asyncio
async def test_job_manager_failed_job_records_failure_reason(temp_settings):
    async def fake_executor(job):
        raise RuntimeError("planner offline")

    manager = JobManager(temp_settings, executor=fake_executor)
    try:
        job = await manager.submit(make_request())
        await asyncio.wait_for(manager._queue.join(), timeout=2)
        stored = await manager.get(job.job_id)
        assert stored is not None
        assert stored.status == "failed"
        assert "planner offline" in str(stored.failure_reason)
        metrics = await manager.metrics()
        assert metrics["failed_jobs"] == 1
    finally:
        await manager.stop()
