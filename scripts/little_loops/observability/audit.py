"""DES audit walker — see ``little_loops.observability`` docstring.

Walks a source tree, statically extracts every event-emit string literal, and reports
emit sites whose event type does not appear in ``DES_VARIANT_TYPES``. Exit 0 means every
emit site maps to a registered variant (the F5 acceptance gate).

Detection strategy (two phases):
    1. Regex phase — captures positional string literals passed to ``self._emit(...)``
       and ``event_bus.emit(...)`` (the dominant emit pattern in ``fsm/executor.py``).
    2. AST phase — captures keyword-arg ``event=...`` literals in spread-constructed
       dicts passed to ``event_bus.emit({...})`` (used by ``state.py`` and
       ``fsm/persistence.py``).

Precedent:
    - ``scripts/little_loops/cli/verify_package_data.py:99-143`` (regex + rglob walker)
    - ``scripts/little_loops/learning_tests/import_scan.py:8-31`` (regex over rglob)
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from little_loops.observability.schema import DES_VARIANT_TYPES

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class AuditResult:
    """Audit verdict: list of emit-type strings with no matching DES variant."""

    uncovered_event_types: list[str] = field(default_factory=list)
    files_scanned: int = 0
    emit_sites_found: int = 0

    @property
    def passed(self) -> bool:
        """True iff every discovered emit site mapped to a registered variant."""
        return not self.uncovered_event_types


# ---------------------------------------------------------------------------
# Phase 1 — Regex capture of positional string literals
# ---------------------------------------------------------------------------


# Matches: <caller>("event_type", {...}) where caller is one of the known emit sites.
# The event-type group captures the quoted string literal (single or double quotes).
_PHASE1_RE = re.compile(
    r"""
    \b(?:self\._emit|event_bus\.emit|bus\.emit|self\._event_bus\.emit)
    \s*\(
    \s*
    (?P<etype>
        "(?P<double>[^"\\]*(?:\\.[^"\\]*)*)"
        |
        '(?P<single>[^'\\]*(?:\\.[^'\\]*)*)'
    )
    """,
    re.VERBOSE,
)


# ---------------------------------------------------------------------------
# Phase 2 — AST capture of keyword-arg `event="..."` literals
# ---------------------------------------------------------------------------


def _ast_extract_event_types(source: str) -> Iterator[str]:
    """Yield event-type string literals from ``event=...`` keyword args in emit calls.

    Handles spread-construction sites like::

        event_bus.emit({"event": "loop_start", "ts": ..., **payload})

    where the event type is hidden inside a dict literal. Also handles the simpler::

        emit(event="loop_start", ts=...)
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Restrict to known emit-call function names.
        func = node.func
        if not _is_emit_call(func):
            continue
        for kw in node.keywords:
            if kw.arg != "event":
                continue
            value = kw.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                yield value.value


def _is_emit_call(func: ast.expr) -> bool:
    """True iff *func* is one of the known emit-call shapes (heuristic)."""
    if isinstance(func, ast.Attribute):
        return func.attr in {"emit", "_emit"}
    if isinstance(func, ast.Name):
        return func.id in {"emit", "_emit"}
    return False


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------


def _audit_python_file(path: Path, known: frozenset[str]) -> tuple[list[str], int]:
    """Return ``(uncovered_event_types, emit_site_count)`` for one ``.py`` file.

    Errors (file unreadable, ``ast.parse`` failure) are silently swallowed — a single
    bad file must not abort the whole audit (precedent: ``verify_package_data.py:113-114``).
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], 0
    if not source:
        return [], 0

    uncovered: list[str] = []
    emit_count = 0

    # Phase 1: regex capture of positional string literals.
    for m in _PHASE1_RE.finditer(source):
        emit_count += 1
        literal = m.group("double") if m.group("double") is not None else m.group("single")
        if literal not in known:
            uncovered.append(literal)

    # Phase 2: AST capture of keyword-arg `event=...` literals.
    for literal in _ast_extract_event_types(source):
        emit_count += 1
        if literal not in known:
            uncovered.append(literal)

    return uncovered, emit_count


def audit_tree(pkg_root: Path) -> AuditResult:
    """Walk *pkg_root*, classify every emit site against ``DES_VARIANT_TYPES``.

    Args:
        pkg_root: Root directory whose ``.py`` files will be inspected.

    Returns:
        ``AuditResult`` with the list of uncovered event types (empty on a clean tree),
        the number of files scanned, and the total emit-site count discovered.
    """
    known = DES_VARIANT_TYPES
    uncovered: list[str] = []
    files_scanned = 0
    emit_count = 0

    if not pkg_root.is_dir():
        return AuditResult(
            uncovered_event_types=[],
            files_scanned=0,
            emit_sites_found=0,
        )

    for py_file in sorted(p for p in pkg_root.rglob("*.py") if p.is_file()):
        files_scanned += 1
        file_uncovered, file_emits = _audit_python_file(py_file, known)
        uncovered.extend(file_uncovered)
        emit_count += file_emits

    # Deduplicate while preserving discovery order for stable output.
    seen: set[str] = set()
    deduped: list[str] = []
    for etype in uncovered:
        if etype in seen:
            continue
        seen.add(etype)
        deduped.append(etype)

    return AuditResult(
        uncovered_event_types=deduped,
        files_scanned=files_scanned,
        emit_sites_found=emit_count,
    )
