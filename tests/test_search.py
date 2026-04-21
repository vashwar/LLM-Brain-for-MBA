"""Tests for SearchIndex.search() — cosine similarity with filters and title boost."""

import json
import pytest
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from wiki_viewer.utils.search import SearchIndex, RELEVANCE_THRESHOLD, TITLE_BOOST


def make_index(entries, dim=384):
    """Create a SearchIndex with synthetic embeddings and metadata.

    Each entry: {"slug", "title", "type", "course", "preview", "embedding"}
    If "embedding" is omitted, a random unit vector is generated.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        embeddings = []
        metadata = []
        for e in entries:
            vec = e.get("embedding", None)
            if vec is None:
                vec = np.random.randn(dim).astype(np.float32)
                vec /= np.linalg.norm(vec)
            embeddings.append(vec)
            metadata.append({
                "slug": e.get("slug", ""),
                "title": e.get("title", ""),
                "type": e.get("type", "concept"),
                "course": e.get("course", ""),
                "preview": e.get("preview", ""),
            })

        emb_array = np.array(embeddings, dtype=np.float32)
        np.savez(tmp / "index.npz", embeddings=emb_array)
        with open(tmp / "meta.json", "w") as f:
            json.dump(metadata, f)

        idx = SearchIndex(tmp / "index.npz", tmp / "meta.json")
        idx.load()
        yield idx


@pytest.fixture
def three_entry_index():
    """Index with 3 entries: Supply Curve (Micro), Demand Curve (Micro), NPV (Finance)."""
    dim = 384
    # Create distinguishable embeddings
    supply_vec = np.zeros(dim, dtype=np.float32)
    supply_vec[0] = 1.0  # pointing in dimension 0

    demand_vec = np.zeros(dim, dtype=np.float32)
    demand_vec[1] = 1.0  # pointing in dimension 1

    npv_vec = np.zeros(dim, dtype=np.float32)
    npv_vec[2] = 1.0  # pointing in dimension 2

    entries = [
        {"slug": "supply-curve", "title": "Supply Curve", "type": "concept", "course": "Microeconomics", "embedding": supply_vec},
        {"slug": "demand-curve", "title": "Demand Curve", "type": "concept", "course": "Microeconomics", "embedding": demand_vec},
        {"slug": "npv", "title": "Net Present Value", "type": "concept", "course": "Finance", "embedding": npv_vec},
    ]
    gen = make_index(entries, dim)
    idx = next(gen)
    yield idx
    # Cleanup
    try:
        next(gen)
    except StopIteration:
        pass


def mock_embed(query_vec):
    """Create a mock model.embed() that returns a fixed vector."""
    def embed(texts):
        for _ in texts:
            yield query_vec
    mock_model = MagicMock()
    mock_model.embed = embed
    return mock_model


class TestEmptyAndGuards:
    """Guard clause tests: empty query, unavailable index."""

    def test_empty_query_returns_empty(self, three_entry_index):
        three_entry_index._model = mock_embed(np.zeros(384))
        assert three_entry_index.search("") == []

    def test_whitespace_query_returns_empty(self, three_entry_index):
        three_entry_index._model = mock_embed(np.zeros(384))
        assert three_entry_index.search("   ") == []

    def test_unavailable_index_returns_empty(self):
        idx = SearchIndex(Path("nonexistent.npz"), Path("nonexistent.json"))
        assert idx.search("anything") == []


class TestBasicSearch:
    """Basic search: cosine similarity ranking."""

    def test_returns_best_match(self, three_entry_index):
        # Query vector points in dimension 0 → should match supply_vec
        query_vec = np.zeros(384, dtype=np.float32)
        query_vec[0] = 1.0
        three_entry_index._model = mock_embed(query_vec)

        results = three_entry_index.search("supply")
        assert len(results) > 0
        assert results[0]["slug"] == "supply-curve"
        assert results[0]["score"] > 0.9

    def test_returns_sorted_by_score(self, three_entry_index):
        # Query between dimensions 0 and 1 — should match both supply and demand
        query_vec = np.zeros(384, dtype=np.float32)
        query_vec[0] = 0.8
        query_vec[1] = 0.6
        query_vec /= np.linalg.norm(query_vec)
        three_entry_index._model = mock_embed(query_vec)

        results = three_entry_index.search("supply and demand")
        assert len(results) >= 2
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_respects_k_limit(self, three_entry_index):
        query_vec = np.ones(384, dtype=np.float32)
        query_vec /= np.linalg.norm(query_vec)
        three_entry_index._model = mock_embed(query_vec)

        results = three_entry_index.search("everything", k=1)
        assert len(results) <= 1


class TestFiltering:
    """Course and type filters."""

    def test_course_filter(self, three_entry_index):
        # Query similar to all, but filter to Finance only
        query_vec = np.zeros(384, dtype=np.float32)
        query_vec[2] = 1.0  # Points at NPV
        three_entry_index._model = mock_embed(query_vec)

        results = three_entry_index.search("value", course="Finance")
        assert all(r["course"] == "Finance" for r in results)

    def test_course_filter_excludes_other_courses(self, three_entry_index):
        # Query pointing at supply curve but filter to Finance
        query_vec = np.zeros(384, dtype=np.float32)
        query_vec[0] = 1.0
        three_entry_index._model = mock_embed(query_vec)

        results = three_entry_index.search("supply", course="Finance")
        slugs = [r["slug"] for r in results]
        assert "supply-curve" not in slugs

    def test_type_filter(self, three_entry_index):
        query_vec = np.ones(384, dtype=np.float32)
        query_vec /= np.linalg.norm(query_vec)
        three_entry_index._model = mock_embed(query_vec)

        results = three_entry_index.search("anything", type_filter="concept")
        assert all(r["type"] == "concept" for r in results)

    def test_type_filter_case(self):
        """Filter for type='case' should exclude concepts."""
        entries = [
            {"slug": "supply", "title": "Supply", "type": "concept", "course": "Micro"},
            {"slug": "tesla", "title": "Tesla", "type": "case", "course": "Strategy"},
        ]
        dim = 384
        case_vec = np.zeros(dim, dtype=np.float32)
        case_vec[0] = 1.0
        concept_vec = np.zeros(dim, dtype=np.float32)
        concept_vec[1] = 1.0
        entries[0]["embedding"] = concept_vec
        entries[1]["embedding"] = case_vec

        gen = make_index(entries, dim)
        idx = next(gen)
        query_vec = np.ones(dim, dtype=np.float32)
        query_vec /= np.linalg.norm(query_vec)
        idx._model = mock_embed(query_vec)

        results = idx.search("test", type_filter="case")
        assert all(r["type"] == "case" for r in results)


class TestTitleBoost:
    """Hybrid title-substring boost (+0.15)."""

    def test_title_boost_applied(self, three_entry_index):
        # Both supply and demand have similar cosine scores,
        # but query contains "Supply" which should boost supply-curve
        query_vec = np.zeros(384, dtype=np.float32)
        query_vec[0] = 0.5
        query_vec[1] = 0.5
        query_vec /= np.linalg.norm(query_vec)
        three_entry_index._model = mock_embed(query_vec)

        results = three_entry_index.search("Supply")
        # Supply Curve should be boosted because "supply" is in "Supply Curve"
        supply_result = next((r for r in results if r["slug"] == "supply-curve"), None)
        demand_result = next((r for r in results if r["slug"] == "demand-curve"), None)
        assert supply_result is not None
        assert demand_result is not None
        assert supply_result["score"] > demand_result["score"]

    def test_title_boost_is_case_insensitive(self, three_entry_index):
        query_vec = np.zeros(384, dtype=np.float32)
        query_vec[0] = 0.5
        query_vec[1] = 0.5
        query_vec /= np.linalg.norm(query_vec)
        three_entry_index._model = mock_embed(query_vec)

        results = three_entry_index.search("supply curve")
        supply = next((r for r in results if r["slug"] == "supply-curve"), None)
        assert supply is not None
        # The boost should be applied (query "supply curve" is in "Supply Curve".lower())


class TestRelevanceThreshold:
    """Results below RELEVANCE_THRESHOLD (0.2) are excluded."""

    def test_low_similarity_excluded(self, three_entry_index):
        # Query orthogonal to all entries
        query_vec = np.zeros(384, dtype=np.float32)
        query_vec[100] = 1.0  # Dimension not used by any entry
        three_entry_index._model = mock_embed(query_vec)

        results = three_entry_index.search("irrelevant topic")
        # All entries have 0 similarity → below 0.2 threshold
        assert len(results) == 0


class TestResultFormat:
    """Verify result dict structure."""

    def test_result_has_all_fields(self, three_entry_index):
        query_vec = np.zeros(384, dtype=np.float32)
        query_vec[0] = 1.0
        three_entry_index._model = mock_embed(query_vec)

        results = three_entry_index.search("supply")
        assert len(results) > 0
        r = results[0]
        assert set(r.keys()) == {"slug", "title", "type", "course", "preview", "score"}
        assert isinstance(r["score"], float)
