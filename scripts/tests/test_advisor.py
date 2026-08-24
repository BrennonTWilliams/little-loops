"""Tests for advisor module."""

import ast
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.advisor import (
    MODEL_RANKS,
    AdvisorNotConfigured,
    AdvisorVerdict,
    CapabilityFloorViolation,
    TaskKey,
    check_floor,
    consult,
    consult_for_trigger,
    rank_model,
    record_consult,
    resolve_task_key,
    should_consult,
)
from little_loops.config.orchestration import AdvisorConfig
from little_loops.host_runner import BlockingJsonError, HostInvocation, HostNotConfigured


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


class TestResolveTaskKey:
    """Precedence: LL_ISSUE_ID -> LL_LOOP_RUN_ID -> session ID. Hermetic — every
    test passes an explicit env dict, never reads live os.environ."""

    def test_issue_id_tier(self):
        key = resolve_task_key(env={"LL_ISSUE_ID": "BUG-123"})
        assert key == TaskKey(kind="issue", value="BUG-123")

    def test_loop_run_id_tier(self):
        key = resolve_task_key(env={"LL_LOOP_RUN_ID": "my-loop-20260101T000000"})
        assert key == TaskKey(kind="loop_run", value="my-loop-20260101T000000")

    def test_issue_id_wins_over_loop_run_id(self):
        key = resolve_task_key(
            env={"LL_ISSUE_ID": "BUG-123", "LL_LOOP_RUN_ID": "my-loop-20260101T000000"}
        )
        assert key == TaskKey(kind="issue", value="BUG-123")

    def test_session_id_tier_from_env(self):
        key = resolve_task_key(env={"CLAUDE_SESSION_ID": "sess-abc"})
        assert key == TaskKey(kind="session", value="sess-abc")

    def test_no_env_vars_falls_back_to_session_lookup(self):
        with patch("little_loops.session_log.get_current_session_id", return_value="fallback-sess"):
            key = resolve_task_key(env={})
        assert key == TaskKey(kind="session", value="fallback-sess")

    def test_no_env_vars_and_no_session_falls_back_to_unknown(self):
        with patch("little_loops.session_log.get_current_session_id", return_value=None):
            key = resolve_task_key(env={})
        assert key == TaskKey(kind="session", value="unknown")


class TestRecordConsult:
    def test_first_call_returns_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        key = TaskKey(kind="issue", value="BUG-1")
        assert record_consult(key) == 1

    def test_increments_across_calls(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        key = TaskKey(kind="issue", value="BUG-1")
        assert record_consult(key) == 1
        assert record_consult(key) == 2
        assert record_consult(key) == 3

    def test_distinct_keys_have_independent_counters(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        a = TaskKey(kind="issue", value="BUG-1")
        b = TaskKey(kind="issue", value="BUG-2")
        assert record_consult(a) == 1
        assert record_consult(b) == 1
        assert record_consult(a) == 2

    def test_counter_survives_a_subprocess_boundary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        key = TaskKey(kind="issue", value="BUG-1")
        assert record_consult(key) == 1

        scripts_root = Path(__file__).parent.parent
        script = (
            f"import sys; sys.path.insert(0, {str(scripts_root)!r})\n"
            "from little_loops.advisor import TaskKey, record_consult\n"
            "print(record_consult(TaskKey(kind='issue', value='BUG-1')))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "2"
        assert record_consult(key) == 3


class TestShouldConsult:
    def test_false_when_disabled(self):
        config = _FakeConfig(AdvisorConfig(enabled=False, triggers=["confidence_gate"]))
        assert should_consult("confidence_gate", config, task_key=TaskKey("session", "s1")) is False

    def test_false_when_trigger_not_allowed(self):
        config = _FakeConfig(AdvisorConfig(enabled=True, triggers=["pre_done"]))
        assert should_consult("confidence_gate", config, task_key=TaskKey("session", "s1")) is False

    def test_true_when_enabled_and_trigger_allowed_and_budget_free(self):
        config = _FakeConfig(
            AdvisorConfig(enabled=True, triggers=["confidence_gate"], max_consults_per_task=3)
        )
        assert should_consult("confidence_gate", config, task_key=TaskKey("session", "s1")) is True

    def test_false_when_budget_exhausted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(
            AdvisorConfig(enabled=True, triggers=["confidence_gate"], max_consults_per_task=1)
        )
        key = TaskKey(kind="issue", value="BUG-1")
        record_consult(key)
        assert should_consult("confidence_gate", config, task_key=key) is False

    def test_manual_ignores_disabled(self):
        config = _FakeConfig(AdvisorConfig(enabled=False, triggers=[]))
        assert (
            should_consult("user_requested", config, task_key=TaskKey("session", "s1"), manual=True)
            is True
        )

    def test_manual_ignores_trigger_allowlist(self):
        config = _FakeConfig(AdvisorConfig(enabled=True, triggers=["pre_done"]))
        assert (
            should_consult("user_requested", config, task_key=TaskKey("session", "s1"), manual=True)
            is True
        )

    def test_manual_still_respects_budget(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(AdvisorConfig(enabled=False, triggers=[], max_consults_per_task=1))
        key = TaskKey(kind="issue", value="BUG-1")
        record_consult(key)
        assert should_consult("user_requested", config, task_key=key, manual=True) is False

    def test_fail_soft_on_config_error(self):
        class _BrokenConfig:
            @property
            def advisor(self):
                raise RuntimeError("config read failed")

        assert (
            should_consult("confidence_gate", _BrokenConfig(), task_key=TaskKey("session", "s1"))
            is False
        )


class TestConsultForTrigger:
    def test_returns_verdict_on_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(
            AdvisorConfig(
                enabled=True, host="claude-code", model="opus", triggers=["confidence_gate"]
            )
        )
        verdict_dict = {
            "recommendation": "do X",
            "risks": [],
            "confidence": 0.9,
            "dissent": "",
        }
        with (
            patch("little_loops.advisor.resolve_host_named", return_value=_make_runner()),
            patch("little_loops.advisor.run_blocking_json", return_value=verdict_dict),
        ):
            outcome = consult_for_trigger(
                "confidence_gate",
                question="q",
                config=config,
                main_host="claude-code",
                main_model="opus",
            )
        assert outcome.verdict is not None
        assert outcome.verdict.recommendation == "do X"
        assert outcome.skipped_reason is None

    def test_disabled_skips_without_calling_consult(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(AdvisorConfig(enabled=False, triggers=["confidence_gate"]))
        with patch("little_loops.advisor.consult") as mock_consult:
            outcome = consult_for_trigger("confidence_gate", question="q", config=config)
        mock_consult.assert_not_called()
        assert outcome.verdict is None
        assert outcome.skipped_reason == "disabled"

    def test_trigger_not_allowed_skips(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(AdvisorConfig(enabled=True, triggers=["pre_done"]))
        with patch("little_loops.advisor.consult") as mock_consult:
            outcome = consult_for_trigger("confidence_gate", question="q", config=config)
        mock_consult.assert_not_called()
        assert outcome.skipped_reason == "trigger_not_allowed"

    def test_budget_exhausted_skips(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(
            AdvisorConfig(enabled=True, triggers=["confidence_gate"], max_consults_per_task=1)
        )
        record_consult(resolve_task_key(env={"LL_ISSUE_ID": "BUG-1"}))
        with (
            patch("little_loops.advisor.resolve_task_key", return_value=TaskKey("issue", "BUG-1")),
            patch("little_loops.advisor.consult") as mock_consult,
        ):
            outcome = consult_for_trigger("confidence_gate", question="q", config=config)
        mock_consult.assert_not_called()
        assert outcome.skipped_reason == "budget_exhausted"

    def test_reserve_before_consult_spends_budget_even_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(
            AdvisorConfig(
                enabled=True, host="claude-code", model="opus", triggers=["confidence_gate"]
            )
        )
        key = TaskKey(kind="issue", value="BUG-1")
        with (
            patch("little_loops.advisor.resolve_task_key", return_value=key),
            patch(
                "little_loops.advisor.consult",
                side_effect=AdvisorNotConfigured("not configured"),
            ),
        ):
            consult_for_trigger("confidence_gate", question="q", config=config)
        from little_loops.advisor import _current_spent

        assert _current_spent(key) == 1

    @pytest.mark.parametrize(
        "exc,expected_reason",
        [
            (AdvisorNotConfigured("nope"), "not_configured"),
            (
                CapabilityFloorViolation(
                    check_floor("claude-code", "haiku", "claude-code", "opus")
                ),
                "floor_violation",
            ),
            (HostNotConfigured("no host"), "failed"),
            (BlockingJsonError("timed out", {"timeout": True}), "timeout"),
            (BlockingJsonError("boom", {}), "failed"),
        ],
    )
    def test_maps_each_exception_to_skipped_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc, expected_reason
    ):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(
            AdvisorConfig(
                enabled=True, host="claude-code", model="opus", triggers=["confidence_gate"]
            )
        )
        with patch("little_loops.advisor.consult", side_effect=exc):
            outcome = consult_for_trigger("confidence_gate", question="q", config=config)
        assert outcome.verdict is None
        assert outcome.skipped_reason == expected_reason
        assert outcome.error is not None

    def test_passes_through_config_main_host_main_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(
            AdvisorConfig(
                enabled=True, host="claude-code", model="opus", triggers=["confidence_gate"]
            )
        )
        with patch("little_loops.advisor.consult") as mock_consult:
            mock_consult.return_value = AdvisorVerdict(
                recommendation="r",
                risks=[],
                confidence=0.5,
                dissent="",
                signal="confidence_gate",
                host="claude-code",
                model="opus",
            )
            consult_for_trigger(
                "confidence_gate",
                question="q",
                context="ctx",
                config=config,
                main_host="codex",
                main_model="gpt-5",
            )
        mock_consult.assert_called_once_with(
            question="q",
            signal="confidence_gate",
            context="ctx",
            config=config,
            main_host="codex",
            main_model="gpt-5",
        )

    def test_manual_routes_ll_advise_style_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(AdvisorConfig(enabled=False, host="claude-code", model="opus"))
        with patch("little_loops.advisor.consult") as mock_consult:
            mock_consult.return_value = AdvisorVerdict(
                recommendation="r",
                risks=[],
                confidence=0.5,
                dissent="",
                signal="user_requested",
                host="claude-code",
                model="opus",
            )
            outcome = consult_for_trigger(
                "user_requested", question="q", config=config, manual=True
            )
        mock_consult.assert_called_once()
        assert outcome.verdict is not None


class TestConsultForTriggerTelemetry:
    """FEAT-3300: consult_for_trigger() writes exactly one advisor_consults row."""

    def _rows(self, db_path: Path) -> list:
        from little_loops.history_reader import query_advisor_consults

        return query_advisor_consults(db_path)

    def test_issued_consult_writes_one_row_with_latency(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(
            AdvisorConfig(
                enabled=True, host="claude-code", model="opus", triggers=["confidence_gate"]
            )
        )
        verdict_dict = {
            "recommendation": "do X",
            "risks": [],
            "confidence": 0.9,
            "dissent": "",
        }
        with (
            patch("little_loops.advisor.resolve_host_named", return_value=_make_runner()),
            patch("little_loops.advisor.run_blocking_json", return_value=verdict_dict),
        ):
            consult_for_trigger(
                "confidence_gate",
                question="q",
                config=config,
                main_host="claude-code",
                main_model="opus",
            )

        from little_loops.session_store import DEFAULT_DB_PATH

        rows = self._rows(DEFAULT_DB_PATH)
        assert len(rows) == 1
        assert rows[0].outcome == "issued"
        assert rows[0].latency_ms is not None
        assert rows[0].input_tokens is None
        assert rows[0].output_tokens is None

    @pytest.mark.parametrize(
        "exc,expected_reason",
        [
            (AdvisorNotConfigured("nope"), "not_configured"),
            (
                CapabilityFloorViolation(
                    check_floor("claude-code", "haiku", "claude-code", "opus")
                ),
                "floor_violation",
            ),
            (HostNotConfigured("no host"), "failed"),
            (BlockingJsonError("timed out", {"timeout": True}), "timeout"),
            (BlockingJsonError("boom", {}), "failed"),
        ],
    )
    def test_each_exception_path_writes_one_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc, expected_reason
    ):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(
            AdvisorConfig(
                enabled=True, host="claude-code", model="opus", triggers=["confidence_gate"]
            )
        )
        with patch("little_loops.advisor.consult", side_effect=exc):
            consult_for_trigger("confidence_gate", question="q", config=config)

        from little_loops.session_store import DEFAULT_DB_PATH

        rows = self._rows(DEFAULT_DB_PATH)
        assert len(rows) == 1
        assert rows[0].outcome == expected_reason

    def test_disabled_skip_writes_one_row(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(AdvisorConfig(enabled=False, triggers=["confidence_gate"]))
        consult_for_trigger("confidence_gate", question="q", config=config)

        from little_loops.session_store import DEFAULT_DB_PATH

        rows = self._rows(DEFAULT_DB_PATH)
        assert len(rows) == 1
        assert rows[0].outcome == "disabled"

    def test_failing_write_does_not_alter_outcome(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        config = _FakeConfig(
            AdvisorConfig(
                enabled=True, host="claude-code", model="opus", triggers=["confidence_gate"]
            )
        )
        verdict_dict = {
            "recommendation": "do X",
            "risks": [],
            "confidence": 0.9,
            "dissent": "",
        }
        with (
            patch("little_loops.advisor.resolve_host_named", return_value=_make_runner()),
            patch("little_loops.advisor.run_blocking_json", return_value=verdict_dict),
            patch(
                "little_loops.session_store.write_advisor_consult",
                side_effect=RuntimeError("boom"),
            ),
        ):
            outcome = consult_for_trigger(
                "confidence_gate",
                question="q",
                config=config,
                main_host="claude-code",
                main_model="opus",
            )
        assert outcome.verdict is not None
        assert outcome.verdict.recommendation == "do X"


class TestConsultExclusivity:
    """AC #5: no code path other than `consult_for_trigger` calls `consult()`.

    AST-based (not grep-based, per the ENH-3184 spawn-site-guard pattern),
    pinned per-module call-site table, scoped to production modules only —
    ``scripts/tests/test_advisor.py``'s ``TestConsult`` direct calls are
    valid low-level unit coverage of ``consult()`` itself and are excluded.
    """

    _ALLOWED_CALLERS: dict[str, int] = {
        "little_loops/advisor.py": 1,  # consult_for_trigger's own call
    }
    _MODULES_TO_SCAN = [
        "little_loops/advisor.py",
        "little_loops/cli/advise.py",
    ]

    @staticmethod
    def _count_consult_calls(source: str) -> int:
        tree = ast.parse(source)
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "consult":
                    count += 1
                elif isinstance(func, ast.Attribute) and func.attr == "consult":
                    count += 1
        return count

    def test_only_consult_for_trigger_calls_consult(self):
        scripts_root = Path(__file__).parent.parent
        for relpath in self._MODULES_TO_SCAN:
            source = (scripts_root / relpath).read_text()
            found = self._count_consult_calls(source)
            expected = self._ALLOWED_CALLERS.get(relpath, 0)
            assert found == expected, (
                f"{relpath}: found {found} call(s) to consult(), expected {expected} "
                "(AC #5: only consult_for_trigger may call consult())"
            )
