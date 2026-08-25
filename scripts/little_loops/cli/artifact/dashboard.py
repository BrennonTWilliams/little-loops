"""``ll-artifact dashboard`` (FEAT-3304).

Exports a filtered, ENH-075-redacted snapshot of ``.ll/history.db`` as a
gzip+base64 blob embedded in a single self-contained HTML file, alongside an
inlined ``sql.js`` runtime, so a recipient with no repo access can open the file
over ``file://`` and run arbitrary read-only SQL against the snapshot with no
network access and no build step.

Export-time filtering is the only place data scope is decided (ENH-069), so the
column allowlist and the ``--since`` window are applied here, not in the page.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import html
import importlib.resources
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from little_loops.artifact_templates import (
    ArtifactTemplate,
    DataValidationError,
    ManifestError,
    load_manifest,
    render_template,
    validate_top_level_data,
)
from little_loops.logger import Logger
from little_loops.session_store.queries import (
    _EXPORT_TABLE_MAP,
    _SHAREABLE_ALLOWLIST_VERSION,
    _SHAREABLE_COLUMNS,
    _SHAREABLE_EXPORT_TYPES,
    build_snapshot_db,
)
from little_loops.session_store.schema import SCHEMA_VERSION

# D17: a 30-day snapshot holds ~150k usage_events rows; rendering them all would
# hang the tab. The page renders at most this many and states the true total.
RENDER_ROW_CAP = 500

_VENDOR_PARTS = ("assets", "vendor", "sql.js")


def _packaged_path(*parts: str) -> Path:
    """Resolve a packaged asset to a real Path (D20 — files() yields a Traversable)."""
    traversable = importlib.resources.files("little_loops")
    for part in parts:
        traversable = traversable.joinpath(part)
    return Path(str(traversable))


def parse_since(since: str) -> str:
    """Parse ``--since`` as ISO 8601 or ``YYYY-MM-DD`` (D4), returning ISO 8601.

    Matches ``ll-session export``'s established shape. No relative-duration
    (``30d``) parser exists in the package and building one is out of scope.
    """
    try:
        dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.strptime(since, "%Y-%m-%d")  # noqa: DTZ007 — date-only, naive by design
    return dt.isoformat()


def resolve_tables(tables_arg: str | None, local_mode: bool) -> list[str]:
    """Resolve ``--tables`` type names, enforcing the shareable-mode scope (D16/D22).

    Defaults to the shareable types (``loop_run,usage_event``) in both modes —
    never ``_EXPORT_DEFAULT_TABLES``, which is 20 types with no allowlist entry
    for 18 of them. In shareable mode ``--tables`` selects from the allowlist and
    cannot widen it; local mode accepts any export type (exported ``SELECT *``).
    """
    if tables_arg is None:
        return list(_SHAREABLE_EXPORT_TYPES)

    selected = [name.strip() for name in tables_arg.split(",") if name.strip()]
    if not selected:
        raise ValueError("--tables was given but selected no types")

    unknown = [name for name in selected if name not in _EXPORT_TABLE_MAP]
    if unknown:
        raise ValueError(
            f"unknown --tables type(s) {sorted(unknown)}; choices: {', '.join(_EXPORT_TABLE_MAP)}"
        )

    if not local_mode:
        widened = [
            name for name in selected if _EXPORT_TABLE_MAP[name][0] not in _SHAREABLE_COLUMNS
        ]
        if widened:
            raise ValueError(
                f"--tables cannot widen the shareable allowlist: {sorted(widened)} "
                f"{'has' if len(widened) == 1 else 'have'} no ENH-075 column allowlist. "
                f"Shareable types: {', '.join(_SHAREABLE_EXPORT_TYPES)}. "
                "Use --local to export unredacted data for personal use."
            )
    return selected


def schema_version_warning(source_version: str | None) -> str:
    """Build the export-time schema-divergence warning (D11), or "" when aligned.

    Divergence is detected here, never at view time: the artifact *contains* its
    snapshot, so once written there is nothing left for it to mismatch against —
    and D2's ``CREATE TABLE … AS SELECT`` does not copy the ``meta`` table that
    holds the version anyway.
    """
    if source_version is None:
        return (
            "The source history.db has no recorded schema_version. This snapshot's "
            f"column layout may not match the installed schema (v{SCHEMA_VERSION})."
        )
    if str(source_version) != str(SCHEMA_VERSION):
        return (
            f"Schema version mismatch at export time: the source history.db records "
            f"v{source_version} but the installed little-loops code is v{SCHEMA_VERSION}. "
            "Queries written against the current schema may not match this snapshot."
        )
    return ""


def cmd_dashboard(args: argparse.Namespace, logger: Logger) -> int:
    """Export a queryable history.db dashboard as a single self-contained HTML file.

    Returns 0 on success, 1 on error (unparseable ``--since``, a ``--tables``
    selection that would widen the shareable allowlist, a missing history.db, a
    snapshot or rendered page over ``artifacts.export.max_artifact_bytes``, or an
    invalid data payload / template).
    """
    from little_loops.config.core import BRConfig

    try:
        config = BRConfig(Path.cwd())
        export_cfg = config.artifacts.export
        mode = "local" if getattr(args, "local", False) else export_cfg.mode
        local_mode = mode == "local"
        max_bytes = export_cfg.max_artifact_bytes

        db_path = (
            Path(args.db)
            if getattr(args, "db", None)
            else config.project_root / ".ll" / "history.db"
        )
        if not db_path.is_file():
            logger.error(f"history database not found: {db_path}")
            return 1

        try:
            tables = resolve_tables(getattr(args, "tables", None), local_mode)
        except ValueError as exc:
            logger.error(str(exc))
            return 1

        since_iso: str | None = None
        if getattr(args, "since", None):
            try:
                since_iso = parse_since(args.since)
            except ValueError:
                logger.error(f"Invalid date: {args.since!r}. Use YYYY-MM-DD or ISO 8601.")
                return 1

        with tempfile.TemporaryDirectory(prefix="ll-dashboard-") as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.db"
            try:
                source_version = build_snapshot_db(
                    db_path,
                    snapshot_path,
                    tables=tables,
                    since=since_iso,
                    local_mode=local_mode,
                )
            except ValueError as exc:
                logger.error(str(exc))
                return 1

            # D16: the cheap pre-check. Without it the all-history path
            # materializes, gzips, base64-encodes and renders hundreds of MB
            # before the authoritative final-HTML ceiling (D7) fires.
            raw_size = snapshot_path.stat().st_size
            if raw_size > max_bytes:
                logger.error(
                    f"raw snapshot is {raw_size} bytes, over the "
                    f"artifacts.export.max_artifact_bytes limit of {max_bytes}. "
                    "Narrow the export window with --since."
                )
                return 1

            snapshot_b64 = base64.b64encode(gzip.compress(snapshot_path.read_bytes())).decode(
                "ascii"
            )

        wasm_b64 = base64.b64encode(
            _packaged_path(*_VENDOR_PARTS, "sql-wasm.wasm").read_bytes()
        ).decode("ascii")
        # The glue is UTF-8 text and rides in `data` verbatim rather than through
        # the template's assets/, which would mean a second copy of the vendored
        # file inside the package template tree for no gain (D10 says the assets/
        # route "may" be used, not "must").
        wasm_js = _packaged_path(*_VENDOR_PARTS, "sql-wasm.js").read_text(encoding="utf-8")

        root = _packaged_path("templates", "dashboard.llat")
        try:
            manifest = load_manifest(root)
        except ManifestError as exc:
            logger.error(str(exc))
            return 1
        template = ArtifactTemplate(root=root, manifest=manifest)

        # D18: autoescape=False, so every stamped value is escaped here. These
        # are all allowlisted or parsed already; escaping is the rule that has to
        # survive the next flag someone adds, not a fix for a live defect.
        data = {
            "snapshot_gzip_b64": snapshot_b64,
            "sql_wasm_b64": wasm_b64,
            "sql_wasm_js": wasm_js,
            "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "filter_tables": html.escape(", ".join(tables)),
            "filter_since": html.escape(since_iso) if since_iso else "all history",
            "export_mode": mode,
            "allowlist_version": _SHAREABLE_ALLOWLIST_VERSION,
            "source_schema_version": html.escape(str(source_version or "unknown")),
            "installed_schema_version": SCHEMA_VERSION,
            "schema_version_warning": html.escape(schema_version_warning(source_version)),
            "row_cap": RENDER_ROW_CAP,
        }

        try:
            validate_top_level_data(data, manifest["data_schema"])
        except DataValidationError as exc:
            logger.error(str(exc))
            return 1

        try:
            rendered = render_template(template, data, config)
        except (ManifestError, DataValidationError) as exc:
            logger.error(str(exc))
            return 1

        # D7: the authoritative ceiling, measured on the final HTML because that
        # is the quantity that actually bites the user. Hard-fail before write.
        rendered_size = len(rendered.encode("utf-8"))
        if rendered_size > max_bytes:
            logger.error(
                f"rendered dashboard is {rendered_size} bytes, over the "
                f"artifacts.export.max_artifact_bytes limit of {max_bytes}. "
                "Narrow the export window with --since. No file was written."
            )
            return 1

        output_dir = (
            Path(args.output)
            if getattr(args, "output", None)
            else Path(config.artifacts.promotion_dir)
        )
        if not output_dir.is_absolute():
            output_dir = config.project_root / output_dir
        if output_dir.is_file():
            logger.error(f"-o names an existing file, not a directory: {output_dir}")
            return 1
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / manifest["output"]
        out_path.write_text(rendered, encoding="utf-8")

        if data["schema_version_warning"]:
            logger.warning(schema_version_warning(source_version))
        logger.success(f"Wrote {out_path} ({rendered_size} bytes, mode={mode})")
        return 0
    except Exception as exc:  # noqa: BLE001 — surface any failure as exit 1
        logger.error(str(exc))
        return 1


def add_dashboard_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``dashboard`` subcommand parser."""
    dashboard = subparsers.add_parser(
        "dashboard",
        help="Export a queryable, self-contained history.db dashboard (embeds sql.js)",
    )
    dashboard.add_argument(
        "--tables",
        type=str,
        default=None,
        help=(
            "Comma-separated export types to embed (default: "
            f"{','.join(_SHAREABLE_EXPORT_TYPES)}). In the default shareable mode these "
            "are the only accepted types — --tables selects from the ENH-075 allowlist "
            "and cannot widen it. With --local, any ll-session export type is accepted "
            f"and types without an allowlist entry export all columns. Choices: "
            f"{', '.join(_EXPORT_TABLE_MAP)}"
        ),
    )
    dashboard.add_argument(
        "--since",
        type=str,
        default=None,
        help=(
            "Only embed rows at or after this timestamp (ISO 8601 or YYYY-MM-DD; no "
            "relative durations). No default — omitting it embeds all history, which on "
            "a large database will exceed artifacts.export.max_artifact_bytes. For loop "
            "runs the filter is COALESCE(ended_at, started_at), so a run that started "
            "inside the window is kept even if it is still in flight."
        ),
    )
    dashboard.add_argument(
        "--local",
        action="store_true",
        help=(
            "Export in local mode: no ENH-075 column projection, any export type "
            "selectable. Overrides artifacts.export.mode. The page is stamped "
            "'mode: local' so a recipient can tell — do not share the result."
        ),
    )
    dashboard.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to the history database (default: <project root>/.ll/history.db)",
    )
    dashboard.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help=(
            "Output directory (default: config.artifacts.promotion_dir). The filename "
            "comes from the packaged template's manifest: history-dashboard.html."
        ),
    )
