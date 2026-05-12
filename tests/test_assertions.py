from __future__ import annotations

from validation.assertions import AssertionEvaluator

from .conftest import FakePage
from .conftest import make_assertion


async def test_text_exists_passes():
    evaluator = AssertionEvaluator()
    page = FakePage(body_text="Welcome to Example Domain")

    results = await evaluator.evaluate(
        page=page,
        assertions=[make_assertion(assertion_type="text_exists", value="Example Domain")],
    )

    assert results[0].status == "passed"
    assert results[0].actual_value == "present in page body"


async def test_text_exists_fails_with_clear_message():
    evaluator = AssertionEvaluator()
    page = FakePage(body_text="Welcome to SentinelAI")

    results = await evaluator.evaluate(
        page=page,
        assertions=[make_assertion(assertion_type="text_exists", value="Example Domain")],
    )

    assert results[0].status == "failed"
    assert 'Text "Example Domain" was not found' in str(results[0].error_message)


async def test_element_exists_passes():
    evaluator = AssertionEvaluator()
    page = FakePage(selector_counts={"#login": 1})

    results = await evaluator.evaluate(
        page=page,
        assertions=[
            make_assertion(
                assertion_type="element_exists",
                selector="#login",
                description="Login element should exist",
            )
        ],
    )

    assert results[0].status == "passed"
    assert results[0].actual_value == "1 matching element(s)"


async def test_element_exists_fails_with_clear_message():
    evaluator = AssertionEvaluator()
    page = FakePage(selector_counts={"#login": 0})

    results = await evaluator.evaluate(
        page=page,
        assertions=[make_assertion(assertion_type="element_exists", selector="#login")],
    )

    assert results[0].status == "failed"
    assert 'No elements matched selector "#login".' == results[0].error_message


async def test_url_contains_pass_and_fail():
    evaluator = AssertionEvaluator()

    passing = await evaluator.evaluate(
        page=FakePage(url="https://example.com/dashboard"),
        assertions=[make_assertion(assertion_type="url_contains", value="dashboard")],
    )
    failing = await evaluator.evaluate(
        page=FakePage(url="https://example.com/dashboard"),
        assertions=[make_assertion(assertion_type="url_contains", value="login")],
    )

    assert passing[0].status == "passed"
    assert failing[0].status == "failed"
    assert 'does not contain "login"' in str(failing[0].error_message)


async def test_title_contains_pass_and_fail():
    evaluator = AssertionEvaluator()

    passing = await evaluator.evaluate(
        page=FakePage(title="Example Domain"),
        assertions=[make_assertion(assertion_type="title_contains", value="Example")],
    )
    failing = await evaluator.evaluate(
        page=FakePage(title="Example Domain"),
        assertions=[make_assertion(assertion_type="title_contains", value="Sentinel")],
    )

    assert passing[0].status == "passed"
    assert failing[0].status == "failed"
    assert 'does not contain "Sentinel"' in str(failing[0].error_message)
