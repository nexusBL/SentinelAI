from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import AppSettings


RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{12}Z$")


def is_valid_run_id(run_id: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(run_id))


def safe_load_json(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def safe_load_text(path: Path) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"


def pretty_json(payload: Any) -> str:
    if payload is None:
        return "{}"
    return json.dumps(payload, indent=2, default=str)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def humanize_datetime(value: str | None) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "Unknown"
    return parsed.astimezone(timezone.utc).strftime("%b %d, %Y %H:%M UTC")


def humanize_duration(duration_ms: int | float | None) -> str:
    if duration_ms is None:
        return "Unknown"
    total_ms = max(0, int(duration_ms))
    if total_ms < 1000:
        return f"{total_ms} ms"
    total_seconds = total_ms / 1000
    if total_seconds < 60:
        return f"{total_seconds:.1f}s"
    minutes, seconds = divmod(total_seconds, 60)
    return f"{int(minutes)}m {seconds:.1f}s"


def coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def ensure_relative_to(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def resolve_run_dir(runs_root: Path, run_id: str) -> Path | None:
    if not is_valid_run_id(run_id):
        return None
    candidate = (runs_root / run_id).resolve()
    if not ensure_relative_to(runs_root.resolve(), candidate):
        return None
    if not candidate.exists() or not candidate.is_dir():
        return None
    return candidate


def discover_run_dirs(runs_root: Path, limit: int | None = None) -> list[Path]:
    if not runs_root.exists():
        return []
    run_dirs = [
        path
        for path in runs_root.iterdir()
        if path.is_dir() and is_valid_run_id(path.name)
    ]
    run_dirs.sort(key=lambda item: item.name, reverse=True)
    if limit is not None:
        return run_dirs[: max(0, limit)]
    return run_dirs


def _relative_path_or_none(run_dir: Path, path_value: str | Path | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = (run_dir / path).resolve()
    if not ensure_relative_to(run_dir, path):
        return None
    return path.relative_to(run_dir).as_posix()


def _extract_duration_ms(report: dict[str, Any] | None, metrics: dict[str, Any] | None) -> int | None:
    if isinstance(metrics, dict):
        total_workflow_duration_ms = metrics.get("total_workflow_duration_ms")
        if isinstance(total_workflow_duration_ms, (int, float)) and total_workflow_duration_ms > 0:
            return int(total_workflow_duration_ms)

    if isinstance(report, dict):
        artifacts = report.get("artifacts", {})
        started_at = parse_datetime(artifacts.get("started_at"))
        completed_at = parse_datetime(artifacts.get("completed_at"))
        if started_at is not None and completed_at is not None:
            return max(0, int((completed_at - started_at).total_seconds() * 1000))
    return None


def _extract_run_summary(
    *,
    run_dir: Path,
    report_payload: dict[str, Any] | None,
    metrics_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    report_payload = report_payload or {}
    metrics_payload = metrics_payload or {}
    workflow = report_payload.get("workflow", {}) if isinstance(report_payload, dict) else {}
    artifacts = report_payload.get("artifacts", {}) if isinstance(report_payload, dict) else {}
    summary = report_payload.get("summary", {}) if isinstance(report_payload, dict) else {}
    duration_ms = _extract_duration_ms(report_payload, metrics_payload)
    created_at = report_payload.get("created_at")

    return {
        "run_id": report_payload.get("run_id", run_dir.name),
        "phase": report_payload.get("phase", "unknown"),
        "status": report_payload.get("status", "unknown"),
        "requested_url": report_payload.get("requested_url"),
        "final_url": report_payload.get("final_url"),
        "instruction": report_payload.get("instruction"),
        "page_title": report_payload.get("page_title"),
        "created_at": created_at,
        "created_at_display": humanize_datetime(created_at),
        "duration_ms": duration_ms,
        "duration_display": humanize_duration(duration_ms),
        "retry_count": workflow.get("retry_count", metrics_payload.get("retry_count", 0)),
        "max_retries": workflow.get("max_retries", metrics_payload.get("max_retries")),
        "memory_hits": workflow.get("memory_hits", metrics_payload.get("memory_hits", 0)),
        "mcp_enabled": workflow.get("mcp_enabled", metrics_payload.get("mcp_enabled", False)),
        "tool_invocation_count": workflow.get(
            "tool_invocation_count",
            metrics_payload.get("tool_invocation_count", 0),
        ),
        "failure_reason": report_payload.get("failure_reason"),
        "total_steps": summary.get("total_steps", 0),
        "passed_steps": summary.get("passed_steps", 0),
        "total_assertions": summary.get("total_assertions", 0),
        "passed_assertions": summary.get("passed_assertions", 0),
        "report_json_exists": (run_dir / "reports" / "report.json").exists(),
        "report_html_exists": (run_dir / "reports" / "report.html").exists(),
        "metrics_exists": (run_dir / "metrics" / "execution_metrics.json").exists(),
        "graph_trace_exists": (run_dir / "graph" / "graph_trace.json").exists(),
        "tool_trace_exists": (run_dir / "graph" / "tool_trace.json").exists(),
        "planner_trace_exists": (run_dir / "planner" / "planner_trace.json").exists(),
        "before_screenshot": _relative_path_or_none(run_dir, artifacts.get("before_screenshot_path")),
        "after_screenshot": _relative_path_or_none(run_dir, artifacts.get("after_screenshot_path")),
    }


def list_runs(settings: AppSettings, *, limit: int | None = None) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for run_dir in discover_run_dirs(settings.storage.runs_root, limit=limit):
        report_payload, _ = safe_load_json(run_dir / "reports" / "report.json")
        metrics_payload, _ = safe_load_json(run_dir / "metrics" / "execution_metrics.json")
        runs.append(
            _extract_run_summary(
                run_dir=run_dir,
                report_payload=report_payload if isinstance(report_payload, dict) else None,
                metrics_payload=metrics_payload if isinstance(metrics_payload, dict) else None,
            )
        )
    return runs


def list_screenshots(run_dir: Path, run_id: str) -> list[dict[str, Any]]:
    screenshots_dir = run_dir / "screenshots"
    if not screenshots_dir.exists():
        return []
    items = []
    for path in sorted(screenshots_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        items.append(
            {
                "name": path.name,
                "relative_path": path.relative_to(run_dir).as_posix(),
                "url": f"/runs/{run_id}/screenshots/{path.name}",
            }
        )
    return items


def _load_memory_retrievals(run_dir: Path) -> list[dict[str, Any]]:
    retrievals: list[dict[str, Any]] = []
    planner_dir = run_dir / "planner"
    if not planner_dir.exists():
        return retrievals
    for path in sorted(
        planner_dir.rglob("cycle_*_memory_retrieval.json"),
        key=lambda item: item.as_posix(),
        reverse=True,
    ):
        payload, error = safe_load_json(path)
        if isinstance(payload, dict):
            retrievals.append(
                {
                    "path": path.relative_to(run_dir).as_posix(),
                    "status": payload.get("status"),
                    "top_k": payload.get("top_k"),
                    "result_count": len(payload.get("results", [])),
                    "prompt_context": payload.get("prompt_context"),
                    "payload": payload,
                }
            )
    return retrievals


def get_run_detail(settings: AppSettings, run_id: str) -> dict[str, Any] | None:
    run_dir = resolve_run_dir(settings.storage.runs_root, run_id)
    if run_dir is None:
        return None

    report_payload, report_error = safe_load_json(run_dir / "reports" / "report.json")
    metrics_payload, metrics_error = safe_load_json(run_dir / "metrics" / "execution_metrics.json")
    graph_trace_payload, graph_error = safe_load_json(run_dir / "graph" / "graph_trace.json")
    planner_trace_payload, planner_error = safe_load_json(run_dir / "planner" / "planner_trace.json")
    tool_trace_payload, tool_error = safe_load_json(run_dir / "graph" / "tool_trace.json")
    report_payload_dict = report_payload if isinstance(report_payload, dict) else None
    metrics_payload_dict = metrics_payload if isinstance(metrics_payload, dict) else None
    summary = _extract_run_summary(
        run_dir=run_dir,
        report_payload=report_payload_dict,
        metrics_payload=metrics_payload_dict,
    )
    memory_retrievals = _load_memory_retrievals(run_dir)
    latest_memory_context = memory_retrievals[0]["prompt_context"] if memory_retrievals else None
    return {
        "run_dir": run_dir,
        "summary": summary,
        "report": report_payload_dict,
        "report_error": report_error,
        "metrics": metrics_payload_dict,
        "metrics_error": metrics_error,
        "graph_trace": graph_trace_payload if isinstance(graph_trace_payload, dict) else None,
        "graph_trace_error": graph_error,
        "planner_trace": planner_trace_payload if isinstance(planner_trace_payload, dict) else None,
        "planner_trace_error": planner_error,
        "tool_trace": tool_trace_payload if isinstance(tool_trace_payload, dict) else None,
        "tool_trace_error": tool_error,
        "screenshots": list_screenshots(run_dir, run_id),
        "memory_retrievals": memory_retrievals,
        "latest_memory_context": latest_memory_context,
        "report_pretty": pretty_json(report_payload_dict),
        "metrics_pretty": pretty_json(metrics_payload_dict),
        "graph_trace_pretty": pretty_json(graph_trace_payload if isinstance(graph_trace_payload, dict) else {}),
        "planner_trace_pretty": pretty_json(planner_trace_payload if isinstance(planner_trace_payload, dict) else {}),
        "tool_trace_pretty": pretty_json(tool_trace_payload if isinstance(tool_trace_payload, dict) else {}),
    }


def build_overview(settings: AppSettings) -> dict[str, Any]:
    runs = list_runs(settings)
    passed_runs = [run for run in runs if run["status"] == "passed"]
    failed_runs = [run for run in runs if run["status"] == "failed"]
    latest_run = runs[0] if runs else None
    workflow_file = Path(".github/workflows/ci.yml")
    return {
        "total_runs": len(runs),
        "passed_runs": len(passed_runs),
        "failed_runs": len(failed_runs),
        "latest_run": latest_run,
        "recent_runs": runs[:5],
        "memory_enabled": settings.memory.enabled,
        "mcp_enabled": settings.mcp.enabled,
        "ci_status": "configured" if workflow_file.exists() else "not configured",
    }


def list_reports(settings: AppSettings) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for run in list_runs(settings):
        if not run["report_json_exists"] and not run["report_html_exists"]:
            continue
        items.append(run)
    return items


def build_memory_summary(settings: AppSettings) -> dict[str, Any]:
    store_path = settings.memory.vector_db_path
    manifest_payload, _ = safe_load_json(store_path / "manifest.json")
    entries_count = (
        int(manifest_payload.get("vector_count", 0))
        if isinstance(manifest_payload, dict)
        else 0
    )
    latest_writes: list[dict[str, Any]] = []
    latest_retrievals: list[dict[str, Any]] = []

    for run_dir in discover_run_dirs(settings.storage.runs_root, limit=10):
        store_payload, _ = safe_load_json(run_dir / "logs" / "stored_memory_entry.json")
        if isinstance(store_payload, dict) and len(latest_writes) < 5:
            entry = store_payload.get("entry") or {}
            latest_writes.append(
                {
                    "run_id": run_dir.name,
                    "status": store_payload.get("status"),
                    "instruction": entry.get("instruction"),
                    "final_result": entry.get("final_result"),
                    "validation_status": entry.get("validation_status"),
                }
            )

        for retrieval in _load_memory_retrievals(run_dir):
            if len(latest_retrievals) >= 5:
                break
            latest_retrievals.append(
                {
                    "run_id": run_dir.name,
                    "status": retrieval.get("status"),
                    "result_count": retrieval.get("result_count"),
                    "prompt_context": retrieval.get("prompt_context"),
                }
            )
        if len(latest_writes) >= 5 and len(latest_retrievals) >= 5:
            break

    recent_runs = list_runs(settings, limit=10)
    return {
        "enabled": settings.memory.enabled,
        "store_path": str(store_path),
        "entry_count": entries_count,
        "latest_writes": latest_writes,
        "latest_retrievals": latest_retrievals,
        "recent_memory_hits": [
            {
                "run_id": run["run_id"],
                "memory_hits": run["memory_hits"],
                "status": run["status"],
            }
            for run in recent_runs
            if run["memory_hits"] > 0
        ][:5],
    }


def build_tools_summary(settings: AppSettings) -> dict[str, Any]:
    recent_events: list[dict[str, Any]] = []
    tool_stats: dict[str, dict[str, Any]] = {}
    for run_dir in discover_run_dirs(settings.storage.runs_root, limit=10):
        payload, _ = safe_load_json(run_dir / "graph" / "tool_trace.json")
        if not isinstance(payload, dict):
            continue
        for event in payload.get("events", []):
            tool_name = str(event.get("tool_name", "unknown"))
            status = str(event.get("status", "unknown"))
            duration_ms = int(event.get("duration_ms", 0) or 0)
            stats = tool_stats.setdefault(
                tool_name,
                {"count": 0, "failure_count": 0, "total_duration_ms": 0},
            )
            stats["count"] += 1
            stats["total_duration_ms"] += duration_ms
            if status != "passed":
                stats["failure_count"] += 1
            if len(recent_events) < 25:
                recent_events.append(
                    {
                        "run_id": run_dir.name,
                        "tool_name": tool_name,
                        "action": event.get("action"),
                        "status": status,
                        "duration_ms": duration_ms,
                        "graph_node": event.get("graph_node"),
                    }
                )

    for stats in tool_stats.values():
        count = max(1, stats["count"])
        stats["average_duration_ms"] = round(stats["total_duration_ms"] / count, 2)

    return {
        "enabled": settings.mcp.enabled,
        "tool_tracing_enabled": settings.mcp.tool_tracing_enabled,
        "available_tools": list(settings.mcp.enabled_tools),
        "tool_stats": tool_stats,
        "recent_events": recent_events[:25],
    }


def build_metrics_summary(settings: AppSettings) -> dict[str, Any]:
    runs = list_runs(settings)
    total_runs = len(runs)
    passed_runs = sum(1 for run in runs if run["status"] == "passed")
    duration_values = [run["duration_ms"] for run in runs if isinstance(run["duration_ms"], int)]
    retry_values = [int(run["retry_count"] or 0) for run in runs]
    memory_hits = [int(run["memory_hits"] or 0) for run in runs]
    tool_invocations = [int(run["tool_invocation_count"] or 0) for run in runs]

    def average(values: list[int]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    return {
        "total_runs": total_runs,
        "pass_rate": round((passed_runs / total_runs) * 100, 2) if total_runs else 0.0,
        "average_duration_ms": average(duration_values),
        "average_duration_display": humanize_duration(average(duration_values)),
        "average_retries": average(retry_values),
        "average_memory_hits": average(memory_hits),
        "average_tool_invocations": average(tool_invocations),
        "recent_runs": runs[:10],
    }


def build_settings_summary(settings: AppSettings) -> dict[str, Any]:
    return {
        "browser_headless": settings.browser.headless,
        "ollama_endpoint": settings.ollama.endpoint,
        "ollama_model": settings.ollama.model,
        "ollama_timeout_seconds": settings.ollama.timeout_seconds,
        "graph_max_retries": settings.graph.max_retries,
        "memory_enabled": settings.memory.enabled,
        "memory_store_path": str(settings.memory.vector_db_path),
        "memory_embedding_provider": settings.memory.embedding_provider,
        "memory_embedding_model": settings.memory.embedding_model,
        "memory_top_k": settings.memory.top_k,
        "mcp_enabled": settings.mcp.enabled,
        "mcp_tool_tracing_enabled": settings.mcp.tool_tracing_enabled,
        "mcp_timeout_seconds": settings.mcp.timeout_seconds,
        "mcp_enabled_tools": list(settings.mcp.enabled_tools),
    }


def list_api_screenshots(settings: AppSettings, run_id: str) -> dict[str, Any] | None:
    run_dir = resolve_run_dir(settings.storage.runs_root, run_id)
    if run_dir is None:
        return None
    return {
        "run_id": run_id,
        "screenshots": list_screenshots(run_dir, run_id),
    }


def build_report_index_entry(settings: AppSettings, run_id: str) -> dict[str, Any] | None:
    detail = get_run_detail(settings, run_id)
    if detail is None:
        return None
    return {
        "run_id": run_id,
        "status": detail["summary"]["status"],
        "report": detail["report"],
    }
