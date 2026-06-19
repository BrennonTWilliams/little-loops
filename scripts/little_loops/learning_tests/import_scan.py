"""Shared utility for scanning Python source files for imported package names (ENH-2214, ENH-2216)."""

from __future__ import annotations

import re
from pathlib import Path

_PY_IMPORT_RE = re.compile(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


def get_imported_packages(source_dirs: list[Path]) -> set[str]:
    """Return unique top-level package names imported across all .py files in source_dirs.

    Args:
        source_dirs: Directories to scan recursively for .py files.

    Returns:
        Set of unique top-level package names (e.g., ``"requests"``, ``"anthropic"``).
    """
    packages: set[str] = set()
    for source_dir in source_dirs:
        if not source_dir.is_dir():
            continue
        for py_file in source_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in _PY_IMPORT_RE.finditer(content):
                packages.add(m.group(1))
    return packages
