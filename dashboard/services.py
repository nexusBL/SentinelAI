from __future__ import annotations

from typing import Any

from agents.graph_workflow import LangGraphWorkflow
from config.settings import AppSettings
from main import resolve_settings
from main import run_phase3


SUPPORTED_MODES = ("phase3", "phase4", "phase5", "phase6")


async def execute_dashboard_run(
    *,
    mode: str,
    url: str,
    instruction: str,
    model: str | None,
    max_retries: int | None,
    memory_enabled: bool,
    mcp_enabled: bool,
) -> dict[str, Any]:
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported execution mode '{mode}'.")

    if mode == "phase3":
        return await run_phase3(
            url=url,
            instruction=instruction,
            headed=False,
            model=model,
        )

    settings = resolve_settings(headed=False)
    settings.memory.enabled = memory_enabled
    settings.mcp.enabled = mcp_enabled
    workflow = LangGraphWorkflow(settings)
    result = await workflow.execute(
        url=url,
        instruction=instruction,
        model=model,
        max_retries=max_retries,
        phase_name=mode,
    )
    return result.to_summary()


def dashboard_defaults(settings: AppSettings) -> dict[str, Any]:
    return {
        "default_mode": "phase6",
        "default_model": settings.ollama.model,
        "default_max_retries": settings.graph.max_retries,
        "default_memory_enabled": settings.memory.enabled,
        "default_mcp_enabled": settings.mcp.enabled,
        "supported_modes": SUPPORTED_MODES,
    }
