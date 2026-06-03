from __future__ import annotations

from pathlib import Path

from config.settings import load_settings


ENV_KEYS = [
    "SENTINELAI_BROWSER_HEADLESS",
    "SENTINELAI_BROWSER_VIEWPORT_WIDTH",
    "SENTINELAI_BROWSER_VIEWPORT_HEIGHT",
    "SENTINELAI_BROWSER_NAVIGATION_TIMEOUT_MS",
    "SENTINELAI_BROWSER_WAIT_UNTIL",
    "SENTINELAI_ARTIFACTS_DIR",
    "SENTINELAI_OLLAMA_ENDPOINT",
    "SENTINELAI_OLLAMA_MODEL",
    "SENTINELAI_OLLAMA_TIMEOUT_SECONDS",
    "SENTINELAI_OLLAMA_MAX_ATTEMPTS",
    "SENTINELAI_GRAPH_MAX_RETRIES",
    "SENTINELAI_MEMORY_ENABLED",
    "SENTINELAI_MEMORY_VECTOR_DB_PATH",
    "SENTINELAI_MEMORY_EMBEDDING_PROVIDER",
    "SENTINELAI_MEMORY_EMBEDDING_MODEL",
    "SENTINELAI_MEMORY_TOP_K",
    "SENTINELAI_MCP_ENABLED",
    "SENTINELAI_MCP_TOOL_TRACING_ENABLED",
    "SENTINELAI_MCP_TIMEOUT_SECONDS",
    "SENTINELAI_MCP_ENABLED_TOOLS",
    "SENTINELAI_AUTH_ENABLED",
    "SENTINELAI_AUTH_SQLITE_PATH",
    "SENTINELAI_AUTH_JWT_SECRET",
    "SENTINELAI_AUTH_TOKEN_EXPIRE_MINUTES",
    "SENTINELAI_AUTH_COOKIE_NAME",
    "SENTINELAI_AUTH_SECURE_COOKIE",
    "SENTINELAI_DATABASE_SQLITE_PATH",
    "SENTINELAI_DATABASE_URL",
]


def test_load_settings_uses_expected_defaults(monkeypatch, tmp_path: Path):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    settings = load_settings(project_root=tmp_path)

    assert settings.browser.headless is True
    assert settings.browser.viewport_width == 1440
    assert settings.browser.viewport_height == 900
    assert settings.browser.navigation_timeout_ms == 30000
    assert settings.browser.wait_until == "load"
    assert settings.ollama.endpoint == "http://localhost:11434/api/generate"
    assert settings.ollama.model == "llama3"
    assert settings.ollama.timeout_seconds == 60
    assert settings.ollama.max_attempts == 3
    assert settings.graph.max_retries == 2
    assert settings.memory.enabled is True
    assert settings.memory.vector_db_path == tmp_path / "memory_store"
    assert settings.memory.embedding_provider == "hashing"
    assert settings.memory.embedding_model == "hashing-384"
    assert settings.memory.top_k == 3
    assert settings.mcp.enabled is True
    assert settings.mcp.tool_tracing_enabled is True
    assert settings.mcp.timeout_seconds == 90
    assert settings.mcp.enabled_tools == ("browser", "memory", "validation")
    assert settings.auth.enabled is True
    assert settings.auth.sqlite_path == tmp_path / "auth_store" / "sentinelai_auth.db"
    assert len(settings.auth.jwt_secret) >= 32
    assert settings.auth.token_expire_minutes == 1440
    assert settings.auth.cookie_name == "sentinelai_session"
    assert settings.auth.secure_cookie is False
    assert settings.database.sqlite_path == tmp_path / "metadata_store" / "sentinelai_metadata.db"
    assert settings.database.url == f"sqlite:///{(tmp_path / 'metadata_store' / 'sentinelai_metadata.db').as_posix()}"
    assert settings.storage.artifacts_root == tmp_path / "artifacts"
    assert settings.storage.runs_root == tmp_path / "artifacts" / "runs"


def test_load_settings_reads_env_overrides(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SENTINELAI_BROWSER_HEADLESS", "false")
    monkeypatch.setenv("SENTINELAI_BROWSER_VIEWPORT_WIDTH", "1600")
    monkeypatch.setenv("SENTINELAI_BROWSER_VIEWPORT_HEIGHT", "1000")
    monkeypatch.setenv("SENTINELAI_BROWSER_NAVIGATION_TIMEOUT_MS", "45000")
    monkeypatch.setenv("SENTINELAI_BROWSER_WAIT_UNTIL", "domcontentloaded")
    monkeypatch.setenv("SENTINELAI_ARTIFACTS_DIR", "custom_artifacts")
    monkeypatch.setenv("SENTINELAI_OLLAMA_ENDPOINT", "http://localhost:9999/api/generate")
    monkeypatch.setenv("SENTINELAI_OLLAMA_MODEL", "mistral")
    monkeypatch.setenv("SENTINELAI_OLLAMA_TIMEOUT_SECONDS", "75")
    monkeypatch.setenv("SENTINELAI_OLLAMA_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("SENTINELAI_GRAPH_MAX_RETRIES", "5")
    monkeypatch.setenv("SENTINELAI_MEMORY_ENABLED", "false")
    monkeypatch.setenv("SENTINELAI_MEMORY_VECTOR_DB_PATH", "persistent_memory")
    monkeypatch.setenv("SENTINELAI_MEMORY_EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("SENTINELAI_MEMORY_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    monkeypatch.setenv("SENTINELAI_MEMORY_TOP_K", "7")
    monkeypatch.setenv("SENTINELAI_MCP_ENABLED", "false")
    monkeypatch.setenv("SENTINELAI_MCP_TOOL_TRACING_ENABLED", "false")
    monkeypatch.setenv("SENTINELAI_MCP_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("SENTINELAI_MCP_ENABLED_TOOLS", "browser,validation")
    monkeypatch.setenv("SENTINELAI_AUTH_ENABLED", "false")
    monkeypatch.setenv("SENTINELAI_AUTH_SQLITE_PATH", "custom_auth/auth.db")
    monkeypatch.setenv("SENTINELAI_AUTH_JWT_SECRET", "custom-test-secret-with-enough-length")
    monkeypatch.setenv("SENTINELAI_AUTH_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("SENTINELAI_AUTH_COOKIE_NAME", "custom_session")
    monkeypatch.setenv("SENTINELAI_AUTH_SECURE_COOKIE", "true")
    monkeypatch.setenv("SENTINELAI_DATABASE_SQLITE_PATH", "custom_metadata/meta.db")
    monkeypatch.setenv("SENTINELAI_DATABASE_URL", "sqlite:///override.db")

    settings = load_settings(project_root=tmp_path)

    assert settings.browser.headless is False
    assert settings.browser.viewport_width == 1600
    assert settings.browser.viewport_height == 1000
    assert settings.browser.navigation_timeout_ms == 45000
    assert settings.browser.wait_until == "domcontentloaded"
    assert settings.storage.artifacts_root == tmp_path / "custom_artifacts"
    assert settings.ollama.endpoint == "http://localhost:9999/api/generate"
    assert settings.ollama.model == "mistral"
    assert settings.ollama.timeout_seconds == 75
    assert settings.ollama.max_attempts == 4
    assert settings.graph.max_retries == 5
    assert settings.memory.enabled is False
    assert settings.memory.vector_db_path == tmp_path / "persistent_memory"
    assert settings.memory.embedding_provider == "sentence_transformers"
    assert settings.memory.embedding_model == "all-MiniLM-L6-v2"
    assert settings.memory.top_k == 7
    assert settings.mcp.enabled is False
    assert settings.mcp.tool_tracing_enabled is False
    assert settings.mcp.timeout_seconds == 120
    assert settings.mcp.enabled_tools == ("browser", "validation")
    assert settings.auth.enabled is False
    assert settings.auth.sqlite_path == tmp_path / "custom_auth" / "auth.db"
    assert settings.auth.jwt_secret == "custom-test-secret-with-enough-length"
    assert settings.auth.token_expire_minutes == 30
    assert settings.auth.cookie_name == "custom_session"
    assert settings.auth.secure_cookie is True
    assert settings.database.sqlite_path == tmp_path / "custom_metadata" / "meta.db"
    assert settings.database.url == "sqlite:///override.db"
