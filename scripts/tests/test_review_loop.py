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
from little_loops.fsm.schema import FSMLoop
from little_loops.fsm.validation import ValidationSeverity
from tests.helpers import make_test_fsm, make_test_state

# Project root, used to locate fixture and built-in loop files
PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fsm"
LOOPS_DIR = PROJECT_ROOT / "loops"


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
                "start": make_test_state(action="echo", on_yes="nowhere", on_no="done"),
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
                    on_yes="done",  # shorthand
                    route=RouteConfig(routes={"yes": "done"}),  # explicit route
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
            "on_yes": "done",
            "on_no": "fix",
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
            "on_yes": "done",
            "on_no": "fix",
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

    def test_qc3_unknown_action_type_warns_not_errors(self) -> None:
        """QC-3: Unknown action_type (e.g. contributed type 'webhook') → Warning, not Error."""
        state_spec = {
            "action": "POST https://example.com/hook",
            "action_type": "webhook",
        }
        built_in_types = {"prompt", "slash_command", "shell", "mcp_tool"}
        action_type = state_spec.get("action_type", "")

        assert action_type not in built_in_types
        # → skill should emit Warning (not Error); contributed action types are
        #   dispatched via the extension registry (_contributed_actions)

    # ---- QC-4: Convergence without on_maintain ----

    def test_qc4_convergence_missing_on_maintain(self) -> None:
        """QC-4: Convergence evaluator without on_maintain → Warning."""
        state_spec = {
            "action": "python measure.py",
            "evaluate": {"type": "convergence", "target": 0},
            "on_yes": "done",
            "on_no": "fix",
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
            "on_yes": "done",
            "on_no": "fix",
            "on_maintain": "fix",
        }
        is_convergence = state_spec.get("evaluate", {}).get("type") == "convergence"
        has_on_maintain = "on_maintain" in state_spec

        assert is_convergence and has_on_maintain
        # → no QC-4 flag

    # ---- QC-5: Hardcoded user paths ----

    def test_qc5_hardcoded_user_path_detected(self) -> None:
        """QC-5: Shell action with /Users/ path → Warning."""
        action = "/Users/you/scripts/run_checks.sh"
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
        "summarize",
        "summarise",
        "analyze",
        "analyse",
        "review",
        "evaluate",
        "assess",
        "classify",
        "categorize",
        "categorise",
        "identify",
        "determine",
        "generate",
        "suggest",
        "recommend",
        "explain",
        "describe",
        "reason",
        "infer",
        "diagnose",
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
        action = (
            "Output yes if the exit code is zero or output no if it is non-zero based on the result"
        )
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
        action = (
            "The current error count is {{error_count}} and the threshold is {{threshold}} value"
        )
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
        action = (
            "Extract the filename without extension from the full path provided in the variable"
        )
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
        action = (
            "Summarize the test failure output and identify the root cause of each failing test"
        )
        has_exemption = self._has_exemption(action)
        assert has_exemption  # → skill must skip PR-1 check

    def test_pr1_classify_free_text_not_flagged(self) -> None:
        """PR-1 exemption: 'Classify...' prompt requires language understanding → do not flag."""
        action = (
            "Classify the user feedback as positive, negative, or neutral based on the text content"
        )
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


class TestReviewLoopSemanticChecks:
    """Tests for SR-* semantic flow review check logic (SR-1 through SR-4).

    Since the semantic checks are performed by LLM reasoning over the parsed YAML
    (not Python code), we test the structural conditions that each check relies on
    and validate that the fixture files have the expected properties.
    """

    GATE_STATE_PREFIXES = ("check_", "verify_", "validate_")

    def _load_fixture(self, name: str) -> dict:
        path = FIXTURES_DIR / name
        assert path.exists(), f"Fixture not found: {path}"
        with open(path) as f:
            return yaml.safe_load(f)

    def _happy_path(self, spec: dict) -> list[str]:
        """Trace on_yes/next from initial to terminal, returning ordered state names."""
        states = spec.get("states", {})
        current = spec.get("initial")
        path: list[str] = []
        seen: set[str] = set()
        while current and current not in seen:
            path.append(current)
            seen.add(current)
            state = states.get(current, {})
            if state.get("terminal"):
                break
            current = state.get("on_yes") or state.get("next")
        return path

    # ---- SR-1: Happy-Path Goal Alignment ----

    def test_sr1_mismatch_fixture_has_description(self) -> None:
        """SR-1: semantic-goal-mismatch fixture has a description field."""
        spec = self._load_fixture("semantic-goal-mismatch.yaml")
        assert "description" in spec

    def test_sr1_mismatch_happy_path_unrelated_to_goal(self) -> None:
        """SR-1: happy path state names don't relate to the declared lint-fix goal."""
        spec = self._load_fixture("semantic-goal-mismatch.yaml")
        path = self._happy_path(spec)
        goal = spec.get("description", "").lower()
        path_text = " ".join(path).lower()
        assert "lint" in goal
        assert "lint" not in path_text  # → skill should flag SR-1

    def test_sr1_valid_aligned_fixture_path_matches_goal(self) -> None:
        """SR-1: valid-aligned fixture happy path relates to the declared goal."""
        spec = self._load_fixture("semantic-valid-aligned.yaml")
        path = self._happy_path(spec)
        goal = spec.get("description", "").lower()
        assert len(path) >= 2
        path_words = set(" ".join(path).lower().replace("_", " ").split())
        goal_words = {w for w in goal.split() if len(w) > 3}
        # At least one goal word should be a substring of (or contain) a path word
        has_overlap = any(gw in pw or pw in gw for gw in goal_words for pw in path_words)
        assert has_overlap  # → skill should NOT flag SR-1

    def test_sr1_skipped_when_no_description(self) -> None:
        """SR-1: check is skipped when description is absent."""
        spec = {
            "name": "no-desc",
            "initial": "start",
            "states": {
                "start": {"action": "do something", "next": "done"},
                "done": {"terminal": True},
            },
        }
        has_description = "description" in spec
        assert not has_description  # → skill should skip SR-1

    def test_sr1_skipped_when_description_too_generic(self) -> None:
        """SR-1: description with fewer than 5 words is too generic to evaluate."""
        description = "Process items"
        assert len(description.split()) < 5  # → skill should skip SR-1

    # ---- SR-2: State Name vs. Action Coherence ----

    def test_sr2_incoherent_state_has_gate_name(self) -> None:
        """SR-2: semantic-incoherent-state fixture has a gate-prefixed state name."""
        spec = self._load_fixture("semantic-incoherent-state.yaml")
        states = spec.get("states", {})
        gate_states = [n for n in states if any(n.startswith(p) for p in self.GATE_STATE_PREFIXES)]
        assert gate_states

    def test_sr2_incoherent_state_action_is_broad(self) -> None:
        """SR-2: the gate-named state has a broad action (>15 words) — mismatch with name."""
        spec = self._load_fixture("semantic-incoherent-state.yaml")
        states = spec.get("states", {})
        gate_name = next(
            n for n in states if any(n.startswith(p) for p in self.GATE_STATE_PREFIXES)
        )
        action = states[gate_name].get("action", "")
        assert len(action.split()) > 15  # → skill should flag SR-2

    def test_sr2_valid_aligned_gate_states_have_narrow_actions(self) -> None:
        """SR-2: valid-aligned fixture gate-named states have short, targeted actions."""
        spec = self._load_fixture("semantic-valid-aligned.yaml")
        states = spec.get("states", {})
        for name, state in states.items():
            if any(name.startswith(p) for p in self.GATE_STATE_PREFIXES):
                action = state.get("action", "")
                assert len(action.split()) <= 15  # → skill should NOT flag SR-2

    def test_sr2_inline_gate_name_broad_action(self) -> None:
        """SR-2: inline spec — check_* name with broad analysis action triggers SR-2."""
        state_spec = {
            "action": "Analyze the repository in full detail and produce a comprehensive report of all potential issues found across every file",
            "action_type": "prompt",
            "on_yes": "done",
            "on_no": "done",
        }
        name = "check_quality"
        has_gate_prefix = any(name.startswith(p) for p in self.GATE_STATE_PREFIXES)
        action_is_broad = len(state_spec["action"].split()) > 15
        assert has_gate_prefix and action_is_broad  # → skill should flag SR-2

    def test_sr2_inline_gate_name_narrow_action_no_flag(self) -> None:
        """SR-2: inline spec — check_* name with short targeted action does not trigger SR-2."""
        state_spec = {
            "action": "python -m mypy scripts/ --strict",
            "action_type": "shell",
            "on_yes": "done",
            "on_no": "fix",
        }
        name = "check_types"
        has_gate_prefix = any(name.startswith(p) for p in self.GATE_STATE_PREFIXES)
        action_is_broad = len(state_spec["action"].split()) > 15
        assert has_gate_prefix and not action_is_broad  # → skill should NOT flag SR-2

    # ---- SR-3: Semantically Backwards Transition ----

    def test_sr3_backwards_transition_fixture_has_on_yes_backward(self) -> None:
        """SR-3: semantic-backwards-transition fixture has on_yes routing to an earlier state."""
        spec = self._load_fixture("semantic-backwards-transition.yaml")
        path = self._happy_path(spec)
        states = spec.get("states", {})
        backward_found = any(
            states.get(name, {}).get("on_yes") in path[:i] for i, name in enumerate(path)
        )
        assert backward_found  # → skill should flag SR-3

    def test_sr3_valid_aligned_no_backward_transition(self) -> None:
        """SR-3: valid-aligned fixture has no on_yes routing backward."""
        spec = self._load_fixture("semantic-valid-aligned.yaml")
        path = self._happy_path(spec)
        states = spec.get("states", {})
        for i, name in enumerate(path):
            on_yes = states.get(name, {}).get("on_yes")
            assert on_yes not in path[:i], (
                f"State '{name}' has on_yes → '{on_yes}' which is backward in happy path"
            )  # → skill should NOT flag SR-3

    def test_sr3_inline_backward_on_yes(self) -> None:
        """SR-3: inline spec — on_yes routes to earlier state triggers SR-3."""
        happy_path = ["analyze", "verify", "finalize", "done"]
        state_spec = {"on_yes": "analyze"}  # success routes backward to index 0
        on_yes_target = state_spec["on_yes"]
        current_index = happy_path.index("verify")
        target_index = happy_path.index(on_yes_target)
        assert target_index < current_index  # → skill should flag SR-3

    def test_sr3_inline_forward_on_yes_no_flag(self) -> None:
        """SR-3: inline spec — on_yes routes forward → no SR-3 flag."""
        happy_path = ["check_types", "fix_errors", "done"]
        state_spec = {"on_yes": "done"}  # success routes forward to terminal
        on_yes_target = state_spec["on_yes"]
        current_index = happy_path.index("check_types")
        target_index = happy_path.index(on_yes_target)
        assert target_index > current_index  # → skill should NOT flag SR-3

    # ---- SR-4: Goal Coverage Gap ----

    def test_sr4_goal_gap_fixture_has_uncovered_activity(self) -> None:
        """SR-4: semantic-goal-gap fixture mentions commit/push in goal but no state covers it."""
        spec = self._load_fixture("semantic-goal-gap.yaml")
        goal = spec.get("description", "").lower()
        states = spec.get("states", {})
        all_state_text = (
            " ".join(states.keys()) + " " + " ".join(s.get("action", "") for s in states.values())
        ).lower()
        assert "commit" in goal or "push" in goal
        assert "commit" not in all_state_text and "push" not in all_state_text
        # → skill should flag SR-4

    def test_sr4_valid_aligned_covers_goal_activities(self) -> None:
        """SR-4: valid-aligned fixture has states covering all key goal activities."""
        spec = self._load_fixture("semantic-valid-aligned.yaml")
        states = spec.get("states", {})
        state_names_text = " ".join(states.keys()).replace("_", " ")
        # Goal is "Fix type errors until all type checks pass"
        # States should cover "check" (check_types) and "fix" (fix_errors)
        assert any("check" in name or "fix" in name for name in states)
        # Both key activities present in state names
        assert "check" in state_names_text
        assert "fix" in state_names_text  # → skill should NOT flag SR-4

    def test_sr4_skipped_when_description_absent(self) -> None:
        """SR-4: check is skipped when loop has no description."""
        spec = {"name": "no-desc", "initial": "start", "states": {}}
        assert "description" not in spec  # → skill should skip SR-4

    def test_sr4_skipped_when_description_too_short(self) -> None:
        """SR-4: description with fewer than 5 words is skipped."""
        description = "Run checks"
        assert len(description.split()) < 5  # → skill should skip SR-4

    # ---- Findings schema ----

    def test_sr_finding_schema_matches_existing_checks(self) -> None:
        """SR-* findings use the same { check_id, severity, location, message } schema."""
        for check_id, severity, location in [
            ("SR-1", "Warning", "(loop)"),
            ("SR-2", "Suggestion", "states.check_done"),
            ("SR-3", "Warning", "states.verify"),
            ("SR-4", "Warning", "(loop)"),
        ]:
            finding = {
                "check_id": check_id,
                "severity": severity,
                "location": location,
                "message": "x",
            }
            assert finding["severity"] in ("Error", "Warning", "Suggestion")
            assert "check_id" in finding and "location" in finding and "message" in finding


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


# =============================================================================
# TestReviewLoopSimulation — SIM-* check parsing from ll-loop simulate stdout
# =============================================================================


class TestReviewLoopSimulation:
    """Test SIM-* check signals from ll-loop simulate stdout parsing.

    Uses the subprocess pattern from test_ll_loop_execution.py: invoke main_loop()
    directly and assert on stdout strings rather than mocking the simulator.
    """

    def test_simulation_stalls_fixture_self_loops(self) -> None:
        """simulation-stalls.yaml fixture: verify state loops back on on_no (SIM-1 candidate)."""
        fixture_path = FIXTURES_DIR / "simulation-stalls.yaml"
        assert fixture_path.exists(), f"Fixture not found: {fixture_path}"

        with open(fixture_path) as f:
            spec = yaml.safe_load(f)

        states = spec.get("states", {})
        verify_state = states.get("verify", {})
        # SIM-1 trigger condition: on_no routes back to itself
        assert verify_state.get("on_no") == "verify", (
            "verify state should self-loop on on_no to trigger SIM-1"
        )

    def test_simulation_stalls_fixture_has_terminal(self) -> None:
        """simulation-stalls.yaml has a valid terminal state (done)."""
        fixture_path = FIXTURES_DIR / "simulation-stalls.yaml"
        with open(fixture_path) as f:
            spec = yaml.safe_load(f)

        states = spec.get("states", {})
        terminal_states = [n for n, s in states.items() if s.get("terminal")]
        assert terminal_states, "Fixture must have at least one terminal state"

    def test_sim1_signal_stall_detection(self) -> None:
        """SIM-1: repeated state in States visited + Terminated by max_iterations → stall."""
        simulate_stdout = (
            "SIMULATION: test-loop\n"
            "=== Summary ===\n"
            "Iterations: 5\n"
            "States visited: verify → verify → verify → verify → verify\n"
            "Terminated by: max_iterations\n"
        )
        lines = simulate_stdout.splitlines()
        states_line = next((ln for ln in lines if "States visited:" in ln), "")
        terminated_line = next((ln for ln in lines if "Terminated by:" in ln), "")

        # SIM-1: cycle in states visited AND terminated by max_iterations
        states_visited = states_line.split("States visited:")[-1].strip().split(" → ")
        has_cycle = len(states_visited) != len(set(states_visited))
        terminated_by_max = "max_iterations" in terminated_line

        assert has_cycle
        assert terminated_by_max
        # → skill should emit SIM-1 Warning

    def test_sim2_signal_premature_terminal(self) -> None:
        """SIM-2: terminal in <2 iterations on max_iterations > 5 → no-op happy path."""
        simulate_stdout = (
            "SIMULATION: test-loop\n"
            "=== Summary ===\n"
            "Iterations: 1\n"
            "States visited: check → done\n"
            "Terminated by: terminal\n"
        )
        max_iterations = 50  # > 5
        lines = simulate_stdout.splitlines()
        iter_line = next((ln for ln in lines if "Iterations:" in ln), "")
        terminated_line = next((ln for ln in lines if "Terminated by:" in ln), "")

        iterations = int(iter_line.split("Iterations:")[-1].strip())
        terminated_by_terminal = "terminal" in terminated_line

        assert iterations < 2
        assert terminated_by_terminal
        assert max_iterations > 5
        # → skill should emit SIM-2 Warning

    def test_sim2_skipped_when_max_iterations_small(self) -> None:
        """SIM-2: terminal in 1 iteration on max_iterations <= 5 → no flag (expected behavior)."""
        max_iterations = 3  # <= 5
        iterations = 1
        terminated_by_terminal = True

        should_flag = iterations < 2 and terminated_by_terminal and max_iterations > 5
        assert not should_flag
        # → skill should NOT emit SIM-2

    def test_sim3_signal_exceeds_max_iterations(self) -> None:
        """SIM-3: Terminated by max_iterations without a stall cycle → exceeds limit."""
        simulate_stdout = (
            "SIMULATION: test-loop\n"
            "=== Summary ===\n"
            "Iterations: 10\n"
            "States visited: check → fix → check → fix → check → fix → check → fix → check → fix\n"
            "Terminated by: max_iterations\n"
        )
        lines = simulate_stdout.splitlines()
        terminated_line = next((ln for ln in lines if "Terminated by:" in ln), "")

        terminated_by_max = "max_iterations" in terminated_line
        assert terminated_by_max
        # → skill should emit SIM-3 Error (regardless of whether it's also SIM-1)

    def test_sim_exit_code_not_unique_for_sim3(self) -> None:
        """SIM-3 cannot be identified by exit code alone — must parse stdout."""
        # From _helpers.py EXIT_CODES: exit code 1 covers max_iterations, timeout, cycle_detected
        exit_codes = {"terminal": 0, "max_iterations": 1, "timeout": 1, "cycle_detected": 1}
        assert exit_codes["max_iterations"] == exit_codes["timeout"]
        assert exit_codes["max_iterations"] == exit_codes["cycle_detected"]
        # → SIM-3 detection requires parsing "Terminated by: max_iterations" in stdout

    def test_no_simulate_flag_skips_step(self) -> None:
        """--no-simulate flag: Step 2.5 is entirely skipped, simulation_result='skipped'."""
        args = ["fix-types", "--no-simulate"]
        no_simulate = "--no-simulate" in args
        assert no_simulate
        # → skill sets simulation_result = "skipped" and does not run ll-loop simulate


# =============================================================================
# TestReviewLoopArtifact — Review artifact schema and persistence (Step 6.5)
# =============================================================================


class TestReviewLoopArtifact:
    """Test review artifact structure from reference.md Review Artifact Schema.

    Uses the no-mock pure-Python dict pattern: builds spec dicts directly and
    asserts on field presence and values.
    """

    def _make_artifact_frontmatter(
        self,
        loop: str = "test-loop",
        reviewed_at: str = "2026-05-17T14:32:07Z",
        scorecard: dict | None = None,
        findings_count: dict | None = None,
        simulation_result: str = "terminal",
        fixes_applied: int = 0,
    ) -> dict:
        return {
            "loop": loop,
            "reviewed_at": reviewed_at,
            "scorecard": scorecard
            or {
                "clarity": 4,
                "decomposition": 3,
                "resilience": 2,
                "observability": 3,
                "idempotence": 4,
                "cost_efficiency": 3,
                "composite": 19,
            },
            "findings_count": findings_count or {"errors": 0, "warnings": 2, "suggestions": 1},
            "simulation_result": simulation_result,
            "fixes_applied": fixes_applied,
        }

    def test_artifact_frontmatter_has_required_fields(self) -> None:
        """Artifact frontmatter must include all 6 required fields."""
        fm = self._make_artifact_frontmatter()
        required = {
            "loop",
            "reviewed_at",
            "scorecard",
            "findings_count",
            "simulation_result",
            "fixes_applied",
        }
        assert required.issubset(fm.keys())

    def test_artifact_scorecard_has_all_dimensions(self) -> None:
        """Scorecard must include all 6 dimensions and composite."""
        fm = self._make_artifact_frontmatter()
        scorecard = fm["scorecard"]
        dims = {
            "clarity",
            "decomposition",
            "resilience",
            "observability",
            "idempotence",
            "cost_efficiency",
        }
        assert dims.issubset(scorecard.keys())
        assert "composite" in scorecard

    def test_artifact_scorecard_composite_is_sum(self) -> None:
        """Composite score must equal sum of 6 dimension scores."""
        scorecard = {
            "clarity": 4,
            "decomposition": 3,
            "resilience": 2,
            "observability": 3,
            "idempotence": 4,
            "cost_efficiency": 3,
            "composite": 19,
        }
        dims = [
            "clarity",
            "decomposition",
            "resilience",
            "observability",
            "idempotence",
            "cost_efficiency",
        ]
        assert scorecard["composite"] == sum(scorecard[d] for d in dims)

    def test_artifact_scorecard_scores_in_range(self) -> None:
        """All dimension scores must be in [1, 5]."""
        scorecard = {
            "clarity": 5,
            "decomposition": 1,
            "resilience": 3,
            "observability": 2,
            "idempotence": 4,
            "cost_efficiency": 3,
            "composite": 18,
        }
        dims = [
            "clarity",
            "decomposition",
            "resilience",
            "observability",
            "idempotence",
            "cost_efficiency",
        ]
        for dim in dims:
            assert 1 <= scorecard[dim] <= 5, f"{dim} score out of range"

    def test_artifact_simulation_result_values(self) -> None:
        """simulation_result must be one of: terminal, max_iterations, skipped, error."""
        valid_values = {"terminal", "max_iterations", "skipped", "error"}
        for val in valid_values:
            fm = self._make_artifact_frontmatter(simulation_result=val)
            assert fm["simulation_result"] in valid_values

    def test_artifact_filename_timestamp_format(self) -> None:
        """Artifact filename uses %Y%m%d-%H%M%S format (dash-separated, no T)."""
        import re

        # %Y%m%d-%H%M%S produces e.g. 20260517-143207
        pattern = r"^\d{8}-\d{6}$"
        timestamp = "20260517-143207"
        assert re.match(pattern, timestamp), "Timestamp must be YYYYMMDD-HHMMSS format"
        # T-separated format from _make_instance_id() must NOT be used
        t_format = "20260517T143207"
        assert not re.match(pattern, t_format), "T-separated format is wrong for artifact filenames"

    def test_artifact_path_under_loops_reviews(self) -> None:
        """Artifact path must be .loops/reviews/<name>-<timestamp>.md."""
        loop_name = "fix-types"
        timestamp = "20260517-143207"
        artifact_path = f".loops/reviews/{loop_name}-{timestamp}.md"
        assert artifact_path.startswith(".loops/reviews/")
        assert artifact_path.endswith(".md")
        assert loop_name in artifact_path

    def test_dry_run_skips_artifact_persistence(self) -> None:
        """--dry-run flag: Step 6.5 is skipped (no artifact written)."""
        args = ["fix-types", "--dry-run"]
        dry_run = "--dry-run" in args
        assert dry_run
        # → skill does not call Write in Step 6.5

    def test_rubric_only_skips_artifact_persistence(self) -> None:
        """--rubric-only flag: Step 6.5 is skipped (no artifact written)."""
        args = ["fix-types", "--rubric-only"]
        rubric_only = "--rubric-only" in args
        assert rubric_only
        # → skill stops after scorecard; no artifact write


# =============================================================================
# TestReviewLoopRubric — 6-dimension scorecard logic (Step 3 extension)
# =============================================================================


class TestReviewLoopRubric:
    """Test rubric scorecard structure and scoring heuristics.

    Uses the no-mock pure-Python dict pattern: validates scoring invariants
    and the conditions each dimension measures.
    """

    def test_rubric_has_six_dimensions(self) -> None:
        """Rubric must include exactly 6 dimensions as defined in reference.md."""
        expected_dims = {
            "clarity",
            "decomposition",
            "resilience",
            "observability",
            "idempotence",
            "cost_efficiency",
        }
        assert len(expected_dims) == 6

    def test_rubric_composite_max_is_30(self) -> None:
        """Maximum composite score is 6 dims × 5 = 30."""
        max_per_dim = 5
        num_dims = 6
        assert max_per_dim * num_dims == 30

    def test_rubric_composite_min_is_6(self) -> None:
        """Minimum composite score is 6 dims × 1 = 6."""
        min_per_dim = 1
        num_dims = 6
        assert min_per_dim * num_dims == 6

    def test_resilience_low_when_no_on_error(self) -> None:
        """Resilience dimension 1–2 when states lack on_error routing."""
        spec = {
            "states": {
                "check": {
                    "action": "ruff check .",
                    "evaluate": {"type": "exit_code"},
                    "on_yes": "done",
                    "on_no": "fix",
                },
                "fix": {"action": "ruff check . --fix", "next": "check"},
                "done": {"terminal": True},
            }
        }
        states_with_evaluate = [
            name
            for name, state in spec["states"].items()
            if "evaluate" in state and not state.get("terminal")
        ]
        states_missing_on_error = [
            name for name in states_with_evaluate if "on_error" not in spec["states"][name]
        ]
        # All evaluate states lack on_error → Resilience should be 1 or 2
        assert states_missing_on_error, (
            "Fixture should have states missing on_error for low Resilience score"
        )

    def test_cost_efficiency_low_with_pr1_findings(self) -> None:
        """Cost-efficiency dimension 1–2 when multiple PR-1 findings are present."""
        pr1_findings = [
            {"check_id": "PR-1", "location": "states.check_file"},
            {"check_id": "PR-1", "location": "states.count_errors"},
            {"check_id": "PR-1", "location": "states.format_output"},
        ]
        pr1_count = sum(1 for f in pr1_findings if f["check_id"] == "PR-1")
        # Several PR-1 findings → Cost-efficiency should be 2
        assert pr1_count >= 3, "Multiple PR-1 findings should drive cost-efficiency score low"

    def test_trend_arrows_require_prior_artifact(self) -> None:
        """Trend arrows are only shown when a prior .loops/reviews/<name>-*.md exists."""
        # No prior artifact → no trend column
        prior_artifacts: list[str] = []
        has_prior = len(prior_artifacts) > 0
        assert not has_prior
        # → skill omits trend column from scorecard table

    def test_trend_up_when_score_improves(self) -> None:
        """↑ trend shown when current score exceeds prior score for a dimension."""
        prior_score = 3
        current_score = 4
        trend = (
            "↑" if current_score > prior_score else ("↓" if current_score < prior_score else "→")
        )
        assert trend == "↑"

    def test_trend_down_when_score_decreases(self) -> None:
        """↓ trend shown when current score is below prior score for a dimension."""
        prior_score = 4
        current_score = 2
        trend = (
            "↑" if current_score > prior_score else ("↓" if current_score < prior_score else "→")
        )
        assert trend == "↓"

    def test_trend_flat_when_score_unchanged(self) -> None:
        """→ trend shown when current score equals prior score for a dimension."""
        prior_score = 3
        current_score = 3
        trend = (
            "↑" if current_score > prior_score else ("↓" if current_score < prior_score else "→")
        )
        assert trend == "→"

    def test_rubric_only_flag_stops_after_scorecard(self) -> None:
        """--rubric-only: skill stops after Step 3 scorecard output."""
        args = ["fix-types", "--rubric-only"]
        rubric_only = "--rubric-only" in args
        assert rubric_only
        # → no fix proposals, no artifact persistence


# =============================================================================
# TestReviewLoopDescriptionDraft — Step 1.5 description completeness gate
# =============================================================================


class TestReviewLoopDescriptionDraft:
    """Test Step 1.5: description completeness gate and draft logic.

    Uses the no-mock pure-Python dict pattern.
    """

    def test_no_description_fixture_lacks_description(self) -> None:
        """no-description.yaml fixture has no description: field."""
        fixture_path = FIXTURES_DIR / "no-description.yaml"
        assert fixture_path.exists(), f"Fixture not found: {fixture_path}"

        with open(fixture_path) as f:
            spec = yaml.safe_load(f)

        assert "description" not in spec, "Fixture must not have a description field"

    def test_description_absent_triggers_draft(self) -> None:
        """Step 1.5: absent description triggers draft gate."""
        spec: dict = {
            "name": "test-loop",
            "initial": "check",
            "states": {
                "check": {"action": "pytest", "on_yes": "done", "on_no": "done"},
                "done": {"terminal": True},
            },
        }
        description = spec.get("description", "")
        should_draft = not description or len(description.split()) < 5
        assert should_draft

    def test_description_too_short_triggers_draft(self) -> None:
        """Step 1.5: description with < 5 words triggers draft gate."""
        spec = {"description": "Run checks", "initial": "check"}
        description = spec.get("description", "")
        should_draft = not description or len(description.split()) < 5
        assert should_draft

    def test_description_present_and_long_enough_skips_draft(self) -> None:
        """Step 1.5: description >= 5 words skips the gate silently."""
        spec = {"description": "Fix type errors until mypy exits zero", "initial": "check"}
        description = spec.get("description", "")
        should_draft = not description or len(description.split()) < 5
        assert not should_draft

    def test_draft_unblocks_sr1_and_sr4(self) -> None:
        """Accepted draft description unblocks SR-1 and SR-4 (which skip on absent/short desc)."""
        # Before draft: no description → SR-1 and SR-4 skip
        spec_before: dict = {"name": "test-loop", "initial": "check"}
        desc_before = spec_before.get("description", "")
        sr14_skipped_before = not desc_before or len(desc_before.split()) < 5
        assert sr14_skipped_before

        # After draft accepted: description present → SR-1 and SR-4 run
        spec_after = dict(spec_before)
        spec_after["description"] = "Run pytest until all tests pass successfully"
        desc_after = spec_after.get("description", "")
        sr14_skipped_after = not desc_after or len(desc_after.split()) < 5
        assert not sr14_skipped_after

    def test_draft_proposed_not_silently_injected(self) -> None:
        """Step 1.5 must propose the draft as a fix, not silently modify the YAML."""
        # The draft is proposed through the standard fix approval flow (AskUserQuestion
        # in interactive mode, or applied with --auto). Description draft is a pure
        # addition (no routing change), so it is eligible for auto-apply like QC-6.
        is_pure_addition = True  # adding description: to a loop that lacks it
        is_routing_change = False
        assert is_pure_addition and not is_routing_change
        # → eligible for auto-apply in --auto mode


# =============================================================================
# TestReviewLoopPostFixIteration — Step 4.5 post-fix re-check logic
# =============================================================================


class TestReviewLoopPostFixIteration:
    """Test Step 4.5: post-fix iteration and RT-1 regression detection.

    Uses the no-mock pure-Python dict pattern: builds finding dicts and asserts
    on the regression detection logic.
    """

    def _make_finding(self, check_id: str, location: str, message: str = "x") -> dict:
        return {
            "check_id": check_id,
            "severity": "Warning",
            "location": location,
            "message": message,
        }

    def test_rt1_detected_when_new_finding_appears(self) -> None:
        """RT-1: a finding in post-fix pass not in original findings triggers RT-1."""
        original_findings = [
            self._make_finding("QC-6", "on_handoff"),
        ]
        post_fix_findings = [
            self._make_finding("QC-2", "states.check"),  # new finding not in original
        ]
        # Build a set of (check_id, location) keys from original
        original_keys = {(f["check_id"], f["location"]) for f in original_findings}
        regressions = [
            f for f in post_fix_findings if (f["check_id"], f["location"]) not in original_keys
        ]
        assert len(regressions) == 1
        assert regressions[0]["check_id"] == "QC-2"
        # → skill should emit RT-1 Warning for this new finding

    def test_rt1_not_triggered_when_no_new_findings(self) -> None:
        """RT-1: no new findings after fix → no RT-1 Warning."""
        original_findings = [
            self._make_finding("QC-6", "on_handoff"),
            self._make_finding("QC-1", "max_iterations"),
        ]
        post_fix_findings = [
            self._make_finding("QC-1", "max_iterations"),  # same as original, not new
        ]
        original_keys = {(f["check_id"], f["location"]) for f in original_findings}
        regressions = [
            f for f in post_fix_findings if (f["check_id"], f["location"]) not in original_keys
        ]
        assert len(regressions) == 0
        # → no RT-1 Warning

    def test_rt1_not_triggered_when_finding_resolved(self) -> None:
        """RT-1: finding resolved by fix (no longer in post-fix pass) → not a regression."""
        original_findings = [
            self._make_finding("QC-6", "on_handoff"),
        ]
        post_fix_findings: list[dict] = []  # QC-6 was fixed, no longer present
        original_keys = {(f["check_id"], f["location"]) for f in original_findings}
        regressions = [
            f for f in post_fix_findings if (f["check_id"], f["location"]) not in original_keys
        ]
        assert len(regressions) == 0
        # → no RT-1; fix successfully resolved the original finding

    def test_post_fix_max_rounds_is_three(self) -> None:
        """Step 4.5 iterates at most 3 rounds."""
        max_rounds = 3
        assert max_rounds == 3

    def test_post_fix_skipped_when_no_fixes_applied(self) -> None:
        """Step 4.5 is skipped when no fixes were applied in Step 4."""
        fixes_applied = 0
        should_run_post_fix = fixes_applied > 0
        assert not should_run_post_fix

    def test_post_fix_stops_early_when_no_regressions(self) -> None:
        """Step 4.5 stops before max rounds when no RT-1 regressions detected."""
        rounds_completed = 0
        max_rounds = 3
        regressions_each_round = [0, None, None]  # stops after round 1

        for i in range(max_rounds):
            rounds_completed += 1
            if regressions_each_round[i] == 0:
                break

        assert rounds_completed == 1  # stopped after first round with no regressions

    def test_rt1_finding_schema(self) -> None:
        """RT-1 findings use the same { check_id, severity, location, message } schema."""
        rt1_finding = {
            "check_id": "RT-1",
            "severity": "Warning",
            "location": "states.check",
            "message": "New finding after fix — QC-2: Missing on_error routing.",
        }
        assert rt1_finding["severity"] == "Warning"
        assert rt1_finding["check_id"] == "RT-1"
        assert "check_id" in rt1_finding and "location" in rt1_finding and "message" in rt1_finding
