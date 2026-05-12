from __future__ import annotations

import json

from agents.planner_agent import PlannerAgentResult
from agents.planner_agent import PlannerAttempt
from reporting.run_artifacts import RunArtifactManager

from .conftest import make_browser_result


def test_reporting_writes_json_html_and_trace_files(temp_settings, sample_test_case):
    manager = RunArtifactManager(temp_settings.storage)
    run_artifacts = manager.create_run(
        phase="phase6",
        target_url="https://example.com",
        instruction="Run reporting test",
    )
    result = make_browser_result(
        status="passed",
        test_name=sample_test_case.name,
        test_file=str(run_artifacts.logs_dir / "final_test_plan.json"),
    )
    planner_result = PlannerAgentResult(
        status="passed",
        model="llama3",
        attempts=[
            PlannerAttempt(
                attempt_number=1,
                raw_response="{}",
                raw_response_path=run_artifacts.logs_dir / "planner_attempt_01_raw.txt",
            )
        ],
        prompt_path=run_artifacts.logs_dir / "planner_prompt.txt",
        final_plan_path=run_artifacts.logs_dir / "final_test_plan.json",
        final_plan=sample_test_case.to_dict(),
        test_case=sample_test_case,
    )
    workflow = {
        "validation_passed": True,
        "retry_count": 0,
        "max_retries": 1,
        "failure_reason": None,
        "instruction_history": [],
        "planner_attempt_count": 1,
        "memory_enabled": True,
        "memory_hits": 1,
        "retrieval_count": 1,
        "similarity_scores": [0.91],
        "memory_store_status": "stored",
        "memory_bootstrap_error": None,
        "mcp_enabled": True,
        "enabled_tools": ["browser", "memory", "validation"],
        "tool_tracing_enabled": True,
        "tool_invocation_count": 4,
        "tool_failure_count": 0,
        "tool_average_duration_ms": 12.5,
        "mcp_bootstrap_error": None,
        "graph_trace_path": str(run_artifacts.graph_dir / "graph_trace.json"),
        "tool_trace_path": str(run_artifacts.graph_dir / "tool_trace.json"),
        "planner_trace_path": str(run_artifacts.planner_dir / "planner_trace.json"),
        "metrics_path": str(run_artifacts.metrics_dir / "execution_metrics.json"),
    }

    payload = manager.build_phase4_payload(
        run_artifacts=run_artifacts,
        result=result,
        planner_result=planner_result,
        workflow=workflow,
    )
    graph_path = manager.write_graph_trace(run_artifacts, {"events": ["graph"]})
    tool_path = manager.write_tool_trace(run_artifacts, {"events": ["tool"]})
    metrics_path = manager.write_execution_metrics(run_artifacts, {"status": "passed"})
    json_path = manager.write_json_report(run_artifacts, payload)
    html_path = manager.write_html_report(run_artifacts, payload)

    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "passed"
    assert "SentinelAI" in html_path.read_text(encoding="utf-8")
    assert json.loads(graph_path.read_text(encoding="utf-8"))["events"] == ["graph"]
    assert json.loads(tool_path.read_text(encoding="utf-8"))["events"] == ["tool"]
    assert json.loads(metrics_path.read_text(encoding="utf-8"))["status"] == "passed"
