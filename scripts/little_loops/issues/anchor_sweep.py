"""Backlog sweeper: rewrite file:line references in active issue files — ENH-1300.

Two-phase sweep:
  1. Scan: find file:line patterns outside code fences, resolve each to an anchor.
  2. Apply: rewrite matches in-place using atomic_write().

Respects --dry-run: always records what would change, gates actual writes.
"""

from __future__ import annotations

import re
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from little_loops.file_utils import atomic_write
from little_loops.issues.anchors import resolve_anchor
from little_loops.text_utils import _CODE_FENCE

# Captures file path (group 1) and line number (group 2) together.
# Unlike _STANDALONE_PATH, the :NNN suffix is required and captured separately.
_FILE_LINE = re.compile(
    r"(?:(?<=\s)|^)([a-zA-Z_][\w/.-]*\.[a-z]{2,4}):(\d+)(?=\s|$|:|\))",
    re.MULTILINE,
)

_ACTIVE_CATEGORIES = ("bugs", "features", "enhancements", "epics")


@dataclass
class SweepResult:
    """Result of a sweep pass."""

    changes: list[str] = field(default_factory=list)
    modified_files: set[str] = field(default_factory=set)
    skipped_refs: int = 0


def _format_anchor_ref(file_path: str, anchor: str) -> str:
    """Format a resolved anchor reference.

    Examples:
        "near function foo"   -> "`file.py` (near function `foo`)"
        "near class Bar"      -> "`file.py` (near class `Bar`)"
        'under section "X"'   -> '`file.py` (under section "X")'
    """
    # Backtick the name in "near function foo" → near function `foo`
    # but leave section titles as-is (already quoted with double-quotes).
    parts = anchor.split(" ", 2)  # e.g. ["near", "function", "foo"]
    if len(parts) == 3 and parts[0] in ("near",):
        anchor_display = f"{parts[0]} {parts[1]} `{parts[2]}`"
    else:
        anchor_display = anchor
    return f"`{file_path}` ({anchor_display})"


def _sweep_file(path: Path, dry_run: bool, result: SweepResult) -> None:
    """Scan one issue file and rewrite file:line references."""
    content = path.read_text(encoding="utf-8", errors="replace")

    fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(content)]

    def _in_fence(start: int, end: int) -> bool:
        return any(fs <= start and end <= fe for fs, fe in fence_spans)

    replacements: list[tuple[int, int, str]] = []
    for m in _FILE_LINE.finditer(content):
        if _in_fence(m.start(), m.end()):
            continue
        ref_path = m.group(1)
        line_no = int(m.group(2))
        anchor = resolve_anchor(ref_path, line_no)
        if anchor is None:
            result.skipped_refs += 1
            warnings.warn(
                f"{path}: could not resolve anchor for {ref_path}:{line_no}",
                stacklevel=2,
            )
            continue
        replacement = _format_anchor_ref(ref_path, anchor)
        replacements.append((m.start(), m.end(), replacement))

    if not replacements:
        return

    desc = f"{path}: rewrote {len(replacements)} file:line reference(s)"
    result.changes.append(desc)

    if not dry_run:
        # Apply replacements in reverse order so positions stay valid
        new_content = content
        for start, end, replacement in reversed(replacements):
            new_content = new_content[:start] + replacement + new_content[end:]
        atomic_write(path, new_content)
        result.modified_files.add(str(path))


def sweep_issues(issues_dir: Path, dry_run: bool = False) -> SweepResult:
    """Sweep all active issue files in issues_dir, rewriting file:line refs.

    Args:
        issues_dir: Base directory containing bugs/, features/, enhancements/ subdirs.
        dry_run: If True, report changes without modifying files.

    Returns:
        SweepResult with changes, modified_files, and skipped_refs counts.
    """
    result = SweepResult()
    for category in _ACTIVE_CATEGORIES:
        cat_dir = issues_dir / category
        if not cat_dir.is_dir():
            continue
        for issue_file in sorted(cat_dir.glob("*.md")):
            try:
                _sweep_file(issue_file, dry_run, result)
            except OSError as exc:
                print(f"Warning: skipping {issue_file}: {exc}", file=sys.stderr)
    return result
