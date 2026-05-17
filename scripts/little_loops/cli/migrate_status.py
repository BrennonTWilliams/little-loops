"""ll-migrate-status: Normalize non-canonical status: values in issue files to canonical ones."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from little_loops.cli_args import add_config_arg, add_dry_run_arg
from little_loops.frontmatter import STATUS_SYNONYMS

_STATUS_FIELD_RE = re.compile(r"^(status: )(.+)$", re.MULTILINE)


def _migrate_content(content: str) -> tuple[str, list[str]]:
    """Normalize status field in frontmatter. Returns (updated_content, list_of_changes)."""
    changes: list[str] = []

    def _replace(m: re.Match[str]) -> str:
        prefix, value = m.group(1), m.group(2)
        canonical = STATUS_SYNONYMS.get(value, value)
        if canonical != value:
            changes.append(f"status: {value!r} → status: {canonical!r}")
            return f"{prefix}{canonical}"
        return m.group(0)

    updated = _STATUS_FIELD_RE.sub(_replace, content)
    return updated, changes


def main_migrate_status() -> int:
    """Entry point for ll-migrate-status command.

    Normalizes non-canonical status: values in all .issues/**/*.md files to their
    canonical equivalents using STATUS_SYNONYMS from frontmatter.py.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    parser = argparse.ArgumentParser(
        prog="ll-migrate-status",
        description=(
            "Normalize non-canonical status: frontmatter values to canonical ones "
            "(e.g. 'completed' → 'done', 'wip' → 'in_progress'). "
            "One-time migration for ENH-1551."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run     # Preview all planned normalizations (strongly advised first)
  %(prog)s               # Execute migration
""",
    )
    add_dry_run_arg(parser)
    add_config_arg(parser)
    args = parser.parse_args()

    dry_run: bool = args.dry_run
    repo_root: Path = args.config or Path.cwd()

    issues_dir = repo_root / ".issues"
    if not issues_dir.exists():
        print(f"No .issues/ directory found at {repo_root}")
        return 1

    if dry_run:
        print("[DRY RUN] No files will be modified.")

    normalized = 0
    errors: list[str] = []

    for file_path in sorted(issues_dir.rglob("*.md")):
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(str(file_path))
            print(f"  [ERROR] {file_path}: {exc}")
            continue

        updated, changes = _migrate_content(content)
        if not changes:
            continue

        prefix = "[DRY RUN] " if dry_run else ""
        rel = file_path.relative_to(repo_root)
        for change in changes:
            print(f"  {prefix}NORMALIZE {rel}: {change}")

        if not dry_run:
            try:
                file_path.write_text(updated, encoding="utf-8")
                normalized += 1
            except OSError as exc:
                errors.append(str(file_path))
                print(f"  [ERROR] {file_path}: {exc}")
        else:
            normalized += 1

    print()
    print(f"Results: {normalized} files {'would be ' if dry_run else ''}updated.")
    if errors:
        print(f"  Errors: {len(errors)}")
        return 1
    return 0
