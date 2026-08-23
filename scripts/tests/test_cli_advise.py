"""Tests for the ll-advise CLI (FEAT-3120)."""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

from little_loops.cli.advise import main_advise
from little_loops.config.orchestration import AdvisorConfig
from little_loops.host_runner import HostInvocation

_VERDICT_DICT = {
    "recommendation": "do X",
    "risks": ["r1"],
    "confidence": 0.9,
    "dissent": "none",
}


def _make_runner():
    return type(
        "FakeRunner",
        (),
        {
            "name": "claude-code",
            "build_blocking_json": lambda self, *, prompt, model=None, json_schema=None: (
                HostInvocation(binary="claude", args=["-p", prompt])
            ),
        },
    )()


class TestMainAdvise:
    def test_requires_signal(self) -> None:
        with (
            patch.object(sys, "argv", ["ll-advise", "--question", "q"]),
            pytest.raises(SystemExit),
        ):
            main_advise()

    def test_success_prints_exact_json_keys(self, capsys: pytest.CaptureFixture) -> None:
        with (
            patch.object(
                sys,
                "argv",
                [
                    "ll-advise",
                    "--signal",
                    "user_requested",
                    "--question",
                    "q",
                    "--host",
                    "claude-code",
                    "--model",
                    "opus",
                    "--json",
                ],
            ),
            patch("little_loops.advisor.resolve_host_named", return_value=_make_runner()),
            patch("little_loops.advisor.run_blocking_json", return_value=_VERDICT_DICT),
        ):
            result = main_advise()

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert set(payload) == {
            "recommendation",
            "risks",
            "confidence",
            "dissent",
            "signal",
            "host",
            "model",
        }
        assert payload["signal"] == "user_requested"
        assert payload["host"] == "claude-code"
        assert payload["model"] == "opus"

    def test_unwired_host_fails_soft_no_traceback(self) -> None:
        # Model: test_cli_doctor.py::test_skips_probe_when_binary_not_detected —
        # patch resolve_host at its defining module namespace, assert the
        # subprocess-level call site is never reached.
        with (
            patch.object(
                sys,
                "argv",
                [
                    "ll-advise",
                    "--signal",
                    "user_requested",
                    "--question",
                    "q",
                    "--host",
                    "opencode",
                ],
            ),
            patch("subprocess.run") as mock_run,
        ):
            result = main_advise()

        assert result != 0
        mock_run.assert_not_called()

    def test_no_advisor_configured_fails_soft(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys,
            "argv",
            ["ll-advise", "--signal", "user_requested", "--question", "q"],
        ):
            result = main_advise()
        assert result != 0

    def test_capability_floor_violation_exits_nonzero_no_consult(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                [
                    "ll-advise",
                    "--signal",
                    "user_requested",
                    "--question",
                    "q",
                    "--host",
                    "claude-code",
                    "--model",
                    "haiku",
                    "--main-host",
                    "claude-code",
                    "--main-model",
                    "opus",
                ],
            ),
            patch("little_loops.advisor.resolve_host_named") as mock_resolve,
        ):
            result = main_advise()
        assert result != 0
        mock_resolve.assert_not_called()

    def test_advisor_host_env_independent_of_orchestration_host_cli(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        # AC #3: advisor.host differing from orchestration.host_cli still
        # invokes the advisor host's binary, and LL_HOST_CLI is unchanged.
        with (
            patch.object(
                sys,
                "argv",
                [
                    "ll-advise",
                    "--signal",
                    "user_requested",
                    "--question",
                    "q",
                    "--host",
                    "claude-code",
                    "--model",
                    "opus",
                    "--main-host",
                    "codex",
                    "--main-model",
                    "opus",
                    "--json",
                ],
            ),
            patch("little_loops.advisor.resolve_host_named", return_value=_make_runner()) as mock_r,
            patch("little_loops.advisor.run_blocking_json", return_value=_VERDICT_DICT),
        ):
            import os

            before = os.environ.get("LL_HOST_CLI")
            result = main_advise()
            after = os.environ.get("LL_HOST_CLI")

        assert result == 0
        assert before == after
        mock_r.assert_called_once_with("claude-code")


def test_advisor_config_default_host_is_none() -> None:
    assert AdvisorConfig().host is None
