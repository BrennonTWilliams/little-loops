"""File hint extraction for overlap detection in parallel processing.

Extracts file paths, directories, and scopes from issue content to predict
potential file modifications before dispatch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import DependencyMappingConfig

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

# Overlap detection thresholds
MIN_OVERLAP_FILES = 2  # Minimum overlapping files to trigger overlap
OVERLAP_RATIO_THRESHOLD = 0.25  # Minimum ratio of overlapping files to smaller set
MIN_DIRECTORY_DEPTH = 2  # Minimum path segments for directory overlap (e.g., src/components/ = 2)

# Common infrastructure files excluded from overlap detection.
# These appear incidentally in many issues but are rarely the actual conflict.
COMMON_FILES_EXCLUDE = frozenset(
    {
        "__init__.py",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "CHANGELOG.md",
        "README.md",
        "conftest.py",
    }
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

    def overlaps_with(
        self,
        other: FileHints,
        *,
        config: DependencyMappingConfig | None = None,
    ) -> bool:
        """Check if this hint set overlaps with another.

        Uses graduated thresholds rather than binary matching:
        - Common infrastructure files are excluded from file checks
        - File overlap requires minimum count or ratio threshold
        - Directory overlap requires minimum path depth
        - Scope matches are kept as-is (intentional semantic signals)

        Args:
            other: FileHints to compare against
            config: Optional dependency mapping config for custom thresholds.
                Falls back to module-level constants when not provided.
        """
        # Empty hints don't overlap
        if self.is_empty or other.is_empty:
            return False

        # Resolve thresholds from config or module constants
        min_files = config.overlap_min_files if config else MIN_OVERLAP_FILES
        ratio_threshold = config.overlap_min_ratio if config else OVERLAP_RATIO_THRESHOLD
        min_depth = config.min_directory_depth if config else MIN_DIRECTORY_DEPTH
        exclude_files = (
            frozenset(config.exclude_common_files) if config else COMMON_FILES_EXCLUDE
        )

        # Filter common infrastructure files
        self_files = {f for f in self.files if not _is_common_file(f, exclude_files)}
        other_files = {f for f in other.files if not _is_common_file(f, exclude_files)}

        # Exact file matches with thresholds
        shared_files = self_files & other_files
        if shared_files:
            smaller_set = min(len(self_files), len(other_files))
            if smaller_set > 0:
                ratio = len(shared_files) / smaller_set
                if len(shared_files) >= min_files or ratio >= ratio_threshold:
                    return True

        # Directory overlaps (depth check in _directories_overlap)
        for d1 in self.directories:
            for d2 in other.directories:
                if _directories_overlap(d1, d2, min_depth=min_depth):
                    return True

        # File in directory (depth check in _file_in_directory)
        for f in self_files:
            for d in other.directories:
                if _file_in_directory(f, d, min_depth=min_depth):
                    return True
        for f in other_files:
            for d in self.directories:
                if _file_in_directory(f, d, min_depth=min_depth):
                    return True

        # Scope matches
        if self.scopes & other.scopes:
            return True

        return False

    def get_overlapping_paths(
        self,
        other: FileHints,
        *,
        config: DependencyMappingConfig | None = None,
    ) -> set[str]:
        """Get specific paths that overlap between two hint sets.

        Unlike overlaps_with() which returns bool, this returns the
        actual file/directory paths causing the overlap. Applies the
        same filtering and thresholds as overlaps_with().

        Args:
            other: FileHints to compare against
            config: Optional dependency mapping config for custom thresholds.
                Falls back to module-level constants when not provided.
        """
        if self.is_empty or other.is_empty:
            return set()

        overlapping: set[str] = set()

        # Resolve thresholds from config or module constants
        min_files = config.overlap_min_files if config else MIN_OVERLAP_FILES
        ratio_threshold = config.overlap_min_ratio if config else OVERLAP_RATIO_THRESHOLD
        min_depth = config.min_directory_depth if config else MIN_DIRECTORY_DEPTH
        exclude_files = (
            frozenset(config.exclude_common_files) if config else COMMON_FILES_EXCLUDE
        )

        # Filter common infrastructure files
        self_files = {f for f in self.files if not _is_common_file(f, exclude_files)}
        other_files = {f for f in other.files if not _is_common_file(f, exclude_files)}

        # Exact file matches (only if they meet thresholds)
        shared_files = self_files & other_files
        if shared_files:
            smaller_set = min(len(self_files), len(other_files))
            if smaller_set > 0:
                ratio = len(shared_files) / smaller_set
                if len(shared_files) >= min_files or ratio >= ratio_threshold:
                    overlapping.update(shared_files)

        # Directory overlaps (depth check in _directories_overlap)
        for d1 in self.directories:
            for d2 in other.directories:
                if _directories_overlap(d1, d2, min_depth=min_depth):
                    overlapping.add(d1 if len(d1) <= len(d2) else d2)

        # File in directory (depth check in _file_in_directory)
        for f in self_files:
            for d in other.directories:
                if _file_in_directory(f, d, min_depth=min_depth):
                    overlapping.add(f)
        for f in other_files:
            for d in self.directories:
                if _file_in_directory(f, d, min_depth=min_depth):
                    overlapping.add(f)

        return overlapping


def _is_common_file(
    path: str,
    exclude_files: frozenset[str] = COMMON_FILES_EXCLUDE,
) -> bool:
    """Check if a file is a common infrastructure file to exclude from overlap."""
    basename = path.rsplit("/", 1)[-1] if "/" in path else path
    return basename in exclude_files


def _directories_overlap(
    dir1: str,
    dir2: str,
    *,
    min_depth: int = MIN_DIRECTORY_DEPTH,
) -> bool:
    """Check if two directory paths overlap (one contains the other).

    Requires the shorter (parent) directory to have at least ``min_depth``
    path segments to avoid treating broad directories like ``scripts/`` as
    a conflict signal.
    """
    d1 = dir1.rstrip("/") + "/"
    d2 = dir2.rstrip("/") + "/"
    if not (d1.startswith(d2) or d2.startswith(d1)):
        return False
    # Require minimum depth on the shorter (parent) path
    shorter = d1 if len(d1) <= len(d2) else d2
    depth = len(shorter.rstrip("/").split("/"))
    return depth >= min_depth


def _file_in_directory(
    file_path: str,
    dir_path: str,
    *,
    min_depth: int = MIN_DIRECTORY_DEPTH,
) -> bool:
    """Check if a file is within a directory.

    Requires the directory to have at least ``min_depth`` path segments
    to avoid treating broad directories as a conflict signal.
    """
    dir_normalized = dir_path.rstrip("/") + "/"
    if not file_path.startswith(dir_normalized):
        return False
    depth = len(dir_normalized.rstrip("/").split("/"))
    return depth >= min_depth


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
