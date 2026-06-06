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
    HostCapabilities,
    HostInvocation,
    HostNotConfigured,
    HostRunner,
    OpenCodeRunner,
    PiRunner,
    apply_host_cli_from_config,
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
        assert "ll-adapt-agents-for-codex" in captured.err

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
        assert report.hooks == []

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
