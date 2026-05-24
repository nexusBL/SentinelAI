from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi import Form
from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from dashboard.services import dashboard_defaults
from dashboard.services import SUPPORTED_MODES
from dashboard.utils import build_memory_summary
from dashboard.utils import build_metrics_summary
from dashboard.utils import build_overview
from dashboard.utils import build_settings_summary
from dashboard.utils import build_tools_summary
from dashboard.utils import coerce_bool
from dashboard.utils import ensure_relative_to
from dashboard.utils import get_run_detail
from dashboard.utils import is_valid_run_id
from dashboard.utils import list_api_screenshots
from dashboard.utils import list_reports
from dashboard.utils import list_runs
from dashboard.utils import resolve_run_dir
from jobs.models import JobRequest


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()

NAV_ITEMS = [
    {"id": "overview", "label": "Overview", "path": "/"},
    {"id": "new_run", "label": "New Run", "path": "/new-run"},
    {"id": "runs", "label": "Runs", "path": "/runs"},
    {"id": "reports", "label": "Reports", "path": "/reports"},
    {"id": "memory", "label": "Memory", "path": "/memory"},
    {"id": "tools", "label": "Tools", "path": "/tools"},
    {"id": "metrics", "label": "Metrics", "path": "/metrics"},
    {"id": "settings", "label": "Settings", "path": "/settings"},
]


def _settings(request: Request):
    return request.app.state.settings


def _job_manager(request: Request):
    return request.app.state.job_manager


def _render_page(
    request: Request,
    template_name: str,
    *,
    active_page: str,
    status_code: int = 200,
    **context,
):
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "active_page": active_page,
            "nav_items": NAV_ITEMS,
            "product_name": "SentinelAI",
            "footer_note": "Phase 9 local-first dashboard",
            **context,
        },
        status_code=status_code,
    )


def _page_error(
    request: Request,
    *,
    title: str,
    message: str,
    status_code: int,
):
    return _render_page(
        request,
        "error.html",
        active_page="error",
        status_code=status_code,
        title=title,
        message=message,
    )


def _json_not_found(message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=404)


@router.get("/health", name="dashboard_health")
async def health_check():
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse, name="dashboard_overview")
async def overview_page(request: Request):
    settings = _settings(request)
    overview = build_overview(settings)
    return _render_page(
        request,
        "index.html",
        active_page="overview",
        overview=overview,
    )


@router.get("/new-run", response_class=HTMLResponse, name="dashboard_new_run")
async def new_run_page(request: Request):
    settings = _settings(request)
    return _render_page(
        request,
        "new_run.html",
        active_page="new_run",
        defaults=dashboard_defaults(settings),
    )


@router.post("/run", name="dashboard_run_submit")
async def run_submit(
    request: Request,
    url: str = Form(...),
    instruction: str = Form(...),
    mode: str = Form(...),
    model: str = Form(""),
    max_retries: int | None = Form(None),
    memory_enabled: str | None = Form(None),
    mcp_enabled: str | None = Form(None),
):
    try:
        job = await _job_manager(request).submit(
            JobRequest(
                mode=mode,
                url=url.strip(),
                instruction=instruction.strip(),
                model=model.strip() or None,
                max_retries=max_retries,
                memory_enabled=memory_enabled is not None,
                mcp_enabled=mcp_enabled is not None,
            )
        )
    except ValueError as exc:
        return _page_error(
            request,
            title="Run Configuration Error",
            message=str(exc),
            status_code=400,
        )
    except Exception as exc:
        return _page_error(
            request,
            title="Execution Failed",
            message=f"{type(exc).__name__}: {exc}",
            status_code=500,
        )

    return RedirectResponse(
        url=request.url_for("dashboard_job_detail", job_id=job.job_id),
        status_code=303,
    )


@router.get("/runs", response_class=HTMLResponse, name="dashboard_runs")
async def runs_page(request: Request):
    settings = _settings(request)
    return _render_page(
        request,
        "runs.html",
        active_page="runs",
        runs=list_runs(settings),
        active_jobs=[
            job.to_dict()
            for job in await _job_manager(request).active_jobs()
        ],
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse, name="dashboard_job_detail")
async def job_detail_page(request: Request, job_id: str):
    job = await _job_manager(request).get(job_id)
    if job is None:
        return _page_error(
            request,
            title="Job Not Found",
            message="The requested job could not be found. In-process jobs reset when the app restarts.",
            status_code=404,
        )
    return _render_page(
        request,
        "job_detail.html",
        active_page="runs",
        job=job.to_dict(),
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse, name="dashboard_run_detail")
async def run_detail_page(request: Request, run_id: str):
    settings = _settings(request)
    detail = get_run_detail(settings, run_id)
    if detail is None:
        return _page_error(
            request,
            title="Run Not Found",
            message="The requested run could not be found or the run ID was invalid.",
            status_code=404,
        )
    return _render_page(
        request,
        "run_detail.html",
        active_page="runs",
        detail=detail,
    )


@router.get("/reports", response_class=HTMLResponse, name="dashboard_reports")
async def reports_page(request: Request):
    settings = _settings(request)
    return _render_page(
        request,
        "reports.html",
        active_page="reports",
        reports=list_reports(settings),
    )


@router.get("/memory", response_class=HTMLResponse, name="dashboard_memory")
async def memory_page(request: Request):
    settings = _settings(request)
    return _render_page(
        request,
        "memory.html",
        active_page="memory",
        memory_summary=build_memory_summary(settings),
    )


@router.get("/tools", response_class=HTMLResponse, name="dashboard_tools")
async def tools_page(request: Request):
    settings = _settings(request)
    return _render_page(
        request,
        "tools.html",
        active_page="tools",
        tools_summary=build_tools_summary(settings),
    )


@router.get("/metrics", response_class=HTMLResponse, name="dashboard_metrics")
async def metrics_page(request: Request):
    settings = _settings(request)
    return _render_page(
        request,
        "metrics.html",
        active_page="metrics",
        metrics_summary=build_metrics_summary(settings),
        job_metrics=await _job_manager(request).metrics(),
    )


@router.get("/settings", response_class=HTMLResponse, name="dashboard_settings")
async def settings_page(request: Request):
    settings = _settings(request)
    return _render_page(
        request,
        "settings.html",
        active_page="settings",
        settings_summary=build_settings_summary(settings),
    )


@router.get("/runs/{run_id}/report-html", response_class=HTMLResponse, name="dashboard_report_html")
async def report_html_page(request: Request, run_id: str):
    settings = _settings(request)
    run_dir = resolve_run_dir(settings.storage.runs_root, run_id)
    if run_dir is None:
        return _page_error(
            request,
            title="Report Not Found",
            message="The requested run could not be found or the run ID was invalid.",
            status_code=404,
        )
    report_html = run_dir / "reports" / "report.html"
    if not report_html.exists():
        return _page_error(
            request,
            title="Report Not Available",
            message="This run does not have an HTML report available.",
            status_code=404,
        )
    return HTMLResponse(report_html.read_text(encoding="utf-8"))


@router.get("/runs/{run_id}/screenshots/{file_name}", name="dashboard_run_screenshot")
async def run_screenshot(request: Request, run_id: str, file_name: str):
    settings = _settings(request)
    run_dir = resolve_run_dir(settings.storage.runs_root, run_id)
    if run_dir is None:
        return _json_not_found("Run not found.")
    if Path(file_name).name != file_name:
        return _json_not_found("Screenshot not found.")
    screenshot_path = (run_dir / "screenshots" / file_name).resolve()
    if not screenshot_path.exists() or not screenshot_path.is_file():
        return _json_not_found("Screenshot not found.")
    if not ensure_relative_to(run_dir, screenshot_path):
        return _json_not_found("Screenshot not found.")
    return FileResponse(screenshot_path)


@router.get("/api/runs", name="api_runs")
async def api_runs(request: Request):
    settings = _settings(request)
    return JSONResponse({"runs": list_runs(settings)})


@router.post("/api/jobs", name="api_create_job")
async def api_create_job(
    request: Request,
    payload: dict,
):
    try:
        mode_value = str(payload.get("mode", "phase6"))
        if mode_value not in SUPPORTED_MODES:
            raise ValueError(f"Unsupported execution mode '{mode_value}'.")
        job_request = JobRequest(
            mode=mode_value,
            url=str(payload.get("url", "")).strip(),
            instruction=str(payload.get("instruction", "")).strip(),
            model=str(payload["model"]).strip() if payload.get("model") else None,
            max_retries=int(payload["max_retries"]) if payload.get("max_retries") is not None else None,
            memory_enabled=coerce_bool(payload.get("memory_enabled", True)),
            mcp_enabled=coerce_bool(payload.get("mcp_enabled", True)),
        )
        if not job_request.url or not job_request.instruction:
            raise ValueError("Both url and instruction are required.")
        job = await _job_manager(request).submit(job_request)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"job": job.to_dict()}, status_code=202)


@router.get("/api/jobs", name="api_list_jobs")
async def api_list_jobs(request: Request):
    jobs = [job.to_dict() for job in await _job_manager(request).list_jobs()]
    return JSONResponse({"jobs": jobs})


@router.get("/api/jobs/active", name="api_active_jobs")
async def api_active_jobs(request: Request):
    jobs = [job.to_dict() for job in await _job_manager(request).active_jobs()]
    return JSONResponse({"jobs": jobs})


@router.get("/api/jobs/metrics", name="api_job_metrics")
async def api_job_metrics(request: Request):
    return JSONResponse(await _job_manager(request).metrics())


@router.get("/api/jobs/{job_id}", name="api_job_status")
async def api_job_status(request: Request, job_id: str):
    job = await _job_manager(request).get(job_id)
    if job is None:
        return _json_not_found("Job not found.")
    return JSONResponse({"job": job.to_dict()})


@router.post("/api/jobs/{job_id}/cancel", name="api_cancel_job")
async def api_cancel_job(request: Request, job_id: str):
    job = await _job_manager(request).cancel(job_id)
    if job is None:
        return _json_not_found("Job not found.")
    return JSONResponse({"job": job.to_dict()})


@router.get("/api/runs/{run_id}/report", name="api_run_report")
async def api_run_report(request: Request, run_id: str):
    settings = _settings(request)
    detail = get_run_detail(settings, run_id)
    if detail is None:
        return _json_not_found("Run not found.")
    return JSONResponse({"run_id": run_id, "report": detail["report"], "error": detail["report_error"]})


@router.get("/api/runs/{run_id}/graph-trace", name="api_run_graph_trace")
async def api_run_graph_trace(request: Request, run_id: str):
    settings = _settings(request)
    detail = get_run_detail(settings, run_id)
    if detail is None:
        return _json_not_found("Run not found.")
    return JSONResponse({"run_id": run_id, "graph_trace": detail["graph_trace"], "error": detail["graph_trace_error"]})


@router.get("/api/runs/{run_id}/planner-trace", name="api_run_planner_trace")
async def api_run_planner_trace(request: Request, run_id: str):
    settings = _settings(request)
    detail = get_run_detail(settings, run_id)
    if detail is None:
        return _json_not_found("Run not found.")
    return JSONResponse({"run_id": run_id, "planner_trace": detail["planner_trace"], "error": detail["planner_trace_error"]})


@router.get("/api/runs/{run_id}/tool-trace", name="api_run_tool_trace")
async def api_run_tool_trace(request: Request, run_id: str):
    settings = _settings(request)
    detail = get_run_detail(settings, run_id)
    if detail is None:
        return _json_not_found("Run not found.")
    return JSONResponse({"run_id": run_id, "tool_trace": detail["tool_trace"], "error": detail["tool_trace_error"]})


@router.get("/api/runs/{run_id}/metrics", name="api_run_metrics")
async def api_run_metrics(request: Request, run_id: str):
    settings = _settings(request)
    detail = get_run_detail(settings, run_id)
    if detail is None:
        return _json_not_found("Run not found.")
    return JSONResponse({"run_id": run_id, "metrics": detail["metrics"], "error": detail["metrics_error"]})


@router.get("/api/runs/{run_id}/screenshots", name="api_run_screenshots")
async def api_run_screenshots(request: Request, run_id: str):
    settings = _settings(request)
    screenshots = list_api_screenshots(settings, run_id)
    if screenshots is None:
        return _json_not_found("Run not found.")
    return JSONResponse(screenshots)


@router.get("/api/memory/summary", name="api_memory_summary")
async def api_memory_summary(request: Request):
    settings = _settings(request)
    return JSONResponse(build_memory_summary(settings))


@router.get("/api/tools/summary", name="api_tools_summary")
async def api_tools_summary(request: Request):
    settings = _settings(request)
    return JSONResponse(build_tools_summary(settings))


@router.get("/api/metrics/summary", name="api_metrics_summary")
async def api_metrics_summary(request: Request):
    settings = _settings(request)
    payload = build_metrics_summary(settings)
    payload["jobs"] = await _job_manager(request).metrics()
    return JSONResponse(payload)
