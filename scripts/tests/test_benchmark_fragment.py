"""Tests for lib/benchmark.yaml fragment and the harbor_scorer evaluator.

Covers:
- Fragment resolution (Shape B: _write_lib + resolve_fragments)
- Load-and-validate integration (Shape D: load_and_validate)
- Scorer dispatch: exit-code verdict mapping
- JSON output parsing / non-float handling
- Missing tasks dir error behavior
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from little_loops.fsm.evaluators import evaluate_harbor_scorer
from little_loops.fsm.fragments import resolve_fragments
from little_loops.fsm.schema import EvaluateConfig

# ---------------------------------------------------------------------------
# evaluate_harbor_scorer unit tests
# ---------------------------------------------------------------------------


class TestEvaluateHarborScorerVerdicts:
    """Unit tests for the evaluate_harbor_scorer evaluator function."""

    def test_exit_zero_with_float_gives_yes(self) -> None:
        result = evaluate_harbor_scorer("0.85\n", 0)
        assert result.verdict == "yes"
        assert result.details["score"] == pytest.approx(0.85)
        assert result.details["exit_code"] == 0

    def test_exit_zero_with_perfect_score(self) -> None:
        result = evaluate_harbor_scorer("1.0", 0)
        assert result.verdict == "yes"
        assert result.details["score"] == pytest.approx(1.0)

    def test_exit_zero_with_zero_score(self) -> None:
        result = evaluate_harbor_scorer("0.0", 0)
        assert result.verdict == "yes"
        assert result.details["score"] == pytest.approx(0.0)

    def test_nonzero_exit_gives_no(self) -> None:
        result = evaluate_harbor_scorer("", 1)
        assert result.verdict == "no"
        assert result.details["exit_code"] == 1

    def test_exit_two_gives_no(self) -> None:
        result = evaluate_harbor_scorer("some output", 2)
        assert result.verdict == "no"

    def test_exit_zero_with_non_float_gives_error(self) -> None:
        result = evaluate_harbor_scorer("not-a-float", 0)
        assert result.verdict == "error"
        assert "not a float" in result.details["error"].lower()

    def test_exit_zero_with_empty_output_gives_error(self) -> None:
        result = evaluate_harbor_scorer("", 0)
        assert result.verdict == "error"

    def test_exit_zero_with_json_output_gives_error(self) -> None:
        """JSON output is not directly parseable as float."""
        payload = json.dumps({"score": 0.9, "per_task": [], "run_id": "abc"})
        result = evaluate_harbor_scorer(payload, 0)
        assert result.verdict == "error"

    def test_whitespace_stripped_from_output(self) -> None:
        result = evaluate_harbor_scorer("  0.75  \n", 0)
        assert result.verdict == "yes"
        assert result.details["score"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Fragment resolution (Shape B: _write_lib + resolve_fragments)
# ---------------------------------------------------------------------------


class TestBenchmarkFragmentResolution:
    """Tests that resolve_fragments correctly deep-merges the run_benchmark fragment."""

    def _write_lib(self, lib_dir: Path) -> None:
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / "benchmark.yaml").write_text(
            textwrap.dedent(
                """\
                fragments:
                  run_benchmark:
                    description: |
                      Run a Harbor-format benchmark task directory.
                    action_type: shell
                    evaluate:
                      type: harbor_scorer
                """
            )
        )

    def test_fragment_merges_action_type(self, tmp_path: Path) -> None:
        self._write_lib(tmp_path / "lib")
        raw = {
            "name": "test",
            "initial": "score",
            "import": ["lib/benchmark.yaml"],
            "states": {
                "score": {
                    "fragment": "run_benchmark",
                    "action": "echo 0.9",
                    "on_yes": "done",
                    "on_no": "fail",
                },
                "done": {"terminal": True},
                "fail": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["score"]
        assert state["action_type"] == "shell"

    def test_fragment_merges_evaluate_type(self, tmp_path: Path) -> None:
        self._write_lib(tmp_path / "lib")
        raw = {
            "name": "test",
            "initial": "score",
            "import": ["lib/benchmark.yaml"],
            "states": {
                "score": {
                    "fragment": "run_benchmark",
                    "action": "echo 0.9",
                    "on_yes": "done",
                    "on_no": "fail",
                },
                "done": {"terminal": True},
                "fail": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["score"]
        assert state["evaluate"]["type"] == "harbor_scorer"

    def test_fragment_key_removed_after_resolution(self, tmp_path: Path) -> None:
        self._write_lib(tmp_path / "lib")
        raw = {
            "name": "test",
            "initial": "score",
            "import": ["lib/benchmark.yaml"],
            "states": {
                "score": {
                    "fragment": "run_benchmark",
                    "action": "echo 0.9",
                    "on_yes": "done",
                    "on_no": "fail",
                },
                "done": {"terminal": True},
                "fail": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        assert "fragment" not in result["states"]["score"]

    def test_caller_supplied_action_preserved(self, tmp_path: Path) -> None:
        self._write_lib(tmp_path / "lib")
        raw = {
            "name": "test",
            "initial": "score",
            "import": ["lib/benchmark.yaml"],
            "states": {
                "score": {
                    "fragment": "run_benchmark",
                    "action": "my-scorer /path/to/tasks",
                    "on_yes": "done",
                    "on_no": "fail",
                },
                "done": {"terminal": True},
                "fail": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        assert result["states"]["score"]["action"] == "my-scorer /path/to/tasks"

    def test_caller_can_add_capture(self, tmp_path: Path) -> None:
        self._write_lib(tmp_path / "lib")
        raw = {
            "name": "test",
            "initial": "score",
            "import": ["lib/benchmark.yaml"],
            "states": {
                "score": {
                    "fragment": "run_benchmark",
                    "action": "echo 0.9",
                    "capture": "benchmark_score",
                    "on_yes": "done",
                    "on_no": "fail",
                },
                "done": {"terminal": True},
                "fail": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        assert result["states"]["score"]["capture"] == "benchmark_score"


# ---------------------------------------------------------------------------
# Load-and-validate integration (Shape D)
# ---------------------------------------------------------------------------


class TestBenchmarkFragmentLoadAndValidate:
    """Integration: load_and_validate accepts harbor_scorer via lib/benchmark.yaml."""

    def test_load_and_validate_harbor_scorer_fragment(self, tmp_path: Path) -> None:
        """Fragment resolves and harbor_scorer passes FSM validation."""
        from little_loops.fsm.validation import load_and_validate

        loop_yaml = tmp_path / "bench.yaml"
        loop_yaml.write_text(
            textwrap.dedent(
                """\
                name: bench-test
                initial: score
                import:
                  - lib/benchmark.yaml
                states:
                  score:
                    fragment: run_benchmark
                    action: "echo 0.9"
                    on_yes: done
                    on_no: fail
                  done:
                    terminal: true
                  fail:
                    terminal: true
                """
            )
        )
        fsm, warnings = load_and_validate(loop_yaml)
        assert fsm is not None
        assert fsm.states["score"].action_type == "shell"
        assert fsm.states["score"].evaluate is not None
        assert fsm.states["score"].evaluate.type == "harbor_scorer"

    def test_no_unknown_key_warnings(self, tmp_path: Path) -> None:
        """Using lib/benchmark.yaml produces no unknown-key warnings."""
        from little_loops.fsm.validation import load_and_validate

        loop_yaml = tmp_path / "bench.yaml"
        loop_yaml.write_text(
            textwrap.dedent(
                """\
                name: bench-test
                initial: score
                import:
                  - lib/benchmark.yaml
                states:
                  score:
                    fragment: run_benchmark
                    action: "echo 0.9"
                    on_yes: done
                    on_no: fail
                  done:
                    terminal: true
                  fail:
                    terminal: true
                """
            )
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown = [w for w in warnings if "Unknown top-level" in str(w)]
        assert unknown == []


# ---------------------------------------------------------------------------
# EvaluateConfig schema: harbor_scorer accepted
# ---------------------------------------------------------------------------


class TestHarborScorerSchema:
    """Verify EvaluateConfig accepts harbor_scorer type."""

    def test_evaluate_config_accepts_harbor_scorer(self) -> None:
        config = EvaluateConfig(type="harbor_scorer")
        assert config.type == "harbor_scorer"

    def test_harbor_scorer_has_no_required_fields(self) -> None:
        """harbor_scorer requires no operator/target/pattern fields."""
        config = EvaluateConfig(type="harbor_scorer")
        assert config.operator is None
        assert config.target is None
        assert config.pattern is None


# ---------------------------------------------------------------------------
# Harbor fixture directory sanity checks
# ---------------------------------------------------------------------------


class TestHarborFixtures:
    """Verify the Harbor fixture directory has the correct structure."""

    @staticmethod
    def _harbor_dir() -> Path:
        return Path(__file__).parent / "fixtures" / "harbor"

    def test_harbor_dir_exists(self) -> None:
        assert self._harbor_dir().is_dir()

    def test_three_task_directories_exist(self) -> None:
        harbor = self._harbor_dir()
        task_dirs = [d for d in harbor.iterdir() if d.is_dir()]
        assert len(task_dirs) == 3

    def test_each_task_has_task_md(self) -> None:
        harbor = self._harbor_dir()
        for d in sorted(harbor.iterdir()):
            if d.is_dir():
                assert (d / "task.md").exists(), f"task.md missing in {d.name}"

    def test_each_task_has_expected_json(self) -> None:
        harbor = self._harbor_dir()
        for d in sorted(harbor.iterdir()):
            if d.is_dir():
                assert (d / "expected.json").exists(), f"expected.json missing in {d.name}"

    def test_expected_json_has_score_field(self) -> None:
        harbor = self._harbor_dir()
        for d in sorted(harbor.iterdir()):
            if d.is_dir():
                with open(d / "expected.json") as f:
                    data = json.load(f)
                assert "score" in data, f"expected.json in {d.name} missing 'score' field"
                assert isinstance(data["score"], (int, float)), (
                    f"expected.json in {d.name}: 'score' must be numeric"
                )
