"""Tests for little_loops.runner_spec (ENH-2668).

Covers:
- :class:`ActionSpec` is a frozen value object (establishes the same
  convention as :class:`~little_loops.host_runner.HostInvocation`).
- ``RunnerResult`` remains importable from its pre-extraction location
  (``little_loops.cli.harness``) via re-export.
- Dispatch-table completeness: all five ll-harness runner kinds plus
  ``RunnerType.LOOP`` exist on the enum.
- ``run_action()`` produces byte-for-byte identical ``RunnerResult`` shapes
  to the pre-extraction per-CLI implementations, for each dispatched runner
  type (skill/cmd/mcp/prompt).
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.host_runner import GH_SCOPED_NO_TOKEN, AutomationContext, HostInvocation
from little_loops.runner_spec import ActionSpec, RunnerResult, RunnerType, run_action


def _make_completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class FakeRunner:
    def build_streaming(self, *, prompt: str, **_: object) -> HostInvocation:
        return HostInvocation(binary="claude", args=["-p", prompt])

    def build_blocking_json(self, *, prompt: str, model: str | None = None) -> HostInvocation:
        return HostInvocation(binary="claude", args=["-p", prompt])


class CapturingRunner:
    """A FakeRunner whose build_streaming() records the kwargs it received.

    ENH-3097 AC 13: the plain ``FakeRunner`` above absorbs automation= into
    ``**_: object`` without a signature change, so it keeps existing tests
    green — but it discards the value, making it unusable for asserting what
    the resolved automation context carries. This variant captures it.
    """

    def __init__(self) -> None:
        self.build_streaming_calls: list[dict] = []

    def build_streaming(self, *, prompt: str, **kwargs: object) -> HostInvocation:
        self.build_streaming_calls.append(kwargs)
        return HostInvocation(binary="claude", args=["-p", prompt])


class TestActionSpecFrozen:
    def test_action_spec_is_frozen(self) -> None:
        """Mutating an ActionSpec must raise FrozenInstanceError (host_runner convention)."""
        spec = ActionSpec(name="x", runner=RunnerType.CMD, target="echo hi")
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.target = "echo bye"  # type: ignore[misc]

    def test_timeout_none_is_constructible(self) -> None:
        """BUG-2928: timeout widened from int to int | None to admit "no outer bound"."""
        spec = ActionSpec(name="x", runner=RunnerType.LOOP, target="loops/x.yaml", timeout=None)
        assert spec.timeout is None


class TestDefaultTimeoutFor:
    """BUG-2928: per-runner default subprocess timeout resolved in cli/queue.py."""

    def test_loop_default_is_none(self) -> None:
        from little_loops.cli.queue import _default_timeout_for

        assert _default_timeout_for(RunnerType.LOOP) is None

    @pytest.mark.parametrize(
        "runner", [RunnerType.SKILL, RunnerType.CMD, RunnerType.MCP, RunnerType.PROMPT]
    )
    def test_non_loop_defaults_are_concrete_ints(self, runner: RunnerType) -> None:
        """CMD/MCP dispatch handlers do raw deadline arithmetic and raise TypeError on None."""
        from little_loops.cli.queue import _default_timeout_for

        result = _default_timeout_for(runner)
        assert result == 120
        assert result is not None


class TestRunnerResultReexport:
    def test_runner_result_importable_from_harness(self) -> None:
        """RunnerResult must stay importable from its pre-extraction location."""
        from little_loops.cli.harness import RunnerResult as HarnessRunnerResult

        assert HarnessRunnerResult is RunnerResult


class TestRunnerTypeCompleteness:
    def test_all_harness_runner_kinds_present(self) -> None:
        names = {member.value for member in RunnerType}
        assert {"skill", "cmd", "mcp", "prompt", "dsl", "loop"} <= names

    def test_loop_not_in_dispatch_table(self) -> None:
        """RunnerType.LOOP is intentionally excluded from run_action()'s dispatch."""
        spec = ActionSpec(name="x", runner=RunnerType.LOOP, target="loops/x.yaml")
        with pytest.raises(ValueError, match="LOOP"):
            run_action(spec)


class TestIsStochasticRunner:
    """ENH-3415 D6: classification of every dispatched RunnerType."""

    def test_skill_and_prompt_are_stochastic(self) -> None:
        from little_loops.runner_spec import is_stochastic_runner

        assert is_stochastic_runner(RunnerType.SKILL) is True
        assert is_stochastic_runner(RunnerType.PROMPT) is True

    def test_cmd_and_mcp_are_deterministic(self) -> None:
        from little_loops.runner_spec import is_stochastic_runner

        assert is_stochastic_runner(RunnerType.CMD) is False
        assert is_stochastic_runner(RunnerType.MCP) is False

    def test_dsl_is_stochastic(self) -> None:
        from little_loops.runner_spec import is_stochastic_runner

        assert is_stochastic_runner(RunnerType.DSL) is True

    def test_loop_excluded_raises(self) -> None:
        from little_loops.runner_spec import is_stochastic_runner

        with pytest.raises(KeyError):
            is_stochastic_runner(RunnerType.LOOP)

    def test_every_dispatched_runner_classified(self) -> None:
        """Completeness: every RunnerType except LOOP has a classification."""
        from little_loops.runner_spec import is_stochastic_runner

        for member in RunnerType:
            if member is RunnerType.LOOP:
                continue
            assert isinstance(is_stochastic_runner(member), bool)


class TestRunActionDispatch:
    def test_skill_dispatch_matches_legacy_shape(self) -> None:
        spec = ActionSpec(
            name="check-code",
            runner=RunnerType.SKILL,
            target="check-code",
            args={"runner_args": []},
            timeout=120,
        )
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="ok")),
        ):
            result = run_action(spec)

        assert result == RunnerResult(stdout="ok", stderr="", exit_code=0)

    def test_skill_dispatch_timeout(self) -> None:
        spec = ActionSpec(name="x", runner=RunnerType.SKILL, target="x", timeout=1)
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1)),
        ):
            result = run_action(spec)

        assert result.timed_out is True
        assert result.exit_code == 2

    def test_prompt_dispatch_matches_legacy_shape(self) -> None:
        spec = ActionSpec(
            name="p", runner=RunnerType.PROMPT, target="What is 2+2?", args={"model": None}
        )
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="4")),
        ):
            result = run_action(spec)

        assert result == RunnerResult(stdout="4", stderr="", exit_code=0)

    def test_prompt_dispatch_merges_invocation_env(self) -> None:
        """ENH-3184 AC4: _run_prompt() previously dropped invocation.env
        entirely; it must now merge it via project_child_env(), matching
        _run_skill()'s existing behaviour."""
        spec = ActionSpec(
            name="p", runner=RunnerType.PROMPT, target="What is 2+2?", args={"model": None}
        )

        class EnvRunner:
            def build_blocking_json(self, *, prompt: str, model: str | None = None):
                return HostInvocation(binary="claude", args=["-p", prompt], env={"FOO": "bar"})

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=EnvRunner()),
            patch(
                "subprocess.run", return_value=_make_completed(returncode=0, stdout="4")
            ) as mock_run,
        ):
            run_action(spec)

        assert mock_run.call_args.kwargs["env"]["FOO"] == "bar"

    def test_mcp_dispatch_matches_legacy_shape(self) -> None:
        spec = ActionSpec(
            name="mcp",
            runner=RunnerType.MCP,
            target="srv:tool",
            args={"mcp_params": {"a": 1}},
        )
        with patch(
            "little_loops.runner_spec.call_mcp_tool", return_value=({"ok": True}, 0)
        ) as mock_call:
            result = run_action(spec)

        mock_call.assert_called_once_with("srv", "tool", {"a": 1}, timeout=120)
        assert result.exit_code == 0
        assert result.stdout == '{"ok": true}'

    def test_cmd_dispatch_matches_legacy_shape(self) -> None:
        spec = ActionSpec(name="echo hi", runner=RunnerType.CMD, target="echo hi", timeout=5)
        result = run_action(spec)
        assert result.exit_code == 0
        assert result.stdout == "hi\n"

    def test_cmd_dispatch_sets_ll_python_env(self) -> None:
        """ENH-3365: _run_cmd()'s bash -c spawn must expose
        LL_PYTHON=sys.executable so a heredoc invoking
        $${LL_PYTHON:-python3} always resolves to the exact interpreter
        running the loop, not whatever `python3` is first on PATH.
        """
        spec = ActionSpec(
            name="print ll_python", runner=RunnerType.CMD, target="echo $LL_PYTHON", timeout=5
        )
        result = run_action(spec)
        assert result.stdout.strip() == sys.executable

    def test_cmd_dispatch_no_scopes_keeps_full_inherit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ENH-3234 AC5: an undeclared ActionSpec keeps today's coarse (full-inherit)
        behavior — env_allow stays None, so an arbitrary ambient var still passes through."""
        monkeypatch.setenv("ZZ_TEST_UNDECLARED", "present")
        spec = ActionSpec(
            name="x", runner=RunnerType.CMD, target="echo $ZZ_TEST_UNDECLARED", timeout=5
        )
        result = run_action(spec)
        assert result.stdout.strip() == "present"

    def test_cmd_dispatch_declared_scope_allows_its_vars_denies_others(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ENH-3234 AC7.2: a declared scope's env vars survive; an undeclared
        credential var is absent from the shell action's environment."""
        monkeypatch.setenv("GH_TOKEN", "gh-secret")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
        spec = ActionSpec(
            name="x",
            runner=RunnerType.CMD,
            target="echo ${GH_TOKEN:-absent}:${ANTHROPIC_API_KEY:-absent}",
            timeout=5,
            scopes=frozenset({"github"}),
        )
        result = run_action(spec)
        assert result.stdout.strip() == "gh-secret:absent"

    def test_cmd_dispatch_unknown_scope_fails_loud_and_spawns_nothing(self) -> None:
        """ENH-3234: an unknown scope name returns a failed RunnerResult naming the
        scope, and never reaches subprocess.Popen (queue worker must not die on
        one bad entry — resolution happens inside _run_cmd(), not at construction)."""
        spec = ActionSpec(
            name="x",
            runner=RunnerType.CMD,
            target="echo should-not-run",
            timeout=5,
            scopes=frozenset({"nonexistent-scope"}),
        )
        with patch("subprocess.Popen") as mock_popen:
            result = run_action(spec)

        mock_popen.assert_not_called()
        assert result.exit_code != 0
        assert "nonexistent-scope" in (result.error or "")

    def test_cmd_dispatch_github_scope_redirects_gh_config_dir_and_injects_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-3400: a declared 'github' scope must get the same gh-isolation
        wiring as the FSM shell path — GH_CONFIG_DIR redirected to a fresh
        ll-gh-* tempdir, GH_TOKEN injected from gh_scope_extra()."""
        monkeypatch.setenv("GH_TOKEN", "gh-secret")
        spec = ActionSpec(
            name="x",
            runner=RunnerType.CMD,
            target="echo should-not-run",
            timeout=5,
            scopes=frozenset({"github"}),
        )
        proc = MagicMock()
        proc.stdout = None
        proc.stderr = None
        proc.returncode = 0
        proc.wait.return_value = None
        with patch("little_loops.runner_spec.subprocess.Popen", return_value=proc) as mock_popen:
            result = run_action(spec)

        assert result.exit_code == 0
        env = mock_popen.call_args.kwargs["env"]
        assert env["GH_TOKEN"] == "gh-secret"
        assert env["GH_CONFIG_DIR"].startswith(str(Path(tempfile.gettempdir())))
        assert "ll-gh-" in env["GH_CONFIG_DIR"]

    def test_cmd_dispatch_empty_scopes_redirects_config_dir_no_token(self) -> None:
        """BUG-3400/BUG-3402: scopes=frozenset() still gets the GH_CONFIG_DIR
        redirect (declaring-but-not-github denies the ambient keyring
        session too) and the GH_SCOPED_NO_TOKEN sentinel as GH_TOKEN, not
        the operator's real token — mirrors
        test_shell_declared_empty_scopes_redirects_config_dir_no_token."""
        spec = ActionSpec(
            name="x",
            runner=RunnerType.CMD,
            target="echo should-not-run",
            timeout=5,
            scopes=frozenset(),
        )
        proc = MagicMock()
        proc.stdout = None
        proc.stderr = None
        proc.returncode = 0
        proc.wait.return_value = None
        with patch("little_loops.runner_spec.subprocess.Popen", return_value=proc) as mock_popen:
            result = run_action(spec)

        assert result.exit_code == 0
        env = mock_popen.call_args.kwargs["env"]
        assert "GH_CONFIG_DIR" in env
        assert env["GH_TOKEN"] == GH_SCOPED_NO_TOKEN

    def test_cmd_dispatch_gh_scope_extra_failure_spawns_nothing_and_cleans_up(self) -> None:
        """BUG-3400: a RuntimeError from gh_scope_extra() (mirrors the FSM
        path's failure contract) returns exit_code=2 without spawning, and
        leaves no ll-gh-* tempdir behind."""
        spec = ActionSpec(
            name="x",
            runner=RunnerType.CMD,
            target="echo should-not-run",
            timeout=5,
            scopes=frozenset({"github"}),
        )
        leaked_dirs: list[str] = []

        def _fake_gh_scope_extra(config_dir: Path, *, with_token: bool) -> dict[str, str]:
            leaked_dirs.append(str(config_dir))
            raise RuntimeError("no token available")

        with (
            patch("little_loops.runner_spec.gh_scope_extra", side_effect=_fake_gh_scope_extra),
            patch("subprocess.Popen") as mock_popen,
        ):
            result = run_action(spec)

        mock_popen.assert_not_called()
        assert result.exit_code == 2
        assert "no token available" in (result.error or "")
        assert leaked_dirs and not Path(leaked_dirs[0]).exists()

    def test_cmd_dispatch_writes_credential_scope_audit_row_with_run_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-3400 AC: a declaring CMD dispatch writes exactly one
        credential_scope_events row, keyed by the caller-supplied run_id
        when given (mirrors ll-queue's drain loop passing entry.id)."""
        db_path = tmp_path / "history.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(db_path))
        monkeypatch.setenv("GH_TOKEN", "gh-secret")
        spec = ActionSpec(
            name="my-spec",
            runner=RunnerType.CMD,
            target="echo hi",
            timeout=5,
            scopes=frozenset({"github"}),
        )
        result = run_action(spec, run_id="queue-entry-123")
        assert result.exit_code == 0

        from little_loops.session_store import recent

        rows = recent(db_path, kind="credential_scope")
        assert len(rows) == 1
        assert rows[0]["run_id"] == "queue-entry-123"
        assert rows[0]["state"] == "my-spec"

    def test_cmd_dispatch_no_scopes_writes_no_audit_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An undeclared spec (scopes=None) writes no credential_scope_events row."""
        db_path = tmp_path / "history.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(db_path))
        spec = ActionSpec(name="x", runner=RunnerType.CMD, target="echo hi", timeout=5)
        result = run_action(spec)
        assert result.exit_code == 0

        from little_loops.session_store import recent

        rows = recent(db_path, kind="credential_scope")
        assert rows == []

    def test_cmd_hang_before_stdout_eof_times_out(self) -> None:
        """BUG-2777: a process that holds stdout open without exiting must still
        time out — the drain loop must not block until EOF before checking the
        deadline. Mirrors test_fsm_runners.py::test_hanging_process_timeout_fires_during_read.
        """
        proc = MagicMock()
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        proc.returncode = None
        proc.pid = 12345
        proc.wait.return_value = None
        proc.kill.return_value = None

        sel = MagicMock()
        sel.get_map.return_value = {"pipe": "data"}  # never empty -> loop continues
        sel.select.return_value = []  # no data ever ready
        sel.close.return_value = None
        sel.register.return_value = None

        spec = ActionSpec(name="hang", runner=RunnerType.CMD, target="sleep 9999", timeout=0)

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.runner_spec._kill_process_group") as mock_killpg,
        ):
            result = run_action(spec)

        assert result.timed_out is True
        assert result.exit_code == 2
        mock_killpg.assert_called_once_with(proc)

    def test_cmd_oversized_target_spawns(self) -> None:
        """BUG-3439: sibling pin to test_fsm_runners.py's shell-path pin —
        a target above Linux's per-argument MAX_ARG_STRLEN (131072 B) must
        still spawn via _run_cmd's temp-file substitution, not
        ``bash -c <target>``. No platform skip: passed on darwin before the
        fix, fails on Linux only before it. Oversize lives in a bash variable
        assignment so no child exec re-trips MAX_ARG_STRLEN on a single argv
        element (see the shell-path pin for the full rationale)."""
        payload = "x" * 140_000
        target = f"payload='{payload}'; echo ${{#payload}}"
        assert len(target) > 131072

        spec = ActionSpec(name="oversized", runner=RunnerType.CMD, target=target, timeout=30)
        result = run_action(spec)

        assert result.exit_code == 0, result.stderr
        assert result.stdout.strip() == "140000"

    def test_cmd_script_tempfile_removed_after_run(self) -> None:
        """No ``ll-action-*.sh`` temp file survives a successful _run_cmd call."""
        before = set(Path(tempfile.gettempdir()).glob("ll-action-*.sh"))

        spec = ActionSpec(name="echo hi", runner=RunnerType.CMD, target="echo hi", timeout=5)
        result = run_action(spec)

        assert result.exit_code == 0
        after = set(Path(tempfile.gettempdir()).glob("ll-action-*.sh"))
        assert after == before

    def test_cmd_script_tempfile_removed_after_timeout(self) -> None:
        """No ``ll-action-*.sh`` temp file survives the timeout path either."""
        before = set(Path(tempfile.gettempdir()).glob("ll-action-*.sh"))

        proc = MagicMock()
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        proc.returncode = None
        proc.pid = 12345
        proc.wait.return_value = None
        proc.kill.return_value = None

        sel = MagicMock()
        sel.get_map.return_value = {"pipe": "data"}
        sel.select.return_value = []
        sel.close.return_value = None
        sel.register.return_value = None

        spec = ActionSpec(name="hang", runner=RunnerType.CMD, target="sleep 9999", timeout=0)

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.runner_spec._kill_process_group"),
        ):
            result = run_action(spec)

        assert result.timed_out is True
        after = set(Path(tempfile.gettempdir()).glob("ll-action-*.sh"))
        assert after == before


class TestRunnerResultEfficiencyFields:
    """ENH-3464: _run_skill()'s default blocking branch and _run_prompt()
    parse tokens/tool_calls post hoc off captured stdout via
    usage_from_stream_lines()."""

    def test_skill_dispatch_populates_tokens_and_tool_calls(self) -> None:
        stdout = "\n".join(
            [
                '{"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}',
                (
                    '{"type": "assistant", "message": {"content": ['
                    '{"type": "tool_use", "id": "tu_1", "name": "Read", "input": {}}]}}'
                ),
                (
                    '{"type": "result", "usage": {"input_tokens": 100, "output_tokens": 50, '
                    '"cache_read_input_tokens": 10, "cache_creation_input_tokens": 5}}'
                ),
            ]
        )
        spec = ActionSpec(
            name="check-code",
            runner=RunnerType.SKILL,
            target="check-code",
            args={"runner_args": []},
            timeout=120,
        )
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout=stdout)),
        ):
            result = run_action(spec)

        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cache_read_tokens == 10
        assert result.cache_creation_tokens == 5
        assert result.tool_calls == 1

    def test_skill_dispatch_non_json_stdout_leaves_fields_none(self) -> None:
        spec = ActionSpec(
            name="check-code",
            runner=RunnerType.SKILL,
            target="check-code",
            args={"runner_args": []},
            timeout=120,
        )
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="ok")),
        ):
            result = run_action(spec)

        assert result.input_tokens is None
        assert result.tool_calls is None

    def test_prompt_dispatch_populates_tokens_but_not_tool_calls(self) -> None:
        stdout = (
            '{"type": "result", "usage": {"input_tokens": 42, "output_tokens": 7, '
            '"cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}'
        )
        spec = ActionSpec(
            name="p", runner=RunnerType.PROMPT, target="What is 2+2?", args={"model": None}
        )
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout=stdout)),
        ):
            result = run_action(spec)

        assert result.input_tokens == 42
        assert result.output_tokens == 7
        assert result.tool_calls is None

    def test_skill_dispatch_timeout_leaves_fields_none(self) -> None:
        spec = ActionSpec(name="x", runner=RunnerType.SKILL, target="x", timeout=1)
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1)),
        ):
            result = run_action(spec)

        assert result.timed_out is True
        assert result.input_tokens is None
        assert result.tool_calls is None

    def test_cmd_dispatch_leaves_fields_none(self) -> None:
        """CMD runners never invoke a host CLI (ENH-3464 Decision 1)."""
        spec = ActionSpec(name="echo hi", runner=RunnerType.CMD, target="echo hi", timeout=5)
        result = run_action(spec)

        assert result.input_tokens is None
        assert result.tool_calls is None


class TestScopeRunnerGuard:
    """ENH-3403: scopes declared on SKILL/PROMPT/MCP must fail loud, unspawned."""

    def test_skill_dispatch_with_scopes_fails_loud_spawns_nothing(self) -> None:
        spec = ActionSpec(
            name="x", runner=RunnerType.SKILL, target="x", scopes=frozenset({"github"})
        )
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run") as mock_run,
        ):
            result = run_action(spec)

        mock_run.assert_not_called()
        assert result.exit_code == 2
        assert "declares 'scopes' but runner is" in (result.error or "")
        assert "skill" in (result.error or "")

    def test_prompt_dispatch_with_scopes_fails_loud_spawns_nothing(self) -> None:
        spec = ActionSpec(
            name="x", runner=RunnerType.PROMPT, target="What is 2+2?", scopes=frozenset({"github"})
        )
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run") as mock_run,
        ):
            result = run_action(spec)

        mock_run.assert_not_called()
        assert result.exit_code == 2
        assert "declares 'scopes' but runner is" in (result.error or "")
        assert "prompt" in (result.error or "")

    def test_mcp_dispatch_with_scopes_fails_loud_spawns_nothing(self) -> None:
        spec = ActionSpec(
            name="x",
            runner=RunnerType.MCP,
            target="srv:tool",
            args={"mcp_params": {}},
            scopes=frozenset({"github"}),
        )
        with patch("little_loops.runner_spec.call_mcp_tool") as mock_call:
            result = run_action(spec)

        mock_call.assert_not_called()
        assert result.exit_code == 2
        assert "declares 'scopes' but runner is" in (result.error or "")
        assert "mcp" in (result.error or "")

    def test_scoped_non_cmd_dispatch_writes_no_audit_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_path = tmp_path / "history.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(db_path))
        spec = ActionSpec(
            name="x", runner=RunnerType.SKILL, target="x", scopes=frozenset({"github"})
        )
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run") as mock_run,
        ):
            run_action(spec)
        mock_run.assert_not_called()

        from little_loops.session_store import recent

        assert recent(db_path, kind="credential_scope") == []


class TestRunSkillAutomationCompat:
    """ENH-3097 AC 2/AC 13: _run_skill()'s spec.args automation compat surface.

    The only externally-facing compatibility surface in ENH-3097 — no
    in-tree producer sets spec.args["automation_profile"]/
    ["disable_background_tasks"] (every consumer is out-of-tree
    ll-harness/ll-action/extension runners), so nothing else in the suite
    covers a key rename here.
    """

    def test_legacy_dict_keys_still_work(self) -> None:
        spec = ActionSpec(
            name="x",
            runner=RunnerType.SKILL,
            target="x",
            args={"automation_profile": "ll-auto", "disable_background_tasks": True},
        )
        runner = CapturingRunner()
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=runner),
            patch("subprocess.run", return_value=_make_completed()),
        ):
            run_action(spec)

        automation = runner.build_streaming_calls[0]["automation"]
        assert automation is not None
        assert automation.profile == "ll-auto"
        assert automation.disable_background_tasks is True

    def test_automation_key_works(self) -> None:
        spec = ActionSpec(
            name="x",
            runner=RunnerType.SKILL,
            target="x",
            args={"automation": AutomationContext(profile="ctx-profile")},
        )
        runner = CapturingRunner()
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=runner),
            patch("subprocess.run", return_value=_make_completed()),
        ):
            run_action(spec)

        automation = runner.build_streaming_calls[0]["automation"]
        assert automation is not None
        assert automation.profile == "ctx-profile"

    def test_conflict_explicit_automation_wins_and_warns(self) -> None:
        spec = ActionSpec(
            name="x",
            runner=RunnerType.SKILL,
            target="x",
            args={
                "automation": AutomationContext(profile="explicit"),
                "automation_profile": "legacy",
            },
        )
        runner = CapturingRunner()
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=runner),
            patch("subprocess.run", return_value=_make_completed()),
            pytest.warns(DeprecationWarning, match="_run_skill()"),
        ):
            run_action(spec)

        automation = runner.build_streaming_calls[0]["automation"]
        assert automation is not None
        assert automation.profile == "explicit"
