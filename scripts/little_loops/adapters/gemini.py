"""GeminiEmitter: host adapter for the Gemini CLI.

Consolidates FEAT-2188 (skill frontmatter) and FEAT-2189 (commands TOML)
into a single emitter following the pattern established by CodexEmitter (FEAT-2391).
"""

from __future__ import annotations

from pathlib import Path

from little_loops.adapters.capabilities import HOST_CAPABILITIES
from little_loops.adapters.core import (
    _emit_degraded_agent,
    _emit_mirrored_skill,
    _extract_body,
    _select_frontmatter_fields,
)

__all__ = ["GeminiEmitter"]


# ---------------------------------------------------------------------------
# Skill helpers
# ---------------------------------------------------------------------------


def _prepare_skill_content(content: str, skill_name: str) -> tuple[str, bool]:
    """Return modified SKILL.md content for Gemini output plus a changed flag.

    Injects ``name: <skill_name>`` when absent and removes
    ``metadata.short-description:`` — both selected from
    ``HOST_CAPABILITIES["gemini"].frontmatter_fields_read`` via the shared
    :func:`little_loops.adapters.core._select_frontmatter_fields` helper
    (ENH-2883), not host-private regex logic.
    """
    fields_read = HOST_CAPABILITIES["gemini"].frontmatter_fields_read
    return _select_frontmatter_fields(content, skill_name, fields_read)


# ---------------------------------------------------------------------------
# Command helpers
# ---------------------------------------------------------------------------


def _make_command_toml(description: str, body: str) -> str:
    """Return TOML content for ``.gemini/commands/<stem>.toml``.

    Emits ``description`` (optional) and ``prompt`` (required) — the two
    fields Gemini command TOML supports.
    """
    safe_body = body.replace('"""', '\\"\\"\\"')
    if not safe_body.endswith("\n"):
        safe_body += "\n"

    lines: list[str] = []
    if description.strip():
        escaped = description.strip().replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'description = "{escaped}"')
    lines.append(f'prompt = """\n{safe_body}"""')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# GeminiEmitter
# ---------------------------------------------------------------------------


class GeminiEmitter:
    """Output emitter for the Gemini CLI (``--host gemini``).

    Writes to ``.gemini/skills/<name>/SKILL.md`` and
    ``.gemini/commands/<stem>.toml``.  Gemini cannot spawn a native
    subagent, so agent emission produces a degraded-mode inline-role file
    at ``.gemini/agents/<name>.md`` instead (ENH-2874) — the role's
    authored body, prefixed with a preamble instructing the model to
    perform the role inline and disclose the substitution in its report.
    """

    name = "gemini"

    def emit_skill(self, skill_meta: dict) -> str:
        """Write adapted SKILL.md to ``.gemini/skills/<name>/SKILL.md``.

        Companion files beside the source SKILL.md are mirrored alongside it
        (BUG-3164): adapted SKILL.md bodies reference companions by relative
        path, so a SKILL.md-only mirror dangles every read. Delegates to the
        shared mirrored-skill core with gemini's content-prep policy.
        """
        return _emit_mirrored_skill(skill_meta, ".gemini", _prepare_skill_content)

    def emit_command(self, cmd_meta: dict) -> str:
        """Write ``.gemini/commands/<stem>.toml``."""
        stem: str = cmd_meta["stem"]
        cmd_path: Path = cmd_meta["cmd_path"]
        content: str = cmd_meta["content"]
        fm: dict = cmd_meta["fm"]
        apply: bool = cmd_meta["apply"]
        quiet: bool = cmd_meta["quiet"]

        label = f"ll-{stem}"

        body = _extract_body(content)
        if not body.strip():
            if not quiet:
                print(f"  SKIP   {label}: no prompt body")
            return "skipped"

        # Derive output path: cmd_path is commands/<stem>.md; parent×2 = plugin root
        plugin_root = cmd_path.parent.parent
        out_path = plugin_root / ".gemini" / "commands" / f"{stem}.toml"

        description = str(fm.get("description", "") or "")
        toml_content = _make_command_toml(description, body)

        if out_path.exists() and out_path.read_text() == toml_content:
            if not quiet:
                print(f"  SKIP   {label}: already adapted")
            return "skipped"

        if apply:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(toml_content)
            if not quiet:
                print(f"  APPLY  {label}")
        else:
            if not quiet:
                print(f"  DRY    {label}")

        return "adapted"

    def emit_agent(self, agent_meta: dict) -> str:
        """Write a degraded-mode inline-role file to ``.gemini/agents/<name>.md``.

        Gemini has no native subagent-spawning support, so this routes
        through the shared degraded-emission helper (ENH-2874) rather than
        emitting a native format. See :func:`little_loops.adapters.core._emit_degraded_agent`.
        """
        return _emit_degraded_agent(agent_meta)

    def emit_mcp_config(self, meta: dict) -> str:
        """No native MCP config emission for Gemini yet; stub keeps ``HostEmitter`` satisfiable."""
        return "skipped"
