from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from mcp_servers.base import MCPToolServer
from mcp_servers.models import MCPServerCapability
from mcp_servers.models import MCPToolResponse


class MCPToolRegistry:
    def __init__(
        self,
        *,
        enabled: bool,
        timeout_seconds: int,
        enabled_tools: tuple[str, ...],
    ) -> None:
        self.enabled = enabled
        self.timeout_seconds = max(1, timeout_seconds)
        self.enabled_tools = frozenset(enabled_tools)
        self._servers: dict[str, MCPToolServer] = {}

    def register(self, server: MCPToolServer) -> None:
        self._servers[server.name] = server

    def get(self, server_name: str) -> MCPToolServer | None:
        return self._servers.get(server_name)

    def available_servers(self) -> tuple[str, ...]:
        return tuple(sorted(self._servers.keys()))

    def available_capabilities(self) -> list[MCPServerCapability]:
        return [
            MCPServerCapability(server_name=server.name, actions=server.actions)
            for server in sorted(self._servers.values(), key=lambda item: item.name)
        ]

    async def execute(
        self,
        *,
        server_name: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> MCPToolResponse:
        started_at = datetime.now(timezone.utc).isoformat()
        if not self.enabled:
            return MCPToolResponse(
                server_name=server_name,
                action=action,
                status="failed",
                started_at=started_at,
                completed_at=started_at,
                duration_ms=0,
                error_message="MCP registry is disabled.",
            )
        if self.enabled_tools and server_name not in self.enabled_tools:
            return MCPToolResponse(
                server_name=server_name,
                action=action,
                status="failed",
                started_at=started_at,
                completed_at=started_at,
                duration_ms=0,
                error_message=f"Server '{server_name}' is not enabled in this runtime.",
            )

        server = self.get(server_name)
        if server is None:
            return MCPToolResponse(
                server_name=server_name,
                action=action,
                status="failed",
                started_at=started_at,
                completed_at=started_at,
                duration_ms=0,
                error_message=f"Server '{server_name}' is not registered.",
            )

        try:
            timeout_seconds = min(server.timeout_seconds, self.timeout_seconds)
            return await asyncio.wait_for(
                server.execute(action, dict(payload or {})),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            completed_at = datetime.now(timezone.utc).isoformat()
            return MCPToolResponse(
                server_name=server_name,
                action=action,
                status="failed",
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=timeout_seconds * 1000,
                error_message=f"MCP tool timed out after {timeout_seconds} seconds.",
            )
