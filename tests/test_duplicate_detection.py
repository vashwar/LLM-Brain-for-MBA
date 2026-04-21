"""Tests for check_for_duplicates() and _fuzzy_match() — tiered duplicate detection."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.process_standalone import check_for_duplicates, _fuzzy_match


# ── _fuzzy_match tests ─────────────────────────────────────────────


class TestFuzzyMatch:
    """Unit tests for the _fuzzy_match helper."""

    def test_exact_substring_forward(self):
        """New title is substring of existing title."""
        concepts = {"The Supply Curve": "the-supply-curve"}
        assert _fuzzy_match("Supply Curve", concepts) == "the-supply-curve"

    def test_exact_substring_reverse(self):
        """Existing title is substring of new title."""
        concepts = {"Supply Curve": "supply-curve"}
        assert _fuzzy_match("The Supply Curve and Shifts", concepts) == "supply-curve"

    def test_two_word_overlap(self):
        """Titles share at least 2 words."""
        concepts = {"Price Elasticity of Demand": "price-elasticity-of-demand"}
        assert _fuzzy_match("Demand Price Sensitivity", concepts) == "price-elasticity-of-demand"

    def test_case_insensitive(self):
        """Matching is case-insensitive."""
        concepts = {"Supply Curve": "supply-curve"}
        assert _fuzzy_match("supply curve", concepts) == "supply-curve"

    def test_no_match_single_word_overlap(self):
        """Single word overlap is not enough."""
        concepts = {"Supply Curve": "supply-curve"}
        assert _fuzzy_match("Supply Chain", concepts) is None

    def test_no_match_different_concepts(self):
        """Completely different concepts should not match."""
        concepts = {"Supply Curve": "supply-curve"}
        assert _fuzzy_match("Game Theory", concepts) is None

    def test_empty_dict(self):
        assert _fuzzy_match("Supply Curve", {}) is None


# ── check_for_duplicates — legacy flat mode ────────────────────────


class TestLegacyFlatMode:
    """Legacy mode: flat dict without tiered keys."""

    def test_exact_match(self):
        concepts = {"Supply Curve": "supply-curve", "Demand": "demand"}
        assert check_for_duplicates("Supply Curve", concepts) == "supply-curve"

    def test_fuzzy_match(self):
        concepts = {"The Supply Curve": "the-supply-curve"}
        assert check_for_duplicates("Supply Curve", concepts) == "the-supply-curve"

    def test_no_match(self):
        concepts = {"Supply Curve": "supply-curve"}
        assert check_for_duplicates("Game Theory", concepts) is None

    def test_empty_dict(self):
        assert check_for_duplicates("Anything", {}) is None


# ── check_for_duplicates — tiered mode ─────────────────────────────


def make_tiered(same_course=None, same_group=None, other=None):
    return {
        "same_course": same_course or {},
        "same_group": same_group or {},
        "other": other or {},
    }


class TestTieredSameCourse:
    """Tier 1: Same course — exact + fuzzy matching."""

    def test_exact_same_course(self):
        t = make_tiered(same_course={"Supply Curve": "supply-curve"})
        assert check_for_duplicates("Supply Curve", t) == "supply-curve"

    def test_fuzzy_same_course(self):
        t = make_tiered(same_course={"The Supply Curve": "the-supply-curve"})
        assert check_for_duplicates("Supply Curve", t) == "the-supply-curve"

    def test_case_insensitive_fuzzy_same_course(self):
        t = make_tiered(same_course={"supply curve": "supply-curve"})
        assert check_for_duplicates("Supply Curve", t) == "supply-curve"


class TestTieredSameGroup:
    """Tier 2: Same group — exact only, no fuzzy."""

    def test_exact_same_group(self):
        t = make_tiered(same_group={"NPV": "npv"})
        assert check_for_duplicates("NPV", t) == "npv"

    def test_fuzzy_does_not_match_same_group(self):
        """Fuzzy matching should NOT work for same_group — only exact."""
        t = make_tiered(same_group={"The Net Present Value": "the-npv"})
        assert check_for_duplicates("Net Present Value", t) is None

    def test_same_course_checked_before_same_group(self):
        t = make_tiered(
            same_course={"NPV": "npv-micro"},
            same_group={"NPV": "npv-finance"},
        )
        assert check_for_duplicates("NPV", t) == "npv-micro"


class TestTieredOther:
    """Tier 3: Other courses — exact only, no fuzzy."""

    def test_exact_other(self):
        t = make_tiered(other={"Equilibrium": "equilibrium"})
        assert check_for_duplicates("Equilibrium", t) == "equilibrium"

    def test_fuzzy_does_not_match_other(self):
        """Fuzzy matching should NOT work for other — only exact."""
        t = make_tiered(other={"Market Equilibrium": "market-equilibrium"})
        assert check_for_duplicates("Equilibrium", t) is None


class TestTieredPriority:
    """Verify the tier priority: same_course > same_group > other."""

    def test_same_course_beats_other(self):
        t = make_tiered(
            same_course={"NPV": "npv-same"},
            other={"NPV": "npv-other"},
        )
        assert check_for_duplicates("NPV", t) == "npv-same"

    def test_same_group_beats_other(self):
        t = make_tiered(
            same_group={"NPV": "npv-group"},
            other={"NPV": "npv-other"},
        )
        assert check_for_duplicates("NPV", t) == "npv-group"

    def test_fuzzy_same_course_beats_exact_other(self):
        """A fuzzy match in same_course should be found before an exact match in other."""
        t = make_tiered(
            same_course={"The Net Present Value": "the-npv-same"},
            other={"Net Present Value": "npv-other"},
        )
        # "Net Present Value" fuzzy matches "The Net Present Value" in same_course
        assert check_for_duplicates("Net Present Value", t) == "the-npv-same"

    def test_no_match_across_all_tiers(self):
        t = make_tiered(
            same_course={"Supply Curve": "supply-curve"},
            same_group={"Demand": "demand"},
            other={"Inflation": "inflation"},
        )
        assert check_for_duplicates("Game Theory", t) is None
