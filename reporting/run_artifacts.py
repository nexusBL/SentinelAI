from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from browser.models import BrowserRunResult
from config.settings import StorageSettings
from sentinelai.run_context import RunContext


@dataclass(slots=True)
class RunArtifacts:
    context: RunContext
    run_dir: Path
    screenshots_dir: Path
    logs_dir: Path
    reports_dir: Path


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

        for directory in (
            self.storage_settings.artifacts_root,
            self.storage_settings.runs_root,
            run_dir,
            screenshots_dir,
            logs_dir,
            reports_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

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
        )

    def build_phase1_payload(
        self, run_artifacts: RunArtifacts, result: BrowserRunResult
    ) -> dict:
        return {
            "run_id": run_artifacts.context.run_id,
            "phase": run_artifacts.context.phase,
            "instruction": run_artifacts.context.instruction,
            "requested_url": result.requested_url,
            "final_url": result.final_url,
            "page_title": result.page_title,
            "navigation_status": result.navigation_status,
            "status": result.status,
            "error_message": result.error_message,
            "artifacts": result.to_dict(),
            "created_at": run_artifacts.context.created_at.isoformat(),
        }

    def write_json_report(self, run_artifacts: RunArtifacts, payload: dict) -> Path:
        report_path = run_artifacts.reports_dir / "report.json"
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return report_path

    def write_html_report(self, run_artifacts: RunArtifacts, payload: dict) -> Path:
        report_path = run_artifacts.reports_dir / "report.html"

        before_path = payload["artifacts"]["before_screenshot_path"]
        after_path = payload["artifacts"]["after_screenshot_path"]
        dom_path = payload["artifacts"]["dom_snapshot_path"]

        before_relative = (
            Path(before_path).relative_to(run_artifacts.run_dir).as_posix()
            if before_path
            else None
        )
        after_relative = (
            Path(after_path).relative_to(run_artifacts.run_dir).as_posix()
            if after_path
            else None
        )
        dom_relative = (
            Path(dom_path).relative_to(run_artifacts.run_dir).as_posix()
            if dom_path
            else None
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SentinelAI Report {escape(payload["run_id"])}</title>
  <style>
    body {{
      background: #f3f5f7;
      color: #1d2939;
      font-family: "Segoe UI", sans-serif;
      margin: 0;
      padding: 32px;
    }}
    main {{
      background: #ffffff;
      border-radius: 18px;
      box-shadow: 0 20px 45px rgba(16, 24, 40, 0.08);
      margin: 0 auto;
      max-width: 1080px;
      padding: 32px;
    }}
    h1, h2 {{
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
      border: 1px solid #e4e7ec;
      border-radius: 14px;
      padding: 16px;
    }}
    .status {{
      color: {"#067647" if payload["status"] == "passed" else "#b42318"};
      font-weight: 700;
      text-transform: uppercase;
    }}
    img {{
      border: 1px solid #d0d5dd;
      border-radius: 12px;
      display: block;
      margin-top: 12px;
      max-width: 100%;
    }}
    a {{
      color: #175cd3;
    }}
  </style>
</head>
<body>
  <main>
    <h1>SentinelAI Phase 1 Report</h1>
    <div class="meta">
      <div class="card"><strong>Run ID</strong><br />{escape(payload["run_id"])}</div>
      <div class="card"><strong>Status</strong><br /><span class="status">{escape(payload["status"])}</span></div>
      <div class="card"><strong>Requested URL</strong><br />{escape(str(payload["requested_url"]))}</div>
      <div class="card"><strong>Final URL</strong><br />{escape(str(payload["final_url"]))}</div>
      <div class="card"><strong>Page Title</strong><br />{escape(str(payload["page_title"]))}</div>
      <div class="card"><strong>Instruction</strong><br />{escape(payload["instruction"])}</div>
    </div>
    <section>
      <h2>Screenshots</h2>
      {"<div class='card'><strong>Before navigation</strong><img src='../" + before_relative + "' alt='Before navigation screenshot' /></div>" if before_relative else "<p>No before screenshot was captured.</p>"}
      {"<div class='card'><strong>After navigation</strong><img src='../" + after_relative + "' alt='After navigation screenshot' /></div>" if after_relative else "<p>No after screenshot was captured.</p>"}
    </section>
    <section>
      <h2>Artifacts</h2>
      <p>DOM snapshot: {("<a href='../" + dom_relative + "'>" + escape(dom_relative) + "</a>") if dom_relative else "Not available"}</p>
      <p>Error: {escape(str(payload["error_message"]))}</p>
    </section>
  </main>
</body>
</html>
"""
        report_path.write_text(html, encoding="utf-8")
        return report_path
