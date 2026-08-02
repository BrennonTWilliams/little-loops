"""ll-issues prioritize: priority-rename mechanics (ENH-2953).

Deterministic discovery of unprioritized/prioritized active issues and a
stdin-JSON-driven bulk rename applier, extracted out of
``commands/prioritize-issues.md`` so only the P0-P5 judgment step stays a
prose skill. See ``.issues/enhancements/P2-ENH-2953-*.md`` for the full
design rationale.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import BRConfig


@dataclass
class PrioritizeEntry:
    """A single active issue from :func:`scan_prioritize`."""

    id: str
    path: Path
    current_priority: str | None  # None only in the unprioritized listing

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-ready dict."""
        return {
            "id": self.id,
            "path": str(self.path),
            "current_priority": self.current_priority,
        }


@dataclass
class RenameResult:
    """The outcome of applying one priority rename in :func:`apply_priorities`."""

    id: str
    old_path: Path
    new_path: Path
    old_priority: str | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-ready dict."""
        return {
            "id": self.id,
            "old_path": str(self.old_path),
            "new_path": str(self.new_path),
            "old_priority": self.old_priority,
        }


def _priority_prefix_re(config: BRConfig) -> re.Pattern[str]:
    """Build the `^P[0-5]-`-equivalent regex from `config.issues.priorities`."""
    alternation = "|".join(re.escape(p) for p in config.issues.priorities)
    return re.compile(rf"^({alternation})-")


def scan_prioritize(
    config: BRConfig, *, include_prioritized: bool = False
) -> list[PrioritizeEntry]:
    """Scan active issues for priority-prefix presence.

    Discovery is scoped to active issues only (`find_issues`'s default
    `status_filter=None` skips `done`/`cancelled`/`deferred`) — terminal
    issues are never candidates for prioritization.

    Args:
        config: Project configuration.
        include_prioritized: When False (default), only unprioritized issues
            are returned. When True (`--all`), every active issue is
            returned with its `current_priority` (`None` if unprioritized).

    Returns:
        Entries sorted by path.
    """
    from little_loops.issue_parser import find_issues

    prefix_re = _priority_prefix_re(config)
    entries: list[PrioritizeEntry] = []
    for info in find_issues(config, status_filter=None):
        match = prefix_re.match(info.path.name)
        current_priority = match.group(1) if match else None
        if current_priority is None or include_prioritized:
            entries.append(
                PrioritizeEntry(id=info.issue_id, path=info.path, current_priority=current_priority)
            )

    entries.sort(key=lambda e: str(e.path))
    return entries


def apply_priorities(config: BRConfig, mapping: dict[str, str]) -> list[RenameResult]:
    """Apply a `{issue_id: priority}` map: prepend or replace the priority prefix.

    An issue already at its target priority is a no-op (reported, not an
    error). Unresolvable issue IDs are skipped silently (not gate-relevant —
    they never appeared in a `scan_prioritize()` result the caller could
    have derived the map from).

    Args:
        config: Project configuration.
        mapping: `{issue_id: target_priority}`.

    Returns:
        One :class:`RenameResult` per entry in *mapping* that resolved to a
        real issue file, including no-op entries.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.issue_lifecycle import git_mv_with_fallback

    prefix_re = _priority_prefix_re(config)
    valid_priorities = set(config.issues.priorities)
    results: list[RenameResult] = []

    for issue_id, priority in mapping.items():
        if priority not in valid_priorities:
            continue
        path = _resolve_issue_id(config, issue_id)
        if path is None:
            continue

        match = prefix_re.match(path.name)
        old_priority = match.group(1) if match else None
        new_name = prefix_re.sub(f"{priority}-", path.name) if match else f"{priority}-{path.name}"
        new_path = path.parent / new_name

        if new_path == path:
            results.append(
                RenameResult(
                    id=issue_id, old_path=path, new_path=new_path, old_priority=old_priority
                )
            )
            continue

        git_mv_with_fallback(path, new_path)
        results.append(
            RenameResult(id=issue_id, old_path=path, new_path=new_path, old_priority=old_priority)
        )

    return results


def _print_findings(findings: list[PrioritizeEntry]) -> None:
    if not findings:
        print("prioritize: no findings")
        return
    for f in findings:
        if f.current_priority is None:
            print(f"[{f.id}] unprioritized: {f.path}")
        else:
            print(f"[{f.id}] {f.current_priority}: {f.path}")


def add_prioritize_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the prioritize subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "prioritize",
        help="Priority-rename mechanics: discover unprioritized/prioritized "
        "issues, apply a priority map from stdin JSON",
    )
    p.set_defaults(command="prioritize")
    p.add_argument(
        "--all",
        action="store_true",
        help="List every active issue with its current_priority, not just "
        "unprioritized ones (the re-prioritize mode's input)",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Deterministic exit-code gate: 0 = every active issue prefixed, "
        "1 = one or more unprioritized. Ignores --all",
    )
    p.add_argument(
        "--apply",
        metavar="FILE",
        default=None,
        help="Path to a {issue_id: priority} JSON map, or '-' for stdin; performs the renames",
    )
    p.add_argument(
        "--json",
        "-j",
        action="store_true",
        help='Output {"findings": [...], "applied": [...]} as JSON',
    )
    add_config_arg(p)
    return p


def cmd_prioritize(config: BRConfig, args: argparse.Namespace) -> int:
    """Report, and optionally apply, priority-prefix findings.

    Returns:
        1 when `--check` is set and an unprioritized active issue exists, 0
        otherwise (including invalid `--apply` JSON, which is reported to
        stderr but does not fail the command's own exit code contract beyond
        that case).
    """
    from little_loops.cli.output import print_json

    include_all = getattr(args, "all", False)
    findings = scan_prioritize(config, include_prioritized=include_all)

    applied: list[RenameResult] = []
    apply_arg = getattr(args, "apply", None)
    if apply_arg is not None:
        raw = sys.stdin.read() if apply_arg == "-" else Path(apply_arg).read_text(encoding="utf-8")
        try:
            mapping = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"Error: invalid JSON for --apply: {exc}", file=sys.stderr)
            return 1
        applied = apply_priorities(config, mapping)

    check_mode: bool = getattr(args, "check", False)
    gate_failed = False
    unprioritized_count = 0
    if check_mode:
        unprioritized = scan_prioritize(config, include_prioritized=False)
        unprioritized_count = len(unprioritized)
        gate_failed = unprioritized_count > 0

    if getattr(args, "json", False):
        print_json(
            {
                "findings": [f.to_dict() for f in findings],
                "applied": [r.to_dict() for r in applied],
            }
        )
    else:
        _print_findings(findings)
        if applied:
            print(f"Applied {len(applied)} rename(s).")
        if check_mode:
            print(
                f"{unprioritized_count} unprioritized issue(s) found"
                if gate_failed
                else "All active issues prioritized"
            )

    if check_mode:
        return 1 if gate_failed else 0
    return 0
