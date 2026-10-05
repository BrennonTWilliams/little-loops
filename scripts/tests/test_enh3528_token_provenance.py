"""ENH-3528: token provenance labeling in ll-ctx-stats and history-reader rollups."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.cli.ctx_stats import (
    _aggregate_usage_events,
    _compute_cache_rate_from_jsonl,
    _print_json,
    _render_fallback,
)
from little_loops.history_reader import (
    aggregate_usage,
    cost_attribution,
    select_usage_observations,
    waste_attribution,
)
from little_loops.logger import Logger
from little_loops.session_store import SessionHandle, connect, ensure_db
from little_loops.token_provenance import (
    UNKNOWN_MODEL_BUCKET,
    ObservationGroup,
    format_figure,
    json_pointer,
    resolve_pointer,
    same_metadata,
    suffix_for,
)

REQUIRED_KEYS = {
    "provenance",
    "metric",
    "availability",
    "known_count",
    "missing_count",
    "coverage",
}


def _insert(db: Path, **row: Any) -> None:
    cols = {
        "ts": "2026-09-01T00:00:00Z",
        "model": "m1",
        "input_tokens": 10,
        "output_tokens": 2,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cost_usd": None,
        **row,
    }
    ensure_db(db)
    conn = connect(db)
    try:
        conn.execute(
            f"INSERT INTO usage_events({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})",
            list(cols.values()),
        )
        conn.commit()
    finally:
        conn.close()


def _capture(argv_json: bool = True) -> tuple[list[str], Any]:
    lines: list[str] = []
    return lines, lambda *a, **_kw: lines.append(str(a[0]) if a else "")


class TestPointers:
    def test_escaping_round_trip(self) -> None:
        pointer = json_pointer("usage_by_model", "per_model", "a/b~c.d", "input_tokens")
        assert pointer == "/usage_by_model/per_model/a~1b~0c.d/input_tokens"
        doc = {"usage_by_model": {"per_model": {"a/b~c.d": {"input_tokens": 7}}}}
        assert resolve_pointer(doc, pointer) == 7

    def test_dotted_model_id_unambiguous(self) -> None:
        pointer = json_pointer("usage_by_model", "per_model", "claude-haiku-4.5", "input_tokens")
        doc = {"usage_by_model": {"per_model": {"claude-haiku-4.5": {"input_tokens": 3}}}}
        assert resolve_pointer(doc, pointer) == 3


class TestUsageAggregation:
    def test_null_components_are_missing_not_zero(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, input_tokens=10, output_tokens=None, provenance="measured")
        _insert(db, input_tokens=5, output_tokens=None, provenance="measured")
        result = _aggregate_usage_events(db)
        assert result is not None
        assert result["totals"]["output_tokens"] is None
        entry = result["provenance"]["/usage_by_model/totals/output_tokens"]
        assert entry["availability"] == "unavailable"
        assert entry["known_count"] == 0 and entry["missing_count"] == 2
        assert entry["qualification_reason"] == "missing_token_component"
        # Row admission: the four token components qualify together (ENH-3731).
        assert result["totals"]["input_tokens"] is None
        audit = result["provenance"]["/usage_by_model/totals/input_tokens"]
        assert audit["composition"] == {"measured": {"count": 2, "subtotal": 15}}

    def test_partial_subtotal_is_labeled_audit_only(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, input_tokens=10, provenance="measured")
        _insert(db, input_tokens=None, provenance="measured")
        _insert(db, input_tokens=4, provenance="measured")
        result = _aggregate_usage_events(db)
        assert result is not None
        # The canonical total is retired; the valid-value sum survives as labeled audit.
        assert result["totals"]["input_tokens"] is None
        entry = result["provenance"]["/usage_by_model/totals/input_tokens"]
        assert (entry["availability"], entry["known_count"], entry["missing_count"]) == (
            "unavailable",
            2,
            1,
        )
        assert entry["composition"] == {"measured": {"count": 2, "subtotal": 14}}
        assert suffix_for(entry).endswith("unavailable]")

    def test_known_zero_stays_zero(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, cache_read_input_tokens=0, provenance="measured")
        result = _aggregate_usage_events(db)
        assert result is not None
        assert result["totals"]["cache_read_input_tokens"] == 0
        entry = result["provenance"]["/usage_by_model/totals/cache_read_input_tokens"]
        assert entry["availability"] == "available"

    def test_null_model_bucket_distinct_from_model_named_unknown(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, model=None)
        _insert(db, model="unknown")
        result = _aggregate_usage_events(db)
        assert result is not None
        assert set(result["per_model"]) == {UNKNOWN_MODEL_BUCKET, "unknown"}

    def test_cost_all_missing_is_null(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, cost_usd=None)
        result = _aggregate_usage_events(db)
        assert result is not None and result["totals"]["cost_usd"] is None

    def test_provenance_composition(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(
            db,
            provenance="measured",
            channel="live",
            host="codex",
            scope_kind="invocation",
            session_id="verified-codex-thread",
            identity_basis="host_observed",
        )
        _insert(db, provenance="estimated", channel="live", host="claude-code")
        result = _aggregate_usage_events(db)
        assert result is not None
        entry = result["provenance"]["/usage_by_model/totals/input_tokens"]
        assert entry["provenance"] == "mixed"
        assert set(entry["composition"]) == {"measured", "estimated"}
        assert entry["hosts"] == ["claude-code", "codex"]

    def test_legacy_null_provenance_reads_unknown(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, provenance=None, host="codex", channel="live")
        result = _aggregate_usage_events(db)
        assert result is not None
        assert result["provenance"]["/usage_by_model/totals/input_tokens"]["provenance"] == (
            "unknown"
        )

    def test_unknown_contributor_makes_aggregate_unknown(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, provenance="measured", channel="live")
        _insert(db, provenance=None, channel="live")
        result = _aggregate_usage_events(db)
        assert result is not None
        entry = result["provenance"]["/usage_by_model/totals/input_tokens"]
        assert entry["provenance"] == "unknown"
        assert "measured" in entry["composition"] and "unknown" in entry["composition"]

    def test_entry_shape(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, provenance="measured", channel="live", host="codex")
        result = _aggregate_usage_events(db)
        assert result is not None
        for entry in result["provenance"].values():
            assert REQUIRED_KEYS <= set(entry)


class TestHostAttribution:
    def test_transcript_row_host_verified_only_with_handle_basis(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, channel="transcript", session_id="s1", host="codex", host_basis="handle")
        _insert(db, channel="transcript", session_id="s2", host="claude-code", host_basis=None)
        result = _aggregate_usage_events(db)
        assert result is not None
        entry = result["provenance"]["/usage_by_model/totals/input_tokens"]
        assert entry["hosts"] == ["codex"]
        assert "unverified" in entry["reason"]

    def test_live_row_null_basis_keeps_invocation_host(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, channel="live", host="codex", host_basis=None)
        result = _aggregate_usage_events(db)
        assert result is not None
        entry = result["provenance"]["/usage_by_model/totals/input_tokens"]
        assert entry["hosts"] == ["codex"]
        assert entry["coverage"] == "unknown"
        assert entry["reason"] == "codex_live_scope_unknown"

    def test_never_falls_back_to_configured_host(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "h.db"
        _insert(db, channel="transcript", session_id="s1", host=None)
        result = _aggregate_usage_events(db)
        assert result is not None
        entry = result["provenance"]["/usage_by_model/totals/input_tokens"]
        assert "hosts" not in entry


class TestChokepoint:
    def test_pre_v54_schema_reads_null_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "old.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE usage_events(id INTEGER PRIMARY KEY, ts TEXT, session_id TEXT, "
            "model TEXT, input_tokens INTEGER, output_tokens INTEGER, "
            "cache_read_input_tokens INTEGER, cache_creation_input_tokens INTEGER, cost_usd REAL)"
        )
        conn.execute(
            "INSERT INTO usage_events VALUES(1,'2026-09-01T00:00:00Z','s','m',1,2,3,4,0.1)"
        )
        conn.commit()
        conn.close()
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        rows = list(select_usage_observations(conn))
        conn.close()
        assert len(rows) == 1
        for col in ("host", "host_basis", "provenance", "channel", "run_id"):
            assert rows[0][col] is None
        result = _aggregate_usage_events(db)
        assert result is not None
        entry = result["provenance"]["/usage_by_model/totals/input_tokens"]
        assert entry["provenance"] == "unknown"

    def test_missing_table_raises(self, tmp_path: Path) -> None:
        conn = sqlite3.connect(":memory:")
        with pytest.raises(sqlite3.OperationalError):
            list(select_usage_observations(conn))

    def test_returns_iterator(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        it = select_usage_observations(conn)
        assert iter(it) is it
        conn.close()

    def test_since_and_require_run_id(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, ts="2026-08-01T00:00:00Z", run_id="r1")
        _insert(db, ts="2026-09-02T00:00:00Z", run_id=None)
        _insert(db, ts="2026-09-03T00:00:00Z", run_id="r2")
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        assert len(list(select_usage_observations(conn))) == 3
        assert len(list(select_usage_observations(conn, since="2026-09-01"))) == 2
        assert len(list(select_usage_observations(conn, require_run_id=True))) == 2
        conn.close()


class TestCoverage:
    def _group(self, rows: list[dict[str, Any]]) -> ObservationGroup:
        group = ObservationGroup()
        for row in rows:
            group.add({"provenance": "measured", "input_tokens": 1, **row})
        return group

    def test_live_plus_transcript_without_identity_is_unresolved(self) -> None:
        group = self._group(
            [
                {"channel": "live", "session_id": None},
                {"channel": "transcript", "session_id": "s1"},
            ]
        )
        assert group.coverage() == "overlap_unresolved"
        assert group.aggregate_provenance("input_tokens") == "unknown"
        assert set(group.channel_subtotals()) == {"live", "transcript"}
        assert "twice" in group.entry("input_tokens")["reason"]

    def test_shared_session_identity_is_unresolved(self) -> None:
        group = self._group(
            [
                {"channel": "live", "session_id": "s1"},
                {"channel": "transcript", "session_id": "s1"},
            ]
        )
        assert group.coverage() == "overlap_unresolved"

    def test_disjoint_session_identities_are_non_overlapping(self) -> None:
        group = self._group(
            [
                {"channel": "live", "session_id": "s1"},
                {"channel": "transcript", "session_id": "s2"},
            ]
        )
        assert group.coverage() == "non_overlapping"
        assert group.aggregate_provenance("input_tokens") == "measured"

    def test_equal_tokens_and_run_id_are_not_proof(self) -> None:
        group = self._group(
            [
                {"channel": "live", "session_id": None, "run_id": "r"},
                {"channel": "transcript", "session_id": "s1", "run_id": "r"},
            ]
        )
        assert group.coverage() == "overlap_unresolved"

    def test_rollups_propagate_overlap(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, channel="live", run_id="r1", provenance="measured", session_id=None)
        _insert(db, channel="transcript", session_id="s1", provenance="measured")
        for rows in (aggregate_usage(db=db), cost_attribution("model", db=db)):
            assert rows[0]["coverage"] == "overlap_unresolved"
            assert rows[0]["provenance"] == "unknown"
            assert set(rows[0]["channel_subtotals"]) == {"live", "transcript"}

    def test_waste_propagates_overlap_and_none_on_missing(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_loop_run_summary

        db = tmp_path / "h.db"
        ensure_db(db)
        record_loop_run_summary(
            db, run_id="r1", loop_name="lp", terminated_by="max_steps", final_state=None
        )
        _insert(db, run_id="r1", channel="live", input_tokens=10, output_tokens=None)
        _insert(db, run_id="r1", channel="transcript", session_id="s", input_tokens=5)
        rows = waste_attribution(db=db)
        assert len(rows) == 1
        row = rows[0]
        assert row["tokens_total"] is None and row["tokens_wasted"] is None
        assert row["tokens_total_missing"] == 1 and row["tokens_wasted_missing"] == 1
        assert row["waste_pct"] is None
        assert row["coverage"] == "overlap_unresolved"


class TestHistoryReaderNullContract:
    def test_aggregate_usage_none_on_any_missing(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, input_tokens=10)
        _insert(db, input_tokens=None)
        row = aggregate_usage(db=db)[0]
        assert row["input_tokens"] is None
        assert row["input_tokens_missing"] == 1

    def test_ctx_stats_and_reader_agree_on_same_fixture(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, input_tokens=10, provenance="measured")
        _insert(db, input_tokens=None, provenance="measured")
        assert aggregate_usage(db=db)[0]["input_tokens"] is None
        result = _aggregate_usage_events(db)
        assert result is not None and result["totals"]["input_tokens"] is None
        entry = result["provenance"]["/usage_by_model/totals/input_tokens"]
        assert entry["composition"] == {"measured": {"count": 1, "subtotal": 10}}

    def test_waste_zero_denominator(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_loop_run_summary

        db = tmp_path / "h.db"
        ensure_db(db)
        record_loop_run_summary(
            db, run_id="r1", loop_name="lp", terminated_by="max_steps", final_state=None
        )
        _insert(db, run_id="r1", input_tokens=0, output_tokens=0, provenance="measured")
        row = waste_attribution(db=db)[0]
        assert row["tokens_total"] == 0 and row["waste_pct"] is None
        assert row["qualification_reason"] is None
        assert row["waste_pct_qualification_reason"] == "zero_denominator"


class TestTextFormat:
    def test_suffix_qualifier_order(self) -> None:
        base = {
            "provenance": "unknown",
            "availability": "available",
            "known_count": 1,
            "missing_count": 0,
            "coverage": "non_overlapping",
        }
        assert suffix_for({**base, "provenance": "measured"}) == "[measured]"
        assert (
            suffix_for({**base, "coverage": "overlap_unresolved"})
            == "[unknown · overlap unresolved]"
        )
        partial = {
            **base,
            "provenance": "mixed",
            "availability": "partial",
            "known_count": 3,
            "missing_count": 2,
        }
        assert suffix_for(partial) == "[mixed · partial 3/5]"
        assert (
            suffix_for({**partial, "coverage": "unknown", "stale": True})
            == "[mixed · partial 3/5 · unknown · stale]"
        )

    def test_unavailable_renders_dash(self) -> None:
        entry = {
            "provenance": "unknown",
            "availability": "unavailable",
            "known_count": 0,
            "missing_count": 1,
            "coverage": "non_overlapping",
        }
        assert format_figure(None, entry) == "— [unknown · unavailable]"
        assert format_figure(12345, {**entry, "availability": "available"}) == ("12,345 [unknown]")

    def test_same_metadata_ignores_reason(self) -> None:
        a = {"provenance": "measured", "reason": "x"}
        b = {"provenance": "measured", "reason": "y"}
        c = {"provenance": "estimated"}
        assert same_metadata([a, b])
        assert not same_metadata([a, c])

    def test_fallback_group_header_and_dash(self, capsys: pytest.CaptureFixture[str]) -> None:
        _render_fallback(
            {"tool_calls": 2, "breakdown": {"read": 10, "bash": 5}}, Logger(use_color=False)
        )
        out = capsys.readouterr().out
        assert "Estimated tokens in context: — [unknown · unavailable]" in out
        assert "Per-tool token estimates: [estimated]" in out
        assert "read" in out and "[estimated]" not in out.split("Per-tool")[1].split("\n", 1)[1]

    def test_fallback_estimate_available(self, capsys: pytest.CaptureFixture[str]) -> None:
        _render_fallback({"estimated_tokens": 12345, "tool_calls": 1}, Logger(use_color=False))
        assert "Estimated tokens in context: 12,345 [estimated]" in capsys.readouterr().out

    def test_fallback_exposes_occupancy_freshness(self, capsys: pytest.CaptureFixture[str]) -> None:
        state = {
            "estimated_tokens": 12345,
            "tool_calls": 2,
            "session_id": "session-1",
            "scope_kind": "context",
            "estimate_reason": "transcript_baseline_plus_heuristic",
            "baseline_observed_at": "2026-09-29T12:00:00Z",
            "estimate_updated_at": "2026-09-29T12:00:05Z",
            "baseline_observation_boundary": "1234567890",
            "context_boundary": "2026-09-29T11:00:00Z",
            "stale": True,
            "stale_reason": "tool_activity_after_baseline",
            "result_token_count": 99000,
        }
        _render_fallback(state, Logger(use_color=False))
        output = capsys.readouterr().out
        assert "12,345 [estimated · stale]" in output
        assert "tool_activity_after_baseline" in output
        assert "session-1" in output
        assert "2026-09-29T12:00:00Z" in output
        assert "2026-09-29T12:00:05Z" in output
        assert "99,000" not in output

    def test_legacy_fallback_freshness_unknown(self, capsys: pytest.CaptureFixture[str]) -> None:
        _render_fallback(
            {"estimated_tokens": 2000, "result_token_count": 90000}, Logger(use_color=False)
        )
        output = capsys.readouterr().out
        assert "freshness unknown" in output
        assert "90,000" not in output


class TestJsonDocument:
    def _run(self, summary: dict, **kw: Any) -> dict:
        lines, side_effect = _capture()
        with patch("builtins.print", side_effect=side_effect):
            _print_json(summary, None, **kw)
        return json.loads("\n".join(lines))

    def test_all_pointers_resolve_and_exclude_byte_fields(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, model="vendor/model~x.1", provenance="measured", channel="live", host="codex")
        usage = _aggregate_usage_events(db)
        summary = {
            "total_in": 1,
            "total_out": 2,
            "cache_hits": 1,
            "cache_bytes": 1,
            "per_tool": {},
        }
        cache_rate = {
            "cache_read": 5,
            "cache_write": 1,
            "uncached": 2,
            "hit_rate_pct": 62,
            "host": "codex",
            "provenance": "measured",
            "session_id": "sess",
        }
        pressure = {"samples": 2, "peak_pct": 80.0, "avg_pct": 50.0, "crossings": {}}
        doc = self._run(
            summary, cache_rate=cache_rate, usage_events=usage, pressure=pressure, waste=[]
        )
        provenance = doc["token_provenance"]
        assert provenance
        for pointer in provenance:
            value = resolve_pointer(doc, pointer)
            assert value is None or isinstance(value, (int, float))
        assert "provenance" not in doc["usage_by_model"]
        assert not any(
            key in pointer
            for pointer in provenance
            for key in ("bytes_", "cache_hits", "cache_bytes_saved", "reduction_pct")
        )
        model_ptr = json_pointer("usage_by_model", "per_model", "vendor/model~x.1", "input_tokens")
        assert model_ptr in provenance
        assert doc["source"] == "sqlite"
        # cache_rate_host equals hosts[0]
        rate_entry = provenance["/cache_hit_rate_pct"]
        assert rate_entry["hosts"][0] == doc["cache_rate_host"]
        assert rate_entry["scope_kind"] == "session"
        assert rate_entry["channels"] == ["transcript_file"]
        assert rate_entry["session_id"] == "sess"
        assert provenance["/context_pressure/peak_pct"]["provenance"] == "estimated"

    def test_fallback_pointers_resolve(self) -> None:
        lines, side_effect = _capture()
        with patch("builtins.print", side_effect=side_effect):
            _print_json(
                None,
                {"estimated_tokens": 9, "tool_calls": 1, "breakdown": {"a/b": 3}},
            )
        doc = json.loads("\n".join(lines))
        assert doc["source"] == "fallback"
        assert doc["token_provenance"]["/estimated_tokens"]["provenance"] == "estimated"
        assert resolve_pointer(doc, "/breakdown/a~1b") == 3
        assert "/breakdown/a~1b" in doc["token_provenance"]

    def test_fallback_json_carries_occupancy_boundary(self) -> None:
        lines, side_effect = _capture()
        state = {
            "estimated_tokens": 900,
            "session_id": "session-1",
            "baseline_observed_at": "2026-09-29T12:00:00Z",
            "estimate_updated_at": "2026-09-29T12:00:05Z",
            "baseline_observation_boundary": "1234567890",
            "context_boundary": "2026-09-29T11:00:00Z",
            "estimate_reason": "transcript_baseline_plus_heuristic",
            "stale": True,
            "stale_reason": "tool_activity_after_baseline",
            "result_token_count": 99999,
        }
        with patch("builtins.print", side_effect=side_effect):
            _print_json(None, state)
        doc = json.loads("\n".join(lines))
        assert doc["estimated_tokens"] == 900
        assert "result_token_count" not in doc
        entry = doc["token_provenance"]["/estimated_tokens"]
        assert entry["metric"] == "context_occupancy_tokens"
        assert entry["session_id"] == "session-1"
        assert entry["stale"] is True
        assert entry["stale_reason"] == "tool_activity_after_baseline"
        assert entry["baseline_observed_at"] == "2026-09-29T12:00:00Z"
        assert entry["estimate_updated_at"] == "2026-09-29T12:00:05Z"
        assert entry["baseline_observation_boundary"] == "1234567890"
        assert entry["context_boundary"] == "2026-09-29T11:00:00Z"

    def test_legacy_fallback_json_has_unknown_freshness(self) -> None:
        lines, side_effect = _capture()
        with patch("builtins.print", side_effect=side_effect):
            _print_json(None, {"estimated_tokens": 9, "result_token_count": 99999})
        entry = json.loads("\n".join(lines))["token_provenance"]["/estimated_tokens"]
        assert entry["stale"] is None
        assert entry["stale_reason"] == "unknown_baseline_freshness"

    def test_missing_occupancy_estimate_is_unavailable(self) -> None:
        lines, side_effect = _capture()
        with patch("builtins.print", side_effect=side_effect):
            _print_json(None, {"result_token_count": 99999})
        doc = json.loads("\n".join(lines))
        assert doc["estimated_tokens"] is None
        entry = doc["token_provenance"]["/estimated_tokens"]
        assert entry["availability"] == "unavailable"
        assert entry["provenance"] == "unknown"
        assert entry["stale"] is None

    def test_none_source_has_no_provenance(self) -> None:
        lines, side_effect = _capture()
        with patch("builtins.print", side_effect=side_effect):
            _print_json(None, None)
        assert json.loads("\n".join(lines)) == {"source": "none"}

    def test_waste_pointers_resolve(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_loop_run_summary

        db = tmp_path / "h.db"
        ensure_db(db)
        record_loop_run_summary(
            db, run_id="r1", loop_name="lp", terminated_by="max_steps", final_state=None
        )
        _insert(db, run_id="r1", channel="live", provenance="measured")
        waste = waste_attribution(db=db)
        summary = {"total_in": 1, "total_out": 1, "cache_hits": 0, "cache_bytes": 0, "per_tool": {}}
        doc = self._run(summary, waste=waste)
        for key in ("tokens_total", "tokens_wasted", "waste_pct"):
            assert f"/waste/0/{key}" in doc["token_provenance"]
            assert (
                resolve_pointer(doc, f"/waste/0/{key}") is None
                or resolve_pointer(doc, f"/waste/0/{key}") >= 0
            )


class TestCacheRateFromTranscript:
    def _run(self, tmp_path: Path, records: list[dict[str, Any]]) -> dict[str, Any] | None:
        session = tmp_path / "s.jsonl"
        session.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        handle = SessionHandle(
            host="pi",
            session_id="sess-1",
            path=session,
            cwd=tmp_path,
            updated_at=0.0,
        )
        with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
            return _compute_cache_rate_from_jsonl(tmp_path, None)

    @staticmethod
    def _assistant(uuid: str, usage: dict[str, Any]) -> dict[str, Any]:
        return {"type": "assistant", "uuid": uuid, "message": {"usage": usage}}

    def test_absent_keys_are_missing_not_zero(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path,
            [
                self._assistant("a", {"cache_read_input_tokens": 90, "input_tokens": 10}),
                self._assistant(
                    "b",
                    {
                        "cache_read_input_tokens": 10,
                        "cache_creation_input_tokens": 0,
                        "input_tokens": 10,
                    },
                ),
            ],
        )
        assert result is not None
        assert result["cache_write"] == 0  # known zero from record b
        assert result["counts"]["cache_write"] == {"known": 1, "missing": 1}
        assert result["counts"]["hit_rate_pct"] == {"known": 1, "missing": 1}
        # rate uses only the eligible record: 10 / (10 + 0 + 10)
        assert result["hit_rate_pct"] == 50
        assert result["cache_read"] == 100  # known components still count
        assert result["provenance"] == "unknown"
        assert result["session_id"] == "sess-1"

    def test_explicit_null_does_not_crash(self, tmp_path: Path) -> None:
        result = self._run(
            tmp_path,
            [
                self._assistant(
                    "a",
                    {
                        "cache_read_input_tokens": None,
                        "cache_creation_input_tokens": None,
                        "input_tokens": 5,
                    },
                )
            ],
        )
        assert result is not None
        assert result["cache_read"] is None and result["cache_write"] is None
        assert result["uncached"] == 5
        assert result["hit_rate_pct"] is None
        assert result["counts"]["cache_read"] == {"known": 0, "missing": 1}

    def test_usage_without_any_key_is_not_an_observation(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, [self._assistant("a", {"output_tokens": 5})]) is None
        result = self._run(
            tmp_path,
            [
                self._assistant("a", {"output_tokens": 5}),
                self._assistant(
                    "b",
                    {
                        "cache_read_input_tokens": 1,
                        "cache_creation_input_tokens": 1,
                        "input_tokens": 2,
                    },
                ),
            ],
        )
        assert result is not None and result["counts"]["hit_rate_pct"]["known"] == 1

    def test_codex_does_not_use_direct_transcript_accounting(self, tmp_path: Path) -> None:
        handle = SessionHandle(
            host="codex", session_id="cx", path=tmp_path / "r.jsonl", cwd=tmp_path, updated_at=0.0
        )
        with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
            result = _compute_cache_rate_from_jsonl(tmp_path, "codex")
        assert result is None
