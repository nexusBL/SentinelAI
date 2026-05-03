from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import Playwright
from playwright.async_api import async_playwright

from agents.step_executor import StepExecutor
from browser.models import BrowserRunResult
from config.settings import BrowserSettings
from reporting.run_artifacts import RunArtifacts
from sentinelai.test_case import TestCase
from validation.assertions import AssertionEvaluator


class PlaywrightBrowserRunner:
    def __init__(self, settings: BrowserSettings) -> None:
        self.settings = settings

    async def capture_initial_state(
        self, url: str, run_artifacts: RunArtifacts
    ) -> BrowserRunResult:
        started_at = datetime.now(timezone.utc)
        before_screenshot_path = run_artifacts.screenshots_dir / "01_before_navigation.png"
        after_screenshot_path = run_artifacts.screenshots_dir / "02_after_navigation.png"
        dom_snapshot_path = run_artifacts.logs_dir / "page_dom.html"
        browser = None
        page = None

        try:
            async with async_playwright() as playwright:
                browser, page = await self._open_browser_page(playwright)

                await page.screenshot(
                    path=str(before_screenshot_path),
                    full_page=False,
                )

                response = await page.goto(url, wait_until=self.settings.wait_until)
                await page.wait_for_load_state("domcontentloaded")

                dom_snapshot = await self._capture_dom_snapshot(page, dom_snapshot_path)
                await page.screenshot(
                    path=str(after_screenshot_path),
                    full_page=self.settings.screenshot_full_page,
                )

                completed_at = datetime.now(timezone.utc)
                return BrowserRunResult(
                    requested_url=url,
                    final_url=page.url,
                    page_title=await self._safe_page_title(page),
                    navigation_status=response.status if response else None,
                    started_at=started_at,
                    completed_at=completed_at,
                    status="passed",
                    before_screenshot_path=before_screenshot_path,
                    after_screenshot_path=after_screenshot_path,
                    dom_snapshot_path=dom_snapshot,
                )
        except (PlaywrightError, Exception) as exc:
            completed_at = datetime.now(timezone.utc)
            return BrowserRunResult(
                requested_url=url,
                final_url=page.url if page is not None else None,
                page_title=await self._safe_page_title(page),
                navigation_status=None,
                started_at=started_at,
                completed_at=completed_at,
                status="failed",
                before_screenshot_path=(
                    before_screenshot_path if before_screenshot_path.exists() else None
                ),
                after_screenshot_path=(
                    after_screenshot_path if after_screenshot_path.exists() else None
                ),
                dom_snapshot_path=(
                    dom_snapshot_path if dom_snapshot_path.exists() else None
                ),
                error_message=f"{type(exc).__name__}: {exc}",
                failure_reason=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if browser is not None:
                await browser.close()

    async def run_test_case(
        self, test_case: TestCase, run_artifacts: RunArtifacts
    ) -> BrowserRunResult:
        started_at = datetime.now(timezone.utc)
        dom_snapshot_path = run_artifacts.logs_dir / "page_dom.html"
        browser = None
        page = None
        step_executor = StepExecutor(
            wait_until=self.settings.wait_until,
            screenshot_full_page=self.settings.screenshot_full_page,
        )
        assertion_evaluator = AssertionEvaluator()
        step_results = []
        assertion_results = []

        try:
            async with async_playwright() as playwright:
                browser, page = await self._open_browser_page(playwright)
                step_results = await step_executor.execute_steps(
                    page=page,
                    steps=test_case.steps,
                    run_artifacts=run_artifacts,
                )

                failed_step = next(
                    (step for step in step_results if step.status == "failed"),
                    None,
                )
                failure_reason = None
                if failed_step is None:
                    assertion_results = await assertion_evaluator.evaluate(
                        page=page,
                        assertions=test_case.assertions,
                    )
                    failed_assertion = next(
                        (
                            assertion
                            for assertion in assertion_results
                            if assertion.status == "failed"
                        ),
                        None,
                    )
                    if failed_assertion is not None:
                        failure_reason = (
                            f"Assertion {failed_assertion.index} failed: "
                            f"{failed_assertion.description}. "
                            f"{failed_assertion.error_message or ''}".strip()
                        )
                else:
                    failure_reason = (
                        f"Step {failed_step.index} failed: {failed_step.description}. "
                        f"{failed_step.error_message or ''}".strip()
                    )

                dom_snapshot = await self._capture_dom_snapshot(page, dom_snapshot_path)
                completed_at = datetime.now(timezone.utc)
                return BrowserRunResult(
                    requested_url=test_case.resolved_target_url(),
                    final_url=page.url,
                    page_title=await self._safe_page_title(page),
                    navigation_status=step_executor.last_navigation_status,
                    started_at=started_at,
                    completed_at=completed_at,
                    status="failed" if failure_reason else "passed",
                    before_screenshot_path=self._coerce_path(
                        step_results[0].screenshot_path if step_results else None
                    ),
                    after_screenshot_path=self._coerce_path(
                        step_results[-1].screenshot_path if step_results else None
                    ),
                    dom_snapshot_path=dom_snapshot,
                    steps_executed=step_results,
                    assertion_results=assertion_results,
                    failure_reason=failure_reason,
                    test_name=test_case.name,
                    test_file=str(test_case.source_path) if test_case.source_path else None,
                )
        except (PlaywrightError, Exception) as exc:
            dom_snapshot = await self._capture_dom_snapshot(page, dom_snapshot_path)
            completed_at = datetime.now(timezone.utc)
            return BrowserRunResult(
                requested_url=test_case.resolved_target_url(),
                final_url=page.url if page is not None else None,
                page_title=await self._safe_page_title(page),
                navigation_status=step_executor.last_navigation_status,
                started_at=started_at,
                completed_at=completed_at,
                status="failed",
                before_screenshot_path=self._coerce_path(
                    step_results[0].screenshot_path if step_results else None
                ),
                after_screenshot_path=self._coerce_path(
                    step_results[-1].screenshot_path if step_results else None
                ),
                dom_snapshot_path=dom_snapshot,
                error_message=f"{type(exc).__name__}: {exc}",
                steps_executed=step_results,
                assertion_results=assertion_results,
                failure_reason=f"Runtime failure: {type(exc).__name__}: {exc}",
                test_name=test_case.name,
                test_file=str(test_case.source_path) if test_case.source_path else None,
            )
        finally:
            if browser is not None:
                await browser.close()

    async def _open_browser_page(self, playwright: Playwright):
        browser = await playwright.chromium.launch(headless=self.settings.headless)
        page = await browser.new_page(
            viewport={
                "width": self.settings.viewport_width,
                "height": self.settings.viewport_height,
            }
        )
        page.set_default_navigation_timeout(self.settings.navigation_timeout_ms)
        page.set_default_timeout(self.settings.navigation_timeout_ms)
        return browser, page

    async def _capture_dom_snapshot(
        self, page: Page | None, output_path: Path
    ) -> Path | None:
        if page is None or page.is_closed():
            return output_path if output_path.exists() else None
        try:
            output_path.write_text(await page.content(), encoding="utf-8")
            return output_path
        except (PlaywrightError, Exception):
            return output_path if output_path.exists() else None

    async def _safe_page_title(self, page: Page | None) -> str | None:
        if page is None or page.is_closed():
            return None
        try:
            return await page.title()
        except (PlaywrightError, Exception):
            return None

    def _coerce_path(self, path_value: str | Path | None) -> Path | None:
        return Path(path_value) if path_value else None
