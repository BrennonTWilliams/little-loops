"""``ll-artifact extract`` and ``ll-artifact refresh`` (FEAT-3310, Phase 2).

``extract`` is the LLM step: source document -> ``data.json``, mapped per
the manifest's ``data_schema`` + ``extraction.prompt`` and validated before
being considered successful. ``refresh`` composes ``extract`` + ``render``
against the manifest's bound ``source`` by default, then records the
render in ``<template>.llat.lock`` (FEAT-3311 owns the reader).

Both verbs live in this one module — a deliberate exception to
``cli/artifact/__init__.py``'s "one module per subcommand" convention,
since ``refresh`` is a thin compose over ``extract`` + ``render`` with no
independent logic of its own.

This is the only module on the ``extract``/``refresh`` call path that
imports ``host_runner`` — ``artifact_templates.py`` and ``render.py`` are
forbidden from doing so (their own module docstrings), mirroring
``discover.py``'s equivalent role for ``templatize``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.artifact_templates import (
    ArtifactTemplate,
    DataValidationError,
    ManifestError,
    TemplateResolutionError,
    load_manifest,
    resolve_template,
    validate_top_level_data,
)
from little_loops.cli.artifact.lockfile import lock_path_for, relativize_path, write_lockfile
from little_loops.cli.artifact.render import OutputPathError, render_to_disk
from little_loops.fsm.schema import DEFAULT_LLM_MODEL
from little_loops.host_runner import BlockingJsonError, resolve_host, run_blocking_json
from little_loops.logger import Logger

_DEFAULT_TIMEOUT_SECONDS = 180

# Composes what to extract (author-supplied) with the shape to return it in
# (the manifest's data_schema) and the material (the source text) —
# mirroring discover.py's _PROMPT_TEMPLATE shape. `extraction.prompt` is
# never used as the entire prompt: every template author would otherwise
# have to hand-inline their own data_schema and keep it in sync.
_PROMPT_TEMPLATE = """{extraction_prompt}

Return a JSON object matching this schema exactly:
{data_schema}

Source document:
{source_text}
"""


class ExtractError(ValueError):
    """Raised on any `extract`/`refresh` domain failure — always fail-loud, never a fallback."""


def _resolve_model(cli_model: str | None, extraction: dict[str, Any]) -> str:
    """`--model` > `manifest.extraction.model` > `fsm.schema.DEFAULT_LLM_MODEL`."""
    if cli_model:
        return cli_model
    manifest_model = extraction.get("model")
    if manifest_model:
        return str(manifest_model)
    return DEFAULT_LLM_MODEL


def _resolve_data_path(cli_data: str | None, root: Path, config: Any) -> Path:
    """`--data` resolves relative paths against the project root, exactly as `cmd_render` does."""
    data_path = Path(cli_data) if cli_data else root / "data.json"
    if not data_path.is_absolute():
        data_path = config.project_root / data_path
    return data_path


def _resolve_default_source(manifest: dict[str, Any], config: Any, template_name: str) -> Path:
    """Resolve `refresh`'s default source from the manifest's scalar `source`.

    Project-root-relative if not absolute (never cwd-relative). Fails loud
    naming the resolved absolute path if it does not exist.
    """
    source = manifest.get("source")
    if not source:
        raise ExtractError(
            f"{template_name}: manifest has no 'source' and no <source-file> was given"
        )
    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = config.project_root / source_path
    if not source_path.is_file():
        raise ExtractError(f"source does not exist: {source_path}")
    return source_path


def extract_data(
    template: ArtifactTemplate,
    source_path: Path,
    config: Any,
    *,
    model: str | None,
    timeout: int,
) -> tuple[dict[str, Any], bytes]:
    """Run the LLM extraction call and validate the result against `data_schema`.

    Returns ``(data, source_bytes)`` — *source_bytes* is exactly what was
    fed into the prompt, so ``cmd_refresh`` can hash the same bytes it
    rendered from, rather than re-reading the file (a TOCTOU window a
    source edited mid-refresh could open).

    Raises ExtractError on: no usable `extraction.prompt`, an unreadable or
    undecodable source, a source over the configured size ceiling, any
    host-call failure, or a response that fails schema validation. No
    partial write results from this function — it never touches disk.
    """
    extraction = template.manifest.get("extraction") or {}
    prompt_fragment = extraction.get("prompt")
    if not prompt_fragment:
        raise ExtractError(
            f"{template.name}: manifest has no extraction.prompt — extract cannot run without "
            "one (templatize-produced manifests need a hand-added prompt before extract works "
            "on them)"
        )

    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise ExtractError(f"{source_path}: could not read source document: {exc}") from exc

    max_input_bytes = config.artifacts.templatize_max_input_bytes
    if len(source_bytes) > max_input_bytes:
        raise ExtractError(
            f"source document ({len(source_bytes)} bytes) exceeds "
            f"artifacts.templatize_max_input_bytes ({max_input_bytes}) — no extraction call issued"
        )

    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractError(
            f"{source_path}: could not decode source document as UTF-8: {exc}"
        ) from exc

    data_schema = template.data_schema
    resolved_model = _resolve_model(model, extraction)
    prompt = _PROMPT_TEMPLATE.format(
        extraction_prompt=prompt_fragment,
        data_schema=json.dumps(data_schema, indent=2, ensure_ascii=False),
        source_text=source_text,
    )

    # extraction.host is diagnostic only — resolve_host()'s ambient
    # selection is never overridden, so a manifest committed on one
    # machine cannot silently redirect another machine's host.
    runner = resolve_host()
    invocation = runner.build_blocking_json(
        prompt=prompt, model=resolved_model, json_schema=data_schema
    )
    try:
        raw = run_blocking_json(invocation, timeout=timeout)
    except BlockingJsonError as exc:
        raise ExtractError(f"extraction call failed: {exc}") from exc

    if raw is None:
        raise ExtractError("extraction response was empty")

    # json_schema enforcement is host-dependent (Claude Code drops it
    # silently; Codex materializes it) — this validation is the only
    # guarantee on the Claude Code path, not defense in depth.
    try:
        validate_top_level_data(raw, data_schema)
    except DataValidationError as exc:
        raise ExtractError(f"extraction response failed schema validation: {exc}") from exc

    return raw, source_bytes


def cmd_extract(args: argparse.Namespace, logger: Logger) -> int:
    """LLM extraction: source document -> `data.json`, schema-checked.

    Returns 0 on success, 1 on error (unresolvable template, invalid
    manifest, missing/oversized/undecodable source, no usable
    `extraction.prompt`, host-call failure, or a schema-invalid response).
    No partial write: a validation failure leaves `data.json` untouched.
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

        template = ArtifactTemplate(root=root, manifest=manifest)

        source_path = Path(args.source)
        if not source_path.is_file():
            logger.error(f"source not found: {source_path}")
            return 1

        try:
            data, _source_bytes = extract_data(
                template, source_path, config, model=args.model, timeout=args.timeout
            )
        except ExtractError as exc:
            logger.error(str(exc))
            return 1

        data_path = _resolve_data_path(args.data, root, config)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.success(f"Wrote {data_path}")
        return 0
    except Exception as exc:  # noqa: BLE001 — surface any failure as exit 1
        logger.error(str(exc))
        return 1


def cmd_refresh(args: argparse.Namespace, logger: Logger) -> int:
    """Compose `extract` + `render` against the template's bound source, then lock it.

    Defaults the source file to the manifest's scalar `source`
    (project-root-relative if not absolute) when no `<source-file>` is
    given. Writes/updates `<template>.llat.lock` only after the render's
    output-file write succeeds — a lock-write failure after a successful
    render is still an exit-1 failure, but the error message says the
    render succeeded and only the lock write failed, so the user does not
    re-pay for an LLM call to fix a filesystem problem.
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

        template = ArtifactTemplate(root=root, manifest=manifest)

        if args.source:
            source_path = Path(args.source)
            if not source_path.is_file():
                logger.error(f"source not found: {source_path}")
                return 1
        else:
            try:
                source_path = _resolve_default_source(manifest, config, template.name)
            except ExtractError as exc:
                logger.error(str(exc))
                return 1

        try:
            data, source_bytes = extract_data(
                template, source_path, config, model=args.model, timeout=args.timeout
            )
        except ExtractError as exc:
            logger.error(str(exc))
            return 1

        data_path = _resolve_data_path(args.data, root, config)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        try:
            out_path = render_to_disk(template, data, config, args.output)
        except OutputPathError as exc:
            logger.error(str(exc))
            return 1
        except (ManifestError, DataValidationError) as exc:
            logger.error(str(exc))
            return 1

        source_key = relativize_path(source_path, config.project_root)
        output_key = relativize_path(out_path, config.project_root)
        sha256 = hashlib.sha256(source_bytes).hexdigest()
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
        except Exception as exc:  # noqa: BLE001 — filesystem failure, distinct message required
            logger.error(f"render succeeded ({out_path}) but writing the lockfile failed: {exc}")
            return 1

        logger.success(f"Wrote {out_path}")
        return 0
    except Exception as exc:  # noqa: BLE001 — surface any failure as exit 1
        logger.error(str(exc))
        return 1


def add_extract_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``extract`` subcommand parser."""
    extract = subparsers.add_parser(
        "extract",
        help="LLM extraction: source document -> data.json, schema-checked",
    )
    extract.add_argument(
        "template",
        type=str,
        help="Path to a .llat/ directory, or a name under config.artifacts.templates_dir",
    )
    extract.add_argument(
        "source",
        type=str,
        help="Path to the source document to extract from",
    )
    extract.add_argument(
        "--data",
        type=str,
        default=None,
        help="Path to write data.json (default: <template>/data.json); "
        "relative paths resolve against the project root",
    )
    extract.add_argument(
        "--model",
        type=str,
        default=None,
        help="LLM model for the extraction call "
        "(default: manifest.extraction.model, else the fsm default model)",
    )
    extract.add_argument(
        "--timeout",
        type=int,
        default=_DEFAULT_TIMEOUT_SECONDS,
        help=f"Host call timeout in seconds (default: {_DEFAULT_TIMEOUT_SECONDS})",
    )


def add_refresh_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``refresh`` subcommand parser."""
    refresh = subparsers.add_parser(
        "refresh",
        help="extract + render composed against the template's bound source",
    )
    refresh.add_argument(
        "template",
        type=str,
        help="Path to a .llat/ directory, or a name under config.artifacts.templates_dir",
    )
    refresh.add_argument(
        "source",
        type=str,
        nargs="?",
        default=None,
        help="Source document (default: the manifest's bound 'source')",
    )
    refresh.add_argument(
        "--data",
        type=str,
        default=None,
        help="Path to write data.json (default: <template>/data.json); "
        "relative paths resolve against the project root",
    )
    refresh.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output directory for the rendered artifact "
        "(default: config.artifacts.default_output_dir)",
    )
    refresh.add_argument(
        "--model",
        type=str,
        default=None,
        help="LLM model for the extraction call "
        "(default: manifest.extraction.model, else the fsm default model)",
    )
    refresh.add_argument(
        "--timeout",
        type=int,
        default=_DEFAULT_TIMEOUT_SECONDS,
        help=f"Host call timeout in seconds (default: {_DEFAULT_TIMEOUT_SECONDS})",
    )
