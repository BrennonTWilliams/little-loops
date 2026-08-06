"""ll-issues normalize: filename/ID mechanics (ENH-2944).

Deterministic detection and fixing of missing/duplicate/malformed issue IDs,
legacy status directories, and (report-only) type misclassifications. See
``.issues/enhancements/P2-ENH-2944-*.md`` for the full design rationale —
notably why duplicate detection groups on the filename regex rather than
``IssueInfo.issue_id`` (that parser fallback fabricates IDs for ID-less
files, which would otherwise manufacture phantom duplicates).
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

AUTO_FIXABLE_KINDS: frozenset[str] = frozenset({"missing_id", "malformed_filename", "duplicate_id"})

# Frontmatter relationship keys scanned/rewritten when an ID is reassigned.
_REFERENCING_KEYS: tuple[str, ...] = (
    "blocked_by",
    "depends_on",
    "parent",
    "epic",
    "relates_to",
    "supersedes",
)

# Keyword-signal table ported from commands/normalize-issues.md:166-171.
_TYPE_SIGNALS: dict[str, tuple[str, ...]] = {
    "BUG": (
        "broken",
        "regression",
        "error",
        "crash",
        "fails",
        "wrong behavior",
        "should not",
        "defect",
        "incorrect",
        "unexpected",
    ),
    "FEAT": (
        "new capability",
        "users can't currently",
        "add support for",
        "implement",
        "missing feature",
        "not yet possible",
    ),
    "ENH": (
        "improve",
        "optimize",
        "enhance",
        "refactor",
        "better ux",
        "reduce",
        "increase performance",
        "simplify",
    ),
    "EPIC": (
        "decompose into",
        "umbrella",
        "rollup of",
        "multi-issue initiative",
        "coordination container",
        "should be an epic",
        "milestone",
    ),
}

_TYPE_MISMATCH_CONFIDENCE_CUTOFF = 0.7

# Statuses excluded from type_mismatch reporting (ENH-3053): reclassifying
# closed historical work has no actionable follow-up. Scan-local set — NOT
# the shared issue_progress._TERMINAL_STATUSES ({"done", "cancelled"}), which
# deliberately treats "deferred" as non-terminal for dependency-graph
# resolution (BUG-2897) and must not widen to match this check's needs.
_TYPE_MISMATCH_EXCLUDED_STATUSES: frozenset[str] = frozenset({"done", "cancelled", "deferred"})

_KEYWORD_RES: dict[str, list[re.Pattern[str]]] = {
    t: [re.compile(re.escape(kw)) for kw in kws] for t, kws in _TYPE_SIGNALS.items()
}


@dataclass
class NormalizeFinding:
    """A single filename/ID-mechanics finding from :func:`scan_normalize`."""

    path: Path
    kind: str  # missing_id | duplicate_id | malformed_filename | legacy_dir | type_mismatch
    proposed_path: Path | None = None
    proposed_id: str | None = None
    inbound_refs: list[str] = field(default_factory=list)
    confidence: float | None = None
    priority_defaulted: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-ready dict."""
        return {
            "path": str(self.path),
            "kind": self.kind,
            "proposed_path": str(self.proposed_path) if self.proposed_path is not None else None,
            "proposed_id": self.proposed_id,
            "inbound_refs": list(self.inbound_refs),
            "confidence": round(self.confidence, 3) if self.confidence is not None else None,
            "priority_defaulted": self.priority_defaulted,
        }


def _priority_and_defaulted(filename: str) -> tuple[str, bool]:
    """Extract a leading ``P[0-5]-`` token, defaulting to P3 when absent."""
    m = re.match(r"^(P[0-5])-", filename)
    return (m.group(1), False) if m else ("P3", True)


def _slug_for(filename: str) -> str:
    """Derive a slug from a filename, stripping priority/type/ID tokens."""
    from little_loops.issue_parser import slugify

    stem = filename[:-3] if filename.endswith(".md") else filename
    stem = re.sub(r"^P[0-5]-", "", stem)
    stem = re.sub(r"^(BUG|FEAT|ENH|EPIC)-\d+-?", "", stem)
    return slugify(stem) or "issue"


def _git_log_date(path: Path) -> str | None:
    """Return the ISO date of a file's oldest git log entry, or None."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%as", "--follow", "--", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    lines = [line for line in result.stdout.strip().splitlines() if line]
    return lines[-1] if lines else None


def _find_legacy_dirs(config: BRConfig) -> list[Path]:
    """Find non-empty legacy `completed/`/`deferred/` dirs, base-level or nested.

    Independent of :func:`~little_loops.issue_parser.find_issues`, which only
    globs configured category directories and would never see these.
    """
    base = config.project_root / config.issues.base_dir
    found: list[Path] = []
    for name in ("completed", "deferred"):
        top = base / name
        if top.exists() and any(top.glob("*.md")):
            found.append(top)
    for cat in config.issue_categories:
        cat_dir = config.get_issue_dir(cat)
        for name in ("completed", "deferred"):
            nested = cat_dir / name
            if nested.exists() and any(nested.glob("*.md")):
                found.append(nested)
    return found


# Sections scanned for classification signals — mirrors
# commands/normalize-issues.md:164's "Summary, Motivation/Current Behavior,
# and Root Cause sections" scope. Whole-file scanning was tried and produces
# a near-100% false-positive rate (engineering words like "implement" and
# "epic" — the latter from EPIC-NNNN cross-references — are common in every
# issue's prose regardless of its actual type).
_CLASSIFY_SECTIONS: tuple[str, ...] = (
    "Summary",
    "Motivation",
    "Current Behavior",
    "Root Cause",
)


def classify_type(issue: IssueInfo) -> tuple[str, float]:
    """Keyword-signal type classification: ``(signals_for_top_type)/(total+1)``.

    Scans only the Summary/Motivation/Current Behavior/Root Cause sections
    (per the ported heuristic's scope), not the whole file body.

    Returns ``("", 0.0)`` when the file is unreadable or no signal keyword
    matches at all, which never clears the mismatch confidence cutoff.
    """
    from little_loops.issue_parser import _section_body

    try:
        content = issue.path.read_text(encoding="utf-8")
    except OSError:
        return "", 0.0

    body = "\n".join(
        section
        for name in _CLASSIFY_SECTIONS
        if (section := _section_body(content, name)) is not None
    ).lower()
    if not body:
        return "", 0.0

    counts = {
        t: sum(len(pat.findall(body)) for pat in patterns) for t, patterns in _KEYWORD_RES.items()
    }
    total = sum(counts.values())
    top_type = max(counts, key=lambda t: counts[t])
    if counts[top_type] == 0:
        return "", 0.0
    return top_type, counts[top_type] / (total + 1)


def scan_normalize(
    config: BRConfig, only_ids: set[str] | list[str] | None = None
) -> list[NormalizeFinding]:
    """Scan the issue corpus for filename/ID-mechanics findings.

    The scan itself is always corpus-wide (duplicate-ID detection and
    ``get_next_issue_number()`` allocation are inherently global); *only_ids*
    filters the *returned* findings to those issues only.

    Args:
        config: Project configuration.
        only_ids: Optional issue IDs to scope reported findings to.

    Returns:
        All findings, sorted by path then kind.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.issue_parser import _FILENAME_ID_RE, find_issues, is_normalized
    from little_loops.issue_progress import _ALL_STATUSES

    findings: list[NormalizeFinding] = []

    path_category: dict[Path, str] = {}
    for cat in config.issue_categories:
        issue_dir = config.get_issue_dir(cat)
        if not issue_dir.exists():
            continue
        for f in sorted(issue_dir.glob("*.md")):
            path_category[f] = cat

    all_issues = find_issues(config, status_filter=set(_ALL_STATUSES))

    # Reverse index: referenced ID -> list of referencing issue IDs.
    refs_index: dict[str, list[str]] = {}
    for info in all_issues:
        for key in _REFERENCING_KEYS:
            value = getattr(info, key, None)
            if isinstance(value, list):
                for v in value:
                    v_str = str(v).strip()
                    if v_str:
                        refs_index.setdefault(v_str, []).append(info.issue_id)
            elif isinstance(value, str) and value.strip():
                refs_index.setdefault(value.strip(), []).append(info.issue_id)

    by_number: dict[int, list[tuple[Path, str, str]]] = {}
    no_id_paths: list[Path] = []
    for path in path_category:
        m = _FILENAME_ID_RE.search(path.name)
        if m is None:
            no_id_paths.append(path)
        else:
            prefix, numstr = m.group(1), m.group(2)
            by_number.setdefault(int(numstr), []).append((path, prefix, numstr))

    next_num_box: list[int] = []

    def _alloc(config: BRConfig = config) -> int:
        from little_loops.issue_parser import get_next_issue_number

        if not next_num_box:
            next_num_box.append(get_next_issue_number(config))
        n = next_num_box[0]
        next_num_box[0] = n + 1
        return n

    # --- missing_id ---
    for path in sorted(no_id_paths):
        cat = path_category[path]
        prefix = config.get_issue_prefix(cat)
        priority, defaulted = _priority_and_defaulted(path.name)
        new_num = _alloc()
        proposed_id = f"{prefix}-{new_num:03d}"
        proposed_path = path.parent / f"{priority}-{prefix}-{new_num:03d}-{_slug_for(path.name)}.md"
        findings.append(
            NormalizeFinding(
                path=path,
                kind="missing_id",
                proposed_path=proposed_path,
                proposed_id=proposed_id,
                priority_defaulted=defaulted,
            )
        )

    # --- duplicate_id / malformed_filename ---
    for num in sorted(by_number):
        entries = by_number[num]
        if len(entries) > 1:

            def _keeper_sort_key(entry: tuple[Path, str, str]) -> tuple[str, str]:
                path = entry[0]
                date = _git_log_date(path)
                return (date or "9999-99-99", path.name)

            ordered = sorted(entries, key=_keeper_sort_key)
            for path, prefix, numstr in ordered[1:]:
                current_id = f"{prefix}-{numstr}"
                priority, defaulted = _priority_and_defaulted(path.name)
                new_num = _alloc()
                proposed_id = f"{prefix}-{new_num:03d}"
                proposed_path = (
                    path.parent / f"{priority}-{prefix}-{new_num:03d}-{_slug_for(path.name)}.md"
                )
                findings.append(
                    NormalizeFinding(
                        path=path,
                        kind="duplicate_id",
                        proposed_path=proposed_path,
                        proposed_id=proposed_id,
                        inbound_refs=refs_index.get(current_id, []),
                        priority_defaulted=defaulted,
                    )
                )
        else:
            path, prefix, numstr = entries[0]
            if is_normalized(path.name):
                continue
            current_id = f"{prefix}-{numstr}"
            priority, defaulted = _priority_and_defaulted(path.name)
            proposed_id = f"{prefix}-{int(numstr):03d}"
            proposed_path = (
                path.parent / f"{priority}-{prefix}-{int(numstr):03d}-{_slug_for(path.name)}.md"
            )
            inbound = refs_index.get(current_id, []) if proposed_id != current_id else []
            findings.append(
                NormalizeFinding(
                    path=path,
                    kind="malformed_filename",
                    proposed_path=proposed_path,
                    proposed_id=proposed_id,
                    inbound_refs=inbound,
                    priority_defaulted=defaulted,
                )
            )

    # --- legacy_dir ---
    for d in _find_legacy_dirs(config):
        findings.append(NormalizeFinding(path=d, kind="legacy_dir"))

    # --- type_mismatch (report-only) ---
    for info in all_issues:
        mismatch_cat = path_category.get(info.path)
        if mismatch_cat is None:
            continue
        if info.status in _TYPE_MISMATCH_EXCLUDED_STATUSES:
            continue
        current_prefix = config.get_issue_prefix(mismatch_cat)
        inferred_prefix, confidence = classify_type(info)
        if inferred_prefix and inferred_prefix != current_prefix:
            if confidence >= _TYPE_MISMATCH_CONFIDENCE_CUTOFF:
                m = _FILENAME_ID_RE.search(info.path.name)
                mismatch_proposed_id = f"{inferred_prefix}-{m.group(2)}" if m else None
                findings.append(
                    NormalizeFinding(
                        path=info.path,
                        kind="type_mismatch",
                        proposed_id=mismatch_proposed_id,
                        confidence=confidence,
                    )
                )

    if only_ids:
        only_paths: set[Path] = set()
        for oid in only_ids:
            p = _resolve_issue_id(config, str(oid))
            if p is not None:
                only_paths.add(p.resolve())
        findings = [f for f in findings if f.path.resolve() in only_paths]

    findings.sort(key=lambda f: (str(f.path), f.kind))
    return findings


def rewrite_inbound_refs(config: BRConfig, old_id: str, new_id: str) -> list[Path]:
    """Repoint every frontmatter relationship edge from *old_id* to *new_id*.

    Scoped to :data:`_REFERENCING_KEYS` across issue frontmatter only; prose
    mentions and non-issue files (thoughts/, sprints, .ll/history.db) are out
    of scope (Design Decision 6).

    Returns:
        Paths of issue files whose frontmatter was rewritten.
    """
    from little_loops.file_utils import atomic_write
    from little_loops.frontmatter import parse_frontmatter, update_frontmatter
    from little_loops.issue_parser import find_issues
    from little_loops.issue_progress import _ALL_STATUSES

    changed: list[Path] = []
    for info in find_issues(config, status_filter=set(_ALL_STATUSES)):
        try:
            content = info.path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = parse_frontmatter(content)
        updates: dict[str, Any] = {}
        for key in _REFERENCING_KEYS:
            if key not in fm:
                continue
            value = fm[key]
            if isinstance(value, list):
                if old_id in value:
                    updates[key] = [new_id if v == old_id else v for v in value]
            elif isinstance(value, str) and value.strip() == old_id:
                updates[key] = new_id
        if updates:
            new_content = update_frontmatter(content, updates)
            atomic_write(info.path, new_content, encoding="utf-8")
            changed.append(info.path)
    return changed


def apply_normalize(config: BRConfig, findings: list[NormalizeFinding]) -> list[NormalizeFinding]:
    """Apply every auto-fixable finding: rename, sync frontmatter `id:`, rewrite edges.

    Never applies a finding outside :data:`AUTO_FIXABLE_KINDS`, never
    overwrites an existing path.

    Returns:
        The subset of *findings* actually applied.
    """
    from little_loops.frontmatter import update_frontmatter
    from little_loops.issue_lifecycle import git_mv_with_fallback
    from little_loops.issue_parser import _FILENAME_ID_RE

    applied: list[NormalizeFinding] = []
    for finding in findings:
        if finding.kind not in AUTO_FIXABLE_KINDS:
            continue
        if finding.proposed_path is None or not finding.path.exists():
            continue
        if finding.proposed_path.exists():
            continue

        original = finding.path
        target = finding.proposed_path
        content = original.read_text(encoding="utf-8")
        if finding.proposed_id is not None:
            content = update_frontmatter(content, {"id": finding.proposed_id})

        m = _FILENAME_ID_RE.search(original.name)
        old_id = f"{m.group(1)}-{m.group(2)}" if m else None

        git_mv_with_fallback(original, target, content=content)
        applied.append(finding)

        if (
            old_id
            and finding.proposed_id
            and old_id != finding.proposed_id
            and finding.inbound_refs
        ):
            rewrite_inbound_refs(config, old_id, finding.proposed_id)

    return applied


def _print_findings(findings: list[NormalizeFinding]) -> None:
    if not findings:
        print("normalize: no findings")
        return
    for f in findings:
        loc = str(f.path)
        if f.kind == "missing_id":
            print(f"[{loc}] normalize: missing valid ID -> {f.proposed_path}")
        elif f.kind == "malformed_filename":
            note = " (priority defaulted to P3)" if f.priority_defaulted else ""
            print(f"[{loc}] normalize: malformed filename -> {f.proposed_path}{note}")
        elif f.kind == "duplicate_id":
            print(
                f"[{loc}] normalize: duplicate ID -> reassign to "
                f"{f.proposed_id} ({f.proposed_path})"
            )
        elif f.kind == "legacy_dir":
            print(f"[{loc}] normalize: legacy status directory — run `ll-migrate`")
        elif f.kind == "type_mismatch":
            confidence = f.confidence if f.confidence is not None else 0.0
            print(
                f"[{loc}] normalize: type mismatch -> {f.proposed_id} (confidence {confidence:.2f})"
            )


def add_normalize_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the normalize subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "normalize",
        help="Detect/fix filename & ID mechanics "
        "(missing_id/malformed_filename/duplicate_id/legacy_dir/type_mismatch)",
    )
    p.set_defaults(command="normalize")
    p.add_argument(
        "issue_id",
        nargs="*",
        help="Scope reported/applied findings to these issue IDs; the scan "
        "(duplicate detection, ID allocation) always stays corpus-wide",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Deterministic exit-code gate: 0 clean / 1 violations. Covers only "
        "the auto-fixable classes unless --strict is also set",
    )
    p.add_argument(
        "--auto",
        action="store_true",
        help="Apply auto-fixable findings (git mv + frontmatter id: + inbound-edge rewrite)",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Widen --check's exit code to also cover legacy_dir/type_mismatch findings",
    )
    p.add_argument(
        "--json",
        "-j",
        action="store_true",
        help='Output {"findings": [...], "applied": [...]} as JSON',
    )
    add_config_arg(p)
    return p


def cmd_normalize(config: BRConfig, args: argparse.Namespace) -> int:
    """Report, and optionally apply, filename/ID-mechanics findings.

    Returns:
        1 when ``--check`` is set and a gate-relevant finding exists, 0 otherwise.
    """
    from little_loops.cli.output import print_json

    only_ids = list(getattr(args, "issue_id", None) or []) or None
    findings = scan_normalize(config, only_ids=only_ids)

    applied: list[NormalizeFinding] = []
    if getattr(args, "auto", False):
        applied = apply_normalize(config, findings)

    check_mode: bool = getattr(args, "check", False)
    strict: bool = getattr(args, "strict", False)
    relevant_kinds = set(AUTO_FIXABLE_KINDS)
    if strict:
        relevant_kinds |= {"legacy_dir", "type_mismatch"}
    gate_failed = any(f.kind in relevant_kinds for f in findings)

    if getattr(args, "json", False):
        print_json(
            {"findings": [f.to_dict() for f in findings], "applied": [f.to_dict() for f in applied]}
        )
    else:
        _print_findings(findings)
        if applied:
            print(f"Applied {len(applied)} fix(es).")
            reassigned = [
                f
                for f in applied
                if f.kind in ("duplicate_id", "malformed_filename") and f.proposed_id
            ]
            if reassigned:
                names = ", ".join(sorted(f.path.name for f in reassigned))
                print(
                    f"Note: out-of-scope references were NOT rewritten for reassigned ID(s) "
                    f"in {names} — .ll/history.db rows, .ll/decisions.d/ fragments, sprint "
                    "definitions, and prose mentions must be updated manually if needed."
                )
        if check_mode:
            print(
                f"{sum(1 for f in findings if f.kind in relevant_kinds)} normalization issues found"
                if gate_failed
                else "All issues normalized"
            )

    if check_mode:
        return 1 if gate_failed else 0
    return 0
