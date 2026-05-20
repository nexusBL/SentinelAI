from __future__ import annotations

from pathlib import Path

from config.settings import MemorySettings
from memory.memory_manager import MemoryManager


def enabled_memory_settings(tmp_path: Path) -> MemorySettings:
    return MemorySettings(
        enabled=True,
        vector_db_path=tmp_path / "memory_store",
        embedding_provider="hashing",
        embedding_model="hashing-384",
        top_k=3,
    )


def test_store_memory_entry_and_retrieve_similar(tmp_path):
    manager = MemoryManager(enabled_memory_settings(tmp_path))

    store_result = manager.store_execution(
        run_id="run-1",
        url="https://example.com",
        instruction="Open homepage and verify title",
        generated_test_plan={"steps": [], "assertions": []},
        execution_summary={"status": "passed"},
        failure_reason=None,
        validation_status="passed",
        retry_count=0,
        final_result="passed",
        tags=["phase5"],
        metadata={"source": "test"},
    )
    retrieval = manager.retrieve_similar(
        url="https://example.com",
        instruction="Verify homepage title",
    )

    assert store_result.status == "stored"
    assert store_result.vector_count == 1
    assert retrieval.status == "passed"
    assert len(retrieval.results) == 1
    assert retrieval.results[0].entry.run_id == "run-1"


def test_persistence_across_manager_reload(tmp_path):
    settings = enabled_memory_settings(tmp_path)
    manager = MemoryManager(settings)
    manager.store_execution(
        run_id="run-1",
        url="https://example.com",
        instruction="Open homepage",
        generated_test_plan={"steps": [], "assertions": []},
        execution_summary={"status": "passed"},
        failure_reason=None,
        validation_status="passed",
        retry_count=0,
        final_result="passed",
    )

    reloaded = MemoryManager(settings)
    retrieval = reloaded.retrieve_similar(
        url="https://example.com",
        instruction="Open homepage",
    )

    assert reloaded.vector_store is not None
    assert reloaded.vector_store.count == 1
    assert len(retrieval.results) == 1


def test_top_k_behavior_limits_results(tmp_path):
    manager = MemoryManager(enabled_memory_settings(tmp_path))
    for index in range(3):
        manager.store_execution(
            run_id=f"run-{index}",
            url="https://example.com",
            instruction=f"Open homepage {index}",
            generated_test_plan={"steps": [], "assertions": []},
            execution_summary={"status": "passed"},
            failure_reason=None,
            validation_status="passed",
            retry_count=0,
            final_result="passed",
        )

    retrieval = manager.retrieve_similar(
        url="https://example.com",
        instruction="Open homepage",
        top_k=2,
    )

    assert len(retrieval.results) == 2
    assert retrieval.top_k == 2


def test_disabled_memory_mode_returns_disabled_result(tmp_path):
    settings = MemorySettings(
        enabled=False,
        vector_db_path=tmp_path / "memory_store",
        embedding_provider="hashing",
        embedding_model="hashing-384",
        top_k=3,
    )
    manager = MemoryManager(settings)

    retrieval = manager.retrieve_similar(
        url="https://example.com",
        instruction="Open homepage",
    )
    store_result = manager.store_execution(
        run_id="run-disabled",
        url="https://example.com",
        instruction="Open homepage",
        generated_test_plan=None,
        execution_summary={},
        failure_reason=None,
        validation_status="passed",
        retry_count=0,
        final_result="passed",
    )

    assert retrieval.status == "disabled"
    assert retrieval.results == []
    assert store_result.status == "disabled"


def test_no_crash_when_memory_store_is_empty(tmp_path):
    manager = MemoryManager(enabled_memory_settings(tmp_path))

    retrieval = manager.retrieve_similar(
        url="https://example.com",
        instruction="Nothing stored yet",
    )

    assert retrieval.status == "passed"
    assert retrieval.results == []
    assert retrieval.prompt_context is None
