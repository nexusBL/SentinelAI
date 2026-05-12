from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Protocol

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from config.settings import MemorySettings


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def build_query_text(*, url: str, instruction: str, failure_context: str | None = None) -> str:
    parts = [
        f"URL: {normalize_text(url)}",
        f"Instruction: {normalize_text(instruction)}",
    ]
    if failure_context:
        parts.append(f"Failure context: {normalize_text(failure_context)}")
    return "\n".join(parts)


def build_memory_document(entry_payload: dict) -> str:
    plan = entry_payload.get("generated_test_plan") or {}
    step_descriptions = [
        str(step.get("description") or step.get("action") or "")
        for step in plan.get("steps", [])
    ]
    assertion_descriptions = [
        str(assertion.get("description") or assertion.get("type") or "")
        for assertion in plan.get("assertions", [])
    ]
    execution_summary = entry_payload.get("execution_summary") or {}
    parts = [
        f"URL: {entry_payload.get('url')}",
        f"Instruction: {entry_payload.get('instruction')}",
        f"Validation status: {entry_payload.get('validation_status')}",
        f"Final result: {entry_payload.get('final_result')}",
        f"Retry count: {entry_payload.get('retry_count')}",
        f"Failure reason: {entry_payload.get('failure_reason') or 'none'}",
        f"Step summary: {' | '.join(filter(None, step_descriptions)) or 'none'}",
        f"Assertion summary: {' | '.join(filter(None, assertion_descriptions)) or 'none'}",
        f"Execution summary: {normalize_text(str(execution_summary))}",
    ]
    return "\n".join(parts)


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


@dataclass(slots=True)
class HashingEmbeddingProvider:
    model_name: str
    provider_name: str = field(init=False, default="hashing")
    dimension: int = field(init=False)
    _vectorizer: HashingVectorizer = field(init=False)

    def __post_init__(self) -> None:
        self.dimension = self._parse_dimension(self.model_name)
        self._vectorizer = HashingVectorizer(
            n_features=self.dimension,
            alternate_sign=False,
            analyzer="word",
            ngram_range=(1, 2),
            norm=None,
        )

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        normalized = [normalize_text(text) for text in texts]
        matrix = self._vectorizer.transform(normalized)
        return _normalize_vectors(matrix.toarray().astype("float32"))

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]

    def _parse_dimension(self, model_name: str) -> int:
        suffix = model_name.rsplit("-", 1)[-1]
        if suffix.isdigit():
            return max(64, int(suffix))
        return 384


@dataclass(slots=True)
class SentenceTransformerEmbeddingProvider:
    model_name: str
    provider_name: str = field(init=False, default="sentence_transformers")
    dimension: int = field(init=False)
    _model: object = field(init=False)

    def __post_init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)
        self.dimension = int(self._model.get_sentence_embedding_dimension())

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        normalized = [normalize_text(text) for text in texts]
        embeddings = self._model.encode(
            normalized,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return np.asarray(embeddings, dtype="float32")

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


def build_embedding_provider(settings: MemorySettings) -> EmbeddingProvider:
    provider_name = settings.embedding_provider.strip().lower()
    if provider_name in {"sentence_transformers", "sentence-transformers", "st"}:
        return SentenceTransformerEmbeddingProvider(settings.embedding_model)
    return HashingEmbeddingProvider(settings.embedding_model)
