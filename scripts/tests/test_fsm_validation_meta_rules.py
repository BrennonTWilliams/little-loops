"""Tests for FSM validation meta-loop rule family (MR-1..MR-6): meta-loop
evaluation, artifact isolation, partial-route dead ends, artifact overwrite,
generator-fix discipline, and the harness multimodal evaluator blind spot.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    StateConfig,
)
from little_loops.fsm.validation import (
    ValidationSeverity,
    _validate_artifact_isolation,
    _validate_artifact_overwrite,
    _validate_generator_fix_discipline,
    _validate_harness_multimodal_evaluator_blind_spot,
    _validate_meta_loop_evaluation,
    _validate_partial_route_dead_end,
    load_and_validate,
    validate_fsm,
)


def make_state(**kwargs) -> StateConfig:
    """Convenience constructor for StateConfig in tests."""
    return StateConfig(**kwargs)


BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"


class TestMetaLoopValidation:
    """ENH-1665: MR-1 and MR-2 validation rules for meta-loops."""

    def _meta_fsm(self, **kwargs) -> FSMLoop:
        """Build a minimal meta-loop (detected via lib/benchmark.yaml import)."""
        defaults: dict = {
            "name": "test-meta",
            "initial": "optimize",
            "states": {
                "optimize": make_state(action="run.sh", on_yes="done"),
                "done": make_state(terminal=True),
            },
            "imports": ["lib/benchmark.yaml"],
        }
        defaults.update(kwargs)
        return FSMLoop(**defaults)

    # --- positive control ---

    def test_harness_optimize_passes_clean(self) -> None:
        """harness-optimize.yaml validates without MR-1 or MR-2 errors (positive control)."""
        harness_path = BUILTIN_LOOPS_DIR / "harness-optimize.yaml"
        if not harness_path.exists():
            pytest.skip("harness-optimize.yaml not found in builtin loops")
        fsm, _ = load_and_validate(harness_path)
        errors = _validate_meta_loop_evaluation(fsm)
        mr_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert mr_errors == [], f"harness-optimize triggered MR-1: {mr_errors}"
        mr_warnings = [e for e in errors if "MR-2" in e.message or "baseline" in e.message]
        assert mr_warnings == [], f"harness-optimize triggered MR-2: {mr_warnings}"

    # --- MR-1: meta-loop must have non-LLM evaluator ---

    def test_mr1_fires_for_meta_loop_with_only_llm_evaluator(self) -> None:
        """MR-1 ERROR fires when meta-loop uses only llm_structured evaluator."""
        fsm = self._meta_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_meta_loop_evaluation(fsm)
        mr1_errors = [
            e for e in errors if e.severity == ValidationSeverity.ERROR and "non-LLM" in e.message
        ]
        assert len(mr1_errors) == 1, f"Expected one MR-1 ERROR, got: {errors}"

    def test_mr1_passes_when_exit_code_evaluator_present(self) -> None:
        """MR-1 does not fire when at least one exit_code evaluator is present."""
        fsm = self._meta_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_meta_loop_evaluation(fsm)
        mr1_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert mr1_errors == [], f"Unexpected MR-1 ERROR: {mr1_errors}"

    def test_mr1_passes_when_score_stall_evaluator_present(self) -> None:
        """MR-1 does not fire when at least one score_stall evaluator is present (ENH-2428)."""
        fsm = self._meta_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="score_stall"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_meta_loop_evaluation(fsm)
        mr1_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert mr1_errors == [], f"Unexpected MR-1 ERROR: {mr1_errors}"

    def test_mr1_suppressed_by_meta_self_eval_ok(self) -> None:
        """meta_self_eval_ok: true suppresses MR-1."""
        fsm = self._meta_fsm(
            meta_self_eval_ok=True,
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_meta_loop_evaluation(fsm)
        assert errors == [], f"meta_self_eval_ok should suppress all MR errors: {errors}"

    # --- MR-2: meta-loop should have measure-then-act spine ---

    def test_mr2_fires_when_no_capture_referenced_in_evaluate(self) -> None:
        """MR-2 WARNING fires when meta-loop has captures but none referenced in evaluate."""
        fsm = self._meta_fsm(
            states={
                "measure": make_state(
                    action_type="shell",
                    action="./score.sh",
                    capture="baseline",
                    next="check",
                ),
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_meta_loop_evaluation(fsm)
        mr2_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "baseline" in e.message
        ]
        assert len(mr2_warnings) == 1, f"Expected one MR-2 WARNING, got: {errors}"

    def test_mr2_does_not_fire_when_capture_referenced_in_previous(self) -> None:
        """MR-2 does not fire when captured variable is referenced in evaluate.previous."""
        fsm = self._meta_fsm(
            states={
                "measure": make_state(
                    action_type="shell",
                    action="./score.sh",
                    capture="baseline",
                    next="gate",
                ),
                "gate": make_state(
                    action_type="shell",
                    action="./score.sh",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target="${context.target_score}",
                        previous="${captured.baseline.output}",
                        direction="maximize",
                    ),
                    route={"target": "done", "progress": "done", "stall": "done"},
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_meta_loop_evaluation(fsm)
        mr2_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "baseline" in e.message
        ]
        assert mr2_warnings == [], f"Unexpected MR-2 WARNING: {mr2_warnings}"

    def test_mr2_suppressed_by_meta_self_eval_ok(self) -> None:
        """meta_self_eval_ok: true suppresses MR-2."""
        fsm = self._meta_fsm(
            meta_self_eval_ok=True,
            states={
                "measure": make_state(
                    action_type="shell", action="./score.sh", capture="baseline", next="check"
                ),
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_meta_loop_evaluation(fsm)
        assert errors == []

    # --- non-meta loops are unaffected ---

    def test_non_meta_loop_with_llm_only_not_flagged(self) -> None:
        """A non-meta loop with only llm_structured evaluator does not trigger MR-1 or MR-2."""
        fsm = FSMLoop(
            name="regular-loop",
            initial="check",
            states={
                "check": make_state(
                    action="/ll:some-skill",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_meta_loop_evaluation(fsm)
        assert errors == [], f"Non-meta loop should not trigger MR rules: {errors}"

    # --- meta_self_eval_ok round-trip via validate_fsm ---

    def test_meta_self_eval_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level meta_self_eval_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A meta-loop with escape hatch\n"
            "initial: work\n"
            "meta_self_eval_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []



class TestArtifactIsolation:
    """MR-3: loops must isolate artifacts to ${context.run_dir}, not shared .loops/tmp/."""

    def _simple_fsm(self, action: str, *, shared_state_ok: bool = False) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(action=action, on_yes="done", on_no="work"),
                "done": make_state(terminal=True),
            },
            shared_state_ok=shared_state_ok,
        )

    def test_mr3_fires_when_loop_writes_to_shared_tmp(self) -> None:
        """MR-3 WARNING fires for any state action referencing .loops/tmp/<path>."""
        fsm = self._simple_fsm("echo hi > .loops/tmp/queue.txt")
        errors = _validate_artifact_isolation(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert ".loops/tmp/queue.txt" in errors[0].message
        assert errors[0].path == "states.work.action"

    def test_mr3_does_not_fire_when_loop_uses_context_run_dir(self) -> None:
        """MR-3 does not fire when the action uses ${context.run_dir} for artifacts."""
        fsm = self._simple_fsm('echo hi > "${context.run_dir}/queue.txt"')
        errors = _validate_artifact_isolation(fsm)
        assert errors == []

    def test_mr3_does_not_fire_for_issues_dir(self) -> None:
        """MR-3 does not fire for legitimate .issues/ writes."""
        fsm = self._simple_fsm("echo content > .issues/bugs/new.md")
        errors = _validate_artifact_isolation(fsm)
        assert errors == []

    def test_mr3_does_not_fire_for_diagnostics_dir(self) -> None:
        """MR-3 does not fire for legitimate .loops/diagnostics/ writes."""
        fsm = self._simple_fsm("echo log > .loops/diagnostics/report.md")
        errors = _validate_artifact_isolation(fsm)
        assert errors == []

    def test_mr3_does_not_fire_for_actionless_states(self) -> None:
        """States without an action (e.g., terminal or sub-loop states) do not trigger MR-3."""
        fsm = FSMLoop(
            name="test-loop",
            initial="s",
            states={"s": make_state(terminal=True)},
        )
        errors = _validate_artifact_isolation(fsm)
        assert errors == []

    def test_mr3_fires_once_per_occurrence(self) -> None:
        """An action with multiple shared-tmp paths emits one warning per path."""
        fsm = self._simple_fsm("cat .loops/tmp/a.txt > .loops/tmp/b.txt && rm .loops/tmp/c.txt")
        errors = _validate_artifact_isolation(fsm)
        assert len(errors) == 3
        matched = sorted(e.message.split("'")[1] for e in errors)
        assert matched == [".loops/tmp/a.txt", ".loops/tmp/b.txt", ".loops/tmp/c.txt"]

    def test_mr3_suppressed_by_shared_state_ok(self) -> None:
        """shared_state_ok: true suppresses MR-3 entirely."""
        fsm = self._simple_fsm("echo hi > .loops/tmp/queue.txt", shared_state_ok=True)
        errors = _validate_artifact_isolation(fsm)
        assert errors == []

    def test_mr3_runs_via_validate_fsm(self) -> None:
        """validate_fsm() wires in MR-3 (end-to-end, not just direct call)."""
        fsm = self._simple_fsm("echo hi > .loops/tmp/queue.txt")
        errors = validate_fsm(fsm)
        mr3 = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and ".loops/tmp/queue.txt" in e.message
        ]
        assert len(mr3) == 1

    def test_shared_state_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level shared_state_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally shares cross-run state\n"
            "initial: work\n"
            "shared_state_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []



class TestPartialRouteDeadEnd:
    """MR-4 (ENH-1917): LLM-judged states with only on_yes have a partial/no dead-end."""

    def _prompt_fsm(
        self,
        *,
        on_yes: str | None = "done",
        on_no: str | None = None,
        on_partial: str | None = None,
        next_state: str | None = None,
        action_type: str | None = "prompt",
        partial_route_ok: bool = False,
        with_route: bool = False,
    ) -> FSMLoop:
        state_kwargs: dict = {
            "action": "Do something",
            "on_error": "failed",
        }
        if action_type is not None:
            state_kwargs["action_type"] = action_type
        if on_yes is not None:
            state_kwargs["on_yes"] = on_yes
        if on_no is not None:
            state_kwargs["on_no"] = on_no
        if on_partial is not None:
            state_kwargs["on_partial"] = on_partial
        if next_state is not None:
            state_kwargs["next"] = next_state
        if with_route:
            from little_loops.fsm.schema import RouteConfig

            state_kwargs.pop("on_yes", None)
            state_kwargs["route"] = RouteConfig(routes={"yes": "done"}, default="done")
        return FSMLoop(
            name="test-loop",
            initial="generate",
            states={
                "generate": make_state(**state_kwargs),
                "done": make_state(terminal=True),
                "failed": make_state(terminal=True),
            },
            partial_route_ok=partial_route_ok,
        )

    # --- positive controls ---

    def test_mr4_fires_for_on_yes_only_prompt_state(self) -> None:
        """MR-4 WARNING fires when a prompt state has only on_yes with no on_no/on_partial."""
        fsm = self._prompt_fsm()
        errors = _validate_partial_route_dead_end(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "generate" in errors[0].message
        assert "ENH-1917" in errors[0].message
        assert errors[0].path == "states.generate"

    def test_mr4_fires_when_on_partial_missing(self) -> None:
        """MR-4 fires when on_no is set but on_partial is missing."""
        fsm = self._prompt_fsm(on_no="generate")
        errors = _validate_partial_route_dead_end(fsm)
        assert len(errors) == 1
        assert "`partial`" in errors[0].message

    def test_mr4_fires_when_on_no_missing(self) -> None:
        """MR-4 fires when on_partial is set but on_no is missing."""
        fsm = self._prompt_fsm(on_partial="generate")
        errors = _validate_partial_route_dead_end(fsm)
        assert len(errors) == 1
        assert "`no`" in errors[0].message

    def test_mr4_fires_for_slash_command_action_type(self) -> None:
        """MR-4 fires for slash_command action_type, not just prompt."""
        fsm = self._prompt_fsm(action_type="slash_command")
        errors = _validate_partial_route_dead_end(fsm)
        assert len(errors) == 1

    def test_mr4_fires_for_implicit_prompt_via_slash_prefix(self) -> None:
        """MR-4 fires for a /slash action with no explicit action_type."""
        fsm = FSMLoop(
            name="test-loop",
            initial="run",
            states={
                "run": make_state(action="/ll:some-skill", on_yes="done", on_error="failed"),
                "done": make_state(terminal=True),
                "failed": make_state(terminal=True),
            },
        )
        errors = _validate_partial_route_dead_end(fsm)
        assert len(errors) == 1

    # --- negative controls ---

    def test_mr4_does_not_fire_when_on_no_and_on_partial_both_set(self) -> None:
        """No warning when both on_no and on_partial are mapped."""
        fsm = self._prompt_fsm(on_no="generate", on_partial="generate")
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    def test_mr4_does_not_fire_when_next_present(self) -> None:
        """No warning when next: provides an unconditional handoff."""
        fsm = self._prompt_fsm(on_yes=None, next_state="done")
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    def test_mr4_does_not_fire_for_full_route_table(self) -> None:
        """No warning when a full route: table (with default) is used."""
        fsm = self._prompt_fsm(with_route=True)
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    def test_mr4_does_not_fire_for_non_llm_evaluator(self) -> None:
        """No warning when the state uses a deterministic exit_code evaluator."""
        fsm = FSMLoop(
            name="test-loop",
            initial="build",
            states={
                "build": make_state(
                    action="make",
                    action_type="shell",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_error="failed",
                ),
                "done": make_state(terminal=True),
                "failed": make_state(terminal=True),
            },
        )
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    def test_mr4_does_not_fire_when_on_yes_absent(self) -> None:
        """No warning when on_yes is not set at all (nothing to flag)."""
        fsm = FSMLoop(
            name="test-loop",
            initial="run",
            states={
                "run": make_state(action="Do something", action_type="prompt", on_no="run"),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    # --- suppression ---

    def test_mr4_suppressed_by_partial_route_ok(self) -> None:
        """partial_route_ok: true suppresses MR-4 entirely."""
        fsm = self._prompt_fsm(partial_route_ok=True)
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == []

    # --- wiring ---

    def test_mr4_runs_via_validate_fsm(self) -> None:
        """validate_fsm() wires in MR-4 (end-to-end, not just direct call)."""
        fsm = self._prompt_fsm()
        errors = validate_fsm(fsm)
        mr4 = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "ENH-1917" in e.message
        ]
        assert len(mr4) == 1

    def test_partial_route_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level partial_route_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop where dead-ending on non-yes is intentional\n"
            "initial: run\n"
            "partial_route_ok: true\n"
            "states:\n"
            "  run:\n"
            "    action: /ll:do-thing\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []



class TestHarnessMultimodalEvaluatorBlindSpot:
    """ENH-1819: WARNING when harness loops use LLM multimodal eval as sole gate to terminal."""

    def _harness_fsm(self, **kwargs) -> FSMLoop:
        """Build a minimal harness-category FSM."""
        defaults: dict = {
            "name": "test-harness",
            "initial": "score",
            "category": "harness",
            "states": {
                "score": make_state(
                    action_type="prompt",
                    action="Read the screenshot screenshot.png and judge the output.",
                    evaluate=EvaluateConfig(type="output_contains", pattern="PASS"),
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        }
        defaults.update(kwargs)
        return FSMLoop(**defaults)

    # --- positive control ---

    def test_fires_for_harness_multimodal_prompt_to_terminal(self) -> None:
        """WARNING fires when harness loop has multimodal prompt routing directly to terminal."""
        fsm = self._harness_fsm()
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert len(errors) == 1, f"Expected one WARNING, got: {errors}"
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "score" in str(errors[0])

    # --- negative controls ---

    def test_does_not_fire_for_non_harness_loop(self) -> None:
        """Does not fire when category is not harness."""
        fsm = self._harness_fsm(category="oracle")
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert errors == [], f"Expected no warnings for non-harness, got: {errors}"

    def test_does_not_fire_when_on_yes_not_terminal(self) -> None:
        """Does not fire when on_yes routes to a non-terminal state."""
        fsm = self._harness_fsm(
            states={
                "score": make_state(
                    action_type="prompt",
                    action="Read the screenshot and evaluate.",
                    evaluate=EvaluateConfig(type="output_contains", pattern="PASS"),
                    on_yes="review",
                ),
                "review": make_state(action="echo check", on_yes="done"),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert errors == [], f"Expected no warnings when on_yes not terminal, got: {errors}"

    def test_does_not_fire_when_shell_action_intervenes(self) -> None:
        """Does not fire when a shell-action state sits between prompt and terminal."""
        fsm = self._harness_fsm(
            states={
                "score": make_state(
                    action_type="prompt",
                    action="Read the screenshot and evaluate.",
                    evaluate=EvaluateConfig(type="output_contains", pattern="PASS"),
                    on_yes="smoke_test",
                ),
                "smoke_test": make_state(
                    action_type="shell",
                    action="pytest smoke_test.py",
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert errors == [], f"Expected no warnings with shell state intervening, got: {errors}"

    def test_does_not_fire_with_non_output_contains_evaluator(self) -> None:
        """Does not fire when evaluator is not output_contains."""
        fsm = self._harness_fsm(
            states={
                "score": make_state(
                    action_type="prompt",
                    action="Read the screenshot and evaluate.",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert errors == [], f"Expected no warnings for non-output_contains, got: {errors}"

    def test_suppressed_by_meta_self_eval_ok(self) -> None:
        """meta_self_eval_ok: true suppresses the warning."""
        fsm = self._harness_fsm(meta_self_eval_ok=True)
        errors = _validate_harness_multimodal_evaluator_blind_spot(fsm)
        assert errors == [], f"meta_self_eval_ok should suppress warnings: {errors}"

    # --- integration ---

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes the multimodal evaluator warning."""
        fsm = self._harness_fsm()
        errors = validate_fsm(fsm)
        blind_spot_warnings = [
            e
            for e in errors
            if "multimodal" in e.message.lower() or "screenshot" in e.message.lower()
        ]
        assert len(blind_spot_warnings) == 1, (
            f"Expected one blind-spot warning in validate_fsm output, got: {blind_spot_warnings}"
        )



class TestArtifactVersioning:
    """MR-5 (ENH-1957): harness loops that overwrite artifacts without versioning."""

    def _iterative_harness_fsm(
        self,
        *,
        artifact_versioning: bool = False,
        artifact_versioning_ok: bool = False,
        category: str = "harness",
        with_loop: bool = False,
        non_iterative: bool = False,
    ) -> FSMLoop:
        """Build a minimal FSM for MR-5 testing.

        Default: iterative generate→evaluate→generate cycle with a flat artifact write.
        """
        if non_iterative:
            # Linear: no loop-back; generate → evaluate → done
            states = {
                "generate": make_state(
                    action="echo 'artifact' > ${context.run_dir}/output.svg",
                    action_type="shell",
                    next="evaluate",
                ),
                "evaluate": make_state(
                    action="Rate this output",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="done",
                ),
                "done": make_state(terminal=True),
            }
        elif with_loop:
            # Uses sub-loop delegation (no direct artifact writes)
            states = {
                "generate": make_state(
                    action="oracles/generator-evaluator",
                    action_type="loop",
                    on_yes="done",
                    on_no="generate",
                ),
                "done": make_state(terminal=True),
            }
        else:
            # Iterative: generate → evaluate → [generate]
            states = {
                "generate": make_state(
                    action="echo 'artifact' > ${context.run_dir}/output.svg",
                    action_type="shell",
                    next="evaluate",
                ),
                "evaluate": make_state(
                    action="Rate this output",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="generate",
                ),
                "done": make_state(terminal=True),
            }
        return FSMLoop(
            name="test-loop",
            initial="generate",
            states=states,
            category=category,
            artifact_versioning=artifact_versioning,
            artifact_versioning_ok=artifact_versioning_ok,
        )

    # --- MR-5 fires for iterative harness loops ---

    def test_mr5_fires_for_iterative_harness_with_flat_artifact(self) -> None:
        """MR-5 WARNING when harness loop overwrites artifact without versioning."""
        fsm = self._iterative_harness_fsm()
        errors = _validate_artifact_overwrite(fsm)
        assert len(errors) >= 1
        assert errors[0].severity == ValidationSeverity.WARNING

    # --- Suppression flags ---

    def test_mr5_suppressed_by_artifact_versioning_true(self) -> None:
        """MR-5 does NOT fire when artifact_versioning: true."""
        fsm = self._iterative_harness_fsm(artifact_versioning=True)
        errors = _validate_artifact_overwrite(fsm)
        assert errors == []

    def test_mr5_suppressed_by_artifact_versioning_ok_true(self) -> None:
        """MR-5 does NOT fire when artifact_versioning_ok: true."""
        fsm = self._iterative_harness_fsm(artifact_versioning_ok=True)
        errors = _validate_artifact_overwrite(fsm)
        assert errors == []

    # --- Non-iterative loops are exempt ---

    def test_mr5_does_not_fire_for_non_iterative_harness(self) -> None:
        """MR-5 does NOT fire for linear (non-iterative) harness loops."""
        fsm = self._iterative_harness_fsm(non_iterative=True)
        errors = _validate_artifact_overwrite(fsm)
        assert errors == []

    # --- Non-harness loops are exempt ---

    def test_mr5_does_not_fire_for_non_harness_category(self) -> None:
        """MR-5 does NOT fire for non-harness category loops."""
        fsm = self._iterative_harness_fsm(category="data")
        errors = _validate_artifact_overwrite(fsm)
        assert errors == []

    # --- Sub-loop delegation is exempt ---

    def test_mr5_does_not_fire_for_loop_delegation(self) -> None:
        """MR-5 does NOT fire when artifact work is delegated to a sub-loop."""
        fsm = self._iterative_harness_fsm(with_loop=True)
        errors = _validate_artifact_overwrite(fsm)
        assert errors == []

    # --- End-to-end: validate_fsm() wiring ---

    def test_mr5_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-5 warnings for iterative harness loops."""
        fsm = self._iterative_harness_fsm()
        errors = validate_fsm(fsm)
        mr5 = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING
            and "artifact" in e.message.lower()
            and "version" in e.message.lower()
        ]
        assert len(mr5) == 1

    # --- Top-level key recognition ---

    def test_artifact_versioning_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """YAML with top-level artifact_versioning produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that snapshots artifacts per iteration\n"
            "initial: work\n"
            "artifact_versioning: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []

    def test_artifact_versioning_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """YAML with top-level artifact_versioning_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally overwrites artifacts\n"
            "initial: work\n"
            "artifact_versioning_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []



class TestGeneratorFixDiscipline:
    """MR-6 (ENH-2079): meta-loops should not hand-patch LLM-generator artifacts."""

    def _mr6_fsm(
        self,
        *,
        generator_fix_ok: bool = False,
        same_path: bool = True,
        with_marker: bool = True,
        is_meta_loop: bool = True,
    ) -> FSMLoop:
        """Build a minimal FSM for MR-6 testing.

        Default: meta-loop with overlapping shell + generator paths (should trigger MR-6).
        """
        gen_path = "${context.run_dir}/output.yaml"
        shell_path = gen_path if same_path else "${context.run_dir}/other.txt"

        if with_marker:
            gen_action = f"Use yaml_state_editor to generate {gen_path} with the proposed changes."
        else:
            gen_action = f"Write the result to {gen_path} with the proposed changes."

        states = {
            "generate": make_state(
                action=gen_action,
                action_type="prompt",
                next="patch",
            ),
            "patch": make_state(
                action=f"echo patched > {shell_path}",
                action_type="shell",
                next="done",
            ),
            "done": make_state(terminal=True),
        }
        imports = ["lib/benchmark.yaml"] if is_meta_loop and not with_marker else []
        return FSMLoop(
            name="test-mr6",
            initial="generate",
            states=states,
            generator_fix_ok=generator_fix_ok,
            imports=imports,
        )

    def test_mr6_fires_when_shell_and_generator_write_same_path(self) -> None:
        """MR-6 WARNING fires when a shell state patches the same path as a generator state."""
        fsm = self._mr6_fsm()
        errors = _validate_generator_fix_discipline(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "ENH-2079" in errors[0].message

    def test_mr6_does_not_fire_when_no_path_overlap(self) -> None:
        """MR-6 does NOT fire when shell and generator states write to different paths."""
        fsm = self._mr6_fsm(same_path=False)
        errors = _validate_generator_fix_discipline(fsm)
        assert errors == []

    def test_mr6_does_not_fire_without_generator_marker(self) -> None:
        """MR-6 does NOT fire when the prompt state has no yaml_state_editor marker."""
        fsm = self._mr6_fsm(with_marker=False, is_meta_loop=True)
        errors = _validate_generator_fix_discipline(fsm)
        assert errors == []

    def test_mr6_suppressed_by_generator_fix_ok(self) -> None:
        """MR-6 does NOT fire when generator_fix_ok: true is set."""
        fsm = self._mr6_fsm(generator_fix_ok=True)
        errors = _validate_generator_fix_discipline(fsm)
        assert errors == []

    def test_mr6_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-6 warnings for hand-patching anti-pattern."""
        fsm = self._mr6_fsm()
        errors = validate_fsm(fsm)
        mr6 = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "ENH-2079" in e.message
        ]
        assert len(mr6) == 1


