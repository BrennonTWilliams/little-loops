"""Tests for issue_history.workspace_quality — FEAT-3410's per-member aggregation.

Covers: healthy multi-member aggregation, the schema-skew gate's six skip
cases (missing file, missing meta table, missing schema_version row, behind,
ahead, non-SQLite file), source-DB-untouched (sha256), a source-inspection
test proving the module never uses a migrating opener, and the
`AggregationResult` overload of all four `format_agent_quality_*` formatters.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from little_loops.issue_history.agent_quality import (
    format_agent_quality_json,
    format_agent_quality_markdown,
    format_agent_quality_text,
    format_agent_quality_yaml,
)
from little_loops.issue_history.workspace_quality import AggregationResult, aggregate_history_dbs
from little_loops.session_store.schema import SCHEMA_VERSION
from little_loops.session_store.writers import record_issue_event
from little_loops.workspace import WorkspaceMember


def _healthy_member(tmp_path: Path, name: str, role: str) -> WorkspaceMember:
    """A member repo with a real, current-schema history.db (via the write API).

    Deliberately named ``<name>-history.db`` rather than the default-shaped
    ``.ll/history.db`` (``_is_default_shaped()``,
    ``session_store/db.py::_resolve_db_path()``): the test suite's autouse
    ``_isolate_history_db`` fixture routes any default-shaped path through a
    single shared ``LL_HISTORY_DB`` env var, which would collapse every
    member onto the same file and defeat the point of a multi-member test.
    """
    repo_path = tmp_path / name
    (repo_path / ".issues").mkdir(parents=True)
    (repo_path / ".ll").mkdir()
    db_path = repo_path / ".ll" / f"{name}-history.db"
    record_issue_event(db_path, f"{name}-BUG-1", "done")
    return WorkspaceMember(repo_path=repo_path, role=role, db_path=db_path)


def _bare_sqlite_member(
    tmp_path: Path, name: str, role: str, *, with_meta: bool
) -> WorkspaceMember:
    """A member with a bare sqlite file, optionally with an empty `meta` table."""
    repo_path = tmp_path / name
    (repo_path / ".issues").mkdir(parents=True)
    ll_dir = repo_path / ".ll"
    ll_dir.mkdir()
    db_path = ll_dir / "history.db"
    conn = sqlite3.connect(db_path)
    if with_meta:
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    else:
        conn.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    return WorkspaceMember(repo_path=repo_path, role=role, db_path=db_path)


def _skewed_member(tmp_path: Path, name: str, role: str, *, schema_version: str) -> WorkspaceMember:
    repo_path = tmp_path / name
    (repo_path / ".issues").mkdir(parents=True)
    ll_dir = repo_path / ".ll"
    ll_dir.mkdir()
    db_path = ll_dir / "history.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (schema_version,))
    conn.commit()
    conn.close()
    return WorkspaceMember(repo_path=repo_path, role=role, db_path=db_path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestHealthyAggregation:
    def test_two_healthy_members(self, tmp_path: Path) -> None:
        m1 = _healthy_member(tmp_path, "repo_a", "primary")
        m2 = _healthy_member(tmp_path, "repo_b", "sibling")

        result = aggregate_history_dbs(
            [m1, m2], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert set(result.per_repo) == {"repo_a (primary)", "repo_b (sibling)"}
        assert result.skipped == []

    def test_empty_members_list(self) -> None:
        result = aggregate_history_dbs(
            [], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )
        assert result.per_repo == {}
        assert result.skipped == []


class TestSchemaSkewGate:
    def test_missing_db_file(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "ghost"
        (repo_path / ".issues").mkdir(parents=True)
        db_path = repo_path / ".ll" / "history.db"
        member = WorkspaceMember(repo_path=repo_path, role="primary", db_path=db_path)

        result = aggregate_history_dbs(
            [member], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.per_repo == {}
        assert len(result.skipped) == 1
        label, reason = result.skipped[0]
        assert label == "ghost (primary)"
        assert reason == f"history.db not found at {db_path}"

    def test_missing_meta_table(self, tmp_path: Path) -> None:
        member = _bare_sqlite_member(tmp_path, "no_meta", "primary", with_meta=False)
        before = _sha256(member.db_path)

        result = aggregate_history_dbs(
            [member], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.skipped == [("no_meta (primary)", "schema_version missing (no meta row)")]
        assert _sha256(member.db_path) == before

    def test_missing_schema_version_row(self, tmp_path: Path) -> None:
        member = _bare_sqlite_member(tmp_path, "empty_meta", "primary", with_meta=True)
        before = _sha256(member.db_path)

        result = aggregate_history_dbs(
            [member], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.skipped == [("empty_meta (primary)", "schema_version missing (no meta row)")]
        assert _sha256(member.db_path) == before

    def test_schema_behind(self, tmp_path: Path) -> None:
        stale_version = str(SCHEMA_VERSION - 1)
        member = _skewed_member(tmp_path, "stale", "primary", schema_version=stale_version)
        before = _sha256(member.db_path)

        result = aggregate_history_dbs(
            [member], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.skipped == [
            ("stale (primary)", f"schema_version {stale_version} != installed {SCHEMA_VERSION}")
        ]
        assert _sha256(member.db_path) == before

    def test_schema_ahead(self, tmp_path: Path) -> None:
        future_version = str(SCHEMA_VERSION + 1)
        member = _skewed_member(tmp_path, "future", "primary", schema_version=future_version)
        before = _sha256(member.db_path)

        result = aggregate_history_dbs(
            [member], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert result.skipped == [
            ("future (primary)", f"schema_version {future_version} != installed {SCHEMA_VERSION}")
        ]
        assert _sha256(member.db_path) == before

    def test_non_sqlite_file(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "garbage"
        (repo_path / ".issues").mkdir(parents=True)
        ll_dir = repo_path / ".ll"
        ll_dir.mkdir()
        db_path = ll_dir / "history.db"
        db_path.write_text("not a database")
        member = WorkspaceMember(repo_path=repo_path, role="primary", db_path=db_path)
        before = _sha256(db_path)

        result = aggregate_history_dbs(
            [member], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert len(result.skipped) == 1
        label, reason = result.skipped[0]
        assert label == "garbage (primary)"
        assert reason.startswith("could not read read-only:")
        assert _sha256(db_path) == before

    def test_healthy_sibling_still_analyzed_alongside_skipped(self, tmp_path: Path) -> None:
        healthy = _healthy_member(tmp_path, "healthy", "primary")
        skewed = _skewed_member(tmp_path, "skewed", "sibling", schema_version="1")

        result = aggregate_history_dbs(
            [healthy, skewed], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert "healthy (primary)" in result.per_repo
        assert result.skipped == [
            ("skewed (sibling)", f"schema_version 1 != installed {SCHEMA_VERSION}")
        ]


class TestSourceDbUntouched:
    def test_main_file_hash_unchanged_after_run(self, tmp_path: Path) -> None:
        member = _healthy_member(tmp_path, "repo_a", "primary")
        before = _sha256(member.db_path)

        aggregate_history_dbs(
            [member], min_sample=1, sensitivity=0.3, baseline_windows=3, latest_only=True
        )

        assert _sha256(member.db_path) == before

    def test_never_uses_migrating_opener(self) -> None:
        """Source-inspection: the module must never touch a migrating opener.

        Mirrors `test_feat3304_artifact_dashboard.py
        ::test_snapshot_builder_never_uses_the_migrating_open_path` — reading
        each member's DB through `ensure_db()` (via
        `history_reader/_base.py::_connect_readonly()`) would migrate a
        stale member in place before the schema-skew gate could see it.
        """
        import little_loops.issue_history.workspace_quality as mod

        text = Path(mod.__file__).read_text()
        code = text[text.index("def _open_member_readonly") :]
        assert "ensure_db(" not in code
        assert "_connect_readonly(" not in code
        assert "immutable=1" not in code
        assert "mode=ro" in code


class TestAggregationResultFormatters:
    def _sample_result(self) -> AggregationResult:
        from little_loops.issue_history.agent_quality import QualityAnalysis

        return AggregationResult(
            per_repo={"repo_a (primary)": QualityAnalysis(min_sample_size=1)},
            skipped=[("repo_b (sibling)", "schema_version 1 != installed 49")],
        )

    def test_text_includes_labels(self) -> None:
        out = format_agent_quality_text(self._sample_result())
        assert "repo_a (primary)" in out
        assert "repo_b (sibling): schema_version 1 != installed 49" in out

    def test_markdown_includes_labels(self) -> None:
        out = format_agent_quality_markdown(self._sample_result())
        assert "## repo_a (primary)" in out
        assert "repo_b (sibling)" in out

    def test_json_round_trips_structure(self) -> None:
        import json

        out = json.loads(format_agent_quality_json(self._sample_result()))
        assert "repo_a (primary)" in out["per_repo"]
        assert out["skipped"] == [
            {"repo": "repo_b (sibling)", "reason": "schema_version 1 != installed 49"}
        ]

    def test_yaml_includes_labels(self) -> None:
        out = format_agent_quality_yaml(self._sample_result())
        assert "repo_a (primary)" in out
        assert "repo_b (sibling)" in out

    def test_no_skipped_members_reports_none(self) -> None:
        from little_loops.issue_history.agent_quality import QualityAnalysis

        result = AggregationResult(
            per_repo={"repo_a (primary)": QualityAnalysis(min_sample_size=1)}, skipped=[]
        )
        assert "none" in format_agent_quality_text(result).lower()
        assert "None." in format_agent_quality_markdown(result)

    def test_totals_set_renders_workspace_totals_section(self) -> None:
        from little_loops.issue_history.agent_quality import QualityAnalysis

        result = AggregationResult(
            per_repo={"repo_a (primary)": QualityAnalysis(min_sample_size=1)},
            skipped=[],
            totals=QualityAnalysis(min_sample_size=1),
        )
        assert "Workspace totals" in format_agent_quality_text(result)
        assert "## Workspace totals" in format_agent_quality_markdown(result)
        assert format_agent_quality_json(result)  # totals/totals_skipped keys present

        import json

        out = json.loads(format_agent_quality_json(result))
        assert out["totals"] is not None
        assert out["totals_skipped"] is None

    def test_totals_skipped_renders_reason(self) -> None:
        from little_loops.issue_history.agent_quality import QualityAnalysis

        result = AggregationResult(
            per_repo={"repo_a (primary)": QualityAnalysis(min_sample_size=1)},
            skipped=[],
            totals=None,
            totals_skipped="no analyzable members",
        )
        assert "no analyzable members" in format_agent_quality_text(result)
        assert "no analyzable members" in format_agent_quality_markdown(result)

        import json

        out = json.loads(format_agent_quality_json(result))
        assert out["totals"] is None
        assert out["totals_skipped"] == "no analyzable members"
