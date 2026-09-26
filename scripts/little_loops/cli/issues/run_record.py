"""ll-issues run-record: write the typed per-issue preparation run record (ENH-3597).

``run-record write`` is the writer ``refine-to-ready-issue``'s terminal-bearing
states call (and, per ENH-3601, the ``prepare-issue`` wrapper will call): it
gathers the issue's terminal-time state — frontmatter status/scores, the shared
``refine-broke-down`` counter, derived children — resolves the outcome via
``little_loops.run_record.outcome_from_legacy_class``, and writes
``<run_dir>/run-records/<writer>/<ID>.json`` atomically.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig

from little_loops.run_record import LEGACY_CLASSES, WRITERS, RunRecord, write_run_record

_BROKE_DOWN_FILENAME = "refine-broke-down"

# Numeric core of an issue ID ("P3-ENH-3597" / "ENH-3597" / "3597" -> "3597").
# The numeric ID is the true unique identifier (TYPE prefix is advisory), so
# parent/child matching anchors on it.
_ID_CORE_RE = re.compile(r"(\d+)")


def add_run_record_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the run-record subparser (with its ``write`` sub-subcommand) on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "run-record",
        help="Write/read/clear the typed per-issue preparation run record (ENH-3597)",
    )
    p.set_defaults(command="run-record")
    subsubs = p.add_subparsers(dest="run_record_command", required=True)

    w = subsubs.add_parser(
        "write",
        help="Write <run_dir>/run-records/<writer>/<ID>.json for one issue",
    )
    w.add_argument("issue_id", help="Issue ID (e.g., 3597, ENH-3597, P3-ENH-3597)")
    w.add_argument(
        "--run-dir",
        required=True,
        help="The run's run_dir (the loop's ${context.run_dir})",
    )
    w.add_argument("--writer", required=True, choices=WRITERS, help="Which loop is writing")
    w.add_argument(
        "--legacy-class",
        default=None,
        choices=LEGACY_CLASSES,
        help=(
            "The refine-terminal-class token this terminal just wrote; omit on the "
            "done paths (no class file is written there)"
        ),
    )
    w.add_argument(
        "--child-ids",
        nargs="*",
        default=None,
        metavar="ID",
        help="Override child derivation with an explicit list",
    )
    w.add_argument(
        "--evidence-refs",
        nargs="*",
        default=[],
        metavar="REF",
        help="Run artifacts evidencing the outcome (recorded verbatim)",
    )
    w.add_argument(
        "--readiness-threshold",
        type=int,
        default=None,
        metavar="N",
        help="Explicit readiness threshold beating config (as check-readiness)",
    )
    w.add_argument(
        "--outcome-threshold",
        type=int,
        default=None,
        metavar="N",
        help="Explicit outcome threshold beating config (as check-readiness)",
    )
    add_config_arg(w)

    r = subsubs.add_parser(
        "read",
        help="Print the routing token for one issue's run record",
    )
    r.add_argument("issue_id", help="Issue ID (e.g., 3597, ENH-3597, P3-ENH-3597)")
    r.add_argument("--run-dir", required=True, help="The run's run_dir")
    r.add_argument("--writer", required=True, choices=WRITERS, help="Which loop wrote the record")
    r.add_argument(
        "--format",
        default="token",
        choices=("token",),
        help="Output format (only 'token': one RUN_RECORD_TOKENS member)",
    )
    add_config_arg(r)

    c = subsubs.add_parser(
        "clear",
        help="Delete one issue's run record (exit 0 whether or not it existed)",
    )
    c.add_argument("issue_id", help="Issue ID (e.g., 3597, ENH-3597, P3-ENH-3597)")
    c.add_argument("--run-dir", required=True, help="The run's run_dir")
    c.add_argument("--writer", required=True, choices=WRITERS, help="Which loop wrote the record")
    add_config_arg(c)

    f = subsubs.add_parser(
        "forward",
        help=(
            "Copy one writer's record for an issue under another writer and print "
            "its routing token (MISSING, writing nothing, when the source is absent)"
        ),
    )
    f.add_argument("issue_id", help="Issue ID (e.g., 3597, ENH-3597, P3-ENH-3597)")
    f.add_argument("--run-dir", required=True, help="The run's run_dir")
    f.add_argument(
        "--from",
        dest="from_writer",
        required=True,
        choices=WRITERS,
        help="Writer whose record is copied",
    )
    f.add_argument("--writer", required=True, choices=WRITERS, help="Writer the copy is written as")
    add_config_arg(f)
    return p


def _id_core(issue_id: str) -> str:
    """Return the numeric core of an issue ID ('' when there is none)."""
    m = _ID_CORE_RE.search(str(issue_id or ""))
    return m.group(1) if m else ""


def _parent_matches(parent_value: object, issue_core: str) -> bool:
    """True when a frontmatter ``parent`` value references the issue's numeric core."""
    if parent_value is None:
        return False
    candidates = parent_value if isinstance(parent_value, list) else [parent_value]
    return any(_id_core(str(v)) == issue_core and _id_core(str(v)) != "" for v in candidates)


def derive_child_ids(config: BRConfig, issue_id: str) -> list[str]:
    """Derive an issue's children by scanning ``parent:`` frontmatter.

    The same provenance autodev's ``detect_children`` trusts (deterministic —
    written by issue-size-review); no in-loop capture of child IDs exists, so
    the writer reproduces the derivation instead of guessing.
    """
    core = _id_core(issue_id)
    if not core:
        return []
    from little_loops.frontmatter import parse_frontmatter

    children: list[str] = []
    for category in config.issue_categories:
        issue_dir = config.get_issue_dir(category)
        if not issue_dir.is_dir():
            continue
        for path in sorted(issue_dir.glob("*.md")):
            if _id_core(path.stem) == core:
                continue  # the issue itself
            try:
                fm = parse_frontmatter(path.read_text())
            except OSError:
                continue
            if _parent_matches(fm.get("parent"), core):
                child_id = str(fm.get("id") or path.stem)
                children.append(child_id)
    return children


def _read_broke_down(run_dir: str) -> bool:
    """Read the shared refine-broke-down counter ('1' == decomposed this run)."""
    try:  # absent/unreadable counter reads as not-broke-down
        return Path(run_dir, _BROKE_DOWN_FILENAME).read_text().strip() == "1"
    except OSError:
        return False


def cmd_run_record(config: BRConfig, args: argparse.Namespace) -> int:
    """Dispatch a ``run-record`` sub-subcommand."""
    command = getattr(args, "run_record_command", None)
    if command == "write":
        return cmd_run_record_write(config, args)
    if command == "read":
        return cmd_run_record_read(config, args)
    if command == "clear":
        return cmd_run_record_clear(config, args)
    if command == "forward":
        return cmd_run_record_forward(config, args)
    print(
        "Error: run-record requires a subcommand (write, read, clear, forward).",
        file=sys.stderr,
    )
    return 2


def canonical_record_id(config: BRConfig, issue_id: str) -> str:
    """Return the id a record is keyed on: the frontmatter ``id``, else *issue_id*.

    Shared by write, read and clear so ``3607`` / ``ENH-3607`` / ``P3-ENH-3607``
    all address the same record file.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter

    path = _resolve_issue_id(config, issue_id)
    if path is None:
        return issue_id
    try:
        fm = parse_frontmatter(path.read_text(), coerce_types=True)
    except OSError:
        return issue_id
    return str(fm.get("id") or issue_id)


def cmd_run_record_read(config: BRConfig, args: argparse.Namespace) -> int:
    """Print the record's routing token (``MISSING`` when absent); always returns 0."""
    from little_loops.run_record import read_run_record, record_token

    record = read_run_record(
        Path(args.run_dir), args.writer, canonical_record_id(config, args.issue_id)
    )
    print(record_token(record))
    return 0


def cmd_run_record_clear(config: BRConfig, args: argparse.Namespace) -> int:
    """Delete the canonical record file; returns 0 whether or not it existed."""
    from little_loops.run_record import record_path

    record_path(Path(args.run_dir), args.writer, canonical_record_id(config, args.issue_id)).unlink(
        missing_ok=True
    )
    return 0


def cmd_run_record_forward(config: BRConfig, args: argparse.Namespace) -> int:
    """Re-write the ``--from`` writer's record under ``--writer``; always returns 0.

    Only ``writer`` changes (``read_run_record`` rejects a stored writer that
    differs from the request). Prints the forwarded record's routing token, or
    ``MISSING`` (writing nothing) when the source record is absent.
    """
    from dataclasses import replace

    from little_loops.run_record import read_run_record, record_token

    record = read_run_record(
        Path(args.run_dir), args.from_writer, canonical_record_id(config, args.issue_id)
    )
    if record is not None:
        write_run_record(Path(args.run_dir), replace(record, writer=args.writer))
    print(record_token(record))
    return 0


def cmd_run_record_write(config: BRConfig, args: argparse.Namespace) -> int:
    """Write the typed run record; prints ``[RUN_RECORD_WRITTEN] <ID> <outcome>``.

    The ``ready`` predicate is autodev ``check_passed``'s exact one —
    ``readiness_status`` with the waiver honored, and scores-absent
    (check-readiness exit 3) counting as not-met — resolved in-process rather
    than via a subprocess.

    Returns:
        0 record written, 2 when the issue cannot be resolved.
    """
    from little_loops.cli.issues.check_readiness import readiness_status
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter
    from little_loops.run_record import outcome_from_legacy_class

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 2

    fm = parse_frontmatter(path.read_text(), coerce_types=True)
    canonical_id = canonical_record_id(config, args.issue_id)
    status = str(fm.get("status") or "") or None

    rs = readiness_status(
        config,
        args.issue_id,
        readiness_override=getattr(args, "readiness_threshold", None),
        outcome_override=getattr(args, "outcome_threshold", None),
    )
    thresholds_met = bool(
        rs is not None
        and not rs.confidence_absent
        and not rs.outcome_absent
        and rs.meets_readiness
        and rs.meets_outcome_or_waived
    )

    child_ids = (
        list(args.child_ids)
        if args.child_ids is not None
        else derive_child_ids(config, args.issue_id)
    )
    outcome = outcome_from_legacy_class(
        args.legacy_class, _read_broke_down(args.run_dir), thresholds_met, status
    )
    record = RunRecord(
        writer=args.writer,
        issue_id=canonical_id,
        outcome=outcome,
        child_ids=tuple(child_ids),
        evidence_refs=tuple(args.evidence_refs),
        legacy_class=args.legacy_class,
        readiness=rs.raw_confidence if rs is not None else None,
        outcome_confidence=rs.raw_outcome if rs is not None else None,
    )
    written = write_run_record(Path(args.run_dir), record)
    print(f"[RUN_RECORD_WRITTEN] {canonical_id} {outcome} {written}")
    return 0
