from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone

from config.settings import BrowserSettings, load_settings
from reporting.run_artifacts import RunArtifactManager
from sentinelai.test_case import load_test_case


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SentinelAI CLI for phased autonomous web testing workflows."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    phase1 = subparsers.add_parser(
        "phase1",
        help="Open a URL, capture before/after screenshots, and store baseline artifacts.",
    )
    phase1.add_argument("--url", required=True, help="Target URL to open in the browser.")
    phase1.add_argument(
        "--instruction",
        default="Open the target page and capture a baseline snapshot.",
        help="Human-readable instruction stored with the run metadata.",
    )
    phase1.add_argument(
        "--headed",
        action="store_true",
        help="Launch the browser in headed mode for debugging.",
    )

    phase2 = subparsers.add_parser(
        "phase2",
        help="Run a structured JSON test case with deterministic steps and assertions.",
    )
    phase2.add_argument(
        "--test",
        required=True,
        help="Path to a JSON test case definition.",
    )
    phase2.add_argument(
        "--headed",
        action="store_true",
        help="Launch the browser in headed mode for debugging.",
    )

    phase3 = subparsers.add_parser(
        "phase3",
        help="Generate a structured test plan from natural language using Ollama and execute it.",
    )
    phase3.add_argument("--url", required=True, help="Target URL to test.")
    phase3.add_argument(
        "--instruction",
        required=True,
        help="Natural language instruction for the planner.",
    )
    phase3.add_argument(
        "--model",
        help="Override the configured Ollama model for this run.",
    )
    phase3.add_argument(
        "--headed",
        action="store_true",
        help="Launch the browser in headed mode for debugging.",
    )

    phase4 = subparsers.add_parser(
        "phase4",
        help="Run the LangGraph-based multi-agent workflow with replanning and retries.",
    )
    phase4.add_argument("--url", required=True, help="Target URL to test.")
    phase4.add_argument(
        "--instruction",
        required=True,
        help="Natural language instruction for the workflow planner.",
    )
    phase4.add_argument(
        "--model",
        help="Override the configured Ollama model for this run.",
    )
    phase4.add_argument(
        "--max-retries",
        type=int,
        help="Override the configured workflow retry limit for this run.",
    )
    phase4.add_argument(
        "--headed",
        action="store_true",
        help="Launch the browser in headed mode for debugging.",
    )

    phase5 = subparsers.add_parser(
        "phase5",
        help="Run the LangGraph workflow with persistent memory retrieval and storage.",
    )
    phase5.add_argument("--url", required=True, help="Target URL to test.")
    phase5.add_argument(
        "--instruction",
        required=True,
        help="Natural language instruction for the workflow planner.",
    )
    phase5.add_argument(
        "--model",
        help="Override the configured Ollama model for this run.",
    )
    phase5.add_argument(
        "--max-retries",
        type=int,
        help="Override the configured workflow retry limit for this run.",
    )
    phase5.add_argument(
        "--headed",
        action="store_true",
        help="Launch the browser in headed mode for debugging.",
    )

    phase6 = subparsers.add_parser(
        "phase6",
        help="Run the LangGraph workflow with MCP tool orchestration enabled.",
    )
    phase6.add_argument("--url", required=True, help="Target URL to test.")
    phase6.add_argument(
        "--instruction",
        required=True,
        help="Natural language instruction for the workflow planner.",
    )
    phase6.add_argument(
        "--model",
        help="Override the configured Ollama model for this run.",
    )
    phase6.add_argument(
        "--max-retries",
        type=int,
        help="Override the configured workflow retry limit for this run.",
    )
    phase6.add_argument(
        "--headed",
        action="store_true",
        help="Launch the browser in headed mode for debugging.",
    )

    return parser


def resolve_settings(headed: bool):
    settings = load_settings()
    if headed:
        settings.browser = BrowserSettings(
            headless=False,
            viewport_width=settings.browser.viewport_width,
            viewport_height=settings.browser.viewport_height,
            navigation_timeout_ms=settings.browser.navigation_timeout_ms,
            wait_until=settings.browser.wait_until,
            screenshot_full_page=settings.browser.screenshot_full_page,
        )
    return settings


async def run_phase1(url: str, instruction: str, headed: bool) -> dict:
    from browser.playwright_runner import PlaywrightBrowserRunner

    settings = resolve_settings(headed)
    artifact_manager = RunArtifactManager(settings.storage)
    run_artifacts = artifact_manager.create_run(
        phase="phase1",
        target_url=url,
        instruction=instruction,
    )

    runner = PlaywrightBrowserRunner(settings.browser)
    result = await runner.capture_initial_state(url=url, run_artifacts=run_artifacts)

    report_payload = artifact_manager.build_phase1_payload(
        run_artifacts=run_artifacts,
        result=result,
    )
    json_report_path = artifact_manager.write_json_report(
        run_artifacts=run_artifacts,
        payload=report_payload,
    )
    html_report_path = artifact_manager.write_html_report(
        run_artifacts=run_artifacts,
        payload=report_payload,
    )

    return {
        "status": report_payload["status"],
        "run_id": run_artifacts.context.run_id,
        "requested_url": report_payload["requested_url"],
        "final_url": report_payload["final_url"],
        "json_report": str(json_report_path),
        "html_report": str(html_report_path),
        "run_directory": str(run_artifacts.run_dir),
    }


async def run_phase2(test_file: str, headed: bool) -> dict:
    from browser.playwright_runner import PlaywrightBrowserRunner

    settings = resolve_settings(headed)
    test_case = load_test_case(test_file)
    artifact_manager = RunArtifactManager(settings.storage)
    run_artifacts = artifact_manager.create_run(
        phase="phase2",
        target_url=test_case.resolved_target_url(),
        instruction=test_case.instruction,
    )

    runner = PlaywrightBrowserRunner(settings.browser)
    result = await runner.run_test_case(test_case=test_case, run_artifacts=run_artifacts)

    report_payload = artifact_manager.build_phase2_payload(
        run_artifacts=run_artifacts,
        test_case=test_case,
        result=result,
    )
    json_report_path = artifact_manager.write_json_report(
        run_artifacts=run_artifacts,
        payload=report_payload,
    )
    html_report_path = artifact_manager.write_html_report(
        run_artifacts=run_artifacts,
        payload=report_payload,
    )

    return {
        "status": report_payload["status"],
        "run_id": run_artifacts.context.run_id,
        "test_name": report_payload["test_name"],
        "requested_url": report_payload["requested_url"],
        "final_url": report_payload["final_url"],
        "json_report": str(json_report_path),
        "html_report": str(html_report_path),
        "run_directory": str(run_artifacts.run_dir),
        "failure_reason": report_payload["failure_reason"],
    }


async def run_phase3(
    url: str,
    instruction: str,
    headed: bool,
    model: str | None,
) -> dict:
    from agents.planner_agent import PlannerAgent
    from ai.ollama_client import OllamaClient
    from browser.models import BrowserRunResult
    from browser.playwright_runner import PlaywrightBrowserRunner

    settings = resolve_settings(headed)
    artifact_manager = RunArtifactManager(settings.storage)
    run_artifacts = artifact_manager.create_run(
        phase="phase3",
        target_url=url,
        instruction=instruction,
    )

    planner = PlannerAgent(
        ollama_client=OllamaClient(settings.ollama),
        max_attempts=settings.ollama.max_attempts,
    )
    planner_result = planner.plan(
        url=url,
        instruction=instruction,
        logs_dir=run_artifacts.logs_dir,
        model=model,
    )

    if planner_result.status == "passed" and planner_result.test_case is not None:
        runner = PlaywrightBrowserRunner(settings.browser)
        result = await runner.run_test_case(
            test_case=planner_result.test_case,
            run_artifacts=run_artifacts,
        )
    else:
        started_at = datetime.now(timezone.utc)
        result = BrowserRunResult(
            requested_url=url,
            final_url=None,
            page_title=None,
            navigation_status=None,
            started_at=started_at,
            completed_at=started_at,
            status="failed",
            before_screenshot_path=None,
            after_screenshot_path=None,
            dom_snapshot_path=None,
            error_message=planner_result.failure_reason,
            failure_reason=planner_result.failure_reason,
            test_name="AI Planned Test",
            test_file=(
                str(planner_result.final_plan_path)
                if planner_result.final_plan_path is not None
                else None
            ),
        )

    if planner_result.test_case is not None:
        result.test_name = planner_result.test_case.name
        if planner_result.final_plan_path is not None:
            result.test_file = str(planner_result.final_plan_path)

    report_payload = artifact_manager.build_phase3_payload(
        run_artifacts=run_artifacts,
        result=result,
        planner_result=planner_result,
    )
    json_report_path = artifact_manager.write_json_report(
        run_artifacts=run_artifacts,
        payload=report_payload,
    )
    html_report_path = artifact_manager.write_html_report(
        run_artifacts=run_artifacts,
        payload=report_payload,
    )

    return {
        "status": report_payload["status"],
        "run_id": run_artifacts.context.run_id,
        "test_name": report_payload["test_name"],
        "requested_url": report_payload["requested_url"],
        "final_url": report_payload["final_url"],
        "json_report": str(json_report_path),
        "html_report": str(html_report_path),
        "run_directory": str(run_artifacts.run_dir),
        "failure_reason": report_payload["failure_reason"],
        "planner_status": report_payload["planner"]["status"],
        "planner_model": report_payload["planner"]["model"],
    }


async def run_phase4(
    url: str,
    instruction: str,
    headed: bool,
    model: str | None,
    max_retries: int | None,
    phase_name: str = "phase4",
) -> dict:
    from agents.graph_workflow import LangGraphWorkflow

    settings = resolve_settings(headed)
    workflow = LangGraphWorkflow(settings)
    result = await workflow.execute(
        url=url,
        instruction=instruction,
        model=model,
        max_retries=max_retries,
        phase_name=phase_name,
    )
    return result.to_summary()


async def run_phase5(
    url: str,
    instruction: str,
    headed: bool,
    model: str | None,
    max_retries: int | None,
) -> dict:
    return await run_phase4(
        url=url,
        instruction=instruction,
        headed=headed,
        model=model,
        max_retries=max_retries,
        phase_name="phase5",
    )


async def run_phase6(
    url: str,
    instruction: str,
    headed: bool,
    model: str | None,
    max_retries: int | None,
) -> dict:
    return await run_phase4(
        url=url,
        instruction=instruction,
        headed=headed,
        model=model,
        max_retries=max_retries,
        phase_name="phase6",
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "phase1":
        summary = asyncio.run(
            run_phase1(
                url=args.url,
                instruction=args.instruction,
                headed=args.headed,
            )
        )
    elif args.command == "phase2":
        summary = asyncio.run(
            run_phase2(
                test_file=args.test,
                headed=args.headed,
            )
        )
    elif args.command == "phase3":
        summary = asyncio.run(
            run_phase3(
                url=args.url,
                instruction=args.instruction,
                headed=args.headed,
                model=args.model,
            )
        )
    elif args.command == "phase4":
        summary = asyncio.run(
            run_phase4(
                url=args.url,
                instruction=args.instruction,
                headed=args.headed,
                model=args.model,
                max_retries=args.max_retries,
            )
        )
    elif args.command == "phase5":
        summary = asyncio.run(
            run_phase5(
                url=args.url,
                instruction=args.instruction,
                headed=args.headed,
                model=args.model,
                max_retries=args.max_retries,
            )
        )
    elif args.command == "phase6":
        summary = asyncio.run(
            run_phase6(
                url=args.url,
                instruction=args.instruction,
                headed=args.headed,
                model=args.model,
                max_retries=args.max_retries,
            )
        )
    else:
        raise ValueError(f"Unsupported command '{args.command}'.")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
