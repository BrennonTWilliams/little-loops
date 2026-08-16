"""Tests for little_loops.host_runner.

FEAT-1467 introduces the host CLI abstraction layer. These tests cover:

- :func:`resolve_host` detection precedence (LL_HOST_CLI → LL_HOOK_HOST → probe → raise)
- :class:`ClaudeCodeRunner` builds argv matching the pre-refactor
  :func:`little_loops.subprocess_utils.run_claude_command` baseline
- :class:`HostInvocation` is a frozen value object (establishes the new
  ``frozen=True`` convention; verified via :class:`dataclasses.FrozenInstanceError`)
- :class:`CapabilityNotSupported` subclasses :class:`UserWarning`
"""

from __future__ import annotations

import dataclasses
import json
import os
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

from little_loops.host_runner import (
    CapabilityEntry,
    CapabilityNotSupported,
    CapabilityReport,
    ClaudeCodeRunner,
    CodexRunner,
    GeminiRunner,
    HostCapabilities,
    HostInvocation,
    HostNotConfigured,
    HostRunner,
    KimiRunner,
    OmpRunner,
    OpenCodeRunner,
    PiRunner,
    QwenRunner,
    apply_host_cli_from_config,
    project_child_env,
    resolve_host,
)


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear any host env vars so probe/override tests start from a known state."""
    monkeypatch.delenv("LL_HOST_CLI", raising=False)
    monkeypatch.delenv("LL_HOOK_HOST", raising=False)
    yield


@pytest.mark.parametrize(
    "runner_cls",
    [
        ClaudeCodeRunner,
        CodexRunner,
        GeminiRunner,
        OmpRunner,
        KimiRunner,
        QwenRunner,
    ],
)
class TestAutomationProfileEnvAcrossRunners:
    """ENH-3081: automation_profile=None clears an inherited LL_AUTOMATION.

    The six *implemented* runners share one env helper; a table-driven test is
    what keeps them from drifting apart again (BUG-3058 precedent). The ``None``
    branch was untested tree-wide before this — the only prior assertion was
    ``TestKimiRunner.test_automation_profile_env``, which covers Kimi's non-None
    branch alone.
    """

    def test_none_profile_neutralizes_inherited_env(self, runner_cls: type[HostRunner]) -> None:
        runner = runner_cls()
        invocation = runner.build_streaming(prompt="hi", automation_profile=None)
        # Present-but-empty, not absent: absence means "inherit" at every merge site.
        assert invocation.env["LL_AUTOMATION"] == ""
        assert invocation.env["LL_AUTOMATION_PROFILE"] == ""

    def test_non_none_profile_injects_signal(self, runner_cls: type[HostRunner]) -> None:
        runner = runner_cls()
        invocation = runner.build_streaming(prompt="hi", automation_profile="autodev")
        assert invocation.env["LL_AUTOMATION"] == "1"
        assert invocation.env["LL_AUTOMATION_PROFILE"] == "autodev"


class TestProjectChildEnv:
    """ENH-3184 AC1: project_child_env() default behaviour is byte-identical
    to the pre-ENH-3184 hand-rolled ``os.environ.copy()``-plus-overrides shape.
    """

    def test_no_args_is_full_inherit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_TEST_PROBE", "parent-value")
        env = project_child_env()
        assert env["LL_TEST_PROBE"] == "parent-value"
        assert env == dict(os.environ)

    def test_invocation_env_overrides_inherited(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_TEST_PROBE", "parent-value")
        invocation = HostInvocation(
            binary="claude",
            args=[],
            env={"LL_TEST_PROBE": "invocation-value"},
            capabilities=HostCapabilities(),
        )
        env = project_child_env(invocation)
        assert env["LL_TEST_PROBE"] == "invocation-value"

    def test_absent_invocation_key_means_inherit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_TEST_PROBE", "parent-value")
        invocation = HostInvocation(
            binary="claude", args=[], env={}, capabilities=HostCapabilities()
        )
        env = project_child_env(invocation)
        assert env["LL_TEST_PROBE"] == "parent-value"

    def test_extra_overrides_invocation_env(self) -> None:
        invocation = HostInvocation(
            binary="claude",
            args=[],
            env={"LL_HOST_CLI": "from-invocation"},
            capabilities=HostCapabilities(),
        )
        env = project_child_env(invocation, extra={"LL_HOST_CLI": "from-extra"})
        assert env["LL_HOST_CLI"] == "from-extra"

    def test_no_invocation_covers_bash_c_paths(self) -> None:
        """The two bash -c task-path spawns never build a HostInvocation at
        all — invocation must be optional so they can still route (AC1)."""
        assert project_child_env(extra={"FOO": "bar"})["FOO"] == "bar"


@pytest.mark.parametrize(
    "runner_cls",
    [ClaudeCodeRunner, CodexRunner, GeminiRunner, OmpRunner, KimiRunner, QwenRunner],
)
class TestProjectChildEnvCrossRunnerParity:
    """ENH-3184 AC6: project_child_env(invocation) reproduces exactly what the
    hand-rolled ``{**os.environ, **invocation.env}`` call sites produced,
    across every implemented runner. Zero behaviour change outside AC3/AC4/AC7.
    """

    def test_matches_hand_rolled_merge(
        self, runner_cls: type[HostRunner], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_TEST_PROBE", "parent-value")
        runner = runner_cls()
        invocation = runner.build_blocking_json(prompt="hi")
        expected = {**os.environ, **invocation.env}
        assert project_child_env(invocation) == expected


class TestProjectChildEnvStubRunnersRaiseFirst:
    """ENH-3184 AC6: the two unimplemented stubs raise HostNotConfigured before
    any HostInvocation (and therefore any env) is constructed — there is
    nothing for project_child_env() to project for them."""

    @pytest.mark.parametrize("runner_cls", [OpenCodeRunner, PiRunner])
    def test_build_blocking_json_raises_before_env(self, runner_cls: type[HostRunner]) -> None:
        with pytest.raises(HostNotConfigured):
            runner_cls().build_blocking_json(prompt="hi")


class TestDisableBackgroundTasksEnv:
    """FEAT-3078: CLAUDE_CODE_DISABLE_BACKGROUND_TASKS gating on ClaudeCodeRunner.

    Claude-Code-only (AC3): the other five runners accept and ignore the
    parameter, asserted separately in TestDisableBackgroundTasksNoOpOnOtherRunners.
    """

    def test_enabled_and_automation_profile_set_injects_one(self) -> None:
        runner = ClaudeCodeRunner()
        invocation = runner.build_streaming(
            prompt="hi",
            automation_profile="autodev",
            disable_background_tasks=True,
        )
        assert invocation.env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"

    def test_disabled_flag_does_not_inject_even_with_automation_profile(self) -> None:
        runner = ClaudeCodeRunner()
        invocation = runner.build_streaming(
            prompt="hi",
            automation_profile="autodev",
            disable_background_tasks=False,
        )
        assert invocation.env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == ""

    def test_automation_profile_none_neutralizes_even_when_flag_enabled(self) -> None:
        """AC2: absence would mean 'inherit'; must be explicitly cleared to ''."""
        runner = ClaudeCodeRunner()
        invocation = runner.build_streaming(
            prompt="hi",
            automation_profile=None,
            disable_background_tasks=True,
        )
        assert invocation.env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == ""

    def test_default_disable_background_tasks_is_false(self) -> None:
        """The build_streaming() default (False) must not inject the var."""
        runner = ClaudeCodeRunner()
        invocation = runner.build_streaming(prompt="hi", automation_profile="autodev")
        assert invocation.env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == ""


@pytest.mark.parametrize(
    "runner_cls",
    [
        ClaudeCodeRunner,
        CodexRunner,
        GeminiRunner,
        OmpRunner,
        KimiRunner,
        QwenRunner,
        OpenCodeRunner,
        PiRunner,
    ],
)
class TestDisableBackgroundTasksNoOpOnOtherRunners:
    """AC3: the six non-Claude runners accept disable_background_tasks and ignore it."""

    def test_no_op_on_other_runners(self, runner_cls: type[HostRunner]) -> None:
        if runner_cls is ClaudeCodeRunner:
            pytest.skip("ClaudeCodeRunner is the only runner that honors this flag")
        runner = runner_cls()
        try:
            invocation = runner.build_streaming(
                prompt="hi",
                automation_profile="autodev",
                disable_background_tasks=True,
            )
        except HostNotConfigured:
            # OpenCodeRunner/PiRunner stubs raise before building any env — the
            # parameter is still accepted (no TypeError), which is what this
            # test guards against.
            return
        assert "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS" not in invocation.env


class TestResolveHost:
    """Detection precedence: LL_HOST_CLI → LL_HOOK_HOST → binary probe → raise."""

    def test_detect_explicit_override(self, isolated_env: None) -> None:
        """LL_HOST_CLI wins over every other signal."""
        # Use only the explicit-override env path so the test is hermetic
        # regardless of which CLIs exist on the host running pytest.
        env = {"LL_HOST_CLI": "claude-code"}
        runner = resolve_host(env=env)
        assert runner.name == "claude-code"
        assert isinstance(runner, ClaudeCodeRunner)

    def test_detect_falls_back_to_hook_host(self, isolated_env: None) -> None:
        """LL_HOOK_HOST is consulted when LL_HOST_CLI is unset."""
        env = {"LL_HOOK_HOST": "claude-code"}
        runner = resolve_host(env=env)
        assert runner.name == "claude-code"

    def test_explicit_override_beats_hook_host(self, isolated_env: None) -> None:
        """When both env vars are set, LL_HOST_CLI takes precedence.

        FEAT-1465 registered ``CodexRunner`` permanently, so this test now
        relies on the real registry entry rather than a stub injection.
        """
        env = {"LL_HOST_CLI": "codex", "LL_HOOK_HOST": "claude-code"}
        runner = resolve_host(env=env)
        assert runner.name == "codex"
        assert isinstance(runner, CodexRunner)

    def test_detect_binary_probe_order(
        self, isolated_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Binary probe order: claude → codex → pi.

        Simulates a host that only has ``claude`` on PATH and asserts the
        resolver picks ``ClaudeCodeRunner`` without consulting later probes.
        """
        seen: list[str] = []

        def fake_which(binary: str) -> str | None:
            seen.append(binary)
            return "/usr/local/bin/claude" if binary == "claude" else None

        monkeypatch.setattr("little_loops.host_runner.shutil.which", fake_which)
        runner = resolve_host(env={})
        assert isinstance(runner, ClaudeCodeRunner)
        # The probe order must consult ``claude`` first.
        assert seen[0] == "claude"

    def test_raises_when_no_host(self, isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """HostNotConfigured is raised with a remediation hint when nothing resolves."""
        monkeypatch.setattr(
            "little_loops.host_runner.shutil.which",
            lambda _binary: None,
        )
        with pytest.raises(HostNotConfigured) as exc_info:
            resolve_host(env={})
        msg = str(exc_info.value)
        assert "LL_HOST_CLI" in msg
        assert "orchestration.host_cli" in msg

    def test_unknown_host_name_raises_with_hint(self, isolated_env: None) -> None:
        """Explicit override of an unknown host name surfaces a clear error."""
        with pytest.raises(HostNotConfigured) as exc_info:
            resolve_host(env={"LL_HOST_CLI": "no-such-host"})
        assert "no-such-host" in str(exc_info.value)


class TestClaudeCodeRunner:
    """ClaudeCodeRunner builds argv compatible with the legacy code path."""

    def test_claude_runner_matches_legacy_args(self) -> None:
        """build_streaming argv must match the pre-refactor cmd_args snapshot.

        Mirrors the inline-list assertion in
        ``test_subprocess_mocks.py::TestRunClaudeCommand::test_command_includes_correct_arguments``
        so callers of subprocess_utils.run_claude_command can migrate to
        host_runner without behavior drift.
        """
        runner = ClaudeCodeRunner()
        invocation = runner.build_streaming(prompt="/ll:ready-issue BUG-001")

        assert [invocation.binary, *invocation.args] == [
            "claude",
            "--dangerously-skip-permissions",
            "--verbose",
            "--output-format",
            "stream-json",
            "-p",
            "/ll:ready-issue BUG-001",
        ]

    def test_build_streaming_includes_resume_flag(self) -> None:
        runner = ClaudeCodeRunner()
        invocation = runner.build_streaming(prompt="hi", resume=True)
        assert "--continue" in invocation.args

    def test_build_streaming_includes_agent_and_tools(self) -> None:
        runner = ClaudeCodeRunner()
        invocation = runner.build_streaming(
            prompt="hi",
            agent="general-purpose",
            tools=["Read", "Edit"],
        )
        assert "--agent" in invocation.args
        assert "general-purpose" in invocation.args
        assert "--tools" in invocation.args
        assert "Read,Edit" in invocation.args

    def test_build_streaming_with_model(self) -> None:
        """build_streaming emits --model <id> when model is set (ENH-2073)."""
        runner = ClaudeCodeRunner()
        invocation = runner.build_streaming(prompt="hi", model="claude-haiku-4-5-20251001")
        assert "--model" in invocation.args
        idx = invocation.args.index("--model")
        assert invocation.args[idx + 1] == "claude-haiku-4-5-20251001"

    def test_build_streaming_without_model_omits_flag(self) -> None:
        """build_streaming omits --model when model is None (default)."""
        runner = ClaudeCodeRunner()
        invocation = runner.build_streaming(prompt="hi")
        assert "--model" not in invocation.args

    def test_build_version_check(self) -> None:
        runner = ClaudeCodeRunner()
        invocation = runner.build_version_check()
        assert invocation.binary == "claude"
        assert invocation.args == ["--version"]

    def test_satisfies_host_runner_protocol(self) -> None:
        """ClaudeCodeRunner is recognized as a HostRunner at runtime."""
        assert isinstance(ClaudeCodeRunner(), HostRunner)

    # ── BUG-2110: non-interactive signal env vars ────────────────────────────

    def test_build_streaming_includes_non_interactive_env(self) -> None:
        """build_streaming sets LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS in env (BUG-2110)."""
        runner = ClaudeCodeRunner()
        invocation = runner.build_streaming(prompt="hi")
        assert invocation.env.get("LL_NON_INTERACTIVE") == "1"
        assert invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1"

    def test_build_blocking_json_includes_non_interactive_env(self) -> None:
        """build_blocking_json sets LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS in env (BUG-2110)."""
        runner = ClaudeCodeRunner()
        invocation = runner.build_blocking_json(prompt="hi")
        assert invocation.env.get("LL_NON_INTERACTIVE") == "1"
        assert invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1"

    def test_build_detached_includes_non_interactive_env(self) -> None:
        """build_detached sets LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS in env (BUG-2110)."""
        runner = ClaudeCodeRunner()
        invocation = runner.build_detached(prompt="hi")
        assert invocation.env.get("LL_NON_INTERACTIVE") == "1"
        assert invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1"


class TestCodexRunner:
    """CodexRunner builds argv per the verified Codex headless contract.

    Translation table source: ``thoughts/research/codex-headless-invocation.md``.
    """

    def test_codex_runner_registered(self) -> None:
        """CodexRunner must be in the registry so LL_HOST_CLI=codex resolves it."""
        from little_loops import host_runner as hr

        assert "codex" in hr._HOST_RUNNER_REGISTRY
        assert hr._HOST_RUNNER_REGISTRY["codex"] is CodexRunner

    def test_codex_runner_probed_when_on_path(
        self, isolated_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_host() auto-detects CodexRunner when codex is on PATH and claude is absent."""
        monkeypatch.setattr(
            "little_loops.host_runner.shutil.which",
            lambda binary: "/usr/local/bin/codex" if binary == "codex" else None,
        )
        runner = resolve_host(env={})
        assert isinstance(runner, CodexRunner)
        invocation = runner.build_streaming(prompt="hi")
        assert invocation.binary == "codex"

    def test_resolve_host_picks_codex_via_env(self, isolated_env: None) -> None:
        """resolve_host(env={'LL_HOST_CLI': 'codex'}) returns a CodexRunner."""
        runner = resolve_host(env={"LL_HOST_CLI": "codex"})
        assert isinstance(runner, CodexRunner)
        assert runner.name == "codex"

    def test_codex_runner_flag_translation(self) -> None:
        """Snapshot of build_streaming argv against the verified translation table."""
        runner = CodexRunner()
        invocation = runner.build_streaming(prompt="/ll:ready-issue BUG-001")

        assert [invocation.binary, *invocation.args] == [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "--skip-git-repo-check",
            "/ll:ready-issue BUG-001",
        ]

    def test_build_streaming_resume_restructures_subcommand(self) -> None:
        """Resume in Codex is `codex exec resume --last`, not a --continue flag."""
        runner = CodexRunner()
        invocation = runner.build_streaming(prompt="follow up", resume=True)
        assert invocation.args[:3] == ["exec", "resume", "--last"]
        assert "--continue" not in invocation.args

    def test_build_streaming_emits_warning_for_agent_when_toml_absent(self, tmp_path: Path) -> None:
        """ENH-1533: warning fires only when .codex/agents/<name>.toml is absent
        (fallback path). When the TOML exists with developer_instructions, persona
        injection succeeds and no warning is emitted."""
        runner = CodexRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            runner.build_streaming(prompt="hi", agent="general-purpose", working_dir=tmp_path)

    def test_build_streaming_injects_persona_when_toml_present(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-1533: When .codex/agents/<name>.toml exists with
        developer_instructions, the prompt is prefixed with a persona block and
        no CapabilityNotSupported warning fires (Pattern C)."""
        agents_dir = tmp_path / ".codex" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "code-reviewer.toml").write_text(
            'name = "code-reviewer"\ndeveloper_instructions = """\nReview code carefully.\n"""\n'
        )

        runner = CodexRunner()
        with warnings.catch_warnings():
            warnings.simplefilter("error", CapabilityNotSupported)
            invocation = runner.build_streaming(
                prompt="please review", agent="code-reviewer", working_dir=tmp_path
            )

        assert "[Persona: code-reviewer]" in invocation.args[-1]
        assert "Review code carefully." in invocation.args[-1]
        assert invocation.args[-1].endswith("please review")
        captured = capsys.readouterr()
        assert "[ll] Warning" not in captured.err

    def test_build_streaming_falls_back_when_toml_absent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-1533: TOML-absent path emits the stderr notice and the
        CapabilityNotSupported warning; persona is not injected."""
        runner = CodexRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            invocation = runner.build_streaming(
                prompt="hi", agent="ghost-agent", working_dir=tmp_path
            )
        assert "[Persona:" not in invocation.args[-1]
        captured = capsys.readouterr()
        assert "ghost-agent" in captured.err
        assert "ll-adapt --host codex --apply" in captured.err

    def test_build_streaming_falls_back_when_developer_instructions_empty(
        self, tmp_path: Path
    ) -> None:
        """ENH-1533: TOML present but with empty/missing developer_instructions
        falls back to warn-and-drop."""
        agents_dir = tmp_path / ".codex" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "empty.toml").write_text('name = "empty"\n')

        runner = CodexRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            invocation = runner.build_streaming(prompt="hi", agent="empty", working_dir=tmp_path)
        assert "[Persona:" not in invocation.args[-1]

    def test_build_streaming_emits_warning_for_tools(self) -> None:
        """Codex uses sandbox modes, not a tool allowlist; expect a warning."""
        runner = CodexRunner()
        with pytest.warns(CapabilityNotSupported, match="tool"):
            runner.build_streaming(prompt="hi", tools=["Read", "Edit"])

    def test_build_streaming_includes_working_dir(self, tmp_path: object) -> None:
        """-C <dir> sets the workspace root before executing."""
        runner = CodexRunner()
        invocation = runner.build_streaming(prompt="hi", working_dir=tmp_path)  # type: ignore[arg-type]
        assert "-C" in invocation.args
        idx = invocation.args.index("-C")
        assert invocation.args[idx + 1] == str(tmp_path)

    def test_build_blocking_json_argv(self) -> None:
        runner = CodexRunner()
        invocation = runner.build_blocking_json(prompt="hi", model="o4-mini")
        assert invocation.binary == "codex"
        assert "--model" in invocation.args
        assert "o4-mini" in invocation.args
        # Codex has no single-blob JSON mode; --json streams NDJSON events.
        assert "--json" in invocation.args
        # Prompt is positional, last.
        assert invocation.args[-1] == "hi"

    def test_build_blocking_json_json_schema_writes_temp_file(self) -> None:
        """ENH-1530: json_schema is serialized to a temp file, not warned and dropped."""
        runner = CodexRunner()
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        invocation = runner.build_blocking_json(prompt="hi", json_schema=schema)

        assert "--output-schema" in invocation.args
        schema_path_str = invocation.args[invocation.args.index("--output-schema") + 1]
        schema_path = Path(schema_path_str)
        assert schema_path.exists(), "temp schema file must be written before subprocess runs"
        assert json.loads(schema_path.read_text()) == schema
        schema_path.unlink(missing_ok=True)

    def test_build_blocking_json_json_schema_returns_cleanup_paths(self) -> None:
        """ENH-1530: cleanup_paths contains the temp schema file path."""
        runner = CodexRunner()
        invocation = runner.build_blocking_json(prompt="hi", json_schema={"type": "object"})

        assert len(invocation.cleanup_paths) == 1
        schema_path = invocation.cleanup_paths[0]
        assert str(schema_path).endswith(".json")
        assert "ll-schema-" in str(schema_path)
        schema_path.unlink(missing_ok=True)

    def test_build_blocking_json_json_schema_no_warning(self) -> None:
        """ENH-1530: no CapabilityNotSupported warning is emitted when json_schema is wired."""
        import warnings as _warnings

        runner = CodexRunner()
        with _warnings.catch_warnings():
            _warnings.simplefilter("error", CapabilityNotSupported)
            invocation = runner.build_blocking_json(prompt="hi", json_schema={"type": "object"})
        for p in invocation.cleanup_paths:
            p.unlink(missing_ok=True)

    def test_build_blocking_json_no_schema_cleanup_paths_empty(self) -> None:
        """ENH-1530: cleanup_paths is empty tuple when no json_schema is passed."""
        runner = CodexRunner()
        invocation = runner.build_blocking_json(prompt="hi")
        assert invocation.cleanup_paths == ()

    def test_build_blocking_json_prompt_still_last_with_schema(self) -> None:
        """ENH-1530: prompt remains the last positional arg even when schema is wired."""
        runner = CodexRunner()
        invocation = runner.build_blocking_json(
            prompt="test prompt", json_schema={"type": "object"}
        )
        assert invocation.args[-1] == "test prompt"
        for p in invocation.cleanup_paths:
            p.unlink(missing_ok=True)

    def test_build_version_check(self) -> None:
        runner = CodexRunner()
        invocation = runner.build_version_check()
        assert invocation.binary == "codex"
        assert invocation.args == ["--version"]

    def test_build_detached(self) -> None:
        runner = CodexRunner()
        invocation = runner.build_detached(prompt="hi there")
        assert invocation.binary == "codex"
        assert invocation.args[0] == "exec"
        assert "--dangerously-bypass-approvals-and-sandbox" in invocation.args
        assert invocation.args[-1] == "hi there"

    # ── sandbox_mode (ENH-1529) ──────────────────────────────────────────

    @pytest.mark.parametrize(
        ("mode", "expected_flag", "expected_value"),
        [
            (None, "--dangerously-bypass-approvals-and-sandbox", None),
            ("off", "--dangerously-bypass-approvals-and-sandbox", None),
            ("read-only", "--sandbox", "read-only"),
            ("workspace-write", "--sandbox", "workspace-write"),
            ("danger-full-access", "--sandbox", "danger-full-access"),
        ],
    )
    def test_build_streaming_sandbox_mode(
        self, mode: str | None, expected_flag: str, expected_value: str | None
    ) -> None:
        """ENH-1529: sandbox_mode controls Codex sandbox flag in build_streaming."""
        runner = CodexRunner()
        invocation = runner.build_streaming(prompt="hi", sandbox_mode=mode)

        assert expected_flag in invocation.args
        if expected_value is not None:
            idx = invocation.args.index(expected_flag)
            assert invocation.args[idx + 1] == expected_value
            # The dangerous bypass flag must NOT be present when sandbox mode is explicit
            assert "--dangerously-bypass-approvals-and-sandbox" not in invocation.args
        else:
            # None/"off" preserves existing behavior
            assert "--dangerously-bypass-approvals-and-sandbox" in invocation.args

    @pytest.mark.parametrize(
        ("mode", "expected_flag", "expected_value"),
        [
            (None, "--dangerously-bypass-approvals-and-sandbox", None),
            ("off", "--dangerously-bypass-approvals-and-sandbox", None),
            ("read-only", "--sandbox", "read-only"),
            ("workspace-write", "--sandbox", "workspace-write"),
            ("danger-full-access", "--sandbox", "danger-full-access"),
        ],
    )
    def test_build_blocking_json_sandbox_mode(
        self, mode: str | None, expected_flag: str, expected_value: str | None
    ) -> None:
        """ENH-1529: sandbox_mode controls Codex sandbox flag in build_blocking_json."""
        runner = CodexRunner()
        invocation = runner.build_blocking_json(prompt="hi", sandbox_mode=mode)

        assert expected_flag in invocation.args
        if expected_value is not None:
            idx = invocation.args.index(expected_flag)
            assert invocation.args[idx + 1] == expected_value
            assert "--dangerously-bypass-approvals-and-sandbox" not in invocation.args
        else:
            assert "--dangerously-bypass-approvals-and-sandbox" in invocation.args

    @pytest.mark.parametrize(
        ("mode", "expected_flag", "expected_value"),
        [
            (None, "--dangerously-bypass-approvals-and-sandbox", None),
            ("off", "--dangerously-bypass-approvals-and-sandbox", None),
            ("read-only", "--sandbox", "read-only"),
            ("workspace-write", "--sandbox", "workspace-write"),
            ("danger-full-access", "--sandbox", "danger-full-access"),
        ],
    )
    def test_build_detached_sandbox_mode(
        self, mode: str | None, expected_flag: str, expected_value: str | None
    ) -> None:
        """ENH-1529: sandbox_mode controls Codex sandbox flag in build_detached."""
        runner = CodexRunner()
        invocation = runner.build_detached(prompt="hi", sandbox_mode=mode)

        assert expected_flag in invocation.args
        if expected_value is not None:
            idx = invocation.args.index(expected_flag)
            assert invocation.args[idx + 1] == expected_value
            assert "--dangerously-bypass-approvals-and-sandbox" not in invocation.args
        else:
            assert "--dangerously-bypass-approvals-and-sandbox" in invocation.args

    def test_sandbox_mode_invalid_value_raises_value_error(self) -> None:
        """ENH-1529: invalid sandbox_mode values raise ValueError."""
        runner = CodexRunner()
        with pytest.raises(ValueError, match="sandbox_mode"):
            runner.build_streaming(prompt="hi", sandbox_mode="bogus")

    def test_sandbox_mode_default_preserves_existing_behavior(self) -> None:
        """ENH-1529: default sandbox_mode=None preserves the existing snapshot test."""
        runner = CodexRunner()
        invocation = runner.build_streaming(prompt="/ll:ready-issue BUG-001")

        assert [invocation.binary, *invocation.args] == [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "--skip-git-repo-check",
            "/ll:ready-issue BUG-001",
        ]

    def test_tools_warning_mentions_sandbox_mode_parameter(self) -> None:
        """ENH-1529: tools warning suggests sandbox_mode= as the Codex-native alternative."""
        runner = CodexRunner()
        with pytest.warns(CapabilityNotSupported, match="sandbox_mode"):
            runner.build_streaming(prompt="hi", tools=["Read", "Edit"])

    def test_describe_capabilities_documents_sandbox_mode_tool_constraint(self) -> None:
        """ENH-1529: describe_capabilities notes partial tool-constraint support via sandbox modes."""
        report = CodexRunner().describe_capabilities()
        by_name = {e.name: e for e in report.capabilities}
        tool_entry = by_name["tool_allowlist"]
        assert "sandbox_mode" in tool_entry.note.lower()

    def test_satisfies_host_runner_protocol(self) -> None:
        assert isinstance(CodexRunner(), HostRunner)

    def test_capabilities_disable_agent_and_tools(self) -> None:
        caps = CodexRunner().capabilities
        assert caps.streaming is True
        assert caps.permission_skip is True
        assert caps.agent_select is False
        assert caps.tool_allowlist is False

    # ── BUG-2110: non-interactive signal env vars ────────────────────────────

    def test_build_streaming_includes_non_interactive_env(self) -> None:
        """build_streaming sets LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS in env (BUG-2110)."""
        runner = CodexRunner()
        invocation = runner.build_streaming(prompt="hi")
        assert invocation.env.get("LL_NON_INTERACTIVE") == "1"
        assert invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1"

    def test_build_blocking_json_includes_non_interactive_env(self) -> None:
        """build_blocking_json sets LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS in env (BUG-2110)."""
        runner = CodexRunner()
        invocation = runner.build_blocking_json(prompt="hi")
        assert invocation.env.get("LL_NON_INTERACTIVE") == "1"
        assert invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1"

    def test_build_detached_includes_non_interactive_env(self) -> None:
        """build_detached sets LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS in env (BUG-2110)."""
        runner = CodexRunner()
        invocation = runner.build_detached(prompt="hi")
        assert invocation.env.get("LL_NON_INTERACTIVE") == "1"
        assert invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1"


class TestOpenCodeRunner:
    """OpenCodeRunner is a stub: registered, resolvable via env, raises HostNotConfigured.

    Per FEAT-1472 Option B: no external CLI research has been performed, so
    every ``build_*`` method raises ``HostNotConfigured`` with a remediation
    hint pointing at ``LL_HOST_CLI=claude-code``. The runner is gated from
    auto-probe (no ``("opencode", "opencode")`` row in ``_PROBE_ORDER``).
    """

    def test_opencode_runner_registered(self) -> None:
        from little_loops import host_runner as hr

        assert "opencode" in hr._HOST_RUNNER_REGISTRY
        assert hr._HOST_RUNNER_REGISTRY["opencode"] is OpenCodeRunner

    def test_opencode_runner_gated_from_auto_probe(self) -> None:
        """OpenCode is intentionally absent from _PROBE_ORDER per Option B."""
        from little_loops import host_runner as hr

        probe_hosts = {name for name, _binary in hr._PROBE_ORDER}
        assert "opencode" not in probe_hosts

    def test_resolve_host_picks_opencode_via_env(self, isolated_env: None) -> None:
        runner = resolve_host(env={"LL_HOST_CLI": "opencode"})
        assert isinstance(runner, OpenCodeRunner)
        assert runner.name == "opencode"

    def test_build_streaming_raises_host_not_configured(self) -> None:
        runner = OpenCodeRunner()
        with pytest.raises(HostNotConfigured, match="OpenCode"):
            runner.build_streaming(prompt="hi")

    def test_build_blocking_json_raises_host_not_configured(self) -> None:
        runner = OpenCodeRunner()
        with pytest.raises(HostNotConfigured, match="OpenCode"):
            runner.build_blocking_json(prompt="hi")

    def test_build_version_check_raises_host_not_configured(self) -> None:
        runner = OpenCodeRunner()
        with pytest.raises(HostNotConfigured, match="OpenCode"):
            runner.build_version_check()

    def test_build_detached_raises_host_not_configured(self) -> None:
        runner = OpenCodeRunner()
        with pytest.raises(HostNotConfigured, match="OpenCode"):
            runner.build_detached(prompt="hi")

    def test_satisfies_host_runner_protocol(self) -> None:
        assert isinstance(OpenCodeRunner(), HostRunner)


class TestPiRunner:
    """PiRunner is a stub: registered, resolvable via env, raises HostNotConfigured.

    Unlike OpenCodeRunner, ``("pi", "pi")`` is already in ``_PROBE_ORDER`` from
    FEAT-1464. Registering ``PiRunner`` activates that probe edge: any host
    with ``pi`` on PATH will resolve to ``PiRunner`` and raise
    ``HostNotConfigured`` on the first ``build_*`` call (pointing at FEAT-992).
    """

    def test_pirunner_registered(self) -> None:
        from little_loops import host_runner as hr

        assert "pi" in hr._HOST_RUNNER_REGISTRY
        assert hr._HOST_RUNNER_REGISTRY["pi"] is PiRunner

    def test_resolve_host_picks_pi_via_env(self, isolated_env: None) -> None:
        runner = resolve_host(env={"LL_HOST_CLI": "pi"})
        assert isinstance(runner, PiRunner)
        assert runner.name == "pi"

    def test_pirunner_probe_returns_stub_not_raise(
        self, isolated_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """On a host with `pi` on PATH, the probe returns PiRunner and only
        raises HostNotConfigured at the first ``build_*`` call."""
        monkeypatch.setattr(
            "little_loops.host_runner.shutil.which",
            lambda binary: "/usr/local/bin/pi" if binary == "pi" else None,
        )
        runner = resolve_host(env={})
        assert isinstance(runner, PiRunner)
        with pytest.raises(HostNotConfigured, match="FEAT-992"):
            runner.build_streaming(prompt="hi")

    def test_build_streaming_raises_host_not_configured(self) -> None:
        runner = PiRunner()
        with pytest.raises(HostNotConfigured, match="FEAT-992"):
            runner.build_streaming(prompt="hi")

    def test_build_blocking_json_raises_host_not_configured(self) -> None:
        runner = PiRunner()
        with pytest.raises(HostNotConfigured, match="FEAT-992"):
            runner.build_blocking_json(prompt="hi")

    def test_build_version_check_raises_host_not_configured(self) -> None:
        runner = PiRunner()
        with pytest.raises(HostNotConfigured, match="FEAT-992"):
            runner.build_version_check()

    def test_build_detached_raises_host_not_configured(self) -> None:
        runner = PiRunner()
        with pytest.raises(HostNotConfigured, match="FEAT-992"):
            runner.build_detached(prompt="hi")

    def test_satisfies_host_runner_protocol(self) -> None:
        assert isinstance(PiRunner(), HostRunner)


class TestGeminiRunner:
    """GeminiRunner builds argv per the FEAT-2179 flag-translation table.

    Source: ``thoughts/research/gemini-cli-surface.md`` (ENH-2184 / ENH-2185).
    """

    def test_gemini_runner_registered(self) -> None:
        from little_loops import host_runner as hr

        assert "gemini" in hr._HOST_RUNNER_REGISTRY
        assert hr._HOST_RUNNER_REGISTRY["gemini"] is GeminiRunner

    def test_gemini_in_probe_order(self) -> None:
        from little_loops import host_runner as hr

        assert ("gemini", "gemini") in hr._PROBE_ORDER

    def test_resolve_host_picks_gemini_via_env(self, isolated_env: None) -> None:
        runner = resolve_host(env={"LL_HOST_CLI": "gemini"})
        assert isinstance(runner, GeminiRunner)
        assert runner.name == "gemini"

    def test_gemini_runner_probed_when_on_path(
        self, isolated_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_host() auto-detects GeminiRunner when only gemini is on PATH."""
        monkeypatch.setattr(
            "little_loops.host_runner.shutil.which",
            lambda binary: "/usr/local/bin/gemini" if binary == "gemini" else None,
        )
        runner = resolve_host(env={})
        assert isinstance(runner, GeminiRunner)
        invocation = runner.build_streaming(prompt="hi")
        assert invocation.binary == "gemini"

    def test_gemini_runner_flag_translation(self) -> None:
        """Snapshot of build_streaming argv against the verified translation table."""
        runner = GeminiRunner()
        invocation = runner.build_streaming(prompt="/ll:ready-issue BUG-001")

        assert [invocation.binary, *invocation.args] == [
            "gemini",
            "--approval-mode",
            "yolo",
            "--output-format",
            "stream-json",
            "-p",
            "/ll:ready-issue BUG-001",
        ]

    def test_build_streaming_resume_maps_to_resume_latest(self) -> None:
        runner = GeminiRunner()
        invocation = runner.build_streaming(prompt="follow up", resume=True)
        assert "--resume" in invocation.args
        idx = invocation.args.index("--resume")
        assert invocation.args[idx + 1] == "latest"
        assert "--continue" not in invocation.args

    def test_build_streaming_with_model(self) -> None:
        runner = GeminiRunner()
        invocation = runner.build_streaming(prompt="hi", model="gemini-2.5-pro")
        idx = invocation.args.index("--model")
        assert invocation.args[idx + 1] == "gemini-2.5-pro"

    def test_build_streaming_emits_warning_for_agent(self) -> None:
        runner = GeminiRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            runner.build_streaming(prompt="hi", agent="general-purpose")

    def test_build_streaming_emits_warning_for_tools(self) -> None:
        runner = GeminiRunner()
        with pytest.warns(CapabilityNotSupported, match="tool"):
            runner.build_streaming(prompt="hi", tools=["Read", "Edit"])

    def test_build_blocking_json_argv(self) -> None:
        runner = GeminiRunner()
        invocation = runner.build_blocking_json(prompt="hello")
        assert [invocation.binary, *invocation.args] == [
            "gemini",
            "--approval-mode",
            "yolo",
            "--output-format",
            "json",
            "-p",
            "hello",
        ]

    def test_build_blocking_json_silently_drops_schema(self) -> None:
        """Like ClaudeCodeRunner, gemini has no schema flag; parameter is dropped."""
        runner = GeminiRunner()
        with warnings.catch_warnings():
            warnings.simplefilter("error", CapabilityNotSupported)
            invocation = runner.build_blocking_json(prompt="hi", json_schema={"type": "object"})
        assert "--output-schema" not in invocation.args
        assert invocation.cleanup_paths == ()

    def test_build_version_check(self) -> None:
        runner = GeminiRunner()
        invocation = runner.build_version_check()
        assert invocation.binary == "gemini"
        assert invocation.args == ["--version"]

    def test_build_detached(self) -> None:
        runner = GeminiRunner()
        invocation = runner.build_detached(prompt="hi there")
        assert invocation.binary == "gemini"
        assert invocation.args == ["--approval-mode", "yolo", "-p", "hi there"]

    def test_build_streaming_worktree_env(self, tmp_path: Path) -> None:
        """Linked-worktree .git file sets GIT_DIR/GIT_WORK_TREE like ClaudeCodeRunner."""
        gitdir = tmp_path / "repo-gitdir"
        gitdir.mkdir()
        (tmp_path / ".git").write_text(f"gitdir: {gitdir}\n")
        runner = GeminiRunner()
        invocation = runner.build_streaming(prompt="hi", working_dir=tmp_path)
        assert invocation.env["GIT_WORK_TREE"] == str(tmp_path)
        assert invocation.env["GIT_DIR"] == str(gitdir.resolve())

    def test_all_builds_include_non_interactive_env(self) -> None:
        """All build_* methods set LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS (BUG-2110)."""
        runner = GeminiRunner()
        for invocation in (
            runner.build_streaming(prompt="hi"),
            runner.build_blocking_json(prompt="hi"),
            runner.build_detached(prompt="hi"),
        ):
            assert invocation.env.get("LL_NON_INTERACTIVE") == "1"
            assert invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1"

    def test_capabilities_flags(self) -> None:
        caps = GeminiRunner().capabilities
        assert caps.streaming is True
        assert caps.permission_skip is True
        assert caps.agent_select is False
        assert caps.tool_allowlist is False

    def test_satisfies_host_runner_protocol(self) -> None:
        assert isinstance(GeminiRunner(), HostRunner)


class TestKimiRunner:
    """KimiRunner builds argv per the FEAT-2911 flag-translation table.

    Source: ``thoughts/research/kimi-cli-surface.md`` (EPIC-2910; ENH-2912
    registration, FEAT-2914 wiring), verified against kimi 0.30.0.
    """

    def test_kimi_runner_registered(self) -> None:
        from little_loops import host_runner as hr

        assert "kimi-code" in hr._HOST_RUNNER_REGISTRY
        assert hr._HOST_RUNNER_REGISTRY["kimi-code"] is KimiRunner

    def test_kimi_in_probe_order_appended_last(self) -> None:
        """New hosts append to _PROBE_ORDER to keep auto-detection stable.

        kimi was appended last by EPIC-2910; EPIC-3154 appended qwen after
        it, so kimi now sits second-to-last (the append-only invariant is
        what both placements verify).
        """
        from little_loops import host_runner as hr

        assert hr._PROBE_ORDER[-2] == ("kimi-code", "kimi")
        assert hr._PROBE_ORDER[-1] == ("qwen", "qwen")

    def test_resolve_host_picks_kimi_via_env(self, isolated_env: None) -> None:
        runner = resolve_host(env={"LL_HOST_CLI": "kimi-code"})
        assert isinstance(runner, KimiRunner)
        assert runner.name == "kimi-code"

    def test_kimi_runner_probed_when_on_path(
        self, isolated_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_host() auto-detects KimiRunner when only kimi is on PATH."""
        monkeypatch.setattr(
            "little_loops.host_runner.shutil.which",
            lambda binary: "/usr/local/bin/kimi" if binary == "kimi" else None,
        )
        runner = resolve_host(env={})
        assert isinstance(runner, KimiRunner)
        invocation = runner.build_streaming(prompt="hi")
        assert invocation.binary == "kimi"

    def test_kimi_runner_flag_translation(self) -> None:
        """Snapshot of build_streaming argv against the verified translation table."""
        runner = KimiRunner()
        invocation = runner.build_streaming(prompt="/ll:ready-issue BUG-001")

        assert [invocation.binary, *invocation.args] == [
            "kimi",
            "--output-format",
            "stream-json",
            "-p",
            "/ll:ready-issue BUG-001",
        ]

    def test_build_streaming_emits_no_permission_flag(self) -> None:
        """kimi -p runs under auto permissions; --yolo/--auto/--plan are rejected with -p."""
        runner = KimiRunner()
        invocation = runner.build_streaming(prompt="hi")
        for flag in ("--yolo", "--auto", "--plan", "--dangerously-skip-permissions"):
            assert flag not in invocation.args

    def test_build_streaming_resume_maps_to_continue(self) -> None:
        runner = KimiRunner()
        invocation = runner.build_streaming(prompt="follow up", resume=True)
        assert "--continue" in invocation.args

    def test_build_streaming_agent_maps_to_agent_flag(self) -> None:
        runner = KimiRunner()
        invocation = runner.build_streaming(prompt="hi", agent="explore")
        idx = invocation.args.index("--agent")
        assert invocation.args[idx + 1] == "explore"

    def test_build_streaming_agent_dropped_on_resume(self) -> None:
        """kimi rejects --agent combined with --continue; warn and drop the agent."""
        runner = KimiRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            invocation = runner.build_streaming(prompt="hi", agent="explore", resume=True)
        assert "--agent" not in invocation.args
        assert "--continue" in invocation.args

    def test_build_streaming_with_model(self) -> None:
        runner = KimiRunner()
        invocation = runner.build_streaming(prompt="hi", model="kimi-code/k3")
        idx = invocation.args.index("--model")
        assert invocation.args[idx + 1] == "kimi-code/k3"

    def test_build_streaming_workspace_root_maps_to_add_dir(self, tmp_path: Path) -> None:
        runner = KimiRunner()
        invocation = runner.build_streaming(prompt="hi", workspace_root=tmp_path)
        idx = invocation.args.index("--add-dir")
        assert invocation.args[idx + 1] == str(tmp_path)
        assert invocation.capabilities.workspace_sandboxed is False

    def test_build_streaming_emits_warning_for_tools(self) -> None:
        runner = KimiRunner()
        with pytest.warns(CapabilityNotSupported, match="tool"):
            runner.build_streaming(prompt="hi", tools=["Read", "Edit"])

    def test_build_streaming_prompt_terminates_argv(self) -> None:
        """kimi's parser treats a bare positional after options as a subcommand."""
        runner = KimiRunner()
        invocation = runner.build_streaming(
            prompt="hi", model="kimi-code/k3", workspace_root=Path("/tmp/x")
        )
        assert invocation.args[-2:] == ["-p", "hi"]

    def test_build_blocking_json_streams(self) -> None:
        """kimi has no single-blob JSON mode — blocking_json uses stream-json."""
        runner = KimiRunner()
        invocation = runner.build_blocking_json(prompt="hello")
        assert [invocation.binary, *invocation.args] == [
            "kimi",
            "--output-format",
            "stream-json",
            "-p",
            "hello",
        ]

    def test_build_blocking_json_warns_and_drops_schema(self) -> None:
        runner = KimiRunner()
        with pytest.warns(CapabilityNotSupported, match="schema"):
            invocation = runner.build_blocking_json(prompt="hi", json_schema={"type": "object"})
        assert "--json-schema" not in invocation.args
        assert invocation.cleanup_paths == ()

    def test_build_version_check(self) -> None:
        runner = KimiRunner()
        invocation = runner.build_version_check()
        assert invocation.binary == "kimi"
        assert invocation.args == ["--version"]

    def test_build_detached(self) -> None:
        runner = KimiRunner()
        invocation = runner.build_detached(prompt="hi there")
        assert invocation.binary == "kimi"
        assert invocation.args == ["-p", "hi there"]

    def test_build_streaming_worktree_env(self, tmp_path: Path) -> None:
        """Linked-worktree .git file sets GIT_DIR/GIT_WORK_TREE like ClaudeCodeRunner."""
        gitdir = tmp_path / "repo-gitdir"
        gitdir.mkdir()
        (tmp_path / ".git").write_text(f"gitdir: {gitdir}\n")
        runner = KimiRunner()
        invocation = runner.build_streaming(prompt="hi", working_dir=tmp_path)
        assert invocation.env["GIT_WORK_TREE"] == str(tmp_path)
        assert invocation.env["GIT_DIR"] == str(gitdir.resolve())

    def test_all_builds_include_non_interactive_env(self) -> None:
        """All build_* methods set LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS (BUG-2110)."""
        runner = KimiRunner()
        for invocation in (
            runner.build_streaming(prompt="hi"),
            runner.build_blocking_json(prompt="hi"),
            runner.build_detached(prompt="hi"),
        ):
            assert invocation.env.get("LL_NON_INTERACTIVE") == "1"
            assert invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1"

    def test_automation_profile_env(self) -> None:
        runner = KimiRunner()
        invocation = runner.build_streaming(prompt="hi", automation_profile="autodev")
        assert invocation.env["LL_AUTOMATION"] == "1"
        assert invocation.env["LL_AUTOMATION_PROFILE"] == "autodev"

    def test_capabilities_flags(self) -> None:
        caps = KimiRunner().capabilities
        assert caps.streaming is True
        assert caps.permission_skip is True
        assert caps.agent_select is True
        assert caps.tool_allowlist is False
        assert caps.structured_output is False
        assert caps.workspace_sandboxed is False

    def test_satisfies_host_runner_protocol(self) -> None:
        assert isinstance(KimiRunner(), HostRunner)

    def test_kimi_runner_returns_capability_report(self) -> None:
        report = KimiRunner().describe_capabilities()
        assert isinstance(report, CapabilityReport)
        assert report.host == "kimi-code"
        assert report.binary == "kimi"
        by_name = {e.name: e for e in report.capabilities}
        assert by_name["streaming"].status == "full"
        assert by_name["agent_select"].status == "partial"
        assert by_name["tool_allowlist"].status == "unsupported"


class TestQwenRunner:
    """QwenRunner builds argv per the FEAT-3155 flag-translation table.

    Source: ``thoughts/research/qwen-code-surface.md`` (EPIC-3154, ENH-3156),
    verified against qwen 0.21.6.
    """

    def test_qwen_runner_registered(self) -> None:
        from little_loops import host_runner as hr

        assert "qwen" in hr._HOST_RUNNER_REGISTRY
        assert hr._HOST_RUNNER_REGISTRY["qwen"] is QwenRunner

    def test_qwen_in_probe_order_appended_last(self) -> None:
        """New hosts append to _PROBE_ORDER to keep auto-detection stable."""
        from little_loops import host_runner as hr

        assert hr._PROBE_ORDER[-1] == ("qwen", "qwen")

    def test_resolve_host_picks_qwen_via_env(self, isolated_env: None) -> None:
        runner = resolve_host(env={"LL_HOST_CLI": "qwen"})
        assert isinstance(runner, QwenRunner)
        assert runner.name == "qwen"

    def test_resolve_host_picks_qwen_via_hook_host(self, isolated_env: None) -> None:
        runner = resolve_host(env={"LL_HOOK_HOST": "qwen"})
        assert isinstance(runner, QwenRunner)

    def test_qwen_runner_probed_when_on_path(
        self, isolated_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_host() auto-detects QwenRunner when only qwen is on PATH."""
        monkeypatch.setattr(
            "little_loops.host_runner.shutil.which",
            lambda binary: "/usr/local/bin/qwen" if binary == "qwen" else None,
        )
        runner = resolve_host(env={})
        assert isinstance(runner, QwenRunner)
        invocation = runner.build_streaming(prompt="hi")
        assert invocation.binary == "qwen"

    def test_qwen_runner_flag_translation(self) -> None:
        """Snapshot of build_streaming argv against the verified translation table."""
        runner = QwenRunner()
        invocation = runner.build_streaming(prompt="/ll:ready-issue BUG-001")

        assert [invocation.binary, *invocation.args] == [
            "qwen",
            "--yolo",
            "--output-format",
            "stream-json",
            "-p",
            "/ll:ready-issue BUG-001",
        ]

    def test_build_streaming_resume_maps_to_continue(self) -> None:
        runner = QwenRunner()
        invocation = runner.build_streaming(prompt="follow up", resume=True)
        assert "--continue" in invocation.args

    def test_build_streaming_with_model(self) -> None:
        runner = QwenRunner()
        invocation = runner.build_streaming(prompt="hi", model="qwen3-coder")
        idx = invocation.args.index("--model")
        assert invocation.args[idx + 1] == "qwen3-coder"

    def test_build_streaming_workspace_root_maps_to_include_directories(
        self, tmp_path: Path
    ) -> None:
        runner = QwenRunner()
        invocation = runner.build_streaming(prompt="hi", workspace_root=tmp_path)
        idx = invocation.args.index("--include-directories")
        assert invocation.args[idx + 1] == str(tmp_path)
        assert invocation.capabilities.workspace_sandboxed is False

    def test_build_streaming_warns_and_drops_agent(self) -> None:
        """qwen has no --agent flag (planned upstream); warn and drop."""
        runner = QwenRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            invocation = runner.build_streaming(prompt="hi", agent="explore")
        assert "--agent" not in invocation.args

    def test_build_streaming_warns_and_drops_tools(self) -> None:
        """--exclude-tools is a denylist; no allowlist semantics exist."""
        runner = QwenRunner()
        with pytest.warns(CapabilityNotSupported, match="tool"):
            runner.build_streaming(prompt="hi", tools=["read_file", "edit"])

    def test_build_streaming_prompt_terminates_argv(self) -> None:
        runner = QwenRunner()
        invocation = runner.build_streaming(
            prompt="hi", model="qwen3-coder", workspace_root=Path("/tmp/x")
        )
        assert invocation.args[-2:] == ["-p", "hi"]

    def test_build_blocking_json_streams(self) -> None:
        """qwen's json mode buffers an array — blocking_json uses stream-json (Kimi posture)."""
        runner = QwenRunner()
        invocation = runner.build_blocking_json(prompt="hello")
        assert [invocation.binary, *invocation.args] == [
            "qwen",
            "--yolo",
            "--output-format",
            "stream-json",
            "-p",
            "hello",
        ]

    def test_build_blocking_json_drops_schema_silently(self) -> None:
        """structured_output=True: evaluators append --json-schema at the call site."""
        runner = QwenRunner()
        with warnings.catch_warnings():
            warnings.simplefilter("error", CapabilityNotSupported)
            invocation = runner.build_blocking_json(prompt="hi", json_schema={"type": "object"})
        assert "--json-schema" not in invocation.args
        assert invocation.capabilities.structured_output is True

    def test_build_version_check(self) -> None:
        runner = QwenRunner()
        invocation = runner.build_version_check()
        assert invocation.binary == "qwen"
        assert invocation.args == ["--version"]

    def test_build_detached(self) -> None:
        runner = QwenRunner()
        invocation = runner.build_detached(prompt="hi there")
        assert invocation.binary == "qwen"
        assert invocation.args == ["--yolo", "-p", "hi there"]

    def test_build_streaming_worktree_env(self, tmp_path: Path) -> None:
        """Linked-worktree .git file sets GIT_DIR/GIT_WORK_TREE like ClaudeCodeRunner."""
        gitdir = tmp_path / "repo-gitdir"
        gitdir.mkdir()
        (tmp_path / ".git").write_text(f"gitdir: {gitdir}\n")
        runner = QwenRunner()
        invocation = runner.build_streaming(prompt="hi", working_dir=tmp_path)
        assert invocation.env["GIT_WORK_TREE"] == str(tmp_path)
        assert invocation.env["GIT_DIR"] == str(gitdir.resolve())

    def test_all_builds_include_non_interactive_env(self) -> None:
        """All build_* methods set LL_NON_INTERACTIVE + DANGEROUSLY_SKIP_PERMISSIONS (BUG-2110)."""
        runner = QwenRunner()
        for invocation in (
            runner.build_streaming(prompt="hi"),
            runner.build_blocking_json(prompt="hi"),
            runner.build_detached(prompt="hi"),
        ):
            assert invocation.env.get("LL_NON_INTERACTIVE") == "1"
            assert invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1"

    def test_all_builds_suppress_yolo_warning(self) -> None:
        """The stderr yolo/no-sandbox warning would pollute error diagnostics."""
        runner = QwenRunner()
        for invocation in (
            runner.build_streaming(prompt="hi"),
            runner.build_blocking_json(prompt="hi"),
            runner.build_detached(prompt="hi"),
        ):
            assert invocation.env.get("QWEN_CODE_SUPPRESS_YOLO_WARNING") == "1"

    def test_automation_profile_env(self) -> None:
        runner = QwenRunner()
        invocation = runner.build_streaming(prompt="hi", automation_profile="autodev")
        assert invocation.env["LL_AUTOMATION"] == "1"
        assert invocation.env["LL_AUTOMATION_PROFILE"] == "autodev"

    def test_capabilities_flags(self) -> None:
        caps = QwenRunner().capabilities
        assert caps.streaming is True
        assert caps.permission_skip is True
        assert caps.agent_select is False
        assert caps.tool_allowlist is False
        # Second host ever with structured_output (inline --json-schema, FEAT-3155).
        assert caps.structured_output is True
        assert caps.workspace_sandboxed is False

    def test_satisfies_host_runner_protocol(self) -> None:
        assert isinstance(QwenRunner(), HostRunner)

    def test_qwen_runner_returns_capability_report(self) -> None:
        report = QwenRunner().describe_capabilities()
        assert isinstance(report, CapabilityReport)
        assert report.host == "qwen"
        assert report.binary == "qwen"
        by_name = {e.name: e for e in report.capabilities}
        assert by_name["streaming"].status == "full"
        assert by_name["permission_skip"].status == "full"
        assert by_name["agent_select"].status == "unsupported"
        assert by_name["tool_allowlist"].status == "unsupported"
        assert by_name["json_schema"].status == "full"
        assert by_name["structured_output"].status == "full"
        assert by_name["workspace_sandboxed"].status == "unsupported"


class TestQwenStructuredOutputArgs:
    """_structured_output_args host-specific persistence flag (EPIC-3154).

    qwen rejects claude's ``--no-session-persistence`` (argv parse error);
    its equivalent is ``--chat-recording false`` (FEAT-3155 spike).
    """

    def test_qwen_invocation_gets_chat_recording_false(self) -> None:
        from little_loops.fsm.evaluators import _structured_output_args

        invocation = QwenRunner().build_blocking_json(prompt="hi")
        args = _structured_output_args(invocation, {"type": "object"})
        assert "--json-schema" in args
        assert json.dumps({"type": "object"}) in args
        idx = args.index("--chat-recording")
        assert args[idx + 1] == "false"
        assert "--no-session-persistence" not in args

    def test_claude_invocation_keeps_no_session_persistence(self) -> None:
        from little_loops.fsm.evaluators import _structured_output_args

        invocation = ClaudeCodeRunner().build_blocking_json(prompt="hi")
        args = _structured_output_args(invocation, {"type": "object"})
        assert "--json-schema" in args
        assert "--no-session-persistence" in args
        assert "--chat-recording" not in args

    def test_unstructured_host_gets_neither_flag(self) -> None:
        from little_loops.fsm.evaluators import _structured_output_args

        invocation = KimiRunner().build_blocking_json(prompt="hi")
        args = _structured_output_args(invocation, {"type": "object"})
        assert "--json-schema" not in args
        assert "--no-session-persistence" not in args
        assert "--chat-recording" not in args


class TestOmpRunner:
    """OmpRunner builds argv per the oh-my-pi headless audit.

    Source: ``thoughts/research/omp-headless-flags.md`` (FEAT-1850).
    """

    def test_omp_runner_registered(self) -> None:
        from little_loops import host_runner as hr

        assert "omp" in hr._HOST_RUNNER_REGISTRY
        assert hr._HOST_RUNNER_REGISTRY["omp"] is OmpRunner

    def test_omp_in_probe_order(self) -> None:
        from little_loops import host_runner as hr

        assert ("omp", "omp") in hr._PROBE_ORDER

    def test_resolve_host_picks_omp_via_env(self, isolated_env: None) -> None:
        runner = resolve_host(env={"LL_HOST_CLI": "omp"})
        assert isinstance(runner, OmpRunner)
        assert runner.name == "omp"

    def test_omp_runner_probed_when_on_path(
        self, isolated_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_host() auto-detects OmpRunner when only omp is on PATH."""
        monkeypatch.setattr(
            "little_loops.host_runner.shutil.which",
            lambda binary: "/usr/local/bin/omp" if binary == "omp" else None,
        )
        runner = resolve_host(env={})
        assert isinstance(runner, OmpRunner)
        invocation = runner.build_streaming(prompt="hi")
        assert invocation.binary == "omp"

    def test_omp_runner_flag_translation(self) -> None:
        """Snapshot of build_streaming argv against the audited flag surface."""
        runner = OmpRunner()
        invocation = runner.build_streaming(prompt="/ll:ready-issue BUG-001")

        assert [invocation.binary, *invocation.args] == [
            "omp",
            "--mode",
            "json",
            "-p",
            "/ll:ready-issue BUG-001",
        ]

    def test_build_streaming_resume_maps_to_continue(self) -> None:
        runner = OmpRunner()
        invocation = runner.build_streaming(prompt="follow up", resume=True)
        assert "--continue" in invocation.args

    def test_build_streaming_tools_allowlist_supported(self) -> None:
        """omp natively supports --tools <comma-list>; no warning fires."""
        runner = OmpRunner()
        with warnings.catch_warnings():
            warnings.simplefilter("error", CapabilityNotSupported)
            invocation = runner.build_streaming(prompt="hi", tools=["read", "edit"])
        idx = invocation.args.index("--tools")
        assert invocation.args[idx + 1] == "read,edit"

    def test_build_streaming_with_model(self) -> None:
        runner = OmpRunner()
        invocation = runner.build_streaming(prompt="hi", model="claude-sonnet-4-5")
        idx = invocation.args.index("--model")
        assert invocation.args[idx + 1] == "claude-sonnet-4-5"

    def test_build_streaming_emits_warning_for_agent(self) -> None:
        runner = OmpRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            runner.build_streaming(prompt="hi", agent="general-purpose")

    def test_build_blocking_json_argv(self) -> None:
        runner = OmpRunner()
        invocation = runner.build_blocking_json(prompt="hello")
        assert [invocation.binary, *invocation.args] == [
            "omp",
            "--mode",
            "json",
            "--no-session",
            "-p",
            "hello",
        ]

    def test_build_blocking_json_silently_drops_schema(self) -> None:
        runner = OmpRunner()
        with warnings.catch_warnings():
            warnings.simplefilter("error", CapabilityNotSupported)
            invocation = runner.build_blocking_json(prompt="hi", json_schema={"type": "object"})
        assert invocation.cleanup_paths == ()

    def test_build_version_check(self) -> None:
        runner = OmpRunner()
        invocation = runner.build_version_check()
        assert invocation.binary == "omp"
        assert invocation.args == ["--version"]

    def test_build_detached(self) -> None:
        runner = OmpRunner()
        invocation = runner.build_detached(prompt="hi there")
        assert invocation.binary == "omp"
        assert invocation.args == ["-p", "hi there"]

    def test_build_streaming_worktree_env(self, tmp_path: Path) -> None:
        gitdir = tmp_path / "repo-gitdir"
        gitdir.mkdir()
        (tmp_path / ".git").write_text(f"gitdir: {gitdir}\n")
        runner = OmpRunner()
        invocation = runner.build_streaming(prompt="hi", working_dir=tmp_path)
        assert invocation.env["GIT_WORK_TREE"] == str(tmp_path)
        assert invocation.env["GIT_DIR"] == str(gitdir.resolve())

    def test_all_builds_include_non_interactive_env(self) -> None:
        """All build_* methods set LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS (BUG-2110)."""
        runner = OmpRunner()
        for invocation in (
            runner.build_streaming(prompt="hi"),
            runner.build_blocking_json(prompt="hi"),
            runner.build_detached(prompt="hi"),
        ):
            assert invocation.env.get("LL_NON_INTERACTIVE") == "1"
            assert invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1"

    def test_capabilities_flags(self) -> None:
        caps = OmpRunner().capabilities
        assert caps.streaming is True
        assert caps.permission_skip is True
        assert caps.agent_select is False
        assert caps.tool_allowlist is True

    def test_satisfies_host_runner_protocol(self) -> None:
        assert isinstance(OmpRunner(), HostRunner)


class TestHostInvocation:
    """Frozen-dataclass convention check for value objects."""

    def test_host_invocation_is_frozen(self) -> None:
        """Mutating a HostInvocation must raise FrozenInstanceError.

        Establishes the new ``@dataclass(frozen=True)`` convention for value
        objects passed across the runner/caller boundary. No prior
        frozen-dataclass test exists in the suite; this is the regression
        guard going forward.
        """
        invocation = HostInvocation(binary="claude", args=["--version"])
        with pytest.raises(dataclasses.FrozenInstanceError):
            invocation.binary = "codex"  # type: ignore[misc]

    def test_default_env_and_capabilities(self) -> None:
        invocation = HostInvocation(binary="claude", args=[])
        assert invocation.env == {}
        assert isinstance(invocation.capabilities, HostCapabilities)
        assert invocation.cleanup_paths == ()

    def test_cleanup_paths_defaults_to_empty_tuple(self) -> None:
        invocation = HostInvocation(binary="x", args=[])
        assert invocation.cleanup_paths == ()


class TestCapabilityWarning:
    """CapabilityNotSupported is a UserWarning that pytest.warns can capture."""

    def test_capability_warning(self) -> None:
        """Emitting CapabilityNotSupported is captured by pytest.warns."""
        with pytest.warns(CapabilityNotSupported, match="streaming"):
            warnings.warn(
                "host does not support streaming",
                CapabilityNotSupported,
                stacklevel=2,
            )

    def test_capability_not_supported_is_user_warning(self) -> None:
        assert issubclass(CapabilityNotSupported, UserWarning)


class TestCapabilityReport:
    """Frozen-dataclass convention and round-trip construction for capability types."""

    def test_capability_entry_is_frozen(self) -> None:
        entry = CapabilityEntry(name="streaming", status="full")
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry.name = "changed"  # type: ignore[misc]

    def test_capability_report_is_frozen(self) -> None:
        report = CapabilityReport(host="claude-code", binary="claude", version="")
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.host = "changed"  # type: ignore[misc]

    def test_capability_report_defaults(self) -> None:
        report = CapabilityReport(host="h", binary="b", version="1.0")
        assert report.capabilities == []
        # BUG-2760: the never-populated ``hooks`` field was removed entirely.
        assert not hasattr(report, "hooks")

    def test_capability_report_round_trip(self) -> None:
        entries = [
            CapabilityEntry("streaming", "full"),
            CapabilityEntry("agent_select", "unsupported", "not supported"),
        ]
        report = CapabilityReport(host="codex", binary="codex", version="0.9", capabilities=entries)
        assert report.host == "codex"
        assert len(report.capabilities) == 2
        assert report.capabilities[0].status == "full"
        assert report.capabilities[1].note == "not supported"


class TestDescribeCapabilities:
    """Each runner must return a CapabilityReport from describe_capabilities()."""

    def test_claude_code_runner_returns_capability_report(self) -> None:
        report = ClaudeCodeRunner().describe_capabilities()
        assert isinstance(report, CapabilityReport)
        assert report.host == "claude-code"
        assert report.binary == "claude"
        names = {e.name for e in report.capabilities}
        assert "streaming" in names
        assert "agent_select" in names

    def test_claude_code_runner_all_core_capabilities_full(self) -> None:
        report = ClaudeCodeRunner().describe_capabilities()
        by_name = {e.name: e for e in report.capabilities}
        assert by_name["streaming"].status == "full"
        assert by_name["permission_skip"].status == "full"
        assert by_name["agent_select"].status == "full"
        assert by_name["tool_allowlist"].status == "full"
        # ENH-2627: claude CLI honors an inline --json-schema flag (Anthropic backend).
        assert by_name["structured_output"].status == "full"

    def test_claude_code_json_schema_matches_structured_output(self) -> None:
        """BUG-2759: json_schema and structured_output describe the same inline
        --json-schema flag and must not disagree, or ll-doctor's flat
        any-unsupported exit-code scan poisons a fully-healthy host."""
        report = ClaudeCodeRunner().describe_capabilities()
        by_name = {e.name: e for e in report.capabilities}
        assert by_name["json_schema"].status == by_name["structured_output"].status

    def test_structured_output_capability_flag_per_host(self) -> None:
        """ENH-2627: only the claude CLI honors the inline --json-schema flag the
        FSM evaluators append; every other host gates the flag off."""
        assert ClaudeCodeRunner().capabilities.structured_output is True
        assert CodexRunner().capabilities.structured_output is False
        assert GeminiRunner().capabilities.structured_output is False
        assert OmpRunner().capabilities.structured_output is False
        assert OpenCodeRunner().capabilities.structured_output is False
        assert PiRunner().capabilities.structured_output is False

    def test_structured_output_entry_unsupported_on_non_claude_hosts(self) -> None:
        """ENH-2627: describe_capabilities surfaces the flag for ll-doctor."""
        for runner in (CodexRunner(), GeminiRunner(), OmpRunner()):
            by_name = {e.name: e for e in runner.describe_capabilities().capabilities}
            assert by_name["structured_output"].status == "unsupported"

    def test_codex_runner_returns_capability_report(self) -> None:
        report = CodexRunner().describe_capabilities()
        assert isinstance(report, CapabilityReport)
        assert report.host == "codex"
        assert report.binary == "codex"

    def test_codex_runner_agent_select_partial(self) -> None:
        """ENH-1533: agent_select is now "partial" — persona is injected via
        .codex/agents/<name>.toml when the file exists; `HostCapabilities.agent_select`
        bool stays False because there is still no native --agent CLI parity."""
        report = CodexRunner().describe_capabilities()
        by_name = {e.name: e for e in report.capabilities}
        assert by_name["agent_select"].status == "partial"
        assert "developer_instructions" in by_name["agent_select"].note
        assert by_name["tool_allowlist"].status == "partial"  # ENH-1529
        assert by_name["json_schema"].status == "partial"

    def test_opencode_runner_returns_capability_report(self) -> None:
        report = OpenCodeRunner().describe_capabilities()
        assert isinstance(report, CapabilityReport)
        assert report.host == "opencode"
        assert len(report.capabilities) >= 1
        assert report.capabilities[0].status == "unsupported"
        assert "HostNotConfigured" in report.capabilities[0].note

    def test_pi_runner_returns_capability_report(self) -> None:
        report = PiRunner().describe_capabilities()
        assert isinstance(report, CapabilityReport)
        assert report.host == "pi"
        assert len(report.capabilities) >= 1
        assert report.capabilities[0].status == "unsupported"
        assert "FEAT-992" in report.capabilities[0].note

    def test_gemini_runner_returns_capability_report(self) -> None:
        report = GeminiRunner().describe_capabilities()
        assert isinstance(report, CapabilityReport)
        assert report.host == "gemini"
        assert report.binary == "gemini"
        by_name = {e.name: e for e in report.capabilities}
        assert by_name["streaming"].status == "full"
        assert by_name["permission_skip"].status == "full"
        assert by_name["agent_select"].status == "unsupported"
        assert by_name["tool_allowlist"].status == "unsupported"
        assert by_name["json_schema"].status == "unsupported"

    def test_omp_runner_returns_capability_report(self) -> None:
        report = OmpRunner().describe_capabilities()
        assert isinstance(report, CapabilityReport)
        assert report.host == "omp"
        assert report.binary == "omp"
        by_name = {e.name: e for e in report.capabilities}
        assert by_name["streaming"].status == "full"
        assert by_name["permission_skip"].status == "full"
        assert by_name["agent_select"].status == "unsupported"
        assert by_name["tool_allowlist"].status == "full"
        assert by_name["json_schema"].status == "unsupported"

    def test_codex_warnings_consistent_with_describe_capabilities(self, tmp_path: Path) -> None:
        """ENH-1533: Pattern D consistency.

        - When `.codex/agents/<name>.toml` is present with developer_instructions,
          no warning fires and `agent_select` is "partial".
        - When the TOML is absent, the fallback emits CapabilityNotSupported.
        - `tools=` still emits CapabilityNotSupported and `tool_allowlist` is
          "unsupported".
        """
        runner = CodexRunner()
        report = runner.describe_capabilities()
        by_name = {e.name: e for e in report.capabilities}

        # TOML-present: no warning, status partial.
        agents_dir = tmp_path / ".codex" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "persona.toml").write_text('developer_instructions = """\nbe helpful\n"""\n')
        with warnings.catch_warnings():
            warnings.simplefilter("error", CapabilityNotSupported)
            runner.build_streaming(prompt="hi", agent="persona", working_dir=tmp_path)
        assert by_name["agent_select"].status == "partial"

        # TOML-absent: fallback emits the warning.
        with pytest.warns(CapabilityNotSupported, match="agent"):
            runner.build_streaming(prompt="hi", agent="missing", working_dir=tmp_path)

        # Tools remain unsupported.
        with pytest.warns(CapabilityNotSupported, match="tool"):
            runner.build_streaming(prompt="hi", tools=["Read"])
        assert by_name["tool_allowlist"].status == "partial"  # ENH-1529


class TestApplyHostCliFromConfig:
    """apply_host_cli_from_config exports orchestration.host_cli as LL_HOST_CLI."""

    def test_sets_env_var_from_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LL_HOST_CLI", raising=False)

        class FakeOrch:
            host_cli = "codex"

        class FakeConfig:
            orchestration = FakeOrch()

        apply_host_cli_from_config(FakeConfig())
        import os

        assert os.environ.get("LL_HOST_CLI") == "codex"
        monkeypatch.delenv("LL_HOST_CLI", raising=False)

    def test_does_not_override_existing_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")

        class FakeOrch:
            host_cli = "codex"

        class FakeConfig:
            orchestration = FakeOrch()

        apply_host_cli_from_config(FakeConfig())
        import os

        assert os.environ["LL_HOST_CLI"] == "claude-code"

    def test_no_op_when_host_cli_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LL_HOST_CLI", raising=False)

        class FakeOrch:
            host_cli = None

        class FakeConfig:
            orchestration = FakeOrch()

        apply_host_cli_from_config(FakeConfig())
        import os

        assert os.environ.get("LL_HOST_CLI") is None

    def test_no_op_when_config_lacks_orchestration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LL_HOST_CLI", raising=False)
        apply_host_cli_from_config(object())
        import os

        assert os.environ.get("LL_HOST_CLI") is None
