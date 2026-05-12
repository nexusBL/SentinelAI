from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime, timezone
from pathlib import Path

import faiss
import numpy as np

from memory.models import MemoryEntry
from memory.models import RetrievedMemory


@dataclass(slots=True)
class FaissVectorStore:
    store_path: Path
    dimension: int
    provider_name: str
    model_name: str
    index_path: Path = field(init=False)
    entries_path: Path = field(init=False)
    manifest_path: Path = field(init=False)
    index: faiss.Index = field(init=False)
    entries: list[MemoryEntry] = field(init=False)

    def __post_init__(self) -> None:
        self.store_path.mkdir(parents=True, exist_ok=True)
        self.index_path = self.store_path / "memory.index"
        self.entries_path = self.store_path / "entries.jsonl"
        self.manifest_path = self.store_path / "manifest.json"
        self._validate_manifest()
        self.index = self._load_or_create_index()
        self.entries = self._load_entries()
        if self.index.ntotal != len(self.entries):
            raise RuntimeError(
                "FAISS index and memory entry metadata are out of sync. "
                "Delete the memory store directory or restore a matching backup."
            )

    @property
    def count(self) -> int:
        return len(self.entries)

    def add(self, *, entry: MemoryEntry, vector: np.ndarray) -> int:
        vectors = self._ensure_matrix(vector)
        self.index.add(vectors)
        self.entries.append(entry)
        self._persist()
        return self.count

    def similarity_search(self, *, query_vector: np.ndarray, top_k: int) -> list[RetrievedMemory]:
        if self.count == 0 or top_k <= 0:
            return []

        limited_top_k = min(top_k, self.count)
        vectors = self._ensure_matrix(query_vector)
        scores, indices = self.index.search(vectors, limited_top_k)

        results: list[RetrievedMemory] = []
        for rank, (score, index) in enumerate(zip(scores[0], indices[0]), start=1):
            if index < 0:
                continue
            results.append(
                RetrievedMemory(
                    rank=rank,
                    score=float(score),
                    entry=self.entries[int(index)],
                )
            )
        return results

    def _load_or_create_index(self):
        if self.index_path.exists():
            index = faiss.read_index(str(self.index_path))
            if index.d != self.dimension:
                raise RuntimeError(
                    f"Existing memory index dimension {index.d} does not match "
                    f"configured dimension {self.dimension}."
                )
            return index
        return faiss.IndexFlatIP(self.dimension)

    def _validate_manifest(self) -> None:
        if not self.manifest_path.exists():
            return
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        stored_dimension = int(manifest.get("dimension", self.dimension))
        if stored_dimension != self.dimension:
            raise RuntimeError(
                f"Existing memory manifest dimension {stored_dimension} does not match "
                f"configured dimension {self.dimension}."
            )
        stored_provider = str(manifest.get("provider_name", self.provider_name))
        stored_model = str(manifest.get("model_name", self.model_name))
        if stored_provider != self.provider_name or stored_model != self.model_name:
            raise RuntimeError(
                "Existing memory store was created with a different embedding "
                f"configuration ({stored_provider}/{stored_model}) than the current "
                f"configuration ({self.provider_name}/{self.model_name})."
            )

    def _load_entries(self) -> list[MemoryEntry]:
        if not self.entries_path.exists():
            return []
        entries: list[MemoryEntry] = []
        for line in self.entries_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            entries.append(MemoryEntry.from_dict(json.loads(line)))
        return entries

    def _persist(self) -> None:
        faiss.write_index(self.index, str(self.index_path))
        if self.entries:
            payload = "\n".join(
                json.dumps(entry.to_dict(), ensure_ascii=True) for entry in self.entries
            )
            self.entries_path.write_text(f"{payload}\n", encoding="utf-8")
        else:
            self.entries_path.write_text("", encoding="utf-8")

        manifest = {
            "dimension": self.dimension,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "vector_count": self.count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _ensure_matrix(self, vector: np.ndarray) -> np.ndarray:
        matrix = np.asarray(vector, dtype="float32")
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        if matrix.shape[1] != self.dimension:
            raise ValueError(
                f"Vector dimension {matrix.shape[1]} does not match store dimension "
                f"{self.dimension}."
            )
        return matrix
