"""``ll-artifact status`` (FEAT-3311 Phase 3): lockfile staleness detection.

Reads each resolved template's ``<template>.llat.lock`` (FEAT-3310's
``cli/artifact/lockfile.py``) and compares the recorded source sha256
against the source's current content, reporting a five-state
classification per ``(template, source)`` pair: FRESH / STALE /
SOURCE-MISSING / OUTPUT-MISSING / NO-LOCK. Never writes a lockfile itself —
``refresh`` (FEAT-3310) and ``render --source`` are the only writers.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from little_loops.artifact_templates import TemplateResolutionError, resolve_template
from little_loops.cli.artifact.lockfile import (
    LockfileError,
    load_lockfile,
    lock_path_for,
    resolve_stored_path,
)
from little_loops.logger import Logger

State = Literal["FRESH", "STALE", "SOURCE-MISSING", "OUTPUT-MISSING", "NO-LOCK"]


@dataclass(frozen=True)
class StatusResult:
    """One reported `(template, source)` classification, or a template-level NO-LOCK."""

    template: str
    source: str | None
    state: State


def _sha256_file(path: Path) -> str | None:
    """Return the hex sha256 of *path*'s bytes, or None if it cannot be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _resolve_stored(stored: str, project_root: Path) -> Path:
    """A `renders` key or `output` value: absolute as-is, else against project_root, never cwd."""
    if os.path.isabs(stored):
        return Path(stored)
    return resolve_stored_path(stored, project_root)


def _classify_entries(template_name: str, renders: dict, project_root: Path) -> list[StatusResult]:
    """Classify every `(template, source)` pair in *renders*, first-match-wins.

    Order: SOURCE-MISSING -> STALE -> OUTPUT-MISSING -> FRESH.
    """
    results: list[StatusResult] = []
    for source_key, entry in renders.items():
        source_path = _resolve_stored(source_key, project_root)
        recorded_sha256 = entry.get("sha256")
        output_key = entry.get("output")

        if not source_path.is_file():
            results.append(StatusResult(template_name, source_key, "SOURCE-MISSING"))
            continue

        current_sha256 = _sha256_file(source_path)
        if current_sha256 != recorded_sha256:
            results.append(StatusResult(template_name, source_key, "STALE"))
            continue

        output_path = _resolve_stored(output_key, project_root) if output_key else None
        if output_path is None or not output_path.is_file():
            results.append(StatusResult(template_name, source_key, "OUTPUT-MISSING"))
            continue

        results.append(StatusResult(template_name, source_key, "FRESH"))

    return results


def _status_for_template(root: Path, project_root: Path) -> list[StatusResult]:
    """Return the classification for one resolved template root.

    Raises LockfileError if the lockfile exists but fails validation.
    """
    template_name = root.name
    lock_path = lock_path_for(root)
    data = load_lockfile(lock_path)
    renders = data.get("renders", {})

    if not lock_path.is_file() or not renders:
        return [StatusResult(template_name, None, "NO-LOCK")]

    return _classify_entries(template_name, renders, project_root)


def _discover_templates(templates_dir: Path) -> list[Path]:
    """Enumerate `.llat/` templates under *templates_dir* that have a lockfile sibling."""
    if not templates_dir.is_dir():
        return []
    discovered = []
    for candidate in sorted(templates_dir.glob("*.llat")):
        if candidate.is_dir() and lock_path_for(candidate).is_file():
            discovered.append(candidate)
    return discovered


def _exit_code_for(results: list[StatusResult]) -> int:
    """0 only if every reported item is FRESH; an empty report is vacuously all-FRESH."""
    has_non_fresh = any(r.state != "FRESH" for r in results)
    return 1 if has_non_fresh else 0


def cmd_status(args: argparse.Namespace, logger: Logger) -> int:
    """Report staleness for each named `<template>`, or discover all tracked templates.

    Returns 0 if every reported `(template, source)` pair is FRESH (or the
    report is empty), 1 otherwise — including NO-LOCK, SOURCE-MISSING,
    STALE, OUTPUT-MISSING, an unresolvable template, or a malformed
    lockfile (`LockfileError`).
    """
    from little_loops.config.core import BRConfig

    try:
        config = BRConfig(Path.cwd())
        templates_dir = config.project_root / config.artifacts.templates_dir

        results: list[StatusResult] = []
        templates: list[str] = getattr(args, "template", None) or []

        if templates:
            roots: list[Path] = []
            for template_arg in templates:
                try:
                    roots.append(resolve_template(template_arg, templates_dir))
                except TemplateResolutionError as exc:
                    logger.error(str(exc))
                    return 1
        else:
            roots = _discover_templates(templates_dir)
            if not roots:
                logger.info(f"no templates with a lockfile found under {templates_dir}")

        try:
            for root in roots:
                results.extend(_status_for_template(root, config.project_root))
        except LockfileError as exc:
            logger.error(str(exc))
            return 1

        for result in results:
            if result.source is None:
                logger.info(f"{result.template}: {result.state}")
            else:
                logger.info(f"{result.template} :: {result.source}: {result.state}")

        return _exit_code_for(results)
    except Exception as exc:  # noqa: BLE001 — surface any failure as exit 1
        logger.error(str(exc))
        return 1


def add_status_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``status`` subcommand parser."""
    status = subparsers.add_parser(
        "status",
        help="Lockfile staleness detection: FRESH/STALE/SOURCE-MISSING/OUTPUT-MISSING/NO-LOCK",
    )
    status.add_argument(
        "template",
        type=str,
        nargs="*",
        help="Template(s) to check (path or name under config.artifacts.templates_dir). "
        "Omit to discover every lockfile-bearing template under templates_dir.",
    )
