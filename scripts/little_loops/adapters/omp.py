"""OmpEmitter (``--host omp``) — full implementation (EPIC-2258).

``emit_agent`` is real: FEAT-2797 established that omp discovers agents via
``.omp/agents/`` (a native scan dir, ignoring ``.claude/agents``/
``.codex/agents``) with a frontmatter ``output:`` key for an optional
per-agent output schema. omp natively spawns real subagents from these
files (``subagents="native"``), the same shape as ``KimiEmitter.emit_agent``
— this is a verbatim copy with ``name:`` injected when absent, not a
degraded-mode emission. ``frontmatter_fields_read`` carries ``output:``
through unmodified when a source agent defines one (none currently do; ll
agent definitions have no schema to express yet).

``emit_skill``/``emit_command`` are real as of FEAT-3105, against the
native discovery format FEAT-3103's research spike documented in
``thoughts/research/omp-skill-command-surface.md``:

- Skills: one directory per skill, ``<plugin_root>/.omp/skills/<name>/
  SKILL.md`` — the same shape as ``KimiEmitter.emit_skill``/
  ``GeminiEmitter.emit_skill``, with ``name:`` injected when absent
  (``description`` is required by omp's native loader and is expected to
  already be present on every source SKILL.md).
- Commands: a flat ``<plugin_root>/.omp/commands/<stem>.md`` file — no
  directory wrapper, no bridging into ``skills/`` (unlike Codex/Kimi).
  ``emit_command`` self-derives the plugin root from ``cmd_meta["cmd_path"]``
  and ignores ``cmd_meta["output_dir"]`` (the Gemini shape, not the Codex
  shape), since omp's flat commands surface has no relationship to a
  skills tree. Content passes through verbatim — omp reads ``description``
  optionally (falling back to a truncated first body line) and everything
  else, including ``$ARGUMENTS``, is resolved downstream of discovery.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.adapters.capabilities import HOST_CAPABILITIES
from little_loops.adapters.core import _select_frontmatter_fields

__all__ = ["OmpEmitter"]


def _fields_read() -> tuple[str, ...]:
    """Frontmatter policy for omp output, from the shared capability map."""
    return HOST_CAPABILITIES["omp"].frontmatter_fields_read


class OmpEmitter:
    """Emitter for the omp surface (``--host omp``). All three artefact types are real."""

    name = "omp"

    def emit_skill(self, skill_meta: dict) -> str:
        """Write adapted SKILL.md to ``.omp/skills/<name>/SKILL.md``."""
        skill_name: str = skill_meta["skill_name"]
        skill_path: Path = skill_meta["skill_path"]
        content: str = skill_meta["content"]
        apply: bool = skill_meta["apply"]
        quiet: bool = skill_meta["quiet"]

        # Derive output path: skill_path is skills/<name>/SKILL.md; parent×3 = plugin root
        plugin_root = skill_path.parent.parent.parent
        out_path = plugin_root / ".omp" / "skills" / skill_name / "SKILL.md"

        new_content, _ = _select_frontmatter_fields(content, skill_name, _fields_read())

        if out_path.exists() and out_path.read_text() == new_content:
            if not quiet:
                print(f"  SKIP   {skill_name}: already adapted")
            return "skipped"

        if apply:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(new_content)
            if not quiet:
                print(f"  APPLY  {skill_name}")
        else:
            if not quiet:
                print(f"  DRY    {skill_name}")

        return "adapted"

    def emit_command(self, cmd_meta: dict) -> str:
        """Write a flat command file to ``.omp/commands/<stem>.md`` (self-derived path)."""
        stem: str = cmd_meta["stem"]
        cmd_path: Path = cmd_meta["cmd_path"]
        content: str = cmd_meta["content"]
        apply: bool = cmd_meta["apply"]
        quiet: bool = cmd_meta["quiet"]

        label = f"ll-{stem}"

        # Self-derive output path (Gemini shape, not Codex/Kimi bridging):
        # cmd_path is commands/<stem>.md; parent×2 = plugin root. omp's flat
        # .omp/commands/ is unrelated to the plugin's skills/ tree, so
        # cmd_meta["output_dir"] (the caller-supplied skills_dir) is unused.
        plugin_root = cmd_path.parent.parent
        out_path = plugin_root / ".omp" / "commands" / f"{stem}.md"

        if out_path.exists() and out_path.read_text() == content:
            if not quiet:
                print(f"  SKIP   {label}: already adapted")
            return "skipped"

        if apply:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content)
            if not quiet:
                print(f"  APPLY  {label}")
        else:
            if not quiet:
                print(f"  DRY    {label}")

        return "adapted"

    def emit_agent(self, agent_meta: dict) -> str:
        """Write a native agent file to ``.omp/agents/<name>.md``.

        omp loads task-agent files natively and spawns real subagents
        (FEAT-2797) — this is a verbatim copy with ``name:`` injected when
        absent, not a degraded-mode emission.
        """
        agent_name: str = agent_meta["agent_name"]
        content: str = agent_meta["content"]
        output_dir: Path = agent_meta["output_dir"]
        apply: bool = agent_meta["apply"]
        quiet: bool = agent_meta["quiet"]

        new_content, _ = _select_frontmatter_fields(content, agent_name, _fields_read())
        out_path = output_dir / f"{agent_name}.md"

        if out_path.exists() and out_path.read_text() == new_content:
            if not quiet:
                print(f"  SKIP   {agent_name}: already adapted")
            return "skipped"

        if apply:
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(new_content)
            if not quiet:
                print(f"  APPLY  {agent_name}: native agent file")
        else:
            if not quiet:
                print(f"  DRY    {agent_name}: native agent file")

        return "adapted"
