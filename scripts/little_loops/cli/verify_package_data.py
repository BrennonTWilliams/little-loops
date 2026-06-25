"""ll-verify-package-data: Package-data escape lint and manifest completeness check.

Runs two gates to prevent the "asset escapes the wheel" bug class:

1. **__file__-escape lint** (regression backstop): regex-scans little_loops/
   source for Path(__file__) expressions whose parent-traversal depth exits
   the package. Reports violations and exits non-zero.

2. **Manifest completeness check** (primary gate): verifies every asset
   declared in PACKAGE_DATA_ASSETS is accessible via importlib.resources
   in the current installation. Exits non-zero when any asset is missing.

The lint is syntactic — it catches the pattern but is blind to reads through
the shared resolver (covered by gate 2). Both must pass for exit 0.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Files exempt from the escape lint (canonical resolver/plugin-root traversals).
# Paths are relative to the little_loops package root, using forward slashes.
_ALLOWLIST: frozenset[str] = frozenset(
    {
        "init/cli.py",        # canonical _plugin_root() resolver — intentional traversal
        "skill_expander.py",  # _find_plugin_root() — same pattern as shared resolver
    }
)

# Match Path(__file__) optionally followed by .resolve(), then either:
#   - .parents[N]  (group 1 = ".parents[N]", group 2 = "N")
#   - a chain of .parent  (group 1 = ".parent...", group 2 = None)
_FILE_ESCAPE_RE = re.compile(
    r"Path\(__file__\)(?:\.resolve\(\))?"
    r"(\.parents\[(\d+)\]|(?:\.parent)+)"
)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class EscapeViolation:
    """A single __file__-escape violation."""

    rel_path: str
    line_no: int
    match_text: str
    parent_count: int
    depth: int


@dataclass
class LintResult:
    """Result of linting one .py file."""

    rel_path: str
    violations: list[EscapeViolation] = field(default_factory=list)

    @property
    def has_violations(self) -> bool:
        return bool(self.violations)


# ---------------------------------------------------------------------------
# Core lint logic
# ---------------------------------------------------------------------------


def _file_depth(py_file: Path, pkg_root: Path) -> int:
    """Directory levels between pkg_root and py_file (excludes the filename)."""
    return len(py_file.relative_to(pkg_root).parts) - 1


def _count_parent_steps(match: re.Match[str]) -> int:
    """Effective number of .parent traversal steps from a regex match.

    .parents[N] is equivalent to N+1 calls to .parent.
    """
    chain = match.group(1)
    idx = match.group(2)
    if idx is not None:
        return int(idx) + 1
    return chain.count(".parent")


def _lint_file(py_file: Path, pkg_root: Path) -> LintResult:
    """Scan one .py file for __file__-escape violations."""
    rel = py_file.relative_to(pkg_root)
    # Normalize to forward-slash string for allowlist comparison
    rel_str = rel.as_posix()

    if rel_str in _ALLOWLIST:
        return LintResult(rel_path=rel_str)

    depth = _file_depth(py_file, pkg_root)
    violations: list[EscapeViolation] = []

    try:
        lines = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return LintResult(rel_path=rel_str)

    for line_no, line in enumerate(lines, start=1):
        for m in _FILE_ESCAPE_RE.finditer(line):
            count = _count_parent_steps(m)
            # Escapes the package when traversals exceed depth + 1.
            # depth+1 .parent calls land at pkg_root itself (still in-package);
            # depth+2 (i.e. count > depth+1) exits to the parent of pkg_root.
            if count > depth + 1:
                violations.append(
                    EscapeViolation(
                        rel_path=rel_str,
                        line_no=line_no,
                        match_text=m.group(0),
                        parent_count=count,
                        depth=depth,
                    )
                )

    return LintResult(rel_path=rel_str, violations=violations)


def run_escape_lint(pkg_root: Path) -> list[LintResult]:
    """Run the __file__-escape lint over all .py files under pkg_root."""
    results: list[LintResult] = []
    for py_file in sorted(pkg_root.rglob("*.py")):
        result = _lint_file(py_file, pkg_root)
        if result.has_violations:
            results.append(result)
    return results


# ---------------------------------------------------------------------------
# Manifest check
# ---------------------------------------------------------------------------


def run_manifest_check() -> list[tuple[str, ...]]:
    """Return asset tuples in PACKAGE_DATA_ASSETS missing from the current install."""
    from little_loops.package_data import list_missing_assets

    return list_missing_assets()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _format_text_report(
    lint_results: list[LintResult],
    missing_assets: list[tuple[str, ...]],
) -> str:
    lines: list[str] = ["Package Data Escape Lint + Manifest Check", "=" * 50, ""]

    if lint_results:
        lines.append("__file__ Escape Violations:")
        for r in lint_results:
            for v in r.violations:
                lines.append(
                    f"  {v.rel_path}:{v.line_no}: {v.match_text}"
                    f"  (depth={v.depth}, traversals={v.parent_count})"
                )
        lines.append("")
    else:
        lines.append("__file__ escape lint: PASS — no violations")
        lines.append("")

    if missing_assets:
        lines.append("Missing assets (not accessible via importlib.resources):")
        for parts in missing_assets:
            lines.append(f"  little_loops/{'/'.join(parts)}")
        lines.append("")
    else:
        lines.append("Manifest check: PASS — all assets accessible")
        lines.append("")

    lines.append("FAILED" if (lint_results or missing_assets) else "PASSED")
    return "\n".join(lines)


def _format_json_report(
    lint_results: list[LintResult],
    missing_assets: list[tuple[str, ...]],
) -> str:
    return json.dumps(
        {
            "escape_violations": [
                {
                    "file": v.rel_path,
                    "line": v.line_no,
                    "match": v.match_text,
                    "parent_count": v.parent_count,
                    "depth": v.depth,
                }
                for r in lint_results
                for v in r.violations
            ],
            "missing_assets": [list(parts) for parts in missing_assets],
            "passed": not lint_results and not missing_assets,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _find_pkg_root(base_dir: Path) -> Path | None:
    """Locate the little_loops/ package directory under base_dir."""
    for candidate in (
        base_dir / "scripts" / "little_loops",
        base_dir / "little_loops",
    ):
        if candidate.is_dir():
            return candidate
    return None


def main_verify_package_data() -> int:
    """Entry point for ll-verify-package-data.

    Returns 0 when no __file__ escapes are detected and all manifest assets
    are accessible; returns 1 otherwise.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-package-data", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-package-data",
            description=(
                "Lint package code for __file__ escapes that would break non-editable "
                "installs, and verify all declared assets are accessible via "
                "importlib.resources."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""\
Examples:
  %(prog)s                     # Run lint + manifest check from cwd
  %(prog)s -C /path/to/root    # Run from a specific project root
  %(prog)s --json              # Machine-readable JSON output
  %(prog)s --lint-only         # Run only the __file__-escape lint
  %(prog)s --manifest-only     # Run only the manifest completeness check

Exit codes:
  0 - No escape violations; all manifest assets accessible
  1 - One or more violations or missing assets
""",
        )
        parser.add_argument(
            "-C",
            "--directory",
            type=Path,
            default=None,
            help="Project root containing the little_loops package (default: cwd)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="Output results as JSON",
        )
        parser.add_argument(
            "--lint-only",
            action="store_true",
            default=False,
            help="Run only the __file__-escape lint (skip manifest check)",
        )
        parser.add_argument(
            "--manifest-only",
            action="store_true",
            default=False,
            help="Run only the manifest completeness check (skip lint)",
        )

        args = parser.parse_args()

        base_dir = args.directory or Path.cwd()
        pkg_root = _find_pkg_root(base_dir)

        if pkg_root is None:
            print(
                f"ERROR: little_loops package directory not found under {base_dir}",
                file=sys.stderr,
            )
            return 1

        lint_results: list[LintResult] = []
        missing_assets: list[tuple[str, ...]] = []

        if not args.manifest_only:
            lint_results = run_escape_lint(pkg_root)

        if not args.lint_only:
            missing_assets = run_manifest_check()

        if args.json:
            print(_format_json_report(lint_results, missing_assets))
        else:
            print(_format_text_report(lint_results, missing_assets))

        return 1 if (lint_results or missing_assets) else 0
