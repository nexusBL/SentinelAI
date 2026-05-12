from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from browser.models import BrowserRunResult
from mcp_servers.base import MCPToolServer
from sentinelai.test_case import TestAssertion
from validation.assertions import AssertionEvaluator


class ValidationMCPServer(MCPToolServer):
    name = "validation"

    def __init__(self, *, timeout_seconds: int = 90) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.assertion_evaluator = AssertionEvaluator()

    def _action_handlers(self):
        return {
            "validate_assertions": self._validate_assertions,
            "summarize_validation": self._summarize_validation,
            "extract_failure_reason": self._extract_failure_reason,
        }

    async def _validate_assertions(self, payload: dict[str, Any]) -> dict[str, Any]:
        page = payload.get("page")
        if not isinstance(page, Page):
            raise ValueError("'page' must be a Playwright Page instance.")
        assertions = self._coerce_assertions(payload.get("assertions"))
        results = await self.assertion_evaluator.evaluate(page=page, assertions=assertions)
        status = "passed" if all(result.status == "passed" for result in results) else "failed"
        return {
            "status": status,
            "results": results,
        }

    def _summarize_validation(self, payload: dict[str, Any]) -> dict[str, Any]:
        execution_result = self._require_execution_result(payload)
        validation_passed = execution_result.status == "passed"
        return {
            "status": "passed" if validation_passed else "failed",
            "validation_passed": validation_passed,
            "failure_reason": execution_result.failure_reason,
            "step_count": len(execution_result.steps_executed),
            "assertion_count": len(execution_result.assertion_results),
            "passed_steps": sum(
                1 for step in execution_result.steps_executed if step.status == "passed"
            ),
            "passed_assertions": sum(
                1
                for assertion in execution_result.assertion_results
                if assertion.status == "passed"
            ),
        }

    def _extract_failure_reason(self, payload: dict[str, Any]) -> dict[str, Any]:
        execution_result = payload.get("execution_result")
        fallback_reason = payload.get("fallback_reason") or (
            "Validation failed without an execution result."
        )
        if execution_result is None:
            return {"failure_reason": str(fallback_reason)}
        if not isinstance(execution_result, BrowserRunResult):
            raise ValueError("'execution_result' must be a BrowserRunResult instance.")
        return {
            "failure_reason": execution_result.failure_reason or str(fallback_reason),
        }

    def _require_execution_result(self, payload: dict[str, Any]) -> BrowserRunResult:
        execution_result = payload.get("execution_result")
        if not isinstance(execution_result, BrowserRunResult):
            raise ValueError("'execution_result' must be a BrowserRunResult instance.")
        return execution_result

    def _coerce_assertions(self, raw_assertions: Any) -> list[TestAssertion]:
        if raw_assertions is None:
            return []
        if not isinstance(raw_assertions, list):
            raise ValueError("'assertions' must be a list.")
        assertions: list[TestAssertion] = []
        for index, item in enumerate(raw_assertions, start=1):
            if isinstance(item, TestAssertion):
                assertions.append(item)
            elif isinstance(item, dict):
                assertions.append(TestAssertion.from_dict(item, index))
            else:
                raise ValueError("Each assertion must be a TestAssertion or dict.")
        return assertions
