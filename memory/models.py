from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemoryEntry:
    run_id: str
    timestamp: str
    url: str
    instruction: str
    generated_test_plan: dict[str, Any] | None
    execution_summary: dict[str, Any]
    failure_reason: str | None
    validation_status: str
    retry_count: int
    final_result: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "url": self.url,
            "instruction": self.instruction,
            "generated_test_plan": self.generated_test_plan,
            "execution_summary": self.execution_summary,
            "failure_reason": self.failure_reason,
            "validation_status": self.validation_status,
            "retry_count": self.retry_count,
            "final_result": self.final_result,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MemoryEntry:
        return cls(
            run_id=str(payload["run_id"]),
            timestamp=str(payload["timestamp"]),
            url=str(payload["url"]),
            instruction=str(payload["instruction"]),
            generated_test_plan=payload.get("generated_test_plan"),
            execution_summary=dict(payload.get("execution_summary", {})),
            failure_reason=payload.get("failure_reason"),
            validation_status=str(payload.get("validation_status", "unknown")),
            retry_count=int(payload.get("retry_count", 0)),
            final_result=str(payload.get("final_result", "unknown")),
            tags=[str(tag) for tag in payload.get("tags", [])],
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(slots=True)
class RetrievedMemory:
    rank: int
    score: float
    entry: MemoryEntry

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "score": self.score,
            "entry": self.entry.to_dict(),
        }


@dataclass(slots=True)
class MemoryRetrieval:
    status: str
    query_text: str
    prompt_context: str | None
    results: list[RetrievedMemory]
    provider_name: str
    model_name: str
    top_k: int
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "query_text": self.query_text,
            "prompt_context": self.prompt_context,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "top_k": self.top_k,
            "error_message": self.error_message,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(slots=True)
class MemoryStoreResult:
    status: str
    entry: MemoryEntry | None
    provider_name: str
    model_name: str
    vector_count: int
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "vector_count": self.vector_count,
            "error_message": self.error_message,
            "entry": self.entry.to_dict() if self.entry is not None else None,
        }
