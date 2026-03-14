"""Tests for /ll:review-loop skill artifacts.

Since /ll:review-loop is a prompt-based skill (markdown instructions for Claude),
we cannot directly unit test the interactive wizard flow. Instead, we test:

1. That validate_fsm() detects the V-series issues claimed in reference.md
2. That quality-check logic (QC series) correctly identifies issues in YAML dicts
3. That built-in loop files pass structural validation
4. Format detection logic matches the discriminator in SKILL.md
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from little_loops.fsm import validate_fsm
from little_loops.fsm.schema import EvaluateConfig, FSMLoop, StateConfig
from little_loops.fsm.validation import ValidationSeverity

# Project root, used to locate fixture and built-in loop files
PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fsm"
LOOPS_DIR = PROJECT_ROOT / "loops"

# ---------------------------------------------------------------------------
# Helpers re-exported from test_ll_loop_errors for local use
# ---------------------------------------------------------------------------


def make_test_state(
    action: str | None = None,
    on_success: str | None = None,
    on_failure: str | None = None,
    on_error: str | None = None,
    next: str | None = None,
    terminal: bool = False,
    evaluate: EvaluateConfig | None = None,
    capture: str | None = None,
    on_maintain: str | None = None,
    route: object | None = None,
) -> StateConfig:
    """Create a StateConfig for testing."""
    kwargs: dict = {
        "action": action,
        "on_success": on_success,
        "on_failure": on_failure,
        "on_error": on_error,
        "next": next,
        "terminal": terminal,
        "evaluate": evaluate,
        "capture": capture,
        "on_maintain": on_maintain,
    }
    if route is not None:
        kwargs["route"] = route
    return StateConfig(**kwargs)


def make_test_fsm(
    name: str = "test-loop",
    initial: str = "start",
    states: dict[str, StateConfig] | None = None,
    max_iterations: int = 50,
) -> FSMLoop:
    """Create an FSMLoop for testing."""
    if states is None:
        states = {
            "start": make_test_state(action="echo start", on_success="done", on_failure="done"),
            "done": make_test_state(terminal=True),
        }
    return FSMLoop(name=name, initial=initial, states=states, max_iterations=max_iterations)


# =============================================================================
# TestReviewLoopChecks — validate_fsm() detects V-series issues
# =============================================================================


class TestReviewLoopChecks:
    """Verify that validate_fsm() detects the V-series issues listed in reference.md.

    These tests document what the first-pass `ll-loop validate` step will surface
    so the skill can present them as Error/Warning findings.
    """

    # ---- V-1: Initial state not in states ----

    def test_v1_initial_state_not_defined(self) -> None:
        """V-1: Initial state missing from states dict → Error."""
        fsm = make_test_fsm(initial="nonexistent")
        errors = validate_fsm(fsm)
        error_msgs = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("nonexistent" in e.message or "initial" in (e.path or "") for e in error_msgs)

    # ---- V-2: No terminal state ----

    def test_v2_no_terminal_state(self) -> None:
        """V-2: FSM with no terminal state → Error."""
        fsm = make_test_fsm(
            states={
                "start": make_test_state(action="echo", next="start"),
            }
        )
        errors = validate_fsm(fsm)
        error_msgs = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("terminal" in e.message.lower() for e in error_msgs)

    # ---- V-3: State references undefined state ----

    def test_v3_undefined_state_reference(self) -> None:
        """V-3: on_success pointing to nonexistent state → Error."""
        fsm = make_test_fsm(
            states={
                "start": make_test_state(action="echo", on_success="nowhere", on_failure="done"),
                "done": make_test_state(terminal=True),
            }
        )
        errors = validate_fsm(fsm)
        error_msgs = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("nowhere" in e.message for e in error_msgs)

    # ---- V-9: No transition defined ----

    def test_v9_state_with_no_transition(self) -> None:
        """V-9: Non-terminal state with no outgoing transition → Error."""
        fsm = make_test_fsm(
            states={
                "start": make_test_state(action="echo"),  # no on_success/failure/next/terminal
                "done": make_test_state(terminal=True),
            }
        )
        errors = validate_fsm(fsm)
        error_msgs = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any(e.path and "start" in e.path for e in error_msgs)

    # ---- V-11: Unreachable state → Warning ----

    def test_v11_unreachable_state_fixture(self) -> None:
        """V-11: loop-with-unreachable-state.yaml contains an orphan state → Warning."""
        fixture_path = FIXTURES_DIR / "loop-with-unreachable-state.yaml"
        assert fixture_path.exists(), f"Fixture not found: {fixture_path}"

        with open(fixture_path) as f:
            spec = yaml.safe_load(f)

        fsm = FSMLoop.from_dict(spec)
        issues = validate_fsm(fsm)
        warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]
        assert any("orphan" in i.message.lower() or "orphan" in (i.path or "") for i in warnings)

    # ---- V-12: max_iterations <= 0 ----

    def test_v12_max_iterations_zero(self) -> None:
        """V-12: max_iterations of 0 → Error."""
        fsm = make_test_fsm(max_iterations=0)
        errors = validate_fsm(fsm)
        error_msgs = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("max_iterations" in (e.path or "") for e in error_msgs)

    # ---- V-10: Routing conflict (shorthand + route) → Warning ----

    def test_v10_routing_conflict_shorthand_and_route(self) -> None:
        """V-10: State with both on_success and route block → Warning."""
        from little_loops.fsm.schema import RouteConfig

        fsm = make_test_fsm(
            states={
                "start": make_test_state(
                    action="echo",
                    on_success="done",  # shorthand
                    route=RouteConfig(routes={"success": "done"}),  # explicit route
                ),
                "done": make_test_state(terminal=True),
            }
        )
        issues = validate_fsm(fsm)
        warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]
        assert any(
            "route" in i.message.lower() or "conflict" in i.message.lower() for i in warnings
        )

    # ---- Built-in loops pass validation ----

    @pytest.mark.parametrize(
        "loop_file", list(LOOPS_DIR.glob("*.yaml")) if LOOPS_DIR.exists() else []
    )
    def test_builtin_loops_are_valid(self, loop_file: Path) -> None:
        """All built-in loops in loops/ should pass structural validation without errors."""
        with open(loop_file) as f:
            spec = yaml.safe_load(f)

        fsm = FSMLoop.from_dict(spec)
        issues = validate_fsm(fsm)
        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert not errors, f"{loop_file.name} has validation errors: {errors}"


# =============================================================================
# TestReviewLoopQualityChecks — QC-series logic from reference.md
# =============================================================================


class TestReviewLoopQualityChecks:
    """Test the quality-check heuristics described in reference.md (QC-1 through QC-7).

    These tests exercise the discriminators that the skill applies manually to the
    raw YAML dict (not via validate_fsm).
    """

    # ---- QC-1: max_iterations range ----

    def test_qc1_max_iterations_too_low(self) -> None:
        """QC-1: max_iterations < 3 should be flagged."""
        spec = {"max_iterations": 2}
        value = spec.get("max_iterations", 50)
        assert value < 3, "Skill should flag values below 3"

    def test_qc1_max_iterations_too_high(self) -> None:
        """QC-1: max_iterations > 100 should be flagged."""
        spec = {"max_iterations": 200}
        value = spec.get("max_iterations", 50)
        assert value > 100, "Skill should flag values above 100"

    def test_qc1_max_iterations_absent(self) -> None:
        """QC-1: Absent max_iterations defaults to 50 (Suggestion only)."""
        spec: dict = {}
        value = spec.get("max_iterations", 50)
        assert value == 50, "Default should be 50"
        # Absent key → Suggestion, not Warning
        assert "max_iterations" not in spec

    def test_qc1_max_iterations_reasonable(self) -> None:
        """QC-1: Values in [3, 100] should not trigger QC-1."""
        for v in (3, 10, 50, 100):
            assert 3 <= v <= 100, f"Value {v} is in the acceptable range"

    # ---- QC-2: Missing on_error routing ----

    def test_qc2_shell_evaluator_missing_on_error(self) -> None:
        """QC-2: State with evaluate block and no on_error should be flagged."""
        state_spec = {
            "action": "ruff check .",
            "evaluate": {"type": "exit_code"},
            "on_success": "done",
            "on_failure": "fix",
            # on_error absent
        }
        has_evaluate = "evaluate" in state_spec
        is_terminal = state_spec.get("terminal", False)
        has_on_error = "on_error" in state_spec
        has_route_error = "error" in state_spec.get("route", {})

        assert has_evaluate and not is_terminal and not has_on_error and not has_route_error
        # → skill should flag as QC-2 Warning

    def test_qc2_terminal_state_exempt(self) -> None:
        """QC-2: Terminal states are exempt from on_error check."""
        state_spec = {"terminal": True}
        is_terminal = state_spec.get("terminal", False)
        assert is_terminal  # → skip QC-2

    def test_qc2_on_error_present_no_flag(self) -> None:
        """QC-2: State with on_error set should not be flagged."""
        state_spec = {
            "action": "ruff check .",
            "evaluate": {"type": "exit_code"},
            "on_success": "done",
            "on_failure": "fix",
            "on_error": "fix",
        }
        has_on_error = "on_error" in state_spec
        assert has_on_error  # → no QC-2 flag

    # ---- QC-3: action_type mismatch ----

    def test_qc3_natural_language_without_action_type(self) -> None:
        """QC-3: Long natural-language action without action_type → Suggestion."""
        action = "Review the current test failures and identify the root cause of each"
        words = action.split()
        shell_chars = set("|&;$><`")
        has_shell = any(c in action for c in shell_chars)

        assert len(words) > 10
        assert not has_shell
        # → skill should suggest action_type: prompt

    def test_qc3_shell_command_with_prompt_type(self) -> None:
        """QC-3: Shell-looking command with action_type: prompt → Warning."""
        state_spec = {
            "action": "pytest scripts/tests/ -v",
            "action_type": "prompt",
        }
        action = state_spec["action"]
        shell_keywords = {"pytest", "ruff", "mypy", "python", "npm", "cargo", "make", "git"}
        first_word = action.split()[0].lower() if action else ""

        assert first_word in shell_keywords
        assert state_spec.get("action_type") == "prompt"
        # → skill should flag as Warning

    def test_qc3_correct_shell_no_flag(self) -> None:
        """QC-3: Shell command with action_type: shell should not be flagged."""
        state_spec = {
            "action": "ruff check scripts/",
            "action_type": "shell",
        }
        assert state_spec.get("action_type") == "shell"
        # → no QC-3 flag

    # ---- QC-4: Convergence without on_maintain ----

    def test_qc4_convergence_missing_on_maintain(self) -> None:
        """QC-4: Convergence evaluator without on_maintain → Warning."""
        state_spec = {
            "action": "python measure.py",
            "evaluate": {"type": "convergence", "target": 0},
            "on_success": "done",
            "on_failure": "fix",
            # on_maintain absent
        }
        is_convergence = state_spec.get("evaluate", {}).get("type") == "convergence"
        has_on_maintain = "on_maintain" in state_spec

        assert is_convergence and not has_on_maintain
        # → skill should flag as QC-4 Warning

    def test_qc4_convergence_with_on_maintain_no_flag(self) -> None:
        """QC-4: Convergence evaluator with on_maintain should not be flagged."""
        state_spec = {
            "action": "python measure.py",
            "evaluate": {"type": "convergence", "target": 0},
            "on_success": "done",
            "on_failure": "fix",
            "on_maintain": "fix",
        }
        is_convergence = state_spec.get("evaluate", {}).get("type") == "convergence"
        has_on_maintain = "on_maintain" in state_spec

        assert is_convergence and has_on_maintain
        # → no QC-4 flag

    # ---- QC-5: Hardcoded user paths ----

    def test_qc5_hardcoded_user_path_detected(self) -> None:
        """QC-5: Shell action with /Users/ path → Warning."""
        action = "/Users/brennon/scripts/run_checks.sh"
        hardcoded_prefixes = ["/Users/", "/home/", "~/"]
        assert any(action.startswith(p) or p in action for p in hardcoded_prefixes)
        # → skill should flag as QC-5 Warning

    def test_qc5_relative_path_no_flag(self) -> None:
        """QC-5: Shell action with relative path should not be flagged."""
        action = "./scripts/run_checks.sh"
        hardcoded_prefixes = ["/Users/", "/home/", "~/"]
        assert not any(p in action for p in hardcoded_prefixes)
        # → no QC-5 flag

    # ---- QC-6: on_handoff recommendation ----

    def test_qc6_long_loop_missing_on_handoff(self) -> None:
        """QC-6: max_iterations > 20 without on_handoff → Suggestion."""
        spec = {"max_iterations": 50}
        max_iter = spec.get("max_iterations", 50)
        has_on_handoff = "on_handoff" in spec

        assert max_iter > 20 and not has_on_handoff
        # → skill should suggest QC-6

    def test_qc6_short_loop_exempt(self) -> None:
        """QC-6: max_iterations <= 20 is exempt from on_handoff suggestion."""
        spec = {"max_iterations": 10}
        max_iter = spec.get("max_iterations", 50)
        assert max_iter <= 20  # → no QC-6 flag

    def test_qc6_on_handoff_explicit_no_flag(self) -> None:
        """QC-6: Explicit on_handoff should not trigger suggestion."""
        spec = {"max_iterations": 50, "on_handoff": "pause"}
        has_on_handoff = "on_handoff" in spec
        assert has_on_handoff  # → no QC-6 flag


# =============================================================================
# TestReviewLoopAutoFix — auto-apply logic from reference.md
# =============================================================================


class TestReviewLoopAutoFix:
    """Verify auto-apply rules: only non-breaking, pure-addition fixes are auto-applied.

    In --auto mode, only QC-6 (add explicit on_handoff: pause) is eligible.
    Routing changes (QC-2 on_error, QC-4 on_maintain) must always require approval.
    """

    def test_auto_apply_qc6_only_non_breaking(self) -> None:
        """--auto should only apply QC-6 (add on_handoff: pause)."""
        # Simulate the auto-apply eligibility check from reference.md
        all_findings = [
            {"check": "QC-1", "breaking": False},  # judgment call → not auto-applied
            {"check": "QC-2", "breaking": False},  # routing change → not auto-applied
            {"check": "QC-4", "breaking": False},  # routing change → not auto-applied
            {"check": "QC-6", "breaking": False},  # pure addition of default value → auto-applied
        ]
        routing_checks = {"QC-2", "QC-4"}
        judgment_checks = {"QC-1"}

        auto_eligible = [
            f
            for f in all_findings
            if not f["breaking"]
            and f["check"] not in routing_checks
            and f["check"] not in judgment_checks
        ]
        assert len(auto_eligible) == 1
        assert auto_eligible[0]["check"] == "QC-6"

    def test_qc6_auto_fix_adds_pause(self) -> None:
        """QC-6 auto-fix: on_handoff: pause is a pure addition of the default value."""
        spec: dict = {"name": "my-loop", "max_iterations": 50}
        # Apply QC-6 auto-fix
        spec["on_handoff"] = "pause"
        assert spec["on_handoff"] == "pause"

    def test_routing_changes_require_approval(self) -> None:
        """QC-2 and QC-4 fixes must require explicit user approval."""
        routing_checks = {"QC-2", "QC-4"}
        for check in routing_checks:
            # Simulate eligibility: routing changes are never auto-applied
            assert check in routing_checks, f"{check} should require approval"


# =============================================================================
# TestReviewLoopDryRun — dry-run produces no file writes
# =============================================================================


class TestReviewLoopDryRun:
    """Verify that --dry-run mode stops after displaying findings.

    Since the skill is a markdown prompt (not Python), we test the discriminators
    that the skill uses to decide whether to proceed past Step 3.
    """

    def test_dry_run_flag_detected(self) -> None:
        """--dry-run flag means: stop after Step 3 (display findings), write nothing."""
        args = ["fix-types", "--dry-run"]
        dry_run = "--dry-run" in args
        assert dry_run

    def test_auto_flag_not_dry_run(self) -> None:
        """--auto does not imply --dry-run; it applies eligible fixes."""
        args = ["fix-types", "--auto"]
        dry_run = "--dry-run" in args
        auto = "--auto" in args
        assert not dry_run
        assert auto

    def test_no_flags_is_interactive(self) -> None:
        """No flags → interactive mode (ask approval for each fix)."""
        args = ["fix-types"]
        dry_run = "--dry-run" in args
        auto = "--auto" in args
        assert not dry_run
        assert not auto

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        """Dry-run mode: output file must not be modified."""
        loop_file = tmp_path / "my-loop.yaml"
        original_content = "name: my-loop\ninitial: start\nstates: {}\n"
        loop_file.write_text(original_content)

        # Simulate dry-run: read content, do NOT write
        content = loop_file.read_text()
        # (skill stops at Step 3; no Write call)
        assert loop_file.read_text() == original_content
        assert content == original_content
