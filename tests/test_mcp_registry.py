from __future__ import annotations

import asyncio

from mcp_servers.base import MCPToolServer
from mcp_servers.registry import MCPToolRegistry


class DummyServer(MCPToolServer):
    name = "dummy"

    def _action_handlers(self):
        return {
            "echo": self._echo,
            "sleep": self._sleep,
        }

    def _echo(self, payload):
        return {"payload": payload}

    async def _sleep(self, payload):
        await asyncio.sleep(float(payload.get("delay", 0)))
        return {"slept": payload.get("delay", 0)}


async def test_register_and_retrieve_tool_by_name():
    registry = MCPToolRegistry(enabled=True, timeout_seconds=5, enabled_tools=("dummy",))
    server = DummyServer(timeout_seconds=5)
    registry.register(server)

    assert registry.get("dummy") is server
    assert registry.available_servers() == ("dummy",)


async def test_list_capabilities():
    registry = MCPToolRegistry(enabled=True, timeout_seconds=5, enabled_tools=("dummy",))
    registry.register(DummyServer(timeout_seconds=5))

    capabilities = registry.available_capabilities()

    assert len(capabilities) == 1
    assert capabilities[0].server_name == "dummy"
    assert capabilities[0].actions == ("echo", "sleep")


async def test_unknown_tool_returns_structured_error():
    registry = MCPToolRegistry(enabled=True, timeout_seconds=5, enabled_tools=())

    response = await registry.execute(server_name="unknown", action="echo", payload={})

    assert response.status == "failed"
    assert "not registered" in str(response.error_message)


async def test_disabled_tool_behavior_returns_structured_error():
    registry = MCPToolRegistry(enabled=True, timeout_seconds=5, enabled_tools=("dummy",))
    registry.register(DummyServer(timeout_seconds=5))

    response = await registry.execute(server_name="browser", action="echo", payload={})

    assert response.status == "failed"
    assert "not enabled" in str(response.error_message)


async def test_registry_timeout_is_handled():
    registry = MCPToolRegistry(enabled=True, timeout_seconds=1, enabled_tools=("dummy",))
    registry.register(DummyServer(timeout_seconds=5))

    response = await registry.execute(
        server_name="dummy",
        action="sleep",
        payload={"delay": 1.5},
    )

    assert response.status == "failed"
    assert "timed out" in str(response.error_message)
