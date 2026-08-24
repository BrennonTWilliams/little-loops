"""``ll-artifact render`` (FEAT-3036 Phase 1).

Deterministic stamp: ``template + data.json -> artifact``. No LLM call.
Validates ``data.json`` against the template's ``manifest.data_schema``
before rendering.
"""

from __future__ import annotations

import argparse
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


def cmd_render(args: argparse.Namespace, logger: Logger) -> int:
    """Render an artifact template against a data file.

    Returns 0 on success, 1 on error (unresolvable template, invalid
    manifest, missing/malformed/schema-invalid data, or an existing file at
    the resolved ``-o`` output directory).
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
            rendered = render_template(template, data, config)
        except (ManifestError, DataValidationError) as exc:
            logger.error(str(exc))
            return 1

        output_dir = Path(args.output) if args.output else Path(config.artifacts.default_output_dir)
        if not output_dir.is_absolute():
            output_dir = config.project_root / output_dir
        if output_dir.is_file():
            logger.error(f"-o names an existing file, not a directory: {output_dir}")
            return 1

        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / manifest["output"]
        out_path.write_text(rendered, encoding="utf-8")

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
