from __future__ import annotations

from dashboard.utils import build_memory_summary
from dashboard.utils import build_metrics_summary
from dashboard.utils import build_tools_summary
from dashboard.utils import get_run_detail
from dashboard.utils import list_api_screenshots
from dashboard.utils import list_runs
from dashboard.utils import resolve_run_dir
from dashboard.utils import safe_load_json


def test_safe_load_json_handles_missing_and_malformed_files(tmp_path):
    missing_payload, missing_error = safe_load_json(tmp_path / "missing.json")
    malformed_path = tmp_path / "broken.json"
    malformed_path.write_text("{broken", encoding="utf-8")
    malformed_payload, malformed_error = safe_load_json(malformed_path)

    assert missing_payload is None
    assert missing_error == "missing"
    assert malformed_payload is None
    assert malformed_error is not None
    assert "JSONDecodeError" in malformed_error


def test_list_runs_and_detail_extraction(temp_settings, make_dashboard_run):
    older_run = "20260520T120000000000Z"
    newer_run = "20260520T121500000000Z"
    make_dashboard_run(run_id=older_run, phase="phase5", memory_hits=0, mcp_enabled=False)
    make_dashboard_run(run_id=newer_run, phase="phase6", memory_hits=2, mcp_enabled=True)

    runs = list_runs(temp_settings)
    detail = get_run_detail(temp_settings, newer_run)
    screenshots = list_api_screenshots(temp_settings, newer_run)

    assert [run["run_id"] for run in runs] == [newer_run, older_run]
    assert detail is not None
    assert detail["summary"]["phase"] == "phase6"
    assert detail["summary"]["memory_hits"] == 2
    assert detail["latest_memory_context"] == "Use the prior successful selector strategy."
    assert screenshots is not None
    assert len(screenshots["screenshots"]) == 2


def test_invalid_run_id_is_rejected_safely(temp_settings):
    run_dir = resolve_run_dir(temp_settings.storage.runs_root, "../bad-run")
    screenshots = list_api_screenshots(temp_settings, "../bad-run")

    assert run_dir is None
    assert screenshots is None


def test_memory_tools_and_metrics_summaries_handle_empty_state(temp_settings):
    memory_summary = build_memory_summary(temp_settings)
    tools_summary = build_tools_summary(temp_settings)
    metrics_summary = build_metrics_summary(temp_settings)

    assert memory_summary["entry_count"] == 0
    assert memory_summary["latest_writes"] == []
    assert tools_summary["tool_stats"] == {}
    assert tools_summary["recent_events"] == []
    assert metrics_summary["total_runs"] == 0
    assert metrics_summary["pass_rate"] == 0.0
