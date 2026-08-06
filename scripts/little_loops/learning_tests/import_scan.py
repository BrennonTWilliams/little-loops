"""Shared utility for scanning Python source files for imported package names (ENH-2214, ENH-2216)."""

from __future__ import annotations

import ast
from pathlib import Path

_PREFIX_CAP = 2


def _expand_prefixes(dotted: str) -> set[str]:
    """Return dotted name plus its prefixes, capped at ``_PREFIX_CAP`` segments."""
    segments = dotted.split(".")
    return {".".join(segments[:n]) for n in range(1, min(len(segments), _PREFIX_CAP) + 1)}


def get_imported_packages(source_dirs: list[Path]) -> set[str]:
    """Return package names (and dotted prefixes, capped at 2 segments) imported
    across all .py files in source_dirs.

    Parses each file with ``ast`` rather than regex, so imports are found at any
    nesting depth and dotted module names are captured in full. Relative imports
    (``from .foo import x``) are skipped — they name first-party siblings, not
    packages. Files that fail to parse are skipped.

    Args:
        source_dirs: Directories to scan recursively for .py files.

    Returns:
        Set of unique, lowercased package names (e.g., ``"requests"``,
        ``"concurrent.futures"``).
    """
    packages: set[str] = set()
    for source_dir in source_dirs:
        if not source_dir.is_dir():
            continue
        for py_file in source_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        packages.update(_expand_prefixes(alias.name.lower()))
                elif isinstance(node, ast.ImportFrom):
                    if node.level > 0 or node.module is None:
                        continue
                    packages.update(_expand_prefixes(node.module.lower()))
    return packages


def normalize_target(target: str) -> str:
    """Normalize a learning-test record's ``target`` for comparison against
    ``get_imported_packages()``'s output.

    Both sides of an "is this imported?" check must share one convention, so
    this is the single normalization helper used by every consumer.
    """
    return target.split()[0].lower()
