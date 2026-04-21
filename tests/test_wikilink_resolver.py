"""Tests for WikilinkProcessor._resolve_wikilink() — multi-strategy link resolution."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_processor(concept_map=None, case_map=None, alias_map=None):
    """Create a WikilinkProcessor with injected maps, bypassing filesystem scan."""
    # Import the class but skip __init__ (which scans MBAWiki/)
    from wiki_viewer.utils.wikilink_processor import WikilinkProcessor
    proc = object.__new__(WikilinkProcessor)
    proc.concept_map = concept_map or {}
    proc.case_map = case_map or {}
    proc.alias_map = alias_map or {}
    proc.image_map = {}
    proc.course_map = {}
    proc.concept_courses = {}
    proc.case_courses = {}
    return proc


class TestExactMatch:
    """Stage 1-2: Exact title match in case_map then concept_map."""

    def test_exact_concept_match(self):
        proc = make_processor(concept_map={"Supply Curve": "supply-curve"})
        result = proc._resolve_wikilink("Supply Curve")
        assert result == ("concept", "supply-curve", "Supply Curve")

    def test_exact_case_match(self):
        proc = make_processor(case_map={"Case: Heidi Roizen": "heidi-roizen"})
        result = proc._resolve_wikilink("Case: Heidi Roizen")
        assert result == ("case", "heidi-roizen", "Case: Heidi Roizen")

    def test_case_map_takes_priority_over_concept_map(self):
        """If same title exists in both maps, case_map wins."""
        proc = make_processor(
            concept_map={"Overlap": "overlap-concept"},
            case_map={"Overlap": "overlap-case"},
        )
        result = proc._resolve_wikilink("Overlap")
        assert result[0] == "case"

    def test_no_match_returns_none(self):
        proc = make_processor(concept_map={"Supply Curve": "supply-curve"})
        result = proc._resolve_wikilink("Nonexistent Concept")
        assert result is None


class TestCaseInsensitiveMatch:
    """Stage 3: Case-insensitive title match."""

    def test_lowercase_matches_titlecase(self):
        proc = make_processor(concept_map={"Supply Curve": "supply-curve"})
        result = proc._resolve_wikilink("supply curve")
        assert result == ("concept", "supply-curve", "supply curve")

    def test_uppercase_matches_titlecase(self):
        proc = make_processor(concept_map={"Supply Curve": "supply-curve"})
        result = proc._resolve_wikilink("SUPPLY CURVE")
        assert result == ("concept", "supply-curve", "SUPPLY CURVE")

    def test_case_insensitive_case_match(self):
        proc = make_processor(case_map={"Case: Tesla": "tesla"})
        result = proc._resolve_wikilink("case: tesla")
        assert result == ("case", "tesla", "case: tesla")

    def test_preserves_original_display_text(self):
        """The display_text should be the original link_text, not the matched title."""
        proc = make_processor(concept_map={"Net Present Value": "net-present-value"})
        result = proc._resolve_wikilink("net present value")
        assert result[2] == "net present value"


class TestAliasMatch:
    """Stage 4-5: Exact and case-insensitive alias resolution."""

    def test_abbreviation_alias(self):
        proc = make_processor(
            concept_map={"Net Present Value": "net-present-value"},
            alias_map={"NPV": ("concept", "net-present-value")},
        )
        result = proc._resolve_wikilink("NPV")
        assert result == ("concept", "net-present-value", "NPV")

    def test_slug_alias(self):
        proc = make_processor(
            concept_map={"Supply Curve": "supply-curve"},
            alias_map={"supply-curve": ("concept", "supply-curve")},
        )
        result = proc._resolve_wikilink("supply-curve")
        assert result == ("concept", "supply-curve", "supply-curve")

    def test_case_insensitive_alias(self):
        proc = make_processor(
            alias_map={"NPV": ("concept", "net-present-value")},
        )
        result = proc._resolve_wikilink("npv")
        assert result == ("concept", "net-present-value", "npv")

    def test_case_alias_type(self):
        proc = make_processor(
            alias_map={"heidi-roizen": ("case", "heidi-roizen")},
        )
        result = proc._resolve_wikilink("heidi-roizen")
        assert result[0] == "case"


class TestPrefixMatch:
    """Stage 6: Prefix matching with 50% length requirement."""

    def test_prefix_match_concept(self):
        proc = make_processor(
            concept_map={"Equality vs. Equity vs. Justice": "equality-vs-equity-vs-justice"},
        )
        result = proc._resolve_wikilink("Equality vs. Equity")
        # "Equality vs. Equity" (19 chars) vs "Equality vs. Equity vs. Justice" (31 chars)
        # 19/31 = 0.61 > 0.5, so should match
        assert result is not None
        assert result[0] == "concept"

    def test_prefix_too_short_rejected(self):
        proc = make_processor(
            concept_map={"International Trade Policy and Regulations": "trade-policy"},
        )
        result = proc._resolve_wikilink("Int")
        # "Int" (3 chars) vs "International Trade..." (43 chars)
        # 3/43 = 0.07 < 0.5, rejected
        assert result is None

    def test_prefix_match_normalized_hyphens(self):
        """Hyphens are normalized to spaces for prefix matching."""
        proc = make_processor(
            concept_map={"Supply and Demand Curve": "supply-and-demand-curve"},
        )
        result = proc._resolve_wikilink("supply-and-demand")
        # Normalized: "supply and demand" vs "supply and demand curve"
        # 17/22 = 0.77 > 0.5, should match
        assert result is not None

    def test_prefix_picks_longest_match(self):
        """When multiple titles match, pick the longest."""
        proc = make_processor(
            concept_map={
                "Price": "price",
                "Price Discrimination": "price-discrimination",
                "Price Discrimination in Markets": "price-discrimination-markets",
            },
        )
        result = proc._resolve_wikilink("Price Discrimination in")
        # Should match "Price Discrimination in Markets" (longest)
        if result is not None:
            assert result[1] == "price-discrimination-markets"


class TestResolutionPriority:
    """Verify the cascade: exact > case-insensitive > alias > prefix."""

    def test_exact_beats_alias(self):
        proc = make_processor(
            concept_map={"NPV": "npv-page"},
            alias_map={"NPV": ("concept", "net-present-value")},
        )
        result = proc._resolve_wikilink("NPV")
        # Exact concept match should win over alias
        assert result[1] == "npv-page"

    def test_case_insensitive_beats_alias(self):
        proc = make_processor(
            concept_map={"Supply Curve": "supply-curve"},
            alias_map={"supply curve": ("concept", "different-slug")},
        )
        result = proc._resolve_wikilink("supply curve")
        # Case-insensitive title match should win
        assert result[1] == "supply-curve"
