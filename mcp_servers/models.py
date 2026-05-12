from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class MCPToolRequest:
    server_name: str
    action: str
    payload: dict[str, Any]
    requested_at: str

    @classmethod
    def create(
        cls,
        *,
        server_name: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> MCPToolRequest:
        return cls(
            server_name=server_name,
            action=action,
            payload=dict(payload or {}),
            requested_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "action": self.action,
            "payload_keys": sorted(self.payload.keys()),
            "requested_at": self.requested_at,
        }


@dataclass(slots=True)
class MCPToolResponse:
    server_name: str
    action: str
    status: str
    started_at: str
    completed_at: str
    duration_ms: int
    result: Any = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "action": self.action,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "result_type": type(self.result).__name__ if self.result is not None else None,
        }


@dataclass(slots=True)
class MCPServerCapability:
    server_name: str
    actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "actions": list(self.actions),
        }
