from __future__ import annotations

from abc import ABC
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Awaitable, Callable

from mcp_servers.models import MCPToolResponse


Handler = Callable[[dict[str, Any]], Awaitable[Any] | Any]


class MCPToolServer(ABC):
    name = "base"

    def __init__(self, *, timeout_seconds: int = 90) -> None:
        self.timeout_seconds = max(1, timeout_seconds)

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(sorted(self._action_handlers().keys()))

    async def execute(self, action: str, payload: dict[str, Any]) -> MCPToolResponse:
        started_at = datetime.now(timezone.utc).isoformat()
        started_monotonic = perf_counter()
        try:
            handler = self._action_handlers()[action]
        except KeyError:
            completed_at = datetime.now(timezone.utc).isoformat()
            return MCPToolResponse(
                server_name=self.name,
                action=action,
                status="failed",
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=int((perf_counter() - started_monotonic) * 1000),
                error_message=(
                    f"Unsupported action '{action}' for server '{self.name}'. "
                    f"Available actions: {sorted(self._action_handlers().keys())}"
                ),
            )

        try:
            result = handler(dict(payload))
            if hasattr(result, "__await__"):
                result = await result
            status = "passed"
            error_message = None
        except Exception as exc:
            result = None
            status = "failed"
            error_message = f"{type(exc).__name__}: {exc}"

        completed_at = datetime.now(timezone.utc).isoformat()
        return MCPToolResponse(
            server_name=self.name,
            action=action,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=int((perf_counter() - started_monotonic) * 1000),
            result=result,
            error_message=error_message,
        )

    def _action_handlers(self) -> dict[str, Handler]:
        raise NotImplementedError
