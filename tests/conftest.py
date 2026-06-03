from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from ai.ollama_client import OllamaGenerateResult
from browser.models import AssertionResult
from browser.models import BrowserRunResult
from browser.models import StepExecutionResult
from config.settings import load_settings
from sentinelai.test_case import TestAssertion
from sentinelai.test_case import build_test_case


class FakeLocator:
    def __init__(self, *, text: str = "", count: int = 0, html: str = "", value: str = "") -> None:
        self._text = text
        self._count = count
        self._html = html
        self._value = value

    async def inner_text(self) -> str:
        return self._text

    async def count(self) -> int:
        return self._count

    async def inner_html(self) -> str:
        return self._html or self._text

    async def input_value(self) -> str:
        return self._value


class FakePage:
    def __init__(
        self,
        *,
        url: str = "https://example.com/",
        title: str = "Example Domain",
        body_text: str = "Example Domain",
        selector_counts: dict[str, int] | None = None,
    ) -> None:
        self.url = url
        self._title = title
        self._body_text = body_text
        self._selector_counts = selector_counts or {}

    def locator(self, selector: str) -> FakeLocator:
        if selector == "body":
            return FakeLocator(text=self._body_text, count=1, html=self._body_text)
        return FakeLocator(
            text=f"text for {selector}",
            count=self._selector_counts.get(selector, 0),
            html=f"<div>{selector}</div>",
            value=f"value for {selector}",
        )

    async def title(self) -> str:
        return self._title


class FakeOllamaClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.settings = type("Settings", (), {"model": "llama3"})()

    def generate(self, *, prompt: str, system_prompt: str, model: str | None = None):
        response_text = self.responses.pop(0)
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "model": model or self.settings.model,
            }
        )
        return OllamaGenerateResult(
            model=model or self.settings.model,
            response_text=response_text,
            raw_payload={"response": response_text},
            prompt=prompt,
            system_prompt=system_prompt,
        )


@pytest.fixture
def temp_settings(tmp_path: Path):
    settings = load_settings(project_root=tmp_path)
    settings.storage.artifacts_root = tmp_path / "artifacts"
    settings.storage.runs_root = settings.storage.artifacts_root / "runs"
    settings.memory.enabled = True
    settings.memory.vector_db_path = tmp_path / "memory_store"
    settings.memory.embedding_provider = "hashing"
    settings.memory.embedding_model = "hashing-384"
    settings.memory.top_k = 3
    settings.mcp.enabled = True
    settings.mcp.tool_tracing_enabled = True
    settings.mcp.enabled_tools = ("browser", "memory", "validation")
    settings.auth.sqlite_path = tmp_path / "auth_store" / "sentinelai_auth.db"
    settings.auth.jwt_secret = "test-secret-key-for-sentinelai-auth-tests"
    settings.auth.secure_cookie = False
    settings.database.sqlite_path = tmp_path / "metadata_store" / "sentinelai_metadata.db"
    settings.database.url = f"sqlite:///{settings.database.sqlite_path.as_posix()}"
    return settings


@pytest.fixture
def sample_test_case():
    payload = {
        "steps": [
            {
                "action": "navigate",
                "value": "https://example.com",
                "description": "Open the homepage",
            }
        ],
        "assertions": [
            {
                "type": "title_contains",
                "value": "Example Domain",
                "description": "Title should contain Example Domain",
            }
        ],
    }
    return build_test_case(
        payload,
        name="Example Homepage Smoke Test",
        description="Example homepage check",
        target_url="https://example.com",
    )


@pytest.fixture
def make_dashboard_run(temp_settings):
    def _make(
        *,
        run_id: str = "20260520T120000000000Z",
        phase: str = "phase6",
        status: str = "passed",
        requested_url: str = "https://example.com",
        final_url: str = "https://example.com/",
        instruction: str = "Test homepage",
        page_title: str = "Example Domain",
        retry_count: int = 1,
        max_retries: int = 2,
        memory_hits: int = 1,
        mcp_enabled: bool = True,
        tool_invocation_count: int = 4,
        duration_ms: int = 1450,
        include_report_html: bool = True,
        include_graph_trace: bool = True,
        include_planner_trace: bool = True,
        include_tool_trace: bool = True,
        include_metrics: bool = True,
        include_screenshots: bool = True,
        include_memory_artifacts: bool = True,
        failure_reason: str | None = None,
        owner_user_id: str | None = None,
    ) -> Path:
        run_dir = temp_settings.storage.runs_root / run_id
        (run_dir / "reports").mkdir(parents=True, exist_ok=True)
        (run_dir / "metrics").mkdir(parents=True, exist_ok=True)
        (run_dir / "graph").mkdir(parents=True, exist_ok=True)
        (run_dir / "planner").mkdir(parents=True, exist_ok=True)
        (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
        (run_dir / "metadata").mkdir(parents=True, exist_ok=True)
        if owner_user_id:
            (run_dir / "metadata" / "owner.json").write_text(
                json.dumps(
                    {
                        "owner_user_id": owner_user_id,
                        "job_id": "test-job",
                        "created_by": "test",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        created_at = datetime.now(timezone.utc).isoformat()
        report_payload = {
            "run_id": run_id,
            "phase": phase,
            "status": status,
            "instruction": instruction,
            "requested_url": requested_url,
            "final_url": final_url,
            "page_title": page_title,
            "failure_reason": failure_reason,
            "created_at": created_at,
            "summary": {
                "total_steps": 3,
                "passed_steps": 3 if status == "passed" else 2,
                "total_assertions": 2,
                "passed_assertions": 2 if status == "passed" else 1,
            },
            "artifacts": {
                "started_at": created_at,
                "completed_at": created_at,
                "before_screenshot_path": str(run_dir / "screenshots" / "01_before.png"),
                "after_screenshot_path": str(run_dir / "screenshots" / "02_after.png"),
            },
            "workflow": {
                "retry_count": retry_count,
                "max_retries": max_retries,
                "memory_hits": memory_hits,
                "mcp_enabled": mcp_enabled,
                "tool_invocation_count": tool_invocation_count,
            },
        }
        (run_dir / "reports" / "report.json").write_text(
            json.dumps(report_payload, indent=2),
            encoding="utf-8",
        )
        if include_report_html:
            (run_dir / "reports" / "report.html").write_text(
                (
                    "<html><body><h1>SentinelAI Report</h1>"
                    f"<p>{run_id}</p></body></html>"
                ),
                encoding="utf-8",
            )

        if include_metrics:
            metrics_payload = {
                "total_workflow_duration_ms": duration_ms,
                "retry_count": retry_count,
                "max_retries": max_retries,
                "memory_hits": memory_hits,
                "mcp_enabled": mcp_enabled,
                "tool_invocation_count": tool_invocation_count,
            }
            (run_dir / "metrics" / "execution_metrics.json").write_text(
                json.dumps(metrics_payload, indent=2),
                encoding="utf-8",
            )

        if include_graph_trace:
            (run_dir / "graph" / "graph_trace.json").write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "events": [
                            {"node": "planner", "status": "passed"},
                            {"node": "executor", "status": status},
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        if include_planner_trace:
            (run_dir / "planner" / "planner_trace.json").write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "planner_cycles": [{"cycle": 0, "status": "passed"}],
                        "planner_attempts": [{"attempt_number": 1, "status": "passed"}],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        if include_tool_trace:
            (run_dir / "graph" / "tool_trace.json").write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "events": [
                            {
                                "tool_name": "memory",
                                "action": "retrieve_similar",
                                "status": "passed",
                                "duration_ms": 3,
                                "graph_node": "memory_retrieval",
                            },
                            {
                                "tool_name": "browser",
                                "action": "run_test_case",
                                "status": "passed",
                                "duration_ms": 12,
                                "graph_node": "executor",
                            },
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        if include_screenshots:
            (run_dir / "screenshots" / "01_before.png").write_bytes(b"fake-image-before")
            (run_dir / "screenshots" / "02_after.png").write_bytes(b"fake-image-after")

        if include_memory_artifacts:
            (run_dir / "planner" / "cycle_00_memory_retrieval.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "top_k": 3,
                        "prompt_context": "Use the prior successful selector strategy.",
                        "results": [{"rank": 1, "score": 0.91}],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (run_dir / "logs" / "stored_memory_entry.json").write_text(
                json.dumps(
                    {
                        "status": "stored",
                        "entry": {
                            "instruction": instruction,
                            "final_result": status,
                            "validation_status": status,
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            temp_settings.memory.vector_db_path.mkdir(parents=True, exist_ok=True)
            (temp_settings.memory.vector_db_path / "manifest.json").write_text(
                json.dumps({"vector_count": 1}, indent=2),
                encoding="utf-8",
            )

        return run_dir

    return _make


def make_browser_result(
    *,
    status: str = "passed",
    failure_reason: str | None = None,
    requested_url: str = "https://example.com",
    final_url: str | None = "https://example.com/",
    page_title: str | None = "Example Domain",
    test_name: str = "Example Homepage Smoke Test",
    test_file: str | None = None,
    step_count: int = 1,
    assertion_results: list[AssertionResult] | None = None,
) -> BrowserRunResult:
    started_at = datetime.now(timezone.utc)
    steps = [
        StepExecutionResult(
            index=index,
            action="navigate",
            description=f"Step {index}",
            selector=None,
            value=requested_url,
            status="passed",
            started_at=started_at,
            completed_at=started_at,
            page_url=final_url,
        )
        for index in range(1, step_count + 1)
    ]
    assertions = list(assertion_results or [])
    return BrowserRunResult(
        requested_url=requested_url,
        final_url=final_url,
        page_title=page_title,
        navigation_status=200,
        started_at=started_at,
        completed_at=started_at,
        status=status,
        before_screenshot_path=None,
        after_screenshot_path=None,
        dom_snapshot_path=None,
        failure_reason=failure_reason,
        error_message=failure_reason,
        steps_executed=steps,
        assertion_results=assertions,
        test_name=test_name,
        test_file=test_file,
    )


def make_assertion(
    *,
    assertion_type: str,
    value: str | None = None,
    selector: str | None = None,
    description: str = "assertion",
) -> TestAssertion:
    return TestAssertion(
        assertion_type=assertion_type,
        description=description,
        value=value,
        selector=selector,
    )
