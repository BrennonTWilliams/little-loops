"""Tests for ENH-3527/ENH-3547: model_hint declarations, resolver, config, and dispatch wiring."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.verify_host_map import _check_hint_backend_coverage
from little_loops.config.core import deep_merge
from little_loops.config.orchestration import OrchestrationConfig
from little_loops.fsm.evaluators import EvaluationResult
from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.persistence import LoopState, PersistentExecutor, StatePersistence
from little_loops.fsm.schema import (
    DEFAULT_LLM_MODEL,
    EvaluateConfig,
    FSMLoop,
    LearningConfig,
    LLMConfig,
    StateConfig,
)
from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm
from little_loops.host_runner import (
    _HOST_RUNNER_REGISTRY,
    MODEL_ALIASES,
    MODEL_HINTS,
    RUNTIME_HOST_CAPABILITIES,
    TEST_ONLY_HOSTS,
    FakeHostRunner,
    FakeMinimalHostRunner,
    ModelHintError,
    resolve_host,
    resolve_model_hint,
)
from tests.test_fsm_executor import MockActionRunner

BACKENDS = sorted(set(RUNTIME_HOST_CAPABILITIES) | TEST_ONLY_HOSTS | {"anthropic-api"})


def _fsm(state: StateConfig, **kw: Any) -> FSMLoop:
    return FSMLoop(
        name="t",
        initial="s",
        states={"s": state, "done": StateConfig(terminal=True)},
        **kw,
    )


def _errors(fsm: FSMLoop, severity: ValidationSeverity = ValidationSeverity.ERROR) -> list[str]:
    return [e.message for e in validate_fsm(fsm) if e.severity == severity]


class TestResolver:
    @pytest.mark.parametrize("hint", MODEL_HINTS)
    def test_claude_code_builtin(self, hint: str) -> None:
        expected = {"coding": "sonnet", "reasoning": "opus", "burst": "haiku"}[hint]
        assert resolve_model_hint(hint, backend="claude-code") == expected

    @pytest.mark.parametrize(
        "hint,alias", [("coding", "sonnet"), ("reasoning", "opus"), ("burst", "haiku")]
    )
    def test_anthropic_api_derives_from_aliases(self, hint: str, alias: str) -> None:
        assert resolve_model_hint(hint, backend="anthropic-api") == MODEL_ALIASES[alias]

    @pytest.mark.parametrize("backend", sorted(TEST_ONLY_HOSTS))
    @pytest.mark.parametrize("hint", MODEL_HINTS)
    def test_fake_hosts_distinct_sentinels(self, backend: str, hint: str) -> None:
        assert resolve_model_hint(hint, backend=backend) == f"fake-{hint}"

    @pytest.mark.parametrize("backend", ["codex", "gemini", "omp", "kimi-code", "qwen"])
    def test_config_only_hosts_error_without_mapping(self, backend: str) -> None:
        with pytest.raises(ModelHintError, match=f"coding.*{backend}"):
            resolve_model_hint("coding", backend=backend)

    def test_codex_config_mapping(self) -> None:
        got = resolve_model_hint(
            "coding", backend="codex", overrides={"codex": {"coding": "gpt-x"}}
        )
        assert got == "gpt-x"

    @pytest.mark.parametrize("backend", ["opencode", "pi"])
    def test_unsupported_backends_error_even_with_config(self, backend: str) -> None:
        with pytest.raises(ModelHintError, match="not supported"):
            resolve_model_hint("coding", backend=backend, overrides={backend: {"coding": "m"}})

    def test_per_hint_merge_over_defaults(self) -> None:
        ov: dict[str, Any] = {"claude-code": {"burst": "sonnet"}}
        assert resolve_model_hint("burst", backend="claude-code", overrides=ov) == "sonnet"
        assert resolve_model_hint("reasoning", backend="claude-code", overrides=ov) == "opus"

    def test_false_disables_builtin(self) -> None:
        ov: dict[str, Any] = {"claude-code": {"burst": False}}
        with pytest.raises(ModelHintError, match="disabled"):
            resolve_model_hint("burst", backend="claude-code", overrides=ov)

    def test_anthropic_api_override_alias_resolved(self) -> None:
        ov: dict[str, Any] = {"anthropic-api": {"coding": "opus"}}
        assert (
            resolve_model_hint("coding", backend="anthropic-api", overrides=ov)
            == MODEL_ALIASES["opus"]
        )

    def test_unknown_hint_and_backend(self) -> None:
        with pytest.raises(ModelHintError):
            resolve_model_hint("fast", backend="claude-code")
        with pytest.raises(ModelHintError):
            resolve_model_hint("coding", backend="nope")

    @pytest.mark.parametrize("backend", BACKENDS)
    @pytest.mark.parametrize("hint", MODEL_HINTS)
    def test_never_returns_none(self, backend: str, hint: str) -> None:
        try:
            result = resolve_model_hint(hint, backend=backend)
        except ModelHintError:
            return
        assert isinstance(result, str) and result

    def test_verify_host_map_hint_coverage_clean(self) -> None:
        assert _check_hint_backend_coverage() == []
        assert set(_HOST_RUNNER_REGISTRY) <= set(BACKENDS)


class TestModelHintsConfig:
    def test_default_empty(self) -> None:
        assert OrchestrationConfig.from_dict({}).model_hints == {}

    def test_accepts_valid_and_fake_keys(self) -> None:
        cfg = OrchestrationConfig.from_dict(
            {
                "model_hints": {
                    "codex": {"coding": "m"},
                    "fake": {"burst": False},
                    "fake-minimal": {},
                }
            }
        )
        assert cfg.model_hints["codex"] == {"coding": "m"}
        assert cfg.model_hints["fake"] == {"burst": False}

    @pytest.mark.parametrize(
        "bad",
        [
            {"nope": {"coding": "m"}},
            {"codex": {"fast": "m"}},
            {"codex": "m"},
            {"codex": {"coding": None}},
            {"codex": {"coding": True}},
            {"codex": {"coding": ""}},
        ],
    )
    def test_invalid_raises(self, bad: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="model_hints"):
            OrchestrationConfig.from_dict({"model_hints": bad})

    def test_local_md_null_unsets_base_value(self) -> None:
        base = {"orchestration": {"model_hints": {"claude-code": {"burst": "sonnet"}}}}
        merged = deep_merge(
            base, {"orchestration": {"model_hints": {"claude-code": {"burst": None}}}}
        )
        cfg = OrchestrationConfig.from_dict(merged["orchestration"])
        assert (
            resolve_model_hint("burst", backend="claude-code", overrides=cfg.model_hints) == "haiku"
        )

    def test_local_md_false_disables_builtin(self) -> None:
        merged = deep_merge(
            {"orchestration": {}},
            {"orchestration": {"model_hints": {"claude-code": {"burst": False}}}},
        )
        cfg = OrchestrationConfig.from_dict(merged["orchestration"])
        with pytest.raises(ModelHintError):
            resolve_model_hint("burst", backend="claude-code", overrides=cfg.model_hints)

    def test_config_schema_declares_model_hints(self) -> None:
        schema = json.loads(
            (Path(__file__).parent.parent / "little_loops" / "config-schema.json").read_text()
        )
        props = schema["properties"]["orchestration"]["properties"]["model_hints"]
        assert props["additionalProperties"]["additionalProperties"] is False
        assert set(props["propertyNames"]["enum"]) == set(BACKENDS)


class TestSchemaRoundTrip:
    def test_state_hint_round_trip(self) -> None:
        st = StateConfig.from_dict(
            {"action": "do it", "action_type": "prompt", "model_hint": "burst"}
        )
        assert st.model_hint == "burst" and st.model is None
        assert st.to_dict()["model_hint"] == "burst"
        assert "model_hint" not in StateConfig(action="x").to_dict()

    def test_llm_omitted_literal_hint_only(self) -> None:
        assert LLMConfig.from_dict({}).model == DEFAULT_LLM_MODEL
        assert LLMConfig.from_dict({}).model_hint is None
        assert LLMConfig.from_dict({"model": "opus"}).to_dict() == {"model": "opus"}
        hinted = LLMConfig.from_dict({"model_hint": "reasoning"})
        assert hinted.to_dict() == {"model_hint": "reasoning"}
        assert LLMConfig.from_dict(hinted.to_dict()).to_dict() == {"model_hint": "reasoning"}

    def test_llm_model_plus_hint_raises(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            LLMConfig.from_dict({"model": "opus", "model_hint": "coding"})

    def test_json_schema_has_no_stale_llm_model_default(self) -> None:
        schema = json.loads(
            (
                Path(__file__).parent.parent / "little_loops" / "fsm" / "fsm-loop-schema.json"
            ).read_text()
        )
        llm = schema["definitions"]["llmConfig"]["properties"]
        assert "default" not in llm["model"]
        assert "DEFAULT_LLM_MODEL" in llm["model"]["description"]
        assert llm["model_hint"]["enum"] == list(MODEL_HINTS)
        state = schema["definitions"]["stateConfig"]["properties"]
        assert state["model_hint"]["enum"] == list(MODEL_HINTS)


class TestStructuralValidation:
    def test_valid_prompt_and_slash_and_implicit(self) -> None:
        for st in (
            StateConfig(action="x", action_type="prompt", model_hint="coding", on_yes="done"),
            StateConfig(
                action="x", action_type="slash_command", model_hint="coding", on_yes="done"
            ),
            StateConfig(action="/ll:x", model_hint="coding", on_yes="done"),
        ):
            assert not [m for m in _errors(_fsm(st)) if "model_hint" in m]

    def test_shell_with_llm_structured_valid(self) -> None:
        st = StateConfig(
            action="echo hi",
            action_type="shell",
            model_hint="burst",
            evaluate=EvaluateConfig(type="llm_structured", prompt="ok?"),
            on_yes="done",
            on_no="done",
        )
        assert not [m for m in _errors(_fsm(st)) if "model_hint" in m]

    @pytest.mark.parametrize("etype", ["contract", "advisor_consult", None])
    def test_inapplicable_state_is_error(self, etype: str | None) -> None:
        ev = EvaluateConfig(type=etype) if etype else None
        st = StateConfig(
            action="echo hi",
            action_type="shell",
            model_hint="coding",
            evaluate=ev,
            on_yes="done",
            on_no="done",
        )
        assert any("never consumes a model" in m for m in _errors(_fsm(st)))

    def test_invalid_vocabulary_and_exclusivity(self) -> None:
        st = StateConfig(
            action="x", action_type="prompt", model_hint="fast", model="opus", on_yes="done"
        )
        msgs = _errors(_fsm(st))
        assert any("must be one of" in m for m in msgs)
        assert any("mutually exclusive" in m for m in msgs)

    def test_llm_hint_invalid_and_no_llm_states_warning(self) -> None:
        shell = StateConfig(action="echo", action_type="shell", on_yes="done", on_no="done")
        fsm = _fsm(shell, llm=LLMConfig(model_hint="coding"))
        assert any(
            "no state consumes a model" in m for m in _errors(fsm, ValidationSeverity.WARNING)
        )
        assert not [m for m in _errors(fsm) if "llm.model_hint" in m]
        bad = _fsm(shell, llm=LLMConfig(model_hint="fast"))
        assert any("llm.model_hint must be one of" in m for m in _errors(bad))


@dataclass
class ModelRunner(MockActionRunner):
    """MockActionRunner that records the ``model`` each dispatch received."""

    models: list[str | None] = field(default_factory=list)

    def run(self, action: str, timeout: int, is_slash_command: bool, **kw: Any) -> Any:
        self.models.append(kw.get("model"))
        return super().run(action, timeout, is_slash_command, **kw)


@dataclass
class ArgvRunner(ModelRunner):
    """Builds the active host's real streaming argv for each prompt dispatch."""

    argv: list[list[str]] = field(default_factory=list)

    def run(self, action: str, timeout: int, is_slash_command: bool, **kw: Any) -> Any:
        if is_slash_command:
            inv = resolve_host().build_streaming(prompt=action, model=kw.get("model"))
            self.argv.append(list(inv.args))
        return super().run(action, timeout, is_slash_command, **kw)


def _model_after_flag(args: list[str]) -> str:
    return args[args.index("--model") + 1]


_SELECTION_KEYS = ("model_requested", "model_resolved", "model_backend")


def _prompt(**kw: Any) -> StateConfig:
    """A prompt state that consumes no evaluator model (output_contains)."""
    kw.setdefault("on_yes", "done")
    kw.setdefault("on_no", "done")
    return StateConfig(
        action=kw.pop("action", "do it"),
        action_type="prompt",
        evaluate=EvaluateConfig(type="output_contains", pattern=""),
        **kw,
    )


def _execute(
    fsm: FSMLoop, runner: MockActionRunner | None = None, **kw: Any
) -> tuple[Any, MockActionRunner, list[dict[str, Any]]]:
    runner = runner if runner is not None else ModelRunner()
    events: list[dict[str, Any]] = []
    ex = FSMExecutor(fsm, action_runner=runner, event_callback=events.append, **kw)
    return ex.run(), runner, events


def _of(events: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [e for e in events if e["event"] == name]


class _EvalSpy:
    """Stands in for evaluate_llm_structured and records the model it received."""

    def __init__(self) -> None:
        self.models: list[str] = []

    def __call__(self, *args: Any, model: str = "", **kw: Any) -> EvaluationResult:
        self.models.append(model)
        return EvaluationResult(verdict="yes", details={"llm_model": model})


@pytest.fixture
def eval_spy() -> Any:
    spy = _EvalSpy()
    with (
        patch("little_loops.fsm.executor.evaluate_llm_structured", side_effect=spy),
        patch("little_loops.fsm.evaluators.evaluate_llm_structured", side_effect=spy),
    ):
        yield spy


@pytest.fixture
def no_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LL_HOST_CLI", raising=False)
    monkeypatch.delenv("LL_HOOK_HOST", raising=False)
    monkeypatch.setattr("little_loops.host_runner.shutil.which", lambda _b: None)


def _sdk_env(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Make the sdk path live and return the mocked SDK client."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        model="m",
        usage=SimpleNamespace(
            input_tokens=1,
            output_tokens=1,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )
    return client


class TestPreflight:
    """ENH-3547 run-start preflight (AC11, AC15, AC18, AC19)."""

    def test_unmapped_state_hint_fails_before_any_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "codex")
        fsm = FSMLoop(
            name="t",
            initial="pre",
            states={
                "pre": StateConfig(action="echo pre", action_type="shell", next="hinted"),
                "hinted": _prompt(model_hint="coding"),
                "done": StateConfig(terminal=True),
            },
        )
        result, runner, events = _execute(fsm)
        assert result.terminated_by == "error"
        assert result.model_hint_error is True
        assert "'coding'" in (result.error or "") and "codex" in (result.error or "")
        assert runner.calls == []
        assert _of(events, "loop_start")
        assert not _of(events, "request_path_downgrade")

    def test_host_not_configured_fails_preflight(self, no_host: None) -> None:
        result, runner, _ = _execute(_fsm(_prompt(model_hint="burst")))
        assert result.terminated_by == "error" and result.model_hint_error
        assert "'burst'" in (result.error or "")
        assert "no host CLI was found" in (result.error or "")
        assert runner.calls == []

    def test_preflight_emits_no_downgrade_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from little_loops.config.orchestration import OrchestrationConfig

        monkeypatch.setenv("LL_HOST_CLI", "codex")
        monkeypatch.setattr(FSMExecutor, "_sdk_credentials_available", staticmethod(lambda: False))
        result, runner, events = _execute(
            _fsm(_prompt(model_hint="coding")),
            orchestration_config=OrchestrationConfig(request_path="sdk"),
        )
        # Downgraded to cli, where codex has no mapping — but no warning at run start.
        assert result.terminated_by == "error" and "codex" in (result.error or "")
        assert not _of(events, "request_path_downgrade")
        assert runner.calls == []

    def test_unconsumed_llm_hint_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Flipped from the ENH-3527 guard: shell + exit_code never resolves llm.model_hint."""
        monkeypatch.setenv("LL_HOST_CLI", "codex")
        fsm = _fsm(
            StateConfig(action="echo", action_type="shell", on_yes="done", on_no="done"),
            llm=LLMConfig(model_hint="coding"),
        )
        result, runner, _ = _execute(fsm)
        assert result.terminated_by == "terminal" and runner.calls == ["echo"]
        assert result.model_hint_error is False

    def test_non_llm_structured_evaluator_skips_llm_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "codex")
        fsm = _fsm(_prompt(), llm=LLMConfig(model_hint="coding"))
        result, runner, _ = _execute(fsm)
        assert result.terminated_by == "terminal" and runner.calls == ["do it"]
        assert runner.models == [None]  # an llm declaration is never a CLI-action default

    def test_no_llm_skips_evaluator_resolution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "codex")
        state = StateConfig(action="do it", action_type="prompt", on_yes="done", on_no="done")
        fsm = _fsm(state, llm=LLMConfig(model_hint="coding", enabled=False))
        result, runner, events = _execute(fsm)
        assert not result.model_hint_error and runner.calls == ["do it"]
        (ev,) = _of(events, "evaluate")
        assert not any(k in ev for k in _SELECTION_KEYS)

    def test_no_hint_unaffected(self) -> None:
        fsm = _fsm(StateConfig(action="echo", action_type="shell", next="done"))
        result, runner, _ = _execute(fsm)
        assert result.terminated_by == "terminal" and runner.calls == ["echo"]

    def test_non_hint_error_leaves_flag_false(self) -> None:
        class Boom(ModelRunner):
            def run(self, *a: Any, **kw: Any) -> Any:
                raise RuntimeError("boom")

        result, _, _ = _execute(_fsm(_prompt()), runner=Boom())
        assert result.terminated_by == "error" and result.model_hint_error is False
        assert "model_hint_error" not in result.to_dict()


class TestLearningState:
    """AC18: the /ll:explore-api remedy consumes the learning state's declaration."""

    def _fsm(self, hint: str) -> FSMLoop:
        return FSMLoop(
            name="t",
            initial="pre",
            states={
                "pre": StateConfig(action="echo pre", action_type="shell", next="learn"),
                "learn": StateConfig(
                    type="learning",
                    learning=LearningConfig(targets=["x"], max_retries=1),
                    model_hint=hint,
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def test_unmapped_hint_fails_preflight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "codex")
        result, runner, _ = _execute(self._fsm("coding"))
        assert result.terminated_by == "error" and result.model_hint_error
        assert "'learn'" in (result.error or "")
        assert runner.calls == []

    def test_resolved_hint_reaches_remedy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        with (
            patch(
                "little_loops.learning_tests.check_learning_test",
                side_effect=[None, SimpleNamespace(status="proven")],
            ),
            patch("little_loops.learning_tests.gate.is_record_stale", return_value=False),
        ):
            result, runner, events = _execute(self._fsm("burst"))
        assert result.terminated_by == "terminal"
        assert runner.calls == ["echo pre", "/ll:explore-api x"]
        assert runner.models == [None, "haiku"]
        remedy = _of(events, "action_complete")[-1]
        assert remedy["model_requested"] == "burst"
        assert remedy["model_resolved"] == "haiku"
        assert remedy["model_backend"] == "claude-code"


class TestCliActionDispatch:
    """AC1/AC16: CLI-action precedence and event fields."""

    def test_state_hint_resolves_for_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        result, runner, events = _execute(_fsm(_prompt(model_hint="burst")), run_model="opus")
        assert runner.models == ["haiku"]
        (ev,) = _of(events, "action_complete")
        assert (ev["model_requested"], ev["model_resolved"], ev["model_backend"]) == (
            "burst",
            "haiku",
            "claude-code",
        )

    def test_literal_state_model_argv_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        _, runner, events = _execute(_fsm(_prompt(model="opus")), run_model="haiku")
        assert runner.models == ["opus"]
        (ev,) = _of(events, "action_complete")
        assert ev["model_requested"] == ev["model_resolved"] == "opus"
        assert ev["model_backend"] == "claude-code"

    def test_run_model_below_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        _, runner, _ = _execute(_fsm(_prompt()), run_model="opus")
        assert runner.models == ["opus"]

    def test_no_declaration_emits_no_selection_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        fsm = _fsm(_prompt(), llm=LLMConfig(model_hint="coding"))
        _, runner, events = _execute(fsm)
        assert runner.models == [None]
        (ev,) = _of(events, "action_complete")
        assert not any(k in ev for k in _SELECTION_KEYS)

    def test_literal_without_host_runs_and_omits_backend(
        self, no_host: None, eval_spy: Any
    ) -> None:
        """AC13: a literal selection never needs the host; model_backend is left out."""
        state = StateConfig(
            action="do it", action_type="prompt", model="opus", on_yes="done", on_no="done"
        )
        result, runner, events = _execute(_fsm(state))
        assert result.terminated_by == "terminal" and runner.models == ["opus"]
        (ac,) = _of(events, "action_complete")
        assert ac["model_resolved"] == "opus" and "model_backend" not in ac
        (ev,) = _of(events, "evaluate")
        assert ev["model_resolved"] == "opus" and "model_backend" not in ev

    def test_downgrade_re_resolves_for_cli_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from little_loops.config.orchestration import OrchestrationConfig

        monkeypatch.setenv("LL_HOST_CLI", "fake")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        state = _prompt(model_hint="coding", tools=["Read"])
        _, runner, events = _execute(
            _fsm(state), orchestration_config=OrchestrationConfig(request_path="sdk")
        )
        assert runner.models == ["fake-coding"]
        assert _of(events, "request_path_downgrade")
        (ev,) = _of(events, "action_complete")
        assert ev["model_backend"] == "fake"


class TestEvaluatorDispatch:
    """AC1/AC3/AC8/AC15/AC16: evaluator precedence, backend and event fields."""

    def _state(self, **kw: Any) -> StateConfig:
        return StateConfig(
            action="echo hi",
            action_type="shell",
            evaluate=EvaluateConfig(type="llm_structured", prompt="ok?"),
            on_yes="done",
            on_no="done",
            **kw,
        )

    @pytest.mark.parametrize(
        "state_kw,llm,expected",
        [
            ({"model_hint": "burst"}, LLMConfig(model="opus"), "haiku"),
            ({"model": "opus"}, LLMConfig(model_hint="burst"), "opus"),
            ({}, LLMConfig(model_hint="reasoning"), "opus"),
            ({}, LLMConfig(model="haiku"), "haiku"),
            ({}, LLMConfig(), DEFAULT_LLM_MODEL),
        ],
    )
    def test_precedence(
        self,
        monkeypatch: pytest.MonkeyPatch,
        eval_spy: Any,
        state_kw: dict[str, Any],
        llm: LLMConfig,
        expected: str,
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        # run --model never feeds the evaluator.
        _execute(_fsm(self._state(**state_kw), llm=llm), run_model="fable")
        assert eval_spy.models == [expected]

    def test_llm_structured_event_carries_fields(
        self, monkeypatch: pytest.MonkeyPatch, eval_spy: Any
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        _, _, events = _execute(_fsm(self._state(model_hint="coding")))
        (ev,) = _of(events, "evaluate")
        assert (ev["model_requested"], ev["model_resolved"], ev["model_backend"]) == (
            "coding",
            "sonnet",
            "claude-code",
        )
        assert ev["llm_model"] == "sonnet"

    def test_non_llm_evaluate_events_carry_no_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        state = StateConfig(action="echo", action_type="shell", on_yes="done", on_no="done")
        _, _, events = _execute(_fsm(state, llm=LLMConfig(model_hint="coding")))
        (ev,) = _of(events, "evaluate")
        assert not any(k in ev for k in _SELECTION_KEYS)

    def test_llm_structured_under_no_llm_carries_no_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "codex")
        fsm = _fsm(self._state(model_hint="coding"), llm=LLMConfig(enabled=False))
        result, _, events = _execute(fsm)
        assert not result.model_hint_error
        (ev,) = _of(events, "evaluate")
        assert not any(k in ev for k in _SELECTION_KEYS)

    def test_sdk_state_evaluator_uses_cli_host_and_action_uses_api(
        self, monkeypatch: pytest.MonkeyPatch, eval_spy: Any
    ) -> None:
        """AC3 + AC8: one declaration, two backends, two model strings."""
        from little_loops.config.orchestration import OrchestrationConfig

        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        client = _sdk_env(monkeypatch)
        state = StateConfig(
            action="do it",
            action_type="prompt",
            model_hint="coding",
            on_yes="done",
            on_no="done",
        )
        with patch("anthropic.Anthropic", return_value=client):
            _, runner, events = _execute(
                _fsm(state), orchestration_config=OrchestrationConfig(request_path="sdk")
            )
        assert runner.calls == []
        assert client.messages.create.call_args.kwargs["model"] == MODEL_ALIASES["sonnet"]
        assert eval_spy.models == ["sonnet"]
        (ev,) = _of(events, "evaluate")
        assert ev["model_backend"] == "claude-code"

    def test_foreign_cli_host_never_supplies_api_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC2: an sdk action resolves on anthropic-api even under an unmapped CLI host."""
        from little_loops.config.orchestration import OrchestrationConfig

        monkeypatch.setenv("LL_HOST_CLI", "codex")
        client = _sdk_env(monkeypatch)
        with patch("anthropic.Anthropic", return_value=client):
            result, _, events = _execute(
                _fsm(_prompt(model_hint="burst")),
                orchestration_config=OrchestrationConfig(
                    request_path="sdk", model_hints={"codex": {"burst": "gpt-mini"}}
                ),
            )
        assert result.terminated_by == "terminal"
        assert client.messages.create.call_args.kwargs["model"] == MODEL_ALIASES["haiku"]
        (ev,) = _of(events, "action_complete")
        assert ev["model_backend"] == "anthropic-api"


class TestSdkDispatch:
    """AC1/AC16: SDK precedence; model_resolved is what the SDK client received."""

    @pytest.mark.parametrize(
        "state_kw,run_model,llm,expected_alias",
        [
            ({"model": "sonnet"}, "opus", LLMConfig(), "sonnet"),
            ({"model_hint": "burst"}, "opus", LLMConfig(), "haiku"),
            ({}, "opus", LLMConfig(model_hint="burst"), "opus"),
            ({}, None, LLMConfig(model_hint="reasoning"), "opus"),
            ({}, None, LLMConfig(model="haiku"), "haiku"),
        ],
    )
    def test_precedence_and_payload_match_client(
        self,
        monkeypatch: pytest.MonkeyPatch,
        state_kw: dict[str, Any],
        run_model: str | None,
        llm: LLMConfig,
        expected_alias: str,
    ) -> None:
        from little_loops.config.orchestration import OrchestrationConfig

        client = _sdk_env(monkeypatch)
        with patch("anthropic.Anthropic", return_value=client):
            _, _, events = _execute(
                _fsm(_prompt(**state_kw), llm=llm),
                run_model=run_model,
                orchestration_config=OrchestrationConfig(request_path="sdk"),
            )
        sent = client.messages.create.call_args.kwargs["model"]
        assert sent == MODEL_ALIASES[expected_alias]
        (ev,) = _of(events, "action_complete")
        assert ev["model_resolved"] == sent
        assert ev["model_backend"] == "anthropic-api"


class TestDispatchTimeErrors:
    """AC12/AC14: a ModelHintError ends the run with "error", never on_error."""

    def test_action_path_ignores_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "codex")
        monkeypatch.setattr(FSMExecutor, "_preflight_model_hints", lambda self: None)
        fsm = FSMLoop(
            name="t",
            initial="s",
            states={
                "s": _prompt(model_hint="coding", on_error="handler"),
                "handler": StateConfig(terminal=True),
                "done": StateConfig(terminal=True),
            },
        )
        result, runner, events = _execute(fsm)
        assert result.terminated_by == "error" and result.model_hint_error
        assert result.final_state == "s"
        assert runner.calls == []
        assert not _of(events, "action_error")

    def test_evaluator_path_skips_post_evaluation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "codex")
        monkeypatch.setattr(FSMExecutor, "_preflight_model_hints", lambda self: None)
        fsm = FSMLoop(
            name="t",
            initial="s",
            states={
                "s": StateConfig(
                    action="echo",
                    action_type="shell",
                    model_hint="coding",
                    evaluate=EvaluateConfig(type="llm_structured", prompt="ok?"),
                    capture="cap",
                    on_yes="done",
                    on_no="done",
                    on_error="handler",
                ),
                "handler": StateConfig(terminal=True),
                "done": StateConfig(terminal=True),
            },
        )
        result, runner, events = _execute(fsm)
        assert result.terminated_by == "error"  # not no_route
        assert result.model_hint_error and result.final_state == "s"
        assert runner.calls == ["echo"]
        assert "verdict" not in result.captured.get("cap", {})
        assert not _of(events, "evaluate") and not _of(events, "route")

    def test_child_hint_failure_ends_parent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "codex")
        (tmp_path / "child.yaml").write_text(
            """
name: child
initial: work
states:
  work:
    action: "do it"
    action_type: prompt
    model_hint: coding
    evaluate:
      type: output_contains
      pattern: ""
    on_yes: done
    on_no: done
  done:
    terminal: true
"""
        )
        parent = FSMLoop(
            name="parent",
            initial="call",
            states={
                "call": StateConfig(
                    loop="child", on_yes="done", on_no="handler", on_error="handler"
                ),
                "handler": StateConfig(terminal=True),
                "done": StateConfig(terminal=True),
            },
        )
        result, runner, _ = _execute(parent, loops_dir=tmp_path)
        assert result.terminated_by == "error" and result.model_hint_error
        assert result.final_state == "call"
        assert "sub-loop 'child'" in (result.error or "")
        assert runner.calls == []


class TestSubLoopSemantics:
    """AC7: run --model inherits; children resolve against their own llm."""

    def test_child_resolves_own_llm_hint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, eval_spy: Any
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        (tmp_path / "child.yaml").write_text(
            """
name: child
initial: work
llm:
  model_hint: burst
states:
  work:
    action: "do it"
    action_type: prompt
    on_yes: done
    on_no: done
  done:
    terminal: true
"""
        )
        parent = FSMLoop(
            name="parent",
            initial="call",
            llm=LLMConfig(model="opus"),
            states={
                "call": StateConfig(loop="child", on_yes="done", on_no="done"),
                "done": StateConfig(terminal=True),
            },
        )
        result, runner, _ = _execute(parent, loops_dir=tmp_path, run_model="fable")
        assert result.terminated_by == "terminal"
        assert runner.models == ["fable"]  # run --model inherits into the child's CLI action
        assert eval_spy.models == ["haiku"]  # child llm.model_hint, not the parent's llm


class TestResume:
    """AC6/AC10: resume re-reads declarations and resolves afresh."""

    def _fsm(self) -> FSMLoop:
        return _fsm(
            StateConfig(action="do it", action_type="prompt", on_yes="done", on_no="done"),
            llm=LLMConfig(model_hint="coding"),
        )

    def _resume(self, tmp_path: Path, fsm: FSMLoop, **kw: Any) -> list[dict[str, Any]]:
        persistence = StatePersistence("t", tmp_path / ".loops")
        persistence.initialize()
        persistence.save_state(
            LoopState(
                loop_name="t",
                current_state="s",
                iteration=1,
                captured={},
                prev_result=None,
                last_result=None,
                started_at="2026-09-27T00:00:00Z",
                updated_at="",
                status="interrupted",
            )
        )
        events: list[dict[str, Any]] = []
        ex = PersistentExecutor(fsm, persistence=persistence, action_runner=ModelRunner(), **kw)
        ex.event_bus.register(events.append)
        assert ex.resume() is not None
        return events

    def test_resume_reactivates_yaml_hint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, eval_spy: Any
    ) -> None:
        """A resume without --llm-model sees the YAML llm.model_hint again."""
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        (ev,) = _of(self._resume(tmp_path, self._fsm()), "evaluate")
        assert (ev["model_requested"], ev["model_resolved"]) == ("coding", "sonnet")

    def test_resume_under_changed_mapping_and_host(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, eval_spy: Any
    ) -> None:
        from little_loops.config.orchestration import OrchestrationConfig

        monkeypatch.setenv("LL_HOST_CLI", "codex")
        events = self._resume(
            tmp_path,
            self._fsm(),
            orchestration_config=OrchestrationConfig(model_hints={"codex": {"coding": "gpt-x"}}),
        )
        (ev,) = _of(events, "evaluate")
        assert (ev["model_resolved"], ev["model_backend"]) == ("gpt-x", "codex")
        assert eval_spy.models == ["gpt-x"]


class TestLlmModelFlag:
    """AC9 (test only): --llm-model replaces the llm declaration and clears the hint."""

    def test_llm_model_clears_inherited_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "hinted.yaml").write_text(
            """
name: hinted
initial: s
llm:
  model_hint: coding
states:
  s:
    action: "echo hi"
    action_type: shell
    next: done
  done:
    terminal: true
"""
        )
        monkeypatch.chdir(tmp_path)
        seen: list[FSMLoop] = []
        original = FSMExecutor.__init__

        def spy_init(self: Any, fsm: FSMLoop, **kw: Any) -> None:
            seen.append(fsm)
            original(self, fsm, **kw)

        with (
            patch.object(FSMExecutor, "__init__", spy_init),
            patch.object(sys, "argv", ["ll-loop", "run", "hinted", "--llm-model", "opus"]),
        ):
            from little_loops.cli import main_loop

            main_loop()
        assert seen and seen[0].llm.model == "opus" and seen[0].llm.model_hint is None


class TestHostArgv:
    """AC4/AC5: every advertised host/operation reaches --model argv or errors."""

    def _run(self, monkeypatch: pytest.MonkeyPatch, host: str, **kw: Any) -> Any:
        monkeypatch.setenv("LL_HOST_CLI", host)
        runner = ArgvRunner()
        result, _, _ = _execute(_fsm(_prompt(model_hint="coding")), runner=runner, **kw)
        return result, runner

    @pytest.mark.parametrize(
        "host,expected",
        [("claude-code", "sonnet"), ("fake", "fake-coding"), ("fake-minimal", "fake-coding")],
    )
    def test_builtin_mappings_reach_argv(
        self, monkeypatch: pytest.MonkeyPatch, host: str, expected: str
    ) -> None:
        result, runner = self._run(monkeypatch, host)
        assert result.terminated_by == "terminal"
        (args,) = runner.argv
        assert _model_after_flag(args) == expected

    @pytest.mark.parametrize("host", ["codex", "gemini", "omp", "kimi-code", "qwen"])
    def test_config_only_hosts_reach_argv(self, monkeypatch: pytest.MonkeyPatch, host: str) -> None:
        from little_loops.config.orchestration import OrchestrationConfig

        cfg = OrchestrationConfig(model_hints={host: {"coding": f"{host}-model"}})
        result, runner = self._run(monkeypatch, host, orchestration_config=cfg)
        assert result.terminated_by == "terminal"
        (args,) = runner.argv
        assert _model_after_flag(args) == f"{host}-model"
        try:
            blocking = resolve_host().build_blocking_json(prompt="p", model=f"{host}-model")
        except (NotImplementedError, RuntimeError):
            return  # host exposes no blocking-JSON build
        assert _model_after_flag(list(blocking.args)) == f"{host}-model"

    @pytest.mark.parametrize(
        "host,overrides,match",
        [
            ("opencode", None, "not supported"),
            ("pi", None, "not supported"),
            ("codex", None, "no mapping"),
            ("claude-code", {"claude-code": {"coding": False}}, "disabled"),
        ],
    )
    def test_missing_or_disabled_mapping_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        host: str,
        overrides: dict[str, Any] | None,
        match: str,
    ) -> None:
        from little_loops.config.orchestration import OrchestrationConfig

        cfg = OrchestrationConfig(model_hints=overrides or {})
        result, runner = self._run(monkeypatch, host, orchestration_config=cfg)
        assert result.terminated_by == "error" and match in (result.error or "")
        assert runner.argv == []

    @pytest.mark.parametrize("runner_cls", [FakeHostRunner, FakeMinimalHostRunner])
    def test_fakes_put_model_before_prompt(self, runner_cls: Any) -> None:
        r = runner_cls()
        for inv in (
            r.build_streaming(prompt="P", model="fake-burst"),
            r.build_blocking_json(prompt="P", model="fake-burst"),
        ):
            args = list(inv.args)
            assert args[-1] == "P" and _model_after_flag(args) == "fake-burst"
            assert args.index("--model") < args.index("P")
        assert "--model" not in r.build_streaming(prompt="P").args
        assert "--model" not in r.build_blocking_json(prompt="P").args

    @pytest.mark.parametrize("runner_cls", [FakeHostRunner, FakeMinimalHostRunner])
    def test_fence_less_prompt_unaffected_by_model(
        self, runner_cls: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.fake_host import main

        prompt = "plain prompt with no fence"
        plain_rc = main(runner_cls().build_streaming(prompt=prompt).args)
        plain = capsys.readouterr()
        model_rc = main(runner_cls().build_streaming(prompt=prompt, model="fake-coding").args)
        with_model = capsys.readouterr()
        assert (model_rc, with_model.out, with_model.err) == (plain_rc, plain.out, plain.err)


class TestPortabilityProof:
    """AC17: one loop with coding/burst states runs unedited on every backend."""

    LOOP = """
name: portable
initial: write
states:
  write:
    action: "write the code"
    action_type: prompt
    model_hint: coding
    next: summarize
  summarize:
    action: "summarize it"
    action_type: prompt
    model_hint: burst
    next: done
  done:
    terminal: true
"""

    def _load(self, tmp_path: Path) -> FSMLoop:
        path = tmp_path / "portable.yaml"
        path.write_text(self.LOOP)
        fsm, _ = load_and_validate(path)
        return fsm

    @pytest.mark.parametrize(
        "host,expected",
        [("fake", ["fake-coding", "fake-burst"]), ("claude-code", ["sonnet", "haiku"])],
    )
    def test_cli_hosts(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, host: str, expected: list[str]
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", host)
        runner = ArgvRunner()
        result, _, _ = _execute(self._load(tmp_path), runner=runner)
        assert result.terminated_by == "terminal"
        assert [_model_after_flag(a) for a in runner.argv] == expected

    def test_anthropic_api(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from little_loops.config.orchestration import OrchestrationConfig

        monkeypatch.setenv("LL_HOST_CLI", "fake")
        client = _sdk_env(monkeypatch)
        with patch("anthropic.Anthropic", return_value=client):
            result, runner, _ = _execute(
                self._load(tmp_path),
                orchestration_config=OrchestrationConfig(request_path="sdk"),
            )
        assert result.terminated_by == "terminal" and runner.calls == []
        sent = [c.kwargs["model"] for c in client.messages.create.call_args_list]
        assert sent == [MODEL_ALIASES["sonnet"], MODEL_ALIASES["haiku"]]


def _res_warnings(
    fsm: FSMLoop,
    host_cli: str | None,
    model_hints: dict[str, Any] | None = None,
    request_path: str | None = None,
) -> list[Any]:
    """WARNING violations produced by the ENH-3548 hint-resolution rule."""
    found = validate_fsm(fsm, request_path, host_cli=host_cli, model_hints=model_hints)
    return [
        e for e in found if e.severity == ValidationSeverity.WARNING and "ENH-3548" in e.message
    ]


class TestValidateResolution:
    """ENH-3548: validate-time WARNINGs for hints that will not resolve."""

    def test_unmapped_cli_hint_warns_with_fix(self) -> None:
        fsm = _fsm(_prompt(model_hint="coding"))
        (w,) = _res_warnings(fsm, "codex")
        assert w.path == "states.s.model_hint"
        assert "[state: s]" in w.message and "codex" in w.message
        assert "orchestration.model_hints.codex.coding" in w.message

    def test_resolved_hint_is_silent(self) -> None:
        fsm = _fsm(_prompt(model_hint="coding"))
        assert _res_warnings(fsm, "claude-code") == []
        assert _res_warnings(fsm, "codex", {"codex": {"coding": "gpt-x"}}) == []

    def test_disabled_and_unsupported_warn(self) -> None:
        fsm = _fsm(_prompt(model_hint="burst"))
        assert len(_res_warnings(fsm, "claude-code", {"claude-code": {"burst": False}})) == 1
        assert len(_res_warnings(fsm, "opencode", {"opencode": {"burst": "m"}})) == 1

    def test_host_none_skips_resolution_but_keeps_vocab_error(self) -> None:
        fsm = _fsm(_prompt(model_hint="coding"))
        assert _res_warnings(fsm, None) == []
        bad = _fsm(_prompt(model_hint="fast"))
        assert _res_warnings(bad, None) == []
        assert any("must be one of" in m for m in _errors(bad))

    def test_out_of_vocabulary_hint_gets_no_resolution_warning(self) -> None:
        fsm = _fsm(_prompt(model_hint="fast"))
        assert _res_warnings(fsm, "codex") == []
        assert any("must be one of" in m for m in _errors(fsm))

    def test_sdk_state_checks_anthropic_api_and_cli_fallback(self) -> None:
        fsm = _fsm(_prompt(model_hint="coding"))
        (w,) = _res_warnings(fsm, "codex", request_path="sdk")
        assert "codex" in w.message and "downgrades to cli" in w.message
        ov = {"anthropic-api": {"coding": False}, "codex": {"coding": "gpt-x"}}
        (w,) = _res_warnings(fsm, "codex", ov, request_path="sdk")
        assert "anthropic-api" in w.message

    def test_state_request_path_overrides_config(self) -> None:
        fsm = _fsm(_prompt(model_hint="coding", request_path="cli"))
        (w,) = _res_warnings(fsm, "codex", request_path="sdk")
        assert "downgrades to cli" not in w.message

    @pytest.mark.parametrize("kw", [{"action": "/ll:do-it"}, {"tools": ["Bash"]}])
    def test_static_downgrade_is_cli_only(self, kw: dict[str, Any]) -> None:
        fsm = _fsm(_prompt(model_hint="coding", **kw))
        ov = {"anthropic-api": {"coding": False}, "codex": {"coding": "gpt-x"}}
        assert _res_warnings(fsm, "codex", ov, request_path="sdk") == []

    def test_evaluator_only_hint_never_checks_anthropic_api(self) -> None:
        st = StateConfig(
            action="echo hi",
            action_type="shell",
            model_hint="coding",
            request_path="sdk",
            evaluate=EvaluateConfig(type="llm_structured", prompt="ok?"),
            on_yes="done",
            on_no="done",
        )
        ov = {"anthropic-api": {"coding": False}, "codex": {"coding": "gpt-x"}}
        assert _res_warnings(_fsm(st), "codex", ov) == []
        (w,) = _res_warnings(_fsm(st), "codex")
        assert "codex" in w.message

    def test_no_evaluator_path_when_next_or_llm_disabled(self) -> None:
        implicit = StateConfig(
            action="do it", action_type="prompt", model_hint="coding", next="done"
        )
        assert len(_res_warnings(_fsm(implicit), "codex")) == 1  # cli path only
        fsm = _fsm(
            StateConfig(action="do it", action_type="prompt", on_yes="done", on_no="done"),
            llm=LLMConfig(model_hint="coding", enabled=False),
        )
        assert _res_warnings(fsm, "codex") == []

    def test_llm_hint_warns_once_per_backend_at_llm_path(self) -> None:
        fsm = FSMLoop(
            name="t",
            initial="a",
            states={
                "a": StateConfig(action="x", action_type="prompt", next="b"),
                "b": StateConfig(
                    action="y",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="llm_structured", prompt="ok?"),
                    on_yes="c",
                    on_no="c",
                ),
                "c": StateConfig(
                    action="z",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="llm_structured", prompt="ok?"),
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
            llm=LLMConfig(model_hint="coding"),
        )
        found = _res_warnings(fsm, "codex")
        assert [w.path for w in found] == ["llm.model_hint"]

    def test_llm_hint_not_checked_on_cli_fallback_or_literal_model(self) -> None:
        cli_only = _fsm(
            StateConfig(action="x", action_type="prompt", next="done"),
            llm=LLMConfig(model_hint="coding"),
        )
        assert _res_warnings(cli_only, "codex") == []
        literal = _fsm(
            StateConfig(
                action="x",
                action_type="prompt",
                model="opus",
                evaluate=EvaluateConfig(type="llm_structured", prompt="ok?"),
                on_yes="done",
                on_no="done",
            ),
            llm=LLMConfig(model_hint="coding"),
        )
        assert _res_warnings(literal, "codex") == []

    def test_llm_hint_on_sdk_state_checks_anthropic_api_only(self) -> None:
        fsm = _fsm(
            StateConfig(action="x", action_type="prompt", next="done"),
            llm=LLMConfig(model_hint="coding"),
        )
        ov = {"anthropic-api": {"coding": False}}
        (w,) = _res_warnings(fsm, "claude-code", ov, request_path="sdk")
        assert w.path == "llm.model_hint" and "anthropic-api" in w.message
        assert _res_warnings(fsm, "codex", request_path="sdk") == []

    def test_non_consumers_never_checked(self) -> None:
        states = {
            "sub": StateConfig(loop="other", on_yes="done", on_no="done"),
            "done": StateConfig(terminal=True),
        }
        fsm = FSMLoop(name="t", initial="sub", states=states, llm=LLMConfig(model_hint="coding"))
        assert _res_warnings(fsm, "codex") == []

    def test_learning_state_has_no_evaluator_path_and_no_skill_downgrade(self) -> None:
        st = StateConfig(
            type="learning",
            learning=LearningConfig(targets=["x"], max_retries=1),
            model_hint="coding",
            on_yes="done",
            on_no="done",
        )
        ov = {"anthropic-api": {"coding": False}, "codex": {"coding": "gpt-x"}}
        (w,) = _res_warnings(_fsm(st), "codex", ov, request_path="sdk")
        assert "anthropic-api" in w.message
        assert len(_res_warnings(_fsm(st), "codex")) == 1

    def test_load_and_validate_forwards_kwargs(self, tmp_path: Path) -> None:
        path = tmp_path / "l.yaml"
        path.write_text(TestPortabilityProof.LOOP)
        _, plain = load_and_validate(path, raise_on_error=False)
        assert not [v for v in plain if "ENH-3548" in v.message]
        _, found = load_and_validate(path, raise_on_error=False, host_cli="codex", model_hints={})
        assert len([v for v in found if "ENH-3548" in v.message]) == 2

    def test_portable_loop_silent_on_builtin_hosts(self, tmp_path: Path) -> None:
        path = tmp_path / "l.yaml"
        path.write_text(TestPortabilityProof.LOOP)
        _, found = load_and_validate(path, raise_on_error=False, host_cli="claude-code")
        assert not [v for v in found if "ENH-3548" in v.message]


class TestValidateAgreesWithPreflight:
    """ENH-3548: validate mirrors ``FSMExecutor._preflight_model_hints``."""

    @staticmethod
    def _cases() -> dict[str, tuple[FSMLoop, str | None]]:
        def eval_state(**kw: Any) -> StateConfig:
            return StateConfig(
                action=kw.pop("action", "do it"),
                action_type=kw.pop("action_type", "prompt"),
                evaluate=EvaluateConfig(type="llm_structured", prompt="ok?"),
                on_yes="done",
                on_no="done",
                **kw,
            )

        learn = StateConfig(
            type="learning",
            learning=LearningConfig(targets=["x"], max_retries=1),
            model_hint="coding",
            on_yes="done",
            on_no="done",
        )
        return {
            "cli": (_fsm(_prompt(model_hint="coding")), None),
            "sdk": (_fsm(_prompt(model_hint="coding")), "sdk"),
            "skill": (_fsm(_prompt(model_hint="coding", action="/ll:x")), "sdk"),
            "tools": (_fsm(_prompt(model_hint="coding", tools=["Bash"])), "sdk"),
            "evaluator": (_fsm(eval_state(model_hint="coding")), None),
            "shell-eval": (
                _fsm(eval_state(action="echo", action_type="shell", model_hint="coding")),
                "sdk",
            ),
            "llm-eval": (_fsm(eval_state(), llm=LLMConfig(model_hint="coding")), None),
            "literal-eval": (
                _fsm(eval_state(model="opus"), llm=LLMConfig(model_hint="coding")),
                None,
            ),
            "llm-cli-only": (
                _fsm(_prompt(), llm=LLMConfig(model_hint="coding")),
                None,
            ),
            "learning": (_fsm(learn), "sdk"),
            "no-hint": (_fsm(_prompt()), None),
        }

    @pytest.mark.parametrize("host", ["codex", "claude-code"])
    @pytest.mark.parametrize("overrides", [{}, {"anthropic-api": {"coding": False}}])
    @pytest.mark.parametrize(
        "case",
        [
            "cli",
            "sdk",
            "skill",
            "tools",
            "evaluator",
            "shell-eval",
            "llm-eval",
            "literal-eval",
            "llm-cli-only",
            "learning",
            "no-hint",
        ],
    )
    def test_agreement(
        self,
        monkeypatch: pytest.MonkeyPatch,
        case: str,
        overrides: dict[str, Any],
        host: str,
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", host)
        monkeypatch.setattr(FSMExecutor, "_sdk_credentials_available", staticmethod(lambda: True))
        pytest.importorskip("anthropic")
        fsm, request_path = self._cases()[case]
        orch = OrchestrationConfig(request_path=request_path or "cli", model_hints=overrides)
        ex = FSMExecutor(fsm, action_runner=ModelRunner(), orchestration_config=orch)
        preflight = ex._preflight_model_hints()
        found = _res_warnings(fsm, host, overrides, request_path)
        if preflight is not None:
            assert found, f"preflight failed ({preflight}) but validate was silent"
        elif case not in ("sdk", "learning"):
            # validate also checks the CLI fallback of sdk states, so it may say more there
            assert not found, [w.message for w in found]
