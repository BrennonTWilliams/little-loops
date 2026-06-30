"""GeminiEmitter: host adapter for the Gemini CLI.

Consolidates FEAT-2188 (skill frontmatter) and FEAT-2189 (commands TOML)
into a single emitter following the pattern established by CodexEmitter (FEAT-2391).
"""

from __future__ import annotations

import re
from pathlib import Path

from little_loops.adapters.core import AdapterError, _extract_body

__all__ = ["GeminiEmitter"]

_AGENT_STUB_MSG = (
    "gemini agent emission not yet stable — "
    "Gemini agents are a preview feature; open a PR when they exit preview"
)

_FM_CLOSE_RE = re.compile(r"\n---\s*\n")


# ---------------------------------------------------------------------------
# Skill helpers
# ---------------------------------------------------------------------------


def _inject_name(fm_text: str, name: str) -> tuple[str, bool]:
    """Inject ``name: <name>`` at the top of frontmatter text if absent."""
    if re.search(r"^name\s*:", fm_text, re.MULTILINE):
        return fm_text, False
    return f"name: {name}\n" + fm_text, True


def _strip_metadata_short_description(fm_text: str) -> tuple[str, bool]:
    """Remove ``metadata.short-description:`` from frontmatter text.

    Removes the line entirely, then removes the ``metadata:`` header if no
    other indented keys remain under it.  Returns ``(new_fm_text, changed)``.
    """
    if "short-description:" not in fm_text:
        return fm_text, False

    cleaned = re.sub(r"^[ \t]*short-description:.*$\n?", "", fm_text, flags=re.MULTILINE)
    # Remove empty metadata: header (followed immediately by blank line or end)
    cleaned = re.sub(r"^metadata:[ \t]*\n(?=\n|\Z)", "", cleaned, flags=re.MULTILINE)
    return cleaned, cleaned != fm_text


def _prepare_skill_content(content: str, skill_name: str) -> tuple[str, bool]:
    """Return modified SKILL.md content for Gemini output plus a changed flag.

    Injects ``name: <skill_name>`` when absent and removes
    ``metadata.short-description:`` (Codex-only field).
    """
    if not content.startswith("---\n"):
        return content, False

    m = _FM_CLOSE_RE.search(content[3:])
    if not m:
        return content, False

    fm_text = content[4 : 3 + m.start()]
    after = content[3 + m.start() :]

    changed = False

    fm_text, name_changed = _inject_name(fm_text, skill_name)
    changed = changed or name_changed

    fm_text, strip_changed = _strip_metadata_short_description(fm_text)
    changed = changed or strip_changed

    return f"---\n{fm_text}{after}", changed


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
    ``.gemini/commands/<stem>.toml``.  Agent emission raises
    :class:`AdapterError` — Gemini agents are a preview feature.
    """

    name = "gemini"

    def emit_skill(self, skill_meta: dict) -> str:
        """Write adapted SKILL.md to ``.gemini/skills/<name>/SKILL.md``."""
        skill_name: str = skill_meta["skill_name"]
        skill_path: Path = skill_meta["skill_path"]
        content: str = skill_meta["content"]
        apply: bool = skill_meta["apply"]
        quiet: bool = skill_meta["quiet"]

        # Derive output path: skill_path is skills/<name>/SKILL.md; parent×3 = plugin root
        plugin_root = skill_path.parent.parent.parent
        out_path = plugin_root / ".gemini" / "skills" / skill_name / "SKILL.md"

        new_content, _ = _prepare_skill_content(content, skill_name)

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
        raise AdapterError(_AGENT_STUB_MSG)
