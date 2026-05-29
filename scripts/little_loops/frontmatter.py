"""Frontmatter read/write utilities for little-loops.

Provides shared YAML-subset frontmatter parsing, stripping, and updating
used by issue_parser, sync, and issue_history modules.
"""

from __future__ import annotations

import logging
import re
import textwrap
from typing import Any

import yaml

logger = logging.getLogger(__name__)

STATUS_SYNONYMS: dict[str, str] = {
    "complete": "done",
    "completed": "done",
    "finished": "done",
    "closed": "done",
    "in-progress": "in_progress",
    "in progress": "in_progress",
    "wip": "in_progress",
}


def parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]:
    """Extract YAML frontmatter from content.

    Looks for content between opening and closing '---' markers.
    Parses a subset of YAML: simple ``key: value`` pairs, YAML block
    sequences (``key:`` followed by ``- item`` lines), and block scalars
    (``key: |`` or ``key: >`` followed by indented lines). Nested
    structures are not supported and will emit a ``logging.WARNING``.
    Returns empty dict if no frontmatter found.

    Args:
        content: File content to parse
        coerce_types: If True, coerce digit strings to int

    Returns:
        Dictionary of frontmatter fields, or empty dict
    """
    if not content or not content.startswith("---"):
        return {}

    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return {}

    frontmatter_text = content[4 : 3 + end_match.start()]

    result: dict[str, Any] = {}
    current_list_key: str | None = None
    lines = frontmatter_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            if current_list_key is not None:
                result[current_list_key].append(line[2:].strip())
            else:
                logger.warning("Unsupported YAML list syntax in frontmatter: %r", line)
            continue
        # Non-list line: finalize any in-progress empty list, then reset
        if current_list_key is not None and result[current_list_key] == []:
            result[current_list_key] = None
        current_list_key = None
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith("|") or value.startswith(">"):
                # Block scalar: collect indented continuation lines
                block_type = value[0]
                block_lines: list[str] = []
                while i < len(lines):
                    next_line = lines[i]
                    if next_line and (next_line[0] == " " or next_line[0] == "\t"):
                        block_lines.append(next_line)
                        i += 1
                    else:
                        break
                if block_lines:
                    dedented = textwrap.dedent("\n".join(block_lines))
                    if block_type == ">":
                        dedented = re.sub(r"\s+", " ", dedented).strip()
                    result[key] = dedented
                else:
                    result[key] = ""
                continue
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                result[key] = [item.strip() for item in inner.split(",")] if inner else []
                continue
            if value.lower() in ("null", "~", ""):
                if value == "":
                    result[key] = []
                    current_list_key = key
                else:
                    result[key] = None
            elif coerce_types and value.isdigit():
                result[key] = int(value)
            else:
                result[key] = value
    # Finalize any trailing empty list key
    if current_list_key is not None and result[current_list_key] == []:
        result[current_list_key] = None
    if "status" in result and isinstance(result["status"], str):
        result["status"] = STATUS_SYNONYMS.get(result["status"], result["status"])
    return result


def parse_skill_frontmatter(text: str) -> dict[str, str]:
    """Extract flat key/value pairs from SKILL.md frontmatter.

    Uses ``yaml.safe_load`` so YAML block scalars (e.g. ``description: |``)
    are resolved to their string content instead of the indicator literal.
    Non-string scalar values are stringified; nested structures are dropped.

    If the frontmatter is not valid YAML (e.g. unquoted colons in values),
    falls back to a permissive line-based scan — top-level ``key: value``
    pairs only, block scalars are not resolved in that path.

    This is the canonical SKILL.md frontmatter parser. Prefer it over the
    general ``parse_frontmatter`` for SKILL.md files: ``parse_frontmatter``
    deliberately drops block scalars (logs a warning, sets value to
    ``None``) which loses the description body for skills that use
    ``description: |``.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    fm_text = text[3:end]
    try:
        loaded = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        loaded = None
    if isinstance(loaded, dict):
        fm: dict[str, str] = {}
        for key, value in loaded.items():
            if value is None:
                fm[str(key)] = ""
            elif isinstance(value, str):
                fm[str(key)] = value
            elif isinstance(value, bool | int | float):
                fm[str(key)] = str(value).lower() if isinstance(value, bool) else str(value)
        return fm
    fm = {}
    for line in fm_text.splitlines():
        if line and not line.startswith(" ") and not line.startswith("\t") and ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from content, returning the body.

    Strips the ``---`` delimited frontmatter block (if present) and
    returns everything after the closing delimiter.

    Args:
        content: File content possibly starting with frontmatter

    Returns:
        Content with frontmatter removed. Returns original content
        unchanged if no valid frontmatter block is found.
    """
    if not content or not content.startswith("---"):
        return content

    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return content

    return content[3 + end_match.end() :]


def update_frontmatter(content: str, updates: dict[str, Any]) -> str:
    """Update or add frontmatter fields in content.

    Merges ``updates`` into an existing ``---`` delimited YAML frontmatter
    block, preserving other fields and their order. If no frontmatter block
    exists, a new one is prepended. Existing keys are overwritten with the
    new values.

    Args:
        content: Full file content, possibly with existing frontmatter
        updates: Fields to add/update in frontmatter; values may be nested dicts

    Returns:
        Content with updated frontmatter block
    """
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        fm_text = yaml.dump(dict(updates), default_flow_style=False, sort_keys=False).strip()
        return f"---\n{fm_text}\n---\n{content}"

    existing: dict[str, Any] = yaml.safe_load(fm_match.group(1)) or {}
    existing.update(updates)
    fm_text = yaml.dump(existing, default_flow_style=False, sort_keys=False).strip()
    return f"---\n{fm_text}\n---{content[fm_match.end() :]}"
