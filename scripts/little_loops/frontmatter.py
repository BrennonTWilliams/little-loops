"""Frontmatter parsing utilities for little-loops.

Provides shared YAML-subset frontmatter parsing used by issue_parser,
sync, and issue_history modules.
"""

from __future__ import annotations

import re
from typing import Any


def parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]:
    """Extract YAML frontmatter from content.

    Looks for content between opening and closing '---' markers.
    Parses simple key: value pairs. Returns empty dict if no
    frontmatter found.

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
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.lower() in ("null", "~", ""):
                result[key] = None
            elif coerce_types and value.isdigit():
                result[key] = int(value)
            else:
                result[key] = value
    return result
