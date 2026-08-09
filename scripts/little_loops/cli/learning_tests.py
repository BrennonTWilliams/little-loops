"""ll-learning-tests: CLI for querying and managing the learning test registry."""

from __future__ import annotations

import argparse
import sys

from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = ["main_learning_tests"]


def cmd_check(args: argparse.Namespace) -> int:
    from little_loops.cli.output import print_json
    from little_loops.learning_tests import check_learning_test

    record = check_learning_test(args.target)
    if record is None:
        print(f"Error: no record found for {args.target!r}", file=sys.stderr)
        return 1

    failing = record.failing_claims()
    output = record.to_dict()
    output["failing_claims"] = len(failing)
    print_json(output)

    if failing:
        print(
            f"⚠ {len(failing)} failing assertion(s) in {args.target!r} (status={record.status}):",
            file=sys.stderr,
        )
        for claim in failing:
            print(f"  - {claim}", file=sys.stderr)

    if getattr(args, "stale_aware", False):
        import json as _json
        from pathlib import Path

        from little_loops.config.core import resolve_config_path
        from little_loops.config.features import LearningTestsConfig
        from little_loops.learning_tests.gate import is_record_stale

        config_path = resolve_config_path(Path.cwd())
        lt_config = LearningTestsConfig()
        if config_path is not None:
            try:
                data = _json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    lt_config = LearningTestsConfig.from_dict(data.get("learning_tests", {}))
            except (OSError, _json.JSONDecodeError):
                pass

        if record.status != "proven" or is_record_stale(
            record,
            lt_config.stale_after_days,
            version_aware=lt_config.version_aware_staleness,
            backstop_multiplier=lt_config.version_match_backstop_multiplier,
        ):
            return 1

    return 0


def cmd_prove(args: argparse.Namespace) -> int:
    import subprocess

    from little_loops.cli.output import print_json
    from little_loops.learning_tests import check_learning_test

    try:
        result = subprocess.run(
            [
                "ll-loop",
                "run",
                "ready-to-implement-gate",
                "--context",
                f"targets={args.target}",
            ],
        )
    except FileNotFoundError:
        print("Error: 'll-loop' not found on PATH — is little-loops installed?", file=sys.stderr)
        return 1

    if result.returncode != 0:
        print(
            f"Error: 'll-loop run ready-to-implement-gate' exited {result.returncode} "
            f"for {args.target!r}",
            file=sys.stderr,
        )
        return 1

    record = check_learning_test(args.target)
    if record is None:
        print(f"Error: no record found for {args.target!r}", file=sys.stderr)
        return 1

    _stamp_proven_version(args.target, record)
    _record_learning_test_mirror(args.target)

    print_json(record.to_dict())
    if record.status != "proven":
        print(f"Error: {args.target!r} re-proven as {record.status}", file=sys.stderr)
        return 1
    return 0


def _write_version_fields(target: str, pkg: str, version: str) -> bool:
    """Stamp ``proven_package``/``proven_version`` onto a record on disk.

    Returns True if the file was written. Records are authored as YAML by
    ``/ll:explore-api`` (never by ``write_record()``), so this enriches the
    file in place rather than rewriting it (ENH-3125).
    """
    from pathlib import Path

    from little_loops.frontmatter import update_frontmatter
    from little_loops.issue_parser import slugify

    path = Path.cwd() / ".ll" / "learning-tests" / f"{slugify(target)}.md"
    if not path.exists():
        return False
    updated = update_frontmatter(
        path.read_text(), {"proven_package": pkg, "proven_version": version}
    )
    path.write_text(updated)
    return True


def _stamp_proven_version(target: str, record: object) -> None:
    """Capture the installed version the target was just proven against (ENH-3125).

    This is the *only* mechanism the version-drift staleness check depends on
    for populating the fields: record creation is owned by ``/ll:explore-api``,
    and an LLM-typed version would be non-deterministic and could silently
    poison the comparison toward "not stale". Best-effort — a resolution or
    write failure leaves the record on the age-based path.
    """
    try:
        from little_loops.learning_tests.gate import resolve_target_version

        resolved = resolve_target_version(target)
        if resolved is None:
            return
        pkg, version = resolved
        if (
            getattr(record, "proven_package", None) == pkg
            and getattr(record, "proven_version", None) == version
        ):
            return
        if _write_version_fields(target, pkg, version):
            record.proven_package = pkg  # type: ignore[attr-defined]
            record.proven_version = version  # type: ignore[attr-defined]
    except Exception:
        pass


def cmd_backfill_versions(args: argparse.Namespace) -> int:
    """Stamp proven_package/proven_version onto pre-ENH-3125 records."""
    from little_loops.learning_tests import list_records
    from little_loops.learning_tests.gate import resolve_target_version

    changed = 0
    skipped = 0
    for record in list_records():
        resolved = resolve_target_version(record.target)
        if resolved is None:
            # Stdlib, unresolvable, or free-text target — stays on the
            # age-based path by design, not a failure.
            skipped += 1
            continue
        pkg, version = resolved
        if record.proven_package == pkg and record.proven_version == version:
            skipped += 1
            continue
        if args.dry_run:
            print(f"would stamp {record.target}  →  {pkg} {version}")
            changed += 1
        elif _write_version_fields(record.target, pkg, version):
            print(f"stamped {record.target}  →  {pkg} {version}")
            changed += 1
        else:
            skipped += 1

    verb = "would stamp" if args.dry_run else "stamped"
    print(f"\n{verb} {changed} record(s); left {skipped} unchanged.")
    return 0


def _record_learning_test_mirror(target: str) -> None:
    """Best-effort mirror write into ``learning_test_events`` (ENH-2466).

    Wrapped in ``try/except: pass`` per the ``set_status.py``/
    ``record_issue_snapshot`` graceful-degradation precedent — a DB failure
    must never break ``ll-learning-tests prove``/``mark-stale``.
    """
    try:
        from little_loops.issue_parser import slugify
        from little_loops.session_store import record_learning_test_event

        file_path = f".ll/learning-tests/{slugify(target)}.md"
        record_learning_test_event(DEFAULT_DB_PATH, target, file_path)
    except Exception:
        pass


def cmd_list(_args: argparse.Namespace) -> int:
    from little_loops.cli.output import print_json
    from little_loops.learning_tests import list_records

    records = list_records()
    print_json([r.to_dict() for r in records])
    return 0


def cmd_mark_stale(args: argparse.Namespace) -> int:
    from little_loops.issue_parser import slugify
    from little_loops.learning_tests import check_learning_test, mark_stale

    record = check_learning_test(args.target)
    if record is None:
        print(f"Error: no record found for {args.target!r}", file=sys.stderr)
        return 1
    mark_stale(slugify(args.target))
    _record_learning_test_mirror(args.target)
    return 0


def cmd_orphans(args: argparse.Namespace) -> int:
    import json as _json
    from pathlib import Path

    from little_loops.config.core import resolve_config_path
    from little_loops.issue_parser import slugify
    from little_loops.learning_tests import list_records, mark_stale
    from little_loops.learning_tests.import_scan import get_imported_packages, normalize_target

    source_dirs: list[Path]
    if args.scope:
        source_dirs = [Path(d.strip()) for d in args.scope.split(",")]
    else:
        resolved: list[Path] | None = None
        config_path = resolve_config_path(Path.cwd())
        if config_path is not None:
            try:
                data = _json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    raw = data.get("learning_tests", {}).get("scan_dirs")
                    if raw:
                        resolved = [Path(d) for d in raw]
            except (OSError, _json.JSONDecodeError):
                pass
        source_dirs = resolved if resolved is not None else [Path("scripts/")]

    imported = get_imported_packages(source_dirs)

    records = list_records()
    orphans = [r for r in records if normalize_target(r.target) not in imported]

    if not orphans:
        print("No orphaned records found.")
        return 0

    for record in orphans:
        print(f"{record.target}  (status: {record.status}, date: {record.date})")

    if args.mark_stale:
        for record in orphans:
            mark_stale(slugify(record.target))
            _record_learning_test_mirror(record.target)
        print(f"\nMarked {len(orphans)} record(s) stale.")
        return 0

    return 1


def main_learning_tests() -> int:
    """CLI handler for ll-learning-tests subcommands."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-learning-tests", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-learning-tests",
            description="Query and manage the little-loops learning test registry",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  ll-learning-tests check "Anthropic SDK streaming"
  ll-learning-tests list
  ll-learning-tests mark-stale "Anthropic SDK streaming"
  ll-learning-tests prove "Anthropic SDK streaming"
""",
        )

        subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
        subparsers.required = True

        check_parser = subparsers.add_parser(
            "check",
            help="Print a record as JSON; exit 1 if not found",
            description="Look up a learning test record by target name and print as JSON",
        )
        check_parser.add_argument("target", help="Target name (e.g. 'Anthropic SDK streaming')")
        check_parser.add_argument(
            "--stale-aware",
            action="store_true",
            default=False,
            dest="stale_aware",
            help=(
                "Exit 1 if the record is absent or date-stale "
                "(even if status=proven); exit 0 only if proven and within stale_after_days threshold"
            ),
        )

        subparsers.add_parser(
            "list",
            help="Print all records as a JSON array",
            description="List all learning test records in the registry",
        )

        stale_parser = subparsers.add_parser(
            "mark-stale",
            help="Mark a record as stale; exit 1 if not found",
            description="Set status=stale on a learning test record",
        )
        stale_parser.add_argument("target", help="Target name (e.g. 'Anthropic SDK streaming')")

        orphans_parser = subparsers.add_parser(
            "orphans",
            help="List records for packages no longer imported; exit 1 if any found",
            description=(
                "Detect learning test records whose target package is no longer imported "
                "anywhere in the configured source directories."
            ),
        )
        orphans_parser.add_argument(
            "--mark-stale",
            action="store_true",
            default=False,
            dest="mark_stale",
            help="Atomically mark all orphaned records stale and exit 0",
        )
        orphans_parser.add_argument(
            "--scope",
            default=None,
            metavar="DIRS",
            help=(
                "Comma-separated list of directories to scan for imports "
                "(default: learning_tests.scan_dirs config key, fallback 'scripts/')"
            ),
        )

        prove_parser = subparsers.add_parser(
            "prove",
            help="Trigger proving for a target; print the refreshed record",
            description=(
                "Trigger proving for a target via the ready-to-implement-gate loop "
                "(retry-then-/ll:explore-api) and print the refreshed registry record"
            ),
        )
        prove_parser.add_argument("target", help="Target name (e.g. 'Anthropic SDK streaming')")

        backfill_parser = subparsers.add_parser(
            "backfill-versions",
            help="Stamp proven_package/proven_version onto existing records",
            description=(
                "Resolve each record's target to an installed distribution and stamp "
                "proven_package/proven_version onto its frontmatter (ENH-3125), enabling "
                "version-drift staleness for records proven before the fields existed. "
                "Stdlib and non-distribution targets are left untouched and keep "
                "age-based staleness. Idempotent."
            ),
        )
        backfill_parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            dest="dry_run",
            help="Print what would be stamped without writing any record",
        )

        parsed = parser.parse_args()

        if parsed.command == "check":
            return cmd_check(parsed)
        elif parsed.command == "list":
            return cmd_list(parsed)
        elif parsed.command == "mark-stale":
            return cmd_mark_stale(parsed)
        elif parsed.command == "orphans":
            return cmd_orphans(parsed)
        elif parsed.command == "prove":
            return cmd_prove(parsed)
        elif parsed.command == "backfill-versions":
            return cmd_backfill_versions(parsed)
        else:
            parser.print_help()
            return 1
