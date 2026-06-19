"""Tests for little_loops.learning_tests.extractor module (ENH-2209)."""

from __future__ import annotations

from little_loops.learning_tests.extractor import extract_learning_targets


def _make_llm(response: str):
    """Return a mock llm_call that always returns the given response."""

    def _call(prompt: str) -> str:
        return response

    return _call


class TestExtractLearningTargets:
    def test_returns_empty_list_when_no_external_deps(self) -> None:
        mock = _make_llm('No external deps here.\nTARGETS_JSON:{"targets": [], "count": 0}')
        result = extract_learning_targets("plain issue with no API deps", llm_call=mock)
        assert result == []

    def test_extracts_single_target(self) -> None:
        mock = _make_llm('Found one.\nTARGETS_JSON:{"targets": ["anthropic"], "count": 1}')
        result = extract_learning_targets("uses the anthropic SDK", llm_call=mock)
        assert result == ["anthropic"]

    def test_extracts_multiple_targets(self) -> None:
        resp = 'analysis\nTARGETS_JSON:{"targets": ["anthropic", "requests", "stripe"], "count": 3}'
        mock = _make_llm(resp)
        result = extract_learning_targets("uses anthropic, requests, stripe", llm_call=mock)
        assert result == ["anthropic", "requests", "stripe"]

    def test_deduplicates_by_slug(self) -> None:
        resp = 'TARGETS_JSON:{"targets": ["Anthropic", "anthropic", "ANTHROPIC"], "count": 3}'
        mock = _make_llm(resp)
        result = extract_learning_targets("uses anthropic", llm_call=mock)
        assert len(result) == 1
        assert result[0] == "Anthropic"  # first occurrence preserved

    def test_strips_whitespace_from_names(self) -> None:
        resp = 'TARGETS_JSON:{"targets": ["  boto3  ", "requests"], "count": 2}'
        mock = _make_llm(resp)
        result = extract_learning_targets("uses boto3 and requests", llm_call=mock)
        assert "boto3" in result
        assert "requests" in result

    def test_returns_empty_when_no_json_marker(self) -> None:
        mock = _make_llm("I found anthropic and requests as dependencies.")
        result = extract_learning_targets("uses anthropic", llm_call=mock)
        assert result == []

    def test_returns_empty_on_invalid_json(self) -> None:
        mock = _make_llm("TARGETS_JSON:{not valid json}")
        result = extract_learning_targets("uses anthropic", llm_call=mock)
        assert result == []

    def test_filters_blank_target_names(self) -> None:
        resp = 'TARGETS_JSON:{"targets": ["anthropic", "", "  ", "requests"], "count": 4}'
        mock = _make_llm(resp)
        result = extract_learning_targets("uses anthropic and requests", llm_call=mock)
        assert "" not in result
        assert "  " not in result
        assert "anthropic" in result
        assert "requests" in result

    def test_mock_injection_receives_prompt_with_issue_text(self) -> None:
        captured: list[str] = []

        def _capture(prompt: str) -> str:
            captured.append(prompt)
            return 'TARGETS_JSON:{"targets": [], "count": 0}'

        issue_text = "## Summary\nUses the Stripe API for billing."
        extract_learning_targets(issue_text, llm_call=_capture)
        assert len(captured) == 1
        assert issue_text in captured[0]

    def test_handles_missing_targets_key(self) -> None:
        mock = _make_llm('TARGETS_JSON:{"count": 0}')
        result = extract_learning_targets("issue text", llm_call=mock)
        assert result == []

    def test_json_marker_can_appear_mid_response(self) -> None:
        resp = (
            'Analyzing...\nFound external deps.\nTARGETS_JSON:{"targets": ["httpx"], "count": 1}\n'
        )
        mock = _make_llm(resp)
        result = extract_learning_targets("uses httpx", llm_call=mock)
        assert result == ["httpx"]
