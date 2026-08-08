"""OmpEmitter (``--host omp``) — partial implementation (EPIC-2258).

``emit_agent`` is real: FEAT-2797 established that omp discovers agents via
``.omp/agents/`` (a native scan dir, ignoring ``.claude/agents``/
``.codex/agents``) with a frontmatter ``output:`` key for an optional
per-agent output schema. omp natively spawns real subagents from these
files (``subagents="native"``), the same shape as ``KimiEmitter.emit_agent``
— this is a verbatim copy with ``name:`` injected when absent, not a
degraded-mode emission. ``frontmatter_fields_read`` carries ``output:``
through unmodified when a source agent defines one (none currently do; ll
agent definitions have no schema to express yet).

``emit_skill``/``emit_command`` remain stubs raising :class:`AdapterError` —
skill/command support needs FEAT-3103/FEAT-3105 first.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.adapters.capabilities import HOST_CAPABILITIES
from little_loops.adapters.core import AdapterError, _select_frontmatter_fields

__all__ = ["OmpEmitter"]

_REMEDIATION = "omp emitter not yet implemented — open a PR adding adapters/omp.py"


def _fields_read() -> tuple[str, ...]:
    """Frontmatter policy for omp agent output, from the shared capability map."""
    return HOST_CAPABILITIES["omp"].frontmatter_fields_read


class OmpEmitter:
    """Emitter for the omp surface. ``emit_agent`` is real; skill/command still raise."""

    name = "omp"

    def emit_skill(self, skill_meta: dict) -> str:
        raise AdapterError(_REMEDIATION)

    def emit_command(self, cmd_meta: dict) -> str:
        raise AdapterError(_REMEDIATION)

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
