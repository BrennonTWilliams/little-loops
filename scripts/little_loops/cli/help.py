"""ll-help: generate the command/skill catalog from frontmatter (FEAT-2940).

Replaces the hand-maintained catalog that used to live in ``commands/help.md``.
Scans ``commands/*.md`` and ``skills/*/SKILL.md`` frontmatter at runtime so the
catalog can never drift from what's actually installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from little_loops.adapters.core import _is_model_invocation_disabled
from little_loops.frontmatter import parse_frontmatter, parse_skill_frontmatter
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = ["HelpEntry", "collect_entries", "render_catalog", "main_help"]

# Name -> area lookup, seeded from .claude/CLAUDE.md's "Commands & Skills"
# section. There is no frontmatter field for this grouping (deliberately —
# adding one would just move the drift the issue is trying to remove into a
# second hand-maintained place), so this table is the single hand-maintained
# seam. Entries absent from this table fall back to area "Other".
_AREA_MAP: dict[str, str] = {
    name: area
    for area, names in {
        "Issue Discovery": [
            "capture-issue",
            "scan-codebase",
            "scan-product",
            "audit-architecture",
            "product-analyzer",
            "scope-epic",
        ],
        "Issue Refinement": [
            "normalize-issues",
            "prioritize-issues",
            "align-issues",
            "format-issue",
            "refine-issue",
            "reconcile-issue",
            "wire-issue",
            "verify-issues",
            "tradeoff-review-issues",
            "ready-issue",
            "issue-workflow",
            "issue-size-review",
            "map-dependencies",
            "audit-issue-conflicts",
            "link-epics",
        ],
        "Planning & Implementation": [
            "create-sprint",
            "review-sprint",
            "review-epic",
            "manage-issue",
            "iterate-plan",
            "confidence-check",
            "go-no-go",
            "create-eval-from-issues",
            "spike",
        ],
        "Code Quality": [
            "check-code",
            "run-tests",
            "audit-docs",
            "update-docs",
            "find-dead-code",
        ],
        "Git & Release": [
            "commit",
            "open-pr",
            "describe-pr",
            "manage-release",
            "sync-issues",
            "cleanup-worktrees",
        ],
        "Automation & Loops": [
            "create-loop",
            "loop-suggester",
            "review-loop",
            "simplify-loop",
            "debug-loop-run",
            "audit-loop-run",
            "rename-loop",
            "cleanup-loops",
            "workflow-automation-proposer",
            "verify-issue-loop",
            "distill-traces",
        ],
        "Meta-Analysis": [
            "audit-claude-config",
            "analyze-workflows",
            "analyze-history",
            "improve-claude-md",
        ],
        "Session & Config": [
            "init",
            "configure",
            "update",
            "help",
            "handoff",
            "resume",
            "toggle-autoprompt",
        ],
    }.items()
    for name in names
}

_OTHER_AREA = "Other"


@dataclass(frozen=True)
class HelpEntry:
    """One catalog row — a single `/ll:` command or model-invocable skill."""

    name: str
    kind: Literal["command", "skill"]
    description: str
    argument_hint: str | None
    area: str


def _clean(value: object) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _argument_hint_from_list(arguments: object) -> str | None:
    """Render a structured `arguments:` YAML list into a display hint.

    Handles the shape used across `commands/*.md` (a list of
    ``{name, description, required}`` mappings) — the case
    :func:`parse_skill_frontmatter` silently drops because it only keeps
    string-valued frontmatter fields.
    """
    if not isinstance(arguments, list):
        return None
    parts: list[str] = []
    for item in arguments:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        # `parse_frontmatter` uses `yaml.BaseLoader`, which resolves every
        # scalar (including booleans) to a string — `required: false` comes
        # through as the string "false", not Python `False`.
        required = str(item.get("required", "")).strip().lower() in ("true", "1", "yes")
        parts.append(f"{name}" if required else f"[{name}]")
    return " ".join(parts) if parts else None


def _command_entries(commands_dir: Path) -> list[HelpEntry]:
    entries: list[HelpEntry] = []
    for command_md in sorted(commands_dir.glob("*.md")):
        name = command_md.stem
        try:
            content = command_md.read_text()
        except OSError:
            content = ""
        fm = parse_frontmatter(content) if content else {}
        description = _clean(fm.get("description"))
        hint = fm.get("argument-hint")
        argument_hint = _clean(hint) if hint else _argument_hint_from_list(fm.get("arguments"))
        entries.append(
            HelpEntry(
                name=name,
                kind="command",
                description=description,
                argument_hint=argument_hint or None,
                area=_AREA_MAP.get(name, _OTHER_AREA),
            )
        )
    return entries


def _skill_entries(skills_dir: Path, command_names: frozenset[str]) -> list[HelpEntry]:
    entries: list[HelpEntry] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        name = skill_md.parent.name
        try:
            content = skill_md.read_text()
        except OSError:
            content = ""
        fm = parse_skill_frontmatter(content) if content else {}
        if _is_model_invocation_disabled(fm) and name in command_names:
            # Codex-bridge stub mirroring `commands/<name>.md` 1:1 — the
            # command is already listed via `_command_entries`; listing both
            # would double every command/skill pair. A `disable-model-
            # invocation` skill with *no* matching command (e.g. `init`,
            # `update`) is a standalone skill, not a bridge, and stays.
            continue
        description = _clean(fm.get("description"))
        raw_args = fm.get("args") or fm.get("argument-hint")
        argument_hint = _clean(raw_args) if raw_args else None
        entries.append(
            HelpEntry(
                name=name,
                kind="skill",
                description=description,
                argument_hint=argument_hint,
                area=_AREA_MAP.get(name, _OTHER_AREA),
            )
        )
    return entries


def collect_entries(plugin_root: Path) -> list[HelpEntry]:
    """Scan ``commands/*.md`` and ``skills/*/SKILL.md`` for the catalog.

    Shared with `cli/action.py::_load_skills`, which projects the skill half
    of this list back down to its narrower historical shape.
    """
    command_entries = _command_entries(plugin_root / "commands")
    command_names = frozenset(e.name for e in command_entries)
    entries = command_entries + _skill_entries(plugin_root / "skills", command_names)
    return sorted(entries, key=lambda e: (e.area, e.name))


def render_catalog(entries: list[HelpEntry], area: str | None, fmt: str) -> str:
    """Render *entries* as ``"md"`` (human-readable text) or ``"json"``."""
    if area:
        entries = [e for e in entries if e.area == area]

    if fmt == "json":
        return json.dumps([asdict(e) for e in entries], indent=2)

    if not entries:
        return "No commands or skills found."

    lines: list[str] = []
    current_area: str | None = None
    for entry in entries:
        if entry.area != current_area:
            current_area = entry.area
            lines.append(f"\n## {current_area}\n")
        prefix = "/ll:" if entry.kind == "command" else ""
        hint = f" {entry.argument_hint}" if entry.argument_hint else ""
        lines.append(f"- `{prefix}{entry.name}{hint}` - {entry.description}")
    return "\n".join(lines).strip()


def main_help(argv: list[str] | None = None) -> int:
    """Entry point for ``ll-help``."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-help", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-help",
            description="List every /ll: command and skill, grouped by area.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "-C",
            "--directory",
            type=Path,
            default=None,
            help="Plugin root override (default: resolved via CLAUDE_PLUGIN_ROOT or repo root)",
        )
        parser.add_argument("--json", action="store_true", default=False, help="Emit JSON")
        parser.add_argument(
            "--format",
            choices=["md", "json"],
            default=None,
            help="Output format (overrides --json when given)",
        )
        parser.add_argument("--area", default=None, help="Filter to a single area")
        args = parser.parse_args(argv)

        if args.directory is not None:
            plugin_root = args.directory
        else:
            from little_loops.skill_expander import _find_plugin_root

            plugin_root = _find_plugin_root()

        commands_dir = plugin_root / "commands"
        skills_dir = plugin_root / "skills"
        if not commands_dir.is_dir() and not skills_dir.is_dir():
            print(
                f"ll-help: no plugin catalog found at {plugin_root} "
                "(pip-only install has no commands/skills directory; "
                "the catalog is only available in a Claude Code plugin checkout).",
                file=sys.stderr,
            )
            return 1

        fmt = args.format or ("json" if args.json else "md")
        entries = collect_entries(plugin_root)
        print(render_catalog(entries, args.area, fmt))
        return 0


if __name__ == "__main__":
    sys.exit(main_help())
