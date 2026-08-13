"""QwenEmitter: host adapter for Qwen Code (EPIC-3154, FEAT-3159).

The cheapest emitter yet. The FEAT-3155 research spike
(``thoughts/research/qwen-code-surface.md``, qwen 0.21.6) verified that Qwen
Code's discovery surfaces are Markdown-native and accept little-loops'
source formats with near-zero translation:

- Skills land in ``.qwen/skills/<name>/SKILL.md`` with ``name:`` injected
  when absent; Claude-only frontmatter keys (``allowed-tools``,
  ``metadata.short-description`` aside) are tolerated — a probe skill
  carrying them loaded and invoked successfully.
- Commands land in ``.qwen/commands/ll/<stem>.md`` — Qwen's native
  subdirectory namespacing yields ``/ll:<stem>`` (live-verified), so no
  skill-bridging fallback is needed (better than Codex and Kimi). The body
  is emitted verbatim with ``$ARGUMENTS`` → ``{{args}}`` rewritten; only
  ``description:`` is carried in the frontmatter (Qwen's documented command
  schema).
- Agents land in ``.qwen/agents/<name>.md`` verbatim — Qwen documents
  explicit Claude Code 2.1.168 frontmatter compatibility, and the spike
  confirmed all nine ll agents load from the converted extension. Native
  subagent spawning → ``subagents="native"``, no degraded mode.

The registry key is ``qwen`` — matching the runner registry key so
``ll-verify-host-map`` check 2 cross-validates the host (EPIC-3154 naming
decision; un-suffixed per the majority convention since key/binary/config
dir align on ``qwen``).
"""

from __future__ import annotations

from pathlib import Path

from little_loops.adapters.capabilities import HOST_CAPABILITIES
from little_loops.adapters.core import _read_frontmatter, _select_frontmatter_fields

__all__ = ["QwenEmitter"]


def _fields_read() -> tuple[str, ...]:
    """Frontmatter policy for qwen output, from the shared capability map."""
    return HOST_CAPABILITIES["qwen"].frontmatter_fields_read


class QwenEmitter:
    """Output emitter for Qwen Code (``--host qwen``).

    Writes to ``.qwen/skills/<name>/SKILL.md``,
    ``.qwen/commands/ll/<stem>.md`` (native ``/ll:<stem>`` namespace), and
    ``.qwen/agents/<name>.md``. See module docstring for why each surface is
    near-passthrough.
    """

    name = "qwen"

    def emit_skill(self, skill_meta: dict) -> str:
        """Write adapted SKILL.md to ``.qwen/skills/<name>/SKILL.md``."""
        skill_name: str = skill_meta["skill_name"]
        skill_path: Path = skill_meta["skill_path"]
        content: str = skill_meta["content"]
        apply: bool = skill_meta["apply"]
        quiet: bool = skill_meta["quiet"]

        # Derive output path: skill_path is skills/<name>/SKILL.md; parent×3 = plugin root
        plugin_root = skill_path.parent.parent.parent
        out_path = plugin_root / ".qwen" / "skills" / skill_name / "SKILL.md"

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
        """Write ``commands/<stem>.md`` to ``.qwen/commands/ll/<stem>.md``.

        Qwen's native subdirectory namespacing maps ``ll/<stem>.md`` to
        ``/ll:<stem>`` (live-verified by the FEAT-3155 probe), so commands
        emit as first-class commands — no skill bridging. Only
        ``description:`` is carried in the frontmatter (Qwen's documented
        command schema); the body passes through with ``$ARGUMENTS``
        rewritten to Qwen's ``{{args}}`` injection placeholder.
        """
        stem: str = cmd_meta["stem"]
        cmd_path: Path = cmd_meta["cmd_path"]
        content: str = cmd_meta["content"]
        apply: bool = cmd_meta["apply"]
        quiet: bool = cmd_meta["quiet"]

        # Derive output path: cmd_path is commands/<stem>.md; parent×2 = plugin root
        plugin_root = cmd_path.parent.parent
        out_path = plugin_root / ".qwen" / "commands" / "ll" / f"{stem}.md"

        fm = _read_frontmatter(content) or {}
        description = str(fm.get("description", "")).strip()
        # Body = everything after the frontmatter block.
        body = content
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                body = content[end + 3 :]
                if body.startswith("\n"):
                    body = body[1:]
        body = body.replace("$ARGUMENTS", "{{args}}")

        if description:
            new_content = f"---\ndescription: {description}\n---\n{body}"
        else:
            new_content = body

        if out_path.exists() and out_path.read_text() == new_content:
            if not quiet:
                print(f"  SKIP   ll:{stem}: already adapted")
            return "skipped"

        if apply:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(new_content)
            if not quiet:
                print(f"  APPLY  ll:{stem}")
        else:
            if not quiet:
                print(f"  DRY    ll:{stem}")

        return "adapted"

    def emit_agent(self, agent_meta: dict) -> str:
        """Write a native agent file to ``.qwen/agents/<name>.md``.

        Qwen documents explicit Claude Code 2.1.168 frontmatter
        compatibility (``permissionMode``, ``maxTurns``, ``color``,
        ``mcpServers``, ``hooks`` parsed identically) and the FEAT-3155
        spike confirmed all nine ll agents load from a converted extension —
        this is a verbatim copy with ``name:`` injected when absent, not a
        degraded-mode emission.
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
        """No native MCP config emission for qwen yet; stub keeps ``HostEmitter`` satisfiable."""
        return "skipped"
