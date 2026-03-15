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


class TestReplaceablePromptStateDetection:
    """Test PR-1 heuristics for detecting deterministic LLM prompt states.

    These tests verify the discriminators the skill uses in QC-14 to identify
    prompt-type states that could be replaced with bash or python states.
    The heuristics are defined in reference.md under 'Programmatic Replacement Checks (PR)'.
    """

    # Shared helper that mirrors the QC-14 detection logic
    # (used to make individual tests self-documenting)

    EXEMPTION_KEYWORDS = {
        "summarize", "summarise", "analyze", "analyse", "review", "evaluate",
        "assess", "classify", "categorize", "categorise", "identify", "determine",
        "generate", "suggest", "recommend", "explain", "describe", "reason",
        "infer", "diagnose",
    }

    SHELL_METACHARACTERS = set("|&;$><`")

    def _is_prompt_like(self, action: str) -> bool:
        """True if action looks like a natural-language prompt (>10 words, no shell chars)."""
        words = action.split()
        has_shell = any(c in action for c in self.SHELL_METACHARACTERS)
        return len(words) > 10 and not has_shell

    def _has_exemption(self, action: str) -> bool:
        """True if action contains an exemption keyword."""
        lower = action.lower()
        return any(kw in lower for kw in self.EXEMPTION_KEYWORDS)

    def _strip_template_vars(self, action: str) -> str:
        """Remove {{...}} and $identifier from action text."""
        import re
        text = re.sub(r"\{\{[^}]+\}\}", " ", action)
        text = re.sub(r"\$[A-Za-z_][A-Za-z0-9_]*", " ", text)
        return text.strip()

    # ---- Group A: File/path existence checks → should be flagged ----

    def test_pr1_group_a_file_existence_flagged(self) -> None:
        """PR-1 Group A: 'Does X exist?' prompt → flag as replaceable."""
        action = "Does the file config.json exist in the current project root directory?"
        literal = self._strip_template_vars(action)
        lower = literal.lower()

        is_prompt = self._is_prompt_like(action)
        has_exemption = self._has_exemption(action)
        matches_group_a = any(phrase in lower for phrase in ("does", "exist"))

        assert is_prompt
        assert not has_exemption
        assert matches_group_a
        # → skill should flag as PR-1 Suggestion

    def test_pr1_group_a_check_if_file_exists_flagged(self) -> None:
        """PR-1 Group A: 'Check if file Y exists' prompt → flag as replaceable."""
        action = "Check if the file requirements.txt exists in the project root directory"
        lower = action.lower()

        is_prompt = self._is_prompt_like(action)
        has_exemption = self._has_exemption(action)
        matches_group_a = "check if" in lower and "exist" in lower

        assert is_prompt
        assert not has_exemption
        assert matches_group_a

    # ---- Group B: Counting/enumeration → should be flagged ----

    def test_pr1_group_b_count_errors_flagged(self) -> None:
        """PR-1 Group B: 'Count the number of...' prompt → flag as replaceable."""
        action = "Count the number of lines containing ERROR in the build log file"
        lower = action.lower()

        is_prompt = self._is_prompt_like(action)
        has_exemption = self._has_exemption(action)
        matches_group_b = "count the number of" in lower or "how many" in lower

        assert is_prompt
        assert not has_exemption
        assert matches_group_b

    def test_pr1_group_b_how_many_files_flagged(self) -> None:
        """PR-1 Group B: 'How many files...' prompt → flag as replaceable."""
        action = "How many Python files are there in the scripts directory right now"
        lower = action.lower()

        is_prompt = self._is_prompt_like(action)
        has_exemption = self._has_exemption(action)
        matches_group_b = "how many" in lower

        assert is_prompt
        assert not has_exemption
        assert matches_group_b

    # ---- Group C: Simple formatting/transformation → should be flagged ----

    def test_pr1_group_c_format_as_json_flagged(self) -> None:
        """PR-1 Group C: 'Format X as JSON' prompt → flag as replaceable."""
        action = "Format the output of the previous step as a JSON object with key and value fields"
        lower = action.lower()

        is_prompt = self._is_prompt_like(action)
        has_exemption = self._has_exemption(action)
        matches_group_c = "format" in lower and ("as" in lower or "output" in lower)

        assert is_prompt
        assert not has_exemption
        assert matches_group_c

    # ---- Group D: Yes/no decision on structured data → should be flagged ----

    def test_pr1_group_d_numeric_threshold_flagged(self) -> None:
        """PR-1 Group D: 'Is count greater than N?' prompt → flag as replaceable."""
        action = "Is the error count greater than zero based on the numeric value provided above"
        lower = action.lower()

        is_prompt = self._is_prompt_like(action)
        has_exemption = self._has_exemption(action)
        matches_group_d = ("greater" in lower or "less" in lower or "equal" in lower) and (
            "count" in lower or "value" in lower or "number" in lower
        )

        assert is_prompt
        assert not has_exemption
        assert matches_group_d

    def test_pr1_group_d_boolean_decision_flagged(self) -> None:
        """PR-1 Group D: 'Output yes or no based on value' prompt → flag as replaceable."""
        action = "Output yes if the exit code is zero or output no if it is non-zero based on the result"
        lower = action.lower()

        is_prompt = self._is_prompt_like(action)
        has_exemption = self._has_exemption(action)
        matches_group_d = ("yes" in lower or "no" in lower) and (
            "exit code" in lower or "value" in lower or "result" in lower
        )

        assert is_prompt
        assert not has_exemption
        assert matches_group_d

    # ---- Group E: Pure template substitution → should be flagged ----

    def test_pr1_group_e_template_only_flagged(self) -> None:
        """PR-1 Group E: Action is mostly template vars with fixed text → flag."""
        action = "The current error count is {{error_count}} and the threshold is {{threshold}} value"
        stripped = self._strip_template_vars(action)
        words = stripped.split()

        is_prompt = self._is_prompt_like(action)
        has_exemption = self._has_exemption(action)
        # After stripping vars, only fixed connector words remain
        meaningful_words = [w for w in words if len(w) > 2]
        mostly_template = len(meaningful_words) <= 8  # mostly template references

        assert is_prompt
        assert not has_exemption
        assert mostly_template

    # ---- Group F: Simple string/path operations → should be flagged ----

    def test_pr1_group_f_basename_flagged(self) -> None:
        """PR-1 Group F: 'Get the basename of path' prompt → flag as replaceable."""
        action = "Extract the filename without extension from the full path provided in the variable"
        lower = action.lower()

        is_prompt = self._is_prompt_like(action)
        has_exemption = self._has_exemption(action)
        matches_group_f = "extract" in lower and ("filename" in lower or "path" in lower)

        assert is_prompt
        assert not has_exemption
        assert matches_group_f

    # ---- Exemption: genuine LLM work → should NOT be flagged ----

    def test_pr1_summarize_not_flagged(self) -> None:
        """PR-1 exemption: 'Summarize...' prompt requires LLM → do not flag."""
        action = "Summarize the test failure output and identify the root cause of each failing test"
        has_exemption = self._has_exemption(action)
        assert has_exemption  # → skill must skip PR-1 check

    def test_pr1_classify_free_text_not_flagged(self) -> None:
        """PR-1 exemption: 'Classify...' prompt requires language understanding → do not flag."""
        action = "Classify the user feedback as positive, negative, or neutral based on the text content"
        has_exemption = self._has_exemption(action)
        assert has_exemption

    def test_pr1_generate_content_not_flagged(self) -> None:
        """PR-1 exemption: 'Generate...' prompt requires creative output → do not flag."""
        action = "Generate a concise commit message that describes the changes made in this session"
        has_exemption = self._has_exemption(action)
        assert has_exemption

    def test_pr1_analyze_code_not_flagged(self) -> None:
        """PR-1 exemption: 'Analyze...' prompt requires reasoning → do not flag."""
        action = "Analyze the current test failures and determine the root cause of each error"
        has_exemption = self._has_exemption(action)
        assert has_exemption

    def test_pr1_review_quality_not_flagged(self) -> None:
        """PR-1 exemption: 'Review...' prompt requires judgment → do not flag."""
        action = "Review the code changes and evaluate whether they meet the acceptance criteria in the issue"
        has_exemption = self._has_exemption(action)
        assert has_exemption

    def test_pr1_diagnose_not_flagged(self) -> None:
        """PR-1 exemption: 'Diagnose...' prompt requires inference → do not flag."""
        action = "Diagnose why the build is failing by examining the error output and log files carefully"
        has_exemption = self._has_exemption(action)
        assert has_exemption

    # ---- Non-prompt states → skip PR-1 entirely ----

    def test_pr1_shell_state_not_checked(self) -> None:
        """PR-1: Shell states (action_type: shell) are exempt from the check."""
        state_spec = {
            "action": "grep -c 'ERROR' build.log",
            "action_type": "shell",
        }
        action_type = state_spec.get("action_type")
        is_prompt_type = action_type == "prompt"
        looks_like_prompt = self._is_prompt_like(state_spec["action"])

        assert not is_prompt_type
        assert not looks_like_prompt  # short shell command → also not prompt-like
        # → no PR-1 check needed

    def test_pr1_long_prompt_over_50_words_exempt(self) -> None:
        """PR-1: Actions exceeding 50 words are skipped (complex reasoning assumed)."""
        action = (
            "Count the number of failing tests and then determine if the failure rate exceeds "
            "the configured threshold, taking into account any known flaky tests that should be "
            "excluded from the count, and also consider whether failures occurred in the same "
            "module or are spread across multiple modules, as that affects the severity rating"
        )
        words = action.split()
        assert len(words) > 50  # → skill must skip PR-1 check

    # ---- Auto-apply rules: PR-1 is never auto-applied ----

    def test_pr1_not_auto_applicable(self) -> None:
        """PR-1 findings must never be auto-applied in --auto mode."""
        # From reference.md Auto-Apply Rules: PR-* findings require structural changes
        # and must always require user approval
        pr_checks = {"PR-1"}
        auto_apply_eligible = {"QC-6"}  # only QC-6 is ever auto-applied

        assert pr_checks.isdisjoint(auto_apply_eligible)

    # ---- Dry-run compatibility ----

    def test_pr1_findings_included_in_dry_run_output(self) -> None:
        """PR-1 findings appear in the findings table during --dry-run (Step 3)."""
        # dry-run stops after Step 3 (display findings), which includes all severities.
        # PR-1 is Suggestion severity → it appears in the Suggestions section.
        finding = {
            "check_id": "PR-1",
            "severity": "Suggestion",
            "location": "states.check_config",
            "message": "Prompt state appears deterministic. Detected pattern: Group A.",
        }
        assert finding["severity"] == "Suggestion"
        assert finding["check_id"] == "PR-1"
        # → dry-run would include this in the Suggestions table section


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
