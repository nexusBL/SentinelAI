from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from main import build_parser


def test_all_phase_commands_exist():
    parser = build_parser()
    commands = set(parser._subparsers._group_actions[0].choices.keys())

    assert {"phase1", "phase2", "phase3", "phase4", "phase5", "phase6"} <= commands


def test_imports_work_for_old_and_new_phases():
    from agents.graph_workflow import LangGraphWorkflow
    from agents.planner_agent import PlannerAgent
    from config.settings import load_settings
    from main import run_phase1
    from main import run_phase2
    from main import run_phase3
    from main import run_phase4
    from main import run_phase5
    from main import run_phase6

    assert load_settings is not None
    assert PlannerAgent is not None
    assert LangGraphWorkflow is not None
    assert run_phase1 is not None
    assert run_phase2 is not None
    assert run_phase3 is not None
    assert run_phase4 is not None
    assert run_phase5 is not None
    assert run_phase6 is not None


def test_help_output_works_for_all_phases():
    repo_root = Path(__file__).resolve().parents[1]
    main_path = repo_root / "main.py"

    for command in ("phase1", "phase2", "phase3", "phase4", "phase5", "phase6"):
        result = subprocess.run(
            [sys.executable, str(main_path), command, "--help"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()


def test_old_phases_do_not_require_optional_mcp_runtime(monkeypatch):
    monkeypatch.setenv("SENTINELAI_MCP_ENABLED", "false")

    from config.settings import load_settings

    settings = load_settings()
    assert settings.mcp.enabled is False
