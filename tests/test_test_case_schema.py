from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentinelai.test_case import build_test_case
from sentinelai.test_case import load_test_case


def test_valid_testcase_loads_from_file(tmp_path: Path):
    path = tmp_path / "test.json"
    payload = {
        "name": "Login Flow",
        "description": "Check login CTA",
        "target_url": "https://example.com",
        "steps": [
            {
                "action": "navigate",
                "value": "https://example.com",
                "description": "Open site",
            },
            {
                "action": "wait",
                "value": 500,
                "description": "Wait for content",
            },
        ],
        "assertions": [
            {
                "type": "url_contains",
                "value": "example.com",
                "description": "URL should contain example.com",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    test_case = load_test_case(path)

    assert test_case.name == "Login Flow"
    assert test_case.instruction == "Check login CTA"
    assert test_case.resolved_target_url() == "https://example.com"
    assert test_case.steps[1].value == 500


def test_invalid_action_is_rejected():
    payload = {
        "steps": [
            {
                "action": "scroll",
                "value": "https://example.com",
                "description": "Unsupported",
            }
        ],
        "assertions": [],
    }

    with pytest.raises(ValueError, match="Unsupported action"):
        build_test_case(
            payload,
            name="Bad Action",
            description="Should fail",
            target_url="https://example.com",
        )


def test_invalid_assertion_type_is_rejected():
    payload = {
        "steps": [
            {
                "action": "navigate",
                "value": "https://example.com",
                "description": "Open",
            }
        ],
        "assertions": [
            {
                "type": "image_matches",
                "value": "hero",
                "description": "Unsupported",
            }
        ],
    }

    with pytest.raises(ValueError, match="Unsupported assertion"):
        build_test_case(
            payload,
            name="Bad Assertion",
            description="Should fail",
            target_url="https://example.com",
        )


def test_ai_generated_plan_converts_into_internal_testcase():
    ai_plan = {
        "steps": [
            {
                "action": "navigate",
                "value": "https://example.com",
                "description": "Open the page",
            },
            {
                "action": "extract",
                "selector": "h1",
                "value": "text",
                "description": "Read the heading",
            },
        ],
        "assertions": [
            {
                "type": "title_contains",
                "value": "Example Domain",
                "description": "Title check",
            }
        ],
    }

    test_case = build_test_case(
        ai_plan,
        name="AI Planned Test",
        description="Generated from planner",
        target_url="https://example.com",
    )

    assert test_case.steps[0].action == "navigate"
    assert test_case.steps[1].selector == "h1"
    assert test_case.assertions[0].assertion_type == "title_contains"


def test_serialization_helpers_round_trip(sample_test_case):
    payload = sample_test_case.to_dict()
    rebuilt = build_test_case(
        payload,
        name=payload["name"],
        description=payload["description"],
        target_url=payload["target_url"],
    )

    assert rebuilt.to_dict() == payload
    assert rebuilt.steps[0].description == sample_test_case.steps[0].description
