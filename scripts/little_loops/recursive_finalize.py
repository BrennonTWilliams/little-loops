"""Decomposed-parent lifecycle + EPIC re-linking for the rn-implement loops.

When ``rn-decompose`` splits a parent issue into children, the parent issue must
be closed (work is now carried by the children) and, if the parent belonged to an
EPIC, its children must be re-linked into that EPIC so they do not silently fall
out of the EPIC's ``relates_to:``/``## Children`` rollup (ENH-1977, GAP F).

This module is the tested core behind ``ll-issues finalize-decomposition``. It is
deliberately filesystem-only (no git, no Logger, no BRConfig) so it can be unit
tested against a temporary ``.issues`` tree.

Field-collision decision (ENH-1977 Fix 4): ``parent:`` is canonically used for
*both* decomposition lineage and EPIC membership. A child cannot carry two
``parent:`` values, so children become first-class EPIC members
(``parent: EPIC-NNN``) and decomposition lineage is recorded via
``relates_to: [<parent-id>]`` plus the ``Decomposed from <parent-id>`` body marker
that ``issue-size-review`` already emits.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.frontmatter import parse_frontmatter, update_frontmatter

_EPIC_RE = re.compile(r"^EPIC-\d+$", re.IGNORECASE)


def _completed_at_now() -> str:
    """Return current UTC time as ISO 8601 with a ``Z`` suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_issue_file(
    issue_id: str, issues_dir: Path, *, include_completed: bool = True
) -> Path | None:
    """Locate the markdown file for ``issue_id`` under ``issues_dir``.

    Matches files whose name contains ``-<issue_id>-`` (case-insensitive), mirroring
    the ``*-$ID-*`` glob used by the loops. Active category directories are searched
    first; the completed directory is only searched when ``include_completed`` is set.
    """
    needle = f"-{issue_id.upper()}-"
    candidates: list[Path] = []
    for path in sorted(issues_dir.rglob("*.md")):
        if not include_completed and "completed" in path.parts:
            continue
        if needle in f"-{path.name.upper()}":
            # Prefer active files over completed ones when both exist.
            candidates.append(path)
    if not candidates:
        return None
    active = [p for p in candidates if "completed" not in p.parts]
    return active[0] if active else candidates[0]


def _dedup(seq: list[str]) -> list[str]:
    """Order-preserving de-duplication (case-insensitive keys, original casing kept)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        key = item.upper()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _git_mv(src: Path, dst: Path) -> None:
    """Move ``src`` to ``dst`` using ``git mv`` when possible, else a plain move."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["git", "mv", str(src), str(dst)],
            capture_output=True,
            text=True,
            cwd=src.parent,
        )
        if result.returncode == 0:
            return
    except (OSError, subprocess.SubprocessError):
        pass
    shutil.move(str(src), str(dst))


def _append_decomposition_note(content: str, parent_id: str, child_ids: list[str]) -> str:
    """Append a ``## Resolution`` decomposition note if not already present.

    Idempotent: a second call is a no-op once the marker line exists.
    """
    if "Decomposed into" in content:
        return content
    children_str = ", ".join(child_ids) if child_ids else "(no children recorded)"
    note = (
        "\n\n---\n\n## Resolution\n\n"
        f"- **Status**: Decomposed\n"
        f"- **Closed**: {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        f"- **Decomposed into**: {children_str}\n\n"
        f"Work for {parent_id} is now carried by its child issues; this parent was "
        f"closed by rn-decompose.\n"
    )
    return content.rstrip() + note


def finalize_decomposed_parent(
    parent_id: str,
    child_ids: list[str],
    issues_dir: Path,
    *,
    move_to_completed: bool = False,
) -> dict[str, Any]:
    """Close a decomposed parent and re-link its children into the parent's EPIC.

    Idempotent across all steps so a retried loop iteration does not corrupt state.

    Steps:
      1. **Close the parent.** Set ``status: done`` + ``completed_at``, append a
         "Decomposed into <child-ids>" body note, and close it in place at its
         existing type-based path (ENH-1418 convention). Only when
         ``move_to_completed`` is explicitly set does it move the file into the
         legacy ``<issues_dir>/completed/`` directory instead.
      2. **Re-link children to the parent's EPIC, if any.** When the parent carries
         ``parent: EPIC-NNN``: repoint each child to ``parent: EPIC-NNN``, record
         lineage via ``relates_to: [<parent-id>]``, append the children to the
         EPIC's ``relates_to:``, and drop the decomposed parent from it.
      3. **No-EPIC guard.** When the parent has no EPIC parent, only step 1 runs and
         children keep their existing ``parent:`` linkage.

    Args:
        parent_id: Bare issue ID of the decomposed parent (e.g. ``ENH-123``).
        child_ids: Child issue IDs created from the parent.
        issues_dir: Root of the issues tree (e.g. ``Path(".issues")``).
        move_to_completed: Move the closed parent into legacy ``completed/`` when
            true (default false — closes in place per ENH-1418).

    Returns:
        Summary dict: ``{"parent", "epic", "children", "moved", "warnings"}``.
    """
    parent_id = parent_id.strip().upper()
    child_ids = [c.strip() for c in child_ids if c.strip()]
    warnings: list[str] = []

    parent_path = _find_issue_file(parent_id, issues_dir)
    if parent_path is None:
        return {
            "parent": parent_id,
            "epic": None,
            "children": child_ids,
            "moved": False,
            "warnings": [f"parent file not found for {parent_id}"],
        }

    content = parent_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
    raw_epic = fm.get("parent")
    epic_id: str | None = None
    if isinstance(raw_epic, str) and _EPIC_RE.match(raw_epic.strip()):
        epic_id = raw_epic.strip().upper()

    # --- Step 1: close the parent -------------------------------------------------
    content = _append_decomposition_note(content, parent_id, child_ids)
    content = update_frontmatter(content, {"status": "done", "completed_at": _completed_at_now()})
    parent_path.write_text(content, encoding="utf-8")

    moved = False
    if move_to_completed and "completed" not in parent_path.parts:
        completed_dir = issues_dir / "completed"
        dst = completed_dir / parent_path.name
        if not dst.exists():
            _git_mv(parent_path, dst)
            moved = True

    # --- Steps 2/3: EPIC re-linking (guarded) -------------------------------------
    if epic_id is not None:
        for child_id in child_ids:
            child_path = _find_issue_file(child_id, issues_dir)
            if child_path is None:
                warnings.append(f"child file not found for {child_id}")
                continue
            child_content = child_path.read_text(encoding="utf-8")
            child_fm = parse_frontmatter(child_content)
            existing_relates = list(child_fm.get("relates_to") or [])
            new_relates = _dedup([*existing_relates, parent_id])
            child_content = update_frontmatter(
                child_content, {"parent": epic_id, "relates_to": new_relates}
            )
            child_path.write_text(child_content, encoding="utf-8")

        epic_path = _find_issue_file(epic_id, issues_dir)
        if epic_path is None:
            warnings.append(f"epic file not found for {epic_id}")
        else:
            epic_content = epic_path.read_text(encoding="utf-8")
            epic_fm = parse_frontmatter(epic_content)
            existing = [str(x) for x in (epic_fm.get("relates_to") or [])]
            # Add children, drop the now-decomposed parent.
            merged = _dedup([*existing, *child_ids])
            merged = [x for x in merged if x.upper() != parent_id]
            epic_content = update_frontmatter(epic_content, {"relates_to": merged})
            epic_path.write_text(epic_content, encoding="utf-8")

    return {
        "parent": parent_id,
        "epic": epic_id,
        "children": child_ids,
        "moved": moved,
        "warnings": warnings,
    }
