"""Catalog-assembly for little-loops' own Anthropic Messages API tool set.

Walks ``skills/*/SKILL.md``, ``commands/*.md``, and ``agents/*.md``
frontmatter and produces a full Anthropic ``tools`` array
(``{"name", "description", "input_schema"}`` per entry, optional
``cache_control``). This is the single, stable data source FEAT-2672
(deferred-loading stub/resolve) and FEAT-2673 (``build_anthropic_request()``)
consume instead of each reimplementing frontmatter enumeration.

``input_schema`` bodies are hand-authored per entry *kind*, not derived
mechanically from frontmatter: skills/commands carry only free-text
``args``/``argument-hint`` display hints with no type information, and
agents carry no args-equivalent field at all. See ``_make_input_schema``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from little_loops.frontmatter import parse_skill_frontmatter

__all__ = ["ToolDefinition", "assemble_tool_catalog", "to_anthropic_tools"]


@dataclass(frozen=True)
class ToolDefinition:
    """One entry in little-loops' Anthropic tool-definition catalog.

    Frozen for the same reason as ``host_runner.CapabilityEntry``: instances
    cross the assembly/serialization boundary and shouldn't be mutated
    in-flight. ``cache_control`` is left unset by ``assemble_tool_catalog``;
    downstream callers may attach it before serializing.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    cache_control: dict[str, str] | None = None


def _read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def _clean(value: object) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _make_input_schema(args_hint: str | None) -> dict[str, Any]:
    """Build a generic ``input_schema`` for a skill/command entry.

    ``args_hint`` is the free-text ``args``/``argument-hint`` frontmatter
    value (e.g. ``"ISSUE_ID [--auto]"``) with no type/required/enum
    information — there's no mechanical path from it to a typed schema, so
    it's surfaced as a single opaque ``args`` string property.
    """
    if args_hint:
        return {
            "type": "object",
            "properties": {"args": {"type": "string", "description": args_hint}},
            "required": [],
        }
    return {"type": "object", "properties": {}, "required": []}


def _agent_input_schema() -> dict[str, Any]:
    """Fixed ``input_schema`` for agent entries.

    Agent frontmatter has no args-equivalent field to derive from, so this
    mirrors the real Agent-tool invocation contract instead: a short task
    summary plus the task prompt.
    """
    return {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Short (3-5 word) description of the task",
            },
            "prompt": {
                "type": "string",
                "description": "The task for the agent to perform",
            },
        },
        "required": ["description", "prompt"],
    }


def _skill_entries(skills_dir: Path) -> list[ToolDefinition]:
    entries = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        content = _read_text_or_empty(skill_md)
        fm = parse_skill_frontmatter(content) if content else {}
        description = _clean(fm.get("description"))
        args_hint = _clean(fm.get("args") or fm.get("argument-hint")) or None
        entries.append(
            ToolDefinition(
                name=skill_md.parent.name,
                description=description,
                input_schema=_make_input_schema(args_hint),
            )
        )
    return entries


def _command_entries(commands_dir: Path) -> list[ToolDefinition]:
    entries = []
    for cmd_md in sorted(commands_dir.glob("*.md")):
        content = _read_text_or_empty(cmd_md)
        fm = parse_skill_frontmatter(content) if content else {}
        description = _clean(fm.get("description"))
        args_hint = _clean(fm.get("args") or fm.get("argument-hint")) or None
        entries.append(
            ToolDefinition(
                name=cmd_md.stem,
                description=description,
                input_schema=_make_input_schema(args_hint),
            )
        )
    return entries


def _agent_entries(agents_dir: Path) -> list[ToolDefinition]:
    entries = []
    for agent_md in sorted(agents_dir.glob("*.md")):
        content = _read_text_or_empty(agent_md)
        fm = parse_skill_frontmatter(content) if content else {}
        description = _clean(fm.get("description"))
        entries.append(
            ToolDefinition(
                name=agent_md.stem,
                description=description,
                input_schema=_agent_input_schema(),
            )
        )
    return entries


def assemble_tool_catalog(project_root: Path) -> list[ToolDefinition]:
    """Walk skills/commands/agents under *project_root* into a tool catalog.

    Missing directories contribute no entries and never raise, matching the
    ``_load_skills()``/``_load_skill_catalog()`` precedent.
    """
    entries: list[ToolDefinition] = []
    entries.extend(_skill_entries(project_root / "skills"))
    entries.extend(_command_entries(project_root / "commands"))
    entries.extend(_agent_entries(project_root / "agents"))
    return entries


def to_anthropic_tools(entries: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Serialize catalog entries into the Anthropic Messages API ``tools`` shape.

    ``cache_control`` is omitted entirely when unset — the Anthropic API
    rejects a literal ``null`` cache_control value, so ``None`` must not
    become a JSON key at all.
    """
    tools: list[dict[str, Any]] = []
    for entry in entries:
        tool: dict[str, Any] = {
            "name": entry.name,
            "description": entry.description,
            "input_schema": entry.input_schema,
        }
        if entry.cache_control is not None:
            tool["cache_control"] = entry.cache_control
        tools.append(tool)
    return tools
