"""Tests for little_loops.fsm.policy_parse_scores (BUG-3489)."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.fsm.policy_parse_scores import main, parse_scores


class TestParseScoresRecognition:
    def test_aggregate_and_dimensions_recognized(self) -> None:
        output = (
            "DIMENSION: security: 42 — rationale text\n"
            "DIMENSION: clarity: 90 — rationale text\n"
            "AGGREGATE: 66\n"
        )
        aggregate, dims = parse_scores(output)
        assert aggregate == 66
        assert dims == {"security": "42", "clarity": "90"}

    def test_dimension_name_normalization_lowercases_and_hyphenates(self) -> None:
        aggregate, dims = parse_scores("DIMENSION: Test Coverage: 75 — ok\nAGGREGATE: 75\n")
        assert dims == {"test-coverage": "75"}

    def test_recognized_dimensions_without_aggregate_returns_none_aggregate(self) -> None:
        aggregate, dims = parse_scores("DIMENSION: security: 42 — ok\n")
        assert aggregate is None
        assert dims == {"security": "42"}

    def test_recognized_aggregate_without_dimensions_returns_empty_mapping(self) -> None:
        aggregate, dims = parse_scores("AGGREGATE: 80\n")
        assert aggregate == 80
        assert dims == {}

    def test_duplicate_dimension_lines_last_one_wins(self) -> None:
        output = "DIMENSION: security: 10 — first\nDIMENSION: security: 90 — second\n"
        _, dims = parse_scores(output)
        assert dims == {"security": "90"}

    def test_wholly_unparseable_output_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_scores("no recognized lines here at all\n")

    def test_empty_output_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_scores("")


class TestMainCleanSlateAndPropagation:
    def _write_input(self, run_dir: Path, output: str) -> None:
        (run_dir / "policy_parse_scores-scores.txt").write_text(output, encoding="utf-8")

    def test_writes_aggregate_and_dimension_files(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        self._write_input(run_dir, "DIMENSION: security: 42 — ok\nAGGREGATE: 66\n")

        rc = main([str(run_dir)])

        assert rc == 0
        assert (run_dir / "rubric-aggregate.txt").read_text() == "66"
        assert (run_dir / "rubric-dim-security.txt").read_text() == "42"

    def test_two_pass_clean_slate_drops_omitted_dimension_and_aggregate(
        self, tmp_path: Path
    ) -> None:
        """The exact BUG-3489 reproduction: a dimension present on pass one and
        omitted on pass two must not leave the pass-one score in play."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        self._write_input(
            run_dir, "DIMENSION: citations: 100 — ok\nDIMENSION: security: 80 — ok\nAGGREGATE: 90\n"
        )
        assert main([str(run_dir)]) == 0
        assert (run_dir / "rubric-dim-citations.txt").exists()

        # Pass two omits `citations` and `AGGREGATE`.
        self._write_input(run_dir, "DIMENSION: security: 40 — ok\n")
        assert main([str(run_dir)]) == 0

        assert not (run_dir / "rubric-dim-citations.txt").exists()
        assert not (run_dir / "rubric-aggregate.txt").exists()
        assert (run_dir / "rubric-dim-security.txt").read_text() == "40"

    def test_unrelated_run_artifacts_survive_clean_slate(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "policy-action.txt").write_text("some-prior-action", encoding="utf-8")
        self._write_input(run_dir, "AGGREGATE: 50\n")

        assert main([str(run_dir)]) == 0
        assert (run_dir / "policy-action.txt").read_text() == "some-prior-action"

    def test_missing_run_dir_argument_returns_nonzero(self) -> None:
        assert main([]) != 0

    def test_missing_input_file_returns_nonzero_and_writes_nothing(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        rc = main([str(run_dir)])

        assert rc != 0
        assert list(run_dir.glob("rubric-*.txt")) == []

    def test_unparseable_input_returns_nonzero_and_writes_nothing(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        self._write_input(run_dir, "nothing recognized here\n")

        rc = main([str(run_dir)])

        assert rc != 0
        assert list(run_dir.glob("rubric-*.txt")) == []

    def test_creates_run_dir_when_absent(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "does-not-exist-yet"
        # main() creates the directory before trying to read the input file,
        # so the read still fails (no input written), but the directory
        # itself must exist afterward rather than raising on mkdir.
        rc = main([str(run_dir)])
        assert rc != 0
        assert run_dir.is_dir()
