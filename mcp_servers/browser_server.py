from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from playwright.async_api import Page
from playwright.async_api import async_playwright

from browser.playwright_runner import PlaywrightBrowserRunner
from mcp_servers.base import MCPToolServer
from reporting.run_artifacts import RunArtifacts
from sentinelai.test_case import TestCase


class BrowserMCPServer(MCPToolServer):
    name = "browser"

    def __init__(self, runner: PlaywrightBrowserRunner, *, timeout_seconds: int = 90) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.runner = runner

    def _action_handlers(self):
        return {
            "capture_initial_state": self._capture_initial_state,
            "run_test_case": self._run_test_case,
            "open_url": self._open_url,
            "click": self._click,
            "type": self._type_text,
            "wait": self._wait,
            "extract_dom": self._extract_dom,
            "screenshot": self._screenshot,
        }

    async def _capture_initial_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._require_string(payload, "url")
        run_artifacts = self._require_type(payload, "run_artifacts", RunArtifacts)
        result = await self.runner.capture_initial_state(url=url, run_artifacts=run_artifacts)
        return {"result": result}

    async def _run_test_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        test_case = self._require_type(payload, "test_case", TestCase)
        run_artifacts = self._require_type(payload, "run_artifacts", RunArtifacts)
        result = await self.runner.run_test_case(
            test_case=test_case,
            run_artifacts=run_artifacts,
        )
        return {"execution_result": result}

    async def _open_url(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._require_string(payload, "url")

        async def action(page: Page):
            response = await page.goto(url, wait_until=self.runner.settings.wait_until)
            await page.wait_for_load_state("domcontentloaded")
            return {
                "requested_url": url,
                "final_url": page.url,
                "page_title": await self.runner._safe_page_title(page),
                "navigation_status": response.status if response else None,
            }

        return await self._with_page(action=action)

    async def _click(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._require_string(payload, "url")
        selector = self._require_string(payload, "selector")
        wait_ms = int(payload.get("wait_ms", 250))

        async def action(page: Page):
            await page.goto(url, wait_until=self.runner.settings.wait_until)
            await page.wait_for_load_state("domcontentloaded")
            await page.locator(selector).click()
            await page.wait_for_timeout(wait_ms)
            return {
                "final_url": page.url,
                "page_title": await self.runner._safe_page_title(page),
                "selector": selector,
            }

        return await self._with_page(action=action)

    async def _type_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._require_string(payload, "url")
        selector = self._require_string(payload, "selector")
        value = self._require_string(payload, "value")
        wait_ms = int(payload.get("wait_ms", 250))

        async def action(page: Page):
            await page.goto(url, wait_until=self.runner.settings.wait_until)
            await page.wait_for_load_state("domcontentloaded")
            await page.locator(selector).fill(value)
            await page.wait_for_timeout(wait_ms)
            return {
                "final_url": page.url,
                "page_title": await self.runner._safe_page_title(page),
                "selector": selector,
                "value_length": len(value),
            }

        return await self._with_page(action=action)

    async def _wait(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._require_string(payload, "url")
        wait_ms = int(payload.get("value", payload.get("wait_ms", 1000)))

        async def action(page: Page):
            await page.goto(url, wait_until=self.runner.settings.wait_until)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(wait_ms)
            return {
                "final_url": page.url,
                "page_title": await self.runner._safe_page_title(page),
                "wait_ms": wait_ms,
            }

        return await self._with_page(action=action)

    async def _extract_dom(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._require_string(payload, "url")
        output_path = self._resolve_output_path(payload.get("output_path"), suffix=".html")

        async def action(page: Page):
            await page.goto(url, wait_until=self.runner.settings.wait_until)
            await page.wait_for_load_state("domcontentloaded")
            dom = await page.content()
            output_path.write_text(dom, encoding="utf-8")
            return {
                "final_url": page.url,
                "output_path": str(output_path),
                "dom_length": len(dom),
            }

        return await self._with_page(action=action)

    async def _screenshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._require_string(payload, "url")
        full_page = bool(payload.get("full_page", self.runner.settings.screenshot_full_page))
        output_path = self._resolve_output_path(payload.get("output_path"), suffix=".png")

        async def action(page: Page):
            await page.goto(url, wait_until=self.runner.settings.wait_until)
            await page.wait_for_load_state("domcontentloaded")
            await page.screenshot(path=str(output_path), full_page=full_page)
            return {
                "final_url": page.url,
                "output_path": str(output_path),
                "full_page": full_page,
            }

        return await self._with_page(action=action)

    async def _with_page(self, *, action):
        browser = None
        async with async_playwright() as playwright:
            browser, page = await self.runner._open_browser_page(playwright)
            try:
                return await action(page)
            finally:
                if browser is not None:
                    await browser.close()

    def _resolve_output_path(self, raw_path: Any, *, suffix: str) -> Path:
        if raw_path:
            path = Path(str(raw_path)).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        return Path(tempfile.gettempdir()) / f"sentinelai_{uuid4().hex}{suffix}"

    def _require_string(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if value is None or str(value).strip() == "":
            raise ValueError(f"'{key}' is required and must be a non-empty string.")
        return str(value)

    def _require_type(self, payload: dict[str, Any], key: str, expected_type):
        value = payload.get(key)
        if not isinstance(value, expected_type):
            raise ValueError(
                f"'{key}' must be an instance of {expected_type.__name__}."
            )
        return value
