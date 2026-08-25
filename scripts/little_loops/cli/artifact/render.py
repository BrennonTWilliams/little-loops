"""``ll-artifact render`` (FEAT-3036 Phase 1).

Deterministic stamp: ``template + data.json -> artifact``. No LLM call.
Validates ``data.json`` against the template's ``manifest.data_schema``
before rendering. An opt-in ``--source <path>`` (FEAT-3311) asserts "this
data.json came from this file" and writes a `<template>.llat.lock` entry
after the render; bare ``render`` (no ``--source``) never touches a
lockfile and stays byte-for-byte the Phase-1 stamp it always was.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from little_loops.artifact_templates import (
    ArtifactTemplate,
    DataValidationError,
    ManifestError,
    TemplateResolutionError,
    load_data,
    load_manifest,
    render_template,
    resolve_template,
    validate_top_level_data,
)
from little_loops.logger import Logger


class OutputPathError(ValueError):
    """Raised when the resolved output path names an existing file, not a directory."""


def render_to_disk(
    template: ArtifactTemplate,
    data: dict,
    config: object,
    output: str | None,
) -> Path:
    """Render *template* against *data* and write it under the resolved output directory.

    Holds the ``-o`` resolution / existing-file guard / ``mkdir`` / write
    sequence that used to live inline in ``cmd_render`` — the single home
    for it, so ``cmd_refresh`` (FEAT-3310) and FEAT-3311's ``render
    --source`` can record the same path in the lockfile's ``output`` field
    without re-deriving it.

    Returns the written file's path. Raises OutputPathError if the
    resolved output directory names an existing file, or
    ManifestError/DataValidationError on a render failure (unchanged from
    ``render_template``).
    """
    from little_loops.config.core import BRConfig

    assert isinstance(config, BRConfig)
    output_dir = Path(output) if output else Path(config.artifacts.default_output_dir)
    if not output_dir.is_absolute():
        output_dir = config.project_root / output_dir
    if output_dir.is_file():
        raise OutputPathError(f"-o names an existing file, not a directory: {output_dir}")

    rendered = render_template(template, data, config)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / template.manifest["output"]
    out_path.write_text(rendered, encoding="utf-8")
    return out_path


def cmd_render(args: argparse.Namespace, logger: Logger) -> int:
    """Render an artifact template against a data file.

    Returns 0 on success, 1 on error (unresolvable template, invalid
    manifest, missing/malformed/schema-invalid data, an existing file at
    the resolved ``-o`` output directory, a ``--source`` that does not
    resolve to an existing file, or — with ``--source`` — a lockfile-write
    failure after a successful render).
    """
    from little_loops.config.core import BRConfig

    try:
        config = BRConfig(Path.cwd())
        templates_dir = config.project_root / config.artifacts.templates_dir

        try:
            root = resolve_template(args.template, templates_dir)
        except TemplateResolutionError as exc:
            logger.error(str(exc))
            return 1

        source_arg = getattr(args, "source", None)
        source_path: Path | None = None
        if source_arg:
            source_path = Path(source_arg)
            if not source_path.is_absolute():
                source_path = config.project_root / source_path
            source_path = source_path.resolve()
            if not source_path.is_file():
                logger.error(f"--source does not exist: {source_path}")
                return 1

        try:
            manifest = load_manifest(root)
        except ManifestError as exc:
            logger.error(str(exc))
            return 1

        data_path = Path(args.data) if args.data else root / "data.json"
        if not data_path.is_absolute():
            data_path = config.project_root / data_path
        if not data_path.is_file():
            logger.error(f"data file not found: {data_path}")
            return 1

        try:
            data = load_data(data_path)
            validate_top_level_data(data, manifest["data_schema"])
        except DataValidationError as exc:
            logger.error(str(exc))
            return 1

        template = ArtifactTemplate(root=root, manifest=manifest)
        try:
            out_path = render_to_disk(template, data, config, args.output)
        except OutputPathError as exc:
            logger.error(str(exc))
            return 1
        except (ManifestError, DataValidationError) as exc:
            logger.error(str(exc))
            return 1

        if source_path is not None:
            from little_loops.cli.artifact.lockfile import (
                lock_path_for,
                relativize_path,
                write_lockfile,
            )

            source_key = relativize_path(source_path, config.project_root)
            output_key = relativize_path(out_path, config.project_root)
            sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
            rendered_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

            lock_path = lock_path_for(root)
            try:
                write_lockfile(
                    lock_path,
                    {
                        source_key: {
                            "sha256": sha256,
                            "rendered_at": rendered_at,
                            "output": output_key,
                        }
                    },
                )
            except Exception as exc:  # noqa: BLE001 — filesystem failure, distinct message
                logger.error(
                    f"render succeeded ({out_path}) but writing the lockfile failed: {exc}"
                )
                return 1

        logger.success(f"Wrote {out_path}")
        return 0
    except Exception as exc:  # noqa: BLE001 — surface any failure as exit 1
        logger.error(str(exc))
        return 1


def add_render_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``render`` subcommand parser."""
    render = subparsers.add_parser(
        "render",
        help="Deterministic template + data.json -> artifact stamp (no LLM call)",
    )
    render.add_argument(
        "template",
        type=str,
        help="Path to a .llat/ directory, or a name under config.artifacts.templates_dir",
    )
    render.add_argument(
        "--data",
        type=str,
        default=None,
        help="Path to data.json (default: <template>/data.json)",
    )
    render.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output directory (default: config.artifacts.default_output_dir)",
    )
    render.add_argument(
        "--source",
        type=str,
        default=None,
        help="Path to the source document this data.json came from. When given, writes/updates "
        "<template>.llat.lock recording the source's sha256 and the rendered output path "
        "(FEAT-3311). Must resolve to an existing file, checked before the render. Omit to "
        "render without touching any lockfile (Phase 1 behavior, unchanged).",
    )
