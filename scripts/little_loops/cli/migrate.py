"""ll-migrate: One-time migration of completed/deferred issues to type-based directories."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import warnings
from pathlib import Path

from little_loops.cli_args import add_config_arg, add_dry_run_arg
from little_loops.frontmatter import parse_frontmatter
from little_loops.issue_lifecycle import _is_git_tracked
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

_FILENAME_PREFIX_RE = re.compile(r"^(?:P\d+-)?([A-Z]+)-\d+")
_FM_FIELD_RE = re.compile(r"^---\s*$", re.MULTILINE)


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
                # markers[0] is opening ---, markers[1] is closing ---
                pos = markers[1].start()
                result = result[:pos] + f"{line}\n" + result[pos:]
    return result


def _extract_prefix_from_filename(name: str) -> str | None:
    """Extract issue type prefix from filename (e.g. 'P2-ENH-1420-...' → 'ENH')."""
    m = _FILENAME_PREFIX_RE.match(name)
    return m.group(1) if m else None


def _get_git_completion_date(file_path: Path) -> str | None:
    """Return ISO-8601 date from git log for file_path, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%as", "-1", "--", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            date_str = result.stdout.strip()
            if date_str:
                return f"{date_str}T00:00:00Z"
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _move_file(src: Path, dst: Path, updated_content: str) -> None:
    """Move src to dst, writing updated_content. Prefers git mv for tracked files."""
    if _is_git_tracked(src):
        result = subprocess.run(
            ["git", "mv", str(src), str(dst)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            dst.write_text(updated_content, encoding="utf-8")
            return
    # Untracked or git mv failed — write then rename
    src.write_text(updated_content, encoding="utf-8")
    src.rename(dst)


def main_migrate() -> int:
    """Entry point for ll-migrate command.

    Moves files from completed/ and deferred/ into their type-based directories,
    backfills completed_at for completed files missing it, and sets correct status
    frontmatter.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-migrate", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-migrate",
            description=(
                "Migrate completed/ and deferred/ issues to type-based directories "
                "with correct status frontmatter. One-time migration for ENH-1390."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s --dry-run     # Preview all planned moves (strongly advised first)
  %(prog)s               # Execute migration
""",
        )
        add_dry_run_arg(parser)
        add_config_arg(parser)
        args = parser.parse_args()

        dry_run: bool = args.dry_run
        repo_root: Path = args.config or Path.cwd()

        from little_loops.config import BRConfig

        config = BRConfig(repo_root)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            completed_dir: Path = config.get_completed_dir()
            deferred_dir: Path = config.get_deferred_dir()

        # Build prefix → category-key mapping (e.g. "BUG" → "bugs")
        prefix_to_key: dict[str, str] = {
            cat.prefix.upper(): key for key, cat in config._issues.categories.items()
        }

        if dry_run:
            print("[DRY RUN] No files will be moved or modified.")

        moved = 0
        backfilled = 0
        untyped: list[str] = []
        errors: list[str] = []

        sources: list[tuple[Path, str]] = []
        if completed_dir.exists():
            sources += [(f, "done") for f in sorted(completed_dir.glob("*.md"))]
        if deferred_dir.exists():
            sources += [(f, "deferred") for f in sorted(deferred_dir.glob("*.md"))]

        for file_path, status in sources:
            content = file_path.read_text(encoding="utf-8")
            fm = parse_frontmatter(content)

            updates: dict[str, str | int] = {"status": status}

            if status == "done" and "completed_at" not in fm:
                date = _get_git_completion_date(file_path)
                if date:
                    updates["completed_at"] = date
                backfilled += 1

            # Determine type prefix from frontmatter or filename
            type_prefix: str | None = fm.get("type") if fm else None
            if not type_prefix:
                type_prefix = _extract_prefix_from_filename(file_path.name)

            if not type_prefix:
                untyped.append(str(file_path))
                print(f"  [UNTYPED] {file_path.name} — cannot determine type, skipped")
                continue

            category_key = prefix_to_key.get(type_prefix.upper())
            if category_key is None:
                untyped.append(str(file_path))
                print(f"  [UNTYPED] {file_path.name} — unknown prefix '{type_prefix}', skipped")
                continue

            target_dir = config.get_issue_dir(category_key)
            target_path = target_dir / file_path.name

            if target_path.exists():
                errors.append(str(file_path))
                print(f"  [SKIP] {file_path.name} — target already exists: {target_path}")
                continue

            updated_content = _set_fields(content, {k: str(v) for k, v in updates.items()})

            prefix = "[DRY RUN] " if dry_run else ""
            print(
                f"  {prefix}MOVE {file_path.relative_to(repo_root)} → {target_path.relative_to(repo_root)}"
            )

            if not dry_run:
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    _move_file(file_path, target_path, updated_content)
                    moved += 1
                except Exception as exc:
                    errors.append(str(file_path))
                    print(f"  [ERROR] {file_path.name}: {exc}")
            else:
                moved += 1

        print()
        print(
            f"Results: {moved} files {'would be ' if dry_run else ''}moved, "
            f"{backfilled} completed_at fields backfilled."
        )
        if untyped:
            print(f"  Untyped (needs manual review): {len(untyped)}")
            for p in untyped:
                print(f"    {p}")
        if errors:
            print(f"  Errors: {len(errors)}")
            return 1
        return 0
