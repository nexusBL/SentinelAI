from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from browser.models import BrowserRunResult
from browser.playwright_runner import PlaywrightBrowserRunner
from config.settings import BrowserSettings
from mcp_servers.browser_server import BrowserMCPServer
from mcp_servers.memory_server import MemoryMCPServer
from mcp_servers.validation_server import ValidationMCPServer
from memory.memory_manager import MemoryManager

from .conftest import make_assertion
from .conftest import make_browser_result


class StubRunner(PlaywrightBrowserRunner):
    def __init__(self):
        super().__init__(
            BrowserSettings(
                headless=True,
                viewport_width=1280,
                viewport_height=720,
                navigation_timeout_ms=30000,
                wait_until="load",
                screenshot_full_page=True,
            )
        )

    async def capture_initial_state(self, url: str, run_artifacts):
        return make_browser_result(
            status="passed",
            requested_url=url,
            final_url=url,
            test_name="Phase1",
        )

    async def run_test_case(self, test_case, run_artifacts):
        return make_browser_result(
            status="passed",
            requested_url=test_case.resolved_target_url(),
            final_url=test_case.resolved_target_url(),
            test_name=test_case.name,
            test_file=str(test_case.source_path) if test_case.source_path else None,
        )


async def test_browser_server_returns_standardized_success_response(temp_settings, sample_test_case):
    from reporting.run_artifacts import RunArtifactManager

    manager = RunArtifactManager(temp_settings.storage)
    run_artifacts = manager.create_run(
        phase="phase2",
        target_url="https://example.com",
        instruction="Run testcase",
    )
    server = BrowserMCPServer(StubRunner(), timeout_seconds=5)

    response = await server.execute(
        "run_test_case",
        {"test_case": sample_test_case, "run_artifacts": run_artifacts},
    )

    assert response.status == "passed"
    assert response.duration_ms >= 0
    assert isinstance(response.result["execution_result"], BrowserRunResult)


async def test_browser_server_returns_error_response_for_invalid_payload():
    server = BrowserMCPServer(StubRunner(), timeout_seconds=5)

    response = await server.execute("run_test_case", {"test_case": "bad"})

    assert response.status == "failed"
    assert "TestCase" in str(response.error_message)


async def test_memory_server_success_and_stats(temp_settings):
    manager = MemoryManager(temp_settings.memory)
    server = MemoryMCPServer(manager, timeout_seconds=5)

    store_response = await server.execute(
        "store_execution",
        {
            "run_id": "run-1",
            "url": "https://example.com",
            "instruction": "Open homepage",
            "generated_test_plan": {"steps": [], "assertions": []},
            "execution_summary": {"status": "passed"},
            "failure_reason": None,
            "validation_status": "passed",
            "retry_count": 0,
            "final_result": "passed",
        },
    )
    stats_response = await server.execute("memory_stats", {})

    assert store_response.status == "passed"
    assert store_response.result["store_result"].status == "stored"
    assert stats_response.status == "passed"
    assert stats_response.result["vector_count"] == 1


async def test_validation_server_success_and_error_paths():
    server = ValidationMCPServer(timeout_seconds=5)
    passing_result = make_browser_result(status="passed", failure_reason=None)
    failing_result = make_browser_result(status="failed", failure_reason="Assertion failed")

    summary_response = await server.execute(
        "summarize_validation",
        {"execution_result": passing_result},
    )
    failure_response = await server.execute(
        "extract_failure_reason",
        {"execution_result": failing_result, "fallback_reason": "fallback"},
    )
    bad_response = await server.execute(
        "summarize_validation",
        {"execution_result": "bad"},
    )

    assert summary_response.status == "passed"
    assert summary_response.result["validation_passed"] is True
    assert failure_response.status == "passed"
    assert failure_response.result["failure_reason"] == "Assertion failed"
    assert bad_response.status == "failed"
