"""Tests for FSM validation evaluator/pairing rule family (MR-8, MR-10, MR-12,
MR-13, haiku-gen, session-mode-eval, classify-route-default).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    PruningProfileConfig,
    StateConfig,
)
from little_loops.fsm.validation import (
    ValidationSeverity,
    _validate_abandonment_verdict,
    _validate_classify_route_default,
    _validate_haiku_pinned_generator,
    _validate_llm_evidence_contract,
    _validate_parse_swallow,
    _validate_pruning_profile,
    _validate_session_mode_evaluator_inheritance,
    _validate_terminal_action_ok,
    load_and_validate,
    validate_fsm,
)


def make_state(**kwargs) -> StateConfig:
    """Convenience constructor for StateConfig in tests."""
    return StateConfig(**kwargs)


BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"


class TestHaikuPinnedGenerator:
    """ENH-2713: haiku-pinned generator states get a WARN — no MR-1 backstop."""

    def _fsm(self, work_state: StateConfig, *, haiku_generator_ok: bool = False) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": work_state,
                "done": make_state(terminal=True),
            },
            haiku_generator_ok=haiku_generator_ok,
        )

    def test_fires_for_haiku_pinned_generator_state(self) -> None:
        """A prompt-action generator state (graded by a non-LLM evaluator, so its
        content is never quality-checked) pinned to haiku is flagged."""
        fsm = self._fsm(
            make_state(
                action="/ll:write-summary",
                action_type="prompt",
                model="claude-haiku-4-5-20251001",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="done",
                on_no="work",
            )
        )
        errors = _validate_haiku_pinned_generator(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert errors[0].path == "states.work.model"

    def test_does_not_fire_for_haiku_pinned_verdict_state(self) -> None:
        """An llm_structured verdict state pinned to haiku is not flagged."""
        fsm = self._fsm(
            make_state(
                action="run.sh",
                action_type="shell",
                model="claude-haiku-4-5-20251001",
                evaluate=EvaluateConfig(type="llm_structured"),
                on_yes="done",
                on_no="work",
            )
        )
        errors = _validate_haiku_pinned_generator(fsm)
        assert errors == []

    def test_does_not_fire_for_non_haiku_model(self) -> None:
        """A generator state pinned to a non-haiku model is not flagged."""
        fsm = self._fsm(
            make_state(
                action="/ll:write-summary",
                action_type="prompt",
                model="claude-opus-4-8",
                next="done",
            )
        )
        errors = _validate_haiku_pinned_generator(fsm)
        assert errors == []

    def test_does_not_fire_without_model(self) -> None:
        """A generator state with no model: override is not flagged."""
        fsm = self._fsm(make_state(action="/ll:write-summary", action_type="prompt", next="done"))
        errors = _validate_haiku_pinned_generator(fsm)
        assert errors == []

    def test_suppressed_by_haiku_generator_ok(self) -> None:
        """haiku_generator_ok: true suppresses the rule."""
        fsm = self._fsm(
            make_state(
                action="/ll:write-summary",
                action_type="prompt",
                model="claude-haiku-4-5-20251001",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="done",
                on_no="work",
            ),
            haiku_generator_ok=True,
        )
        errors = _validate_haiku_pinned_generator(fsm)
        assert errors == []

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes the haiku-pinned-generator WARN."""
        fsm = self._fsm(
            make_state(
                action="/ll:write-summary",
                action_type="prompt",
                model="claude-haiku-4-5-20251001",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="done",
                on_no="work",
            )
        )
        errors = validate_fsm(fsm)
        matches = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "(ENH-2713)" in e.message
        ]
        assert len(matches) == 1

    def test_haiku_generator_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level haiku_generator_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally pins haiku on a generator state\n"
            "initial: work\n"
            "haiku_generator_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: /ll:write-summary\n"
            "    action_type: prompt\n"
            "    model: claude-haiku-4-5-20251001\n"
            "    evaluate:\n"
            "      type: exit_code\n"
            "    on_yes: done\n"
            "    on_no: work\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []



class TestClassifyRouteDefault:
    """Classify-route-default WARNING check (ENH-2165)."""

    def _classify_fsm(
        self,
        *,
        with_default: bool = False,
        partial_route_ok: bool = False,
        with_route: bool = True,
    ) -> FSMLoop:
        from little_loops.fsm.schema import RouteConfig

        route: RouteConfig | None = None
        if with_route:
            route = RouteConfig(
                routes={"IMPLEMENT": "done", "WIRE": "done"},
                default="fallback" if with_default else None,
            )
        state_kwargs: dict = {
            "action": "classify.sh",
            "evaluate": EvaluateConfig(type="classify"),
        }
        if route is not None:
            state_kwargs["route"] = route
        return FSMLoop(
            name="test-loop",
            initial="classify",
            states={
                "classify": make_state(**state_kwargs),
                "done": make_state(terminal=True),
                "fallback": make_state(terminal=True),
            },
            partial_route_ok=partial_route_ok,
        )

    def test_warning_fires_when_default_absent(self) -> None:
        """WARNING fires for a classify state with a route: table and no default:."""
        fsm = self._classify_fsm(with_default=False)
        errors = _validate_classify_route_default(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "default" in errors[0].message

    def test_no_warning_when_default_present(self) -> None:
        """No warning when route: table has a default: entry."""
        fsm = self._classify_fsm(with_default=True)
        errors = _validate_classify_route_default(fsm)
        assert errors == []

    def test_no_warning_without_route_table(self) -> None:
        """No warning when classify state has no route: table at all."""
        fsm = self._classify_fsm(with_route=False)
        errors = _validate_classify_route_default(fsm)
        assert errors == []

    def test_suppressed_by_partial_route_ok(self) -> None:
        """partial_route_ok: true suppresses the classify-route-default warning."""
        fsm = self._classify_fsm(with_default=False, partial_route_ok=True)
        errors = _validate_classify_route_default(fsm)
        assert errors == []

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes the classify-route-default warning."""
        fsm = self._classify_fsm(with_default=False)
        errors = validate_fsm(fsm)
        classify_warnings = [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING and "classify route" in e.message
        ]
        assert len(classify_warnings) == 1

    def test_non_classify_state_not_flagged(self) -> None:
        """States with other evaluator types are not flagged by this check."""
        fsm = FSMLoop(
            name="test-loop",
            initial="check",
            states={
                "check": make_state(
                    action="check.sh",
                    evaluate=EvaluateConfig(type="output_contains", pattern="OK"),
                    on_yes="done",
                    on_no="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_classify_route_default(fsm)
        assert errors == []



class TestLLMEvidenceContractValidation:
    """ENH-2342: MR-8 validation rule for LLM evidence contract in check_semantic states."""

    def _simple_fsm(self, **kwargs) -> FSMLoop:
        defaults: dict = {
            "name": "test-evidence",
            "initial": "check",
            "states": {
                "check": make_state(terminal=True),
            },
        }
        defaults.update(kwargs)
        return FSMLoop(**defaults)

    # --- positive controls ---

    def test_mr8_fires_for_llm_state_missing_evidence_keywords(self) -> None:
        """MR-8 WARNING fires when llm_structured prompt has no evidence keywords."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        prompt="Did the task complete successfully? Answer yes or no.",
                    ),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_llm_evidence_contract(fsm)
        mr8_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "MR-8" in e.message
        ]
        assert len(mr8_warnings) == 1, f"Expected one MR-8 WARNING, got: {errors}"

    def test_mr8_does_not_fire_when_verbatim_present(self) -> None:
        """MR-8 does not fire when prompt contains 'verbatim'."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        prompt="Quote verbatim from the output to support your verdict.",
                    ),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            }
        )
        errors = _validate_llm_evidence_contract(fsm)
        mr8_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "MR-8" in e.message
        ]
        assert mr8_warnings == [], f"Unexpected MR-8 WARNING: {mr8_warnings}"

    def test_mr8_does_not_fire_when_evaluate_prompt_is_none(self) -> None:
        """MR-8 does not fire when evaluate.prompt is None — DEFAULT_LLM_PROMPT carries the contract."""
        fsm = self._simple_fsm(
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
        errors = _validate_llm_evidence_contract(fsm)
        mr8_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "MR-8" in e.message
        ]
        assert mr8_warnings == [], f"Unexpected MR-8 WARNING for None prompt: {mr8_warnings}"

    def test_mr8_does_not_fire_for_non_llm_evaluators(self) -> None:
        """MR-8 does not fire for exit_code evaluators."""
        fsm = self._simple_fsm(
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
        errors = _validate_llm_evidence_contract(fsm)
        mr8_warnings = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "MR-8" in e.message
        ]
        assert mr8_warnings == [], f"Unexpected MR-8 WARNING for exit_code: {mr8_warnings}"

    def test_mr8_suppressed_by_evidence_contract_ok(self) -> None:
        """evidence_contract_ok: true suppresses MR-8."""
        fsm = self._simple_fsm(
            evidence_contract_ok=True,
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        prompt="Did the task complete? No evidence required.",
                    ),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_llm_evidence_contract(fsm)
        assert errors == [], f"Unexpected errors with suppression flag: {errors}"

    def test_mr8_fires_end_to_end_via_validate_fsm(self) -> None:
        """MR-8 WARNING appears in validate_fsm() output (end-to-end wiring check)."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(
                    action="run.sh",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        prompt="Did the task complete? Answer yes or no.",
                    ),
                    on_yes="done",
                    on_no="check",
                ),
                "done": make_state(terminal=True),
            },
        )
        all_errors = validate_fsm(fsm)
        mr8_warnings = [
            e
            for e in all_errors
            if e.severity == ValidationSeverity.WARNING and "MR-8" in e.message
        ]
        assert len(mr8_warnings) >= 1, (
            f"MR-8 WARNING not found in validate_fsm output: {all_errors}"
        )


# ---------------------------------------------------------------------------
# MR-10 — parse-swallow detector
# ---------------------------------------------------------------------------

_SWALLOW_ACTION = """\
import json, sys
text = open("data.json").read()
try:
    data = json.loads(text)
except json.JSONDecodeError:
    sys.exit(0)
print(data)
"""

_SWALLOW_ACTION_VALUE_ERROR = """\
import json, sys
text = open("data.json").read()
try:
    data = json.loads(text)
except ValueError:
    exit(0)
print(data)
"""



class TestParseSwallow:
    """MR-10: shell state silently swallows a JSON parse failure with exit 0."""

    def _simple_fsm(
        self,
        action: str,
        *,
        action_type: str | None = "shell",
        on_error: str | None = None,
        parse_swallow_ok: bool = False,
    ) -> FSMLoop:
        state_kwargs: dict = {
            "action": action,
            "action_type": action_type,
            "on_yes": "done",
            "on_no": "work",
        }
        if on_error is not None:
            state_kwargs["on_error"] = on_error
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(**state_kwargs),
                "done": make_state(terminal=True),
            },
            parse_swallow_ok=parse_swallow_ok,
        )

    def test_mr10_fires_for_explicit_zero_exit(self) -> None:
        """MR-10 WARNING fires for json.loads + except JSONDecodeError + sys.exit(0)."""
        fsm = self._simple_fsm(_SWALLOW_ACTION)
        errors = _validate_parse_swallow(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert errors[0].path == "states.work.action"
        assert "MR-10" in errors[0].message

    def test_mr10_fires_for_value_error_variant(self) -> None:
        """MR-10 WARNING fires when ValueError is caught and exit(0) is used."""
        fsm = self._simple_fsm(_SWALLOW_ACTION_VALUE_ERROR)
        errors = _validate_parse_swallow(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING

    def test_mr10_clean_with_on_error_route(self) -> None:
        """MR-10 does not fire when on_error: is present on the state."""
        fsm = self._simple_fsm(_SWALLOW_ACTION, on_error="handle_error")
        errors = _validate_parse_swallow(fsm)
        assert errors == []

    def test_mr10_suppressed_by_parse_swallow_ok(self) -> None:
        """parse_swallow_ok: true suppresses MR-10."""
        fsm = self._simple_fsm(_SWALLOW_ACTION, parse_swallow_ok=True)
        errors = _validate_parse_swallow(fsm)
        assert errors == []

    def test_mr10_does_not_fire_without_json_parse_call(self) -> None:
        """MR-10 does not fire when there is no json.loads/json.load call."""
        action = "import sys\ntry:\n    pass\nexcept ValueError:\n    sys.exit(0)\n"
        fsm = self._simple_fsm(action)
        errors = _validate_parse_swallow(fsm)
        assert errors == []

    def test_mr10_does_not_fire_for_prompt_action(self) -> None:
        """MR-10 ignores prompt-type actions (only shell is relevant)."""
        fsm = self._simple_fsm(_SWALLOW_ACTION, action_type="prompt")
        errors = _validate_parse_swallow(fsm)
        assert errors == []

    def test_mr10_does_not_fire_without_except_clause(self) -> None:
        """MR-10 does not fire when there is no except clause catching the right exceptions."""
        action = "import json, sys\ndata = json.loads(open('f').read())\nsys.exit(0)\n"
        fsm = self._simple_fsm(action)
        errors = _validate_parse_swallow(fsm)
        assert errors == []

    def test_mr10_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-10 WARNING for parse-swallow pattern."""
        fsm = self._simple_fsm(_SWALLOW_ACTION)
        all_errors = validate_fsm(fsm)
        mr10 = [
            e
            for e in all_errors
            if e.severity == ValidationSeverity.WARNING and "(MR-10)" in e.message
        ]
        assert len(mr10) == 1

    def test_mr10_parse_swallow_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level parse_swallow_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: Intentionally swallows parse errors\n"
            "initial: work\n"
            "parse_swallow_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        from little_loops.fsm.validation import load_and_validate

        _, warnings = load_and_validate(loop_yaml, raise_on_error=False)
        unknown = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown == [], f"parse_swallow_ok flagged as unknown: {unknown}"



class TestSessionModeEvaluatorInheritance:
    """FEAT-2711: an evaluator state must not inherit session_mode: continue.

    Mirrors TestHaikuPinnedGenerator's _fsm()/suppression-flag pattern.
    """

    def _fsm(
        self,
        work_state: StateConfig,
        *,
        loop_session_mode: str | None = None,
        session_mode_ok: bool = False,
    ) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": work_state,
                "done": make_state(terminal=True),
            },
            session_mode=loop_session_mode,
            session_mode_ok=session_mode_ok,
        )

    def test_fires_for_evaluator_state_with_own_continue_override(self) -> None:
        """An llm_structured evaluator state overriding session_mode: continue is flagged."""
        fsm = self._fsm(
            make_state(
                action="run.sh",
                action_type="shell",
                evaluate=EvaluateConfig(type="llm_structured"),
                session_mode="continue",
                on_yes="done",
                on_no="work",
            )
        )
        errors = _validate_session_mode_evaluator_inheritance(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert errors[0].path == "states.work.session_mode"
        assert "(FEAT-2711)" in errors[0].message

    def test_fires_for_evaluator_state_inheriting_loop_default(self) -> None:
        """An evaluator state with no override inherits a loop-level continue default."""
        fsm = self._fsm(
            make_state(
                action="run.sh",
                action_type="shell",
                evaluate=EvaluateConfig(type="check_semantic"),
                on_yes="done",
                on_no="work",
            ),
            loop_session_mode="continue",
        )
        errors = _validate_session_mode_evaluator_inheritance(fsm)
        assert len(errors) == 1

    def test_does_not_fire_for_evaluator_state_forced_fresh(self) -> None:
        """An evaluator state that overrides session_mode: fresh is not flagged,
        even when the loop-level default is continue."""
        fsm = self._fsm(
            make_state(
                action="run.sh",
                action_type="shell",
                evaluate=EvaluateConfig(type="llm_structured"),
                session_mode="fresh",
                on_yes="done",
                on_no="work",
            ),
            loop_session_mode="continue",
        )
        errors = _validate_session_mode_evaluator_inheritance(fsm)
        assert errors == []

    def test_does_not_fire_for_non_evaluator_state(self) -> None:
        """A non-evaluator (exit_code-graded) state inheriting continue is not flagged."""
        fsm = self._fsm(
            make_state(
                action="run.sh",
                action_type="shell",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="done",
                on_no="work",
            ),
            loop_session_mode="continue",
        )
        errors = _validate_session_mode_evaluator_inheritance(fsm)
        assert errors == []

    def test_does_not_fire_when_default_fresh(self) -> None:
        """Default fresh (no session_mode set anywhere) never fires."""
        fsm = self._fsm(
            make_state(
                action="run.sh",
                action_type="shell",
                evaluate=EvaluateConfig(type="llm_structured"),
                on_yes="done",
                on_no="work",
            )
        )
        errors = _validate_session_mode_evaluator_inheritance(fsm)
        assert errors == []

    def test_suppressed_by_session_mode_ok(self) -> None:
        """session_mode_ok: true suppresses the rule."""
        fsm = self._fsm(
            make_state(
                action="run.sh",
                action_type="shell",
                evaluate=EvaluateConfig(type="llm_structured"),
                session_mode="continue",
                on_yes="done",
                on_no="work",
            ),
            session_mode_ok=True,
        )
        errors = _validate_session_mode_evaluator_inheritance(fsm)
        assert errors == []

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes the FEAT-2711 WARNING for evaluator inheritance."""
        fsm = self._fsm(
            make_state(
                action="run.sh",
                action_type="shell",
                evaluate=EvaluateConfig(type="llm_structured"),
                session_mode="continue",
                on_yes="done",
                on_no="work",
            )
        )
        all_errors = validate_fsm(fsm)
        matches = [
            e
            for e in all_errors
            if e.severity == ValidationSeverity.WARNING and "(FEAT-2711)" in e.message
        ]
        assert len(matches) == 1

    def test_session_mode_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level session_mode/session_mode_ok produces no
        Unknown-top-level-key warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: Continuity-chain smoke test\n"
            "initial: work\n"
            "session_mode: continue\n"
            "session_mode_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "    on_no: work\n"
            "  done:\n"
            "    terminal: true\n",
            encoding="utf-8",
        )
        fsm, errors = load_and_validate(loop_yaml)
        assert fsm is not None
        unknown_key_errors = [e for e in errors if "Unknown top-level" in e.message]
        assert unknown_key_errors == []



class TestPruningProfileCoverageValidation:
    """ENH-2805: MR-12 coverage-ranking check — a skill/command-invoking state

    with no resolvable ``pruning_profile`` (state override or loop default)
    is flagged WARNING. Modeled on TestLLMEvidenceContractValidation (MR-8).
    """

    def _simple_fsm(self, **kwargs) -> FSMLoop:
        defaults: dict = {
            "name": "test-pruning-coverage",
            "initial": "check",
            "states": {
                "check": make_state(terminal=True),
            },
        }
        defaults.update(kwargs)
        return FSMLoop(**defaults)

    def _mr12_coverage_warnings(self, errors: list) -> list:
        return [
            e
            for e in errors
            if e.severity == ValidationSeverity.WARNING
            and "ENH-2805" in e.message
            and "no resolvable pruning_profile" in e.message
        ]

    # --- positive control ---

    def test_fires_for_skill_state_with_no_pruning_profile(self) -> None:
        """WARNING fires when a /ll:<skill> state has no state or loop default profile."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    next="done",
                ),
                "done": make_state(terminal=True),
            }
        )
        warnings = self._mr12_coverage_warnings(_validate_pruning_profile(fsm))
        assert len(warnings) == 1, f"Expected one MR-12 coverage WARNING, got: {warnings}"

    # --- negative control ---

    def test_does_not_fire_when_state_pruning_profile_set(self) -> None:
        """No WARNING when the state itself declares a pruning_profile."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    pruning_profile=PruningProfileConfig(enabled=True),
                    next="done",
                ),
                "done": make_state(terminal=True),
            }
        )
        warnings = self._mr12_coverage_warnings(_validate_pruning_profile(fsm))
        assert warnings == [], f"Unexpected MR-12 coverage WARNING: {warnings}"

    def test_does_not_fire_when_loop_default_pruning_profile_set(self) -> None:
        """No WARNING when the loop-level default pruning_profile covers the state."""
        fsm = self._simple_fsm(
            pruning_profile=PruningProfileConfig(enabled=True),
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    next="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        warnings = self._mr12_coverage_warnings(_validate_pruning_profile(fsm))
        assert warnings == [], f"Unexpected MR-12 coverage WARNING: {warnings}"

    # --- suppress-flag-honored ---

    def test_suppressed_by_pruning_profile_ok(self) -> None:
        """pruning_profile_ok: true suppresses the coverage WARNING."""
        fsm = self._simple_fsm(
            pruning_profile_ok=True,
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    next="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_pruning_profile(fsm)
        assert errors == [], f"Unexpected errors with suppression flag: {errors}"

    # --- sdk/batch exemption (BUG-2831: narrowed to no longer apply to
    # skill-invoking states — the executor now force-downgrades those to
    # cli at runtime, so they genuinely reach action_runner and need
    # pruning guidance same as any other skill-invoking state) ---

    def test_fires_for_sdk_request_path_state_invoking_skill(self) -> None:
        """BUG-2831: a skill-invoking request_path: sdk state now warns — it's
        force-downgraded to cli at runtime and genuinely needs pruning."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    request_path="sdk",
                    next="done",
                ),
                "done": make_state(terminal=True),
            }
        )
        warnings = self._mr12_coverage_warnings(_validate_pruning_profile(fsm))
        assert len(warnings) == 1, f"Expected one MR-12 coverage WARNING, got: {warnings}"

    def test_fires_for_batch_request_path_state_invoking_skill(self) -> None:
        """BUG-2831: a skill-invoking request_path: batch state now warns — it's
        force-downgraded to cli at runtime and genuinely needs pruning."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    request_path="batch",
                    next="done",
                ),
                "done": make_state(terminal=True),
            }
        )
        warnings = self._mr12_coverage_warnings(_validate_pruning_profile(fsm))
        assert len(warnings) == 1, f"Expected one MR-12 coverage WARNING, got: {warnings}"

    # --- config-level request_path (ENH-2810) ---

    def test_fires_when_orchestration_request_path_sdk_invoking_skill(self) -> None:
        """BUG-2831: no state-level request_path, orchestration config default is
        sdk — still warns, since the skill-invoking state is force-downgraded
        to cli at runtime and genuinely needs pruning."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    next="done",
                ),
                "done": make_state(terminal=True),
            }
        )
        warnings = self._mr12_coverage_warnings(
            _validate_pruning_profile(fsm, orchestration_request_path="sdk")
        )
        assert len(warnings) == 1, (
            f"Expected one MR-12 coverage WARNING under config sdk: {warnings}"
        )

    def test_still_fires_when_orchestration_request_path_cli(self) -> None:
        """No state-level request_path, orchestration config default is cli — still warns."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    next="done",
                ),
                "done": make_state(terminal=True),
            }
        )
        warnings = self._mr12_coverage_warnings(
            _validate_pruning_profile(fsm, orchestration_request_path="cli")
        )
        assert len(warnings) == 1, f"Expected one MR-12 coverage WARNING, got: {warnings}"

    def test_still_fires_when_orchestration_request_path_unset(self) -> None:
        """orchestration_request_path=None (default) preserves current no-exemption behavior."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    next="done",
                ),
                "done": make_state(terminal=True),
            }
        )
        warnings = self._mr12_coverage_warnings(_validate_pruning_profile(fsm))
        assert len(warnings) == 1, f"Expected one MR-12 coverage WARNING, got: {warnings}"

    def test_state_level_cli_override_still_warns_under_config_sdk(self) -> None:
        """A state's explicit request_path: cli overrides a config-level sdk default."""
        fsm = self._simple_fsm(
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    request_path="cli",
                    next="done",
                ),
                "done": make_state(terminal=True),
            }
        )
        warnings = self._mr12_coverage_warnings(
            _validate_pruning_profile(fsm, orchestration_request_path="sdk")
        )
        assert len(warnings) == 1, (
            f"Expected explicit state request_path: cli to still warn under config sdk: {warnings}"
        )

    def test_config_request_path_sdk_via_validate_fsm_still_fires(self) -> None:
        """BUG-2831: validate_fsm() threads orchestration_request_path through to
        Check 3, but a skill-invoking sdk state still warns (no exemption)."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    next="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        warnings = self._mr12_coverage_warnings(validate_fsm(fsm, orchestration_request_path="sdk"))
        assert len(warnings) == 1, (
            f"Expected one MR-12 coverage WARNING under config sdk: {warnings}"
        )

    # --- end-to-end via validate_fsm() ---

    def test_fires_end_to_end_via_validate_fsm(self) -> None:
        """MR-12 coverage WARNING appears in validate_fsm() output (end-to-end wiring check)."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(
                    action="/ll:confidence-check ${captured.input.output}",
                    action_type="slash_command",
                    next="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        all_errors = validate_fsm(fsm)
        warnings = self._mr12_coverage_warnings(all_errors)
        assert len(warnings) == 1, f"Expected one MR-12 coverage WARNING, got: {warnings}"



class TestTerminalActionOk:
    """BUG-2813: non-empty `action` on a `terminal: true` state is dead code."""

    def _simple_fsm(self, *, terminal_action_ok: bool = False) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(action="run.sh", on_yes="done", on_no="work"),
                "done": make_state(action="echo done summary", terminal=True),
            },
            terminal_action_ok=terminal_action_ok,
        )

    def test_fires_for_terminal_with_action(self) -> None:
        """A terminal state with a non-empty action produces a finding."""
        fsm = self._simple_fsm()
        errors = _validate_terminal_action_ok(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "done" in errors[0].message
        assert errors[0].path == "states.done.action"

    def test_does_not_fire_for_bare_terminal(self) -> None:
        """A terminal state with no action produces no finding."""
        fsm = FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(action="run.sh", on_yes="done", on_no="work"),
                "done": make_state(terminal=True),
            },
        )
        errors = _validate_terminal_action_ok(fsm)
        assert errors == []

    def test_suppressed_by_terminal_action_ok(self) -> None:
        """terminal_action_ok: true suppresses the rule."""
        fsm = self._simple_fsm(terminal_action_ok=True)
        errors = _validate_terminal_action_ok(fsm)
        assert errors == []

    def test_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes the terminal-action-ok finding."""
        fsm = self._simple_fsm()
        errors = validate_fsm(fsm)
        matches = [e for e in errors if "BUG-2813" in e.message]
        assert len(matches) == 1

    def test_terminal_action_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level terminal_action_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally keeps a terminal action\n"
            "initial: work\n"
            "terminal_action_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    action: echo done summary\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []

    def test_does_not_fire_for_on_max_steps_handler_terminal(self) -> None:
        """A terminal doubling as the on_max_steps handler is exempt (BUG-158)."""
        fsm = FSMLoop(
            name="test-loop",
            initial="work",
            on_max_steps="capped",
            states={
                "work": make_state(action="run.sh", on_yes="done", on_no="work"),
                "done": make_state(terminal=True),
                "capped": make_state(action="echo capped summary", terminal=True),
            },
        )
        errors = _validate_terminal_action_ok(fsm)
        assert errors == []



class TestAbandonmentVerdict:
    """MR-13: abandonment mechanism must emit an "abandoned" key; a hardcoded
    "verdict":"success" must be guarded by an abandonment/failure counter."""

    def _simple_fsm(self, states: dict, **kwargs) -> FSMLoop:
        defaults: dict = {
            "name": "test-loop",
            "initial": "work",
            "states": states,
        }
        defaults.update(kwargs)
        return FSMLoop(**defaults)

    def test_mr13_fires_for_mechanism_without_abandoned_key(self) -> None:
        """MR-13 fires when a checkbox-abandonment mechanism exists but no
        state emits an "abandoned" key into the summary JSON."""
        fsm = self._simple_fsm(
            {
                "select_step": make_state(
                    action=(
                        "awk 'sub(/^- \\[ \\]/, \"- [!]\")' plan.md > plan.tmp && "
                        "mv plan.tmp plan.md"
                    ),
                    action_type="shell",
                    on_yes="done",
                ),
                "done": make_state(
                    action='printf \'{"verdict":"%s"}\\n\' "$V"',
                    action_type="shell",
                    terminal=True,
                ),
            }
        )
        errors = _validate_abandonment_verdict(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "MR-13" in errors[0].message

    def test_mr13_fires_for_attempt_cap_mechanism_without_abandoned_key(self) -> None:
        """MR-13 also detects the max_step_attempts-style attempt-cap heuristic."""
        fsm = self._simple_fsm(
            {
                "select_step": make_state(
                    action='PRIOR=$(cat attempts.txt); '
                    'if [ "$PRIOR" -ge "${context.max_step_attempts}" ]; then echo cap; fi',
                    action_type="shell",
                    on_yes="done",
                ),
                "done": make_state(action="echo done", action_type="shell", terminal=True),
            }
        )
        errors = _validate_abandonment_verdict(fsm)
        assert len(errors) == 1
        assert "MR-13" in errors[0].message

    def test_mr13_clean_when_mechanism_emits_abandoned_key(self) -> None:
        """MR-13 does not fire when a state emits the "abandoned" key (the
        general-task.yaml post-ENH-2857 shape)."""
        fsm = self._simple_fsm(
            {
                "select_step": make_state(
                    action="awk 'sub(/^- \\[ \\]/, \"- [!]\")' plan.md",
                    action_type="shell",
                    on_yes="summarize",
                ),
                "summarize": make_state(
                    action=(
                        'printf \'{"verdict":"%s","abandoned":%s}\\n\' "$VERDICT" "$ABANDONED"'
                    ),
                    action_type="shell",
                    terminal=True,
                ),
            }
        )
        errors = _validate_abandonment_verdict(fsm)
        assert errors == []

    def test_mr13_fires_for_hardcoded_success_verdict_without_guard(self) -> None:
        """MR-13 fires on a hardcoded "verdict":"success" with no abandonment guard."""
        fsm = self._simple_fsm(
            {
                "summarize": make_state(
                    action='printf \'{"verdict":"success"}\\n\' > summary.json',
                    action_type="shell",
                    terminal=True,
                ),
            }
        )
        errors = _validate_abandonment_verdict(fsm)
        assert len(errors) == 1
        assert "MR-13" in errors[0].message

    def test_mr13_clean_for_hardcoded_success_guarded_by_abandoned_counter(self) -> None:
        """MR-13 does not fire on a literal verdict=success guarded by an
        abandonment counter branch (the auto-refine-and-implement.yaml shape)."""
        fsm = self._simple_fsm(
            {
                "finalize": make_state(
                    action=(
                        'ABANDONED=$(count abandoned.txt); '
                        'if [ "$ABANDONED" -gt 0 ]; then VERDICT=incomplete-abandoned; '
                        "else VERDICT=success; fi; "
                        'printf \'{"verdict":"%s","abandoned":%s}\\n\' "$VERDICT" "$ABANDONED"'
                    ),
                    action_type="shell",
                    terminal=True,
                ),
            }
        )
        errors = _validate_abandonment_verdict(fsm)
        assert errors == []

    def test_mr13_suppressed_by_abandonment_verdict_ok(self) -> None:
        """abandonment_verdict_ok: true suppresses both MR-13 sub-checks."""
        fsm = self._simple_fsm(
            {
                "select_step": make_state(
                    action="awk 'sub(/^- \\[ \\]/, \"- [!]\")' plan.md",
                    action_type="shell",
                    on_yes="summarize",
                ),
                "summarize": make_state(
                    action='printf \'{"verdict":"success"}\\n\'',
                    action_type="shell",
                    terminal=True,
                ),
            },
            abandonment_verdict_ok=True,
        )
        errors = _validate_abandonment_verdict(fsm)
        assert errors == []

    def test_mr13_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-13 WARNING for a hardcoded success verdict."""
        fsm = self._simple_fsm(
            {
                "summarize": make_state(
                    action='printf \'{"verdict":"success"}\\n\'',
                    action_type="shell",
                    terminal=True,
                ),
            }
        )
        all_errors = validate_fsm(fsm)
        mr13 = [
            e
            for e in all_errors
            if e.severity == ValidationSeverity.WARNING and "(MR-13)" in e.message
        ]
        assert len(mr13) == 1

    def test_mr13_abandonment_verdict_ok_recognized_as_top_level_key(
        self, tmp_path: Path
    ) -> None:
        """A YAML with top-level abandonment_verdict_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: Intentionally hardcodes a success verdict\n"
            "initial: work\n"
            "abandonment_verdict_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml, raise_on_error=False)
        unknown = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown == [], f"abandonment_verdict_ok flagged as unknown: {unknown}"

    def test_mr13_general_task_yaml_passes_clean(self) -> None:
        """general-task.yaml (post-ENH-2857) triggers no MR-13 warnings."""
        loop_path = BUILTIN_LOOPS_DIR / "general-task.yaml"
        if not loop_path.exists():
            pytest.skip("general-task.yaml not found in builtin loops")
        fsm, _ = load_and_validate(loop_path)
        errors = _validate_abandonment_verdict(fsm)
        assert errors == [], f"general-task.yaml triggered MR-13: {errors}"

    def test_enh2858_general_task_yaml_validates_with_no_errors(self) -> None:
        """general-task.yaml (post-ENH-2858 marker-grep gate) has no ERROR-severity
        validation issues — the new check_provisional_markers shell state must be
        MR-3/MR-7/MR-9/MR-11 clean (bash escaping, run_dir artifact isolation, no
        unsafe interpolation)."""
        loop_path = BUILTIN_LOOPS_DIR / "general-task.yaml"
        if not loop_path.exists():
            pytest.skip("general-task.yaml not found in builtin loops")
        _, violations = load_and_validate(loop_path, raise_on_error=False)
        errors = [v for v in violations if v.severity == ValidationSeverity.ERROR]
        assert errors == [], f"general-task.yaml has validation errors: {errors}"

    def test_mr13_auto_refine_and_implement_yaml_passes_clean(self) -> None:
        """auto-refine-and-implement.yaml (the ENH-2657 reference shape) triggers no MR-13 warnings."""
        loop_path = BUILTIN_LOOPS_DIR / "auto-refine-and-implement.yaml"
        if not loop_path.exists():
            pytest.skip("auto-refine-and-implement.yaml not found in builtin loops")
        fsm, _ = load_and_validate(loop_path)
        errors = _validate_abandonment_verdict(fsm)
        assert errors == [], f"auto-refine-and-implement.yaml triggered MR-13: {errors}"
