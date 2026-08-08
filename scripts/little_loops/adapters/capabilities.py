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
from typing import Literal

__all__ = ["HostCapabilityEntry", "HOST_CAPABILITIES", "SubagentSupport"]

# Two-value discriminator (ENH-2874). "native" = the host can spawn a real
# subagent for a role; "none" = it cannot, so agent emission (when it emits
# at all) falls back to a degraded inline-role file. A third value was
# considered (permission-gated spawning) but ENH-2874's research found no
# host that needs it — Codex's asymmetry vs. Claude Code is spawn-based
# (no `--agent` flag), not permission-gated, so the two-value flag is
# sufficient. See ENH-2874's Open Question / resolution notes.
SubagentSupport = Literal["native", "none"]


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
    subagents: SubagentSupport = "none"


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
        subagents="native",
    ),
    "gemini": HostCapabilityEntry(
        host="gemini",
        config_dir=".gemini",
        skill_output_format="SKILL.md (name injected, metadata.short-description stripped)",
        command_output_format="TOML (.gemini/commands/<stem>.toml)",
        # ENH-2874: Gemini cannot spawn a subagent, but emit_agent no longer
        # raises — it emits a degraded-mode inline-role file (Markdown,
        # .gemini/agents/<name>.md) generated from the same agents/*.md
        # source, prefixed with a preamble that instructs the model to
        # perform the role inline and disclose the substitution in its
        # report. `agents=True` reflects that this now produces real output;
        # `subagents="none"` records that it is degraded, not delegated. If
        # Gemini agents exit preview and gain native subagent spawning later,
        # flip subagents to "native" and this entry's agent_output_format to
        # describe the native format — no other code changes required.
        agent_output_format="Markdown inline-role file, degraded mode (.gemini/agents/<name>.md)",
        frontmatter_fields_read=("description", "name"),
        agents=True,
        commands=True,
        hooks=False,
        subagents="none",
    ),
    "omp": HostCapabilityEntry(
        host="omp",
        # emit_skill/emit_command are real (FEAT-3105), against the native
        # discovery format FEAT-3103's research spike documented in
        # thoughts/research/omp-skill-command-surface.md. emit_agent is real
        # (FEAT-3104): FEAT-2797 established omp discovers agents via a
        # native `.omp/agents/` scan dir and spawns real subagents from
        # them, the same native shape as kimi-code — hence
        # subagents="native" and a working agent_output_format, unlike
        # gemini's degraded path.
        config_dir=".omp",
        skill_output_format="SKILL.md (name injected when absent, .omp/skills/<name>/SKILL.md)",
        command_output_format="Markdown, flat file (.omp/commands/<stem>.md, self-derived path)",
        agent_output_format="Markdown, native task-agent file (.omp/agents/<name>.md)",
        frontmatter_fields_read=("description", "name"),
        agents=True,
        commands=True,
        hooks=False,
        subagents="native",
    ),
    "kimi-code": HostCapabilityEntry(
        host="kimi-code",
        config_dir=".kimi-code",
        skill_output_format="SKILL.md (name injected when absent, metadata.short-description stripped)",
        # Kimi has no project-local *commands* discovery outside plugin
        # manifests (FEAT-2917 covers that route), so commands bridge into
        # skills — the codex bridging pattern, minus the openai.yaml sidecar.
        command_output_format="bridged into .kimi-code/skills/ll-<stem>/ (SKILL.md)",
        # FEAT-2911 spike: kimi natively loads Claude-style agent files and
        # spawns real subagents — native emission, no degraded mode (ENH-2874
        # not needed). Key deliberately suffixed to match the runner registry
        # key so ll-verify-host-map check 2 cross-validates kimi (EPIC-2910).
        agent_output_format="Markdown, native Claude-style agent file (.kimi-code/agents/<name>.md)",
        frontmatter_fields_read=("description", "name"),
        agents=True,
        commands=True,
        hooks=True,
        subagents="native",
    ),
}
