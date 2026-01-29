"""File hint extraction for overlap detection in parallel processing.

Extracts file paths, directories, and scopes from issue content to predict
potential file modifications before dispatch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# File path patterns - adapted from workflow_sequence_analyzer.py
# Match paths with common source code extensions
# NOTE: Order matters! Longer extensions must come before shorter ones (tsx before ts, jsx before js)
FILE_PATH_PATTERN = re.compile(
    r"(?:^|[\s`\"'(\[])([a-zA-Z0-9_./\-]+\.(?:tsx|jsx|json|yaml|yml|toml|scss|html|cpp|hpp|py|ts|js|md|sh|css|go|rs|java|c|h))",
    re.MULTILINE,
)

# Directory path patterns (paths ending with / followed by whitespace/delimiter)
# This ensures we only capture explicit directory references, not prefixes of file paths
DIR_PATH_PATTERN = re.compile(
    r"(?:^|[\s`\"'(\[])([a-zA-Z0-9_./\-]+/)(?=[\s`\"')\],$]|$)",
    re.MULTILINE,
)

# Component/scope patterns from issue content
# Matches: "scope: sidebar", "Component: auth", "module: api"
SCOPE_PATTERN = re.compile(
    r"(?:scope|component|module|directory|folder)[:\s]+[`\"']?([a-zA-Z0-9_./\-]+)[`\"']?",
    re.IGNORECASE,
)


@dataclass
class FileHints:
    """Extracted file hints from issue content.

    Attributes:
        files: Specific file paths mentioned
        directories: Directory paths mentioned
        scopes: Component/scope identifiers
        issue_id: Source issue ID
    """

    files: set[str] = field(default_factory=set)
    directories: set[str] = field(default_factory=set)
    scopes: set[str] = field(default_factory=set)
    issue_id: str = ""

    @property
    def all_paths(self) -> set[str]:
        """All paths (files and directories) combined."""
        return self.files | self.directories

    @property
    def is_empty(self) -> bool:
        """Check if no hints were extracted."""
        return not self.files and not self.directories and not self.scopes

    def overlaps_with(self, other: FileHints) -> bool:
        """Check if this hint set overlaps with another.

        Returns True if:
        - Any files match exactly
        - Any directories overlap (one contains the other)
        - Any scopes match
        """
        # Empty hints don't overlap
        if self.is_empty or other.is_empty:
            return False

        # Exact file matches
        if self.files & other.files:
            return True

        # Directory overlaps
        for d1 in self.directories:
            for d2 in other.directories:
                if _directories_overlap(d1, d2):
                    return True

        # File in directory
        for f in self.files:
            for d in other.directories:
                if _file_in_directory(f, d):
                    return True
        for f in other.files:
            for d in self.directories:
                if _file_in_directory(f, d):
                    return True

        # Scope matches
        if self.scopes & other.scopes:
            return True

        return False


def _directories_overlap(dir1: str, dir2: str) -> bool:
    """Check if two directory paths overlap (one contains the other)."""
    d1 = dir1.rstrip("/") + "/"
    d2 = dir2.rstrip("/") + "/"
    return d1.startswith(d2) or d2.startswith(d1)


def _file_in_directory(file_path: str, dir_path: str) -> bool:
    """Check if a file is within a directory."""
    dir_normalized = dir_path.rstrip("/") + "/"
    return file_path.startswith(dir_normalized)


def extract_file_hints(content: str, issue_id: str = "") -> FileHints:
    """Extract file hints from issue content.

    Args:
        content: Issue markdown content
        issue_id: Optional issue ID for tracking

    Returns:
        FileHints with extracted paths and scopes
    """
    hints = FileHints(issue_id=issue_id)

    # Extract file paths
    for match in FILE_PATH_PATTERN.findall(content):
        # Filter out obvious non-paths
        if not _is_valid_path(match):
            continue
        hints.files.add(match)

    # Extract directory paths
    for match in DIR_PATH_PATTERN.findall(content):
        if not _is_valid_path(match):
            continue
        hints.directories.add(match)

    # Extract scopes
    for match in SCOPE_PATTERN.findall(content):
        hints.scopes.add(match.lower())

    return hints


def _is_valid_path(path: str) -> bool:
    """Filter out false positive paths."""
    # Skip URLs
    if path.startswith("http") or path.startswith("//"):
        return False
    # Skip very short paths (likely not real file paths)
    if len(path) < 3:
        return False
    # Skip paths that are just file extensions
    if path.startswith(".") and "/" not in path:
        return False
    # Skip common false positives
    false_positives = {"e.g.", "i.e.", "etc.", "vs.", "v1.", "v2."}
    if path.lower() in false_positives:
        return False
    return True
