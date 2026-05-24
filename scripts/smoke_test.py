from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from agents.graph_workflow import LangGraphWorkflow
    from config.settings import load_settings
    from dashboard.app import create_app
    from jobs.manager import JobManager
    from mcp_servers import MCPToolRegistry
    from memory.memory_manager import MemoryManager
    from sentinelai.test_case import load_test_case

    with tempfile.TemporaryDirectory(prefix="sentinelai_smoke_") as temp_dir:
        temp_root = Path(temp_dir)
        settings = load_settings(project_root=repo_root)
        settings.storage.artifacts_root = temp_root / "artifacts"
        settings.storage.runs_root = settings.storage.artifacts_root / "runs"
        settings.memory.vector_db_path = temp_root / "memory_store"
        settings.auth.sqlite_path = temp_root / "auth_store" / "sentinelai_auth.db"

        sample_test_path = repo_root / "testcases" / "sample_test.json"
        failing_test_path = repo_root / "testcases" / "failing_sample_test.json"
        login_template_path = repo_root / "testcases" / "login_flow_template.json"
        test_case = load_test_case(sample_test_path)
        failing_test_case = load_test_case(failing_test_path)
        login_template = load_test_case(login_template_path)
        memory_manager = MemoryManager(settings.memory)
        registry = MCPToolRegistry(
            enabled=settings.mcp.enabled,
            timeout_seconds=settings.mcp.timeout_seconds,
            enabled_tools=settings.mcp.enabled_tools,
        )
        workflow = LangGraphWorkflow(settings)
        dashboard_app = create_app(settings)
        job_manager = JobManager(settings)
        job_metrics = asyncio.run(job_manager.metrics())

        summary = {
            "settings_loaded": True,
            "sample_testcase_name": test_case.name,
            "sample_testcase_steps": len(test_case.steps),
            "failing_testcase_name": failing_test_case.name,
            "login_template_name": login_template.name,
            "memory_enabled": memory_manager.enabled,
            "mcp_registry_enabled": registry.enabled,
            "graph_compiled": workflow.graph is not None,
            "registered_mcp_servers": workflow.mcp_registry.available_servers(),
            "dashboard_loaded": dashboard_app is not None,
            "dashboard_route_count": len(dashboard_app.router.routes),
            "auth_enabled": settings.auth.enabled,
            "auth_store_path": str(settings.auth.sqlite_path),
            "job_manager_loaded": job_manager is not None,
            "job_worker_running": job_metrics["worker_running"],
            "job_queue_length": job_metrics["queue_length"],
        }
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
