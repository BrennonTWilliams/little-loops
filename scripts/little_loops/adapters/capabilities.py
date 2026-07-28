"""Declarative per-host capability map for adapter hosts (ENH-2873).

One :class:`HostCapabilityEntry` per host in ``adapters/core.py``'s
``_EMITTER_MAP`` (``"codex"``, ``"gemini"``, ``"omp"``). This module is the
single place adapter-host knowledge is written down as data; today the same
knowledge is scattered as code across ``codex.py``, ``gemini.py``, and
``omp.py`` (which fields a host reads, whether it takes agents, how tools map
to a sandbox mode). ``ENH-2883`` will drive ``core.py``'s dispatch from these
entries; this module is additive only — it does not change emission
behavior.

**Relationship to `host_runner.HostCapabilities` (Option B, decided
2026-07-28):** this map is a distinct **build-time** surface — "what does
`ll-adapt` write for this host" — cross-referenced by docstring only, with no
inheritance from `host_runner.HostCapabilities` (a **runtime** invocation
surface: "what can this host's CLI do when it's running"). The two key sets
are not congruent (this module: ``codex``/``gemini``/``omp``; `host_runner`
adds ``claude-code``/``opencode``/``pi``), which makes an "extends"
relationship structurally awkward for hosts on only one side. Precedent:
``cli/doctor.py``'s ``CheckResult`` mirrors `host_runner.CapabilityEntry`'s
shape in its docstring without subclassing it. See
`host_runner.HostCapabilities` for the runtime-side surface and
``docs/reference/HOST_COMPATIBILITY.md`` for the authoritative parity matrix
both sides are checked against.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["HostCapabilityEntry", "HOST_CAPABILITIES"]


@dataclass(frozen=True)
class HostCapabilityEntry:
    """Declarative description of one adapter host's emission surface.

    Frozen, following the `HostInvocation`/`HostCapabilities` convention
    established in `host_runner.py`.
    """

    host: str
    config_dir: str | None
    skill_output_format: str | None
    command_output_format: str | None
    agent_output_format: str | None
    frontmatter_fields_read: tuple[str, ...] = field(default_factory=tuple)
    agents: bool = False
    commands: bool = False
    hooks: bool = False
    subagents: bool = False


HOST_CAPABILITIES: dict[str, HostCapabilityEntry] = {
    "codex": HostCapabilityEntry(
        host="codex",
        config_dir=".codex",
        skill_output_format="SKILL.md + agents/openai.yaml sidecar (Codex Skills API)",
        command_output_format="bridged into skills/ll-<stem>/ (SKILL.md + openai.yaml)",
        agent_output_format="TOML (.codex/agents/<name>.toml)",
        frontmatter_fields_read=("description", "name", "metadata.short-description", "tools"),
        agents=True,
        commands=True,
        hooks=True,
        # Agent selection is "partial (subagents)" per HOST_COMPATIBILITY.md's
        # Runner Capabilities table — Codex supports subagents but has no
        # `--agent` flag for direct selection.
        subagents=True,
    ),
    "gemini": HostCapabilityEntry(
        host="gemini",
        config_dir=".gemini",
        skill_output_format="SKILL.md (name injected, metadata.short-description stripped)",
        command_output_format="TOML (.gemini/commands/<stem>.toml)",
        # emit_agent unconditionally raises AdapterError(_AGENT_STUB_MSG) —
        # Gemini agents are a preview feature (gemini.py:16). This entry must
        # reflect that stub, not aspirational support.
        agent_output_format=None,
        frontmatter_fields_read=("description", "name"),
        agents=False,
        commands=True,
        hooks=False,
        subagents=False,
    ),
    "omp": HostCapabilityEntry(
        host="omp",
        # All three emit_* methods raise AdapterError(_REMEDIATION) — omp.py
        # is a 28-line stub (EPIC-2258). This entry describes it as fully
        # unimplemented, per ENH-2873's Scope Boundaries.
        config_dir=None,
        skill_output_format=None,
        command_output_format=None,
        agent_output_format=None,
        frontmatter_fields_read=(),
        agents=False,
        commands=False,
        hooks=False,
        subagents=False,
    ),
}
