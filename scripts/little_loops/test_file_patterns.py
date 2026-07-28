"""Shared test-file identification.

Classifies a repo-relative path as "a test file" against
``project.test_patterns`` (per-project-type defaults in
``scripts/little_loops/templates/*.json``). Pure and deterministic: no git
calls, no filesystem stat, no LLM. Consumers (ENH-2853, ENH-2854) wire this
in independently.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.config.core import BRConfig
from little_loops.git_operations import file_matches_pattern


def _default_config() -> BRConfig:
    return BRConfig(Path("."))


def is_test_file(path: str, config: BRConfig | None = None) -> bool:
    """Return True if *path* matches any of ``project.test_patterns``.

    Args:
        path: Repo-relative path, POSIX-normalized (e.g. as emitted by
            ``git diff --name-only``).
        config: Optional BRConfig to read patterns from; loads the current
            project's config when omitted.

    Returns:
        True if path matches any configured test-file pattern.
    """
    if config is None:
        config = _default_config()
    normalized = path.replace("\\", "/")
    patterns = config.project.test_patterns
    return any(file_matches_pattern(normalized, pattern) for pattern in patterns)


def filter_test_files(paths: list[str], config: BRConfig | None = None) -> list[str]:
    """Return the subset of *paths* that are test files.

    Args:
        paths: Repo-relative paths, POSIX-normalized.
        config: Optional BRConfig to read patterns from; loads the current
            project's config when omitted.

    Returns:
        Paths matching any configured test-file pattern, preserving order.
    """
    if config is None:
        config = _default_config()
    return [path for path in paths if is_test_file(path, config=config)]
