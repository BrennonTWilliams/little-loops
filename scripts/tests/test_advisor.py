"""Tests for advisor module."""

from unittest.mock import patch

import pytest

from little_loops.advisor import (
    MODEL_RANKS,
    AdvisorNotConfigured,
    AdvisorVerdict,
    CapabilityFloorViolation,
    check_floor,
    consult,
    rank_model,
)
from little_loops.config.orchestration import AdvisorConfig
from little_loops.host_runner import BlockingJsonError, HostInvocation


class TestModelRanks:
    def test_claude_code_covers_haiku_sonnet_opus_fable(self):
        ranks = MODEL_RANKS["claude-code"]
        assert set(ranks) == {
            "claude-haiku-4-5",
            "claude-sonnet-5",
            "claude-opus-5",
            "claude-fable-5",
        }

    def test_claude_code_haiku_ranks_below_opus(self):
        ranks = MODEL_RANKS["claude-code"]
        assert ranks["claude-haiku-4-5"] < ranks["claude-opus-5"]

    def test_covers_canonical_host_name_set(self):
        assert set(MODEL_RANKS) == {
            "claude-code",
            "codex",
            "opencode",
            "pi",
            "gemini",
            "omp",
            "kimi-code",
        }


class TestRankModel:
    def test_alias_and_concrete_id_return_same_rank(self):
        assert rank_model("claude-code", "opus") == rank_model("claude-code", "claude-opus-5")

    def test_haiku_ranks_below_opus(self):
        assert rank_model("claude-code", "haiku") < rank_model("claude-code", "opus")

    def test_unknown_model_returns_none(self):
        assert rank_model("claude-code", "claude-opus-1-ancient") is None

    def test_unrankable_host_returns_none(self):
        assert rank_model("codex", "gpt-5") is None


class TestCheckFloor:
    def test_pinned_same_host_violation(self):
        result = check_floor("claude-code", "haiku", "claude-code", "opus")
        assert result.status == "violation"

    def test_same_mismatch_across_hosts_is_advisory(self):
        result = check_floor("codex", "haiku", "claude-code", "opus")
        assert result.status == "advisory"

    def test_unknown_model_returns_unknown_not_silent_pass(self):
        result = check_floor("claude-code", "claude-opus-1-ancient", "claude-code", "opus")
        assert result.status == "unknown"

    def test_cross_host_is_advisory_even_when_unrankable(self):
        # Pin: the cross-host check runs before rank lookup — two hosts'
        # rank tables are separate ordinal spaces, so a host mismatch is
        # "advisory" regardless of whether either model is rankable.
        result = check_floor("codex", "gpt-5", "claude-code", "opus")
        assert result.status == "advisory"

    def test_equal_rank_same_host_is_ok(self):
        # Pin: equality (advisor rank == main rank, same host) classifies as
        # "ok" — an advisor no weaker than main satisfies the floor. This
        # semantics choice was left open by FEAT-3108; pinned here.
        result = check_floor("claude-code", "opus", "claude-code", "opus")
        assert result.status == "ok"

    def test_advisor_ranked_above_main_same_host_is_ok(self):
        result = check_floor("claude-code", "opus", "claude-code", "haiku")
        assert result.status == "ok"


class _FakeConfig:
    """Minimal config double — consult() only reads `.advisor.{host,model,timeout_seconds}`."""

    def __init__(self, advisor: AdvisorConfig) -> None:
        self.advisor = advisor


def _make_runner():
    runner = type(
        "FakeRunner",
        (),
        {
            "name": "claude-code",
            "build_blocking_json": lambda self, *, prompt, model=None, json_schema=None: (
                HostInvocation(binary="claude", args=["-p", prompt])
            ),
        },
    )()
    return runner


class TestConsult:
    """consult() contract against a mocked host runner — no live host/auth required."""

    def test_returns_verdict_with_exact_keys(self):
        config = _FakeConfig(AdvisorConfig(host="claude-code", model="opus"))
        verdict_dict = {
            "recommendation": "do X",
            "risks": ["r1", "r2"],
            "confidence": 0.8,
            "dissent": "none",
        }
        with (
            patch("little_loops.advisor.resolve_host_named", return_value=_make_runner()),
            patch("little_loops.advisor.run_blocking_json", return_value=verdict_dict),
        ):
            verdict = consult(
                question="q",
                signal="user_requested",
                config=config,
                main_host="claude-code",
                main_model="opus",
            )
        assert isinstance(verdict, AdvisorVerdict)
        assert verdict.recommendation == "do X"
        assert verdict.risks == ["r1", "r2"]
        assert verdict.confidence == 0.8
        assert verdict.dissent == "none"
        assert verdict.signal == "user_requested"
        assert verdict.host == "claude-code"
        assert verdict.model == "opus"

    def test_unconfigured_host_raises(self):
        config = _FakeConfig(AdvisorConfig(host=None))
        with pytest.raises(AdvisorNotConfigured):
            consult(
                question="q",
                signal="user_requested",
                config=config,
                main_host="claude-code",
                main_model="opus",
            )

    def test_capability_floor_violation_refuses_consult(self):
        config = _FakeConfig(AdvisorConfig(host="claude-code", model="haiku"))
        with (
            patch("little_loops.advisor.resolve_host_named") as mock_resolve,
            patch("little_loops.advisor.run_blocking_json") as mock_run,
        ):
            with pytest.raises(CapabilityFloorViolation):
                consult(
                    question="q",
                    signal="user_requested",
                    config=config,
                    main_host="claude-code",
                    main_model="opus",
                )
        mock_resolve.assert_not_called()
        mock_run.assert_not_called()

    def test_cross_host_advisory_proceeds(self, capsys):
        config = _FakeConfig(AdvisorConfig(host="claude-code", model="haiku"))
        verdict_dict = {
            "recommendation": "do X",
            "risks": [],
            "confidence": 0.5,
            "dissent": "",
        }
        with (
            patch("little_loops.advisor.resolve_host_named", return_value=_make_runner()),
            patch("little_loops.advisor.run_blocking_json", return_value=verdict_dict),
        ):
            verdict = consult(
                question="q",
                signal="user_requested",
                config=config,
                main_host="codex",
                main_model="opus",
            )
        assert verdict.recommendation == "do X"
        assert "advisory" in capsys.readouterr().err

    def test_shape_mismatch_fails_soft_not_defaulted(self):
        config = _FakeConfig(AdvisorConfig(host="claude-code", model="opus"))
        malformed = {"verdict": "yes", "confidence": 0.5, "reason": "...", "evidence": "..."}
        with (
            patch("little_loops.advisor.resolve_host_named", return_value=_make_runner()),
            patch("little_loops.advisor.run_blocking_json", return_value=malformed),
        ):
            with pytest.raises(BlockingJsonError) as exc_info:
                consult(
                    question="q",
                    signal="user_requested",
                    config=config,
                    main_host="claude-code",
                    main_model="opus",
                )
        assert exc_info.value.details.get("shape_mismatch") is True

    def test_never_touches_dispatch_anthropic_request_or_input_hash(self):
        config = _FakeConfig(AdvisorConfig(host="claude-code", model="opus"))
        verdict_dict = {
            "recommendation": "do X",
            "risks": [],
            "confidence": 0.5,
            "dissent": "",
        }
        with (
            patch("little_loops.advisor.resolve_host_named", return_value=_make_runner()),
            patch("little_loops.advisor.run_blocking_json", return_value=verdict_dict),
            patch("little_loops.host_runner.dispatch_anthropic_request") as mock_dispatch,
            patch("little_loops.cli.loop._helpers.derive_input_hash") as mock_hash,
        ):
            consult(
                question="q",
                signal="user_requested",
                config=config,
                main_host="claude-code",
                main_model="opus",
            )
        mock_dispatch.assert_not_called()
        mock_hash.assert_not_called()

    def test_signal_required_by_caller_contract(self):
        # consult() itself has no default for `signal` — a TypeError at the
        # call boundary is the enforcement mechanism for "no unsignalled
        # consult path" at the Python level (main_advise enforces it via
        # argparse `required=True` at the CLI level).
        with pytest.raises(TypeError):
            consult(question="q", config=_FakeConfig(AdvisorConfig(host="claude-code")))  # type: ignore[call-arg]
