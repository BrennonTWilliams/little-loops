"""Tests for little_loops.output_cleaner (FEAT-2470, EPIC-2456 technique [25]).

Pure-function tests following the ``Test<FunctionName>`` class-per-function
shape from ``test_output_parsing.py`` (no tmp_path, no monkeypatch).
"""

from __future__ import annotations

from little_loops.output_cleaner import filter_output


class TestFilterOutputAntiEvents:
    def test_drops_tqdm_progress_bar(self) -> None:
        raw = "start\n 42%|████████  | 3/7 [00:01<00:02]\ndone"
        assert filter_output(raw) == "start\ndone"

    def test_drops_ascii_progress_bar(self) -> None:
        raw = "start\n[====>      ] 40%\ndone"
        assert filter_output(raw) == "start\ndone"

    def test_drops_xdist_bringup_and_worker_chatter(self) -> None:
        raw = "bringing up nodes...\n[gw0] PASSED test_foo\nresult"
        # Both the bring-up line and the [gw0] worker line are anti-events.
        assert filter_output(raw) == "result"

    def test_strips_ansi_before_matching(self) -> None:
        # ANSI-wrapped progress bar still matches the anti-event pattern.
        raw = "keep\n\x1b[32m[####........]\x1b[0m\nkeep2"
        assert filter_output(raw) == "keep\nkeep2"

    def test_preserves_real_content(self) -> None:
        raw = "line one\nline two\nline three"
        assert filter_output(raw) == raw


class TestFilterOutputDuplicateWindows:
    def test_collapses_consecutive_duplicates(self) -> None:
        raw = "err\nerr\nerr\nerr\ntail"
        out = filter_output(raw)
        assert out == "err\n… (repeated 4×)\ntail"

    def test_single_occurrence_not_collapsed(self) -> None:
        raw = "a\nb\nc"
        assert filter_output(raw) == "a\nb\nc"

    def test_non_consecutive_duplicates_kept(self) -> None:
        raw = "a\nb\na"
        assert filter_output(raw) == "a\nb\na"

    def test_marker_preserves_indent(self) -> None:
        raw = "    warn\n    warn\n    warn"
        out = filter_output(raw)
        assert out == "    warn\n    … (repeated 3×)"

    def test_custom_threshold(self) -> None:
        # threshold=3 → a run of 3 is NOT collapsed, a run of 4 IS.
        assert filter_output("x\nx\nx", dup_threshold=3) == "x\nx\nx"
        assert filter_output("x\nx\nx\nx", dup_threshold=3) == "x\n… (repeated 4×)"


class TestFilterOutputBlankLines:
    def test_collapses_multiple_blank_lines(self) -> None:
        raw = "a\n\n\n\nb"
        assert filter_output(raw) == "a\n\nb"

    def test_blank_lines_do_not_get_repeated_marker(self) -> None:
        out = filter_output("a\n\n\n\n\nb")
        assert "repeated" not in out

    def test_blank_breaks_duplicate_run(self) -> None:
        # A blank between identical lines means they are not consecutive.
        raw = "x\n\nx"
        assert filter_output(raw) == "x\n\nx"


class TestFilterOutputEdges:
    def test_empty_string(self) -> None:
        assert filter_output("") == ""

    def test_preserves_trailing_newline(self) -> None:
        assert filter_output("a\nb\n").endswith("\n")

    def test_no_trailing_newline_stays_absent(self) -> None:
        assert not filter_output("a\nb").endswith("\n")
