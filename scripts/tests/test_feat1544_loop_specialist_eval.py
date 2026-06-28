"""Tests for loop-specialist-eval built-in loop (FEAT-1544).

Structural and per-state assertions follow the patterns from test_outer_loop_eval.py
and test_create_eval_from_issues.py. Optional behavioral class is gated by
@pytest.mark.skipif so CI stays green without a live claude CLI.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "loop-specialist-eval.yaml"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fsm"
BROKEN_LOOP_FIXTURE = FIXTURES_DIR / "broken-verify-loop.yaml"


@pytest.fixture
def loop_data() -> dict:
    """Load loop-specialist-eval.yaml."""
    assert LOOP_FILE.exists(), f"loop-specialist-eval.yaml not found at {LOOP_FILE}"
    with open(LOOP_FILE) as f:
        return yaml.safe_load(f)


class TestLoopSpecialistEvalFile:
    """Tests that loop-specialist-eval.yaml exists and is structurally valid."""

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists(), f"loop-specialist-eval.yaml not found at {LOOP_FILE}"

    def test_parses_as_yaml(self, loop_data: dict) -> None:
        assert isinstance(loop_data, dict), "root must be a mapping"

    def test_validates_as_fsm(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM validation errors: {[str(e) for e in error_list]}"

    def test_name(self, loop_data: dict) -> None:
        assert loop_data.get("name") == "loop-specialist-eval"

    def test_initial_state(self, loop_data: dict) -> None:
        assert loop_data.get("initial") == "execute"

    def test_category_is_evaluation(self, loop_data: dict) -> None:
        # Category changed from "harness" to "evaluation" in commit 90425f27
        # (loop-specialist-eval is an evaluation loop, not a generic harness).
        assert loop_data.get("category") == "evaluation"

    def test_description_is_non_empty(self, loop_data: dict) -> None:
        desc = loop_data.get("description", "")
        assert desc and len(str(desc).strip()) > 0, "description field must not be empty"

    def test_terminal_done_state(self, loop_data: dict) -> None:
        states = loop_data.get("states", {})
        assert "done" in states, "must have a 'done' terminal state"
        assert states["done"].get("terminal") is True, "'done' must be terminal"


class TestLoopSpecialistEvalStates:
    """Per-state assertions for loop-specialist-eval.yaml."""

    REQUIRED_STATES = {"execute", "check_skill", "done"}

    def test_has_all_required_states(self, loop_data: dict) -> None:
        actual = set(loop_data.get("states", {}).keys())
        missing = self.REQUIRED_STATES - actual
        assert not missing, f"Missing required states: {missing}"

    def test_execute_is_prompt_with_agent(self, loop_data: dict) -> None:
        state = loop_data["states"]["execute"]
        assert state.get("action_type") == "prompt"
        assert state.get("agent") == "loop-specialist"

    def test_execute_captures_output(self, loop_data: dict) -> None:
        state = loop_data["states"]["execute"]
        assert state.get("capture") is not None, "execute must capture its output"

    def test_execute_routes_to_check_skill(self, loop_data: dict) -> None:
        state = loop_data["states"]["execute"]
        assert state.get("next") == "check_skill"

    def test_check_skill_has_llm_structured_evaluator(self, loop_data: dict) -> None:
        state = loop_data["states"]["check_skill"]
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "llm_structured"

    def test_check_skill_evaluator_has_prompt(self, loop_data: dict) -> None:
        state = loop_data["states"]["check_skill"]
        prompt = state.get("evaluate", {}).get("prompt", "")
        assert len(str(prompt).strip()) > 20, "llm_structured prompt must not be empty"

    def test_check_skill_routes_on_yes_to_done(self, loop_data: dict) -> None:
        state = loop_data["states"]["check_skill"]
        assert state.get("on_yes") == "done"

    def test_check_skill_routes_on_no_to_execute(self, loop_data: dict) -> None:
        state = loop_data["states"]["check_skill"]
        assert state.get("on_no") == "execute"


class TestBrokenVerifyFixture:
    """Tests for the seeded broken-verify-loop.yaml fixture.

    Mirrors TestAssessLoopSkill pattern (test_audit_loop_run_skill.py) to isolate
    the fixture's semantic intent: a verify state that self-loops on on_no,
    exemplifying the ambiguous-output failure mode from agents/loop-specialist.md.
    """

    @pytest.fixture
    def fixture_data(self) -> dict:
        assert BROKEN_LOOP_FIXTURE.exists(), f"Fixture not found: {BROKEN_LOOP_FIXTURE}"
        with open(BROKEN_LOOP_FIXTURE) as f:
            return yaml.safe_load(f)

    def test_fixture_file_exists(self) -> None:
        assert BROKEN_LOOP_FIXTURE.exists(), f"Fixture not found: {BROKEN_LOOP_FIXTURE}"

    def test_fixture_parses_as_yaml(self, fixture_data: dict) -> None:
        assert isinstance(fixture_data, dict), "fixture root must be a mapping"

    def test_fixture_validates_as_fsm(self) -> None:
        fsm, _ = load_and_validate(BROKEN_LOOP_FIXTURE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"Fixture FSM errors: {[str(e) for e in error_list]}"

    def test_fixture_has_verify_state(self, fixture_data: dict) -> None:
        assert "verify" in fixture_data.get("states", {}), "fixture must have a 'verify' state"

    def test_verify_state_self_loops_on_no(self, fixture_data: dict) -> None:
        """The pathology: on_no routes back to verify (infinite self-loop, no escape)."""
        verify = fixture_data["states"]["verify"]
        assert verify.get("on_no") == "verify", (
            "verify.on_no must be 'verify' — the ambiguous-output self-loop pathology"
        )

    def test_verify_state_has_llm_structured_evaluator(self, fixture_data: dict) -> None:
        verify = fixture_data["states"]["verify"]
        evaluate = verify.get("evaluate", {})
        assert evaluate.get("type") == "llm_structured", (
            "verify state must use llm_structured evaluator"
        )

    def test_verify_state_has_escape_on_yes(self, fixture_data: dict) -> None:
        """on_yes must lead somewhere other than verify (otherwise there is no exit at all)."""
        verify = fixture_data["states"]["verify"]
        assert verify.get("on_yes") is not None, "verify must have on_yes route"
        assert verify.get("on_yes") != "verify", "on_yes must not be a self-loop"

    def test_fixture_has_terminal_done(self, fixture_data: dict) -> None:
        states = fixture_data.get("states", {})
        assert "done" in states
        assert states["done"].get("terminal") is True


class TestLoopSpecialistPIDCorruptionMode:
    """Tests that agents/loop-specialist.md includes over-escaped-shell-pid-corruption
    in its failure-mode taxonomy and diagnosis artifact checklist (ENH-2367).
    """

    AGENT_FILE = Path(__file__).parent.parent.parent / "agents" / "loop-specialist.md"

    def test_agent_file_exists(self) -> None:
        assert self.AGENT_FILE.exists(), "agents/loop-specialist.md not found"

    def test_failure_mode_taxonomy_has_pid_corruption(self) -> None:
        """Failure-mode taxonomy table must include over-escaped-shell-pid-corruption."""
        content = self.AGENT_FILE.read_text()
        assert "over-escaped-shell-pid-corruption" in content, (
            "agents/loop-specialist.md must include over-escaped-shell-pid-corruption in taxonomy"
        )

    def test_diagnosis_checklist_has_pid_corruption(self) -> None:
        """Diagnosis artifact checklist must include over-escaped-shell-pid-corruption."""
        content = self.AGENT_FILE.read_text()
        assert "- [ ] over-escaped-shell-pid-corruption" in content, (
            "Diagnosis artifact checklist must include '- [ ] over-escaped-shell-pid-corruption'"
        )

    def test_pid_corruption_mode_mentions_mr9(self) -> None:
        """over-escaped-shell-pid-corruption mode description must reference MR-9."""
        content = self.AGENT_FILE.read_text()
        assert "MR-9" in content, (
            "over-escaped-shell-pid-corruption must reference MR-9 validation rule"
        )

    def test_pid_corruption_mode_recommends_single_dollar(self) -> None:
        """over-escaped-shell-pid-corruption fix must recommend removing the extra $."""
        content = self.AGENT_FILE.read_text()
        idx = content.find("over-escaped-shell-pid-corruption")
        assert idx != -1, "Mode must be present in agent file"
        surrounding = content[idx : idx + 500]
        assert "single" in surrounding or "remove" in surrounding or "Remove" in surrounding, (
            "Fix description must recommend removing the extra $ (single $ form)"
        )


@pytest.mark.skipif(
    shutil.which("claude") is None,
    reason="live LLM required; skip in CI unless claude CLI is available",
)
@pytest.mark.slow
class TestLoopSpecialistEvalBehavioral:
    """Optional behavioral round-trip test requiring a live claude CLI.

    Validates that the loop-specialist-eval.yaml still passes FSM validation
    in the live environment. Full end-to-end invocation via ll-loop run is
    intentionally left as a manual step due to non-deterministic LLM output.
    """

    def test_eval_file_survives_live_validation(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM errors in live env: {[str(e) for e in error_list]}"
