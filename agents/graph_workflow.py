from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, TypedDict, cast

from langgraph.graph import END
from langgraph.graph import START
from langgraph.graph import StateGraph

from agents.planner_agent import PlannerAgent
from agents.planner_agent import PlannerAgentResult
from ai.ollama_client import OllamaClient
from browser.models import BrowserRunResult
from browser.playwright_runner import PlaywrightBrowserRunner
from config.settings import AppSettings
from reporting.run_artifacts import RunArtifactManager
from reporting.run_artifacts import RunArtifacts
from sentinelai.logging_utils import bind_logger
from sentinelai.logging_utils import get_logger
from sentinelai.logging_utils import log_event
from sentinelai.test_case import TestCase


class GraphWorkflowState(TypedDict, total=False):
    run_id: str
    url: str
    instruction: str
    current_instruction: str
    model: str | None
    test_plan: dict[str, Any] | None
    test_case: TestCase | None
    planner_result: PlannerAgentResult | None
    execution_result: BrowserRunResult | None
    validation_result: dict[str, Any]
    validation_passed: bool
    retry_count: int
    max_retries: int
    failure_reason: str | None
    planner_attempts: list[dict[str, Any]]
    planner_cycles: list[dict[str, Any]]
    artifacts_dir: str
    graph_trace: list[dict[str, Any]]
    instruction_history: list[dict[str, Any]]
    metrics: dict[str, Any]
    run_artifacts: RunArtifacts
    report_payload: dict[str, Any]
    report_paths: dict[str, str]
    workflow_started_at: str
    workflow_started_monotonic: float


@dataclass(slots=True)
class GraphWorkflowResult:
    final_state: GraphWorkflowState

    def to_summary(self) -> dict[str, Any]:
        execution_result = self.final_state.get("execution_result")
        report_paths = self.final_state.get("report_paths", {})
        planner_result = self.final_state.get("planner_result")
        return {
            "status": execution_result.status if execution_result else "failed",
            "run_id": self.final_state.get("run_id"),
            "test_name": execution_result.test_name if execution_result else None,
            "requested_url": execution_result.requested_url if execution_result else None,
            "final_url": execution_result.final_url if execution_result else None,
            "json_report": report_paths.get("json_report"),
            "html_report": report_paths.get("html_report"),
            "run_directory": self.final_state.get("artifacts_dir"),
            "failure_reason": self.final_state.get("failure_reason"),
            "validation_passed": self.final_state.get("validation_passed"),
            "retry_count": self.final_state.get("retry_count"),
            "max_retries": self.final_state.get("max_retries"),
            "planner_status": planner_result.status if planner_result else None,
            "planner_model": planner_result.model if planner_result else None,
            "graph_trace": report_paths.get("graph_trace"),
            "metrics": report_paths.get("metrics"),
        }


class LangGraphWorkflow:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.artifact_manager = RunArtifactManager(settings.storage)
        self.planner = PlannerAgent(
            ollama_client=OllamaClient(settings.ollama),
            max_attempts=settings.ollama.max_attempts,
        )
        self.runner = PlaywrightBrowserRunner(settings.browser)
        self.logger = get_logger("graph_workflow", phase="phase4")
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(GraphWorkflowState)
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("executor", self._executor_node)
        workflow.add_node("validator", self._validator_node)
        workflow.add_node("replan", self._replan_node)
        workflow.add_node("reporter", self._reporter_node)

        workflow.add_edge(START, "planner")
        workflow.add_conditional_edges("planner", self._route_after_planner)
        workflow.add_edge("executor", "validator")
        workflow.add_conditional_edges("validator", self._route_after_validation)
        workflow.add_edge("replan", "planner")
        workflow.add_edge("reporter", END)
        return workflow.compile()

    async def execute(
        self,
        *,
        url: str,
        instruction: str,
        model: str | None = None,
        max_retries: int | None = None,
    ) -> GraphWorkflowResult:
        run_artifacts = self.artifact_manager.create_run(
            phase="phase4",
            target_url=url,
            instruction=instruction,
        )
        workflow_started_at = self._timestamp()
        workflow_started_monotonic = perf_counter()
        initial_trace = [
            self._trace_event(
                node="workflow",
                event="started",
                retry_count=0,
                details={
                    "url": url,
                    "instruction": instruction,
                    "model": model or self.settings.ollama.model,
                },
            )
        ]
        initial_state: GraphWorkflowState = {
            "run_id": run_artifacts.context.run_id,
            "url": url,
            "instruction": instruction,
            "current_instruction": instruction,
            "model": model,
            "test_plan": None,
            "test_case": None,
            "planner_result": None,
            "execution_result": None,
            "validation_result": {},
            "validation_passed": False,
            "retry_count": 0,
            "max_retries": max(0, max_retries if max_retries is not None else self.settings.graph.max_retries),
            "failure_reason": None,
            "planner_attempts": [],
            "planner_cycles": [],
            "artifacts_dir": str(run_artifacts.run_dir),
            "graph_trace": initial_trace,
            "instruction_history": [
                {
                    "retry_count": 0,
                    "instruction": instruction,
                    "reason": None,
                }
            ],
            "metrics": {
                "status": "running",
                "retry_count": 0,
                "max_retries": max(
                    0,
                    max_retries if max_retries is not None else self.settings.graph.max_retries,
                ),
                "planner_duration_ms": 0,
                "execution_duration_ms": 0,
                "validation_duration_ms": 0,
                "replan_duration_ms": 0,
                "reporter_duration_ms": 0,
                "total_workflow_duration_ms": 0,
                "node_timings_ms": {
                    "planner": [],
                    "executor": [],
                    "validator": [],
                    "replan": [],
                    "reporter": [],
                },
            },
            "run_artifacts": run_artifacts,
            "report_payload": {},
            "report_paths": {},
            "workflow_started_at": workflow_started_at,
            "workflow_started_monotonic": workflow_started_monotonic,
        }
        self._persist_observability(initial_state)
        final_state = cast(GraphWorkflowState, await self.graph.ainvoke(initial_state))
        return GraphWorkflowResult(final_state=final_state)

    async def _planner_node(self, state: GraphWorkflowState) -> GraphWorkflowState:
        cycle = state.get("retry_count", 0)
        node_start = perf_counter()
        logger = bind_logger(self.logger, run_id=state.get("run_id"), graph_node="planner")
        log_event(
            logger,
            "planner_started",
            retry_count=cycle,
            instruction=state.get("current_instruction"),
        )

        run_artifacts = state["run_artifacts"]
        planner_logs_dir = run_artifacts.planner_dir / f"cycle_{cycle:02d}"
        planner_logs_dir.mkdir(parents=True, exist_ok=True)

        planner_result = self.planner.plan(
            url=state["url"],
            instruction=state["current_instruction"],
            logs_dir=planner_logs_dir,
            model=state.get("model"),
        )
        duration_ms = self._elapsed_ms(node_start)
        planner_attempts = state.get("planner_attempts", []) + [
            {
                "cycle": cycle,
                **attempt.to_dict(),
            }
            for attempt in planner_result.attempts
        ]
        planner_cycles = state.get("planner_cycles", []) + [
            {
                "cycle": cycle,
                "instruction": state.get("current_instruction"),
                **planner_result.to_dict(),
            }
        ]
        next_node = self._planner_route(
            planner_result=planner_result,
            retry_count=cycle,
            max_retries=state["max_retries"],
        )
        graph_trace = self._with_trace(
            state,
            node="planner",
            event="completed",
            retry_count=cycle,
            duration_ms=duration_ms,
            status=planner_result.status,
            next_node=next_node,
            failure_reason=planner_result.failure_reason,
            attempt_count=len(planner_result.attempts),
        )
        metrics = self._record_metric(state, "planner", duration_ms)

        updates: GraphWorkflowState = {
            "planner_result": planner_result,
            "test_plan": planner_result.final_plan,
            "test_case": planner_result.test_case,
            "failure_reason": planner_result.failure_reason,
            "planner_attempts": planner_attempts,
            "planner_cycles": planner_cycles,
            "graph_trace": graph_trace,
            "metrics": metrics,
        }
        self._persist_observability(self._merged_state(state, updates))
        log_event(
            logger,
            "planner_completed",
            retry_count=cycle,
            duration_ms=duration_ms,
            status=planner_result.status,
            next_node=next_node,
        )
        return updates

    async def _executor_node(self, state: GraphWorkflowState) -> GraphWorkflowState:
        node_start = perf_counter()
        retry_count = state.get("retry_count", 0)
        logger = bind_logger(self.logger, run_id=state.get("run_id"), graph_node="executor")
        log_event(logger, "executor_started", retry_count=retry_count)

        test_case = state.get("test_case")
        if test_case is None:
            duration_ms = self._elapsed_ms(node_start)
            failure_reason = "Executor received no test case from the planner."
            graph_trace = self._with_trace(
                state,
                node="executor",
                event="completed",
                retry_count=retry_count,
                duration_ms=duration_ms,
                status="failed",
                next_node="validator",
                failure_reason=failure_reason,
            )
            metrics = self._record_metric(state, "executor", duration_ms)
            updates: GraphWorkflowState = {
                "execution_result": None,
                "failure_reason": failure_reason,
                "graph_trace": graph_trace,
                "metrics": metrics,
            }
            self._persist_observability(self._merged_state(state, updates))
            log_event(
                logger,
                "executor_completed",
                retry_count=retry_count,
                duration_ms=duration_ms,
                status="failed",
            )
            return updates

        execution_result = await self.runner.run_test_case(
            test_case=test_case,
            run_artifacts=state["run_artifacts"],
        )
        duration_ms = self._elapsed_ms(node_start)
        graph_trace = self._with_trace(
            state,
            node="executor",
            event="completed",
            retry_count=retry_count,
            duration_ms=duration_ms,
            status=execution_result.status,
            next_node="validator",
            failure_reason=execution_result.failure_reason,
        )
        metrics = self._record_metric(state, "executor", duration_ms)
        updates = {
            "execution_result": execution_result,
            "failure_reason": execution_result.failure_reason,
            "graph_trace": graph_trace,
            "metrics": metrics,
        }
        self._persist_observability(self._merged_state(state, updates))
        log_event(
            logger,
            "executor_completed",
            retry_count=retry_count,
            duration_ms=duration_ms,
            status=execution_result.status,
        )
        return updates

    async def _validator_node(self, state: GraphWorkflowState) -> GraphWorkflowState:
        node_start = perf_counter()
        retry_count = state.get("retry_count", 0)
        logger = bind_logger(self.logger, run_id=state.get("run_id"), graph_node="validator")
        log_event(logger, "validator_started", retry_count=retry_count)

        execution_result = state.get("execution_result")
        validation_passed = bool(execution_result and execution_result.status == "passed")
        failure_reason = None if validation_passed else (
            execution_result.failure_reason
            if execution_result is not None
            else state.get("failure_reason") or "Validation failed without an execution result."
        )
        validation_result = {
            "status": "passed" if validation_passed else "failed",
            "failure_reason": failure_reason,
            "step_count": len(execution_result.steps_executed) if execution_result else 0,
            "assertion_count": len(execution_result.assertion_results) if execution_result else 0,
        }
        duration_ms = self._elapsed_ms(node_start)
        next_node = self._validation_route(
            validation_passed=validation_passed,
            retry_count=retry_count,
            max_retries=state["max_retries"],
        )
        graph_trace = self._with_trace(
            state,
            node="validator",
            event="completed",
            retry_count=retry_count,
            duration_ms=duration_ms,
            status=validation_result["status"],
            next_node=next_node,
            failure_reason=failure_reason,
        )
        metrics = self._record_metric(state, "validator", duration_ms)
        updates = {
            "validation_result": validation_result,
            "validation_passed": validation_passed,
            "failure_reason": failure_reason,
            "graph_trace": graph_trace,
            "metrics": metrics,
        }
        self._persist_observability(self._merged_state(state, updates))
        log_event(
            logger,
            "validator_completed",
            retry_count=retry_count,
            duration_ms=duration_ms,
            status=validation_result["status"],
            next_node=next_node,
        )
        return updates

    async def _replan_node(self, state: GraphWorkflowState) -> GraphWorkflowState:
        node_start = perf_counter()
        next_retry_count = state.get("retry_count", 0) + 1
        logger = bind_logger(self.logger, run_id=state.get("run_id"), graph_node="replan")
        failure_reason = state.get("failure_reason") or "Unknown validation failure."
        log_event(
            logger,
            "replan_started",
            retry_count=next_retry_count,
            failure_reason=failure_reason,
        )

        revised_instruction = self._build_retry_instruction(
            base_instruction=state["instruction"],
            failure_reason=failure_reason,
            retry_count=next_retry_count,
        )
        instruction_history = state.get("instruction_history", []) + [
            {
                "retry_count": next_retry_count,
                "instruction": revised_instruction,
                "reason": failure_reason,
            }
        ]
        duration_ms = self._elapsed_ms(node_start)
        graph_trace = self._with_trace(
            state,
            node="replan",
            event="completed",
            retry_count=next_retry_count,
            duration_ms=duration_ms,
            status="passed",
            next_node="planner",
            failure_reason=failure_reason,
        )
        metrics = self._record_metric(state, "replan", duration_ms)
        updates = {
            "current_instruction": revised_instruction,
            "retry_count": next_retry_count,
            "instruction_history": instruction_history,
            "graph_trace": graph_trace,
            "metrics": metrics,
        }
        self._persist_observability(self._merged_state(state, updates))
        log_event(
            logger,
            "replan_completed",
            retry_count=next_retry_count,
            duration_ms=duration_ms,
        )
        return updates

    async def _reporter_node(self, state: GraphWorkflowState) -> GraphWorkflowState:
        node_start = perf_counter()
        retry_count = state.get("retry_count", 0)
        logger = bind_logger(self.logger, run_id=state.get("run_id"), graph_node="reporter")
        log_event(logger, "reporter_started", retry_count=retry_count)

        execution_result = state.get("execution_result") or self._fallback_result(state)
        planner_result = state.get("planner_result")
        if planner_result and planner_result.test_case is not None:
            execution_result.test_name = planner_result.test_case.name
            if planner_result.final_plan_path is not None:
                execution_result.test_file = str(planner_result.final_plan_path)

        reporter_duration_ms = self._elapsed_ms(node_start)
        graph_trace = self._with_trace(
            state,
            node="reporter",
            event="completed",
            retry_count=retry_count,
            duration_ms=reporter_duration_ms,
            status=execution_result.status,
            failure_reason=state.get("failure_reason"),
        )
        metrics = self._record_metric(state, "reporter", reporter_duration_ms)
        metrics["status"] = execution_result.status
        metrics["retry_count"] = retry_count
        metrics["max_retries"] = state["max_retries"]
        metrics["total_workflow_duration_ms"] = self._elapsed_ms(
            state["workflow_started_monotonic"]
        )

        merged_state = self._merged_state(
            state,
            {
                "execution_result": execution_result,
                "graph_trace": graph_trace,
                "metrics": metrics,
            },
        )

        graph_trace_path = self.artifact_manager.write_graph_trace(
            run_artifacts=state["run_artifacts"],
            payload={
                "run_id": state["run_id"],
                "status": execution_result.status,
                "retry_count": retry_count,
                "max_retries": state["max_retries"],
                "events": graph_trace,
            },
        )
        planner_trace_path = self.artifact_manager.write_planner_trace(
            run_artifacts=state["run_artifacts"],
            payload={
                "run_id": state["run_id"],
                "status": planner_result.status if planner_result else "failed",
                "planner_cycles": state.get("planner_cycles", []),
                "planner_attempts": state.get("planner_attempts", []),
            },
        )
        metrics_path = self.artifact_manager.write_execution_metrics(
            run_artifacts=state["run_artifacts"],
            payload=metrics,
        )

        workflow_payload = {
            "validation_passed": merged_state.get("validation_passed"),
            "retry_count": retry_count,
            "max_retries": state["max_retries"],
            "failure_reason": merged_state.get("failure_reason"),
            "instruction_history": merged_state.get("instruction_history", []),
            "planner_attempt_count": len(merged_state.get("planner_attempts", [])),
            "graph_trace_path": str(graph_trace_path),
            "planner_trace_path": str(planner_trace_path),
            "metrics_path": str(metrics_path),
        }
        report_payload = self.artifact_manager.build_phase4_payload(
            run_artifacts=state["run_artifacts"],
            result=execution_result,
            planner_result=planner_result,
            workflow=workflow_payload,
        )
        json_report_path = self.artifact_manager.write_json_report(
            run_artifacts=state["run_artifacts"],
            payload=report_payload,
        )
        html_report_path = self.artifact_manager.write_html_report(
            run_artifacts=state["run_artifacts"],
            payload=report_payload,
        )

        report_paths = {
            "json_report": str(json_report_path),
            "html_report": str(html_report_path),
            "graph_trace": str(graph_trace_path),
            "planner_trace": str(planner_trace_path),
            "metrics": str(metrics_path),
        }
        final_updates: GraphWorkflowState = {
            "execution_result": execution_result,
            "graph_trace": graph_trace,
            "metrics": metrics,
            "report_payload": report_payload,
            "report_paths": report_paths,
        }
        self._persist_observability(self._merged_state(merged_state, final_updates))
        log_event(
            logger,
            "reporter_completed",
            retry_count=retry_count,
            duration_ms=reporter_duration_ms,
            status=execution_result.status,
        )
        return final_updates

    def _route_after_planner(
        self, state: GraphWorkflowState
    ) -> Literal["executor", "replan", "reporter"]:
        return self._planner_route(
            planner_result=state.get("planner_result"),
            retry_count=state.get("retry_count", 0),
            max_retries=state["max_retries"],
        )

    def _route_after_validation(
        self, state: GraphWorkflowState
    ) -> Literal["replan", "reporter"]:
        return self._validation_route(
            validation_passed=state.get("validation_passed", False),
            retry_count=state.get("retry_count", 0),
            max_retries=state["max_retries"],
        )

    def _planner_route(
        self,
        *,
        planner_result: PlannerAgentResult | None,
        retry_count: int,
        max_retries: int,
    ) -> Literal["executor", "replan", "reporter"]:
        if planner_result is not None and planner_result.status == "passed" and planner_result.test_case is not None:
            return "executor"
        if retry_count < max_retries:
            return "replan"
        return "reporter"

    def _validation_route(
        self,
        *,
        validation_passed: bool,
        retry_count: int,
        max_retries: int,
    ) -> Literal["replan", "reporter"]:
        if validation_passed:
            return "reporter"
        if retry_count < max_retries:
            return "replan"
        return "reporter"

    def _fallback_result(self, state: GraphWorkflowState) -> BrowserRunResult:
        started_at = datetime.now(timezone.utc)
        planner_result = state.get("planner_result")
        return BrowserRunResult(
            requested_url=state["url"],
            final_url=None,
            page_title=None,
            navigation_status=None,
            started_at=started_at,
            completed_at=started_at,
            status="failed",
            before_screenshot_path=None,
            after_screenshot_path=None,
            dom_snapshot_path=None,
            error_message=state.get("failure_reason"),
            failure_reason=state.get("failure_reason"),
            test_name=(
                planner_result.test_case.name
                if planner_result and planner_result.test_case is not None
                else "AI Planned Test"
            ),
            test_file=(
                str(planner_result.final_plan_path)
                if planner_result and planner_result.final_plan_path is not None
                else None
            ),
        )

    def _build_retry_instruction(
        self,
        *,
        base_instruction: str,
        failure_reason: str,
        retry_count: int,
    ) -> str:
        return (
            f"{base_instruction}\n"
            f"Retry attempt: {retry_count}\n"
            f"Previous attempt failed because: {failure_reason}\n"
            "Generate a revised JSON plan that avoids the failure, uses stable selectors, "
            "and keeps the assertions achievable from the page."
        )

    def _persist_observability(self, state: GraphWorkflowState) -> None:
        run_artifacts = state["run_artifacts"]
        self.artifact_manager.write_graph_trace(
            run_artifacts=run_artifacts,
            payload={
                "run_id": state["run_id"],
                "status": state.get("execution_result").status
                if state.get("execution_result") is not None
                else "running",
                "retry_count": state.get("retry_count", 0),
                "max_retries": state.get("max_retries", 0),
                "events": state.get("graph_trace", []),
            },
        )
        self.artifact_manager.write_planner_trace(
            run_artifacts=run_artifacts,
            payload={
                "run_id": state["run_id"],
                "planner_cycles": state.get("planner_cycles", []),
                "planner_attempts": state.get("planner_attempts", []),
                "status": (
                    state.get("planner_result").status
                    if state.get("planner_result") is not None
                    else "pending"
                ),
            },
        )
        self.artifact_manager.write_execution_metrics(
            run_artifacts=run_artifacts,
            payload=state.get("metrics", {}),
        )

    def _record_metric(
        self,
        state: GraphWorkflowState,
        node_name: Literal["planner", "executor", "validator", "replan", "reporter"],
        duration_ms: int,
    ) -> dict[str, Any]:
        metrics = json.loads(json.dumps(state.get("metrics", {})))
        node_timings = metrics.setdefault("node_timings_ms", {})
        node_timings.setdefault(node_name, [])
        node_timings[node_name].append(duration_ms)

        if node_name == "planner":
            metrics["planner_duration_ms"] = sum(node_timings["planner"])
        elif node_name == "executor":
            metrics["execution_duration_ms"] = sum(node_timings["executor"])
        elif node_name == "validator":
            metrics["validation_duration_ms"] = sum(node_timings["validator"])
        elif node_name == "replan":
            metrics["replan_duration_ms"] = sum(node_timings["replan"])
        elif node_name == "reporter":
            metrics["reporter_duration_ms"] = sum(node_timings["reporter"])
        return metrics

    def _with_trace(
        self,
        state: GraphWorkflowState,
        *,
        node: str,
        event: str,
        retry_count: int,
        duration_ms: int | None = None,
        status: str | None = None,
        next_node: str | None = None,
        failure_reason: str | None = None,
        attempt_count: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        trace = list(state.get("graph_trace", []))
        trace.append(
            self._trace_event(
                node=node,
                event=event,
                retry_count=retry_count,
                duration_ms=duration_ms,
                status=status,
                next_node=next_node,
                failure_reason=failure_reason,
                attempt_count=attempt_count,
                details=details,
            )
        )
        return trace

    def _trace_event(
        self,
        *,
        node: str,
        event: str,
        retry_count: int,
        duration_ms: int | None = None,
        status: str | None = None,
        next_node: str | None = None,
        failure_reason: str | None = None,
        attempt_count: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "timestamp": self._timestamp(),
            "node": node,
            "event": event,
            "retry_count": retry_count,
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if status is not None:
            payload["status"] = status
        if next_node is not None:
            payload["next_node"] = next_node
        if failure_reason is not None:
            payload["failure_reason"] = failure_reason
        if attempt_count is not None:
            payload["attempt_count"] = attempt_count
        if details:
            payload["details"] = details
        return payload

    def _merged_state(
        self,
        state: GraphWorkflowState,
        updates: GraphWorkflowState,
    ) -> GraphWorkflowState:
        merged = dict(state)
        merged.update(updates)
        return cast(GraphWorkflowState, merged)

    def _elapsed_ms(self, started_at: float) -> int:
        return int((perf_counter() - started_at) * 1000)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def build_graph(settings: AppSettings):
    return LangGraphWorkflow(settings).graph
