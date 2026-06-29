"""Host CLI abstraction layer.

Provides a host-agnostic ``HostRunner`` Protocol and a concrete
``ClaudeCodeRunner`` implementation that builds argv for the ``claude`` CLI.
``resolve_host()`` discovers the active host runner from environment overrides
or by probing for known host binaries on ``PATH``.

This module is the foundation for FEAT-1464's call-site migrations
(FEAT-1468): production sites currently building ``claude`` argv inline will
consult ``resolve_host()`` and use the returned runner's factory methods to
build invocations. FEAT-1467 introduces only the abstraction and its
ClaudeCode implementation; no production sites are migrated yet.

Public exports:
    HostInvocation: frozen value object describing a host invocation
    HostCapabilities: capability flags describing what a host supports
    HostRunner: Protocol that host runners must satisfy
    ClaudeCodeRunner: ClaudeCode CLI implementation
    resolve_host: discovery entry point
    HostNotConfigured: raised when no host can be resolved
    CapabilityNotSupported: warning emitted when a host lacks a capability
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import tomllib
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

__all__ = [
    "CapabilityEntry",
    "CapabilityNotSupported",
    "CapabilityReport",
    "ClaudeCodeRunner",
    "CodexRunner",
    "HookEntry",
    "HostCapabilities",
    "HostInvocation",
    "HostNotConfigured",
    "HostRunner",
    "OpenCodeRunner",
    "PiRunner",
    "apply_host_cli_from_config",
    "resolve_host",
]


class HostNotConfigured(RuntimeError):
    """Raised when no host runner can be resolved from env or binary probe.

    The error message includes a remediation hint pointing at the
    ``LL_HOST_CLI`` and ``LL_HOOK_HOST`` env vars and the ``orchestration.host_cli``
    config key so users have a clear path to fix the failure.
    """


class CapabilityNotSupported(UserWarning):
    """Emitted when a caller requests a capability the active host lacks.

    Subclasses ``UserWarning`` (not ``Warning``) so test code can capture it
    via :func:`pytest.warns` and production code can route it through
    :func:`warnings.simplefilter("error", CapabilityNotSupported)` for strict
    contexts. Mirrors the precedent set by :mod:`config.core` which emits
    :class:`DeprecationWarning` via ``warnings.warn(..., stacklevel=2)``.
    """


@dataclass(frozen=True)
class HostCapabilities:
    """Capability flags describing what a host runner supports.

    Each flag corresponds to a feature that may or may not be available on
    a given host. Call sites that require a capability should check the
    relevant flag and either fall back gracefully or emit
    :class:`CapabilityNotSupported`.
    """

    streaming: bool = False
    permission_skip: bool = False
    agent_select: bool = False
    tool_allowlist: bool = False


@dataclass(frozen=True)
class HostInvocation:
    """Immutable description of how to invoke a host CLI.

    Returned by the ``build_*`` factory methods on :class:`HostRunner`. Call
    sites pass ``binary`` + ``args`` to :mod:`subprocess` and merge ``env``
    into the child process environment. ``capabilities`` records the host's
    capability surface so callers can branch on what was actually wired.

    Frozen because instances cross the runner/caller boundary; mutating one
    in-flight would silently corrupt argv. This establishes the
    ``frozen=True`` convention for new value objects in ``scripts/little_loops/``.
    """

    binary: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)
    capabilities: HostCapabilities = field(default_factory=HostCapabilities)
    cleanup_paths: tuple[Path, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CapabilityEntry:
    """A single host capability with its support status.

    ``status`` is one of ``"full"``, ``"partial"``, or ``"unsupported"``.
    ``note`` carries an optional human-readable explanation (e.g. workaround).
    """

    name: str
    status: Literal["full", "partial", "unsupported"]
    note: str = ""


@dataclass(frozen=True)
class HookEntry:
    """A single hook's installation status for a given host.

    ``status`` is one of ``"installed"``, ``"registered"``, ``"deferred"``, or ``"absent"``.
    """

    name: str
    status: Literal["installed", "registered", "deferred", "absent"]
    note: str = ""


@dataclass(frozen=True)
class CapabilityReport:
    """Full capability and hook report for one host runner.

    Returned by :meth:`HostRunner.describe_capabilities`. Consumers (e.g. the
    ``ll-doctor`` CLI) iterate ``capabilities`` and ``hooks`` to produce a
    tabular preflight report.
    """

    host: str
    binary: str
    version: str
    capabilities: list[CapabilityEntry] = field(default_factory=list)
    hooks: list[HookEntry] = field(default_factory=list)


@runtime_checkable
class HostRunner(Protocol):
    """Protocol for host-specific CLI invocation builders.

    Implementations construct argv lists for a particular agent host (Claude
    Code, Codex, OpenCode, Pi, ...). Each ``build_*`` factory returns a
    :class:`HostInvocation` describing the binary, arguments, environment,
    and capability surface.

    Protocols are matched structurally — any class with a ``name`` attribute
    and the five methods below satisfies ``HostRunner`` whether or not it
    subclasses this Protocol explicitly. ``@runtime_checkable`` enables
    ``isinstance(obj, HostRunner)`` checks for registry validation.
    """

    name: str

    def detect(self) -> bool:
        """Return True if this host is available in the current environment."""
        ...

    def build_streaming(
        self,
        *,
        prompt: str,
        working_dir: Path | None = None,
        resume: bool = False,
        agent: str | None = None,
        tools: list[str] | None = None,
        model: str | None = None,
    ) -> HostInvocation:
        """Build an invocation that streams structured output.

        Used by the long-running orchestration paths (``ll-auto``, ``ll-parallel``,
        ``fsm.runners``) that need to consume turn-by-turn JSON events.
        """
        ...

    def build_blocking_json(
        self,
        *,
        prompt: str,
        model: str | None = None,
        json_schema: dict | None = None,
    ) -> HostInvocation:
        """Build a one-shot invocation that returns a single JSON blob."""
        ...

    def build_version_check(self) -> HostInvocation:
        """Build an invocation that prints the host's version and exits."""
        ...

    def build_detached(self, *, prompt: str) -> HostInvocation:
        """Build an invocation suitable for fire-and-forget detached execution."""
        ...

    def describe_capabilities(self) -> CapabilityReport:
        """Return a structured capability and hook report for this host."""
        ...


class ClaudeCodeRunner:
    """``HostRunner`` for the ``claude`` CLI (Claude Code).

    The argv produced by :meth:`build_streaming` mirrors
    :func:`little_loops.subprocess_utils.run_claude_command` so existing
    behavior is preserved when FEAT-1468 migrates call sites. The version
    snapshot lives in ``tests/test_host_runner.py::test_claude_runner_matches_legacy_args``.
    """

    name = "claude-code"

    capabilities = HostCapabilities(
        streaming=True,
        permission_skip=True,
        agent_select=True,
        tool_allowlist=True,
    )

    def detect(self) -> bool:
        return shutil.which("claude") is not None

    def build_streaming(
        self,
        *,
        prompt: str,
        working_dir: Path | None = None,
        resume: bool = False,
        agent: str | None = None,
        tools: list[str] | None = None,
        model: str | None = None,
    ) -> HostInvocation:
        args: list[str] = [
            "--dangerously-skip-permissions",
            "--verbose",
            "--output-format",
            "stream-json",
        ]
        if resume:
            args.append("--continue")
        args += ["-p", prompt]
        if agent:
            args += ["--agent", agent]
        if tools:
            args += ["--tools", ",".join(tools)]
        if model:
            args += ["--model", model]

        env: dict[str, str] = {
            "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1",
            "LL_NON_INTERACTIVE": "1",
            "DANGEROUSLY_SKIP_PERMISSIONS": "1",
        }
        if working_dir is not None:
            git_path = Path(working_dir) / ".git"
            if git_path.is_file():
                gitdir_ref = git_path.read_text().strip()
                if gitdir_ref.startswith("gitdir: "):
                    actual_gitdir = gitdir_ref[8:].strip()
                    resolved = (Path(working_dir) / actual_gitdir).resolve()
                    env["GIT_DIR"] = str(resolved)
                    env["GIT_WORK_TREE"] = str(working_dir)

        return HostInvocation(
            binary="claude",
            args=args,
            env=env,
            capabilities=self.capabilities,
        )

    def build_blocking_json(
        self,
        *,
        prompt: str,
        model: str | None = None,
        json_schema: dict | None = None,
    ) -> HostInvocation:
        args: list[str] = [
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "-p",
            prompt,
        ]
        if model:
            args += ["--model", model]
        # json_schema is part of the Protocol surface so other hosts can wire
        # structured-output constraints; the claude CLI does not currently
        # accept a schema flag, so we silently drop it here. Callers that
        # require schema enforcement should warn via CapabilityNotSupported.
        _ = json_schema
        return HostInvocation(
            binary="claude",
            args=args,
            env={"LL_NON_INTERACTIVE": "1", "DANGEROUSLY_SKIP_PERMISSIONS": "1"},
            capabilities=self.capabilities,
        )

    def build_version_check(self) -> HostInvocation:
        return HostInvocation(
            binary="claude",
            args=["--version"],
            env={},
            capabilities=self.capabilities,
        )

    def build_detached(self, *, prompt: str) -> HostInvocation:
        args = [
            "--dangerously-skip-permissions",
            "-p",
            prompt,
        ]
        return HostInvocation(
            binary="claude",
            args=args,
            env={"LL_NON_INTERACTIVE": "1", "DANGEROUSLY_SKIP_PERMISSIONS": "1"},
            capabilities=self.capabilities,
        )

    def describe_capabilities(self) -> CapabilityReport:
        return CapabilityReport(
            host=self.name,
            binary="claude",
            version="",
            capabilities=[
                CapabilityEntry("streaming", "full"),
                CapabilityEntry("permission_skip", "full"),
                CapabilityEntry("agent_select", "full"),
                CapabilityEntry("tool_allowlist", "full"),
                # build_blocking_json silently drops json_schema (no Codex-style warning)
                CapabilityEntry(
                    "json_schema",
                    "unsupported",
                    "claude CLI does not accept an inline schema flag; parameter is silently dropped",
                ),
            ],
        )


class CodexRunner:
    """``HostRunner`` for the ``codex`` CLI (OpenAI Codex, Rust-based GA build).

    Translates the Claude-shaped Protocol surface to Codex's ``codex exec``
    headless mode. See ``thoughts/research/codex-headless-invocation.md`` for
    the verified flag-translation table and source citations.

    Key divergences from :class:`ClaudeCodeRunner`:

    - Prompt is **positional** (``codex exec <prompt>``); Claude's ``-p`` maps
      to Codex ``--profile``, so we cannot reuse the same flag.
    - The combined ``--dangerously-bypass-approvals-and-sandbox`` flag is the
      1:1 equivalent of Claude's ``--dangerously-skip-permissions`` (skips
      both approval prompt and sandbox restrictions).
    - Codex has no single-blob JSON mode; ``--json`` always streams NDJSON
      events. ``build_blocking_json`` uses ``--json`` and callers must consume
      the final event.
    - Agent selection (``--agent``) has no CLI-flag equivalent in Codex.
      Codex *does* support custom subagents
      (`developers.openai.com/codex/subagents`_) defined in
      ``.codex/agents/*.toml``, but they are spawned by the model during a
      conversation rather than selected by the caller at invocation. The
      ``agent`` parameter is therefore dropped with a
      :class:`CapabilityNotSupported` warning; to get persona behavior under
      Codex, ship native ``.codex/agents/*.toml`` files via
      ``ll-adapt-agents-for-codex`` (mirrors ``ll-adapt-skills-for-codex``).
    - Tool allowlist (``--tools``) has no Codex equivalent — Codex routes
      tool access through sandbox modes, and ``--profile`` is for auth, not
      persona. Emits :class:`CapabilityNotSupported` when requested. The
      warnings here deliberately diverge from
      :class:`ClaudeCodeRunner.build_blocking_json` which silently drops
      ``json_schema``; FEAT-1465 AC requires the warning be emitted here so
      callers can degrade explicitly.

    .. _developers.openai.com/codex/subagents:
       https://developers.openai.com/codex/subagents
    - Resume restructures the subcommand to ``codex exec resume --last`` per
      Codex CLI reference, rather than appending a ``--continue`` flag.
    """

    name = "codex"

    capabilities = HostCapabilities(
        streaming=True,
        permission_skip=True,
        agent_select=False,
        tool_allowlist=False,
    )

    def detect(self) -> bool:
        return shutil.which("codex") is not None

    _VALID_SANDBOX_MODES = frozenset({"off", "read-only", "workspace-write", "danger-full-access"})

    @staticmethod
    def _sandbox_args(sandbox_mode: str | None) -> list[str]:
        """Return the Codex sandbox flag(s) for *sandbox_mode*.

        ``None`` or ``"off"`` → ``--dangerously-bypass-approvals-and-sandbox``
        (current default — skips both approval prompt and sandbox restrictions).
        ``"read-only"`` → ``--sandbox read-only``
        ``"workspace-write"`` → ``--sandbox workspace-write``
        ``"danger-full-access"`` → ``--sandbox danger-full-access``
        Other values raise :exc:`ValueError`.
        """
        if sandbox_mode is None or sandbox_mode == "off":
            return ["--dangerously-bypass-approvals-and-sandbox"]
        if sandbox_mode in CodexRunner._VALID_SANDBOX_MODES:
            return ["--sandbox", sandbox_mode]
        raise ValueError(
            f"Invalid sandbox_mode {sandbox_mode!r}. "
            f"Valid values: None, 'off', {', '.join(sorted(CodexRunner._VALID_SANDBOX_MODES))!r}"
        )

    @staticmethod
    def _emit_agent_warning(agent: str) -> None:
        # Note: this stderr print writes to the parent process's sys.stderr.
        # `subprocess_utils.run_claude_command()`'s `stream_callback(is_stderr=True)`
        # captures the spawned subprocess's stderr only — programmatic stream
        # consumers will not see this message; interactive terminals will.
        warnings.warn(
            "codex has no CLI-flag agent selection. Codex subagents "
            "(.codex/agents/*.toml) exist but are spawned by the model "
            "during a conversation, not selected at invocation. The "
            "'agent' parameter will be ignored; ship native Codex agent "
            "files for persona behavior under this host.",
            CapabilityNotSupported,
            stacklevel=3,
        )
        print(
            f"[ll] Warning: Codex does not support --agent at invocation time (ENH-1531).\n"
            f"     Persona hint {agent!r} was dropped. For interactive sessions,\n"
            f"     run `ll-adapt --host codex --apply` and use `--agent {agent}`\n"
            f"     in the Codex TUI.",
            file=sys.stderr,
        )

    @staticmethod
    def _inject_agent_persona(
        agent: str, prompt: str, working_dir: Path | None
    ) -> tuple[str, bool]:
        base = Path(working_dir) if working_dir is not None else Path.cwd()
        toml_path = base / ".codex" / "agents" / f"{agent}.toml"
        if not toml_path.exists():
            return prompt, False
        try:
            data = tomllib.loads(toml_path.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            return prompt, False
        instructions = str(data.get("developer_instructions", "")).strip()
        if not instructions:
            return prompt, False
        return f"[Persona: {agent}]\n{instructions}\n\n---\n\n{prompt}", True

    def build_streaming(
        self,
        *,
        prompt: str,
        working_dir: Path | None = None,
        resume: bool = False,
        agent: str | None = None,
        tools: list[str] | None = None,
        sandbox_mode: str | None = None,
        model: str | None = None,
    ) -> HostInvocation:
        del model  # codex does not support --model in streaming mode
        if agent is not None:
            prompt, injected = self._inject_agent_persona(agent, prompt, working_dir)
            if not injected:
                self._emit_agent_warning(agent)
        if tools:
            warnings.warn(
                "codex host does not support a tool allowlist; "
                "tool access is controlled via --sandbox mode. "
                "Use sandbox_mode='read-only' or 'workspace-write' for "
                "constrained Codex execution (ENH-1529). "
                "The 'tools' parameter will be ignored.",
                CapabilityNotSupported,
                stacklevel=2,
            )

        args: list[str] = ["exec"]
        if resume:
            args += ["resume", "--last"]
        args += self._sandbox_args(sandbox_mode)
        args += [
            "--json",
            "--skip-git-repo-check",
        ]
        if working_dir is not None:
            args += ["-C", str(working_dir)]
        args.append(prompt)

        env: dict[str, str] = {
            "LL_NON_INTERACTIVE": "1",
            "DANGEROUSLY_SKIP_PERMISSIONS": "1",
        }
        if working_dir is not None:
            git_path = Path(working_dir) / ".git"
            if git_path.is_file():
                gitdir_ref = git_path.read_text().strip()
                if gitdir_ref.startswith("gitdir: "):
                    actual_gitdir = gitdir_ref[8:].strip()
                    resolved = (Path(working_dir) / actual_gitdir).resolve()
                    env["GIT_DIR"] = str(resolved)
                    env["GIT_WORK_TREE"] = str(working_dir)

        return HostInvocation(
            binary="codex",
            args=args,
            env=env,
            capabilities=self.capabilities,
        )

    def build_blocking_json(
        self,
        *,
        prompt: str,
        model: str | None = None,
        json_schema: dict | None = None,
        sandbox_mode: str | None = None,
    ) -> HostInvocation:
        args: list[str] = ["exec"]
        args += self._sandbox_args(sandbox_mode)
        args += [
            "--json",
            "--skip-git-repo-check",
        ]
        if model:
            args += ["--model", model]

        cleanup: tuple[Path, ...] = ()
        if json_schema is not None:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".json", prefix="ll-schema-", mode="w"
            ) as f:
                json.dump(json_schema, f)
                schema_file = Path(f.name)
            args += ["--output-schema", str(schema_file)]
            cleanup = (schema_file,)

        args.append(prompt)
        return HostInvocation(
            binary="codex",
            args=args,
            env={"LL_NON_INTERACTIVE": "1", "DANGEROUSLY_SKIP_PERMISSIONS": "1"},
            capabilities=self.capabilities,
            cleanup_paths=cleanup,
        )

    def build_version_check(self) -> HostInvocation:
        return HostInvocation(
            binary="codex",
            args=["--version"],
            env={},
            capabilities=self.capabilities,
        )

    def build_detached(self, *, prompt: str, sandbox_mode: str | None = None) -> HostInvocation:
        args: list[str] = ["exec"]
        args += self._sandbox_args(sandbox_mode)
        args += [
            "--skip-git-repo-check",
            prompt,
        ]
        return HostInvocation(
            binary="codex",
            args=args,
            env={"LL_NON_INTERACTIVE": "1", "DANGEROUSLY_SKIP_PERMISSIONS": "1"},
            capabilities=self.capabilities,
        )

    def describe_capabilities(self) -> CapabilityReport:
        return CapabilityReport(
            host=self.name,
            binary="codex",
            version="",
            capabilities=[
                CapabilityEntry("streaming", "full"),
                CapabilityEntry("permission_skip", "full"),
                # agent_select=False bool stays False (no native --agent CLI flag),
                # but status is "partial" because build_streaming injects persona via
                # .codex/agents/<name>.toml `developer_instructions` when present.
                # Fallback path (TOML absent) emits CapabilityNotSupported + stderr notice.
                CapabilityEntry(
                    "agent_select",
                    "partial",
                    "codex has no native --agent CLI flag; build_streaming injects "
                    "`developer_instructions` from .codex/agents/<name>.toml into the "
                    "prompt as a persona prefix when the file exists. Falls back to "
                    "CapabilityNotSupported + stderr warning when the TOML is absent.",
                ),
                # tool_allowlist=False; partial constraint available via sandbox_mode=
                # parameter on build_streaming / build_blocking_json / build_detached
                # (ENH-1529). The --tools allowlist parameter is still unsupported.
                CapabilityEntry(
                    "tool_allowlist",
                    "partial",
                    "codex uses sandbox modes for tool access; --tools parameter is "
                    "unsupported, but sandbox_mode= parameter on build methods offers "
                    "constrained execution (off, read-only, workspace-write, "
                    "danger-full-access)",
                ),
                # json_schema: partial — --output-schema requires a file path; ENH-1530 bridges
                # via temp file written in build_blocking_json, path returned in cleanup_paths
                CapabilityEntry(
                    "json_schema",
                    "partial",
                    "codex --output-schema requires a file path; schema is written to a "
                    "temp file and path returned in HostInvocation.cleanup_paths for caller cleanup",
                ),
            ],
        )


class OpenCodeRunner:
    """``HostRunner`` stub for the ``opencode`` CLI (FEAT-1472, Option B).

    No external CLI research has been performed. Every ``build_*`` method
    raises :class:`HostNotConfigured` pointing callers at
    ``LL_HOST_CLI=claude-code``. Registration in ``_HOST_RUNNER_REGISTRY``
    means an explicit ``LL_HOST_CLI=opencode`` resolves to a useful error
    message rather than the generic "unknown host" error. The runner is
    deliberately absent from ``_PROBE_ORDER`` so no auto-detection occurs.
    """

    name = "opencode"

    capabilities = HostCapabilities()

    def detect(self) -> bool:
        return shutil.which("opencode") is not None

    def build_streaming(
        self,
        *,
        prompt: str,
        working_dir: Path | None = None,
        resume: bool = False,
        agent: str | None = None,
        tools: list[str] | None = None,
        model: str | None = None,
    ) -> HostInvocation:
        raise HostNotConfigured(
            "OpenCode orchestration not yet wired — research OpenCode headless CLI. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    def build_blocking_json(
        self,
        *,
        prompt: str,
        model: str | None = None,
        json_schema: dict | None = None,
    ) -> HostInvocation:
        raise HostNotConfigured(
            "OpenCode orchestration not yet wired — research OpenCode headless CLI. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    def build_version_check(self) -> HostInvocation:
        raise HostNotConfigured(
            "OpenCode orchestration not yet wired — research OpenCode headless CLI. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    def build_detached(self, *, prompt: str) -> HostInvocation:
        raise HostNotConfigured(
            "OpenCode orchestration not yet wired — research OpenCode headless CLI. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    def describe_capabilities(self) -> CapabilityReport:
        return CapabilityReport(
            host=self.name,
            binary="opencode",
            version="",
            capabilities=[
                CapabilityEntry(
                    "host",
                    "unsupported",
                    "binary not configured (HostNotConfigured) — opencode orchestration not yet wired",
                )
            ],
        )


class PiRunner:
    """``HostRunner`` stub for the ``pi`` CLI (FEAT-1472).

    Pi orchestration is tracked under FEAT-992; until that lands, all four
    ``build_*`` methods raise :class:`HostNotConfigured`. Unlike
    :class:`OpenCodeRunner`, ``("pi", "pi")`` is already present in
    ``_PROBE_ORDER`` (added in FEAT-1464), so registering ``PiRunner`` now
    activates that probe edge: hosts with ``pi`` on PATH will resolve to
    this stub and raise on the first ``build_*`` call.
    """

    name = "pi"

    capabilities = HostCapabilities()

    def detect(self) -> bool:
        return shutil.which("pi") is not None

    def build_streaming(
        self,
        *,
        prompt: str,
        working_dir: Path | None = None,
        resume: bool = False,
        agent: str | None = None,
        tools: list[str] | None = None,
        model: str | None = None,
    ) -> HostInvocation:
        raise HostNotConfigured(
            "Pi orchestration not yet wired — see FEAT-992. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    def build_blocking_json(
        self,
        *,
        prompt: str,
        model: str | None = None,
        json_schema: dict | None = None,
    ) -> HostInvocation:
        raise HostNotConfigured(
            "Pi orchestration not yet wired — see FEAT-992. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    def build_version_check(self) -> HostInvocation:
        raise HostNotConfigured(
            "Pi orchestration not yet wired — see FEAT-992. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    def build_detached(self, *, prompt: str) -> HostInvocation:
        raise HostNotConfigured(
            "Pi orchestration not yet wired — see FEAT-992. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    def describe_capabilities(self) -> CapabilityReport:
        return CapabilityReport(
            host=self.name,
            binary="pi",
            version="",
            capabilities=[
                CapabilityEntry(
                    "host",
                    "unsupported",
                    "binary not configured (HostNotConfigured) — see FEAT-992",
                )
            ],
        )


# Built-in host runners keyed by their ``name`` attribute. Extensions may
# register additional runners but built-ins always win on collision —
# mirrors ``hooks/__init__.py:_dispatch_table`` (built-ins shadow extensions).
_HOST_RUNNER_REGISTRY: dict[str, type[HostRunner]] = {
    "claude-code": ClaudeCodeRunner,
    "codex": CodexRunner,
    "opencode": OpenCodeRunner,
    "pi": PiRunner,
}

# Order of probing when no explicit host is configured. Matches the binary
# names users typically have on PATH; extends as new runners land.
_PROBE_ORDER: list[tuple[str, str]] = [
    ("claude-code", "claude"),
    ("codex", "codex"),
    ("pi", "pi"),
]


def _remediation_hint() -> str:
    return (
        "Set LL_HOST_CLI=<host> (one of: claude-code, codex, opencode, pi), "
        "or LL_HOOK_HOST, or configure orchestration.host_cli in ll-config.json, "
        "or install a supported host CLI on PATH (claude, codex, or pi)."
    )


def resolve_host(env: dict[str, str] | None = None) -> HostRunner:
    """Resolve the active :class:`HostRunner`.

    Detection order (first match wins):

    1. ``LL_HOST_CLI`` environment variable — explicit override.
    2. ``LL_HOOK_HOST`` environment variable — falls back to the hooks-layer
       host identifier so users with an existing hook config don't need a
       second knob.
    3. Binary probe: ``claude`` → ``codex`` → ``pi`` (see ``_PROBE_ORDER``).
    4. Raise :class:`HostNotConfigured` with a remediation hint.

    Args:
        env: Optional environment dict for testability. Defaults to
            ``os.environ`` when omitted.

    Returns:
        A :class:`HostRunner` instance ready to build invocations.

    Raises:
        HostNotConfigured: if no host can be resolved.
    """
    import os

    if env is None:
        env = dict(os.environ)

    explicit = env.get("LL_HOST_CLI") or env.get("LL_HOOK_HOST")
    if explicit:
        runner_cls = _HOST_RUNNER_REGISTRY.get(explicit)
        if runner_cls is not None:
            return runner_cls()
        raise HostNotConfigured(
            f"Host {explicit!r} is not registered. Available: "
            f"{sorted(_HOST_RUNNER_REGISTRY)}. {_remediation_hint()}"
        )

    for host_name, binary in _PROBE_ORDER:
        if shutil.which(binary) is None:
            continue
        runner_cls = _HOST_RUNNER_REGISTRY.get(host_name)
        if runner_cls is not None:
            return runner_cls()

    raise HostNotConfigured(f"No host CLI detected on PATH. {_remediation_hint()}")


def apply_host_cli_from_config(config: object) -> None:
    """Export ``orchestration.host_cli`` from *config* as ``LL_HOST_CLI``.

    Reads ``config.orchestration.host_cli`` (a :class:`~little_loops.config.OrchestrationConfig`
    attribute) and sets ``LL_HOST_CLI`` in the process environment so that a
    subsequent call to :func:`resolve_host` picks up the config-driven value.

    The env var takes precedence if already set — callers that set ``LL_HOST_CLI``
    explicitly in their environment are not overridden. This matches the
    documented resolution order (env var > config key > binary probe).

    Args:
        config: A :class:`~little_loops.config.BRConfig` instance (typed as
            ``object`` to avoid a circular import; the attribute access pattern
            is ``config.orchestration.host_cli``).
    """
    import os

    if os.environ.get("LL_HOST_CLI"):
        return  # explicit env override takes precedence
    try:
        host_cli: str | None = config.orchestration.host_cli  # type: ignore[attr-defined]
    except AttributeError:
        return  # config object doesn't support orchestration (e.g. tests)
    if host_cli:
        os.environ["LL_HOST_CLI"] = host_cli
