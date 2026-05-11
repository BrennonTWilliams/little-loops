"""ll-migrate-relationships: Rename parent_issue: -> parent: and related: -> relates_to: in issue files."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from little_loops.cli_args import add_config_arg, add_dry_run_arg
from little_loops.frontmatter import parse_frontmatter

_FM_FIELD_RE = re.compile(r"^---\s*$", re.MULTILINE)

_PARENT_ISSUE_RE = re.compile(r"^parent_issue:(.*)$", re.MULTILINE)
_RELATED_RE = re.compile(r"^related:(.*)$", re.MULTILINE)


def _set_fields(content: str, fields: dict[str, str]) -> str:
    """Set frontmatter fields via direct string manipulation (avoids yaml roundtrip).

    Replaces existing fields in-place; inserts missing fields before the closing
    ``---`` marker. Prepends a new frontmatter block if none exists.
    """
    if not content.startswith("---\n"):
        lines = "\n".join(f"{k}: {v}" for k, v in fields.items())
        return f"---\n{lines}\n---\n{content}"

    result = content
    for key, value in fields.items():
        line = f"{key}: {value}"
        key_re = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
        if key_re.search(result):
            result = key_re.sub(line, result)
        else:
            # Insert before the closing --- of the frontmatter
            markers = list(_FM_FIELD_RE.finditer(result))
            if len(markers) >= 2:
                pos = markers[1].start()
                result = result[:pos] + f"{line}\n" + result[pos:]
    return result


def _migrate_content(content: str) -> tuple[str, list[str]]:
    """Rename relationship keys in frontmatter. Returns (updated_content, list_of_renames)."""
    fm = parse_frontmatter(content)
    if not fm:
        return content, []

    renames: list[str] = []
    result = content

    if "parent_issue" in fm:
        value = str(fm["parent_issue"])
        result = _set_fields(result, {"parent": value})
        result = _PARENT_ISSUE_RE.sub("", result)
        # Clean up blank line left by removal
        result = re.sub(r"\n{3,}", "\n\n", result)
        renames.append(f"parent_issue: {value!r} → parent: {value!r}")

    if "related" in fm:
        value_raw = _RELATED_RE.search(content)
        raw_suffix = value_raw.group(1) if value_raw else ""
        result = _set_fields(result, {"relates_to": fm["related"]})
        result = _RELATED_RE.sub("", result)
        result = re.sub(r"\n{3,}", "\n\n", result)
        renames.append(f"related:{raw_suffix} → relates_to:{raw_suffix}")

    return result, renames


def main_migrate_relationships() -> int:
    """Entry point for ll-migrate-relationships command.

    Renames parent_issue: -> parent: and related: -> relates_to: in all issue files.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    parser = argparse.ArgumentParser(
        prog="ll-migrate-relationships",
        description=(
            "Rename parent_issue: → parent: and related: → relates_to: "
            "in all issue frontmatter files. One-time migration for ENH-1431."
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

    issues_dir = repo_root / ".issues"
    if not issues_dir.exists():
        print(f"No .issues/ directory found at {repo_root}")
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
