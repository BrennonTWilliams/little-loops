"""Repo-relative directory value canonicalization (BUG-3631).

Stdlib-only, no ``little_loops`` imports — a dependency-free leaf module so
both ``config/core.py`` and ``config/features.py`` (which ``core.py``
imports) can call it without a circular import.
"""

from __future__ import annotations


def canonical_dir(value: str) -> str:
    """Canonical spelling of a repo-relative dir value; root spellings -> '.'."""
    if not value:
        return value  # "" = unset; callers decide
    while value.startswith("./") and value != "./":
        value = value[2:]  # "./src/" -> "src/"
    if value.rstrip("/") in ("", "."):
        return "."  # ".", "./", ".//", "/"
    return value


def dir_prefix(value: str) -> str:
    """Path prefix for ``startswith()`` matching; ``""`` means whole repo."""
    if not value:
        raise ValueError("dir_prefix() requires a non-empty dir; test for unset first")
    value = canonical_dir(value)
    return "" if value == "." else value.rstrip("/") + "/"
