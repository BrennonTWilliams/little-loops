"""ENH-3543: exported usage surfaces preserve selector coverage and privacy."""

from __future__ import annotations

import dataclasses
import inspect
import itertools
import re
import sqlite3
from pathlib import Path

import pytest

from little_loops.session_store import ensure_db
from little_loops.session_store.queries import _SHAREABLE_COLUMNS, build_snapshot_db
from little_loops.session_store.schema import SCHEMA_VERSION

_SENSITIVE_PATH = "/private/snapshot-source-sentinel.jsonl"
_SENSITIVE_TURN = "native-turn-sentinel"
_SENSITIVE_REQUEST = "native-request-sentinel"


def _source_db(tmp_path: Path) -> Path:
    db = tmp_path / "history.db"
    ensure_db(db)
    columns = (
        "ts",
        "session_id",
        "model",
        "host",
        "host_basis",
        "channel",
        "identity_basis",
        "scope_kind",
        "request_identity_basis",
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "cost_usd",
        "provenance",
        "source_path",
        "turn_id",
        "request_id",
    )

    def insert(
        conn: sqlite3.Connection,
        *,
        ts: str = "2026-09-29T10:00:00Z",
        session: str,
        model: str,
        host: str,
        channel: str,
        input_tokens: int,
        cost: float | None,
        scope: str | None = None,
    ) -> None:
        values = (
            ts,
            session,
            model,
            host,
            "handle" if channel != "live" else None,
            channel,
            "host_observed" if host == "codex" else None,
            scope,
            "native_response" if channel == "rollout" else None,
            input_tokens,
            2,
            1,
            0,
            cost,
            "measured",
            _SENSITIVE_PATH,
            _SENSITIVE_TURN,
            _SENSITIVE_REQUEST,
        )
        conn.execute(
            f"INSERT INTO usage_events ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            values,
        )

    with sqlite3.connect(db) as conn:
        # Two verified channels for one Codex thread cannot be joined to a
        # native request. The earlier row still governs a later --since export.
        insert(
            conn,
            ts="2026-09-28T10:00:00Z",
            session="partial-thread",
            model="partial-model",
            host="codex",
            channel="live",
            input_tokens=10,
            cost=0.10,
            scope="invocation",
        )
        insert(
            conn,
            session="partial-thread",
            model="partial-model",
            host="codex",
            channel="rollout",
            input_tokens=11,
            cost=0.20,
        )
        # A qualified row for the same model remains visible as a known
        # subtotal, while the model-wide canonical total remains unavailable.
        insert(
            conn,
            session="claude-partial",
            model="partial-model",
            host="claude-code",
            channel="transcript",
            input_tokens=5,
            cost=0.05,
        )
        # Qualified independent channels can be selected; missing cost in one
        # channel must keep the entire model's canonical cost NULL.
        insert(
            conn,
            session="claude-known",
            model="known-model",
            host="claude-code",
            channel="transcript",
            input_tokens=7,
            cost=0.07,
        )
        insert(
            conn,
            session="rollout-known",
            model="known-model",
            host="codex",
            channel="rollout",
            input_tokens=8,
            cost=None,
        )
        insert(
            conn,
            session="rollout-complete",
            model="complete-model",
            host="codex",
            channel="rollout",
            input_tokens=12,
            cost=0.12,
        )
        insert(
            conn,
            session="live-unknown",
            model="unknown-model",
            host="codex",
            channel="live",
            input_tokens=9,
            cost=0.09,
            scope="unknown",
        )
    return db


def _snapshot(db: Path, dest: Path, *, since: str | None = None) -> sqlite3.Connection:
    build_snapshot_db(db, dest, tables=["usage_event"], since=since)
    return sqlite3.connect(dest)


def _rows(conn: sqlite3.Connection, table: str) -> list[dict[str, object]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]


def test_shareable_snapshot_keeps_known_rows_and_audit_without_claiming_overlap(
    tmp_path: Path,
) -> None:
    db = _source_db(tmp_path)
    dest = tmp_path / "shareable.db"
    with _snapshot(db, dest) as conn:
        raw = _rows(conn, "usage_events")
        selected = _rows(conn, "selected_usage_events")
        audit = _rows(conn, "usage_coverage_audit")
        schemas = {
            table: {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for table in ("usage_events", "selected_usage_events", "usage_coverage_audit")
        }
        assert [
            row[1] for row in conn.execute("PRAGMA table_info(selected_usage_events)")
        ] == _SHAREABLE_COLUMNS["selected_usage_events"]
        assert [
            row[1] for row in conn.execute("PRAGMA table_info(usage_coverage_audit)")
        ] == _SHAREABLE_COLUMNS["usage_coverage_audit"]

    assert len(raw) == 7
    assert {(row["model"], row["channel"]) for row in selected} == {
        ("partial-model", "transcript"),
        ("known-model", "transcript"),
        ("known-model", "rollout"),
        ("complete-model", "rollout"),
    }
    assert all(row["coverage"] == "non_overlapping" for row in selected)

    by_key = {(row["model"], row["channel"]): row for row in audit}
    partial = [row for row in audit if row["model"] == "partial-model"]
    assert {row["channel"] for row in partial} == {"live", "rollout", "transcript"}
    assert all(row["coverage"] == "overlap_unresolved" for row in partial)
    assert all(row["canonical_input_tokens"] is None for row in partial)
    assert all(row["canonical_cost_usd"] is None for row in partial)
    assert by_key["partial-model", "transcript"]["known_input_tokens"] == 5
    assert by_key["partial-model", "live"]["raw_input_tokens"] == 10
    assert by_key["partial-model", "rollout"]["raw_input_tokens"] == 11
    assert by_key["known-model", "transcript"]["canonical_input_tokens"] == 7
    assert by_key["known-model", "rollout"]["canonical_input_tokens"] == 8
    assert by_key["known-model", "transcript"]["known_cost_usd"] == 0.07
    assert by_key["known-model", "transcript"]["canonical_cost_usd"] is None
    assert by_key["known-model", "rollout"]["canonical_cost_usd"] is None
    assert by_key["complete-model", "rollout"]["canonical_cost_usd"] == 0.12
    assert by_key["unknown-model", "live"]["coverage"] == "unknown"
    assert by_key["unknown-model", "live"]["selected_observation_count"] == 0
    assert by_key["unknown-model", "live"]["canonical_cost_usd"] is None

    forbidden = {"source_path", "turn_id", "request_id", "source_raw_event_id"}
    assert all(not forbidden.intersection(columns) for columns in schemas.values())
    snapshot_bytes = dest.read_bytes()
    for sentinel in (_SENSITIVE_PATH, _SENSITIVE_TURN, _SENSITIVE_REQUEST):
        assert sentinel.encode() not in snapshot_bytes


def test_since_window_keeps_full_source_coverage_classification(tmp_path: Path) -> None:
    db = _source_db(tmp_path)
    with _snapshot(db, tmp_path / "window.db", since="2026-09-29T00:00:00Z") as conn:
        audit = _rows(conn, "usage_coverage_audit")
        selected = _rows(conn, "selected_usage_events")
        raw = _rows(conn, "usage_events")

    by_key = {(row["model"], row["channel"]): row for row in audit}
    assert ("partial-model", "live") not in by_key
    rollout = by_key["partial-model", "rollout"]
    assert rollout["raw_observation_count"] == 1
    assert rollout["coverage"] == "overlap_unresolved"
    assert rollout["canonical_input_tokens"] is None
    assert not any(
        row["model"] == "partial-model" and row["channel"] == "rollout" for row in selected
    )
    assert not any(row["model"] == "partial-model" and row["channel"] == "live" for row in raw)


def test_loop_only_snapshot_does_not_create_usage_surfaces(tmp_path: Path) -> None:
    db = _source_db(tmp_path)
    dest = tmp_path / "loop-only.db"
    build_snapshot_db(db, dest, tables=["loop_run"])
    with sqlite3.connect(dest) as conn:
        names = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert names == {"loop_runs"}


# ---------------------------------------------------------------------------
# ENH-3733: model-wide qualification, bounded metadata, representability, one
# read snapshot.
# ---------------------------------------------------------------------------

_UNSET = object()
_ALL_TOKENS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def _store(tmp_path: Path, rows: list[dict[str, object]], *, wal: bool = False) -> Path:
    """Build a source store from simple row specs (one verified session per row)."""
    db = tmp_path / "history.db"
    ensure_db(db)
    with sqlite3.connect(db) as conn:
        if wal:
            conn.execute("PRAGMA journal_mode=WAL")
        for index, spec in enumerate(rows):
            _insert_spec(conn, index, spec)
    return db


def _insert_spec(conn: sqlite3.Connection, index: int, spec: dict[str, object]) -> None:
    channel = spec.get("channel", "transcript")
    host = spec.get("host", "codex" if channel in ("rollout",) else "claude-code")
    tokens = spec.get("tokens", (1, 1, 1, 1))
    assert isinstance(tokens, tuple)
    values: dict[str, object] = {
        "ts": spec.get("ts", "2026-09-29T10:00:00Z"),
        "session_id": spec.get("session", f"sess-{index}"),
        "model": spec.get("model", "m"),
        "host": host,
        "host_basis": "handle" if channel != "live" else None,
        "channel": channel,
        "identity_basis": "host_observed" if host == "codex" else None,
        "scope_kind": spec.get("scope"),
        "request_identity_basis": "native_response" if channel == "rollout" else None,
        "input_tokens": tokens[0],
        "output_tokens": tokens[1],
        "cache_read_input_tokens": tokens[2],
        "cache_creation_input_tokens": tokens[3],
        "cost_usd": spec.get("cost", 0.1),
        "provenance": spec.get("provenance", "measured"),
        "source_path": _SENSITIVE_PATH,
        "turn_id": f"{_SENSITIVE_TURN}-{index}" if channel == "rollout" else None,
        "request_id": _SENSITIVE_REQUEST,
    }
    conn.execute(
        f"INSERT INTO usage_events ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
        tuple(values.values()),
    )


def _audit_by_key(conn: sqlite3.Connection) -> dict[tuple[str, str], dict[str, object]]:
    return {(row["model"], row["channel"]): row for row in _rows(conn, "usage_coverage_audit")}


def test_audit_metadata_columns_and_policy_version(tmp_path: Path) -> None:
    from little_loops.token_provenance import USAGE_QUALIFICATION_POLICY_VERSION

    db = _store(tmp_path, [{"model": "a"}, {"model": "a", "provenance": "estimated"}])
    with _snapshot(db, tmp_path / "s.db") as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(usage_coverage_audit)")]
        audit = _audit_by_key(conn)
    assert columns[-4:] == [
        "provenance",
        "qualification_reason",
        "cost_qualification_reason",
        "qualification_policy_version",
    ]
    row = audit["a", "transcript"]
    assert row["provenance"] == "mixed"
    assert row["qualification_reason"] is None and row["cost_qualification_reason"] is None
    assert row["qualification_policy_version"] == USAGE_QUALIFICATION_POLICY_VERSION
    assert row["canonical_input_tokens"] == 2


def test_source_snapshot_qualification_parity(tmp_path: Path) -> None:
    """Snapshot canonical figures agree with the source reader per logical model."""
    from little_loops.history_reader.usage import cost_attribution
    from little_loops.observability.tracing import (
        GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
        GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
        GEN_AI_USAGE_INPUT_TOKENS,
        GEN_AI_USAGE_OUTPUT_TOKENS,
    )
    from little_loops.token_provenance import UNKNOWN_MODEL_BUCKET

    inf = float("inf")
    rows: list[dict[str, object]] = []
    for model, specs in {
        "p-measured": [{}, {}],
        "p-estimated": [{"provenance": "estimated"}, {"provenance": "estimated"}],
        "p-mixed": [{}, {"provenance": "estimated"}],
        "p-unknown": [{"provenance": None}],
        "p-missing-token": [{"tokens": (1, None, 1, 1)}],
        "p-invalid-token": [{"tokens": (-1, 1, 1, 1)}, {}],
        "p-unpriced": [{"cost": None}, {}],
        "p-invalid-cost": [{"cost": inf}, {}],
        "p-zero": [{"tokens": (0, 0, 0, 0), "cost": 0.0}],
        None: [{}],
    }.items():
        rows.extend({**spec, "model": model} for spec in specs)
    db = _store(tmp_path, rows)
    source = {entry["model"]: entry for entry in cost_attribution("model", db=db)}
    with _snapshot(db, tmp_path / "s.db") as conn:
        audit = _rows(conn, "usage_coverage_audit")
    names = (
        (GEN_AI_USAGE_INPUT_TOKENS, "input_tokens"),
        (GEN_AI_USAGE_OUTPUT_TOKENS, "output_tokens"),
        (GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS, "cache_read_input_tokens"),
        (GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS, "cache_creation_input_tokens"),
    )
    assert {row["model"] for row in audit} == {
        (UNKNOWN_MODEL_BUCKET if m is None else m) for m in source
    }
    for model, entry in source.items():
        bucket = UNKNOWN_MODEL_BUCKET if model is None else model
        mine = [row for row in audit if row["model"] == bucket]
        assert {row["qualification_reason"] for row in mine} == {entry["qualification_reason"]}
        assert {row["cost_qualification_reason"] for row in mine} == {
            entry["cost_qualification_reason"]
        }
        assert {row["coverage"] for row in mine} == {entry["coverage"]}
        for otel, column in names:
            canonical = [row[f"canonical_{column}"] for row in mine]
            if entry["qualification_reason"] is None:
                assert sum(canonical) == entry[otel], (model, column)
            else:
                assert otel not in entry and all(value is None for value in canonical)
        cost = [row["canonical_cost_usd"] for row in mine]
        if entry["cost_qualification_reason"] is None:
            assert sum(cost) == pytest.approx(entry["cost_usd"])
        else:
            assert all(value is None for value in cost) and entry["cost_usd"] is None
    by_model = {row["model"]: row for row in audit}
    assert by_model["p-zero"]["canonical_input_tokens"] == 0
    assert by_model["p-zero"]["canonical_cost_usd"] == 0.0
    assert by_model["p-unpriced"]["canonical_input_tokens"] == 2
    assert by_model["p-unpriced"]["canonical_cost_usd"] is None
    assert by_model["p-unknown"]["provenance"] == "unknown"
    assert by_model["p-estimated"]["provenance"] == "estimated"
    assert by_model[UNKNOWN_MODEL_BUCKET]["qualification_reason"] is None


def test_channel_cannot_recertify_incomplete_model(tmp_path: Path) -> None:
    rows = [
        {"model": "m", "channel": "transcript"},
        {"model": "m", "channel": "rollout", "tokens": (1, None, 1, 1)},
    ]
    db = _store(tmp_path, rows)
    with _snapshot(db, tmp_path / "s.db") as conn:
        audit = _audit_by_key(conn)
    for channel in ("transcript", "rollout"):
        row = audit["m", channel]
        assert row["qualification_reason"] == "missing_token_component"
        assert all(row[f"canonical_{c}"] is None for c in _ALL_TOKENS)
        assert row["selected_observation_count"] == 1  # audit evidence intact
    # The complete channel's own known subtotal stays visible as audit evidence.
    assert audit["m", "transcript"]["known_input_tokens"] == 1


def test_cost_missing_and_invalid_counts_are_null_only(tmp_path: Path) -> None:
    inf = float("inf")
    db = _store(tmp_path, [{"model": "m", "cost": None}, {"model": "m", "cost": inf}])
    with _snapshot(db, tmp_path / "s.db") as conn:
        row = _audit_by_key(conn)["m", "transcript"]
    assert row["raw_missing_cost_count"] == 1
    assert row["known_missing_cost_count"] == 1
    assert row["cost_qualification_reason"] == "invalid_cost"
    assert row["qualification_reason"] is None
    assert row["canonical_input_tokens"] == 2
    assert row["raw_cost_usd"] is None and row["known_cost_usd"] is None
    assert row["canonical_cost_usd"] is None


def test_invalid_values_never_enter_audit_subtotals(tmp_path: Path) -> None:
    inf = float("inf")
    db = _store(
        tmp_path,
        [
            {"model": "m", "cost": inf, "tokens": (-5, 1, 1, 1)},
            {"model": "m", "cost": 0.5, "tokens": (4, 1, 1, 1)},
        ],
    )
    with _snapshot(db, tmp_path / "s.db") as conn:
        row = _audit_by_key(conn)["m", "transcript"]
    assert row["raw_observation_count"] == 2
    assert row["raw_input_tokens"] == 4  # the invalid -5 is not admitted
    assert row["raw_cost_usd"] == 0.5  # inf is not a finite contribution
    assert row["raw_missing_cost_count"] == 0
    assert row["qualification_reason"] == "invalid_token_component"
    assert row["canonical_input_tokens"] is None


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
@pytest.mark.parametrize("second", [2**62, 2**62 - 1])
def test_int64_overflow_is_export_only_and_model_wide(
    tmp_path: Path, order: tuple[int, ...], second: int
) -> None:
    specs: list[dict[str, object]] = [
        {"model": "big", "channel": "transcript", "tokens": (2**62, 1, 1, 1), "cost": 0.1},
        {"model": "big", "channel": "transcript", "tokens": (second, 1, 1, 1), "cost": 0.2},
        {"model": "big", "channel": "rollout", "tokens": (3, 1, 1, 1), "cost": 0.3},
        {"model": "ok", "tokens": (5, 1, 1, 1), "cost": 0.05},
    ]
    shuffled = [specs[i] for i in order] + [specs[3]]
    db = _store(tmp_path, shuffled)
    with _snapshot(db, tmp_path / "s.db") as conn:
        audit = _audit_by_key(conn)
        selected = _rows(conn, "selected_usage_events")
    overflow = 2**62 + second > 2**63 - 1
    big_t, big_r = audit["big", "transcript"], audit["big", "rollout"]
    assert big_t["raw_observation_count"] == 2 and big_t["selected_observation_count"] == 2
    assert big_t["coverage"] == "non_overlapping"
    assert sorted(row["input_tokens"] for row in selected if row["model"] == "big") == sorted(
        [2**62, second, 3]
    )
    if overflow:
        assert big_t["raw_input_tokens"] is None and big_t["known_input_tokens"] is None
        for row in (big_t, big_r):
            assert row["qualification_reason"] == "snapshot_integer_overflow"
            assert all(row[f"canonical_{c}"] is None for c in _ALL_TOKENS)
        assert big_r["raw_input_tokens"] == 3
        assert big_t["raw_output_tokens"] == 2  # unaffected columns stay published
    else:
        assert big_t["raw_input_tokens"] == 2**63 - 1
        assert big_t["canonical_input_tokens"] == 2**63 - 1
        assert big_t["qualification_reason"] is None
    # cost is qualified independently and the shared policy outcome is unchanged
    assert big_t["cost_qualification_reason"] is None
    assert big_t["canonical_cost_usd"] == pytest.approx(0.3)
    assert big_r["canonical_cost_usd"] == pytest.approx(0.3)
    ok = audit["ok", "transcript"]
    assert ok["canonical_input_tokens"] == 5 and ok["qualification_reason"] is None
    # a missing and an overflowing component do not inflate the missing-cost counts
    assert big_t["raw_missing_cost_count"] == 0


@pytest.mark.parametrize("flip", [False, True])
def test_disjoint_channels_keep_representable_tokens_but_cost_fails_model_wide(
    tmp_path: Path, flip: bool
) -> None:
    from little_loops.history_reader.usage import cost_attribution

    specs: list[dict[str, object]] = [
        {"model": "wide", "channel": "transcript", "tokens": (2**62, 1, 1, 1), "cost": 1e308},
        {"model": "wide", "channel": "rollout", "tokens": (2**62, 1, 1, 1), "cost": 1e308},
    ]
    db = _store(tmp_path, list(reversed(specs)) if flip else specs)
    source = {e["model"]: e for e in cost_attribution("model", db=db)}["wide"]
    assert source["channel_subtotals"]["transcript"]["input_tokens"] == 2**62
    with _snapshot(db, tmp_path / "s.db") as conn:
        audit = _audit_by_key(conn)
    for channel in ("transcript", "rollout"):
        row = audit["wide", channel]
        assert row["coverage"] == "non_overlapping"
        assert row["canonical_input_tokens"] == 2**62  # the unbound 2**63 model sum is irrelevant
        assert row["qualification_reason"] is None
        assert row["cost_qualification_reason"] == "invalid_cost"
        assert row["canonical_cost_usd"] is None
    assert source["cost_qualification_reason"] == "invalid_cost"
    assert source["qualification_reason"] is None


def test_out_of_window_audit_only_row_does_not_taint_other_window(tmp_path: Path) -> None:
    rows = [
        # Audit-only (codex live, unknown scope) in its own coverage group, old.
        {
            "model": "m",
            "channel": "live",
            "host": "codex",
            "scope": "unknown",
            "ts": "2026-09-01T10:00:00Z",
        },
        {"model": "m", "channel": "transcript", "ts": "2026-09-29T10:00:00Z"},
    ]
    db = _store(tmp_path, rows)
    with _snapshot(db, tmp_path / "all.db") as conn:
        everything = _audit_by_key(conn)
    with _snapshot(db, tmp_path / "win.db", since="2026-09-20T00:00:00Z") as conn:
        windowed = _audit_by_key(conn)
    assert everything["m", "transcript"]["qualification_reason"] == "coverage_unknown"
    assert everything["m", "transcript"]["coverage_reason"] == "codex_live_scope_unknown"
    assert everything["m", "live"]["selected_observation_count"] == 0
    assert ("m", "live") not in windowed
    assert windowed["m", "transcript"]["qualification_reason"] is None
    assert windowed["m", "transcript"]["canonical_input_tokens"] == 1


def test_empty_generated_usage_tables_have_no_rows_or_policy_version(tmp_path: Path) -> None:
    db = _store(tmp_path, [])
    with _snapshot(db, tmp_path / "s.db") as conn:
        assert _rows(conn, "usage_coverage_audit") == []
        assert conn.execute("SELECT COUNT(*) FROM usage_coverage_audit").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM selected_usage_events").fetchone()[0] == 0
    (tmp_path / "p").mkdir()
    populated = _store(tmp_path / "p", [{}])
    with _snapshot(populated, tmp_path / "w.db", since="2099-01-01T00:00:00Z") as conn:
        assert _rows(conn, "usage_coverage_audit") == []


def test_legacy_null_channel_uses_logical_channel(tmp_path: Path) -> None:
    db = _store(tmp_path, [{"model": "m", "channel": "transcript"}])
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE usage_events SET channel = NULL")
    with _snapshot(db, tmp_path / "s.db") as conn:
        audit = _audit_by_key(conn)
        raw = _rows(conn, "usage_events")
    assert ("m", "transcript") in audit  # row_channel: NULL channel + session_id
    assert raw[0]["channel"] is None  # the raw observation keeps its stored value


def test_unknown_model_bucket_in_audit_and_raw_model_preserved(tmp_path: Path) -> None:
    from little_loops.token_provenance import UNKNOWN_MODEL_BUCKET

    db = _store(tmp_path, [{"model": None}])
    with _snapshot(db, tmp_path / "s.db") as conn:
        audit = _audit_by_key(conn)
        raw = _rows(conn, "usage_events")
        selected = _rows(conn, "selected_usage_events")
    assert (UNKNOWN_MODEL_BUCKET, "transcript") in audit
    assert raw[0]["model"] is None and selected[0]["model"] is None


def test_reason_admission_is_bounded_to_approved_codes() -> None:
    from little_loops.session_store.queries import _COVERAGE_REASON_CODES, _snapshot_reason
    from little_loops.token_provenance import USAGE_QUALIFICATION_REASONS

    assert _snapshot_reason(None) is None
    for code in (
        USAGE_QUALIFICATION_REASONS | _COVERAGE_REASON_CODES | {"snapshot_integer_overflow"}
    ):
        assert _snapshot_reason(code) == code
    assert _snapshot_reason("sk_live_abc123_secret") == "unclassified"
    assert _snapshot_reason("free text with spaces") == "unclassified"
    assert _snapshot_reason(42) == "unclassified"


def test_coverage_reason_allowlist_matches_selector_codes() -> None:
    from little_loops.history_reader import usage as usage_module
    from little_loops.session_store.queries import _COVERAGE_REASON_CODES

    source = inspect.getsource(usage_module._classify_coverage) + inspect.getsource(
        usage_module.select_usage_coverage
    )
    emitted = set(re.findall(r'"(?:overlap_unresolved|unknown)", "(\w+)"', source))
    emitted |= set(re.findall(r'"unknown", "(\w+)"', source))
    assert emitted and emitted <= _COVERAGE_REASON_CODES
    assert {"no_verified_identity_columns", "no_host_column"} <= _COVERAGE_REASON_CODES


def test_identifier_shaped_reason_inputs_never_reach_the_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from little_loops.history_reader import usage as usage_module

    secret = "sk_live_identifier_shaped_secret"
    prose = "free prose with a /private/path"
    real = usage_module.select_usage_coverage

    def tainted(conn: sqlite3.Connection, **kwargs: object) -> object:
        selection = real(conn, **kwargs)  # type: ignore[arg-type]
        rows = tuple(
            {**row, "_coverage_reason": secret if i % 2 else prose}
            for i, row in enumerate(selection.audit_rows)
        )
        return dataclasses.replace(selection, audit_rows=rows)

    monkeypatch.setattr(usage_module, "select_usage_coverage", tainted)
    db = _store(tmp_path, [{"model": "m"}, {"model": "m"}])
    dest = tmp_path / "s.db"
    with _snapshot(db, dest) as conn:
        row = _audit_by_key(conn)["m", "transcript"]
    assert row["coverage_reason"] == "unclassified"
    blob = dest.read_bytes()
    for sentinel in (secret, prose, _SENSITIVE_PATH, _SENSITIVE_TURN, _SENSITIVE_REQUEST):
        assert sentinel.encode() not in blob


def _concurrent_write(db: Path) -> None:
    writer = sqlite3.connect(db, timeout=0)
    try:
        writer.execute("UPDATE meta SET value = 'writer-revision' WHERE key = 'schema_version'")
        _insert_spec(writer, 99, {"model": "late", "session": "late-session"})
        writer.commit()
    finally:
        writer.close()


def _assert_single_revision(db: Path, dest: Path, version: str | None) -> None:
    with sqlite3.connect(dest) as conn:
        raw = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        selected = conn.execute("SELECT COUNT(*) FROM selected_usage_events").fetchone()[0]
        audit = conn.execute("SELECT SUM(raw_observation_count) FROM usage_coverage_audit")
        audited = audit.fetchone()[0]
        late = conn.execute("SELECT COUNT(*) FROM usage_events WHERE model = 'late'").fetchone()[0]
    assert (raw, selected, audited, late) == (2, 2, 2, 0)
    assert version == str(SCHEMA_VERSION)
    with sqlite3.connect(db) as source:  # the writer's later revision is intact
        assert source.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 3
        meta = source.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    assert meta == ("writer-revision",)


def test_version_and_tables_share_one_read_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from little_loops.session_store import queries

    db = _store(tmp_path, [{"model": "a"}, {"model": "b"}], wal=True)
    original = queries.read_schema_version

    def after_version(conn: sqlite3.Connection) -> str | None:
        version = original(conn)
        _concurrent_write(db)
        return version

    monkeypatch.setattr(queries, "read_schema_version", after_version)
    dest = tmp_path / "s.db"
    version = build_snapshot_db(db, dest, tables=["usage_event"])
    _assert_single_revision(db, dest, version)


def test_selector_seam_write_does_not_split_the_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from little_loops.history_reader import usage as usage_module

    db = _store(tmp_path, [{"model": "a"}, {"model": "b"}], wal=True)
    real = usage_module.select_usage_coverage

    def write_then_select(conn: sqlite3.Connection, **kwargs: object) -> object:
        _concurrent_write(db)  # after the raw tables were copied
        return real(conn, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(usage_module, "select_usage_coverage", write_then_select)
    dest = tmp_path / "s.db"
    version = build_snapshot_db(db, dest, tables=["usage_event"])
    _assert_single_revision(db, dest, version)
