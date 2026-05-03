from __future__ import annotations

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from browser.models import AssertionResult
from sentinelai.test_case import TestAssertion


class AssertionEvaluator:
    async def evaluate(
        self, page: Page, assertions: list[TestAssertion]
    ) -> list[AssertionResult]:
        results: list[AssertionResult] = []
        for index, assertion in enumerate(assertions, start=1):
            results.append(await self._evaluate_single(page, assertion, index))
        return results

    async def _evaluate_single(
        self, page: Page, assertion: TestAssertion, index: int
    ) -> AssertionResult:
        try:
            if assertion.assertion_type == "text_exists":
                body_text = await page.locator("body").inner_text()
                expected = str(assertion.value)
                passed = expected in body_text
                return self._build_result(
                    index=index,
                    assertion=assertion,
                    passed=passed,
                    expected_value=expected,
                    actual_value="present in page body" if passed else "not found in page body",
                    error_message=(
                        None
                        if passed
                        else f'Text "{expected}" was not found in the page body.'
                    ),
                )

            if assertion.assertion_type == "element_exists":
                selector = str(assertion.selector)
                match_count = await page.locator(selector).count()
                passed = match_count > 0
                return self._build_result(
                    index=index,
                    assertion=assertion,
                    passed=passed,
                    expected_value="at least 1 matching element",
                    actual_value=f"{match_count} matching element(s)",
                    error_message=(
                        None
                        if passed
                        else f'No elements matched selector "{selector}".'
                    ),
                )

            if assertion.assertion_type == "url_contains":
                expected = str(assertion.value)
                current_url = page.url
                passed = expected in current_url
                return self._build_result(
                    index=index,
                    assertion=assertion,
                    passed=passed,
                    expected_value=expected,
                    actual_value=current_url,
                    error_message=(
                        None
                        if passed
                        else f'Current URL "{current_url}" does not contain "{expected}".'
                    ),
                )

            if assertion.assertion_type == "title_contains":
                expected = str(assertion.value)
                page_title = await page.title()
                passed = expected in page_title
                return self._build_result(
                    index=index,
                    assertion=assertion,
                    passed=passed,
                    expected_value=expected,
                    actual_value=page_title,
                    error_message=(
                        None
                        if passed
                        else f'Page title "{page_title}" does not contain "{expected}".'
                    ),
                )

            raise ValueError(f"Unsupported assertion type '{assertion.assertion_type}'.")
        except (PlaywrightError, Exception) as exc:
            return AssertionResult(
                index=index,
                assertion_type=assertion.assertion_type,
                description=assertion.description,
                status="failed",
                selector=assertion.selector,
                expected_value=(
                    str(assertion.value)
                    if assertion.value is not None and assertion.value != ""
                    else assertion.selector
                ),
                error_message=f"{type(exc).__name__}: {exc}",
            )

    def _build_result(
        self,
        index: int,
        assertion: TestAssertion,
        passed: bool,
        expected_value: str,
        actual_value: str,
        error_message: str | None,
    ) -> AssertionResult:
        return AssertionResult(
            index=index,
            assertion_type=assertion.assertion_type,
            description=assertion.description,
            status="passed" if passed else "failed",
            selector=assertion.selector,
            expected_value=expected_value,
            actual_value=actual_value,
            error_message=error_message,
        )
