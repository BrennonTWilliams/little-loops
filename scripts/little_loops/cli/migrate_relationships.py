"""ll-migrate-relationships: Rename parent_issue: -> parent: and related: -> relates_to: in issue files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.cli_args import add_config_arg, add_dry_run_arg
from little_loops.config import BRConfig
from little_loops.frontmatter import (
    parse_frontmatter,
    remove_frontmatter_keys,
    update_frontmatter,
)
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

# Deprecated key -> canonical replacement, in the order they are reported.
_RENAMES: tuple[tuple[str, str], ...] = (
    ("parent_issue", "parent"),
    ("related", "relates_to"),
    ("target_branch", "base_branch"),
)


def _migrate_content(content: str) -> tuple[str, list[str]]:
    """Rename deprecated relationship keys in frontmatter.

    Writes the canonical key into the *canonical* (``id:``-bearing) block via
    :func:`update_frontmatter` — on a file carrying more than one frontmatter
    block, a hand-rolled splice would land it in the wrong one (BUG-2955). When
    a file already carries the canonical key, the deprecated one is dropped
    rather than promoted, matching the parser's ``if parent is None`` precedence
    in :func:`little_loops.issue_parser.IssueParser.parse_file`.

    Returns:
        ``(updated_content, list_of_renames)``; an empty rename list means the
        file needs no change.
    """
    fm = parse_frontmatter(content)
    if not fm:
        return content, []

    renames: list[str] = []
    result = content

    for old_key, new_key in _RENAMES:
        if old_key not in fm:
            continue
        value = fm[old_key]
        if new_key in fm:
            renames.append(f"{old_key}: {value!r} dropped ({new_key}: {fm[new_key]!r} already set)")
        else:
            result = update_frontmatter(result, {new_key: value})
            renames.append(f"{old_key}: {value!r} → {new_key}: {value!r}")
        result = remove_frontmatter_keys(result, [old_key])

    return result, renames


def main_migrate_relationships() -> int:
    """Entry point for ll-migrate-relationships command.

    Renames parent_issue: -> parent:, related: -> relates_to:, and
    target_branch: -> base_branch: in all issue files.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-migrate-relationships", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-migrate-relationships",
            description=(
                "Rename parent_issue: → parent:, related: → relates_to:, and "
                "target_branch: → base_branch: in all issue frontmatter files. "
                "One-time migration for ENH-1431."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s --dry-run     # Preview all planned renames (strongly advised first)
  %(prog)s               # Execute migration
""",
        )
        add_dry_run_arg(parser)
        add_config_arg(parser)
        args = parser.parse_args()

        dry_run: bool = args.dry_run
        repo_root: Path = args.config or Path.cwd()

        # Honor a project's configured issues.base_dir — a hardcoded ".issues"
        # made this CLI a silent no-op on any project that renamed it.
        base_dir = BRConfig(repo_root).issues.base_dir
        issues_dir = repo_root / base_dir
        if not issues_dir.exists():
            print(f"No {base_dir}/ directory found at {repo_root}")
            return 1

        if dry_run:
            print("[DRY RUN] No files will be modified.")

        renamed = 0
        errors: list[str] = []

        for file_path in sorted(issues_dir.rglob("*.md")):
            try:
                content = file_path.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(str(file_path))
                print(f"  [ERROR] {file_path}: {exc}")
                continue

            updated, renames = _migrate_content(content)
            if not renames:
                continue

            prefix = "[DRY RUN] " if dry_run else ""
            rel = file_path.relative_to(repo_root)
            for rename in renames:
                print(f"  {prefix}RENAME {rel}: {rename}")

            if not dry_run:
                try:
                    file_path.write_text(updated, encoding="utf-8")
                    renamed += 1
                except OSError as exc:
                    errors.append(str(file_path))
                    print(f"  [ERROR] {file_path}: {exc}")
            else:
                renamed += 1

        print()
        print(f"Results: {renamed} files {'would be ' if dry_run else ''}updated.")
        if errors:
            print(f"  Errors: {len(errors)}")
            return 1
        return 0
