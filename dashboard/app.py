from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from auth.service import AuthService
from config.settings import AppSettings
from config.settings import load_settings
from dashboard.routes import router
from jobs.manager import JobManager


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.job_manager = JobManager(resolved_settings)
        app.state.auth_service = AuthService(resolved_settings.auth)
        await app.state.job_manager.start()
        try:
            yield
        finally:
            await app.state.job_manager.stop()

    app = FastAPI(
        title="SentinelAI Dashboard",
        description="Local-first dashboard for SentinelAI workflows, artifacts, memory, and tooling.",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.job_manager = JobManager(resolved_settings)
    app.state.auth_service = AuthService(resolved_settings.auth)
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    app.include_router(router)
    return app


app = create_app()
