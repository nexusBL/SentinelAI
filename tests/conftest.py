from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from ai.ollama_client import OllamaGenerateResult
from browser.models import AssertionResult
from browser.models import BrowserRunResult
from browser.models import StepExecutionResult
from config.settings import load_settings
from sentinelai.test_case import TestAssertion
from sentinelai.test_case import build_test_case


class FakeLocator:
    def __init__(self, *, text: str = "", count: int = 0, html: str = "", value: str = "") -> None:
        self._text = text
        self._count = count
        self._html = html
        self._value = value

    async def inner_text(self) -> str:
        return self._text

    async def count(self) -> int:
        return self._count

    async def inner_html(self) -> str:
        return self._html or self._text

    async def input_value(self) -> str:
        return self._value


class FakePage:
    def __init__(
        self,
        *,
        url: str = "https://example.com/",
        title: str = "Example Domain",
        body_text: str = "Example Domain",
        selector_counts: dict[str, int] | None = None,
    ) -> None:
        self.url = url
        self._title = title
        self._body_text = body_text
        self._selector_counts = selector_counts or {}

    def locator(self, selector: str) -> FakeLocator:
        if selector == "body":
            return FakeLocator(text=self._body_text, count=1, html=self._body_text)
        return FakeLocator(
            text=f"text for {selector}",
            count=self._selector_counts.get(selector, 0),
            html=f"<div>{selector}</div>",
            value=f"value for {selector}",
        )

    async def title(self) -> str:
        return self._title


class FakeOllamaClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.settings = type("Settings", (), {"model": "llama3"})()

    def generate(self, *, prompt: str, system_prompt: str, model: str | None = None):
        response_text = self.responses.pop(0)
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "model": model or self.settings.model,
            }
        )
        return OllamaGenerateResult(
            model=model or self.settings.model,
            response_text=response_text,
            raw_payload={"response": response_text},
            prompt=prompt,
            system_prompt=system_prompt,
        )


@pytest.fixture
def temp_settings(tmp_path: Path):
    settings = load_settings(project_root=tmp_path)
    settings.storage.artifacts_root = tmp_path / "artifacts"
    settings.storage.runs_root = settings.storage.artifacts_root / "runs"
    settings.memory.vector_db_path = tmp_path / "memory_store"
    return settings


@pytest.fixture
def sample_test_case():
    payload = {
        "steps": [
            {
                "action": "navigate",
                "value": "https://example.com",
                "description": "Open the homepage",
            }
        ],
        "assertions": [
            {
                "type": "title_contains",
                "value": "Example Domain",
                "description": "Title should contain Example Domain",
            }
        ],
    }
    return build_test_case(
        payload,
        name="Example Homepage Smoke Test",
        description="Example homepage check",
        target_url="https://example.com",
    )


def make_browser_result(
    *,
    status: str = "passed",
    failure_reason: str | None = None,
    requested_url: str = "https://example.com",
    final_url: str | None = "https://example.com/",
    page_title: str | None = "Example Domain",
    test_name: str = "Example Homepage Smoke Test",
    test_file: str | None = None,
    step_count: int = 1,
    assertion_results: list[AssertionResult] | None = None,
) -> BrowserRunResult:
    started_at = datetime.now(timezone.utc)
    steps = [
        StepExecutionResult(
            index=index,
            action="navigate",
            description=f"Step {index}",
            selector=None,
            value=requested_url,
            status="passed",
            started_at=started_at,
            completed_at=started_at,
            page_url=final_url,
        )
        for index in range(1, step_count + 1)
    ]
    assertions = list(assertion_results or [])
    return BrowserRunResult(
        requested_url=requested_url,
        final_url=final_url,
        page_title=page_title,
        navigation_status=200,
        started_at=started_at,
        completed_at=started_at,
        status=status,
        before_screenshot_path=None,
        after_screenshot_path=None,
        dom_snapshot_path=None,
        failure_reason=failure_reason,
        error_message=failure_reason,
        steps_executed=steps,
        assertion_results=assertions,
        test_name=test_name,
        test_file=test_file,
    )


def make_assertion(
    *,
    assertion_type: str,
    value: str | None = None,
    selector: str | None = None,
    description: str = "assertion",
) -> TestAssertion:
    return TestAssertion(
        assertion_type=assertion_type,
        description=description,
        value=value,
        selector=selector,
    )
