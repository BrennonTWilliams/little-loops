"""Pre-expand skill/command Markdown content for subprocess prompts.

Eliminates the ToolSearch → Skill deferred-tool dependency when ll-auto
spawns Claude subprocesses: instead of passing `/ll:<name> <args>`, Python
reads the skill file, substitutes all ``{{config.xxx}}`` placeholders and
the ``$ARGUMENTS`` marker, and returns a self-contained prompt string.

Falls back to None on any failure so callers can use the original slash
command.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from little_loops.config import BRConfig
from little_loops.frontmatter import strip_frontmatter


def _find_plugin_root() -> Path:
    """Return the plugin root directory.

    Checks ``CLAUDE_PLUGIN_ROOT`` env var first, then falls back to the
    project root derived from this file's location
    (``scripts/little_loops/skill_expander.py`` → three parents up).
    """
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parent.parent.parent


def _resolve_content_path(plugin_root: Path, name: str) -> Path | None:
    """Locate the skill or command Markdown file for *name*.

    Tries ``skills/{name}/SKILL.md`` first, then ``commands/{name}.md``.
    Returns the path if found, otherwise None.
    """
    skill_path = plugin_root / "skills" / name / "SKILL.md"
    if skill_path.exists():
        return skill_path

    command_path = plugin_root / "commands" / f"{name}.md"
    if command_path.exists():
        return command_path

    return None


def _substitute_config(content: str, config: BRConfig) -> str:
    """Replace ``{{config.xxx}}`` placeholders using *config*.

    Unresolvable placeholders are left as-is so downstream consumers can
    still inspect them (and callers can detect failure if needed).
    """

    def _replacer(match: re.Match[str]) -> str:
        var_path = match.group(1)
        value = config.resolve_variable(var_path)
        if value is None:
            return ""  # unconfigured → blank; removes placeholder
        return value

    return re.sub(r"\{\{config\.([^}]+)\}\}", _replacer, content)


def _substitute_relative_refs(content: str, content_dir: Path) -> str:
    """Convert relative Markdown link targets to absolute paths.

    Finds patterns like ``(templates.md)`` or ``(subdir/file.md)`` and
    replaces the target with the absolute path when the file exists next to
    the skill/command file.  Links to non-existent files are left unchanged.
    """

    def _replacer(match: re.Match[str]) -> str:
        target = match.group(1)
        # Skip already-absolute paths and URLs
        if target.startswith("/") or "://" in target:
            return match.group(0)
        candidate = content_dir / target
        if candidate.exists():
            return f"({candidate.resolve()})"
        return match.group(0)

    return re.sub(r"\(([^)]+\.md)\)", _replacer, content)


def _substitute_arguments(content: str, args: list[str]) -> str:
    """Replace the ``$ARGUMENTS`` token with the joined *args* string."""
    joined = " ".join(args)
    return content.replace("$ARGUMENTS", joined)


def expand_skill(name: str, args: list[str], config: BRConfig) -> str | None:
    """Pre-expand a skill or command into a self-contained prompt string.

    Reads the Markdown source for *name*, strips frontmatter, substitutes
    ``{{config.xxx}}`` placeholders, converts relative ``(file.md)``
    references to absolute paths, and replaces ``$ARGUMENTS`` with the
    joined *args*.

    Args:
        name: Skill or command name (e.g. ``"manage-issue"``, ``"ready-issue"``).
        args: Arguments that would normally follow the slash command.
        config: Project configuration used for placeholder substitution.

    Returns:
        Fully-expanded prompt string, or ``None`` on any failure (file not
        found, substitution error, …).  Callers should fall back to the
        original slash command when ``None`` is returned.
    """
    try:
        plugin_root = _find_plugin_root()
        content_path = _resolve_content_path(plugin_root, name)
        if content_path is None:
            return None

        raw = content_path.read_text(encoding="utf-8")
        body = strip_frontmatter(raw)
        body = _substitute_config(body, config)
        body = _substitute_relative_refs(body, content_path.parent)
        body = _substitute_arguments(body, args)
        return body
    except Exception:  # noqa: BLE001
        return None
