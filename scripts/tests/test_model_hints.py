"""Tests for ENH-3527: model_hint declarations, resolver, config, and pre-dispatch guard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.cli.verify_host_map import _check_hint_backend_coverage
from little_loops.config.core import deep_merge
from little_loops.config.orchestration import OrchestrationConfig
from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.schema import (
    DEFAULT_LLM_MODEL,
    EvaluateConfig,
    FSMLoop,
    LLMConfig,
    StateConfig,
)
from little_loops.fsm.validation import ValidationSeverity, validate_fsm
from little_loops.host_runner import (
    _HOST_RUNNER_REGISTRY,
    MODEL_ALIASES,
    MODEL_HINTS,
    RUNTIME_HOST_CAPABILITIES,
    TEST_ONLY_HOSTS,
    ModelHintError,
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


class TestPreDispatchGuard:
    def _run(self, fsm: FSMLoop) -> tuple[Any, MockActionRunner]:
        runner = MockActionRunner()
        return FSMExecutor(fsm, action_runner=runner, event_callback=lambda _: None).run(), runner

    def test_state_hint_blocks_before_any_state(self) -> None:
        fsm = FSMLoop(
            name="t",
            initial="pre",
            states={
                "pre": StateConfig(action="echo pre", action_type="shell", next="hinted"),
                "hinted": StateConfig(
                    action="x",
                    action_type="prompt",
                    model_hint="coding",
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        result, runner = self._run(fsm)
        assert result.terminated_by == "error"
        assert "model_hint dispatch not yet supported" in (result.error or "")
        assert runner.calls == []

    def test_llm_hint_blocks(self) -> None:
        fsm = _fsm(
            StateConfig(action="echo", action_type="shell", on_yes="done", on_no="done"),
            llm=LLMConfig(model_hint="coding"),
        )
        result, runner = self._run(fsm)
        assert result.terminated_by == "error" and runner.calls == []

    def test_no_hint_unaffected(self) -> None:
        fsm = _fsm(StateConfig(action="echo", action_type="shell", next="done"))
        result, runner = self._run(fsm)
        assert result.terminated_by == "terminal" and runner.calls == ["echo"]
