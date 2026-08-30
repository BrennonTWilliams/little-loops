"""``ll-artifact dashboard`` — sql.js + filtered history.db export (FEAT-3304).

Covers the issue's 19 acceptance criteria. The load-bearing one is the
round-trip: pull the base64 blob back out of the generated HTML, gunzip it,
open it as a SQLite database and assert on its *schema* that excluded
columns/tables are absent — an assert-absent substring check is not sufficient,
and no prior test in this repo decodes an embedded blob back out of an artifact.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.artifact_templates import (
    DataValidationError,
    load_manifest,
    validate_top_level_data,
)
from little_loops.cli.artifact.dashboard import (
    RENDER_ROW_CAP,
    RenderedDashboard,
    ServeContext,
    _packaged_path,
    build_dashboard_html,
    cmd_dashboard,
    parse_since,
    render_live_fragment,
    resolve_tables,
    schema_version_warning,
)
from little_loops.logger import Logger
from little_loops.package_data import PACKAGE_DATA_ASSETS, check_asset_accessible
from little_loops.session_store.queries import (
    _EXPORT_DEFAULT_TABLES,
    _SHAREABLE_ALLOWLIST_VERSION,
    _SHAREABLE_COLUMNS,
    _SHAREABLE_EXPORT_TYPES,
    build_snapshot_db,
)
from little_loops.session_store.schema import SCHEMA_VERSION

VENDOR_DIR = Path(__file__).parent.parent / "little_loops" / "assets" / "vendor" / "sql.js"
VENDOR_HTMX_DIR = Path(__file__).parent.parent / "little_loops" / "assets" / "vendor" / "htmx"
DASHBOARD_PY = Path(__file__).parent.parent / "little_loops" / "cli" / "artifact" / "dashboard.py"
QUERIES_PY = Path(__file__).parent.parent / "little_loops" / "session_store" / "queries.py"
SCHEMA_JSON = Path(__file__).parent.parent / "little_loops" / "config-schema.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_history_db(path: Path, *, schema_version: str = str(SCHEMA_VERSION)) -> None:
    """Build a synthetic history.db shaped like the real one.

    Deliberately not the repo's live multi-GB `.ll/history.db`. Column lists
    match `session_store/schema.py`'s DDL, including the two columns ENH-075
    excludes (`loop_runs.error` free text, `loop_runs.diagnostics_path` path).
    """
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE loop_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT, loop_name TEXT, started_at TEXT, ended_at TEXT,
            final_state TEXT, iterations INTEGER, terminated_by TEXT,
            error TEXT, evaluator_score REAL, diagnostics_path TEXT,
            head_sha TEXT, branch TEXT, failure_terminal INTEGER
        );
        CREATE TABLE usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, session_id TEXT, model TEXT, state TEXT,
            input_tokens INTEGER, output_tokens INTEGER,
            cache_read_input_tokens INTEGER, cache_creation_input_tokens INTEGER,
            cost_usd REAL, invocation_id TEXT, provider_vendor TEXT, run_id TEXT
        );
        CREATE TABLE user_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, session_id TEXT, content TEXT
        );
        CREATE INDEX idx_usage_events_model ON usage_events(model);
        """
    )
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (schema_version,))
    conn.executemany(
        "INSERT INTO loop_runs (run_id, loop_name, started_at, ended_at, final_state, "
        "iterations, error, diagnostics_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "r-done",
                "loop-a",
                "2026-08-01T00:00:00Z",
                "2026-08-01T01:00:00Z",
                "done",
                3,
                "secret failure text",
                "/opt/synthetic-fixture/diag.json",
            ),
            # D13: in flight — ended_at IS NULL, started_at inside the window.
            ("r-inflight", "loop-b", "2026-08-02T00:00:00Z", None, None, 1, None, None),
            # Outside any 2026-07-01 window.
            (
                "r-old",
                "loop-c",
                "2026-01-01T00:00:00Z",
                "2026-01-01T01:00:00Z",
                "done",
                2,
                None,
                None,
            ),
        ],
    )
    conn.executemany(
        "INSERT INTO usage_events (ts, session_id, model, input_tokens, cost_usd) "
        "VALUES (?, ?, ?, ?, ?)",
        [("2026-08-01T00:00:00Z", "s1", "opus", 10, 0.5)],
    )
    conn.execute(
        "INSERT INTO user_corrections (ts, session_id, content) VALUES "
        "('2026-08-01T00:00:00Z', 's1', 'free text a viewer must never see')"
    )
    conn.commit()
    conn.close()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A minimal project root with a synthetic .ll/history.db."""
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
    _build_history_db(tmp_path / ".ll" / "history.db")
    return tmp_path


class _Args:
    def __init__(self, **kwargs: object) -> None:
        self.tables = None
        self.since = None
        self.local = False
        self.db = None
        self.output = None
        for key, value in kwargs.items():
            setattr(self, key, value)


def _run(project_root: Path, **kwargs: object) -> tuple[int, Path]:
    """Invoke cmd_dashboard with cwd pinned to *project_root*."""
    logger = Logger(use_color=False)
    with patch("pathlib.Path.cwd", return_value=project_root):
        code = cmd_dashboard(_Args(**kwargs), logger)  # type: ignore[arg-type]
    return code, project_root / ".loops" / "artifacts" / "history-dashboard.html"


def _set_export_config(project_root: Path, **export: object) -> None:
    project_root.joinpath(".ll", "ll-config.json").write_text(
        json.dumps({"artifacts": {"export": export}}), encoding="utf-8"
    )


def _recover_snapshot(html: str, dest: Path) -> sqlite3.Connection:
    """Pull the embedded blob back out of *html*, gunzip it, open it as SQLite."""
    match = re.search(r'SNAPSHOT_B64 = "([^"]*)"', html)
    assert match, "no SNAPSHOT_B64 constant found in the generated page"
    dest.write_bytes(gzip.decompress(base64.b64decode(match.group(1))))
    return sqlite3.connect(dest)


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


# ---------------------------------------------------------------------------
# AC: self-contained, no network, no external assets
# ---------------------------------------------------------------------------


class TestSelfContained:
    def test_single_file_with_no_external_assets(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        assert "<script src=" not in html
        assert '<link rel="stylesheet"' not in html
        assert "http://" not in html
        # The vendored glue carries its own (unused) fetch/XHR locateFile path;
        # what matters is that the page's own script never reaches for the
        # network — guaranteed by initializing with an explicit wasmBinary.
        page_script = html[html.index('var WASM_B64 = "') :]
        assert "XMLHttpRequest" not in page_script
        assert "fetch(" not in page_script
        assert "wasmBinary" in page_script
        assert list(out.parent.iterdir()) == [out]

    def test_output_directory_override(self, project: Path) -> None:
        code, _ = _run(project, since="2026-07-01", output="build")
        assert code == 0
        assert (project / "build" / "history-dashboard.html").is_file()


# ---------------------------------------------------------------------------
# AC: round-trip — excluded tables/columns absent from the embedded snapshot
# ---------------------------------------------------------------------------


class TestSnapshotRoundTrip:
    def test_excluded_columns_absent_from_recovered_schema(
        self, project: Path, tmp_path: Path
    ) -> None:
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        conn = _recover_snapshot(out.read_text(encoding="utf-8"), tmp_path / "rt.db")
        columns = _table_columns(conn, "loop_runs")
        assert columns == _SHAREABLE_COLUMNS["loop_runs"]
        assert "error" not in columns
        assert "diagnostics_path" not in columns
        assert _table_columns(conn, "usage_events") == _SHAREABLE_COLUMNS["usage_events"]

    def test_non_allowlisted_tables_absent(self, project: Path, tmp_path: Path) -> None:
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        conn = _recover_snapshot(out.read_text(encoding="utf-8"), tmp_path / "rt.db")
        assert "user_corrections" not in _table_names(conn)

    def test_default_tables_are_the_shareable_set_not_export_defaults(
        self, project: Path, tmp_path: Path
    ) -> None:
        """D16: no --tables covers exactly loop_run/usage_event, not all 20 types."""
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        conn = _recover_snapshot(out.read_text(encoding="utf-8"), tmp_path / "rt.db")
        assert _table_names(conn) == {"loop_runs", "usage_events"}
        assert len(_EXPORT_DEFAULT_TABLES) > len(_SHAREABLE_EXPORT_TYPES)
        assert _SHAREABLE_EXPORT_TYPES == ["loop_run", "usage_event"]

    def test_since_window_filters_rows(self, project: Path, tmp_path: Path) -> None:
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        conn = _recover_snapshot(out.read_text(encoding="utf-8"), tmp_path / "rt.db")
        run_ids = {r[0] for r in conn.execute("SELECT run_id FROM loop_runs")}
        assert "r-old" not in run_ids

    def test_inflight_run_survives_the_window(self, project: Path, tmp_path: Path) -> None:
        """D13: ended_at IS NULL + started_at in window must be present (COALESCE)."""
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        conn = _recover_snapshot(out.read_text(encoding="utf-8"), tmp_path / "rt.db")
        rows = dict(conn.execute("SELECT run_id, ended_at FROM loop_runs"))
        assert "r-inflight" in rows
        assert rows["r-inflight"] is None

    def test_snapshot_carries_no_indexes(self, project: Path, tmp_path: Path) -> None:
        """D2: CREATE TABLE ... AS SELECT copies no indexes — no VACUUM needed."""
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        conn = _recover_snapshot(out.read_text(encoding="utf-8"), tmp_path / "rt.db")
        assert list(conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")) == []
        assert conn.execute("PRAGMA freelist_count").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# AC: stamps — timestamp, filters, mode, allowlist version, schema versions
# ---------------------------------------------------------------------------


class TestPageStamps:
    def test_timestamp_and_filter_args_visible(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-26", tables="loop_run")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        assert re.search(r"<b>exported</b>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", html)
        assert "<b>tables</b>loop_run<" in html
        assert "2026-07-26" in html

    def test_since_absent_is_stamped_as_all_history(self, project: Path) -> None:
        code, out = _run(project)
        assert code == 0
        assert "<b>since</b>all history<" in out.read_text(encoding="utf-8")

    def test_shareable_mode_and_allowlist_version_stamped(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        assert "<b>mode</b>shareable<" in html
        assert f"<b>allowlist</b>v{_SHAREABLE_ALLOWLIST_VERSION}<" in html

    def test_local_mode_stamped(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-01", local=True)
        assert code == 0
        html = out.read_text(encoding="utf-8")
        assert "<b>mode</b>local<" in html
        assert f"<b>allowlist</b>v{_SHAREABLE_ALLOWLIST_VERSION}<" in html

    def test_schema_version_stamped(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        assert f"source v{SCHEMA_VERSION} / installed v{SCHEMA_VERSION}" in html
        assert "Schema version mismatch" not in html

    def test_schema_version_mismatch_warns(self, tmp_path: Path) -> None:
        """D11: divergence is detected at export time, from the source DB's meta row."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
        _build_history_db(tmp_path / ".ll" / "history.db", schema_version="7")
        code, out = _run(tmp_path, since="2026-07-01")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        assert "Schema version mismatch at export time" in html
        assert f"source v7 / installed v{SCHEMA_VERSION}" in html

    def test_schema_version_warning_helper(self) -> None:
        assert schema_version_warning(str(SCHEMA_VERSION)) == ""
        assert "mismatch" in schema_version_warning("7")
        assert "no recorded schema_version" in schema_version_warning(None)


# ---------------------------------------------------------------------------
# AC: local mode lifts the projection; shareable mode cannot be widened
# ---------------------------------------------------------------------------


class TestModes:
    def test_local_mode_exports_all_columns(self, project: Path, tmp_path: Path) -> None:
        code, out = _run(project, since="2026-07-01", local=True)
        assert code == 0
        conn = _recover_snapshot(out.read_text(encoding="utf-8"), tmp_path / "rt.db")
        columns = _table_columns(conn, "loop_runs")
        assert "error" in columns
        assert "diagnostics_path" in columns

    def test_local_mode_accepts_any_export_type(self, project: Path, tmp_path: Path) -> None:
        """D22: local mode may select a type with no allowlist entry (SELECT *)."""
        code, out = _run(project, since="2026-07-01", local=True, tables="correction")
        assert code == 0
        conn = _recover_snapshot(out.read_text(encoding="utf-8"), tmp_path / "rt.db")
        assert "content" in _table_columns(conn, "user_corrections")

    def test_shareable_mode_rejects_widening(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-01", tables="correction")
        assert code == 1
        assert not out.exists()

    def test_unknown_table_type_rejected(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-01", tables="not_a_type")
        assert code == 1
        assert not out.exists()

    def test_config_mode_local_applies_without_the_flag(self, project: Path) -> None:
        _set_export_config(project, mode="local")
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        assert "<b>mode</b>local<" in out.read_text(encoding="utf-8")

    def test_resolve_tables_defaults_and_scope(self) -> None:
        assert resolve_tables(None, False) == ["loop_run", "usage_event"]
        assert resolve_tables(None, True) == ["loop_run", "usage_event"]
        assert resolve_tables("loop_run", False) == ["loop_run"]
        assert resolve_tables("correction", True) == ["correction"]
        with pytest.raises(ValueError, match="cannot widen"):
            resolve_tables("correction", False)
        with pytest.raises(ValueError, match="unknown"):
            resolve_tables("nope", True)


# ---------------------------------------------------------------------------
# AC: size ceilings (D7 final HTML, D16 raw snapshot pre-check)
# ---------------------------------------------------------------------------


class TestSizeCeilings:
    def test_final_html_ceiling_hard_fails_without_writing(self, project: Path) -> None:
        """D7: a ceiling above the raw snapshot but below the rendered page."""
        _set_export_config(project, max_artifact_bytes=200000)
        with patch("little_loops.cli.artifact.dashboard.render_template") as render:
            render.return_value = "x" * 200001
            code, out = _run(project, since="2026-07-01")
        assert code == 1
        assert render.called, "the final-HTML ceiling must fire after a render, not before"
        assert not out.exists()

    def test_final_html_ceiling_message_names_size_limit_and_since(self, project: Path) -> None:
        _set_export_config(project, max_artifact_bytes=200000)
        logger = Logger(use_color=False)
        with (
            patch("pathlib.Path.cwd", return_value=project),
            patch.object(logger, "error") as error,
        ):
            code = cmd_dashboard(_Args(since="2026-07-01"), logger)  # type: ignore[arg-type]
        assert code == 1
        message = error.call_args[0][0]
        assert "200000" in message
        assert "--since" in message
        assert "No file was written" in message

    def test_raw_snapshot_precheck_fails_before_render(self, project: Path) -> None:
        """D16: a ceiling below the raw snapshot must short-circuit the render."""
        _set_export_config(project, max_artifact_bytes=100)
        with patch("little_loops.cli.artifact.dashboard.render_template") as render:
            code, out = _run(project, since="2026-07-01")
        assert code == 1
        assert not render.called, "the raw-snapshot pre-check must fire before any render"
        assert not out.exists()

    def test_raw_snapshot_precheck_message_names_since(self, project: Path) -> None:
        _set_export_config(project, max_artifact_bytes=100)
        logger = Logger(use_color=False)
        with (
            patch("pathlib.Path.cwd", return_value=project),
            patch.object(logger, "error") as error,
        ):
            code = cmd_dashboard(_Args(since="2026-07-01"), logger)  # type: ignore[arg-type]
        assert code == 1
        message = error.call_args[0][0]
        assert "raw snapshot" in message
        assert "--since" in message


# ---------------------------------------------------------------------------
# AC: the source database is never mutated (D19)
# ---------------------------------------------------------------------------


class TestSourceDbUntouched:
    def test_history_db_byte_identical_after_export(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        code, _ = _run(project, since="2026-07-01")
        assert code == 0
        assert hashlib.sha256(db.read_bytes()).hexdigest() == before

    def test_snapshot_builder_never_uses_the_migrating_open_path(self) -> None:
        """The store's connect() migrates on open; the export must not call it."""
        source = QUERIES_PY.read_text(encoding="utf-8")
        builder = source[
            source.index("def _connect_readonly") : source.index("def export_tables_help")
        ]
        assert "_pkg.connect" not in builder
        assert "mode=ro" in builder


# ---------------------------------------------------------------------------
# AC: read-only guardrail + row cap emitted into the page
# ---------------------------------------------------------------------------


class TestPageQueryEngine:
    def test_query_only_pragma_set_after_every_instantiation(self, project: Path) -> None:
        """D6: PRAGMA query_only=1 is the enforcement, applied at every instantiate().

        Browser-side behavior is not directly assertable from Python; the
        engine-level rejection of `SELECT 1; DELETE FROM loop_runs;` (the case a
        leading-SELECT check was measured to miss) is proven against this exact
        vendored build in `.ll/learning-tests/sqljs.md` (claims C5/C8). What this
        asserts is that the generated page actually wires that mechanism in.
        """
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        instantiate = html[html.index("function instantiate()") : html.index("function textCheck")]
        assert "new SQL.Database(snapshotBytes)" in instantiate
        assert 'db.run("PRAGMA query_only = 1")' in instantiate
        # Both the initial load and the reset action route through instantiate(),
        # so the pragma cannot be skipped on either path.
        assert html.count("instantiate();") == 2

    def test_reset_action_reinstantiates_from_embedded_bytes(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        assert 'getElementById("reset")' in html
        assert "Snapshot reset from the embedded bytes." in html

    def test_text_check_rejects_multi_statement_and_pragma(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        assert "Only one statement at a time" in html
        assert "PRAGMA statements are not accepted here." in html

    def test_row_cap_uses_prepare_step_and_reports_the_true_total(self, project: Path) -> None:
        """D17: the cap is applied at render; the submitted SQL is never rewritten."""
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        run_query = html[html.index("function runQuery(") : html.index("function buildViews()")]
        assert f"var ROW_CAP = {RENDER_ROW_CAP};" in html
        assert "db.prepare(text)" in run_query
        assert "stmt.step()" in run_query
        assert "stmt.free()" in run_query
        assert "rows.length < ROW_CAP" in run_query
        assert "total++" in run_query
        assert '"showing " + ROW_CAP + " of " + total + " rows"' in run_query
        # The submitted text reaches sql.js unmodified: no LIMIT is appended.
        assert "LIMIT" not in run_query

    def test_page_never_calls_db_exec(self, project: Path) -> None:
        """D17 (amended): db.exec() would materialize every result row first."""
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        page_script = html[html.index('var WASM_B64 = "') :]
        code_lines = [
            line for line in page_script.splitlines() if not line.lstrip().startswith("//")
        ]
        assert "db.exec(" not in "\n".join(code_lines)

    def test_predefined_view_requires_no_sql(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        html = out.read_text(encoding="utf-8")
        assert "Loop runs by final state" in html
        assert "GROUP BY final_state" in html
        assert 'getElementById("views")' in html


# ---------------------------------------------------------------------------
# AC: template pipeline (D5/D9/D14/D20)
# ---------------------------------------------------------------------------


class TestTemplatePipeline:
    def test_template_resolves_from_inside_the_package(self) -> None:
        root = _packaged_path("templates", "dashboard.llat")
        assert root.is_dir()
        manifest = load_manifest(root)
        assert manifest["name"] == "history-dashboard"
        assert manifest["output"] == "history-dashboard.html"
        assert manifest["theme"] == "design-tokens"
        assert manifest["renderer"] == "jinja2"

    def test_every_template_and_vendor_file_is_registered_in_package_data(self) -> None:
        for parts in (
            ("templates", "dashboard.llat", "manifest.yaml"),
            ("templates", "dashboard.llat", "template.html.j2"),
            ("assets", "vendor", "sql.js", "sql-wasm.wasm"),
            ("assets", "vendor", "sql.js", "sql-wasm.js"),
            ("assets", "vendor", "sql.js", "PROVENANCE.md"),
        ):
            assert parts in PACKAGE_DATA_ASSETS, f"{parts} missing from PACKAGE_DATA_ASSETS"
            assert check_asset_accessible(parts), f"{parts} not reachable via importlib.resources"
        # One tuple per file: the manifest has no directory-glob form.
        registered = {p for p in PACKAGE_DATA_ASSETS if p[:3] == ("assets", "vendor", "sql.js")}
        on_disk = {("assets", "vendor", "sql.js", f.name) for f in VENDOR_DIR.iterdir()}
        assert registered == on_disk

    def test_theme_css_rendered_through_the_template_not_stamp_page_shell(
        self, project: Path
    ) -> None:
        """D5: theme_css arrives via build_ll_namespace(), never a direct stamp call."""
        source = DASHBOARD_PY.read_text(encoding="utf-8")
        assert "stamp_page_shell" not in source
        assert "themed_css_vars" not in source
        assert "render_template" in source
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        assert "/*__THEMED_CSS_VARS__*/" not in out.read_text(encoding="utf-8")

    def test_data_payload_is_validated_before_rendering(self) -> None:
        """D14: render_template() does not validate; cmd_dashboard must."""
        manifest = load_manifest(_packaged_path("templates", "dashboard.llat"))
        incomplete = {"snapshot_gzip_b64": "", "sql_wasm_b64": "", "sql_wasm_js": ""}
        with pytest.raises(DataValidationError, match="missing required key"):
            validate_top_level_data(incomplete, manifest["data_schema"])
        source = DASHBOARD_PY.read_text(encoding="utf-8")
        assert source.index("validate_top_level_data(data") < source.index(
            "render_template(template"
        )

    def test_missing_required_key_exits_1_as_a_validation_error(self, project: Path) -> None:
        logger = Logger(use_color=False)
        with (
            patch("pathlib.Path.cwd", return_value=project),
            patch(
                "little_loops.cli.artifact.dashboard.validate_top_level_data",
                side_effect=DataValidationError("data: missing required key 'row_cap'"),
            ),
            patch.object(logger, "error") as error,
        ):
            code = cmd_dashboard(_Args(since="2026-07-01"), logger)  # type: ignore[arg-type]
        assert code == 1
        assert "missing required key" in error.call_args[0][0]

    def test_template_body_avoids_jinja_delimiters_in_inline_js(self) -> None:
        """D10: every [[= / [[% in the body must be an intended substitution."""
        root = _packaged_path("templates", "dashboard.llat")
        body = (root / "template.html.j2").read_text(encoding="utf-8")
        manifest = load_manifest(root)
        declared = set(manifest["data_schema"]["properties"]) | {"ll.theme_css"}
        assert set(re.findall(r"\[\[=\s*(.*?)\s*=\]\]", body)) <= declared
        assert set(re.findall(r"\[\[%\s*(.*?)\s*%\]\]", body)) == {
            "if schema_version_warning",
            "if serve_enabled",
            "endif",
        }
        assert "[[#" not in body


# ---------------------------------------------------------------------------
# AC: vendored sql.js provenance (D8/D23)
# ---------------------------------------------------------------------------


class TestVendoredSqlJs:
    def test_glue_contains_no_literal_closing_script_tag(self) -> None:
        """D23: a </script> in the minified glue truncates the inline script tag."""
        glue = (VENDOR_DIR / "sql-wasm.js").read_text(encoding="utf-8")
        assert "</" + "script>" not in glue

    def test_provenance_records_version_hashes_license_and_procedure(self) -> None:
        provenance = (VENDOR_DIR / "PROVENANCE.md").read_text(encoding="utf-8")
        assert "1.14.2" in provenance
        assert "cdn.jsdelivr.net/npm/sql.js" in provenance
        assert "MIT" in provenance
        assert "public domain" in provenance
        assert "Update procedure" in provenance
        for name in ("sql-wasm.wasm", "sql-wasm.js"):
            digest = hashlib.sha256((VENDOR_DIR / name).read_bytes()).hexdigest()
            assert digest in provenance, f"PROVENANCE.md records a stale hash for {name}"


# ---------------------------------------------------------------------------
# AC: allowlist constant / version lockstep (D12)
# ---------------------------------------------------------------------------


class TestAllowlistVersionLockstep:
    """Changing `_SHAREABLE_COLUMNS` means updating BOTH the pinned hash below AND
    bumping `_SHAREABLE_ALLOWLIST_VERSION`, in the same commit. That is the point:
    without it, "stamped with the allowlist version" stamps a string nobody
    maintains and the control it exists to provide does not exist.
    """

    PINNED_VERSION = 1
    PINNED_HASH = "809757f8ee32a1d28aa31a2e8a128f0bcfec3ffa9f35ae27fde8ea6d434280fc"

    def test_allowlist_and_version_change_together(self) -> None:
        digest = hashlib.sha256(
            repr(sorted(_SHAREABLE_COLUMNS.items())).encode("utf-8")
        ).hexdigest()
        assert _SHAREABLE_ALLOWLIST_VERSION == self.PINNED_VERSION, (
            "_SHAREABLE_ALLOWLIST_VERSION changed: update PINNED_VERSION and PINNED_HASH here"
        )
        assert digest == self.PINNED_HASH, (
            "_SHAREABLE_COLUMNS changed without bumping _SHAREABLE_ALLOWLIST_VERSION — "
            "bump the version and update PINNED_VERSION/PINNED_HASH in the same commit"
        )

    def test_allowlist_excludes_free_text_and_absolute_paths(self) -> None:
        assert "error" not in _SHAREABLE_COLUMNS["loop_runs"]
        assert "diagnostics_path" not in _SHAREABLE_COLUMNS["loop_runs"]


# ---------------------------------------------------------------------------
# AC: artifacts.export config block (D21)
# ---------------------------------------------------------------------------


class TestExportConfig:
    def test_defaults_round_trip_through_brconfig(self, tmp_path: Path) -> None:
        from little_loops.config.core import BRConfig

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
        config = BRConfig(tmp_path)
        assert config.artifacts.export.mode == "shareable"
        assert config.artifacts.export.max_artifact_bytes == 8000000
        assert config.to_dict()["artifacts"]["export"] == {
            "mode": "shareable",
            "max_artifact_bytes": 8000000,
        }

    def test_explicit_values_round_trip(self, tmp_path: Path) -> None:
        from little_loops.config.core import BRConfig

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"artifacts": {"export": {"mode": "local", "max_artifact_bytes": 42}}}),
            encoding="utf-8",
        )
        config = BRConfig(tmp_path)
        assert config.artifacts.export.mode == "local"
        assert config.artifacts.export.max_artifact_bytes == 42
        assert config.to_dict()["artifacts"]["export"]["max_artifact_bytes"] == 42

    def test_v1_shape_is_exactly_mode_and_max_artifact_bytes(self) -> None:
        schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
        export = schema["properties"]["artifacts"]["properties"]["export"]
        assert set(export["properties"]) == {"mode", "max_artifact_bytes"}
        assert export["additionalProperties"] is False

    def test_unknown_key_under_export_is_rejected(self) -> None:
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
        # ENH-075's "additions" field is deferred (D21) and must not validate.
        bad = {"artifacts": {"export": {"mode": "shareable", "additions": {}}}}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)
        jsonschema.validate({"artifacts": {"export": {"mode": "local"}}}, schema)

    def test_invalid_mode_is_rejected(self) -> None:
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"artifacts": {"export": {"mode": "public"}}}, schema)


# ---------------------------------------------------------------------------
# Snapshot builder unit surface
# ---------------------------------------------------------------------------


class TestBuildSnapshotDb:
    def test_returns_the_recorded_schema_version(self, tmp_path: Path) -> None:
        src = tmp_path / "h.db"
        _build_history_db(src, schema_version="41")
        assert build_snapshot_db(src, tmp_path / "s.db", tables=["loop_run"]) == "41"

    def test_shareable_mode_rejects_a_type_with_no_allowlist(self, tmp_path: Path) -> None:
        src = tmp_path / "h.db"
        _build_history_db(src)
        with pytest.raises(ValueError, match="no shareable column allowlist"):
            build_snapshot_db(src, tmp_path / "s.db", tables=["correction"])

    def test_unknown_type_rejected(self, tmp_path: Path) -> None:
        src = tmp_path / "h.db"
        _build_history_db(src)
        with pytest.raises(ValueError, match="unknown export type"):
            build_snapshot_db(src, tmp_path / "s.db", tables=["nope"])

    def test_export_history_surface_is_untouched(self) -> None:
        """The builder is a sibling of export_history(), not a wrapper."""
        import inspect

        from little_loops.session_store.queries import export_history

        params = inspect.signature(export_history).parameters
        assert set(params) == {"db", "tables", "since", "include_messages"}


class TestParseSince:
    def test_accepts_date_and_iso8601(self) -> None:
        assert parse_since("2026-07-26").startswith("2026-07-26")
        assert parse_since("2026-07-26T12:00:00Z").startswith("2026-07-26T12:00:00")

    def test_rejects_relative_duration(self) -> None:
        with pytest.raises(ValueError):
            parse_since("30d")

    def test_invalid_since_exits_1(self, project: Path) -> None:
        code, out = _run(project, since="30d")
        assert code == 1
        assert not out.exists()


class TestMissingDatabase:
    def test_missing_history_db_exits_1(self, tmp_path: Path) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
        code, out = _run(tmp_path, since="2026-07-01")
        assert code == 1
        assert not out.exists()


# ---------------------------------------------------------------------------
# ENH-3351: vendored htmx bundle + serve-mode build_dashboard_html/render_live_fragment
# ---------------------------------------------------------------------------


class TestVendoredHtmax:
    def test_bundle_contains_no_literal_closing_script_tag(self) -> None:
        bundle = (VENDOR_HTMX_DIR / "htmax.js").read_text(encoding="utf-8")
        assert "</" + "script>" not in bundle

    def test_provenance_records_version_hash_license_and_procedure(self) -> None:
        provenance = (VENDOR_HTMX_DIR / "PROVENANCE.md").read_text(encoding="utf-8")
        assert "4.0.0" in provenance
        assert "unpkg.com/htmx.org" in provenance
        assert "BSD-0-Clause" in provenance
        assert "Update procedure" in provenance
        digest = hashlib.sha256((VENDOR_HTMX_DIR / "htmax.js").read_bytes()).hexdigest()
        assert digest in provenance, "PROVENANCE.md records a stale hash for htmax.js"


class TestServeModeDashboardDefaultUnchanged:
    """The default file:// path stays byte-for-byte htmx-free (ENH-3351)."""

    def test_default_output_has_no_htmx_or_hx_markers(self, project: Path) -> None:
        code, out = _run(project, since="2026-07-01")
        assert code == 0
        html_text = out.read_text(encoding="utf-8")
        assert "htmx" not in html_text
        assert "hx-" not in html_text
        assert "hx_sse" not in html_text

    def test_cmd_dashboard_delegates_to_build_dashboard_html_with_no_serve_context(
        self, project: Path
    ) -> None:
        from unittest.mock import ANY

        with patch(
            "little_loops.cli.artifact.dashboard.build_dashboard_html",
            wraps=build_dashboard_html,
        ) as spy:
            code, _out = _run(project, since="2026-07-01")
        assert code == 0
        spy.assert_called_once_with(
            db_path=ANY,
            config=ANY,
            tables=ANY,
            since_iso=ANY,
            mode=ANY,
            serve_context=None,
        )


class TestServeModeBuildDashboardHtml:
    def test_missing_db_with_serve_context_renders_empty_snapshot_instead_of_failing(
        self, tmp_path: Path
    ) -> None:
        from little_loops.config.core import BRConfig

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
        config = BRConfig(tmp_path)
        result = build_dashboard_html(
            db_path=tmp_path / ".ll" / "history.db",
            config=config,
            tables=list(_SHAREABLE_EXPORT_TYPES),
            since_iso=None,
            mode="shareable",
            serve_context=ServeContext(
                events_url="http://127.0.0.1:9/tok/events",
                interaction_url="http://127.0.0.1:9/tok/interaction",
            ),
        )
        assert isinstance(result, RenderedDashboard)
        assert "hx-sse:connect" in result.html
        assert "http://127.0.0.1:9/tok/events" in result.html

    def test_missing_db_without_serve_context_raises(self, tmp_path: Path) -> None:
        from little_loops.config.core import BRConfig

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text("{}", encoding="utf-8")
        config = BRConfig(tmp_path)
        with pytest.raises(ValueError, match="history database not found"):
            build_dashboard_html(
                db_path=tmp_path / ".ll" / "history.db",
                config=config,
                tables=list(_SHAREABLE_EXPORT_TYPES),
                since_iso=None,
                mode="shareable",
                serve_context=None,
            )

    def test_serve_context_enabled_page_declares_level_3_and_htmax_js(self, project: Path) -> None:
        from little_loops.config.core import BRConfig

        config = BRConfig(project)
        result = build_dashboard_html(
            db_path=project / ".ll" / "history.db",
            config=config,
            tables=list(_SHAREABLE_EXPORT_TYPES),
            since_iso=None,
            mode="shareable",
            serve_context=ServeContext(
                events_url="http://127.0.0.1:12345/tok/events",
                interaction_url="http://127.0.0.1:12345/tok/interaction",
            ),
        )
        assert "Level 3" in result.html
        assert "var htmx" in result.html  # vendored bundle inlined verbatim

    def test_gzip_snapshot_is_reproducible_across_renders(self, project: Path) -> None:
        """mtime=0 makes two renders of identical input byte-identical (ENH-3351).

        ``exported_at`` is stamped from wall-clock ``datetime.now(UTC)``, which
        is real, desired behavior for a live render but would make this
        reproducibility check itself flaky across a wall-clock second
        boundary — so the clock is frozen for the duration of the test.
        """
        from datetime import UTC, datetime

        from little_loops.config.core import BRConfig

        config = BRConfig(project)
        kwargs = {
            "db_path": project / ".ll" / "history.db",
            "config": config,
            "tables": list(_SHAREABLE_EXPORT_TYPES),
            "since_iso": "2026-07-01T00:00:00",
            "mode": "shareable",
            "serve_context": None,
        }
        frozen = datetime(2026, 7, 1, tzinfo=UTC)
        with patch("little_loops.cli.artifact.dashboard.datetime") as mock_datetime:
            mock_datetime.now.return_value = frozen
            first = build_dashboard_html(**kwargs)
            second = build_dashboard_html(**kwargs)
        assert first.html == second.html


class TestRenderLiveFragment:
    def test_state_enter_event_yields_badge_and_log_partials(self) -> None:
        fragment = render_live_fragment(
            {"event": "state_enter", "state": "running", "ts": "2026-08-28T00:00:00Z"}
        )
        assert fragment is not None
        assert '<hx-partial hx-target="#ll-state-badge"' in fragment
        assert '<hx-partial hx-target="#ll-log-tail"' in fragment

    def test_run_complete_sentinel_sets_complete_badge(self) -> None:
        fragment = render_live_fragment({"event": "run_complete", "ts": "2026-08-28T00:00:00Z"})
        assert fragment is not None
        assert "complete" in fragment

    def test_event_without_event_key_returns_none(self) -> None:
        assert render_live_fragment({}) is None

    def test_iteration_present_yields_iter_count_partial(self) -> None:
        fragment = render_live_fragment(
            {"event": "state_enter", "state": "x", "iteration": 3, "ts": "t"}
        )
        assert fragment is not None
        assert '<hx-partial hx-target="#ll-iter-count"' in fragment
        assert ">3<" in fragment


# ---------------------------------------------------------------------------
# Node runtime gate — exercises the generated page's engine, not just its text
# ---------------------------------------------------------------------------


def _node_major(node: str) -> int | None:
    try:
        proc = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    head = proc.stdout.strip().lstrip("v").split(".", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


class TestDashboardNodeRuntimeGate:
    """Run the JS runtime proof against a real generated artifact.

    The Python assertions above can only show the page *wires in* PRAGMA
    query_only / prepare()/step(); these exercise them against the vendored WASM
    that actually ships, including the multi-statement `SELECT 1; DELETE FROM
    loop_runs;` case a leading-SELECT check was measured to miss. No hosted CI
    exists here by design, so the gate rides inside `python -m pytest
    scripts/tests/` (the FEAT-2390 precedent) and skips when Node is absent so
    contributors without a Node toolchain are not hard-blocked.
    """

    def test_generated_page_runtime_behaviour(self, project: Path) -> None:
        import shutil

        node = shutil.which("node")
        if node is None or (_node_major(node) or 0) < 22:
            pytest.skip("node >= 22 not available")

        code, out = _run(project, since="2026-07-01")
        assert code == 0

        js_test = Path(__file__).parent / "js" / "feat3304" / "feat3304_dashboard_runtime.test.mjs"
        proc = subprocess.run(
            [node, "--test", str(js_test)],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env={**os.environ, "LL_DASHBOARD_HTML": str(out)},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


class TestArtifactCLIDispatchDashboard:
    def test_dashboard_dispatches_to_handler(self) -> None:
        from little_loops.cli.artifact import main_artifact

        with (
            patch("sys.argv", ["ll-artifact", "dashboard", "--since", "2026-07-26"]),
            patch("little_loops.cli.artifact.cmd_dashboard", return_value=0) as handler,
        ):
            code = main_artifact()
        assert code == 0
        handler.assert_called_once()

    def test_dashboard_help_documents_the_size_ceiling(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.argv=['ll-artifact','--help'];"
                "from little_loops.cli.artifact import main_artifact; main_artifact()",
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert "dashboard" in proc.stdout
        assert "max_artifact_bytes" in proc.stdout
