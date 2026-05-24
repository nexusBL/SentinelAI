from __future__ import annotations

import asyncio
from typing import Any

from config.settings import AppSettings
from dashboard.services import execute_dashboard_run
from jobs.models import JobRecord


class JobWorker:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    async def execute(self, job: JobRecord) -> dict[str, Any]:
        def run_in_thread() -> dict[str, Any]:
            return asyncio.run(
                execute_dashboard_run(
                    base_settings=self.settings,
                    mode=job.request.mode,
                    url=job.request.url,
                    instruction=job.request.instruction,
                    model=job.request.model,
                    max_retries=job.request.max_retries,
                    memory_enabled=job.request.memory_enabled,
                    mcp_enabled=job.request.mcp_enabled,
                )
            )

        return await asyncio.to_thread(run_in_thread)
