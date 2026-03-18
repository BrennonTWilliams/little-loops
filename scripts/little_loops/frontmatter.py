"""Frontmatter parsing utilities for little-loops.

Provides shared YAML-subset frontmatter parsing and stripping used by
issue_parser, sync, and issue_history modules.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]:
    """Extract YAML frontmatter from content.

    Looks for content between opening and closing '---' markers.
    Parses a subset of YAML: simple ``key: value`` pairs only. Lists,
    block scalars, and nested structures are not supported and will emit
    a ``logging.WARNING``. Returns empty dict if no frontmatter found.

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
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            logger.warning("Unsupported YAML list syntax in frontmatter: %r", line)
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith("|") or value.startswith(">"):
                logger.warning("Unsupported YAML block scalar in frontmatter: %r", line)
                result[key] = None
                continue
            if value.lower() in ("null", "~", ""):
                result[key] = None
            elif coerce_types and value.isdigit():
                result[key] = int(value)
            else:
                result[key] = value
    return result


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
