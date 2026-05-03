from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from browser.models import StepExecutionResult
from reporting.run_artifacts import RunArtifacts
from sentinelai.test_case import TestStep


class StepExecutor:
    def __init__(self, wait_until: str, screenshot_full_page: bool) -> None:
        self.wait_until = wait_until
        self.screenshot_full_page = screenshot_full_page
        self.last_navigation_status: int | None = None

    async def execute_steps(
        self, page: Page, steps: list[TestStep], run_artifacts: RunArtifacts
    ) -> list[StepExecutionResult]:
        results: list[StepExecutionResult] = []
        for index, step in enumerate(steps, start=1):
            result = await self._execute_single_step(
                page=page,
                step=step,
                index=index,
                run_artifacts=run_artifacts,
            )
            results.append(result)
            if result.status == "failed":
                break
        return results

    async def _execute_single_step(
        self, page: Page, step: TestStep, index: int, run_artifacts: RunArtifacts
    ) -> StepExecutionResult:
        started_at = datetime.now(timezone.utc)

        try:
            output = await self._perform_action(page=page, step=step)
            screenshot_path = await self._capture_step_screenshot(
                page=page,
                index=index,
                action=step.action,
                status="passed",
                run_artifacts=run_artifacts,
            )
            completed_at = datetime.now(timezone.utc)
            return StepExecutionResult(
                index=index,
                action=step.action,
                description=step.description,
                selector=step.selector,
                value=step.value,
                status="passed",
                started_at=started_at,
                completed_at=completed_at,
                page_url=page.url,
                screenshot_path=screenshot_path,
                output=output,
            )
        except (PlaywrightError, Exception) as exc:
            screenshot_path = await self._capture_step_screenshot(
                page=page,
                index=index,
                action=step.action,
                status="failed",
                run_artifacts=run_artifacts,
            )
            completed_at = datetime.now(timezone.utc)
            return StepExecutionResult(
                index=index,
                action=step.action,
                description=step.description,
                selector=step.selector,
                value=step.value,
                status="failed",
                started_at=started_at,
                completed_at=completed_at,
                page_url=page.url if not page.is_closed() else None,
                screenshot_path=screenshot_path,
                error_message=f"{type(exc).__name__}: {exc}",
            )

    async def _perform_action(self, page: Page, step: TestStep) -> str | None:
        if step.action == "navigate":
            response = await page.goto(str(step.value), wait_until=self.wait_until)
            await page.wait_for_load_state("domcontentloaded")
            self.last_navigation_status = response.status if response else None
            return f"Navigated to {page.url} (status: {self.last_navigation_status})"

        if step.action == "click":
            await page.locator(str(step.selector)).click()
            await page.wait_for_timeout(250)
            return f"Clicked {step.selector}"

        if step.action == "type":
            await page.locator(str(step.selector)).fill(str(step.value))
            await page.wait_for_timeout(250)
            return f"Filled {step.selector}"

        if step.action == "wait":
            wait_ms = int(step.value)
            await page.wait_for_timeout(wait_ms)
            return f"Waited {wait_ms} ms"

        if step.action == "extract":
            locator = page.locator(str(step.selector))
            mode = str(step.value).strip().lower() if step.value is not None else "text"
            if mode in {"text", "inner_text"}:
                return await locator.inner_text()
            if mode in {"html", "inner_html"}:
                return await locator.inner_html()
            if mode == "value":
                return await locator.input_value()
            raise ValueError(
                f"Unsupported extract mode '{mode}'. Use text, html, or value."
            )

        raise ValueError(f"Unsupported step action '{step.action}'.")

    async def _capture_step_screenshot(
        self,
        page: Page,
        index: int,
        action: str,
        status: str,
        run_artifacts: RunArtifacts,
    ) -> Path | None:
        if page.is_closed():
            return None

        safe_action = re.sub(r"[^a-z0-9]+", "_", action.lower()).strip("_") or "step"
        screenshot_path = (
            run_artifacts.screenshots_dir
            / f"step_{index:02d}_{safe_action}_{status}.png"
        )
        await page.screenshot(
            path=str(screenshot_path),
            full_page=self.screenshot_full_page,
        )
        return screenshot_path
