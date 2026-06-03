from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from auth.service import AuthService
from config.settings import AppSettings
from config.settings import load_settings
from dashboard.routes import router
from database.repositories import MetadataRepository
from database.session import create_session_factory
from database.session import initialize_database
from jobs.manager import JobManager


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    initialize_database(resolved_settings)
    session_factory = create_session_factory(resolved_settings)
    metadata_repository = MetadataRepository(session_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.metadata_repository = metadata_repository
        app.state.job_manager = JobManager(resolved_settings, repository=metadata_repository)
        app.state.auth_service = AuthService(
            resolved_settings.auth,
            repository=metadata_repository,
        )
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
    app.state.metadata_repository = metadata_repository
    app.state.job_manager = JobManager(resolved_settings, repository=metadata_repository)
    app.state.auth_service = AuthService(
        resolved_settings.auth,
        repository=metadata_repository,
    )
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    app.include_router(router)
    return app


app = create_app()
