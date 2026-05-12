from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from ai.ollama_client import OllamaClient
from ai.ollama_client import OllamaClientError
from sentinelai.test_case import SUPPORTED_ACTIONS
from sentinelai.test_case import SUPPORTED_ASSERTIONS
from sentinelai.test_case import TestCase
from sentinelai.test_case import build_test_case


@dataclass(slots=True)
class PlannerAttempt:
    attempt_number: int
    raw_response: str | None
    raw_response_path: Path | None
    parsed_plan: dict | None = None
    parsed_plan_path: Path | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "attempt_number": self.attempt_number,
            "raw_response_path": (
                str(self.raw_response_path) if self.raw_response_path else None
            ),
            "parsed_plan_path": (
                str(self.parsed_plan_path) if self.parsed_plan_path else None
            ),
            "error_message": self.error_message,
        }


@dataclass(slots=True)
class PlannerAgentResult:
    status: str
    model: str
    attempts: list[PlannerAttempt]
    prompt_path: Path | None
    final_plan_path: Path | None = None
    test_case: TestCase | None = None
    final_plan: dict | None = None
    failure_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "model": self.model,
            "prompt_path": str(self.prompt_path) if self.prompt_path else None,
            "final_plan_path": str(self.final_plan_path) if self.final_plan_path else None,
            "failure_reason": self.failure_reason,
            "attempt_count": len(self.attempts),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }


class PlannerAgent:
    def __init__(self, ollama_client: OllamaClient, max_attempts: int = 3) -> None:
        self.ollama_client = ollama_client
        self.max_attempts = max(1, max_attempts)

    def plan(
        self,
        *,
        url: str,
        instruction: str,
        logs_dir: Path,
        model: str | None = None,
        memory_context: str | None = None,
    ) -> PlannerAgentResult:
        resolved_model = model or self.ollama_client.settings.model
        system_prompt = self._build_system_prompt()
        base_prompt = self._build_user_prompt(
            url=url,
            instruction=instruction,
            memory_context=memory_context,
        )
        prompt_path = logs_dir / "planner_prompt.txt"
        prompt_path.write_text(
            f"[system]\n{system_prompt}\n\n[user]\n{base_prompt}\n",
            encoding="utf-8",
        )

        attempts: list[PlannerAttempt] = []
        validation_error: str | None = None

        for attempt_number in range(1, self.max_attempts + 1):
            prompt = self._retry_prompt(
                base_prompt=base_prompt,
                previous_error=validation_error,
            )
            try:
                generate_result = self.ollama_client.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=resolved_model,
                )
            except OllamaClientError as exc:
                attempt = PlannerAttempt(
                    attempt_number=attempt_number,
                    raw_response=None,
                    raw_response_path=None,
                    error_message=str(exc),
                )
                attempts.append(attempt)
                self._write_text(
                    logs_dir / f"planner_attempt_{attempt_number:02d}_error.txt",
                    str(exc),
                )
                return PlannerAgentResult(
                    status="failed",
                    model=resolved_model,
                    attempts=attempts,
                    prompt_path=prompt_path,
                    failure_reason=str(exc),
                )

            raw_response_path = self._write_text(
                logs_dir / f"planner_attempt_{attempt_number:02d}_raw.txt",
                generate_result.response_text,
            )
            parsed_plan_path: Path | None = None
            try:
                parsed_plan = self._parse_plan(generate_result.response_text)
                parsed_plan_path = self._write_json(
                    logs_dir / f"planner_attempt_{attempt_number:02d}_parsed.json",
                    parsed_plan,
                )
                test_case = build_test_case(
                    parsed_plan,
                    name=self._build_test_name(url=url, instruction=instruction),
                    description=instruction,
                    target_url=url,
                )
                final_plan = test_case.to_dict()
                final_plan_path = self._write_json(
                    logs_dir / "final_test_plan.json",
                    final_plan,
                )
                test_case.source_path = final_plan_path
                attempts.append(
                    PlannerAttempt(
                        attempt_number=attempt_number,
                        raw_response=generate_result.response_text,
                        raw_response_path=raw_response_path,
                        parsed_plan=parsed_plan,
                        parsed_plan_path=parsed_plan_path,
                    )
                )
                return PlannerAgentResult(
                    status="passed",
                    model=resolved_model,
                    attempts=attempts,
                    prompt_path=prompt_path,
                    final_plan_path=final_plan_path,
                    test_case=test_case,
                    final_plan=final_plan,
                )
            except (json.JSONDecodeError, ValueError) as exc:
                validation_error = str(exc)
                attempts.append(
                    PlannerAttempt(
                        attempt_number=attempt_number,
                        raw_response=generate_result.response_text,
                        raw_response_path=raw_response_path,
                        parsed_plan_path=parsed_plan_path,
                        error_message=validation_error,
                    )
                )
                self._write_text(
                    logs_dir / f"planner_attempt_{attempt_number:02d}_validation_error.txt",
                    validation_error,
                )

        return PlannerAgentResult(
            status="failed",
            model=resolved_model,
            attempts=attempts,
            prompt_path=prompt_path,
            failure_reason=(
                f"Planner failed after {self.max_attempts} attempts. "
                f"Last validation error: {validation_error}"
            ),
        )

    def _build_system_prompt(self) -> str:
        return (
            "You are SentinelAI's deterministic planning engine. "
            "Return only valid JSON. "
            "Do not include markdown, prose, comments, or code fences. "
            "The root object must contain exactly two keys: `steps` and `assertions`. "
            f"Allowed step actions: {sorted(SUPPORTED_ACTIONS)}. "
            "Action rules: "
            "`navigate` requires `value` as an absolute URL string and no selector. "
            "`click` requires `selector`. "
            "`type` requires `selector` and `value`. "
            "`wait` requires `value` as an integer number of milliseconds. "
            "`extract` requires `selector` and `value` set to one of `text`, `html`, or `value`. "
            f"Allowed assertion types: {sorted(SUPPORTED_ASSERTIONS)}. "
            "Assertion rules: "
            "`text_exists` requires `value`. "
            "`element_exists` requires `selector`. "
            "`url_contains` requires `value`. "
            "`title_contains` requires `value`. "
            "Always include a first `navigate` step to the provided URL. "
            "Prefer simple CSS selectors over brittle selectors. "
            "Only create assertions you can justify from the instruction."
        )

    def _build_user_prompt(
        self,
        *,
        url: str,
        instruction: str,
        memory_context: str | None = None,
    ) -> str:
        prompt = (
            "Generate a web test plan for this target.\n"
            f"URL: {url}\n"
            f"Instruction: {instruction}\n"
            "Required JSON schema:\n"
            "{\n"
            '  "steps": [\n'
            "    {\n"
            '      "action": "navigate|click|type|wait|extract",\n'
            '      "selector": "optional CSS selector",\n'
            '      "value": "optional input value",\n'
            '      "description": "human-readable step description"\n'
            "    }\n"
            "  ],\n"
            '  "assertions": [\n'
            "    {\n"
            '      "type": "text_exists|element_exists|url_contains|title_contains",\n'
            '      "selector": "optional CSS selector",\n'
            '      "value": "optional expected value",\n'
            '      "description": "human-readable assertion description"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Return JSON only."
        )
        if not memory_context:
            return prompt
        return (
            f"{prompt}\n"
            "Relevant memory from previous runs:\n"
            f"{memory_context}\n"
            "Use this memory to avoid repeating past failures and to prefer strategies "
            "that previously succeeded when they fit the current page."
        )

    def _retry_prompt(self, *, base_prompt: str, previous_error: str | None) -> str:
        if not previous_error:
            return base_prompt
        return (
            f"{base_prompt}\n"
            "The previous response failed validation.\n"
            f"Validation error: {previous_error}\n"
            "Return corrected JSON only."
        )

    def _parse_plan(self, response_text: str) -> dict:
        payload = json.loads(response_text)
        if not isinstance(payload, dict):
            raise ValueError("Planner response root must be a JSON object.")

        allowed_keys = {"steps", "assertions"}
        unexpected_keys = sorted(set(payload.keys()) - allowed_keys)
        if unexpected_keys:
            raise ValueError(
                f"Planner response contained unsupported top-level keys: {unexpected_keys}"
            )
        if "steps" not in payload:
            raise ValueError("Planner response must include a `steps` array.")
        if "assertions" not in payload:
            payload["assertions"] = []
        return payload

    def _build_test_name(self, *, url: str, instruction: str) -> str:
        hostname = urlparse(url).netloc or "target"
        trimmed_instruction = " ".join(instruction.split())
        if trimmed_instruction:
            return f"AI Planned Test - {trimmed_instruction[:48]}"
        return f"AI Planned Test - {hostname}"

    def _write_text(self, path: Path, content: str) -> Path:
        path.write_text(content, encoding="utf-8")
        return path

    def _write_json(self, path: Path, payload: dict) -> Path:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
