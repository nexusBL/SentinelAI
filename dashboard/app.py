from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config.settings import AppSettings
from config.settings import load_settings
from dashboard.routes import router


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    app = FastAPI(
        title="SentinelAI Dashboard",
        description="Local-first dashboard for SentinelAI workflows, artifacts, memory, and tooling.",
    )
    app.state.settings = resolved_settings
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    app.include_router(router)
    return app


app = create_app()
