"""ll-loop rename: rename a loop YAML and rewrite all references."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from little_loops.fsm.loop_paths import get_builtin_loops_dir
from little_loops.logger import Logger


_KO_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_LOOP_REF_RE = re.compile(rf"(loop:\s+)([\w./-]+)")


@dataclass
class RenameReport:
    """Outcome of a rename-loop operation. Always populated, even in dry-run."""

    old: str
    new: str
    scope: str = "unknown"
    yaml_moved: bool = False
    yaml_name_updated: bool = False
    refs_rewritten: list[tuple[str, int]] = field(default_factory=list)
    dry_run: bool = True

    @property
    def changed(self) -> bool:
        return self.yaml_moved or self.yaml_name_updated or bool(self.refs_rewritten)


def _strip_yaml_ext(name: str) -> str:
    """Remove trailing `.yaml` if present."""
    return name[:-5] if name.endswith(".yaml") else name


def _resolve_loop(old: str, loops_dir: Path) -> tuple[Path, str] | None:
    """Find the loop YAML. Project scope (`.loops/<old>.yaml`) first, then builtin.

    Returns (path, scope) where scope is 'project' or 'builtin', or None if not found.
    """
    project = loops_dir / f"{old}.yaml"
    if project.exists():
        return project, "project"
    builtin = get_builtin_loops_dir() / f"{old}.yaml"
    if builtin.exists():
        return builtin, "builtin"
    return None


def _is_running(old: str, loops_dir: Path) -> bool:
    """True if any PID file in `.loops/.running/` matches `<old>-*.pid`."""
    running = loops_dir / ".running"
    if not running.exists():
        return False
    return any(p.name.startswith(f"{old}-") and p.suffix == ".pid" for p in running.iterdir())


def _search_paths(loops_dir: Path, scope: str) -> list[Path]:
    """Directories to walk for `loop:` ref rewrites.

    Convention (per `cli/loop/__init__.py`): `loops_dir` *is* the `.loops` directory.
    Project-scope loops live directly under it; builtin loops live under `loops/`.
    """
    paths: list[Path] = []
    if scope == "project":
        paths.append(loops_dir)
    paths.append(get_builtin_loops_dir())
    return [p for p in paths if p.exists()]


def _rewrite_loop_refs(
    paths: list[Path], old: str, new: str, dry_run: bool
) -> list[tuple[str, int]]:
    """Rewrite `loop: <old>` -> `loop: <new>` in-place. Returns touched (relpath, line)."""
    touched: list[tuple[str, int]] = []
    for base in paths:
        for path in sorted(base.rglob("*.yaml")):
            try:
                text = path.read_text()
            except OSError:
                continue
            lines = text.splitlines()
            changed = False
            new_lines = []
            for i, line in enumerate(lines, start=1):
                m = _LOOP_REF_RE.search(line)
                if m and m.group(2) == old:
                    new_lines.append(f"{m.group(1)}{new}")
                    touched.append((str(path.relative_to(base.parent.parent)), i))
                    changed = True
                else:
                    new_lines.append(line)
            if changed and not dry_run:
                path.write_text("\n".join(new_lines) + "\n")
    return touched


def _update_yaml_name_field(yaml_path: Path, old: str, new: str, dry_run: bool) -> bool:
    """Update the top-level `name:` field in the renamed YAML."""
    try:
        text = yaml_path.read_text()
    except OSError:
        return False
    pattern = re.compile(rf'^(name:\s*)(["\']?){re.escape(old)}\2(\s*)$', re.MULTILINE)
    new_text, count = pattern.subn(rf"\g<1>\g<2>{new}\g<2>\g<3>", text, count=1)
    if count > 0 and not dry_run:
        yaml_path.write_text(new_text)
    return count > 0


def rename_loop(
    old: str,
    new: str,
    *,
    dry_run: bool = True,
    loops_dir: Path,
) -> RenameReport:
    """Pure logic: validate, collect changes, apply (or not in dry-run)."""
    report = RenameReport(old=old, new=new, dry_run=dry_run)

    if not _KO_RE.match(new):
        raise ValueError(
            f"Invalid loop name: {new!r} (expected kebab-case: lowercase letters, digits, hyphens)"
        )
    if old == new:
        raise ValueError(f"Old and new loop names are identical: {old!r}")

    resolved = _resolve_loop(old, loops_dir)
    if resolved is None:
        raise FileNotFoundError(
            f"Loop not found: {old!r} (checked .loops/{old}.yaml and "
            f"scripts/little_loops/loops/{old}.yaml)"
        )
    src, scope = resolved
    report.scope = scope

    dest = src.parent / f"{new}.yaml"
    if dest.exists():
        raise FileExistsError(
            f"Destination loop already exists at {dest}. Remove or rename it first."
        )
    if _is_running(old, loops_dir):
        raise RuntimeError(
            f"Loop {old!r} appears to be running (PID file in .loops/.running/). "
            f"Stop it first: ll-loop stop {old}"
        )

    # Move the YAML: git mv for built-in scope, plain mv for project.
    if not dry_run:
        if scope == "builtin":
            subprocess.run(
                ["git", "mv", str(src), str(dest)], check=True
            )
        else:
            shutil.move(str(src), str(dest))
    report.yaml_moved = True

    # Update the `name:` field in the renamed file (best-effort).
    report.yaml_name_updated = _update_yaml_name_field(dest, old, new, dry_run)

    # Rewrite `loop: <old>` references across loop YAMLs.
    search_paths = _search_paths(loops_dir, scope)
    report.refs_rewritten = _rewrite_loop_refs(search_paths, old, new, dry_run)

    return report


def cmd_rename(args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int:
    """CLI entry point for `ll-loop rename`."""
    old = _strip_yaml_ext(args.old)
    new = _strip_yaml_ext(args.new)
    try:
        report = rename_loop(old, new, dry_run=args.dry_run, loops_dir=loops_dir)
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as e:
        logger.error(str(e))
        return 1

    verb = "would" if report.dry_run else "applied"
    logger.success(f"Rename {verb}: {old} -> {new}  [scope: {report.scope}]")
    if report.yaml_moved:
        verb2 = "would move" if report.dry_run else "moved"
        logger.info(
            f"  YAML {verb2}: {(loops_dir if report.scope == 'project' else get_builtin_loops_dir())}/{old}.yaml "
            f"-> {new}.yaml"
        )
    if report.yaml_name_updated:
        logger.info(f"  YAML name field {verb} updated: '{old}' -> '{new}'")
    if report.refs_rewritten:
        logger.info(f"  Loop references {verb} updated: {len(report.refs_rewritten)} occurrence(s)")
        for rel, line in report.refs_rewritten:
            logger.info(f"    {rel}:{line}")
    if report.dry_run:
        logger.info("No changes applied (--dry-run).")
    return 0
