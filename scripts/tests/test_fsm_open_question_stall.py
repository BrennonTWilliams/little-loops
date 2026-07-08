"""Tests for evaluate_open_question_stall and the open_question_stall evaluator (ENH-2446).

Mirrors TestScoreStallEvaluator at scripts/tests/test_fsm_evaluators.py:1472-1566.
Like score_stall, this evaluator is stateless across calls: the per-round
count-history file is the persisted state. Unlike score_stall, lower counts
are *better* (open questions being resolved is progress), so the
strictly-decreasing-counter check is inverted.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.fsm.interpolation import InterpolationContext
from little_loops.fsm.schema import EvaluateConfig


class TestOpenQuestionStallEvaluator:
    """Tests for evaluate_open_question_stall (ENH-2446).

    Reads a per-round open-question-count history file (one integer per line)
    and detects when the count stops strictly decreasing for `max_stall`
    consecutive rounds. Returns `no` (accept best-so-far / stop) when the
    stall threshold is hit; `yes` (continue) while progress is being made.
    """

    def _write_history(self, tmp_path: Path, counts: list[int]) -> str:
        hist = tmp_path / ".open_questions_history"
        hist.write_text("".join(f"{c}\n" for c in counts))
        return str(hist)

    def test_missing_history_returns_success(self, tmp_path: Path) -> None:
        """No history file yet (first iterations) returns yes (keep going)."""
        from little_loops.fsm.evaluators import evaluate_open_question_stall

        result = evaluate_open_question_stall(
            str(tmp_path / ".open_questions_history"), max_stall=2
        )
        assert result.verdict == "yes"
        assert result.details["stall_count"] == 0
        assert result.details["rounds"] == 0

    def test_single_count_returns_success(self, tmp_path: Path) -> None:
        """A single recorded count is not enough to declare a plateau."""
        from little_loops.fsm.evaluators import evaluate_open_question_stall

        hist = self._write_history(tmp_path, [5])
        result = evaluate_open_question_stall(hist, max_stall=2)
        assert result.verdict == "yes"
        assert result.details["rounds"] == 1

    def test_flat_history_at_threshold_returns_failure(self, tmp_path: Path) -> None:
        """A flat count history plateaus and returns no at max_stall rounds."""
        from little_loops.fsm.evaluators import evaluate_open_question_stall

        hist = self._write_history(tmp_path, [5, 5, 5])
        result = evaluate_open_question_stall(hist, max_stall=2)
        assert result.verdict == "no"
        assert result.details["stall_count"] == 2
        assert result.details["max_stall"] == 2

    def test_flat_history_below_threshold_returns_success(self, tmp_path: Path) -> None:
        """Below the max_stall threshold, a flat history still returns yes."""
        from little_loops.fsm.evaluators import evaluate_open_question_stall

        hist = self._write_history(tmp_path, [5, 5])
        result = evaluate_open_question_stall(hist, max_stall=2)
        assert result.verdict == "yes"
        assert result.details["stall_count"] == 1

    def test_progress_resets_counter(self, tmp_path: Path) -> None:
        """A count strictly less than the previous minimum resets the stall counter."""
        from little_loops.fsm.evaluators import evaluate_open_question_stall

        hist = self._write_history(tmp_path, [5, 5, 3])
        result = evaluate_open_question_stall(hist, max_stall=2)
        assert result.verdict == "yes"
        assert result.details["stall_count"] == 0

    def test_increasing_count_returns_failure(self, tmp_path: Path) -> None:
        """An increasing count is bad: it should not reset the stall counter."""
        from little_loops.fsm.evaluators import evaluate_open_question_stall

        hist = self._write_history(tmp_path, [3, 5, 7])
        result = evaluate_open_question_stall(hist, max_stall=2)
        assert result.verdict == "no"
        assert result.details["stall_count"] == 2

    def test_zero_count_means_resolved(self, tmp_path: Path) -> None:
        """Reaching zero open questions is the terminal state — always yes."""
        from little_loops.fsm.evaluators import evaluate_open_question_stall

        hist = self._write_history(tmp_path, [3, 2, 1, 0])
        result = evaluate_open_question_stall(hist, max_stall=2)
        assert result.verdict == "yes"
        assert result.details["best"] == 0

    def test_blank_and_garbage_lines_ignored(self, tmp_path: Path) -> None:
        """Blank and non-numeric lines are skipped when parsing history."""
        from little_loops.fsm.evaluators import evaluate_open_question_stall

        hist = tmp_path / ".open_questions_history"
        hist.write_text("5\n\nnot-a-number\n5\n5\n")
        result = evaluate_open_question_stall(str(hist), max_stall=2)
        assert result.verdict == "no"
        assert result.details["rounds"] == 3

    def test_dispatch_open_question_stall(self, tmp_path: Path) -> None:
        """evaluate() dispatcher routes open_question_stall with explicit history_file."""
        from little_loops.fsm.evaluators import evaluate

        hist = self._write_history(tmp_path, [5, 5, 5])
        config = EvaluateConfig(type="open_question_stall", history_file=hist, max_stall=2)
        ctx = InterpolationContext()
        result = evaluate(config, "", 0, ctx)
        assert result.verdict == "no"
        assert result.details["max_stall"] == 2

    def test_dispatch_defaults_to_run_dir_history(self, tmp_path: Path) -> None:
        """With no history_file, evaluate() reads ${context.run_dir}/.open_questions_history."""
        from little_loops.fsm.evaluators import evaluate

        self._write_history(tmp_path, [7, 7, 7])
        config = EvaluateConfig(type="open_question_stall", max_stall=2)
        ctx = InterpolationContext(context={"run_dir": str(tmp_path)})
        result = evaluate(config, "", 0, ctx)
        assert result.verdict == "no"

    def test_dispatch_nonzero_exit_does_not_short_circuit(self, tmp_path: Path) -> None:
        """open_question_stall is exit-code-aware: a nonzero action exit is not an error."""
        from little_loops.fsm.evaluators import evaluate

        hist = self._write_history(tmp_path, [5, 5, 5])
        config = EvaluateConfig(type="open_question_stall", history_file=hist, max_stall=2)
        ctx = InterpolationContext()
        result = evaluate(config, "", 1, ctx)
        assert result.verdict == "no"


class TestOpenQuestionStallGateFragment:
    """The open_question_stall_gate fragment exists in lib/common.yaml (ENH-2446)."""

    def test_open_question_stall_gate_defined(self) -> None:
        import yaml

        common_yaml = (
            Path(__file__).resolve().parents[1] / "little_loops" / "loops" / "lib" / "common.yaml"
        )
        data = yaml.safe_load(common_yaml.read_text())
        assert "open_question_stall_gate" in data["fragments"], (
            "open_question_stall_gate fragment must be defined in lib/common.yaml"
        )

    def test_open_question_stall_gate_evaluator_type(self) -> None:
        import yaml

        common_yaml = (
            Path(__file__).resolve().parents[1] / "little_loops" / "loops" / "lib" / "common.yaml"
        )
        frag = yaml.safe_load(common_yaml.read_text())["fragments"]["open_question_stall_gate"]
        assert frag["evaluate"]["type"] == "open_question_stall"

    def test_open_question_stall_gate_has_max_stall_override(self) -> None:
        import yaml

        common_yaml = (
            Path(__file__).resolve().parents[1] / "little_loops" / "loops" / "lib" / "common.yaml"
        )
        frag = yaml.safe_load(common_yaml.read_text())["fragments"]["open_question_stall_gate"]
        # Default EvaluateConfig max_stall is 1; the fragment should override to 2
        # (mirroring score_stall_gate's 2-round plateau).
        assert frag["evaluate"]["max_stall"] >= 2

    def test_open_question_stall_gate_resolves_in_loop(self, tmp_path: Path) -> None:
        """The fragment merges into a consuming state via fragments resolver."""
        from little_loops.fsm.fragments import resolve_fragments

        common_yaml = (
            Path(__file__).resolve().parents[1] / "little_loops" / "loops" / "lib" / "common.yaml"
        )
        # Use the lib as the loop's directory so resolve_fragments can find it.
        loop_dir = common_yaml.parent
        loop_yaml = {
            "import": ["common.yaml"],
            "fragments": {},
            "states": {
                "check_open_question_progress": {
                    "fragment": "open_question_stall_gate",
                    "action_type": "shell",
                    "action": "echo 5",
                    "on_yes": "next",
                    "on_no": "stop",
                }
            },
        }
        resolved = resolve_fragments(loop_yaml, loop_dir)
        state = resolved["states"]["check_open_question_progress"]
        assert state["evaluate"]["type"] == "open_question_stall"


class TestOpenQuestionStallDisplay:
    """_EVALUATE_TYPE_DISPLAY has the new evaluator's label (ENH-2446)."""

    def test_display_label_in_info(self) -> None:
        from little_loops.cli.loop.info import _EVALUATE_TYPE_DISPLAY

        assert "open_question_stall" in _EVALUATE_TYPE_DISPLAY
        assert _EVALUATE_TYPE_DISPLAY["open_question_stall"] == "open question stall"


class TestMR1NonLLMEvaluatorForOpenQuestionStall:
    """MR-1 holds: open_question_stall is a non-LLM gate (ENH-2446)."""

    def test_non_llm_classification(self) -> None:
        """open_question_stall reads a file, so it's classified as non-LLM."""
        from little_loops.fsm.validation import (
            EVALUATOR_REQUIRED_FIELDS,
            NON_LLM_EVALUATOR_TYPES,
        )

        assert "open_question_stall" in EVALUATOR_REQUIRED_FIELDS
        assert "open_question_stall" in NON_LLM_EVALUATOR_TYPES

    def test_required_fields_empty(self) -> None:
        from little_loops.fsm.validation import EVALUATOR_REQUIRED_FIELDS

        # No fields are required — all have defaults (history_file, max_stall, epsilon).
        assert EVALUATOR_REQUIRED_FIELDS["open_question_stall"] == []


class TestOpenQuestionStallValidation:
    """open_question_stall-specific validation in fsm/validation.py (ENH-2446)."""

    def test_max_stall_must_be_positive(self) -> None:
        from little_loops.fsm.schema import EvaluateConfig
        from little_loops.fsm.validation import _validate_evaluator

        evaluate = EvaluateConfig(type="open_question_stall", max_stall=0)
        errors = _validate_evaluator("test_state", evaluate)
        assert any("max_stall" in str(e) for e in errors)

    def test_epsilon_must_be_non_negative(self) -> None:
        from little_loops.fsm.schema import EvaluateConfig
        from little_loops.fsm.validation import _validate_evaluator

        evaluate = EvaluateConfig(type="open_question_stall", epsilon=-1.0)
        errors = _validate_evaluator("test_state", evaluate)
        assert any("epsilon" in str(e) for e in errors)
