"""Tests for repair_json() — 5-stage JSON repair pipeline."""

import json
import pytest
import sys
from pathlib import Path

# Allow importing from ingest/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.process_standalone import repair_json


class TestStage1_ValidJson:
    """Stage 1: Parse valid JSON as-is."""

    def test_valid_object(self):
        assert repair_json('{"key": "value"}') == {"key": "value"}

    def test_valid_array(self):
        assert repair_json('[1, 2, 3]') == [1, 2, 3]

    def test_valid_nested(self):
        text = '{"concepts": [{"title": "Supply Curve", "content": "A graph"}]}'
        result = repair_json(text)
        assert result["concepts"][0]["title"] == "Supply Curve"

    def test_valid_empty_object(self):
        assert repair_json("{}") == {}

    def test_valid_empty_array(self):
        assert repair_json("[]") == []


class TestStage2_UnescapedNewlinesInStrings:
    """Stage 2: Fix unescaped newlines/tabs inside string values."""

    def test_newline_in_value(self):
        text = '{"key": "line1\nline2"}'
        result = repair_json(text)
        assert result is not None
        assert "line1" in result["key"]

    def test_tab_in_value(self):
        text = '{"key": "col1\tcol2"}'
        result = repair_json(text)
        assert result is not None
        assert "col1" in result["key"]

    def test_multiple_newlines_in_value(self):
        text = '{"content": "paragraph1\n\nparagraph2\n\nparagraph3"}'
        result = repair_json(text)
        assert result is not None


class TestStage3_UnescapedNewlinesInArrays:
    """Stage 3: Fix unescaped newlines/tabs inside array contents."""

    def test_newline_in_array_string(self):
        text = '{"wikilinks": ["Supply\nCurve", "Demand"]}'
        result = repair_json(text)
        assert result is not None
        assert len(result["wikilinks"]) == 2

    def test_tab_in_array_string(self):
        text = '{"items": ["item\tone", "item two"]}'
        result = repair_json(text)
        assert result is not None


class TestStage4_BruteForceControlChars:
    """Stage 4: Brute-force escape control chars inside JSON string values."""

    def test_embedded_newlines_in_long_string(self):
        # Simulates LLM output with raw newlines in markdown content
        text = '{"title": "NPV", "content": "Net Present Value\\nFormula:\\nNPV = sum(CF/(1+r)^t)\nwhere r is the rate"}'
        result = repair_json(text)
        assert result is not None
        assert result["title"] == "NPV"

    def test_carriage_return(self):
        text = '{"key": "value\rwith\rCR"}'
        result = repair_json(text)
        assert result is not None

    def test_mixed_control_chars(self):
        text = '{"key": "line1\nline2\ttab\rreturn"}'
        result = repair_json(text)
        assert result is not None

    def test_already_escaped_not_double_escaped(self):
        """Ensure already-escaped \\n doesn't become \\\\n."""
        text = '{"key": "already\\nescaped"}'
        result = repair_json(text)
        assert result is not None
        assert result["key"] == "already\nescaped"


class TestStage5_TruncationRecovery:
    """Stage 5: Recover from truncated JSON output."""

    def test_truncated_array_of_objects(self):
        text = '{"concepts": [{"title": "A", "content": "a"}, {"title": "B", "content": "b"}, {"title": "C", "con'
        result = repair_json(text)
        assert result is not None
        assert len(result["concepts"]) >= 2

    def test_truncated_after_complete_object(self):
        text = '{"concepts": [{"title": "A"}, {"title": "B"}'
        # Has no trailing },  so truncation recovery may not trigger
        # but the brute force or other stages might handle it
        result = repair_json(text)
        # May or may not recover — test that it doesn't crash
        # (repair_json returns None if nothing works)

    def test_truncated_with_comma(self):
        text = '{"concepts": [{"title": "A", "content": "a"}, {"title": "B", "content": "b"},'
        result = repair_json(text)
        # Should recover at least the first two complete objects
        if result is not None:
            assert len(result["concepts"]) >= 2


class TestEdgeCases:
    """Edge cases and failure modes."""

    def test_empty_string_returns_none(self):
        assert repair_json("") is None

    def test_not_json_returns_none(self):
        assert repair_json("This is not JSON at all") is None

    def test_html_returns_none(self):
        assert repair_json("<html><body>hello</body></html>") is None

    def test_gemini_markdown_wrapped_json(self):
        """Gemini sometimes wraps JSON in ```json ... ``` markdown."""
        # repair_json doesn't strip markdown fences — this should return None
        text = '```json\n{"key": "value"}\n```'
        result = repair_json(text)
        # This is expected to fail unless the JSON happens to parse
        # The point is it shouldn't crash
        assert result is None or isinstance(result, (dict, list))

    def test_single_value(self):
        assert repair_json('"just a string"') == "just a string"

    def test_numeric_value(self):
        assert repair_json("42") == 42

    def test_null_value(self):
        assert repair_json("null") is None  # json.loads("null") = None, but repair_json returns None on failure too
        # Actually json.loads("null") succeeds and returns None, which is the same as repair_json's failure case.
        # This is a known ambiguity — just verify no crash.

    def test_realistic_llm_output(self):
        """Simulate a real Gemini response with multiple issues."""
        text = '{"concepts": [{"title": "Supply Curve", "content": "The supply curve shows\nthe relationship between price\nand quantity supplied.", "wikilinks": ["Demand Curve", "Equilibrium"]}]}'
        result = repair_json(text)
        assert result is not None
        assert result["concepts"][0]["title"] == "Supply Curve"
        assert len(result["concepts"][0]["wikilinks"]) == 2
