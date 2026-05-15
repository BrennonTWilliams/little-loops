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
import warnings
from collections.abc import Iterator

import pytest

from little_loops.host_runner import (
    CapabilityNotSupported,
    ClaudeCodeRunner,
    CodexRunner,
    HostCapabilities,
    HostInvocation,
    HostNotConfigured,
    HostRunner,
    resolve_host,
)


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear any host env vars so probe/override tests start from a known state."""
    monkeypatch.delenv("LL_HOST_CLI", raising=False)
    monkeypatch.delenv("LL_HOOK_HOST", raising=False)
    yield


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

    def test_raises_when_no_host(
        self, isolated_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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

    def test_build_version_check(self) -> None:
        runner = ClaudeCodeRunner()
        invocation = runner.build_version_check()
        assert invocation.binary == "claude"
        assert invocation.args == ["--version"]

    def test_satisfies_host_runner_protocol(self) -> None:
        """ClaudeCodeRunner is recognized as a HostRunner at runtime."""
        assert isinstance(ClaudeCodeRunner(), HostRunner)


class TestCodexRunner:
    """CodexRunner builds argv per the verified Codex headless contract.

    Translation table source: ``thoughts/research/codex-headless-invocation.md``.
    """

    def test_codex_runner_registered(self) -> None:
        """CodexRunner must be in the registry so LL_HOST_CLI=codex resolves it."""
        from little_loops import host_runner as hr

        assert "codex" in hr._HOST_RUNNER_REGISTRY
        assert hr._HOST_RUNNER_REGISTRY["codex"] is CodexRunner

    def test_codex_runner_gated_from_auto_probe(self) -> None:
        """Codex is intentionally absent from _PROBE_ORDER pending validation.

        FEAT-1465 AC: gated behind LL_HOST_CLI=codex until manually tested.
        """
        from little_loops import host_runner as hr

        probe_hosts = {name for name, _binary in hr._PROBE_ORDER}
        assert "codex" not in probe_hosts

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

    def test_build_streaming_emits_warning_for_agent(self) -> None:
        """Per AC: --agent has no Codex equivalent and must surface a warning."""
        runner = CodexRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            runner.build_streaming(prompt="hi", agent="general-purpose")

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

    def test_build_blocking_json_emits_warning_for_json_schema(self) -> None:
        """Codex --output-schema requires a file path; inline dict is unsupported.

        Verifies CapabilityNotSupported is emitted and no TypeError is raised.
        """
        runner = CodexRunner()
        with pytest.warns(CapabilityNotSupported, match="schema"):
            invocation = runner.build_blocking_json(
                prompt="hi",
                json_schema={"type": "object"},
            )
        # Must still produce a valid invocation despite the warning.
        assert invocation.binary == "codex"
        assert invocation.args[-1] == "hi"

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

    def test_satisfies_host_runner_protocol(self) -> None:
        assert isinstance(CodexRunner(), HostRunner)

    def test_capabilities_disable_agent_and_tools(self) -> None:
        caps = CodexRunner().capabilities
        assert caps.streaming is True
        assert caps.permission_skip is True
        assert caps.agent_select is False
        assert caps.tool_allowlist is False


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
