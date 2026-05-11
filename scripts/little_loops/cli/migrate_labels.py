"""ll-migrate-labels: Move freeform ## Labels body sections to labels: frontmatter."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from little_loops.cli_args import add_config_arg, add_dry_run_arg
from little_loops.frontmatter import parse_frontmatter

_FM_FIELD_RE = re.compile(r"^---\s*$", re.MULTILINE)
_LABELS_SECTION_RE = re.compile(
    r"^## Labels\s*\n(.*?)(?=\n## |\Z)", re.MULTILINE | re.DOTALL
)


def _parse_body_labels(content: str) -> list[str]:
    """Extract backtick-wrapped labels from ## Labels body section."""
    match = _LABELS_SECTION_RE.search(content)
    if not match:
        return []
    return [m.lower() for m in re.findall(r"`([^`]+)`", match.group(1))]


def _set_labels_frontmatter(content: str, labels: list[str]) -> str:
    """Write labels: list field to frontmatter (avoids yaml roundtrip)."""
    if not content.startswith("---\n"):
        yaml_labels = "\n".join(f"- {lb}" for lb in labels)
        return f"---\nlabels:\n{yaml_labels}\n---\n{content}"

    labels_line = "labels:\n" + "\n".join(f"- {lb}" for lb in labels)
    key_re = re.compile(r"^labels:.*?(?=\n\S|\n---)", re.MULTILINE | re.DOTALL)
    if key_re.search(content):
        return key_re.sub(labels_line, content)

    # Insert before closing ---
    markers = list(_FM_FIELD_RE.finditer(content))
    if len(markers) >= 2:
        pos = markers[1].start()
        return content[:pos] + f"{labels_line}\n" + content[pos:]
    return content


def _remove_labels_section(content: str) -> str:
    """Remove ## Labels body section after migration."""
    result = _LABELS_SECTION_RE.sub("", content)
    # Clean up excessive blank lines left by removal
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def _migrate_content(content: str) -> tuple[str, list[str] | None]:
    """Migrate ## Labels body section to frontmatter labels: field.

    Returns:
        (updated_content, migrated_labels) — migrated_labels is None when no change needed.
    """
    fm = parse_frontmatter(content)

    body_labels = _parse_body_labels(content)
    if not body_labels:
        return content, None

    existing_fm_labels: list[str] = []
    raw = fm.get("labels")
    if raw:
        if isinstance(raw, list):
            existing_fm_labels = [str(lb) for lb in raw]
        else:
            existing_fm_labels = [lb.strip() for lb in str(raw).split(",") if lb.strip()]

    # Merge: keep frontmatter labels, add any body labels not already present
    merged = list(existing_fm_labels)
    for lb in body_labels:
        if lb not in merged:
            merged.append(lb)

    result = _set_labels_frontmatter(content, merged)
    result = _remove_labels_section(result)
    return result, merged


def main_migrate_labels() -> int:
    """Entry point for ll-migrate-labels command.

    Migrates freeform ## Labels body sections to labels: frontmatter in all issue files.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    parser = argparse.ArgumentParser(
        prog="ll-migrate-labels",
        description=(
            "Migrate freeform ## Labels body sections → labels: frontmatter "
            "in all issue files. One-time migration for ENH-1392."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run     # Preview all planned migrations (strongly advised first)
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

    migrated = 0
    errors: list[str] = []

    for file_path in sorted(issues_dir.rglob("*.md")):
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(str(file_path))
            print(f"  [ERROR] {file_path}: {exc}")
            continue

        updated, labels = _migrate_content(content)
        if labels is None:
            continue

        prefix = "[DRY RUN] " if dry_run else ""
        rel = file_path.relative_to(repo_root)
        print(f"  {prefix}MIGRATE {rel}: ## Labels → labels: {labels}")

        if not dry_run:
            try:
                file_path.write_text(updated, encoding="utf-8")
                migrated += 1
            except OSError as exc:
                errors.append(str(file_path))
                print(f"  [ERROR] {file_path}: {exc}")
        else:
            migrated += 1

    print()
    print(f"Results: {migrated} files {'would be ' if dry_run else ''}updated.")
    if errors:
        print(f"  Errors: {len(errors)}")
        return 1
    return 0
