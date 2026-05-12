from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from browser.models import BrowserRunResult
from config.settings import StorageSettings
from agents.planner_agent import PlannerAgentResult
from sentinelai.run_context import RunContext
from sentinelai.test_case import TestCase


@dataclass(slots=True)
class RunArtifacts:
    context: RunContext
    run_dir: Path
    screenshots_dir: Path
    logs_dir: Path
    reports_dir: Path
    graph_dir: Path
    planner_dir: Path
    metrics_dir: Path


class RunArtifactManager:
    def __init__(self, storage_settings: StorageSettings) -> None:
        self.storage_settings = storage_settings

    def create_run(self, phase: str, target_url: str, instruction: str) -> RunArtifacts:
        created_at = datetime.now(timezone.utc)
        run_id = created_at.strftime("%Y%m%dT%H%M%S%fZ")
        run_dir = self.storage_settings.runs_root / run_id
        screenshots_dir = run_dir / "screenshots"
        logs_dir = run_dir / "logs"
        reports_dir = run_dir / "reports"
        graph_dir = run_dir / "graph"
        planner_dir = run_dir / "planner"
        metrics_dir = run_dir / "metrics"

        for directory in (
            self.storage_settings.artifacts_root,
            self.storage_settings.runs_root,
            run_dir,
            screenshots_dir,
            logs_dir,
            reports_dir,
            graph_dir,
            planner_dir,
            metrics_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self._initialize_observability_placeholders(
            graph_dir=graph_dir,
            planner_dir=planner_dir,
            metrics_dir=metrics_dir,
        )

        return RunArtifacts(
            context=RunContext(
                run_id=run_id,
                phase=phase,
                target_url=target_url,
                instruction=instruction,
                created_at=created_at,
            ),
            run_dir=run_dir,
            screenshots_dir=screenshots_dir,
            logs_dir=logs_dir,
            reports_dir=reports_dir,
            graph_dir=graph_dir,
            planner_dir=planner_dir,
            metrics_dir=metrics_dir,
        )

    def build_phase1_payload(
        self, run_artifacts: RunArtifacts, result: BrowserRunResult
    ) -> dict:
        return self._build_common_payload(
            run_artifacts=run_artifacts,
            result=result,
            extra_payload={},
        )

    def build_phase2_payload(
        self,
        run_artifacts: RunArtifacts,
        test_case: TestCase,
        result: BrowserRunResult,
    ) -> dict:
        return self._build_common_payload(
            run_artifacts=run_artifacts,
            result=result,
            extra_payload={
                "test_name": test_case.name,
                "test_description": test_case.description,
                "test_file": str(test_case.source_path) if test_case.source_path else None,
            },
        )

    def build_phase3_payload(
        self,
        run_artifacts: RunArtifacts,
        result: BrowserRunResult,
        planner_result: PlannerAgentResult,
    ) -> dict:
        return self._build_common_payload(
            run_artifacts=run_artifacts,
            result=result,
            extra_payload={
                "planner": planner_result.to_dict(),
            },
        )

    def build_phase4_payload(
        self,
        run_artifacts: RunArtifacts,
        result: BrowserRunResult,
        planner_result: PlannerAgentResult | None,
        workflow: dict,
    ) -> dict:
        extra_payload = {
            "workflow": workflow,
        }
        if planner_result is not None:
            extra_payload["planner"] = planner_result.to_dict()
        return self._build_common_payload(
            run_artifacts=run_artifacts,
            result=result,
            extra_payload=extra_payload,
        )

    def write_graph_trace(self, run_artifacts: RunArtifacts, payload: dict) -> Path:
        path = run_artifacts.graph_dir / "graph_trace.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def write_planner_trace(self, run_artifacts: RunArtifacts, payload: dict) -> Path:
        path = run_artifacts.planner_dir / "planner_trace.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def write_tool_trace(self, run_artifacts: RunArtifacts, payload: dict) -> Path:
        path = run_artifacts.graph_dir / "tool_trace.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def write_execution_metrics(self, run_artifacts: RunArtifacts, payload: dict) -> Path:
        path = run_artifacts.metrics_dir / "execution_metrics.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def write_json_report(self, run_artifacts: RunArtifacts, payload: dict) -> Path:
        report_path = run_artifacts.reports_dir / "report.json"
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return report_path

    def write_html_report(self, run_artifacts: RunArtifacts, payload: dict) -> Path:
        report_path = run_artifacts.reports_dir / "report.html"

        before_relative = self._relative_artifact_path(
            run_artifacts, payload.get("artifacts", {}).get("before_screenshot_path")
        )
        after_relative = self._relative_artifact_path(
            run_artifacts, payload.get("artifacts", {}).get("after_screenshot_path")
        )
        dom_relative = self._relative_artifact_path(
            run_artifacts, payload.get("artifacts", {}).get("dom_snapshot_path")
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SentinelAI Report {escape(payload["run_id"])}</title>
  <style>
    body {{
      background:
        radial-gradient(circle at top right, rgba(76, 137, 255, 0.16), transparent 28%),
        linear-gradient(180deg, #eef4ff 0%, #f7f9fc 100%);
      color: #17212b;
      font-family: "Segoe UI", sans-serif;
      margin: 0;
      padding: 32px;
    }}
    main {{
      background: #ffffff;
      border-radius: 20px;
      box-shadow: 0 24px 60px rgba(16, 24, 40, 0.10);
      margin: 0 auto;
      max-width: 1180px;
      padding: 32px;
    }}
    h1, h2, h3 {{
      margin-top: 0;
    }}
    .meta {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      margin-bottom: 24px;
    }}
    .card {{
      background: #f8fafc;
      border: 1px solid #dbe3ec;
      border-radius: 14px;
      padding: 16px;
    }}
    .status-badge {{
      border-radius: 999px;
      display: inline-block;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      padding: 6px 10px;
      text-transform: uppercase;
    }}
    .passed {{
      background: #dcfae6;
      color: #067647;
    }}
    .failed {{
      background: #fee4e2;
      color: #b42318;
    }}
    .steps {{
      display: grid;
      gap: 16px;
      margin-top: 16px;
    }}
    .step-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      margin-top: 12px;
    }}
    table {{
      border-collapse: collapse;
      margin-top: 16px;
      width: 100%;
    }}
    th, td {{
      border-bottom: 1px solid #e4e7ec;
      padding: 12px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #f8fafc;
      color: #344054;
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    img {{
      border: 1px solid #d0d5dd;
      border-radius: 12px;
      display: block;
      margin-top: 12px;
      max-width: 100%;
    }}
    .summary {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      margin-top: 12px;
    }}
    .mono {{
      font-family: Consolas, "Courier New", monospace;
    }}
    a {{
      color: #175cd3;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main>
    <h1>SentinelAI {escape(str(payload["phase"]).upper())} Report</h1>
    <div class="meta">
      <div class="card"><strong>Run ID</strong><br />{escape(payload["run_id"])}</div>
      <div class="card"><strong>Status</strong><br />{self._status_badge(payload["status"])}</div>
      <div class="card"><strong>Requested URL</strong><br />{escape(str(payload["requested_url"]))}</div>
      <div class="card"><strong>Final URL</strong><br />{escape(str(payload["final_url"]))}</div>
      <div class="card"><strong>Page Title</strong><br />{escape(str(payload["page_title"]))}</div>
      <div class="card"><strong>Instruction</strong><br />{escape(str(payload["instruction"]))}</div>
    </div>
    {self._render_failure_section(payload)}
    {self._render_summary_section(payload)}
    {self._render_planner_section(run_artifacts, payload.get("planner"))}
    {self._render_workflow_section(run_artifacts, payload.get("workflow"))}
    {self._render_steps_section(run_artifacts, payload.get("steps", []))}
    {self._render_assertions_section(payload.get("assertions", []))}
    {self._render_phase1_screenshots(before_relative, after_relative, payload.get("steps", []))}
    <section>
      <h2>Artifacts</h2>
      <div class="card">
        <p><strong>Test file</strong><br />{escape(str(payload.get("test_file")))}</p>
        <p><strong>DOM snapshot</strong><br />{self._artifact_link(dom_relative)}</p>
        <p><strong>Infrastructure error</strong><br />{escape(str(payload.get("error_message")))}</p>
      </div>
    </section>
  </main>
</body>
</html>
"""
        report_path.write_text(html, encoding="utf-8")
        return report_path

    def _build_common_payload(
        self,
        run_artifacts: RunArtifacts,
        result: BrowserRunResult,
        extra_payload: dict,
    ) -> dict:
        steps = [step.to_dict() for step in result.steps_executed]
        assertions = [assertion.to_dict() for assertion in result.assertion_results]
        passed_steps = sum(1 for step in steps if step["status"] == "passed")
        passed_assertions = sum(
            1 for assertion in assertions if assertion["status"] == "passed"
        )

        payload = {
            "run_id": run_artifacts.context.run_id,
            "phase": run_artifacts.context.phase,
            "instruction": run_artifacts.context.instruction,
            "requested_url": result.requested_url,
            "final_url": result.final_url,
            "page_title": result.page_title,
            "navigation_status": result.navigation_status,
            "status": result.status,
            "error_message": result.error_message,
            "failure_reason": result.failure_reason,
            "created_at": run_artifacts.context.created_at.isoformat(),
            "summary": {
                "total_steps": len(steps),
                "passed_steps": passed_steps,
                "failed_steps": len(steps) - passed_steps,
                "total_assertions": len(assertions),
                "passed_assertions": passed_assertions,
                "failed_assertions": len(assertions) - passed_assertions,
            },
            "steps": steps,
            "assertions": assertions,
            "artifacts": result.to_dict(),
            "test_name": result.test_name,
            "test_file": result.test_file,
        }
        payload.update(extra_payload)
        return payload

    def _initialize_observability_placeholders(
        self,
        *,
        graph_dir: Path,
        planner_dir: Path,
        metrics_dir: Path,
    ) -> None:
        placeholders = {
            graph_dir / "graph_trace.json": {
                "events": [],
                "status": "pending",
            },
            planner_dir / "planner_trace.json": {
                "events": [],
                "status": "pending",
            },
            graph_dir / "tool_trace.json": {
                "events": [],
                "status": "pending",
            },
            metrics_dir / "execution_metrics.json": {
                "retry_count": 0,
                "node_timings_ms": {},
                "status": "pending",
            },
        }
        for path, payload in placeholders.items():
            if not path.exists():
                path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _relative_artifact_path(
        self, run_artifacts: RunArtifacts, artifact_path: str | None
    ) -> str | None:
        if not artifact_path:
            return None
        return Path(artifact_path).relative_to(run_artifacts.run_dir).as_posix()

    def _status_badge(self, status: str) -> str:
        css_class = "passed" if status == "passed" else "failed"
        return (
            f"<span class='status-badge {css_class}'>"
            f"{escape(status.upper())}</span>"
        )

    def _artifact_link(self, relative_path: str | None) -> str:
        if not relative_path:
            return "Not available"
        safe_relative = escape(relative_path)
        return f"<a href='../{safe_relative}'>{safe_relative}</a>"

    def _render_failure_section(self, payload: dict) -> str:
        failure_reason = payload.get("failure_reason")
        if not failure_reason:
            return ""
        return (
            "<section>"
            "<h2>Failure Summary</h2>"
            f"<div class='card'><p>{escape(str(failure_reason))}</p></div>"
            "</section>"
        )

    def _render_summary_section(self, payload: dict) -> str:
        summary = payload.get("summary", {})
        return f"""
<section>
  <h2>Execution Summary</h2>
  <div class="summary">
    <div class="card"><strong>Test Name</strong><br />{escape(str(payload.get("test_name")))}</div>
    <div class="card"><strong>Total Steps</strong><br />{escape(str(summary.get("total_steps")))}</div>
    <div class="card"><strong>Passed Steps</strong><br />{escape(str(summary.get("passed_steps")))}</div>
    <div class="card"><strong>Total Assertions</strong><br />{escape(str(summary.get("total_assertions")))}</div>
    <div class="card"><strong>Passed Assertions</strong><br />{escape(str(summary.get("passed_assertions")))}</div>
  </div>
</section>
"""

    def _render_steps_section(self, run_artifacts: RunArtifacts, steps: list[dict]) -> str:
        if not steps:
            return ""

        cards: list[str] = []
        for step in steps:
            screenshot_relative = self._relative_artifact_path(
                run_artifacts, step.get("screenshot_path")
            )
            screenshot_html = (
                f"<img src='../{escape(screenshot_relative)}' alt='Step screenshot' />"
                if screenshot_relative
                else "<p>No screenshot captured for this step.</p>"
            )
            cards.append(
                f"""
<div class="card">
  <h3>Step {escape(str(step["index"]))}: {escape(str(step["description"]))}</h3>
  <p>{self._status_badge(str(step["status"]))}</p>
  <div class="step-grid">
    <div><strong>Action</strong><br />{escape(str(step["action"]))}</div>
    <div><strong>Selector</strong><br /><span class="mono">{escape(str(step["selector"]))}</span></div>
    <div><strong>Value</strong><br />{escape(str(step["value"]))}</div>
    <div><strong>Page URL</strong><br />{escape(str(step["page_url"]))}</div>
  </div>
  <p><strong>Output</strong><br />{escape(str(step["output"]))}</p>
  <p><strong>Error</strong><br />{escape(str(step["error_message"]))}</p>
  {screenshot_html}
</div>
"""
            )

        return (
            "<section><h2>Step Execution</h2><div class='steps'>"
            + "".join(cards)
            + "</div></section>"
        )

    def _render_planner_section(
        self, run_artifacts: RunArtifacts, planner: dict | None
    ) -> str:
        if not planner:
            return ""

        attempts = planner.get("attempts", [])
        attempt_rows = []
        for attempt in attempts:
            raw_relative = self._relative_artifact_path(
                run_artifacts, attempt.get("raw_response_path")
            )
            parsed_relative = self._relative_artifact_path(
                run_artifacts, attempt.get("parsed_plan_path")
            )
            attempt_rows.append(
                f"""
<tr>
  <td>{escape(str(attempt.get("attempt_number")))}</td>
  <td>{self._artifact_link(raw_relative)}</td>
  <td>{self._artifact_link(parsed_relative)}</td>
  <td>{escape(str(attempt.get("error_message")))}</td>
</tr>
"""
            )

        prompt_relative = self._relative_artifact_path(
            run_artifacts, planner.get("prompt_path")
        )
        final_plan_relative = self._relative_artifact_path(
            run_artifacts, planner.get("final_plan_path")
        )

        return (
            "<section><h2>AI Planning</h2>"
            "<div class='summary'>"
            f"<div class='card'><strong>Planner Status</strong><br />{self._status_badge(str(planner.get('status')))}</div>"
            f"<div class='card'><strong>Model</strong><br />{escape(str(planner.get('model')))}</div>"
            f"<div class='card'><strong>Attempt Count</strong><br />{escape(str(planner.get('attempt_count')))}</div>"
            f"<div class='card'><strong>Prompt</strong><br />{self._artifact_link(prompt_relative)}</div>"
            f"<div class='card'><strong>Final Plan</strong><br />{self._artifact_link(final_plan_relative)}</div>"
            "</div>"
            f"<div class='card' style='margin-top: 12px;'><strong>Planner Failure</strong><br />{escape(str(planner.get('failure_reason')))}</div>"
            "<table><thead><tr>"
            "<th>Attempt</th><th>Raw Response</th><th>Parsed JSON</th><th>Error</th>"
            "</tr></thead><tbody>"
            + "".join(attempt_rows)
            + "</tbody></table></section>"
        )

    def _render_assertions_section(self, assertions: list[dict]) -> str:
        if not assertions:
            return ""

        rows = []
        for assertion in assertions:
            rows.append(
                f"""
<tr>
  <td>{escape(str(assertion["index"]))}</td>
  <td>{escape(str(assertion["assertion_type"]))}</td>
  <td>{escape(str(assertion["description"]))}</td>
  <td>{self._status_badge(str(assertion["status"]))}</td>
  <td><span class="mono">{escape(str(assertion["selector"]))}</span></td>
  <td>{escape(str(assertion["expected_value"]))}</td>
  <td>{escape(str(assertion["actual_value"]))}</td>
  <td>{escape(str(assertion["error_message"]))}</td>
</tr>
"""
            )

        return (
            "<section><h2>Assertions</h2><table><thead><tr>"
            "<th>#</th><th>Type</th><th>Description</th><th>Status</th>"
            "<th>Selector</th><th>Expected</th><th>Actual</th><th>Message</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></section>"
        )

    def _render_workflow_section(
        self, run_artifacts: RunArtifacts, workflow: dict | None
    ) -> str:
        if not workflow:
            return ""

        graph_trace_relative = self._relative_artifact_path(
            run_artifacts, workflow.get("graph_trace_path")
        )
        planner_trace_relative = self._relative_artifact_path(
            run_artifacts, workflow.get("planner_trace_path")
        )
        metrics_relative = self._relative_artifact_path(
            run_artifacts, workflow.get("metrics_path")
        )
        tool_trace_relative = self._relative_artifact_path(
            run_artifacts, workflow.get("tool_trace_path")
        )
        history_rows = []
        for item in workflow.get("instruction_history", []):
            history_rows.append(
                f"""
<tr>
  <td>{escape(str(item.get("retry_count")))}</td>
  <td>{escape(str(item.get("reason")))}</td>
  <td>{escape(str(item.get("instruction")))}</td>
</tr>
"""
            )

        history_table = ""
        if history_rows:
            history_table = (
                "<table><thead><tr>"
                "<th>Retry</th><th>Reason</th><th>Instruction</th>"
                "</tr></thead><tbody>"
                + "".join(history_rows)
                + "</tbody></table>"
            )

        return (
            "<section><h2>Workflow</h2>"
            "<div class='summary'>"
            f"<div class='card'><strong>Validation Passed</strong><br />{escape(str(workflow.get('validation_passed')))}</div>"
            f"<div class='card'><strong>Retry Count</strong><br />{escape(str(workflow.get('retry_count')))}</div>"
            f"<div class='card'><strong>Max Retries</strong><br />{escape(str(workflow.get('max_retries')))}</div>"
            f"<div class='card'><strong>Planner Attempts</strong><br />{escape(str(workflow.get('planner_attempt_count')))}</div>"
            f"<div class='card'><strong>Memory Enabled</strong><br />{escape(str(workflow.get('memory_enabled')))}</div>"
            f"<div class='card'><strong>Memory Hits</strong><br />{escape(str(workflow.get('memory_hits')))}</div>"
            f"<div class='card'><strong>Retrieval Count</strong><br />{escape(str(workflow.get('retrieval_count')))}</div>"
            f"<div class='card'><strong>Memory Store</strong><br />{escape(str(workflow.get('memory_store_status')))}</div>"
            f"<div class='card'><strong>MCP Enabled</strong><br />{escape(str(workflow.get('mcp_enabled')))}</div>"
            f"<div class='card'><strong>Tool Tracing</strong><br />{escape(str(workflow.get('tool_tracing_enabled')))}</div>"
            f"<div class='card'><strong>Tool Invocations</strong><br />{escape(str(workflow.get('tool_invocation_count')))}</div>"
            f"<div class='card'><strong>Tool Failures</strong><br />{escape(str(workflow.get('tool_failure_count')))}</div>"
            f"<div class='card'><strong>Graph Trace</strong><br />{self._artifact_link(graph_trace_relative)}</div>"
            f"<div class='card'><strong>Tool Trace</strong><br />{self._artifact_link(tool_trace_relative)}</div>"
            f"<div class='card'><strong>Planner Trace</strong><br />{self._artifact_link(planner_trace_relative)}</div>"
            f"<div class='card'><strong>Metrics</strong><br />{self._artifact_link(metrics_relative)}</div>"
            "</div>"
            f"<div class='card' style='margin-top: 12px;'><strong>Workflow Failure</strong><br />{escape(str(workflow.get('failure_reason')))}</div>"
            f"<div class='card' style='margin-top: 12px;'><strong>Memory Bootstrap</strong><br />{escape(str(workflow.get('memory_bootstrap_error')))}</div>"
            f"<div class='card' style='margin-top: 12px;'><strong>Enabled Tools</strong><br />{escape(str(workflow.get('enabled_tools')))}</div>"
            f"<div class='card' style='margin-top: 12px;'><strong>MCP Bootstrap</strong><br />{escape(str(workflow.get('mcp_bootstrap_error')))}</div>"
            + history_table
            + "</section>"
        )

    def _render_phase1_screenshots(
        self,
        before_relative: str | None,
        after_relative: str | None,
        steps: list[dict],
    ) -> str:
        if steps:
            return ""
        before_html = (
            f"<div class='card'><strong>Before navigation</strong><img src='../{escape(before_relative)}' alt='Before navigation screenshot' /></div>"
            if before_relative
            else "<p>No before screenshot was captured.</p>"
        )
        after_html = (
            f"<div class='card'><strong>After navigation</strong><img src='../{escape(after_relative)}' alt='After navigation screenshot' /></div>"
            if after_relative
            else "<p>No after screenshot was captured.</p>"
        )
        return f"<section><h2>Screenshots</h2>{before_html}{after_html}</section>"
