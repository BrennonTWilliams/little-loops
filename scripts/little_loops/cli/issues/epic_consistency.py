"""ll-issues epic-consistency: detect and reconcile EPIC body/parent drift (FEAT-2332)."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

_ALL_STATUSES: set[str] = {"open", "in_progress", "blocked", "done", "cancelled", "deferred"}

# Matches the frontmatter type: field value (captures the value after "type: ")
_FM_TYPE_RE = re.compile(r"^type:\s*(\S+)", re.MULTILINE)
# Matches a frontmatter children: key (list start)
_FM_CHILDREN_RE = re.compile(r"^children\s*:", re.MULTILINE)

# Issue types that participate in the (a)/(b) parent-child diff.
# EPIC-* refs in body are treated as sub-epic prose (advisory only).
# Everything else (MR-*, CT-*, EG-*, …) is skipped.
_REAL_ISSUE_TYPES = frozenset({"BUG", "FEAT", "ENH"})

# Matches bullet list items with an optional bold wrapper around the ID:
#   - FEAT-001 …            →  group(1) = "FEAT-001"
#   - **FEAT-001** — …      →  group(1) = "FEAT-001"
_BODY_BULLET_RE = re.compile(r"^\s*[-*]\s+\*{0,2}([A-Z]+-\d+)", re.MULTILINE)


@dataclass
class EpicDrift:
    """Drift report for a single EPIC."""

    epic_id: str
    epic_title: str
    missing_from_body: list[str] = field(default_factory=list)    # (a)
    body_without_parent: list[str] = field(default_factory=list)  # (b)
    relates_to_is_child: list[str] = field(default_factory=list)  # (c)
    sub_epic_advisory: list[str] = field(default_factory=list)    # advisory
    type_casing_wrong: bool = False   # schema: type: must be 'EPIC'
    has_children_frontmatter: bool = False  # schema: children: key forbidden

    @property
    def has_drift(self) -> bool:
        """True when any actionable drift exists (a/b/c categories or schema violations)."""
        return bool(
            self.missing_from_body
            or self.body_without_parent
            or self.relates_to_is_child
            or self.type_casing_wrong
            or self.has_children_frontmatter
        )

    def to_dict(self) -> dict:
        """Serialize to a JSON-serializable dict for --format json output."""
        return {
            "epic": self.epic_id,
            "missing_from_body": sorted(self.missing_from_body),
            "body_without_parent": sorted(self.body_without_parent),
            "relates_to_is_child": sorted(self.relates_to_is_child),
            "sub_epic_advisory": sorted(self.sub_epic_advisory),
            "type_casing_wrong": self.type_casing_wrong,
            "has_children_frontmatter": self.has_children_frontmatter,
        }


def _section_bounds(content: str, heading: str) -> tuple[int, int] | None:
    """Return (body_start, body_end) byte offsets for a ## heading section.

    Returns None when the heading is absent.
    """
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return None
    start = match.end()
    next_match = re.search(r"^##\s", content[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(content)
    return start, end


def _parse_children_body(section_text: str) -> tuple[set[str], set[str]]:
    """Parse a ## Children section body.

    Returns:
        (real_issue_ids, sub_epic_ids) where real_issue_ids contains only
        BUG/FEAT/ENH tokens and sub_epic_ids contains EPIC-* tokens.
        Non-issue tokens (MR-*, CT-*, EG-*, …) are silently dropped.
    """
    real_ids: set[str] = set()
    sub_epic_ids: set[str] = set()
    for m in _BODY_BULLET_RE.finditer(section_text):
        token = m.group(1)
        issue_type = token.split("-")[0]
        if issue_type in _REAL_ISSUE_TYPES:
            real_ids.add(token)
        elif issue_type == "EPIC":
            sub_epic_ids.add(token)
        # else: skip non-issue tokens (MR-*, CT-*, EG-*, …)
    return real_ids, sub_epic_ids


def compute_drift(
    epic_id: str,
    all_issues: list[IssueInfo],
) -> EpicDrift | None:
    """Compute drift for a single EPIC against all loaded issues.

    Returns None when the EPIC ID is not found in all_issues.
    """
    epic_id = epic_id.upper()

    epic_matches = [i for i in all_issues if i.issue_id == epic_id]
    if not epic_matches:
        return None
    epic_info = epic_matches[0]

    # Authoritative child set: issues carrying parent: epic_id (real types only)
    parent_children: set[str] = {
        i.issue_id
        for i in all_issues
        if i.parent == epic_id and i.issue_id.split("-")[0] in _REAL_ISSUE_TYPES
    }

    # Advisory: EPICs that carry parent: epic_id (should use relates_to + prose)
    sub_epic_advisory: list[str] = sorted(
        i.issue_id
        for i in all_issues
        if i.parent == epic_id and i.issue_id.startswith("EPIC-")
    )

    # Parse file content for body and frontmatter checks
    try:
        content = epic_info.path.read_text(encoding="utf-8")
    except OSError:
        content = ""

    # Extract frontmatter block (between first pair of --- delimiters)
    fm_block = ""
    if content.startswith("---"):
        end_marker = content.find("\n---", 3)
        if end_marker != -1:
            fm_block = content[3:end_marker]

    # Schema check (d): type: must be 'EPIC' when present; absent is OK
    type_casing_wrong = False
    type_match = _FM_TYPE_RE.search(fm_block)
    if type_match and type_match.group(1) != "EPIC":
        type_casing_wrong = True

    # Schema check (e): children: frontmatter key is forbidden
    has_children_frontmatter = bool(_FM_CHILDREN_RE.search(fm_block))

    bounds = _section_bounds(content, "Children")
    if bounds is not None:
        section_body = content[bounds[0] : bounds[1]]
        body_real_ids, _ = _parse_children_body(section_body)
    else:
        body_real_ids = set()

    # (a) parent: child missing from body
    missing_from_body = sorted(parent_children - body_real_ids)

    # (b) body-listed real issue with no parent: backref
    body_without_parent = sorted(body_real_ids - parent_children)

    # (c) relates_to: entries that are also parent: children
    relates_to_set = set(epic_info.relates_to or [])
    relates_to_is_child = sorted(relates_to_set & parent_children)

    return EpicDrift(
        epic_id=epic_id,
        epic_title=epic_info.title,
        missing_from_body=missing_from_body,
        body_without_parent=body_without_parent,
        relates_to_is_child=relates_to_is_child,
        sub_epic_advisory=sub_epic_advisory,
        type_casing_wrong=type_casing_wrong,
        has_children_frontmatter=has_children_frontmatter,
    )


def fix_epic(epic_path: Path, missing_from_body: list[str]) -> None:
    """Add missing parent: children to an EPIC's ## Children section.

    Existing lines (sub-epic prose, non-issue tokens, category-(b) entries)
    are preserved.  Only category-(a) drift is fixed.  Running twice on an
    already-fixed file is a no-op (idempotent).
    """
    if not missing_from_body:
        return

    content = epic_path.read_text(encoding="utf-8")
    new_bullets = "\n".join(
        f"- **{child_id}** — (added by epic-consistency --fix)"
        for child_id in sorted(missing_from_body)
    )

    bounds = _section_bounds(content, "Children")
    if bounds is None:
        # No ## Children section — create one at the end of the file
        new_section = "\n## Children\n\n" + new_bullets + "\n"
        new_content = content.rstrip("\n") + "\n" + new_section
    else:
        start, end = bounds
        section_body = content[start:end]
        # Append after existing content (preserving all existing lines)
        stripped = section_body.rstrip("\n")
        sep = "\n" if stripped.strip() else ""
        new_section_body = stripped + sep + "\n" + new_bullets + "\n"
        new_content = content[:start] + new_section_body + content[end:]

    from little_loops.file_utils import atomic_write

    atomic_write(epic_path, new_content)


def add_epic_consistency_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the epic-consistency subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "epic-consistency",
        aliases=["ec"],
        help="Detect and reconcile EPIC body/parent drift",
    )
    p.set_defaults(command="epic-consistency")
    p.add_argument(
        "epic_id",
        nargs="?",
        default=None,
        help="EPIC ID (e.g., EPIC-1773); omit when using --all",
    )
    p.add_argument("--all", "-a", action="store_true", help="Check all EPICs in epics dir")
    p.add_argument(
        "--fix",
        action="store_true",
        help="Rewrite ## Children for category-(a) drift (report-only by default)",
    )
    p.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    add_config_arg(p)
    return p


def cmd_epic_consistency(config: BRConfig, args: argparse.Namespace) -> int:
    """Detect and reconcile EPIC body/parent drift.

    Returns:
        0 when no drift found (or --fix ran cleanly), 1 on drift/error.
    """
    from little_loops.cli.output import print_json
    from little_loops.issue_parser import find_issues

    epic_id: str | None = getattr(args, "epic_id", None)
    check_all: bool = getattr(args, "all", False)
    fix: bool = getattr(args, "fix", False)
    fmt: str = getattr(args, "format", "text") or "text"

    if not epic_id and not check_all:
        print("Error: provide an EPIC-ID or --all")
        return 1

    if epic_id and not epic_id.upper().startswith("EPIC-"):
        print(f"Error: expected an EPIC ID (e.g., EPIC-1773), got {epic_id!r}")
        return 1

    all_issues = find_issues(config, status_filter=_ALL_STATUSES)

    if check_all:
        epic_ids = sorted(
            i.issue_id for i in all_issues if i.issue_id.startswith("EPIC-")
        )
    else:
        epic_ids = [epic_id.upper()]  # type: ignore[union-attr]

    results: list[EpicDrift] = []
    for eid in epic_ids:
        drift = compute_drift(eid, all_issues)
        if drift is None:
            print(f"Error: EPIC {eid!r} not found")
            return 1
        results.append(drift)

    if fix:
        for drift in results:
            if drift.missing_from_body:
                epic_issues = [i for i in all_issues if i.issue_id == drift.epic_id]
                if epic_issues:
                    fix_epic(epic_issues[0].path, drift.missing_from_body)
        # Re-check after fix so output reflects the updated state
        results = []
        for eid in epic_ids:
            drift = compute_drift(eid, all_issues)
            if drift is not None:
                results.append(drift)

    any_drift = any(d.has_drift for d in results)

    if fmt == "json":
        if len(results) == 1:
            print_json(results[0].to_dict())
        else:
            print_json({"results": [d.to_dict() for d in results]})
        return 0 if fix else (1 if any_drift else 0)

    # text format
    for drift in results:
        if not drift.has_drift and not drift.sub_epic_advisory:
            print(f"{drift.epic_id}: {drift.epic_title} — OK")
            continue
        print(f"{drift.epic_id}: {drift.epic_title}")
        if drift.type_casing_wrong:
            print("  (d) Schema: type: casing must be 'EPIC' (not lowercase 'epic')")
        if drift.has_children_frontmatter:
            print("  (e) Schema: frontmatter children: array is forbidden; use parent: backrefs")
        if drift.missing_from_body:
            print("  (a) Missing from body (parent: child not documented):")
            for child_id in drift.missing_from_body:
                print(f"      {child_id}")
        if drift.body_without_parent:
            print("  (b) Body-listed, no parent: backref (human decision needed):")
            for child_id in drift.body_without_parent:
                print(f"      {child_id}")
        if drift.relates_to_is_child:
            print("  (c) relates_to: leaking membership:")
            for child_id in drift.relates_to_is_child:
                print(f"      {child_id}")
        if drift.sub_epic_advisory:
            print("  [advisory] Sub-epic via parent: (should use relates_to + prose):")
            for child_id in drift.sub_epic_advisory:
                print(f"      {child_id}")

    return 0 if fix else (1 if any_drift else 0)
