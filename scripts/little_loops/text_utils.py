"""Text extraction utilities for issue content.

Provides shared functions for extracting file paths from markdown issue
content. Used by dependency_mapper, issue_history, and other modules that
need to identify file references in issue text.
"""

from __future__ import annotations

import re
from pathlib import Path

# File path patterns for extraction from issue content
_BACKTICK_PATH = re.compile(r"`([^`\s]+\.[a-z]{2,4})`")
_BOLD_FILE_PATH = re.compile(r"\*\*File\*\*:\s*`?([^`\n]+\.[a-z]{2,4})`?")
_STANDALONE_PATH = re.compile(
    r"(?:^|\s)([a-zA-Z_][\w/.-]*\.[a-z]{2,4})(?::\d+)?(?:\s|$|:|\))",
    re.MULTILINE,
)
_CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# File extensions that indicate real source file paths
SOURCE_EXTENSIONS = frozenset(
    {
        ".py",
        ".ts",
        ".js",
        ".tsx",
        ".jsx",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".cfg",
        ".ini",
        ".html",
        ".css",
        ".scss",
        ".sh",
        ".bash",
        ".sql",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".rb",
        ".php",
    }
)


def extract_file_paths(content: str) -> set[str]:
    """Extract file paths from issue content.

    Searches for file paths in:
    - Backtick-quoted paths: `path/to/file.py`
    - Location section bold paths: **File**: `path/to/file.py`
    - Standalone paths with recognized extensions

    Code fence blocks are stripped before extraction to avoid
    matching paths inside example code. Line number suffixes
    (e.g., ``path.py:123``) are normalized by stripping the
    line number portion.

    Args:
        content: Issue file content

    Returns:
        Set of file paths found in the content
    """
    if not content:
        return set()

    # Strip code fences to avoid matching example paths
    stripped = _CODE_FENCE.sub("", content)

    paths: set[str] = set()
    for pattern in (_BOLD_FILE_PATH, _BACKTICK_PATH, _STANDALONE_PATH):
        for match in pattern.finditer(stripped):
            path = match.group(1).strip()
            # Normalize: remove line numbers (path.py:123 -> path.py)
            if ":" in path and path.split(":")[-1].isdigit():
                path = ":".join(path.split(":")[:-1])
            # Only include paths with directory separators or recognized extensions
            ext = Path(path).suffix.lower()
            if ext in SOURCE_EXTENSIONS and ("/" in path or ext):
                paths.add(path)
    return paths
