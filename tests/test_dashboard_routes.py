from __future__ import annotations

from fastapi.testclient import TestClient

from dashboard.app import app as module_app
from dashboard.app import create_app
from jobs.models import JobRecord
from jobs.models import JobRequest


def build_client(temp_settings) -> TestClient:
    return TestClient(create_app(temp_settings))


def test_dashboard_app_imports_and_routes_exist(temp_settings):
    client = build_client(temp_settings)

    assert module_app is not None
    assert client.app is not None
    assert any(route.path == "/" for route in client.app.router.routes)
    assert any(route.path == "/api/runs" for route in client.app.router.routes)


def test_dashboard_pages_render_empty_states(temp_settings):
    client = build_client(temp_settings)

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}

    for path in ("/", "/new-run", "/runs", "/reports", "/memory", "/tools", "/metrics", "/settings"):
        response = client.get(path)
        assert response.status_code == 200
        assert "SentinelAI" in response.text

    for path in ("/api/runs", "/api/memory/summary", "/api/tools/summary", "/api/metrics/summary"):
        response = client.get(path)
        assert response.status_code == 200


def test_dashboard_run_routes_and_apis_handle_sample_artifacts(temp_settings, make_dashboard_run):
    run_id = "20260520T123000000000Z"
    make_dashboard_run(run_id=run_id)
    client = build_client(temp_settings)

    detail_response = client.get(f"/runs/{run_id}")
    report_response = client.get(f"/api/runs/{run_id}/report")
    graph_response = client.get(f"/api/runs/{run_id}/graph-trace")
    planner_response = client.get(f"/api/runs/{run_id}/planner-trace")
    tool_response = client.get(f"/api/runs/{run_id}/tool-trace")
    metrics_response = client.get(f"/api/runs/{run_id}/metrics")
    screenshots_response = client.get(f"/api/runs/{run_id}/screenshots")
    memory_summary_response = client.get("/api/memory/summary")
    tools_summary_response = client.get("/api/tools/summary")
    metrics_summary_response = client.get("/api/metrics/summary")
    html_response = client.get(f"/runs/{run_id}/report-html")
    image_response = client.get(f"/runs/{run_id}/screenshots/01_before.png")

    assert detail_response.status_code == 200
    assert run_id in detail_response.text
    assert report_response.status_code == 200
    assert report_response.json()["report"]["run_id"] == run_id
    assert graph_response.status_code == 200
    assert planner_response.status_code == 200
    assert tool_response.status_code == 200
    assert metrics_response.status_code == 200
    assert screenshots_response.status_code == 200
    assert len(screenshots_response.json()["screenshots"]) == 2
    assert memory_summary_response.status_code == 200
    assert tools_summary_response.status_code == 200
    assert metrics_summary_response.status_code == 200
    assert html_response.status_code == 200
    assert "SentinelAI Report" in html_response.text
    assert image_response.status_code == 200


def test_dashboard_invalid_run_ids_return_safe_errors(temp_settings):
    client = build_client(temp_settings)

    detail_response = client.get("/runs/not-a-valid-run-id")
    report_response = client.get("/api/runs/not-a-valid-run-id/report")
    html_response = client.get("/runs/not-a-valid-run-id/report-html")

    assert detail_response.status_code == 404
    assert "could not be found" in detail_response.text
    assert report_response.status_code == 404
    assert report_response.json()["error"] == "Run not found."
    assert html_response.status_code == 404


def test_dashboard_screenshot_route_rejects_path_traversal(temp_settings, make_dashboard_run):
    run_id = "20260520T124000000000Z"
    make_dashboard_run(run_id=run_id)
    client = build_client(temp_settings)

    response = client.get(f"/runs/{run_id}/screenshots/..%5Csecret.png")

    assert response.status_code == 404
    assert response.json()["error"] == "Screenshot not found."


def test_dashboard_job_page_and_apis_work(temp_settings, monkeypatch):
    client = build_client(temp_settings)
    job = JobRecord(
        request=JobRequest(
            mode="phase6",
            url="https://example.com",
            instruction="Test homepage",
        ),
        job_id="job-123",
        status="queued",
        progress={"message": "Queued for execution", "stage": "queued", "percent": 0},
    )

    class FakeManager:
        async def submit(self, request):
            assert request.mode == "phase6"
            return job

        async def get(self, job_id):
            return job if job_id == job.job_id else None

        async def list_jobs(self):
            return [job]

        async def active_jobs(self):
            return [job]

        async def cancel(self, job_id):
            job.status = "cancelled"
            return job

        async def metrics(self):
            return {
                "total_jobs": 1,
                "queued_jobs": 1,
                "running_jobs": 0,
                "completed_jobs": 0,
                "failed_jobs": 0,
                "cancelled_jobs": 0,
                "queue_length": 1,
                "average_execution_ms": 0,
                "worker_running": True,
            }

    monkeypatch.setattr("dashboard.routes._job_manager", lambda request: FakeManager())

    response = client.post(
        "/run",
        data={
            "url": "https://example.com",
            "instruction": "Test homepage",
            "mode": "phase6",
            "model": "llama3",
            "max_retries": "2",
            "memory_enabled": "on",
            "mcp_enabled": "on",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/jobs/{job.job_id}")

    page_response = client.get(f"/jobs/{job.job_id}")
    status_response = client.get(f"/api/jobs/{job.job_id}")
    list_response = client.get("/api/jobs")
    active_response = client.get("/api/jobs/active")
    metrics_response = client.get("/api/jobs/metrics")
    cancel_response = client.post(f"/api/jobs/{job.job_id}/cancel")

    assert page_response.status_code == 200
    assert "Job Status" in page_response.text
    assert status_response.status_code == 200
    assert status_response.json()["job"]["job_id"] == job.job_id
    assert list_response.status_code == 200
    assert active_response.status_code == 200
    assert metrics_response.status_code == 200
    assert cancel_response.status_code == 200


def test_dashboard_run_submit_returns_friendly_error_page(temp_settings, monkeypatch):
    client = build_client(temp_settings)

    class FakeManager:
        async def submit(self, request):
            raise RuntimeError("boom")

    monkeypatch.setattr("dashboard.routes._job_manager", lambda request: FakeManager())

    response = client.post(
        "/run",
        data={
            "url": "https://example.com",
            "instruction": "Test homepage",
            "mode": "phase6",
            "model": "llama3",
            "max_retries": "1",
        },
    )

    assert response.status_code == 500
    assert "Execution Failed" in response.text
