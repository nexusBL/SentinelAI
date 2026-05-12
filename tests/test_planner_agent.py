from __future__ import annotations

from pathlib import Path

from agents.planner_agent import PlannerAgent

from .conftest import FakeOllamaClient


def test_valid_json_response_creates_test_plan(tmp_path: Path):
    client = FakeOllamaClient(
        [
            (
                '{"steps":[{"action":"navigate","value":"https://example.com",'
                '"description":"Open homepage"}],'
                '"assertions":[{"type":"title_contains","value":"Example Domain",'
                '"description":"Title check"}]}'
            )
        ]
    )
    planner = PlannerAgent(client, max_attempts=2)

    result = planner.plan(
        url="https://example.com",
        instruction="Test the homepage",
        logs_dir=tmp_path,
    )

    assert result.status == "passed"
    assert result.test_case is not None
    assert result.final_plan_path is not None and result.final_plan_path.exists()
    assert result.test_case.steps[0].action == "navigate"
    assert result.test_case.assertions[0].assertion_type == "title_contains"


def test_invalid_json_triggers_retry(tmp_path: Path):
    client = FakeOllamaClient(
        [
            "not valid json",
            (
                '{"steps":[{"action":"navigate","value":"https://example.com",'
                '"description":"Open homepage"}],"assertions":[]}'
            ),
        ]
    )
    planner = PlannerAgent(client, max_attempts=2)

    result = planner.plan(
        url="https://example.com",
        instruction="Retry invalid JSON",
        logs_dir=tmp_path,
    )

    assert result.status == "passed"
    assert len(result.attempts) == 2
    assert result.attempts[0].error_message is not None
    assert len(client.calls) == 2
    assert "Validation error:" in client.calls[1]["prompt"]


def test_schema_breaking_output_is_rejected(tmp_path: Path):
    client = FakeOllamaClient(
        [
            '{"steps":[{"action":"navigate","value":"https://example.com","description":"Open"}],"extra":"bad"}'
        ]
    )
    planner = PlannerAgent(client, max_attempts=1)

    result = planner.plan(
        url="https://example.com",
        instruction="Reject unsupported keys",
        logs_dir=tmp_path,
    )

    assert result.status == "failed"
    assert "unsupported top-level keys" in str(result.failure_reason)


def test_planner_metadata_is_recorded(tmp_path: Path):
    client = FakeOllamaClient(
        [
            '{"steps":[{"action":"navigate","value":"https://example.com","description":"Open"}],"assertions":[]}'
        ]
    )
    planner = PlannerAgent(client, max_attempts=1)

    result = planner.plan(
        url="https://example.com",
        instruction="Record metadata",
        logs_dir=tmp_path,
    )

    assert result.prompt_path is not None and result.prompt_path.exists()
    assert result.attempts[0].raw_response_path is not None
    assert result.attempts[0].raw_response_path.exists()
    assert result.final_plan_path is not None and result.final_plan_path.exists()
    assert "status" in result.to_dict()


def test_memory_context_is_included_when_provided(tmp_path: Path):
    client = FakeOllamaClient(
        [
            '{"steps":[{"action":"navigate","value":"https://example.com","description":"Open"}],"assertions":[]}'
        ]
    )
    planner = PlannerAgent(client, max_attempts=1)
    memory_context = "Previous selector #login failed, prefer button[type=submit]."

    result = planner.plan(
        url="https://example.com",
        instruction="Use memory context",
        logs_dir=tmp_path,
        memory_context=memory_context,
    )

    prompt_text = result.prompt_path.read_text(encoding="utf-8") if result.prompt_path else ""
    assert "Relevant memory from previous runs:" in prompt_text
    assert memory_context in prompt_text
    assert memory_context in client.calls[0]["prompt"]
