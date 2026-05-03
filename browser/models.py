from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class StepExecutionResult:
    index: int
    action: str
    description: str
    selector: str | None
    value: str | int | float | None
    status: str
    started_at: datetime
    completed_at: datetime
    page_url: str | None = None
    screenshot_path: Path | None = None
    output: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "action": self.action,
            "description": self.description,
            "selector": self.selector,
            "value": self.value,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "page_url": self.page_url,
            "screenshot_path": str(self.screenshot_path) if self.screenshot_path else None,
            "output": self.output,
            "error_message": self.error_message,
        }


@dataclass(slots=True)
class AssertionResult:
    index: int
    assertion_type: str
    description: str
    status: str
    selector: str | None = None
    expected_value: str | None = None
    actual_value: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "assertion_type": self.assertion_type,
            "description": self.description,
            "status": self.status,
            "selector": self.selector,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "error_message": self.error_message,
        }


@dataclass(slots=True)
class BrowserRunResult:
    requested_url: str
    final_url: str | None
    page_title: str | None
    navigation_status: int | None
    started_at: datetime
    completed_at: datetime
    status: str
    before_screenshot_path: Path | None
    after_screenshot_path: Path | None
    dom_snapshot_path: Path | None
    error_message: str | None = None
    steps_executed: list[StepExecutionResult] = field(default_factory=list)
    assertion_results: list[AssertionResult] = field(default_factory=list)
    failure_reason: str | None = None
    test_name: str | None = None
    test_file: str | None = None

    def to_dict(self) -> dict:
        return {
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "page_title": self.page_title,
            "navigation_status": self.navigation_status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "status": self.status,
            "before_screenshot_path": (
                str(self.before_screenshot_path) if self.before_screenshot_path else None
            ),
            "after_screenshot_path": (
                str(self.after_screenshot_path) if self.after_screenshot_path else None
            ),
            "dom_snapshot_path": (
                str(self.dom_snapshot_path) if self.dom_snapshot_path else None
            ),
            "error_message": self.error_message,
            "failure_reason": self.failure_reason,
            "test_name": self.test_name,
            "test_file": self.test_file,
            "steps_executed": [step.to_dict() for step in self.steps_executed],
            "assertion_results": [
                assertion.to_dict() for assertion in self.assertion_results
            ],
        }
