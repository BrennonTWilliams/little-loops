"""KimiEmitter: host adapter for the Kimi Code CLI (EPIC-2910, FEAT-2916).

Near-passthrough emitter. The FEAT-2911 research spike
(``thoughts/research/kimi-cli-surface.md``, kimi 0.30.0) verified that kimi
loads little-loops' source formats almost directly: SKILL.md skills parse
with extra frontmatter keys ignored, Claude-style agent files load natively,
and markdown command prompts are already kimi's command file shape. The
emitter's job is therefore *placement*, not translation:

- Skills land in ``.kimi-code/skills/<name>/SKILL.md`` (a native kimi scan
  dir), with ``name:`` injected when absent — kimi requires ``name`` +
  ``description`` in directory-form SKILL.md.
- Commands bridge into ``.kimi-code/skills/ll-<stem>/SKILL.md`` because kimi
  has no project-local *commands* discovery surface outside plugin
  manifests; a bridged skill is invocable as ``/ll-<stem>`` (the skill
  shorthand). The plugin route (``kimi.plugin.json``, FEAT-2917) provides
  the true ``/ll:<stem>`` namespace.
- Agents land in ``.kimi-code/agents/<name>.md`` — kimi natively loads
  Claude-style agent files (comma-separated ``tools``, filename fallback
  for ``name``) and spawns real subagents, so no degraded-mode emission is
  needed (``subagents="native"``, unlike gemini).

The registry key is deliberately ``kimi-code`` (not ``kimi``), breaking the
un-suffixed emitter convention: ``ll-verify-host-map`` check 2 only
cross-validates hosts in the ``HOST_CAPABILITIES`` ∩ ``_HOST_RUNNER_REGISTRY``
intersection, and the runner is keyed ``kimi-code`` (matches the
``claude-code`` precedent) — an un-suffixed key would silently exempt kimi
from cross-validation forever.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.adapters.capabilities import HOST_CAPABILITIES
from little_loops.adapters.core import _emit_mirrored_skill, _select_frontmatter_fields

__all__ = ["KimiEmitter"]


def _fields_read() -> tuple[str, ...]:
    """Frontmatter policy for kimi output, from the shared capability map."""
    return HOST_CAPABILITIES["kimi-code"].frontmatter_fields_read


class KimiEmitter:
    """Output emitter for the Kimi Code CLI (``--host kimi-code``).

    Writes to ``.kimi-code/skills/<name>/SKILL.md``,
    ``.kimi-code/skills/ll-<stem>/SKILL.md`` (bridged commands), and
    ``.kimi-code/agents/<name>.md``. See module docstring for why each
    surface is near-passthrough.
    """

    name = "kimi-code"

    def emit_skill(self, skill_meta: dict) -> str:
        """Write adapted SKILL.md to ``.kimi-code/skills/<name>/SKILL.md``.

        Companion files beside the source SKILL.md are mirrored alongside it
        (BUG-3164): adapted SKILL.md bodies reference companions by relative
        path, so a SKILL.md-only mirror dangles every read. Delegates to the
        shared mirrored-skill core.
        """
        return _emit_mirrored_skill(
            skill_meta,
            ".kimi-code",
            lambda content, name: _select_frontmatter_fields(content, name, _fields_read()),
        )

    def emit_command(self, cmd_meta: dict) -> str:
        """Bridge ``commands/<stem>.md`` to ``.kimi-code/skills/ll-<stem>/SKILL.md``.

        Kimi's only native *command* discovery is the plugin manifest
        (FEAT-2917); project-locally, bridging to a skill makes the command
        invocable as ``/ll-<stem>``. Command bodies already use kimi's
        ``$ARGUMENTS`` placeholder convention, so the body passes through
        verbatim; ``name: ll-<stem>`` is injected because directory-form
        SKILL.md requires it.
        """
        stem: str = cmd_meta["stem"]
        cmd_path: Path = cmd_meta["cmd_path"]
        content: str = cmd_meta["content"]
        apply: bool = cmd_meta["apply"]
        quiet: bool = cmd_meta["quiet"]

        label = f"ll-{stem}"

        # Derive output path: cmd_path is commands/<stem>.md; parent×2 = plugin root
        plugin_root = cmd_path.parent.parent
        out_path = plugin_root / ".kimi-code" / "skills" / label / "SKILL.md"

        new_content, _ = _select_frontmatter_fields(content, label, _fields_read())

        if out_path.exists() and out_path.read_text() == new_content:
            if not quiet:
                print(f"  SKIP   {label}: already adapted")
            return "skipped"

        if apply:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(new_content)
            if not quiet:
                print(f"  APPLY  {label}")
        else:
            if not quiet:
                print(f"  DRY    {label}")

        return "adapted"

    def emit_agent(self, agent_meta: dict) -> str:
        """Write a native agent file to ``.kimi-code/agents/<name>.md``.

        Kimi loads Claude-style agent files natively (comma-separated
        ``tools`` lists, ``name`` falling back to the filename) and spawns
        real subagents — this is a verbatim copy with ``name:`` injected
        when absent, not a degraded-mode emission.
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

    def emit_mcp_config(self, meta: dict) -> str:
        """No native MCP config emission for kimi-code yet; stub keeps ``HostEmitter`` satisfiable."""
        return "skipped"
