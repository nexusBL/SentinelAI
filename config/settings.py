from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


@dataclass(slots=True)
class BrowserSettings:
    headless: bool
    viewport_width: int
    viewport_height: int
    navigation_timeout_ms: int
    wait_until: str
    screenshot_full_page: bool


@dataclass(slots=True)
class StorageSettings:
    artifacts_root: Path
    runs_root: Path


@dataclass(slots=True)
class OllamaSettings:
    endpoint: str
    model: str
    timeout_seconds: int
    max_attempts: int


@dataclass(slots=True)
class GraphSettings:
    max_retries: int


@dataclass(slots=True)
class AppSettings:
    browser: BrowserSettings
    storage: StorageSettings
    ollama: OllamaSettings
    graph: GraphSettings


def load_settings(project_root: Path | None = None) -> AppSettings:
    resolved_root = project_root or Path(__file__).resolve().parents[1]
    artifacts_root = Path(
        os.getenv("SENTINELAI_ARTIFACTS_DIR", str(resolved_root / "artifacts"))
    )
    if not artifacts_root.is_absolute():
        artifacts_root = resolved_root / artifacts_root

    return AppSettings(
        browser=BrowserSettings(
            headless=_get_bool("SENTINELAI_BROWSER_HEADLESS", True),
            viewport_width=_get_int("SENTINELAI_BROWSER_VIEWPORT_WIDTH", 1440),
            viewport_height=_get_int("SENTINELAI_BROWSER_VIEWPORT_HEIGHT", 900),
            navigation_timeout_ms=_get_int(
                "SENTINELAI_BROWSER_NAVIGATION_TIMEOUT_MS", 30000
            ),
            wait_until=os.getenv("SENTINELAI_BROWSER_WAIT_UNTIL", "load"),
            screenshot_full_page=True,
        ),
        storage=StorageSettings(
            artifacts_root=artifacts_root,
            runs_root=artifacts_root / "runs",
        ),
        ollama=OllamaSettings(
            endpoint=os.getenv(
                "SENTINELAI_OLLAMA_ENDPOINT",
                "http://localhost:11434/api/generate",
            ),
            model=os.getenv("SENTINELAI_OLLAMA_MODEL", "llama3"),
            timeout_seconds=_get_int("SENTINELAI_OLLAMA_TIMEOUT_SECONDS", 60),
            max_attempts=_get_int("SENTINELAI_OLLAMA_MAX_ATTEMPTS", 3),
        ),
        graph=GraphSettings(
            max_retries=_get_int("SENTINELAI_GRAPH_MAX_RETRIES", 2),
        ),
    )
