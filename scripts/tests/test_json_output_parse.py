"""Tests for little_loops.output.parse (FEAT-2470, EPIC-2456 pass-2 #7).

Pure-function tests following the ``Test<FunctionName>`` class-per-function
shape from ``test_output_parsing.py:TestParseSections`` (no tmp_path,
no monkeypatch). Both helpers return a ``(value, error)`` tuple.
"""

from __future__ import annotations

from little_loops.output.parse import extract_between_tags, parse_prefilled_json


class TestExtractBetweenTags:
    def test_clean_extraction(self) -> None:
        value, err = extract_between_tags("<json>", "</json>", "noise <json>{\"a\": 1}</json> tail")
        assert err is None
        assert value == '{"a": 1}'

    def test_strips_surrounding_whitespace(self) -> None:
        value, err = extract_between_tags("<x>", "</x>", "<x>\n  hi  \n</x>")
        assert err is None
        assert value == "hi"

    def test_missing_end_tag_returns_remainder(self) -> None:
        # Stop-sequence recipe: closing tag consumed as the stop sequence.
        value, err = extract_between_tags("<json>", "</json>", 'prefix <json>{"a": 1}')
        assert err is None
        assert value == '{"a": 1}'

    def test_missing_start_tag_is_error(self) -> None:
        value, err = extract_between_tags("<json>", "</json>", "no tags here")
        assert value is None
        assert err is not None
        assert "<json>" in err

    def test_first_occurrence_used(self) -> None:
        value, err = extract_between_tags("<t>", "</t>", "<t>one</t><t>two</t>")
        assert err is None
        assert value == "one"

    def test_empty_content(self) -> None:
        value, err = extract_between_tags("<t>", "</t>", "<t></t>")
        assert err is None
        assert value == ""


class TestParsePrefilledJson:
    def test_clean_bare_object(self) -> None:
        obj, err = parse_prefilled_json('{"verdict": "yes", "confidence": 0.9}')
        assert err is None
        assert obj == {"verdict": "yes", "confidence": 0.9}

    def test_object_with_leading_prose(self) -> None:
        obj, err = parse_prefilled_json('Here is the result: {"verdict": "no"}')
        assert err is None
        assert obj == {"verdict": "no"}

    def test_object_with_trailing_prose(self) -> None:
        obj, err = parse_prefilled_json('{"verdict": "partial"}\nThat is my answer.')
        assert err is None
        assert obj == {"verdict": "partial"}

    def test_nested_object(self) -> None:
        obj, err = parse_prefilled_json('{"a": {"b": {"c": 1}}, "d": [1, 2]}')
        assert err is None
        assert obj == {"a": {"b": {"c": 1}}, "d": [1, 2]}

    def test_braces_inside_string_do_not_confuse_scan(self) -> None:
        obj, err = parse_prefilled_json('{"note": "use {curly} braces \\"here\\""}')
        assert err is None
        assert obj == {"note": 'use {curly} braces "here"'}

    def test_last_object_wins_with_rfind(self) -> None:
        # rfind('{') recipe: recover the final object when text has fragments.
        obj, err = parse_prefilled_json('{"stale": 1} ... final: {"fresh": 2}')
        assert err is None
        assert obj == {"fresh": 2}

    def test_empty_output_is_error(self) -> None:
        obj, err = parse_prefilled_json("   ")
        assert obj is None
        assert err is not None

    def test_no_brace_is_error(self) -> None:
        obj, err = parse_prefilled_json("no json here at all")
        assert obj is None
        assert err is not None

    def test_unbalanced_object_is_error(self) -> None:
        obj, err = parse_prefilled_json('{"a": 1')
        assert obj is None
        assert err is not None

    def test_malformed_object_is_error(self) -> None:
        obj, err = parse_prefilled_json('{"a": }')
        assert obj is None
        assert err is not None
