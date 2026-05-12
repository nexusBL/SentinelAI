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
from config.settings import MemorySettings
from memory import MemoryManager
from memory.models import MemoryRetrieval
from memory.models import MemoryStoreResult
from mcp_servers import BrowserMCPServer
from mcp_servers import MCPToolRegistry
from mcp_servers import MemoryMCPServer
from mcp_servers import ValidationMCPServer
from mcp_servers.models import MCPToolResponse
from reporting.run_artifacts import RunArtifactManager
from reporting.run_artifacts import RunArtifacts
from sentinelai.logging_utils import bind_logger
from sentinelai.logging_utils import get_logger
from sentinelai.logging_utils import log_event
from sentinelai.test_case import TestCase


class GraphWorkflowState(TypedDict, total=False):
    phase_name: str
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
    memory_retrieval: MemoryRetrieval | None
    memory_store: MemoryStoreResult | None
    memory_context: str | None
    mcp_enabled: bool
    artifacts_dir: str
    graph_trace: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
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
            "tool_trace": report_paths.get("tool_trace"),
            "metrics": report_paths.get("metrics"),
            "memory_hits": self.final_state.get("metrics", {}).get("memory_hits", 0),
            "memory_store_status": (
                self.final_state.get("memory_store").status
                if self.final_state.get("memory_store") is not None
                else None
            ),
            "mcp_enabled": self.final_state.get("mcp_enabled"),
        }


class LangGraphWorkflow:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.artifact_manager = RunArtifactManager(settings.storage)
        self.logger = get_logger("graph_workflow", phase="phase5")
        self.planner = PlannerAgent(
            ollama_client=OllamaClient(settings.ollama),
            max_attempts=settings.ollama.max_attempts,
        )
        self.runner = PlaywrightBrowserRunner(settings.browser)
        self.memory_bootstrap_error: str | None = None
        self.mcp_bootstrap_error: str | None = None
        try:
            self.memory_manager = MemoryManager(settings.memory)
        except Exception as exc:
            self.memory_bootstrap_error = (
                f"Memory initialization failed: {type(exc).__name__}: {exc}"
            )
            disabled_settings = MemorySettings(
                enabled=False,
                vector_db_path=settings.memory.vector_db_path,
                embedding_provider=settings.memory.embedding_provider,
                embedding_model=settings.memory.embedding_model,
                top_k=settings.memory.top_k,
            )
            self.memory_manager = MemoryManager(disabled_settings)
            log_event(
                self.logger,
                "memory_bootstrap_failed",
                error=self.memory_bootstrap_error,
            )
        try:
            self.mcp_registry = MCPToolRegistry(
                enabled=settings.mcp.enabled,
                timeout_seconds=settings.mcp.timeout_seconds,
                enabled_tools=settings.mcp.enabled_tools,
            )
            self.mcp_registry.register(
                BrowserMCPServer(
                    self.runner,
                    timeout_seconds=settings.mcp.timeout_seconds,
                )
            )
            self.mcp_registry.register(
                MemoryMCPServer(
                    self.memory_manager,
                    timeout_seconds=settings.mcp.timeout_seconds,
                )
            )
            self.mcp_registry.register(
                ValidationMCPServer(timeout_seconds=settings.mcp.timeout_seconds)
            )
        except Exception as exc:
            self.mcp_bootstrap_error = (
                f"MCP initialization failed: {type(exc).__name__}: {exc}"
            )
            self.mcp_registry = MCPToolRegistry(
                enabled=False,
                timeout_seconds=settings.mcp.timeout_seconds,
                enabled_tools=settings.mcp.enabled_tools,
            )
            log_event(
                self.logger,
                "mcp_bootstrap_failed",
                error=self.mcp_bootstrap_error,
            )
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(GraphWorkflowState)
        workflow.add_node("memory_retrieval", self._memory_retrieval_node)
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("executor", self._executor_node)
        workflow.add_node("validator", self._validator_node)
        workflow.add_node("replan", self._replan_node)
        workflow.add_node("memory_store", self._memory_store_node)
        workflow.add_node("reporter", self._reporter_node)

        workflow.add_edge(START, "memory_retrieval")
        workflow.add_edge("memory_retrieval", "planner")
        workflow.add_conditional_edges("planner", self._route_after_planner)
        workflow.add_edge("executor", "validator")
        workflow.add_conditional_edges("validator", self._route_after_validation)
        workflow.add_edge("replan", "memory_retrieval")
        workflow.add_edge("memory_store", "reporter")
        workflow.add_edge("reporter", END)
        return workflow.compile()

    async def execute(
        self,
        *,
        url: str,
        instruction: str,
        model: str | None = None,
        max_retries: int | None = None,
        phase_name: str = "phase5",
    ) -> GraphWorkflowResult:
        run_artifacts = self.artifact_manager.create_run(
            phase=phase_name,
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
                    "phase_name": phase_name,
                    "memory_enabled": self.memory_manager.enabled,
                    "memory_bootstrap_error": self.memory_bootstrap_error,
                    "mcp_enabled": self._phase_uses_mcp(phase_name),
                    "enabled_tools": list(self.settings.mcp.enabled_tools),
                    "tool_tracing_enabled": self.settings.mcp.tool_tracing_enabled,
                    "mcp_bootstrap_error": self.mcp_bootstrap_error,
                },
            )
        ]
        initial_state: GraphWorkflowState = {
            "phase_name": phase_name,
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
            "memory_retrieval": None,
            "memory_store": None,
            "memory_context": None,
            "mcp_enabled": self._phase_uses_mcp(phase_name),
            "artifacts_dir": str(run_artifacts.run_dir),
            "graph_trace": initial_trace,
            "tool_trace": [],
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
                "memory_retrieval_duration_ms": 0,
                "memory_store_duration_ms": 0,
                "total_workflow_duration_ms": 0,
                "memory_hits": 0,
                "retrieval_count": 0,
                "similarity_scores": [],
                "planner_memory_usage": False,
                "memory_store_status": "pending",
                "memory_bootstrap_error": self.memory_bootstrap_error,
                "mcp_enabled": self._phase_uses_mcp(phase_name),
                "enabled_tools": list(self.settings.mcp.enabled_tools),
                "tool_tracing_enabled": self.settings.mcp.tool_tracing_enabled,
                "mcp_bootstrap_error": self.mcp_bootstrap_error,
                "tool_invocation_count": 0,
                "tool_failure_count": 0,
                "tool_average_duration_ms": 0,
                "tool_metrics": {},
                "node_timings_ms": {
                    "memory_retrieval": [],
                    "planner": [],
                    "executor": [],
                    "validator": [],
                    "replan": [],
                    "memory_store": [],
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

    async def _memory_retrieval_node(self, state: GraphWorkflowState) -> GraphWorkflowState:
        node_start = perf_counter()
        retry_count = state.get("retry_count", 0)
        logger = bind_logger(
            self.logger,
            phase=state.get("phase_name"),
            run_id=state.get("run_id"),
            graph_node="memory_retrieval",
        )
        log_event(logger, "memory_retrieval_started", retry_count=retry_count)
        tool_trace = list(state.get("tool_trace", []))
        metrics = json.loads(json.dumps(state.get("metrics", {})))

        try:
            if state.get("mcp_enabled"):
                response, tool_trace, metrics = await self._invoke_tool(
                    state=state,
                    server_name="memory",
                    action="retrieve_similar",
                    payload={
                        "url": state["url"],
                        "instruction": state["current_instruction"],
                        "failure_context": state.get("failure_reason"),
                        "top_k": self.settings.memory.top_k,
                    },
                    graph_node="memory_retrieval",
                    retry_count=retry_count,
                    tool_trace=tool_trace,
                    metrics=metrics,
                )
                if response.status != "passed":
                    raise RuntimeError(
                        response.error_message or "Memory retrieval tool invocation failed."
                    )
                retrieval_payload = response.result or {}
                retrieval = retrieval_payload.get("retrieval")
                if not isinstance(retrieval, MemoryRetrieval):
                    raise TypeError(
                        "Memory retrieval tool returned an unexpected payload."
                    )
            else:
                retrieval = self.memory_manager.retrieve_similar(
                    url=state["url"],
                    instruction=state["current_instruction"],
                    failure_context=state.get("failure_reason"),
                )
            retrieval_path = state["run_artifacts"].planner_dir / (
                f"cycle_{retry_count:02d}_memory_retrieval.json"
            )
            self.memory_manager.write_retrieval_artifact(
                output_path=retrieval_path,
                retrieval=retrieval,
            )
            duration_ms = self._elapsed_ms(node_start)
            graph_trace = self._with_trace(
                state,
                node="memory_retrieval",
                event="completed",
                retry_count=retry_count,
                duration_ms=duration_ms,
                status=retrieval.status,
                next_node="planner",
                details={
                    "result_count": len(retrieval.results),
                    "artifact_path": str(retrieval_path),
                },
            )
            metrics = self._record_metric(
                self._merged_state(state, {"metrics": metrics}), "memory_retrieval", duration_ms
            )
            metrics["retrieval_count"] = len(retrieval.results)
            metrics["memory_hits"] = len(retrieval.results)
            metrics["similarity_scores"] = [
                round(result.score, 6) for result in retrieval.results
            ]
            metrics["planner_memory_usage"] = bool(retrieval.prompt_context)
            updates: GraphWorkflowState = {
                "memory_retrieval": retrieval,
                "memory_context": retrieval.prompt_context,
                "graph_trace": graph_trace,
                "tool_trace": tool_trace,
                "metrics": metrics,
            }
            self._persist_observability(self._merged_state(state, updates))
            log_event(
                logger,
                "memory_retrieval_completed",
                retry_count=retry_count,
                duration_ms=duration_ms,
                status=retrieval.status,
                result_count=len(retrieval.results),
            )
            return updates
        except Exception as exc:
            duration_ms = self._elapsed_ms(node_start)
            failure_reason = f"Memory retrieval error: {type(exc).__name__}: {exc}"
            graph_trace = self._with_trace(
                state,
                node="memory_retrieval",
                event="completed",
                retry_count=retry_count,
                duration_ms=duration_ms,
                status="failed",
                next_node="planner",
                failure_reason=failure_reason,
            )
            metrics = self._record_metric(
                self._merged_state(state, {"metrics": metrics}),
                "memory_retrieval",
                duration_ms,
            )
            metrics["planner_memory_usage"] = False
            metrics["retrieval_count"] = 0
            metrics["memory_hits"] = 0
            metrics["similarity_scores"] = []
            updates = {
                "memory_retrieval": None,
                "memory_context": None,
                "graph_trace": graph_trace,
                "tool_trace": tool_trace,
                "metrics": metrics,
            }
            self._persist_observability(self._merged_state(state, updates))
            log_event(
                logger,
                "memory_retrieval_completed",
                retry_count=retry_count,
                duration_ms=duration_ms,
                status="failed",
                error=failure_reason,
            )
            return updates

    async def _planner_node(self, state: GraphWorkflowState) -> GraphWorkflowState:
        cycle = state.get("retry_count", 0)
        node_start = perf_counter()
        logger = bind_logger(
            self.logger,
            phase=state.get("phase_name"),
            run_id=state.get("run_id"),
            graph_node="planner",
        )
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
            memory_context=state.get("memory_context"),
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

    async def _memory_store_node(self, state: GraphWorkflowState) -> GraphWorkflowState:
        node_start = perf_counter()
        retry_count = state.get("retry_count", 0)
        logger = bind_logger(
            self.logger,
            phase=state.get("phase_name"),
            run_id=state.get("run_id"),
            graph_node="memory_store",
        )
        log_event(logger, "memory_store_started", retry_count=retry_count)
        tool_trace = list(state.get("tool_trace", []))
        metrics = json.loads(json.dumps(state.get("metrics", {})))

        try:
            execution_result = state.get("execution_result") or self._fallback_result(state)
            validation_status = (
                state.get("validation_result", {}).get("status")
                or ("passed" if state.get("validation_passed") else "failed")
            )
            if state.get("mcp_enabled"):
                response, tool_trace, metrics = await self._invoke_tool(
                    state=state,
                    server_name="memory",
                    action="store_execution",
                    payload={
                        "run_id": state["run_id"],
                        "url": state["url"],
                        "instruction": state["instruction"],
                        "generated_test_plan": state.get("test_plan"),
                        "execution_summary": self._build_execution_summary(execution_result),
                        "failure_reason": state.get("failure_reason"),
                        "validation_status": str(validation_status),
                        "retry_count": retry_count,
                        "final_result": execution_result.status,
                        "tags": self._build_memory_tags(state, execution_result),
                        "metadata": {
                            "phase": state.get("phase_name", "phase5"),
                            "planner_status": (
                                state.get("planner_result").status
                                if state.get("planner_result") is not None
                                else "unknown"
                            ),
                            "test_name": execution_result.test_name,
                            "memory_hits": state.get("metrics", {}).get("memory_hits", 0),
                        },
                    },
                    graph_node="memory_store",
                    retry_count=retry_count,
                    tool_trace=tool_trace,
                    metrics=metrics,
                )
                if response.status != "passed":
                    raise RuntimeError(
                        response.error_message or "Memory store tool invocation failed."
                    )
                store_payload = response.result or {}
                store_result = store_payload.get("store_result")
                if not isinstance(store_result, MemoryStoreResult):
                    raise TypeError("Memory store tool returned an unexpected payload.")
            else:
                store_result = self.memory_manager.store_execution(
                    run_id=state["run_id"],
                    url=state["url"],
                    instruction=state["instruction"],
                    generated_test_plan=state.get("test_plan"),
                    execution_summary=self._build_execution_summary(execution_result),
                    failure_reason=state.get("failure_reason"),
                    validation_status=str(validation_status),
                    retry_count=retry_count,
                    final_result=execution_result.status,
                    tags=self._build_memory_tags(state, execution_result),
                    metadata={
                        "phase": state.get("phase_name", "phase5"),
                        "planner_status": (
                            state.get("planner_result").status
                            if state.get("planner_result") is not None
                            else "unknown"
                        ),
                        "test_name": execution_result.test_name,
                        "memory_hits": state.get("metrics", {}).get("memory_hits", 0),
                    },
                )
            store_artifact_path = state["run_artifacts"].logs_dir / "stored_memory_entry.json"
            self.memory_manager.write_store_artifact(
                output_path=store_artifact_path,
                store_result=store_result,
            )
            duration_ms = self._elapsed_ms(node_start)
            graph_trace = self._with_trace(
                state,
                node="memory_store",
                event="completed",
                retry_count=retry_count,
                duration_ms=duration_ms,
                status=store_result.status,
                next_node="reporter",
                details={
                    "artifact_path": str(store_artifact_path),
                    "vector_count": store_result.vector_count,
                },
            )
            metrics = self._record_metric(
                self._merged_state(state, {"metrics": metrics}), "memory_store", duration_ms
            )
            metrics["memory_store_status"] = store_result.status
            updates: GraphWorkflowState = {
                "memory_store": store_result,
                "graph_trace": graph_trace,
                "tool_trace": tool_trace,
                "metrics": metrics,
            }
            self._persist_observability(self._merged_state(state, updates))
            log_event(
                logger,
                "memory_store_completed",
                retry_count=retry_count,
                duration_ms=duration_ms,
                status=store_result.status,
                vector_count=store_result.vector_count,
            )
            return updates
        except Exception as exc:
            duration_ms = self._elapsed_ms(node_start)
            failure_reason = f"Memory store error: {type(exc).__name__}: {exc}"
            graph_trace = self._with_trace(
                state,
                node="memory_store",
                event="completed",
                retry_count=retry_count,
                duration_ms=duration_ms,
                status="failed",
                next_node="reporter",
                failure_reason=failure_reason,
            )
            metrics = self._record_metric(
                self._merged_state(state, {"metrics": metrics}), "memory_store", duration_ms
            )
            metrics["memory_store_status"] = "failed"
            updates = {
                "memory_store": None,
                "graph_trace": graph_trace,
                "tool_trace": tool_trace,
                "metrics": metrics,
            }
            self._persist_observability(self._merged_state(state, updates))
            log_event(
                logger,
                "memory_store_completed",
                retry_count=retry_count,
                duration_ms=duration_ms,
                status="failed",
                error=failure_reason,
            )
            return updates

    async def _executor_node(self, state: GraphWorkflowState) -> GraphWorkflowState:
        node_start = perf_counter()
        retry_count = state.get("retry_count", 0)
        logger = bind_logger(
            self.logger,
            phase=state.get("phase_name"),
            run_id=state.get("run_id"),
            graph_node="executor",
        )
        log_event(logger, "executor_started", retry_count=retry_count)
        tool_trace = list(state.get("tool_trace", []))
        metrics = json.loads(json.dumps(state.get("metrics", {})))

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
            metrics = self._record_metric(
                self._merged_state(state, {"metrics": metrics}), "executor", duration_ms
            )
            updates: GraphWorkflowState = {
                "execution_result": None,
                "failure_reason": failure_reason,
                "graph_trace": graph_trace,
                "tool_trace": tool_trace,
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

        if state.get("mcp_enabled"):
            response, tool_trace, metrics = await self._invoke_tool(
                state=state,
                server_name="browser",
                action="run_test_case",
                payload={
                    "test_case": test_case,
                    "run_artifacts": state["run_artifacts"],
                },
                graph_node="executor",
                retry_count=retry_count,
                tool_trace=tool_trace,
                metrics=metrics,
            )
            if response.status != "passed":
                failure_reason = (
                    response.error_message or "Browser tool failed to execute the test case."
                )
                execution_result = self._fallback_result(
                    self._merged_state(state, {"failure_reason": failure_reason})
                )
                execution_result.failure_reason = failure_reason
                execution_result.error_message = failure_reason
            else:
                execution_payload = response.result or {}
                execution_result = execution_payload.get("execution_result")
                if not isinstance(execution_result, BrowserRunResult):
                    failure_reason = "Browser tool returned an unexpected execution payload."
                    execution_result = self._fallback_result(
                        self._merged_state(state, {"failure_reason": failure_reason})
                    )
                    execution_result.failure_reason = failure_reason
                    execution_result.error_message = failure_reason
        else:
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
        metrics = self._record_metric(
            self._merged_state(state, {"metrics": metrics}), "executor", duration_ms
        )
        updates = {
            "execution_result": execution_result,
            "failure_reason": execution_result.failure_reason,
            "graph_trace": graph_trace,
            "tool_trace": tool_trace,
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
        logger = bind_logger(
            self.logger,
            phase=state.get("phase_name"),
            run_id=state.get("run_id"),
            graph_node="validator",
        )
        log_event(logger, "validator_started", retry_count=retry_count)
        tool_trace = list(state.get("tool_trace", []))
        metrics = json.loads(json.dumps(state.get("metrics", {})))

        execution_result = state.get("execution_result")
        if state.get("mcp_enabled") and execution_result is not None:
            summary_response, tool_trace, metrics = await self._invoke_tool(
                state=state,
                server_name="validation",
                action="summarize_validation",
                payload={"execution_result": execution_result},
                graph_node="validator",
                retry_count=retry_count,
                tool_trace=tool_trace,
                metrics=metrics,
            )
            if summary_response.status != "passed":
                validation_passed = bool(execution_result and execution_result.status == "passed")
                failure_reason = summary_response.error_message or execution_result.failure_reason
                validation_result = {
                    "status": "passed" if validation_passed else "failed",
                    "validation_passed": validation_passed,
                    "failure_reason": failure_reason,
                    "step_count": len(execution_result.steps_executed) if execution_result else 0,
                    "assertion_count": len(execution_result.assertion_results) if execution_result else 0,
                }
            else:
                validation_result = dict(summary_response.result or {})
                validation_passed = bool(validation_result.get("validation_passed"))
                if validation_passed:
                    failure_reason = None
                else:
                    failure_response, tool_trace, metrics = await self._invoke_tool(
                        state=state,
                        server_name="validation",
                        action="extract_failure_reason",
                        payload={
                            "execution_result": execution_result,
                            "fallback_reason": state.get("failure_reason")
                            or "Validation failed without an execution result.",
                        },
                        graph_node="validator",
                        retry_count=retry_count,
                        tool_trace=tool_trace,
                        metrics=metrics,
                    )
                    if failure_response.status == "passed":
                        failure_reason = dict(failure_response.result or {}).get(
                            "failure_reason"
                        )
                    else:
                        failure_reason = (
                            failure_response.error_message
                            or execution_result.failure_reason
                            or state.get("failure_reason")
                            or "Validation failed without an execution result."
                        )
                    validation_result["failure_reason"] = failure_reason
        else:
            validation_passed = bool(execution_result and execution_result.status == "passed")
            failure_reason = None if validation_passed else (
                execution_result.failure_reason
                if execution_result is not None
                else state.get("failure_reason") or "Validation failed without an execution result."
            )
            validation_result = {
                "status": "passed" if validation_passed else "failed",
                "validation_passed": validation_passed,
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
        metrics = self._record_metric(
            self._merged_state(state, {"metrics": metrics}), "validator", duration_ms
        )
        updates = {
            "validation_result": validation_result,
            "validation_passed": validation_passed,
            "failure_reason": failure_reason,
            "graph_trace": graph_trace,
            "tool_trace": tool_trace,
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
        logger = bind_logger(
            self.logger,
            phase=state.get("phase_name"),
            run_id=state.get("run_id"),
            graph_node="replan",
        )
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
        logger = bind_logger(
            self.logger,
            phase=state.get("phase_name"),
            run_id=state.get("run_id"),
            graph_node="reporter",
        )
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
        tool_trace_path = self.artifact_manager.write_tool_trace(
            run_artifacts=state["run_artifacts"],
            payload={
                "run_id": state["run_id"],
                "status": execution_result.status,
                "mcp_enabled": state.get("mcp_enabled", False),
                "events": merged_state.get("tool_trace", []),
            },
        )

        workflow_payload = {
            "validation_passed": merged_state.get("validation_passed"),
            "retry_count": retry_count,
            "max_retries": state["max_retries"],
            "failure_reason": merged_state.get("failure_reason"),
            "instruction_history": merged_state.get("instruction_history", []),
            "planner_attempt_count": len(merged_state.get("planner_attempts", [])),
            "memory_enabled": self.memory_manager.enabled,
            "memory_hits": metrics.get("memory_hits", 0),
            "retrieval_count": metrics.get("retrieval_count", 0),
            "similarity_scores": metrics.get("similarity_scores", []),
            "memory_store_status": metrics.get("memory_store_status"),
            "memory_bootstrap_error": self.memory_bootstrap_error,
            "mcp_enabled": state.get("mcp_enabled", False),
            "enabled_tools": list(self.settings.mcp.enabled_tools),
            "tool_tracing_enabled": self.settings.mcp.tool_tracing_enabled,
            "tool_invocation_count": metrics.get("tool_invocation_count", 0),
            "tool_failure_count": metrics.get("tool_failure_count", 0),
            "tool_average_duration_ms": metrics.get("tool_average_duration_ms", 0),
            "mcp_bootstrap_error": self.mcp_bootstrap_error,
            "graph_trace_path": str(graph_trace_path),
            "tool_trace_path": str(tool_trace_path),
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
            "tool_trace": str(tool_trace_path),
            "planner_trace": str(planner_trace_path),
            "metrics": str(metrics_path),
        }
        final_updates: GraphWorkflowState = {
            "execution_result": execution_result,
            "graph_trace": graph_trace,
            "tool_trace": merged_state.get("tool_trace", []),
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
    ) -> Literal["executor", "replan", "memory_store"]:
        return self._planner_route(
            planner_result=state.get("planner_result"),
            retry_count=state.get("retry_count", 0),
            max_retries=state["max_retries"],
        )

    def _route_after_validation(
        self, state: GraphWorkflowState
    ) -> Literal["replan", "memory_store"]:
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
    ) -> Literal["executor", "replan", "memory_store"]:
        if planner_result is not None and planner_result.status == "passed" and planner_result.test_case is not None:
            return "executor"
        if retry_count < max_retries:
            return "replan"
        return "memory_store"

    def _validation_route(
        self,
        *,
        validation_passed: bool,
        retry_count: int,
        max_retries: int,
    ) -> Literal["replan", "memory_store"]:
        if validation_passed:
            return "memory_store"
        if retry_count < max_retries:
            return "replan"
        return "memory_store"

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

    def _build_execution_summary(self, execution_result: BrowserRunResult) -> dict[str, Any]:
        step_count = len(execution_result.steps_executed)
        assertion_count = len(execution_result.assertion_results)
        passed_steps = sum(
            1 for step in execution_result.steps_executed if step.status == "passed"
        )
        passed_assertions = sum(
            1
            for assertion in execution_result.assertion_results
            if assertion.status == "passed"
        )
        return {
            "requested_url": execution_result.requested_url,
            "final_url": execution_result.final_url,
            "page_title": execution_result.page_title,
            "navigation_status": execution_result.navigation_status,
            "step_count": step_count,
            "passed_steps": passed_steps,
            "failed_steps": step_count - passed_steps,
            "assertion_count": assertion_count,
            "passed_assertions": passed_assertions,
            "failed_assertions": assertion_count - passed_assertions,
            "test_name": execution_result.test_name,
        }

    def _build_memory_tags(
        self,
        state: GraphWorkflowState,
        execution_result: BrowserRunResult,
    ) -> list[str]:
        tags = [state.get("phase_name", "phase5"), execution_result.status]
        if state.get("validation_passed"):
            tags.append("validated")
        else:
            tags.append("needs_attention")
        if state.get("retry_count", 0) > 0:
            tags.append("retried")
        if state.get("metrics", {}).get("memory_hits", 0) > 0:
            tags.append("memory_hit")
        if state.get("mcp_enabled"):
            tags.append("mcp")
        return tags

    def _phase_uses_mcp(self, phase_name: str) -> bool:
        return phase_name == "phase6" and self.mcp_registry.enabled

    async def _invoke_tool(
        self,
        *,
        state: GraphWorkflowState,
        server_name: str,
        action: str,
        payload: dict[str, Any],
        graph_node: str,
        retry_count: int,
        tool_trace: list[dict[str, Any]] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> tuple[MCPToolResponse, list[dict[str, Any]], dict[str, Any]]:
        response = await self.mcp_registry.execute(
            server_name=server_name,
            action=action,
            payload=payload,
        )
        current_trace = list(tool_trace if tool_trace is not None else state.get("tool_trace", []))
        current_metrics = json.loads(
            json.dumps(metrics if metrics is not None else state.get("metrics", {}))
        )
        summary = self._summarize_tool_payload(payload)
        if self.settings.mcp.tool_tracing_enabled and state.get("mcp_enabled"):
            current_trace.append(
                {
                    "timestamp": self._timestamp(),
                    "graph_node": graph_node,
                    "tool_name": server_name,
                    "action": action,
                    "retry_count": retry_count,
                    "status": response.status,
                    "duration_ms": response.duration_ms,
                    "payload_summary": summary,
                    "error_message": response.error_message,
                }
            )
        self._record_tool_metrics(
            metrics=current_metrics,
            server_name=server_name,
            response=response,
            retry_count=retry_count,
        )
        return response, current_trace, current_metrics

    def _summarize_tool_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, TestCase):
                summary[key] = {
                    "type": "TestCase",
                    "name": value.name,
                    "step_count": len(value.steps),
                    "assertion_count": len(value.assertions),
                    "target_url": value.target_url,
                }
            elif isinstance(value, RunArtifacts):
                summary[key] = {
                    "type": "RunArtifacts",
                    "run_id": value.context.run_id,
                    "phase": value.context.phase,
                }
            elif isinstance(value, BrowserRunResult):
                summary[key] = {
                    "type": "BrowserRunResult",
                    "status": value.status,
                    "step_count": len(value.steps_executed),
                    "assertion_count": len(value.assertion_results),
                    "failure_reason": value.failure_reason,
                }
            elif isinstance(value, dict):
                summary[key] = {
                    "type": "dict",
                    "keys": sorted(value.keys()),
                }
            elif isinstance(value, (list, tuple, set)):
                summary[key] = {
                    "type": type(value).__name__,
                    "count": len(value),
                }
            elif isinstance(value, Path):
                summary[key] = str(value)
            elif value is None or isinstance(value, (str, int, float, bool)):
                summary[key] = value
            else:
                summary[key] = type(value).__name__
        return summary

    def _record_tool_metrics(
        self,
        *,
        metrics: dict[str, Any],
        server_name: str,
        response: MCPToolResponse,
        retry_count: int,
    ) -> None:
        metrics["tool_invocation_count"] = int(metrics.get("tool_invocation_count", 0)) + 1
        if response.status != "passed":
            metrics["tool_failure_count"] = int(metrics.get("tool_failure_count", 0)) + 1

        tool_metrics = metrics.setdefault("tool_metrics", {})
        tool_entry = tool_metrics.setdefault(
            server_name,
            {
                "invocation_count": 0,
                "failure_count": 0,
                "retry_invocations": 0,
                "total_duration_ms": 0,
                "average_duration_ms": 0,
                "actions": {},
            },
        )
        tool_entry["invocation_count"] += 1
        tool_entry["total_duration_ms"] += response.duration_ms
        tool_entry["average_duration_ms"] = round(
            tool_entry["total_duration_ms"] / max(1, tool_entry["invocation_count"]),
            2,
        )
        if response.status != "passed":
            tool_entry["failure_count"] += 1
        if retry_count > 0:
            tool_entry["retry_invocations"] += 1
        actions = tool_entry.setdefault("actions", {})
        action_entry = actions.setdefault(
            response.action,
            {
                "count": 0,
                "failure_count": 0,
            },
        )
        action_entry["count"] += 1
        if response.status != "passed":
            action_entry["failure_count"] += 1

        total_duration = sum(
            item.get("total_duration_ms", 0)
            for item in tool_metrics.values()
            if isinstance(item, dict)
        )
        metrics["tool_average_duration_ms"] = round(
            total_duration / max(1, metrics["tool_invocation_count"]),
            2,
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
        self.artifact_manager.write_tool_trace(
            run_artifacts=run_artifacts,
            payload={
                "run_id": state["run_id"],
                "status": state.get("execution_result").status
                if state.get("execution_result") is not None
                else "running",
                "mcp_enabled": state.get("mcp_enabled", False),
                "tool_tracing_enabled": self.settings.mcp.tool_tracing_enabled,
                "events": state.get("tool_trace", []),
            },
        )
        self.artifact_manager.write_execution_metrics(
            run_artifacts=run_artifacts,
            payload=state.get("metrics", {}),
        )

    def _record_metric(
        self,
        state: GraphWorkflowState,
        node_name: Literal[
            "memory_retrieval",
            "planner",
            "executor",
            "validator",
            "replan",
            "memory_store",
            "reporter",
        ],
        duration_ms: int,
    ) -> dict[str, Any]:
        metrics = json.loads(json.dumps(state.get("metrics", {})))
        node_timings = metrics.setdefault("node_timings_ms", {})
        node_timings.setdefault(node_name, [])
        node_timings[node_name].append(duration_ms)

        if node_name == "memory_retrieval":
            metrics["memory_retrieval_duration_ms"] = sum(node_timings["memory_retrieval"])
        elif node_name == "planner":
            metrics["planner_duration_ms"] = sum(node_timings["planner"])
        elif node_name == "executor":
            metrics["execution_duration_ms"] = sum(node_timings["executor"])
        elif node_name == "validator":
            metrics["validation_duration_ms"] = sum(node_timings["validator"])
        elif node_name == "replan":
            metrics["replan_duration_ms"] = sum(node_timings["replan"])
        elif node_name == "memory_store":
            metrics["memory_store_duration_ms"] = sum(node_timings["memory_store"])
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
