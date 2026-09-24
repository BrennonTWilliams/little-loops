"""ENH-3538: nullable token components and per-observation provenance storage."""

from __future__ import annotations

import io
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.fake_host import emit, parse_directives
from little_loops.fsm.cost_graph import CostReport
from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.fsm.types import ActionResult
from little_loops.history_reader.usage import aggregate_usage, cost_attribution
from little_loops.observability.tracing import OTelAttributes, StreamingParityChecker
from little_loops.pricing import estimate_cost_usd
from little_loops.session_store import connect, ensure_db, record_usage_event
from little_loops.session_store.writers import _backfill_usage_events, _iter_events_with_host
from little_loops.subprocess_utils import (
    TokenUsage,
    _fire_legacy_usage,
    _stamp_usage,
    known_input_lower_bound,
    run_claude_command,
    usage_from_event,
)


def _rows(db: Path) -> list[sqlite3.Row]:
    conn = connect(db)
    try:
        conn.row_factory = sqlite3.Row
        return list(conn.execute("SELECT * FROM usage_events ORDER BY id"))
    finally:
        conn.close()


class TestUsageFromEvent:
    def test_missing_and_null_components_stay_none_zero_stays_zero(self) -> None:
        usage = usage_from_event(
            {
                "type": "result",
                "usage": {"input_tokens": 5, "output_tokens": 0, "cache_read_input_tokens": None},
            },
            default_model="m",
        )
        assert usage is not None
        assert (usage.input_tokens, usage.output_tokens) == (5, 0)
        assert usage.cache_read_tokens is None
        assert usage.cache_creation_tokens is None
        assert usage.provenance == "unknown"
        assert usage.host is None and usage.scope_kind == "unknown"

    def test_complete_result_event_is_unchanged(self) -> None:
        usage = usage_from_event(
            {
                "type": "result",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "cache_read_input_tokens": 3,
                    "cache_creation_input_tokens": 4,
                },
            },
            default_model="m",
        )
        assert usage == TokenUsage(1, 2, 3, 4, "m")


class TestStampAndCallbacks:
    def test_stamp_sets_host_scope_and_received_time(self) -> None:
        stamped = _stamp_usage(TokenUsage(1, 2, 3, 4, "m"), "codex")
        assert stamped.host == "codex"
        assert stamped.scope_kind == "invocation"
        assert stamped.observed_at_basis == "received"
        assert stamped.observed_at
        assert stamped.provenance == "unknown"

    def test_legacy_callback_only_when_all_known(self) -> None:
        calls: list[tuple[int, int]] = []
        _fire_legacy_usage(lambda i, o: calls.append((i, o)), TokenUsage(10, 5, 2, None, "m"))
        assert calls == [(12, 5)]
        calls.clear()
        _fire_legacy_usage(lambda i, o: calls.append((i, o)), TokenUsage(10, 5, None, 0, "m"))
        assert calls == []

    def test_lower_bound_sums_known_components(self) -> None:
        assert known_input_lower_bound(TokenUsage(10, 5, None, None, "m")) == (10, 5)
        assert known_input_lower_bound(TokenUsage(None, None, None, None, "m")) == (0, 0)


@pytest.fixture
def _fake_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("ll-fake-host") is None:
        pytest.skip("ll-fake-host not on PATH")
    monkeypatch.setenv("LL_HOST_CLI", "fake")


class TestFakeHostPartialEvents:
    def _emit(self, *lines: str) -> list[dict[str, Any]]:
        script = parse_directives("@@fake\n" + "\n".join(lines) + "\n@@end")
        out = io.StringIO()
        emit(script, stdout=out, stderr=io.StringIO())
        return [json.loads(line) for line in out.getvalue().splitlines() if line]

    def test_result_emits_cache_creation_by_default(self) -> None:
        (event,) = self._emit("result in=1 out=2 cache=3")
        assert event["usage"]["cache_creation_input_tokens"] == 0

    def test_turn_completed_emits_cache_write_zero_by_default(self) -> None:
        (event,) = self._emit("turn_completed in=1 out=2 cached=3")
        assert event["usage"]["cache_write_input_tokens"] == 0

    def test_turn_completed_omit_cache_write(self) -> None:
        (event,) = self._emit("turn_completed in=1 out=2 cached=3 omit=cache_write")
        assert "cache_write_input_tokens" not in event["usage"]

    def test_omit_and_explicit_null(self) -> None:
        (event,) = self._emit("result in=1 out=2 cache=null omit=create")
        assert event["usage"]["cache_read_input_tokens"] is None
        assert "cache_creation_input_tokens" not in event["usage"]

    def test_partial_event_drives_detailed_callback_with_host_stamp(
        self, _fake_host_env: None
    ) -> None:
        seen: list[TokenUsage] = []
        legacy: list[tuple[int, int]] = []
        run_claude_command(
            "@@fake\nresult in=7 out=3 cache=null\n@@end",
            timeout=10,
            on_usage=lambda i, o: legacy.append((i, o)),
            on_usage_detailed=seen.append,
        )
        assert legacy == []  # incomplete: legacy two-int callback suppressed
        (usage,) = seen
        assert usage.cache_read_tokens is None
        assert (usage.input_tokens, usage.output_tokens, usage.cache_creation_tokens) == (7, 3, 0)
        assert usage.host == "fake"
        assert usage.scope_kind == "invocation"
        assert usage.observed_at_basis == "received"


class TestPricing:
    def test_none_component_yields_none_cost(self) -> None:
        assert estimate_cost_usd("claude-sonnet-4-6", 10, 10, None, 0) is None
        assert estimate_cost_usd("claude-sonnet-4-6", 10, 10, 0, 0) == pytest.approx(
            estimate_cost_usd("claude-sonnet-4-6", 10, 10)
        )
        assert estimate_cost_usd("claude-sonnet-4-6", 0, 0, 0, 0) == 0.0


class TestRecordUsageEvent:
    def test_defaults_are_unknown_and_none_cost(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        record_usage_event(
            db,
            run_id="r",
            ts="2026-01-01T00:00:00Z",
            state="s",
            model="claude-sonnet-4-6",
            input_tokens=1,
            output_tokens=2,
            cache_read_tokens=None,
            cache_creation_tokens=0,
        )
        (row,) = _rows(db)
        assert row["cache_read_input_tokens"] is None
        assert row["cache_creation_input_tokens"] == 0
        assert row["cost_usd"] is None
        assert row["provenance"] == "unknown"
        assert row["channel"] == "live"
        assert row["host"] is None and row["observed_at"] is None

    def test_metadata_round_trip(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        record_usage_event(
            db,
            run_id="r",
            ts="t",
            state=None,
            model="m",
            input_tokens=1,
            output_tokens=1,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            host="codex",
            provider_vendor="openai",
            scope_kind="invocation",
            observed_at="2026-01-02T00:00:00Z",
            observed_at_basis="received",
            invocation_id="inv",
        )
        (row,) = _rows(db)
        assert (row["host"], row["provider_vendor"], row["scope_kind"]) == (
            "codex",
            "openai",
            "invocation",
        )
        assert (row["observed_at"], row["observed_at_basis"]) == (
            "2026-01-02T00:00:00Z",
            "received",
        )
        assert row["invocation_id"] == "inv"
        assert row["provenance"] == "unknown"


def _transcript_line(usage: dict[str, Any], ts: str | None = "2026-01-01T00:00:00Z") -> str:
    record: dict[str, Any] = {
        "type": "assistant",
        "sessionId": "sess",
        "message": {"model": "claude-sonnet-4-6", "usage": usage},
    }
    if ts:
        record["timestamp"] = ts
    return json.dumps(record)


class TestReplay:
    def _cursor(self, db: Path, rows: list[tuple[str, str, str | None]]) -> sqlite3.Cursor:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE raw_events(raw_line TEXT, source_path TEXT, host TEXT)")
        conn.executemany("INSERT INTO raw_events VALUES(?, ?, ?)", rows)
        return conn.execute("SELECT raw_line, source_path, host FROM raw_events")

    def test_iterator_preserves_host_and_jsonl_source_has_none(self, tmp_path: Path) -> None:
        cursor = self._cursor(tmp_path / "x", [("{}", "a", "codex"), ("{}", "b", None)])
        assert [(lbl, host) for _, lbl, host in _iter_events_with_host(cursor)] == [
            ("a", "codex"),
            ("b", None),
        ]
        jsonl = tmp_path / "t.jsonl"
        jsonl.write_text("{}\n")
        assert [host for _, _, host in _iter_events_with_host([jsonl])] == [None]

    def test_backfill_writes_metadata_and_none_cost_for_missing_component(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        full = {
            "input_tokens": 1,
            "output_tokens": 2,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
        partial = {"input_tokens": 1, "output_tokens": 2}
        cursor = self._cursor(
            db,
            [
                (_transcript_line(full), "f1", "claude-code"),
                (_transcript_line(partial), "f2", None),
                (_transcript_line(full, ts=None), "f3", "codex"),
            ],
        )
        conn = connect(db)
        try:
            assert _backfill_usage_events(conn, cursor) == 3
            conn.commit()
        finally:
            conn.close()
        rows = _rows(db)
        assert rows[0]["cost_usd"] is not None
        assert rows[0]["host"] == "claude-code" and rows[0]["provider_vendor"] == "anthropic"
        assert rows[0]["scope_kind"] == "request"
        assert rows[0]["observed_at_basis"] == "event"
        assert rows[0]["observed_at"] == "2026-01-01T00:00:00Z"
        assert rows[0]["provenance"] == "unknown" and rows[0]["channel"] == "transcript"
        assert rows[1]["cost_usd"] is None
        assert rows[1]["host"] is None and rows[1]["provider_vendor"] is None
        assert rows[2]["observed_at"] is None and rows[2]["observed_at_basis"] is None


class _Runner:
    def __init__(self, usage: list[TokenUsage]) -> None:
        self._usage = usage

    def run(self, action: str, timeout: int, is_slash_command: bool, **kwargs: Any) -> ActionResult:
        return ActionResult(
            output="", stderr="", exit_code=0, duration_ms=1, usage_events=list(self._usage)
        )


def _run_loop(usage: list[TokenUsage]) -> tuple[FSMExecutor, list[dict[str, Any]]]:
    fsm = FSMLoop(
        name="t",
        initial="a",
        states={"a": StateConfig(action="x.sh", on_yes="done"), "done": StateConfig(terminal=True)},
    )
    executor = FSMExecutor(fsm, action_runner=_Runner(usage))
    events: list[dict[str, Any]] = []
    executor.event_callback = events.append  # type: ignore[assignment]
    with (
        patch("little_loops.session_store.record_loop_run_summary"),
        patch("little_loops.session_store.record_usage_event"),
    ):
        executor.run()
    return executor, [e for e in events if e.get("event") == "action_complete"]


class TestExecutorPayload:
    def test_known_contributors_summed_with_missing_counts(self) -> None:
        _, completes = _run_loop(
            [
                TokenUsage(10, 5, None, 0, "m"),
                TokenUsage(20, 5, None, None, "m"),
            ]
        )
        payload = completes[0]
        assert payload["usage_event_count"] == 2
        assert payload["input_tokens"] == 30 and payload["input_tokens_missing"] == 0
        assert payload["cache_read_tokens"] is None and payload["cache_read_tokens_missing"] == 2
        assert payload["cache_creation_tokens"] == 0
        assert payload["cache_creation_tokens_missing"] == 1

    def test_complete_payload_is_numeric_with_zero_missing(self) -> None:
        _, completes = _run_loop([TokenUsage(1, 2, 3, 4, "m")])
        payload = completes[0]
        assert (
            payload["input_tokens"],
            payload["output_tokens"],
            payload["cache_read_tokens"],
            payload["cache_creation_tokens"],
        ) == (1, 2, 3, 4)
        assert not any(payload[f"{c}_missing"] for c in ("input_tokens", "output_tokens"))

    def test_finish_persists_host_metadata_and_vendor(self) -> None:
        usage = _stamp_usage(TokenUsage(1, 2, 3, 4, "m"), "codex")
        fsm = FSMLoop(
            name="t",
            initial="a",
            states={
                "a": StateConfig(action="x.sh", on_yes="done"),
                "done": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm, action_runner=_Runner([usage]))
        with (
            patch("little_loops.session_store.record_loop_run_summary"),
            patch("little_loops.session_store.record_usage_event") as record,
            patch("little_loops.config.BRConfig") as cfg,
        ):
            cfg.return_value.analytics_capture.usage_events = True
            executor.run()
        kwargs = record.call_args.kwargs
        assert kwargs["host"] == "codex" and kwargs["provider_vendor"] == "openai"
        assert kwargs["provenance"] == "unknown"
        assert kwargs["scope_kind"] == "invocation"
        assert kwargs["observed_at_basis"] == "received"
        assert kwargs["observed_at"] == usage.observed_at


class TestCostGraphRoundTrip:
    def _write(self, tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
        path = tmp_path / "usage.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        return path

    def test_incomplete_state_is_unpriced_and_survives_json_round_trip(
        self, tmp_path: Path
    ) -> None:
        base = {"model": "claude-sonnet-4-6", "input_tokens": 100, "output_tokens": 10}
        path = self._write(
            tmp_path,
            [
                {"state": "ok", **base, "cache_read_tokens": 0, "cache_creation_tokens": 0},
                {"state": "gap", **base, "cache_read_tokens": None, "cache_creation_tokens": 0},
                {
                    "state": "partial",
                    **base,
                    "cache_read_tokens": 5,
                    "cache_read_tokens_missing": 1,
                    "cache_creation_tokens": 0,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(path)
        by_state = {s.state: s for s in report.states}
        assert by_state["ok"].cost_usd is not None and not by_state["ok"].has_unknown_model
        assert by_state["gap"].cost_usd is None and by_state["gap"].cache_read_tokens is None
        assert by_state["partial"].cost_usd is None
        assert by_state["partial"].cache_read_tokens == 5
        assert by_state["partial"].cache_read_tokens_missing == 1
        assert report.totals["cost_usd"] is None

        out = tmp_path / "cost.json"
        report.write_json(out)
        loaded = CostReport.read_json(out)
        assert loaded is not None
        loaded_by_state = {s.state: s for s in loaded.states}
        assert loaded_by_state["gap"].cost_usd is None and loaded_by_state["gap"].has_unknown_model
        assert loaded_by_state["gap"].cache_read_tokens is None
        assert loaded_by_state["partial"].cache_read_tokens_missing == 1
        assert loaded_by_state["ok"].cost_usd == pytest.approx(by_state["ok"].cost_usd)
        assert loaded.totals["cost_usd"] is None
        table = loaded.table()
        assert "n/a" in table and "$0.0000" not in table
        assert "5+" in table  # partial cache subtotal is marked

    def test_complete_json_has_no_missing_keys_and_legacy_numeric_reads(
        self, tmp_path: Path
    ) -> None:
        path = self._write(
            tmp_path,
            [
                {
                    "state": "s",
                    "model": "claude-sonnet-4-6",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                }
            ],
        )
        report = CostReport.from_usage_jsonl(path)
        assert not any(k.endswith("_missing") for k in report.to_dict()["states"][0])
        legacy = tmp_path / "legacy.json"
        legacy.write_text(
            json.dumps(
                {
                    "states": [
                        {
                            "state": "s",
                            "iterations": 1,
                            "input_tokens": 1,
                            "output_tokens": 1,
                            "cache_read_tokens": 0,
                            "cache_creation_tokens": 0,
                            "cost_usd": 0.0,
                            "wallclock_ms": 0,
                        }
                    ],
                    "totals": {},
                }
            )
        )
        loaded = CostReport.read_json(legacy)
        assert loaded is not None
        assert loaded.states[0].cost_usd == 0.0 and not loaded.states[0].has_unknown_model
        assert loaded.states[0].input_tokens_missing == 0


def _insert(db: Path, rows: list[tuple[int | None, float | None]]) -> None:
    conn = connect(db)
    try:
        for tokens, cost in rows:
            conn.execute(
                "INSERT INTO usage_events(ts, model, input_tokens, output_tokens, "
                "cache_read_input_tokens, cache_creation_input_tokens, cost_usd, "
                "invocation_id, channel) VALUES('t', 'm', ?, 0, 0, 0, ?, 'inv', 'live')",
                (tokens, cost),
            )
        conn.commit()
    finally:
        conn.close()


class TestSqlCompleteness:
    @pytest.mark.parametrize(
        ("rows", "total", "missing"),
        [
            ([(100, 1.0), (None, None)], None, 1),
            ([(None, None), (None, None)], None, 2),
            ([(0, 0.0), (0, 0.0)], 0, 0),
        ],
    )
    def test_aggregate_usage(
        self, tmp_path: Path, rows: list[tuple[int | None, float | None]], total: Any, missing: int
    ) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        _insert(db, rows)
        (result,) = aggregate_usage(db=db)
        assert result["input_tokens"] == total
        assert result["input_tokens_missing"] == missing
        assert (result["cost_usd"] is None) == (missing > 0)
        assert result["output_tokens"] == 0

    def test_cost_attribution_omits_partial_attribute_keeps_complete_sibling(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        _insert(db, [(100, 1.0), (None, None)])
        (result,) = cost_attribution(db=db)
        assert "gen_ai.usage.input_tokens" not in result
        assert result["gen_ai.usage.output_tokens"] == 0
        assert result["cost_usd"] is None
        assert result["input_tokens_missing"] == 1


@dataclass
class _U:
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None


class TestParity:
    def test_unknown_on_one_or_both_sides_is_not_within_threshold(self) -> None:
        checker = StreamingParityChecker()
        known = _U(1, 1, 1, 1)
        one_sided = _U(1, 1, None, 1)
        assert not checker.within_threshold(known, one_sided)
        assert not checker.within_threshold(one_sided, one_sided)
        diff = {d.field: d for d in checker.diff(known, one_sided)}
        assert diff["cache_read_tokens"].diff_pct is None
        assert (
            diff["cache_read_tokens"].blocking == 1.0
            and diff["cache_read_tokens"].streaming is None
        )

    def test_partial_subtotal_is_incomplete(self) -> None:
        checker = StreamingParityChecker()
        partial = {
            "input_tokens": 1,
            "input_tokens_missing": 1,
            "output_tokens": 1,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
        }
        assert not checker.within_threshold(partial, partial)

    def test_complete_comparisons_keep_behavior(self) -> None:
        checker = StreamingParityChecker()
        zero = _U(0, 0, 0, 0)
        assert checker.within_threshold(zero, zero)
        assert not checker.within_threshold(_U(100, 1, 1, 1), _U(200, 1, 1, 1))


class TestOtelStamp:
    def test_none_and_partial_omitted_zero_kept(self) -> None:
        attrs = OTelAttributes.from_usage(_U(None, 0, 4, 5))
        assert "gen_ai.usage.input_tokens" not in attrs
        assert attrs["gen_ai.usage.output_tokens"] == 0


class TestLegacyCallbackConsumers:
    def test_context_guard_gets_lower_bound_when_component_missing(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        from little_loops.issue_manager import run_with_continuation

        result = MagicMock(returncode=0, stdout="done", stderr="", args=["claude"])
        forwarded: list[tuple[int, int]] = []

        def fake_run(command: str, *args: Any, **kwargs: Any) -> Any:
            # A missing cache_read suppresses the legacy callback; the detailed
            # callback still carries the observation.
            kwargs["on_usage_detailed"](TokenUsage(1000, 200, None, 0, "m"))
            return result

        with (
            patch("little_loops.issue_manager.run_claude_command", side_effect=fake_run),
            patch("little_loops.issue_manager.detect_context_handoff", return_value=False),
        ):
            run_with_continuation(
                "/ll:manage-issue bug fix BUG-1",
                MagicMock(),
                repo_path=tmp_path,
                max_continuations=0,
                context_limit=200_000,
                on_usage=lambda i, o: forwarded.append((i, o)),
            )
        assert forwarded == [(1000, 200)]


class TestBaselineUnavailable:
    def _executor(self) -> FSMExecutor:
        fsm = FSMLoop(
            name="t",
            initial="a",
            states={
                "a": StateConfig(action="x.sh", on_yes="done"),
                "done": StateConfig(terminal=True),
            },
        )
        return FSMExecutor(fsm, action_runner=_Runner([]))

    def _run(self, harness: list[TokenUsage], baseline: list[TokenUsage]) -> dict[str, Any]:
        executor = self._executor()
        events: list[dict[str, Any]] = []
        executor.event_callback = events.append  # type: ignore[assignment]

        def harness_arm(action: str, state: Any, ctx: Any, on_usage: Any) -> ActionResult:
            for u in harness:
                on_usage((u.input_tokens or 0) + (u.cache_read_tokens or 0), u.output_tokens or 0)
            return ActionResult("h", "", 0, 1, usage_events=harness)

        def baseline_arm(skill: str, state: Any, on_usage: Any) -> ActionResult:
            for u in baseline:
                on_usage((u.input_tokens or 0) + (u.cache_read_tokens or 0), u.output_tokens or 0)
            return ActionResult("b", "", 0, 1, usage_events=baseline)

        executor._run_action = harness_arm  # type: ignore[method-assign]
        executor._run_baseline_arm = baseline_arm  # type: ignore[method-assign]
        ctx = executor._build_context()
        with patch("little_loops.fsm.executor.evaluate_blind_comparator", return_value={}):
            executor._execute_with_baseline(
                executor.fsm.states["a"], ctx, {"enabled": True, "skill": "s"}
            )
        (event,) = [e for e in events if e.get("event") == "baseline_complete"]
        return event

    def test_complete_totals_unchanged(self) -> None:
        event = self._run([TokenUsage(10, 5, 0, 0, "m")], [TokenUsage(4, 1, 0, 0, "m")])
        assert (event["harness_tokens"], event["baseline_tokens"]) == (15, 5)

    def test_incomplete_arm_makes_comparison_unavailable(self) -> None:
        event = self._run([TokenUsage(10, 5, None, 0, "m")], [TokenUsage(4, 1, 0, 0, "m")])
        assert event["harness_tokens"] is None and event["baseline_tokens"] is None


class TestAbWriterMedians:
    def test_none_when_any_item_unavailable(self) -> None:
        from little_loops.ab_writer import calculate_ab_summary

        items = [
            {
                "harness_pass": True,
                "baseline_pass": True,
                "harness_tokens": 10,
                "baseline_tokens": 5,
            },
            {
                "harness_pass": True,
                "baseline_pass": True,
                "harness_tokens": None,
                "baseline_tokens": None,
            },
        ]
        summary = calculate_ab_summary(items)
        assert summary.median_tokens_harness is None
        assert summary.median_tokens_baseline is None
        complete = calculate_ab_summary(items[:1])
        assert (complete.median_tokens_harness, complete.median_tokens_baseline) == (10, 5)
