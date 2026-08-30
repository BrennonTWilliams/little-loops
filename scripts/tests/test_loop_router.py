"""Tests for the loop-router built-in loop."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "loop-router.yaml"


@pytest.fixture
def loop_data() -> dict:
    """Load the loop-router YAML."""
    assert LOOP_FILE.exists(), f"loop-router.yaml not found at {LOOP_FILE}"
    with open(LOOP_FILE) as f:
        return yaml.safe_load(f)


class TestLoopRouterFile:
    """Tests that loop-router.yaml exists and is structurally valid."""

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists(), f"loop-router.yaml not found at {LOOP_FILE}"

    def test_parses_as_yaml(self, loop_data: dict) -> None:
        assert isinstance(loop_data, dict), "root must be a mapping"

    def test_validates_as_fsm(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM validation errors: {[str(e) for e in error_list]}"

    def test_name(self, loop_data: dict) -> None:
        assert loop_data.get("name") == "loop-router"

    def test_category(self, loop_data: dict) -> None:
        assert loop_data.get("category") == "routing"

    def test_input_key(self, loop_data: dict) -> None:
        assert loop_data.get("input_key") == "goal"

    def test_initial_state(self, loop_data: dict) -> None:
        assert loop_data.get("initial") == "discover_loops"

    def test_context_variables(self, loop_data: dict) -> None:
        ctx = loop_data.get("context", {})
        assert "goal" in ctx, "context must have goal variable (populated via input_key)"
        assert "auto" in ctx, "context must have auto variable"
        assert "auto_create" in ctx, "context must have auto_create variable"
        assert "confidence_threshold" in ctx, "context must have confidence_threshold variable"
        assert "include" in ctx, "context must have include variable"
        assert "exclude" in ctx, "context must have exclude variable"

    def test_context_defaults(self, loop_data: dict) -> None:
        ctx = loop_data.get("context", {})
        assert ctx.get("goal") == "", "goal default must be empty string"
        assert ctx.get("auto") == "true", "auto default must be 'true'"
        assert ctx.get("auto_create") == "false", "auto_create default must be 'false'"
        assert ctx.get("confidence_threshold") == "0.7", (
            "confidence_threshold default must be '0.7'"
        )
        assert ctx.get("include") == "", "include default must be empty string"
        assert ctx.get("exclude") == "", "exclude default must be empty string"


class TestLoopRouterStates:
    """Tests for required states and their structure."""

    REQUIRED_STATES = {
        "discover_loops",
        "classify_goal",
        "route_branch_project",
        "route_branch_builtin",
        "score_project_loops",
        "parse_project_score",
        "score_builtin_loops",
        "parse_builtin_score",
        "extract_input",
        "select_loop",
        "present_choices",
        "apply_user_choice",
        "refresh_input",
        "dispatch",
        "review",
        "propose_new_loop",
        "check_auto_create",
        "invoke_create_loop",
        "present_result",
        "failed",
    }

    def test_has_all_required_states(self, loop_data: dict) -> None:
        actual = set(loop_data.get("states", {}).keys())
        missing = self.REQUIRED_STATES - actual
        assert not missing, f"Missing required states: {missing}"

    def test_discover_loops_is_shell(self, loop_data: dict) -> None:
        state = loop_data["states"]["discover_loops"]
        assert state.get("action_type") == "shell"
        assert "ll-loop list" in state.get("action", "")
        assert state.get("capture") == "catalog"
        assert state.get("next") == "classify_goal"
        assert state.get("on_error") == "finalize_failed"

    def test_discover_loops_excludes_self(self, loop_data: dict) -> None:
        state = loop_data["states"]["discover_loops"]
        assert "loop-router" in state.get("action", ""), (
            "discover_loops must exclude 'loop-router' from the catalog"
        )

    def test_discover_loops_uses_visibility_public(self, loop_data: dict) -> None:
        state = loop_data["states"]["discover_loops"]
        assert "--visibility public" in state.get("action", ""), (
            "discover_loops action must include '--visibility public' flag on ll-loop list"
        )

    def test_classify_goal_is_prompt(self, loop_data: dict) -> None:
        state = loop_data["states"]["classify_goal"]
        assert state.get("action_type") == "prompt"
        assert state.get("capture") == "classification"
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "llm_structured"

    def test_classify_goal_routes_to_branch_project(self, loop_data: dict) -> None:
        state = loop_data["states"]["classify_goal"]
        assert state.get("on_yes") == "route_branch_project"
        assert state.get("on_no") == "route_branch_project"
        assert state.get("on_partial") == "route_branch_project"
        assert state.get("on_cannot_judge") == "route_branch_project"

    def test_three_branch_targets_reachable_from_classify_goal(self, loop_data: dict) -> None:
        """All three branch targets are reachable from the classify_goal→route_branch chain."""
        states = loop_data.get("states", {})
        # classify_goal → route_branch_project
        assert states["classify_goal"]["on_yes"] == "route_branch_project"
        # route_branch_project → score_project_loops (branch A) or route_branch_builtin
        assert states["route_branch_project"]["on_yes"] == "score_project_loops"
        assert states["route_branch_project"]["on_no"] == "route_branch_builtin"
        # route_branch_builtin → score_builtin_loops (branch B) or propose_new_loop (branch C)
        assert states["route_branch_builtin"]["on_yes"] == "score_builtin_loops"
        assert states["route_branch_builtin"]["on_no"] == "propose_new_loop"

    def test_route_branch_project_is_shell_exit_code(self, loop_data: dict) -> None:
        state = loop_data["states"]["route_branch_project"]
        assert state.get("action_type") == "shell"
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "exit_code"

    def test_route_branch_builtin_is_shell_exit_code(self, loop_data: dict) -> None:
        state = loop_data["states"]["route_branch_builtin"]
        assert state.get("action_type") == "shell"
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "exit_code"

    def test_score_project_loops_is_prompt(self, loop_data: dict) -> None:
        state = loop_data["states"]["score_project_loops"]
        assert state.get("action_type") == "prompt"
        assert state.get("capture") == "project_score"

    def test_score_project_loops_cannot_judge_follows_funnel(self, loop_data: dict) -> None:
        state = loop_data["states"]["score_project_loops"]
        assert (
            state.get("on_cannot_judge")
            == state.get("on_yes")
            == state.get("on_no")
            == state.get("on_partial")
        )

    def test_score_builtin_loops_is_prompt(self, loop_data: dict) -> None:
        state = loop_data["states"]["score_builtin_loops"]
        assert state.get("action_type") == "prompt"
        assert state.get("capture") == "builtin_score"

    def test_score_builtin_loops_cannot_judge_follows_funnel(self, loop_data: dict) -> None:
        state = loop_data["states"]["score_builtin_loops"]
        assert (
            state.get("on_cannot_judge")
            == state.get("on_yes")
            == state.get("on_no")
            == state.get("on_partial")
        )

    def test_review_cannot_judge_follows_funnel(self, loop_data: dict) -> None:
        state = loop_data["states"]["review"]
        assert (
            state.get("on_cannot_judge")
            == state.get("on_yes")
            == state.get("on_no")
            == state.get("on_partial")
        )

    def test_dispatch_uses_native_loop_field(self, loop_data: dict) -> None:
        state = loop_data["states"]["dispatch"]
        assert "loop" in state, "dispatch must use the native loop: field (not action_type)"
        assert "captured.chosen" in state.get("loop", ""), (
            "dispatch loop: field must reference captured.chosen.output"
        )
        assert state.get("capture") == "sub_loop_output"
        # BUG-3334: dispatch no longer routes directly to review — it routes
        # through write_sub_loop_output, which spills the unbounded sub-loop
        # event stream to a file before review's prompt ever sees it.
        assert state.get("on_yes") == "write_sub_loop_output"
        assert state.get("on_no") == "write_sub_loop_output"
        assert state.get("on_error") == "write_sub_loop_output"

    def test_write_sub_loop_output_wiring(self, loop_data: dict) -> None:
        """BUG-3334 AC4/AC12: the intermediate shell state must write
        sub_loop_output to the deterministic path via the combined
        :shell:default= suffix (never bare :shell, which raises on a missing
        capture), and its own on_error/next must both degrade forward to
        review (refresh_input's convention), not dead-end."""
        state = loop_data["states"]["write_sub_loop_output"]
        assert state.get("action_type") == "shell"
        action = state.get("action", "") or ""
        assert "${captured.sub_loop_output.output:shell:default=}" in action
        assert "${context.run_dir}/sub-loop-events.jsonl" in action
        assert state.get("on_error") == "review"
        assert state.get("next") == "review"

        review_action = loop_data["states"]["review"].get("action", "") or ""
        assert "${context.run_dir}/sub-loop-events.jsonl" in review_action
        assert "${captured.sub_loop_output.output}" not in review_action

    def test_write_sub_loop_output_survives_oversized_stream(
        self, loop_data: dict, tmp_path: Path
    ) -> None:
        """BUG-3334 AC14: a large, quote-dense sub_loop_output must not crash
        the write step with an uncaught E2BIG/OSError. The write action is
        rendered through the real interpolate() (so :shell's shlex.quote()
        expansion is actually exercised) and executed via subprocess, mirroring
        TestFinalizePresentResult's substitute-then-execute-then-assert shape.
        executor.py's _run_action_or_route already converts any exception from
        a shell state's subprocess call into a graceful on_error route when
        on_error is set (as it is here), so this pins that no *lower-level*
        crash escapes the subprocess call itself for a large, quote-heavy
        payload sized well under the real OS ARG_MAX."""
        from little_loops.fsm.interpolation import InterpolationContext, interpolate

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Quote-dense filler so shlex.quote()'s ~4x expansion on embedded
        # single quotes is actually exercised, not just the pre-quoting length.
        big_stream = "{\"event\": \"it's a test, it's fine\"}\n" * 6000  # ~230KB raw
        action = loop_data["states"]["write_sub_loop_output"]["action"]
        ctx = InterpolationContext(
            context={"run_dir": str(run_dir)},
            captured={"sub_loop_output": {"output": big_stream, "stderr": "", "exit_code": 0}},
            state_name="write_sub_loop_output",
        )
        rendered = interpolate(action, ctx)
        result = subprocess.run(
            ["bash", "-c", rendered], capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, result.stderr
        written = (run_dir / "sub-loop-events.jsonl").read_text()
        assert written == big_stream

    def test_dispatch_with_binding_references_derived_params(self, loop_data: dict) -> None:
        state = loop_data["states"]["dispatch"]
        with_ = state.get("with", {})
        assert "input" in with_, "dispatch must bind an input via with:"
        assert "captured.derived_params" in with_.get("input", ""), (
            "dispatch with.input must reference captured.derived_params.output"
        )

    def test_present_choices_uses_output_contains_cancel(self, loop_data: dict) -> None:
        state = loop_data["states"]["present_choices"]
        assert state.get("action_type") == "prompt"
        assert state.get("capture") == "user_choice"
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_contains"
        assert evaluate.get("pattern") == "CANCEL", (
            "present_choices must use CANCEL sentinel (not PASS/ALL_PASS)"
        )
        assert state.get("on_yes") == "finalize_present_result"
        assert state.get("on_no") == "apply_user_choice"

    def test_present_result_is_terminal(self, loop_data: dict) -> None:
        state = loop_data["states"]["present_result"]
        assert state.get("terminal") is True

    def test_failed_is_terminal(self, loop_data: dict) -> None:
        state = loop_data["states"]["failed"]
        assert state.get("terminal") is True

    def test_propose_new_loop_routes_to_check_auto_create(self, loop_data: dict) -> None:
        state = loop_data["states"]["propose_new_loop"]
        assert state.get("action_type") == "prompt"
        assert state.get("capture") == "new_loop_proposal"
        assert state.get("on_yes") == "check_auto_create"

    def test_check_auto_create_routes_to_invoke_or_result(self, loop_data: dict) -> None:
        state = loop_data["states"]["check_auto_create"]
        assert state.get("on_yes") == "invoke_create_loop"
        assert state.get("on_no") == "finalize_present_result"

    def test_discover_loops_handles_include_allowlist(self, loop_data: dict) -> None:
        action = loop_data["states"]["discover_loops"].get("action", "")
        assert "_matches_include" in action, (
            "discover_loops must define _matches_include filter for the include allowlist"
        )
        assert "category:" in action, (
            "discover_loops include filter must support category:<label> selector form"
        )
        assert "builtin:*" in action, (
            "discover_loops include filter must support builtin:* selector form"
        )
        assert "project:*" in action, (
            "discover_loops include filter must support project:* selector form"
        )


class TestFinalizePresentResult:
    """Regression tests for BUG-3349: finalize_present_result must not parse
    model output unanchored, and must not interpolate it into a Python string
    literal."""

    @staticmethod
    def _run(loop_data: dict, tmp_path: Path, proposal_out: str, review_out: str) -> dict:
        """Execute finalize_present_result's bash `action`, substituting the
        `${captured.*.output:shell:default=}` refs with shlex-quoted synthetic
        values — mirroring how `:shell` interpolation quotes at runtime — and
        `${context.run_dir}` with a scratch directory."""
        action = loop_data["states"]["finalize_present_result"].get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        script = action.replace("${context.run_dir}", str(run_dir))
        script = script.replace(
            "${captured.new_loop_proposal.output:shell:default=}",
            shlex.quote(proposal_out),
        )
        script = script.replace(
            "${captured.review_result.output:shell:default=}",
            shlex.quote(review_out),
        )
        assert "${" not in script, f"unsubstituted interpolation token remains: {script}"
        result = subprocess.run(
            ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 0, f"finalize_present_result failed: {result.stderr}"
        return json.loads(result.stdout)

    def test_decoy_verdict_in_summary_does_not_flip_success(
        self, loop_data: dict, tmp_path: Path
    ) -> None:
        """A REVIEW_SUCCESS:false echoed inside the summary must not beat the
        real line-anchored REVIEW_SUCCESS:true verdict."""
        review_out = (
            "REVIEW_SUCCESS:true\n"
            "REVIEW_SUMMARY:the run discussed a prior REVIEW_SUCCESS:false result\n"
        )
        result = self._run(loop_data, tmp_path, proposal_out="", review_out=review_out)
        assert result["success"] is True

    def test_triple_quote_in_proposal_output_does_not_break_the_heredoc(
        self, loop_data: dict, tmp_path: Path
    ) -> None:
        """A literal `\"\"\"` in captured model output must not reach a Python
        string literal (SyntaxError on the pre-fix tree)."""
        proposal_out = 'PROPOSED_NAME:foo """ bar\n'
        result = self._run(loop_data, tmp_path, proposal_out=proposal_out, review_out="")
        assert result["branch"] == "propose_new"
        assert result["proposed_loop_spec"]["name"] == 'foo """ bar'

    def test_mid_line_proposed_name_does_not_select_propose_branch(
        self, loop_data: dict, tmp_path: Path
    ) -> None:
        """A `PROPOSED_NAME:` appearing mid-line inside prose must not select
        the propose_new branch; only a line-anchored occurrence should."""
        review_out = (
            "REVIEW_SUCCESS:true\n"
            "REVIEW_SUMMARY:the prior run mentioned PROPOSED_NAME:decoy in passing\n"
        )
        result = self._run(loop_data, tmp_path, proposal_out="", review_out=review_out)
        assert result["branch"] != "propose_new"
        assert result["success"] is True


@pytest.mark.slow
@pytest.mark.skipif(
    shutil.which("claude") is None,
    reason="live LLM required; skip in CI unless claude CLI is available",
)
class TestLoopRouterLive:
    """Behavioural tests requiring a live LLM (claude CLI). Guarded by --slow."""

    def test_loop_validates_before_live_run(self) -> None:
        """Sanity check — loop must validate before any live test runs."""
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM validation errors: {[str(e) for e in error_list]}"
