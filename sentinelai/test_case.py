from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_ACTIONS = {"navigate", "click", "type", "wait", "extract"}
SUPPORTED_ASSERTIONS = {
    "text_exists",
    "element_exists",
    "url_contains",
    "title_contains",
}


def _optional_string(value: object, *, strip: bool = True) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text.strip() if strip else text


def _required_string(value: object, field_name: str) -> str:
    text = _optional_string(value)
    if not text:
        raise ValueError(f"'{field_name}' is required and must be a non-empty string.")
    return text


@dataclass(slots=True)
class TestStep:
    action: str
    description: str
    selector: str | None = None
    value: str | int | float | None = None

    def to_dict(self) -> dict:
        payload = {
            "action": self.action,
            "description": self.description,
        }
        if self.selector is not None:
            payload["selector"] = self.selector
        if self.value is not None:
            payload["value"] = self.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict, index: int) -> TestStep:
        if not isinstance(payload, dict):
            raise ValueError(f"Step {index} must be a JSON object.")

        action = _required_string(payload.get("action"), f"steps[{index}].action").lower()
        if action not in SUPPORTED_ACTIONS:
            raise ValueError(
                f"Unsupported action '{action}' in steps[{index}]. "
                f"Supported actions: {sorted(SUPPORTED_ACTIONS)}"
            )

        description = _optional_string(payload.get("description")) or f"Step {index}: {action}"
        selector = _optional_string(payload.get("selector"))
        value = payload.get("value")

        if action in {"click", "type", "extract"} and not selector:
            raise ValueError(f"steps[{index}].selector is required for '{action}'.")
        if action in {"navigate", "type", "wait"} and (value is None or value == ""):
            raise ValueError(f"steps[{index}].value is required for '{action}'.")
        if action == "wait":
            try:
                wait_ms = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"steps[{index}].value must be an integer number of milliseconds "
                    "for 'wait'."
                ) from exc
            if wait_ms < 0:
                raise ValueError(
                    f"steps[{index}].value must be zero or greater for 'wait'."
                )
            value = wait_ms

        return cls(
            action=action,
            description=description,
            selector=selector,
            value=value,
        )


@dataclass(slots=True)
class TestAssertion:
    assertion_type: str
    description: str
    selector: str | None = None
    value: str | int | float | None = None

    def to_dict(self) -> dict:
        payload = {
            "type": self.assertion_type,
            "description": self.description,
        }
        if self.selector is not None:
            payload["selector"] = self.selector
        if self.value is not None:
            payload["value"] = self.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict, index: int) -> TestAssertion:
        if not isinstance(payload, dict):
            raise ValueError(f"Assertion {index} must be a JSON object.")

        assertion_type = _required_string(
            payload.get("type"), f"assertions[{index}].type"
        ).lower()
        if assertion_type not in SUPPORTED_ASSERTIONS:
            raise ValueError(
                f"Unsupported assertion '{assertion_type}' in assertions[{index}]. "
                f"Supported assertions: {sorted(SUPPORTED_ASSERTIONS)}"
            )

        description = (
            _optional_string(payload.get("description"))
            or f"Assertion {index}: {assertion_type}"
        )
        selector = _optional_string(payload.get("selector"))
        value = payload.get("value")

        if assertion_type == "element_exists" and not selector:
            raise ValueError(
                f"assertions[{index}].selector is required for 'element_exists'."
            )
        if assertion_type in {"text_exists", "url_contains", "title_contains"} and (
            value is None or value == ""
        ):
            raise ValueError(
                f"assertions[{index}].value is required for '{assertion_type}'."
            )

        return cls(
            assertion_type=assertion_type,
            description=description,
            selector=selector,
            value=value,
        )


@dataclass(slots=True)
class TestCase:
    name: str
    description: str
    steps: list[TestStep]
    assertions: list[TestAssertion]
    target_url: str | None = None
    source_path: Path | None = None

    @property
    def instruction(self) -> str:
        return self.description or self.name

    def resolved_target_url(self) -> str:
        if self.target_url:
            return self.target_url
        for step in self.steps:
            if step.action == "navigate" and step.value is not None and step.value != "":
                return str(step.value)
        raise ValueError(
            "The test case must include 'target_url' or at least one 'navigate' step."
        )

    def to_dict(self) -> dict:
        payload = {
            "name": self.name,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
            "assertions": [assertion.to_dict() for assertion in self.assertions],
        }
        if self.target_url is not None:
            payload["target_url"] = self.target_url
        return payload


def build_test_case(
    payload: dict,
    *,
    name: str,
    description: str,
    target_url: str | None = None,
    source_path: Path | None = None,
) -> TestCase:
    if not isinstance(payload, dict):
        raise ValueError("Test case root must be a JSON object.")

    resolved_name = _required_string(name, "name")
    resolved_description = _optional_string(description) or resolved_name
    resolved_target_url = _optional_string(target_url, strip=False)

    steps_payload = payload.get("steps")
    if not isinstance(steps_payload, list) or not steps_payload:
        raise ValueError("'steps' must be a non-empty array.")
    steps = [TestStep.from_dict(step, index) for index, step in enumerate(steps_payload, 1)]

    assertions_payload = payload.get("assertions", [])
    if not isinstance(assertions_payload, list):
        raise ValueError("'assertions' must be an array.")
    assertions = [
        TestAssertion.from_dict(assertion, index)
        for index, assertion in enumerate(assertions_payload, 1)
    ]

    test_case = TestCase(
        name=resolved_name,
        description=resolved_description,
        target_url=resolved_target_url,
        steps=steps,
        assertions=assertions,
        source_path=source_path,
    )
    test_case.resolved_target_url()
    return test_case


def load_test_case(path: str | Path) -> TestCase:
    source_path = Path(path).resolve()
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    return build_test_case(
        payload,
        name=_required_string(payload.get("name"), "name"),
        description=_optional_string(payload.get("description")) or _required_string(
            payload.get("name"), "name"
        ),
        target_url=_optional_string(payload.get("target_url"), strip=False),
        source_path=source_path,
    )
