"""Tests for usage.py: tool-event and usage-event queries (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

from pathlib import Path

from little_loops.history_reader import (
    aggregate_usage,
    cost_attribution,
    recent_usage_events,
    waste_attribution,
)
from little_loops.session_store import (
    connect,
    ensure_db,
)


class TestCostAttribution:
    """cost_attribution() token/cost rollup over usage_events (FEAT-2478)."""

    @staticmethod
    def _seed(db: Path) -> None:
        ensure_db(db)
        conn = connect(db)
        rows = [
            # (ts, session, model, state, in, out, cread, ccreate, cost, inv, vendor)
            (
                "2026-07-16T00:00:00Z",
                "s1",
                "claude",
                None,
                100,
                20,
                5,
                7,
                0.01,
                "inv-1",
                "anthropic",
            ),
            (
                "2026-07-16T00:00:01Z",
                "s1",
                "claude",
                None,
                200,
                40,
                10,
                14,
                0.02,
                "inv-1",
                "anthropic",
            ),
            (
                "2026-07-16T00:00:02Z",
                "s2",
                "claude",
                None,
                50,
                10,
                0,
                0,
                0.005,
                "inv-2",
                "anthropic",
            ),
        ]
        conn.executemany(
            "INSERT INTO usage_events(ts, session_id, model, state, input_tokens, "
            "output_tokens, cache_read_input_tokens, cache_creation_input_tokens, "
            "cost_usd, invocation_id, provider_vendor) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()

    def test_missing_db_returns_empty(self, tmp_path: Path) -> None:
        assert cost_attribution(db=tmp_path / "nope.db") == []

    def test_group_by_invocation_id_sums_match_raw_totals(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._seed(db)
        rows = cost_attribution(group_by="gen_ai.invocation.id", db=db)
        assert len(rows) == 2  # one row per invocation
        inv1 = next(r for r in rows if r["gen_ai.invocation.id"] == "inv-1")
        # sum across the invocation's two rows == raw usage totals row-for-row
        assert inv1["gen_ai.usage.input_tokens"] == 300
        assert inv1["gen_ai.usage.output_tokens"] == 60
        assert inv1["gen_ai.usage.cache_read.input_tokens"] == 15
        assert inv1["gen_ai.usage.cache_creation.input_tokens"] == 21
        assert inv1["invocations"] == 2

    def test_group_by_vendor(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._seed(db)
        rows = cost_attribution(group_by="gen_ai.provider.vendor", db=db)
        assert len(rows) == 1
        assert rows[0]["gen_ai.provider.vendor"] == "anthropic"
        assert rows[0]["gen_ai.usage.input_tokens"] == 350

    def test_unsupported_group_by_raises(self, tmp_path: Path) -> None:
        import pytest

        db = tmp_path / "history.db"
        self._seed(db)
        with pytest.raises(ValueError):
            cost_attribution(group_by="'; DROP TABLE usage_events; --", db=db)

    def test_group_by_run_id(self, tmp_path: Path) -> None:
        """ENH-2724: run_id is a valid group_by column once the live writer lands."""
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        conn.execute(
            "INSERT INTO usage_events(ts, model, state, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, cost_usd, run_id) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("2026-07-21T19:00:00Z", "claude", "check", 100, 20, 5, 7, 0.01, "run-1-loop"),
        )
        conn.commit()
        conn.close()

        rows = cost_attribution(group_by="run_id", db=db)
        assert len(rows) == 1
        assert rows[0]["run_id"] == "run-1-loop"
        assert rows[0]["gen_ai.usage.input_tokens"] == 100


class TestWasteAttribution:
    """waste_attribution() per-loop tokens-wasted rollup, joined on run_id (ENH-2722)."""

    @staticmethod
    def _seed_run(
        db: Path,
        *,
        run_id: str,
        loop_name: str,
        terminated_by: str,
        final_state: str | None,
        input_tokens: int,
        output_tokens: int,
        failure_terminal: bool | None = None,
    ) -> None:
        from little_loops.session_store import record_loop_run_summary

        ensure_db(db)
        record_loop_run_summary(
            db,
            run_id=run_id,
            loop_name=loop_name,
            terminated_by=terminated_by,
            final_state=final_state,
            failure_terminal=failure_terminal,
        )
        conn = connect(db)
        conn.execute(
            "INSERT INTO usage_events(ts, model, state, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, cost_usd, run_id) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                "2026-07-21T19:00:00Z",
                "claude",
                "check",
                input_tokens,
                output_tokens,
                0,
                0,
                0.0,
                run_id,
            ),
        )
        conn.commit()
        conn.close()

    def test_missing_db_returns_empty(self, tmp_path: Path) -> None:

        assert waste_attribution(db=tmp_path / "nope.db") == []

    def test_empty_tables_returns_empty(self, tmp_path: Path) -> None:

        db = tmp_path / "history.db"
        ensure_db(db)
        assert waste_attribution(db=db) == []

    def test_success_and_wasted_runs_split_by_loop(self, tmp_path: Path) -> None:

        db = tmp_path / "history.db"
        # Successful run: terminated_by="terminal", final_state="done" -> not wasted.
        self._seed_run(
            db,
            run_id="run-1",
            loop_name="rn-implement",
            terminated_by="terminal",
            final_state="done",
            input_tokens=100,
            output_tokens=20,
        )
        # Infra-exit run: terminated_by="max_steps" -> wasted regardless of final_state.
        self._seed_run(
            db,
            run_id="run-2",
            loop_name="rn-implement",
            terminated_by="max_steps",
            final_state=None,
            input_tokens=50,
            output_tokens=10,
        )
        # Normal completion into a non-"done" final state -> wasted.
        self._seed_run(
            db,
            run_id="run-3",
            loop_name="rn-implement",
            terminated_by="terminal",
            final_state="failed",
            input_tokens=30,
            output_tokens=5,
        )

        rows = waste_attribution(db=db)
        assert len(rows) == 1
        row = rows[0]
        assert row["loop_name"] == "rn-implement"
        assert row["tokens_total"] == 215  # 120 + 60 + 35
        assert row["tokens_wasted"] == 95  # 60 + 35
        assert row["waste_pct"] == 95 / 215
        assert row["runs_total"] == 3
        assert row["runs_wasted"] == 2

    def test_wasted_run_read_from_persisted_failure_flag(self, tmp_path: Path) -> None:
        """ENH-2814: waste is read from loop_runs.failure_terminal, not the name.

        Covers both directions of the flag against the legacy name heuristic:
        a flagged terminal named `blocked` counts as wasted, while an
        unflagged terminal named `present_result` does not.
        """

        db = tmp_path / "history.db"
        self._seed_run(
            db,
            run_id="run-1",
            loop_name="gate",
            terminated_by="terminal",
            final_state="blocked",
            failure_terminal=True,
            input_tokens=80,
            output_tokens=20,
        )
        self._seed_run(
            db,
            run_id="run-2",
            loop_name="gate",
            terminated_by="terminal",
            final_state="present_result",
            failure_terminal=False,
            input_tokens=80,
            output_tokens=20,
        )

        row = waste_attribution(db=db)[0]
        assert row["runs_total"] == 2
        assert row["runs_wasted"] == 1
        assert row["tokens_wasted"] == 100

    def test_legacy_null_flag_falls_back_to_name_check(self, tmp_path: Path) -> None:
        """Pre-ENH-2814 rows (failure_terminal NULL) keep the old semantics."""

        db = tmp_path / "history.db"
        self._seed_run(
            db,
            run_id="run-1",
            loop_name="legacy",
            terminated_by="terminal",
            final_state="failed",
            failure_terminal=None,
            input_tokens=80,
            output_tokens=20,
        )

        assert waste_attribution(db=db)[0]["runs_wasted"] == 1

    def test_waste_pct_none_when_no_tokens(self, tmp_path: Path) -> None:
        """Divide-by-zero guard: a loop with zero-token rows reports waste_pct=None."""

        db = tmp_path / "history.db"
        self._seed_run(
            db,
            run_id="run-1",
            loop_name="rn-implement",
            terminated_by="terminal",
            final_state="done",
            input_tokens=0,
            output_tokens=0,
        )

        rows = waste_attribution(db=db)
        assert len(rows) == 1
        assert rows[0]["tokens_total"] == 0
        assert rows[0]["waste_pct"] is None

    def test_ambiguous_terminations_not_counted_as_wasted(self, tmp_path: Path) -> None:
        """user_stopped/handoff are operator-initiated, not counted as waste."""

        db = tmp_path / "history.db"
        self._seed_run(
            db,
            run_id="run-1",
            loop_name="rn-refine",
            terminated_by="user_stopped",
            final_state=None,
            input_tokens=10,
            output_tokens=5,
        )
        self._seed_run(
            db,
            run_id="run-2",
            loop_name="rn-refine",
            terminated_by="handoff",
            final_state=None,
            input_tokens=10,
            output_tokens=5,
        )

        rows = waste_attribution(db=db)
        assert len(rows) == 1
        assert rows[0]["tokens_wasted"] == 0
        assert rows[0]["runs_wasted"] == 0

    def test_unjoined_usage_events_excluded(self, tmp_path: Path) -> None:
        """usage_events rows with no matching loop_runs.run_id are excluded (inner join)."""

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        conn.execute(
            "INSERT INTO usage_events(ts, model, state, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, cost_usd, run_id) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("2026-07-21T19:00:00Z", "claude", "check", 100, 20, 0, 0, 0.0, "orphan-run"),
        )
        conn.commit()
        conn.close()

        assert waste_attribution(db=db) == []


class TestUsageEventReaders:
    """ENH-2461: recent_usage_events / aggregate_usage over usage_events."""

    def _seed(self, db: Path, rows: list[dict]) -> None:
        ensure_db(db)
        conn = connect(db)
        try:
            for r in rows:
                conn.execute(
                    "INSERT INTO usage_events(ts, session_id, model, state, input_tokens, "
                    "output_tokens, cache_read_input_tokens, cache_creation_input_tokens, "
                    "cost_usd) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        r["ts"],
                        r.get("session_id"),
                        r.get("model"),
                        None,
                        r.get("input_tokens"),
                        r.get("output_tokens"),
                        r.get("cache_read_input_tokens", 0),
                        r.get("cache_creation_input_tokens", 0),
                        r.get("cost_usd"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def test_recent_usage_events_newest_first_and_filters(self, tmp_path: Path) -> None:

        db = tmp_path / "history.db"
        self._seed(
            db,
            [
                {
                    "ts": "2026-07-01T10:00:00Z",
                    "session_id": "a",
                    "model": "m1",
                    "input_tokens": 10,
                    "output_tokens": 1,
                    "cost_usd": 0.1,
                },
                {
                    "ts": "2026-07-01T11:00:00Z",
                    "session_id": "b",
                    "model": "m2",
                    "input_tokens": 20,
                    "output_tokens": 2,
                    "cost_usd": 0.2,
                },
            ],
        )
        rows = recent_usage_events(db=db)
        assert [r.model for r in rows] == ["m2", "m1"]  # newest (highest id) first
        assert recent_usage_events(model="m1", db=db)[0].session_id == "a"
        assert recent_usage_events(session_id="b", db=db)[0].model == "m2"
        assert recent_usage_events(since="2026-07-01T10:30:00Z", db=db) == [
            r for r in rows if r.model == "m2"
        ]

    def test_recent_usage_events_missing_db(self, tmp_path: Path) -> None:

        assert recent_usage_events(db=tmp_path / "no" / "history.db") == []

    def test_aggregate_usage_by_model(self, tmp_path: Path) -> None:
        import pytest


        db = tmp_path / "history.db"
        self._seed(
            db,
            [
                {
                    "ts": "t1",
                    "session_id": "a",
                    "model": "m1",
                    "input_tokens": 10,
                    "output_tokens": 1,
                    "cost_usd": 0.10,
                },
                {
                    "ts": "t2",
                    "session_id": "a",
                    "model": "m1",
                    "input_tokens": 30,
                    "output_tokens": 3,
                    "cost_usd": 0.30,
                },
                {
                    "ts": "t3",
                    "session_id": "b",
                    "model": "m2",
                    "input_tokens": 5,
                    "output_tokens": 5,
                    "cost_usd": None,
                },
            ],
        )
        agg = aggregate_usage("model", db=db)
        by_model = {a["model"]: a for a in agg}
        assert by_model["m1"]["events"] == 2
        assert by_model["m1"]["input_tokens"] == 40
        assert by_model["m1"]["cost_usd"] == pytest.approx(0.40)
        # unpriced model rows: NULL cost sums to 0 in SQLite SUM
        assert by_model["m2"]["events"] == 1

    def test_aggregate_usage_by_session(self, tmp_path: Path) -> None:

        db = tmp_path / "history.db"
        self._seed(
            db,
            [
                {
                    "ts": "t1",
                    "session_id": "a",
                    "model": "m1",
                    "input_tokens": 10,
                    "output_tokens": 1,
                    "cost_usd": 0.1,
                },
                {
                    "ts": "t2",
                    "session_id": "a",
                    "model": "m2",
                    "input_tokens": 20,
                    "output_tokens": 2,
                    "cost_usd": 0.2,
                },
            ],
        )
        agg = aggregate_usage("session", db=db)
        assert len(agg) == 1
        assert agg[0]["session"] == "a"
        assert agg[0]["events"] == 2
        assert agg[0]["input_tokens"] == 30
