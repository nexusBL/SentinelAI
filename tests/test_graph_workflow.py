from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from agents.graph_workflow import LangGraphWorkflow
from agents.planner_agent import PlannerAgentResult
from agents.planner_agent import PlannerAttempt
from mcp_servers.models import MCPToolResponse
from memory.models import MemoryEntry
from memory.models import MemoryRetrieval
from memory.models import MemoryStoreResult
from memory.models import RetrievedMemory

from .conftest import make_browser_result


def make_planner_result(sample_test_case, logs_dir: Path, *, status: str = "passed"):
    logs_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = logs_dir / "planner_prompt.txt"
    plan_path = logs_dir / "final_test_plan.json"
    prompt_path.write_text("prompt", encoding="utf-8")
    plan_path.write_text("{}", encoding="utf-8")
    sample_test_case.source_path = plan_path
    raw_response_path = logs_dir / "planner_attempt_01_raw.txt"
    raw_response_path.write_text("{}", encoding="utf-8")
    return PlannerAgentResult(
        status=status,
        model="llama3",
        attempts=[
            PlannerAttempt(
                attempt_number=1,
                raw_response="{}",
                raw_response_path=raw_response_path,
            )
        ],
        prompt_path=prompt_path,
        final_plan_path=plan_path,
        test_case=sample_test_case if status == "passed" else None,
        final_plan=sample_test_case.to_dict() if status == "passed" else None,
        failure_reason=None if status == "passed" else "Planner failed",
    )


def make_memory_retrieval(*, result_count: int = 0) -> MemoryRetrieval:
    entries = []
    for index in range(result_count):
        entries.append(
            MemoryEntry(
                run_id=f"run-{index}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                url="https://example.com",
                instruction=f"Instruction {index}",
                generated_test_plan={"steps": [], "assertions": []},
                execution_summary={"status": "passed"},
                failure_reason=None,
                validation_status="passed",
                retry_count=0,
                final_result="passed",
            )
        )
    return MemoryRetrieval(
        status="passed",
        query_text="query",
        prompt_context="memory context" if result_count else None,
        results=[
            RetrievedMemory(rank=idx + 1, score=0.9 - idx * 0.1, entry=entry)
            for idx, entry in enumerate(entries)
        ],
        provider_name="hashing",
        model_name="hashing-384",
        top_k=3,
    )


def make_memory_store_result() -> MemoryStoreResult:
    return MemoryStoreResult(
        status="stored",
        entry=MemoryEntry(
            run_id="run-final",
            timestamp=datetime.now(timezone.utc).isoformat(),
            url="https://example.com",
            instruction="Instruction",
            generated_test_plan={"steps": [], "assertions": []},
            execution_summary={"status": "passed"},
            failure_reason=None,
            validation_status="passed",
            retry_count=0,
            final_result="passed",
        ),
        provider_name="hashing",
        model_name="hashing-384",
        vector_count=1,
    )


class FakeMemoryManager:
    def __init__(
        self,
        *,
        enabled: bool,
        retrieval_callback,
        store_callback,
        settings,
    ) -> None:
        self.enabled = enabled
        self._retrieval_callback = retrieval_callback
        self._store_callback = store_callback
        self.settings = settings

    def retrieve_similar(self, **kwargs):
        return self._retrieval_callback(**kwargs)

    def store_execution(self, **kwargs):
        return self._store_callback(**kwargs)

    def write_retrieval_artifact(self, *, output_path: Path, retrieval: MemoryRetrieval) -> Path:
        output_path.write_text(json.dumps(retrieval.to_dict(), indent=2), encoding="utf-8")
        return output_path

    def write_store_artifact(self, *, output_path: Path, store_result: MemoryStoreResult) -> Path:
        output_path.write_text(json.dumps(store_result.to_dict(), indent=2), encoding="utf-8")
        return output_path


async def test_graph_workflow_success_path(temp_settings, sample_test_case, tmp_path, monkeypatch):
    workflow = LangGraphWorkflow(temp_settings)
    call_order: list[str] = []

    def fake_retrieve(**kwargs):
        call_order.append("memory_retrieval")
        return make_memory_retrieval()

    def fake_plan(**kwargs):
        call_order.append("planner")
        return make_planner_result(sample_test_case, kwargs["logs_dir"])

    async def fake_run_test_case(**kwargs):
        call_order.append("executor")
        return make_browser_result(status="passed", test_name=sample_test_case.name)

    def fake_store(**kwargs):
        call_order.append("memory_store")
        return make_memory_store_result()

    original_write_json = workflow.artifact_manager.write_json_report

    def tracked_write_json(run_artifacts, payload):
        call_order.append("reporter")
        return original_write_json(run_artifacts, payload)

    workflow.memory_manager = FakeMemoryManager(
        enabled=True,
        retrieval_callback=fake_retrieve,
        store_callback=fake_store,
        settings=temp_settings.memory,
    )
    monkeypatch.setattr(workflow.planner, "plan", fake_plan)
    monkeypatch.setattr(workflow.runner, "run_test_case", fake_run_test_case)
    monkeypatch.setattr(workflow.artifact_manager, "write_json_report", tracked_write_json)

    result = await workflow.execute(
        url="https://example.com",
        instruction="Test homepage",
        max_retries=1,
        phase_name="phase5",
    )

    summary = result.to_summary()
    nodes = [event["node"] for event in result.final_state["graph_trace"] if event["node"] != "workflow"]

    assert summary["status"] == "passed"
    assert result.final_state["validation_passed"] is True
    assert call_order == ["memory_retrieval", "planner", "executor", "memory_store", "reporter"]
    assert nodes == ["memory_retrieval", "planner", "executor", "validator", "memory_store", "reporter"]


async def test_graph_workflow_retry_path(temp_settings, sample_test_case, tmp_path, monkeypatch):
    workflow = LangGraphWorkflow(temp_settings)
    execution_calls = {"count": 0}

    workflow.memory_manager = FakeMemoryManager(
        enabled=True,
        retrieval_callback=lambda **kwargs: make_memory_retrieval(),
        store_callback=lambda **kwargs: make_memory_store_result(),
        settings=temp_settings.memory,
    )
    monkeypatch.setattr(
        workflow.planner,
        "plan",
        lambda **kwargs: make_planner_result(sample_test_case, kwargs["logs_dir"]),
    )

    async def fake_run_test_case(**kwargs):
        execution_calls["count"] += 1
        if execution_calls["count"] == 1:
            return make_browser_result(
                status="failed",
                failure_reason="First attempt failed",
                test_name=sample_test_case.name,
            )
        return make_browser_result(status="passed", test_name=sample_test_case.name)

    monkeypatch.setattr(workflow.runner, "run_test_case", fake_run_test_case)

    result = await workflow.execute(
        url="https://example.com",
        instruction="Retry on failure",
        max_retries=1,
        phase_name="phase5",
    )

    assert result.final_state["retry_count"] == 1
    assert result.final_state["validation_passed"] is True
    assert len(result.final_state["instruction_history"]) == 2
    assert execution_calls["count"] == 2


async def test_graph_workflow_max_retry_stop(temp_settings, sample_test_case, tmp_path, monkeypatch):
    workflow = LangGraphWorkflow(temp_settings)

    workflow.memory_manager = FakeMemoryManager(
        enabled=True,
        retrieval_callback=lambda **kwargs: make_memory_retrieval(),
        store_callback=lambda **kwargs: make_memory_store_result(),
        settings=temp_settings.memory,
    )
    monkeypatch.setattr(
        workflow.planner,
        "plan",
        lambda **kwargs: make_planner_result(sample_test_case, kwargs["logs_dir"]),
    )

    async def always_fail_run_test_case(**kwargs):
        return make_browser_result(
            status="failed",
            failure_reason="Still failing",
            test_name=sample_test_case.name,
        )

    monkeypatch.setattr(workflow.runner, "run_test_case", always_fail_run_test_case)

    result = await workflow.execute(
        url="https://example.com",
        instruction="Stop after retries",
        max_retries=1,
        phase_name="phase5",
    )

    nodes = [event["node"] for event in result.final_state["graph_trace"] if event["node"] != "workflow"]
    assert result.final_state["retry_count"] == 1
    assert result.final_state["validation_passed"] is False
    assert nodes.count("replan") == 1
    assert result.to_summary()["status"] == "failed"


async def test_graph_workflow_memory_retrieval_happens_before_planning(temp_settings, sample_test_case, tmp_path, monkeypatch):
    workflow = LangGraphWorkflow(temp_settings)
    call_order: list[str] = []

    def fake_retrieve(**kwargs):
        call_order.append("memory_retrieval")
        return make_memory_retrieval(result_count=1)

    def fake_plan(**kwargs):
        call_order.append("planner")
        assert kwargs["memory_context"] == "memory context"
        return make_planner_result(sample_test_case, kwargs["logs_dir"])

    workflow.memory_manager = FakeMemoryManager(
        enabled=True,
        retrieval_callback=fake_retrieve,
        store_callback=lambda **kwargs: make_memory_store_result(),
        settings=temp_settings.memory,
    )
    monkeypatch.setattr(workflow.planner, "plan", fake_plan)

    async def passing_run_test_case(**kwargs):
        return make_browser_result(status="passed", test_name=sample_test_case.name)

    monkeypatch.setattr(workflow.runner, "run_test_case", passing_run_test_case)

    await workflow.execute(
        url="https://example.com",
        instruction="Use memory before plan",
        max_retries=0,
        phase_name="phase5",
    )

    assert call_order[:2] == ["memory_retrieval", "planner"]


async def test_graph_workflow_mcp_enabled_path(temp_settings, sample_test_case, tmp_path, monkeypatch):
    workflow = LangGraphWorkflow(temp_settings)

    monkeypatch.setattr(
        workflow.planner,
        "plan",
        lambda **kwargs: make_planner_result(sample_test_case, kwargs["logs_dir"]),
    )

    async def fake_execute(*, server_name, action, payload=None):
        payload = payload or {}
        if server_name == "memory" and action == "retrieve_similar":
            return MCPToolResponse(
                server_name=server_name,
                action=action,
                status="passed",
                started_at="now",
                completed_at="now",
                duration_ms=1,
                result={"retrieval": make_memory_retrieval(result_count=1)},
            )
        if server_name == "browser" and action == "run_test_case":
            return MCPToolResponse(
                server_name=server_name,
                action=action,
                status="passed",
                started_at="now",
                completed_at="now",
                duration_ms=2,
                result={"execution_result": make_browser_result(status="passed", test_name=sample_test_case.name)},
            )
        if server_name == "validation" and action == "summarize_validation":
            return MCPToolResponse(
                server_name=server_name,
                action=action,
                status="passed",
                started_at="now",
                completed_at="now",
                duration_ms=1,
                result={
                    "status": "passed",
                    "validation_passed": True,
                    "failure_reason": None,
                    "step_count": 1,
                    "assertion_count": 0,
                    "passed_steps": 1,
                    "passed_assertions": 0,
                },
            )
        if server_name == "memory" and action == "store_execution":
            return MCPToolResponse(
                server_name=server_name,
                action=action,
                status="passed",
                started_at="now",
                completed_at="now",
                duration_ms=1,
                result={"store_result": make_memory_store_result()},
            )
        raise AssertionError(f"Unexpected MCP call: {server_name}.{action}")

    monkeypatch.setattr(workflow.mcp_registry, "execute", fake_execute)

    result = await workflow.execute(
        url="https://example.com",
        instruction="Use MCP tool routing",
        max_retries=0,
        phase_name="phase6",
    )

    tool_names = [event["tool_name"] for event in result.final_state["tool_trace"]]
    assert result.final_state["mcp_enabled"] is True
    assert tool_names == ["memory", "browser", "validation", "memory"]
    assert result.final_state["metrics"]["tool_invocation_count"] == 4


async def test_graph_workflow_mcp_disabled_path(temp_settings, sample_test_case, tmp_path, monkeypatch):
    temp_settings.mcp.enabled = False
    workflow = LangGraphWorkflow(temp_settings)

    workflow.memory_manager = FakeMemoryManager(
        enabled=True,
        retrieval_callback=lambda **kwargs: make_memory_retrieval(),
        store_callback=lambda **kwargs: make_memory_store_result(),
        settings=temp_settings.memory,
    )
    monkeypatch.setattr(
        workflow.planner,
        "plan",
        lambda **kwargs: make_planner_result(sample_test_case, kwargs["logs_dir"]),
    )

    async def passing_run_test_case(**kwargs):
        return make_browser_result(status="passed", test_name=sample_test_case.name)

    monkeypatch.setattr(
        workflow.runner,
        "run_test_case",
        passing_run_test_case,
    )

    result = await workflow.execute(
        url="https://example.com",
        instruction="Do not use MCP",
        max_retries=0,
        phase_name="phase6",
    )

    assert result.final_state["mcp_enabled"] is False
    assert result.final_state["tool_trace"] == []
    assert result.final_state["metrics"]["tool_invocation_count"] == 0
