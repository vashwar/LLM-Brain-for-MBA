"""
Semantic search index loader and query interface for the wiki viewer.

Loads the pre-built search_index.npz + search_metadata.json sidecar and
provides a cosine-similarity search over BAAI/bge-small-en-v1.5 embeddings.

The embedding model itself is lazy-loaded on the first search() call so that
Flask startup stays fast.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"
RELEVANCE_THRESHOLD = 0.2
TITLE_BOOST = 0.15


class SearchIndex:
    """Cosine-similarity search over pre-built embeddings + JSON metadata."""

    def __init__(self, index_path: Path, metadata_path: Path) -> None:
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path)
        self._model = None
        self._embeddings: Optional[np.ndarray] = None
        self._metadata: Optional[list[dict]] = None

    @property
    def available(self) -> bool:
        """True if the index is loaded and has at least one entry."""
        return self._embeddings is not None and self._metadata is not None and len(self._metadata) > 0

    def load(self) -> bool:
        """Load embeddings + metadata from disk. Returns True on success, False if files missing."""
        if not self.index_path.exists() or not self.metadata_path.exists():
            self._embeddings = None
            self._metadata = None
            return False
        try:
            data = np.load(self.index_path)
            self._embeddings = data["embeddings"].astype(np.float32)
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)
            if self._embeddings.shape[0] != len(self._metadata):
                print(
                    f"Warning: search index/metadata row count mismatch "
                    f"({self._embeddings.shape[0]} vs {len(self._metadata)})"
                )
                self._embeddings = None
                self._metadata = None
                return False
            return True
        except Exception as e:
            print(f"Warning: Could not load search index: {e}")
            self._embeddings = None
            self._metadata = None
            return False

    @property
    def model(self):
        """Lazy-load the embedding model on first query (~3s cold start)."""
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=MODEL_NAME)
        return self._model

    def search(
        self,
        query: str,
        k: int = 10,
        course: Optional[str] = None,
        type_filter: Optional[str] = None,
    ) -> list[dict]:
        """Run a semantic search against the index.

        Args:
            query: Natural-language query.
            k: Max number of results to return.
            course: If set, only return entries from this course.
            type_filter: If set, only return entries of this type ('concept' or 'case').

        Returns:
            List of dicts: {slug, title, type, course, preview, score} sorted by score desc.
            Empty list if index not loaded or query is empty.
        """
        if not self.available or not query or not query.strip():
            return []

        # Embed query (fastembed returns a generator)
        q_vec = next(iter(self.model.embed([query])))
        q_vec = np.asarray(q_vec, dtype=np.float32)
        norm = float(np.linalg.norm(q_vec))
        if norm > 0:
            q_vec = q_vec / norm

        # Cosine similarity (embeddings are already L2-normalized)
        scores = self._embeddings @ q_vec  # type: ignore[operator]
        scores = scores.astype(np.float32).copy()

        query_lower = query.lower()
        for i, m in enumerate(self._metadata):  # type: ignore[union-attr]
            if course and m.get("course") != course:
                scores[i] = -1.0
                continue
            if type_filter and m.get("type") != type_filter:
                scores[i] = -1.0
                continue
            # Hybrid boost: exact substring match on title
            title = m.get("title", "")
            if title and query_lower in title.lower():
                scores[i] += TITLE_BOOST

        top = np.argsort(scores)[::-1][:k]
        results: list[dict] = []
        for idx in top:
            score = float(scores[idx])
            if score < RELEVANCE_THRESHOLD:
                continue
            m = self._metadata[int(idx)]  # type: ignore[index]
            results.append({
                "slug": m.get("slug", ""),
                "title": m.get("title", ""),
                "type": m.get("type", ""),
                "course": m.get("course", ""),
                "preview": m.get("preview", ""),
                "score": score,
            })
        return results
