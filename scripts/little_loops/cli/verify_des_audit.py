"""ll-verify-des-audit: Walk the source tree and verify every event-emit site maps to a registered DES variant.

The audit walker (``little_loops.observability.audit``) statically extracts every emit
string literal from the source tree and checks each against ``DES_VARIANT_TYPES``. Exit 0
when every emit site maps to a registered variant (the F5 adoption gate); exit 1
otherwise.

Precedent: ``scripts/little_loops/cli/verify_design_tokens.py`` (cli_event_context +
argparse + dataclass result + dual --json/text output).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from little_loops.observability.audit import AuditResult, audit_tree
from little_loops.observability.schema import DES_VARIANT_TYPES, DES_VARIANTS
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

# ---------------------------------------------------------------------------
# Source-tree discovery
# ---------------------------------------------------------------------------


def _find_source_dir(base_dir: Path) -> Path | None:
    """Locate a ``scripts/little_loops`` source directory under *base_dir*.

    Tries the source-repo editable layout first, then the user-project layout for
    completeness (matches ``verify_design_tokens.py:_find_profiles_dir`` precedent).
    """
    for candidate in (
        base_dir / "scripts" / "little_loops",
        base_dir / "little_loops",
    ):
        if candidate.is_dir():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _format_text_report(result: AuditResult, source_dir: Path) -> str:
    """Human-readable audit verdict."""
    lines: list[str] = [
        "DES Audit (F5 adoption gate)",
        "=" * 50,
        "",
        f"Source directory: {source_dir}",
        f"Files scanned:    {result.files_scanned}",
        f"Emit sites found: {result.emit_sites_found}",
        f"Variants registered: {len(DES_VARIANTS)}",
        "",
    ]
    if result.passed:
        lines.append("All emit sites map to a registered DES variant.")
        lines.append("")
        lines.append("PASSED")
    else:
        lines.append("Uncovered event types (no registered DES variant):")
        for etype in result.uncovered_event_types:
            lines.append(f"  - {etype}")
        lines.append("")
        lines.append("Register a new variant in scripts/little_loops/observability/schema.py")
        lines.append("and add it to DES_VARIANTS, then re-run the audit.")
        lines.append("")
        lines.append("FAILED")
    return "\n".join(lines)


def _format_json_report(result: AuditResult, source_dir: Path) -> str:
    """Machine-readable audit verdict."""
    return json.dumps(
        {
            "source_dir": str(source_dir),
            "files_scanned": result.files_scanned,
            "emit_sites_found": result.emit_sites_found,
            "variants_registered": len(DES_VARIANTS),
            "variant_types_count": len(DES_VARIANT_TYPES),
            "uncovered_event_types": result.uncovered_event_types,
            "passed": result.passed,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main_verify_des_audit() -> int:
    """Entry point for ``ll-verify-des-audit``.

    Returns 0 when every emit site maps to a registered DES variant; 1 otherwise.

    This is the F5 acceptance gate: until every currently-emitted event has a registered
    variant, F5's ``gen_ai.usage.*`` emit path cannot land without coercing unmodeled
    shapes.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-des-audit", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-des-audit",
            description=(
                "Walk the source tree and verify every event-emit site maps to a "
                "registered DES variant — the F5 (DES adoption) gate (ENH-2475)."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""\
Examples:
  %(prog)s                          # Auto-discover source dir from cwd
  %(prog)s -C /path/to/root         # Discover under a specific project root
  %(prog)s --source-dir DIR         # Walk a specific source directory
  %(prog)s --json                   # Machine-readable JSON output

Exit codes:
  0 - Every emit site maps to a registered DES variant
  1 - One or more uncovered event types (or source dir not found)
""",
        )
        parser.add_argument(
            "-C",
            "--directory",
            type=Path,
            default=None,
            help="Project root to discover the source directory under (default: cwd)",
        )
        parser.add_argument(
            "--source-dir",
            type=Path,
            default=None,
            help="Explicit path to a little_loops source/ directory (overrides -C discovery)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="Output results as JSON",
        )

        args = parser.parse_args()

        source_dir = args.source_dir or _find_source_dir(args.directory or Path.cwd())
        if source_dir is None or not source_dir.is_dir():
            print(
                "ERROR: source directory not found "
                f"(searched under {args.directory or Path.cwd()})",
                file=sys.stderr,
            )
            return 1

        result = audit_tree(source_dir)

        if args.json:
            print(_format_json_report(result, source_dir))
        else:
            print(_format_text_report(result, source_dir))

        return 0 if result.passed else 1
