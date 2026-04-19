from __future__ import annotations

import argparse
import asyncio
import json

from config.settings import BrowserSettings, load_settings
from reporting.run_artifacts import RunArtifactManager


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

    return parser


async def run_phase1(url: str, instruction: str, headed: bool) -> dict:
    from browser.playwright_runner import PlaywrightBrowserRunner

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
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
