from __future__ import annotations

from datetime import datetime, timezone

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from browser.models import BrowserRunResult
from config.settings import BrowserSettings
from reporting.run_artifacts import RunArtifacts


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
                browser = await playwright.chromium.launch(headless=self.settings.headless)
                page = await browser.new_page(
                    viewport={
                        "width": self.settings.viewport_width,
                        "height": self.settings.viewport_height,
                    }
                )
                page.set_default_navigation_timeout(self.settings.navigation_timeout_ms)
                page.set_default_timeout(self.settings.navigation_timeout_ms)

                await page.screenshot(
                    path=str(before_screenshot_path),
                    full_page=False,
                )

                response = await page.goto(url, wait_until=self.settings.wait_until)
                await page.wait_for_load_state("domcontentloaded")

                dom_snapshot_path.write_text(await page.content(), encoding="utf-8")
                await page.screenshot(
                    path=str(after_screenshot_path),
                    full_page=self.settings.screenshot_full_page,
                )

                completed_at = datetime.now(timezone.utc)
                return BrowserRunResult(
                    requested_url=url,
                    final_url=page.url,
                    page_title=await page.title(),
                    navigation_status=response.status if response else None,
                    started_at=started_at,
                    completed_at=completed_at,
                    status="passed",
                    before_screenshot_path=before_screenshot_path,
                    after_screenshot_path=after_screenshot_path,
                    dom_snapshot_path=dom_snapshot_path,
                )
        except (PlaywrightError, Exception) as exc:
            completed_at = datetime.now(timezone.utc)
            return BrowserRunResult(
                requested_url=url,
                final_url=page.url if page is not None else None,
                page_title=None,
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
            )
        finally:
            if browser is not None:
                await browser.close()
