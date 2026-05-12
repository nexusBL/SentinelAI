from __future__ import annotations

from typing import Any

from mcp_servers.base import MCPToolServer
from memory import MemoryManager


class MemoryMCPServer(MCPToolServer):
    name = "memory"

    def __init__(self, memory_manager: MemoryManager, *, timeout_seconds: int = 90) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.memory_manager = memory_manager

    def _action_handlers(self):
        return {
            "retrieve_similar": self._retrieve_similar,
            "store_execution": self._store_execution,
            "memory_stats": self._memory_stats,
        }

    def _retrieve_similar(self, payload: dict[str, Any]) -> dict[str, Any]:
        retrieval = self.memory_manager.retrieve_similar(
            url=self._require_string(payload, "url"),
            instruction=self._require_string(payload, "instruction"),
            failure_context=self._optional_string(payload.get("failure_context")),
            top_k=self._optional_int(payload.get("top_k")),
        )
        return {"retrieval": retrieval}

    def _store_execution(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.memory_manager.store_execution(
            run_id=self._require_string(payload, "run_id"),
            url=self._require_string(payload, "url"),
            instruction=self._require_string(payload, "instruction"),
            generated_test_plan=payload.get("generated_test_plan"),
            execution_summary=dict(payload.get("execution_summary") or {}),
            failure_reason=self._optional_string(payload.get("failure_reason")),
            validation_status=self._require_string(payload, "validation_status"),
            retry_count=int(payload.get("retry_count", 0)),
            final_result=self._require_string(payload, "final_result"),
            tags=list(payload.get("tags") or []),
            metadata=dict(payload.get("metadata") or {}),
        )
        return {"store_result": result}

    def _memory_stats(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        vector_store = self.memory_manager.vector_store
        provider = self.memory_manager.provider
        return {
            "enabled": self.memory_manager.enabled,
            "vector_count": vector_store.count if vector_store is not None else 0,
            "store_path": (
                str(vector_store.store_path) if vector_store is not None else None
            ),
            "provider_name": (
                provider.provider_name
                if provider is not None
                else self.memory_manager.settings.embedding_provider
            ),
            "model_name": (
                provider.model_name
                if provider is not None
                else self.memory_manager.settings.embedding_model
            ),
            "top_k": self.memory_manager.settings.top_k,
        }

    def _require_string(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if value is None or str(value).strip() == "":
            raise ValueError(f"'{key}' is required and must be a non-empty string.")
        return str(value)

    def _optional_string(self, value: Any) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        return str(value)

    def _optional_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)
