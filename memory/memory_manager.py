from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import MemorySettings
from memory.embeddings import build_embedding_provider
from memory.embeddings import build_memory_document
from memory.embeddings import build_query_text
from memory.models import MemoryEntry
from memory.models import MemoryRetrieval
from memory.models import MemoryStoreResult
from memory.vector_store import FaissVectorStore


@dataclass(slots=True)
class MemoryManager:
    settings: MemorySettings
    provider: Any = field(init=False, default=None)
    vector_store: FaissVectorStore | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if not self.settings.enabled:
            return
        self.provider = build_embedding_provider(self.settings)
        self.vector_store = FaissVectorStore(
            store_path=self.settings.vector_db_path,
            dimension=self.provider.dimension,
            provider_name=self.provider.provider_name,
            model_name=self.provider.model_name,
        )

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def retrieve_similar(
        self,
        *,
        url: str,
        instruction: str,
        failure_context: str | None = None,
        top_k: int | None = None,
    ) -> MemoryRetrieval:
        query_text = build_query_text(
            url=url,
            instruction=instruction,
            failure_context=failure_context,
        )
        resolved_top_k = max(0, top_k if top_k is not None else self.settings.top_k)
        if not self.enabled:
            return MemoryRetrieval(
                status="disabled",
                query_text=query_text,
                prompt_context=None,
                results=[],
                provider_name=self.settings.embedding_provider,
                model_name=self.settings.embedding_model,
                top_k=resolved_top_k,
            )

        assert self.provider is not None
        assert self.vector_store is not None
        query_vector = self.provider.embed_query(query_text)
        results = self.vector_store.similarity_search(
            query_vector=query_vector,
            top_k=resolved_top_k,
        )
        return MemoryRetrieval(
            status="passed",
            query_text=query_text,
            prompt_context=self._build_prompt_context(results),
            results=results,
            provider_name=self.provider.provider_name,
            model_name=self.provider.model_name,
            top_k=resolved_top_k,
        )

    def store_execution(
        self,
        *,
        run_id: str,
        url: str,
        instruction: str,
        generated_test_plan: dict[str, Any] | None,
        execution_summary: dict[str, Any],
        failure_reason: str | None,
        validation_status: str,
        retry_count: int,
        final_result: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryStoreResult:
        if not self.enabled:
            return MemoryStoreResult(
                status="disabled",
                entry=None,
                provider_name=self.settings.embedding_provider,
                model_name=self.settings.embedding_model,
                vector_count=self.vector_store.count if self.vector_store else 0,
            )

        assert self.provider is not None
        assert self.vector_store is not None
        entry = MemoryEntry(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            url=url,
            instruction=instruction,
            generated_test_plan=generated_test_plan,
            execution_summary=execution_summary,
            failure_reason=failure_reason,
            validation_status=validation_status,
            retry_count=retry_count,
            final_result=final_result,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
        )
        document = build_memory_document(entry.to_dict())
        vector = self.provider.embed_query(document)
        vector_count = self.vector_store.add(entry=entry, vector=vector)
        return MemoryStoreResult(
            status="stored",
            entry=entry,
            provider_name=self.provider.provider_name,
            model_name=self.provider.model_name,
            vector_count=vector_count,
        )

    def write_retrieval_artifact(
        self,
        *,
        output_path: Path,
        retrieval: MemoryRetrieval,
    ) -> Path:
        output_path.write_text(
            json.dumps(retrieval.to_dict(), indent=2),
            encoding="utf-8",
        )
        return output_path

    def write_store_artifact(
        self,
        *,
        output_path: Path,
        store_result: MemoryStoreResult,
    ) -> Path:
        output_path.write_text(
            json.dumps(store_result.to_dict(), indent=2),
            encoding="utf-8",
        )
        return output_path

    def _build_prompt_context(self, results: list) -> str | None:
        if not results:
            return None

        lines = [
            "Use the following relevant past runs as guidance. They are hints, not hard rules.",
        ]
        for result in results:
            entry = result.entry
            lines.append(
                (
                    f"- Similar run {result.rank} (score={result.score:.3f}, run_id={entry.run_id}): "
                    f"result={entry.final_result}, validation={entry.validation_status}, "
                    f"retries={entry.retry_count}, failure_reason={entry.failure_reason or 'none'}, "
                    f"instruction={entry.instruction}"
                )
            )
        return "\n".join(lines)
