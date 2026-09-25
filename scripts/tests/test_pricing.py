"""Tests for the pricing module."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops import pricing
from little_loops.pricing import BATCH_DISCOUNT, MODEL_PRICING, _event_date, estimate_cost_usd

SYNTHETIC_MODEL = "claude-synthetic-intro"

# Live rates (USD/Mtok): input, output, cache_read, cache_creation. Checked 2026-09-24.
LIVE_RATES: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5-1": (10.0, 50.0, 0.25, 12.50),
    "claude-fable-5": (10.0, 50.0, 1.0, 12.50),
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-opus-5": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-8": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-7": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-6": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-5": (5.0, 25.0, 0.50, 6.25),
    "claude-sonnet-5": (2.0, 10.0, 0.20, 2.50),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-3-7": (3.0, 15.0, 0.30, 3.75),
    "claude-haiku-4-5": (1.0, 5.0, 0.10, 1.25),
    "claude-haiku-4-5-20251001": (1.0, 5.0, 0.10, 1.25),
    "claude-haiku-3-5": (0.80, 4.0, 0.08, 1.0),
}


@pytest.fixture
def synthetic_intro_pricing(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Register a synthetic model with an intro rate expiring 2026-08-31.

    Standard rate is 3/15/0.30/3.75; intro rate is 2/10/0.20/2.50. Yields the model id.
    """
    monkeypatch.setitem(
        MODEL_PRICING,
        SYNTHETIC_MODEL,
        {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_creation": 3.75},
    )
    monkeypatch.setitem(
        pricing.INTRO_PRICING,
        SYNTHETIC_MODEL,
        {
            "expires": "2026-08-31",
            "input": 2.0,
            "output": 10.0,
            "cache_read": 0.20,
            "cache_creation": 2.50,
        },
    )
    yield SYNTHETIC_MODEL


class TestModelPricing:
    def test_known_models_present(self) -> None:
        assert "claude-opus-4-7" in MODEL_PRICING
        assert "claude-sonnet-4-6" in MODEL_PRICING
        assert "claude-haiku-4-5-20251001" in MODEL_PRICING
        assert "claude-sonnet-5" in MODEL_PRICING
        assert "claude-opus-4-8" in MODEL_PRICING
        assert "claude-fable-5" in MODEL_PRICING

    def test_pricing_fields_present(self) -> None:
        for model, prices in MODEL_PRICING.items():
            assert "input" in prices, f"{model} missing input price"
            assert "output" in prices, f"{model} missing output price"
            assert "cache_read" in prices, f"{model} missing cache_read price"
            assert "cache_creation" in prices, f"{model} missing cache_creation price"

    def test_output_more_expensive_than_input(self) -> None:
        for model, prices in MODEL_PRICING.items():
            assert prices["output"] > prices["input"], (
                f"{model}: output should cost more than input"
            )


class TestLiveRates:
    @pytest.mark.parametrize("model", sorted(LIVE_RATES))
    def test_rates_match_live_table(self, model: str) -> None:
        inp, out, cr, cc = LIVE_RATES[model]
        assert MODEL_PRICING[model] == {
            "input": inp,
            "output": out,
            "cache_read": cr,
            "cache_creation": cc,
        }

    def test_new_alias_target_prices(self) -> None:
        assert estimate_cost_usd(
            "claude-opus-5-5", 1_000_000, 1_000_000, 1_000_000, 1_000_000
        ) == pytest.approx(4.0 + 20.0 + 0.20 + 5.0)
        assert estimate_cost_usd("claude-fable-5-1", 0, 0, 1_000_000, 0) == pytest.approx(0.25)

    def test_haiku_ids_share_one_rate_dict(self) -> None:
        assert MODEL_PRICING["claude-haiku-4-5"] is MODEL_PRICING["claude-haiku-4-5-20251001"]

    def test_every_model_pinned(self) -> None:
        assert set(MODEL_PRICING) == set(LIVE_RATES)

    def test_sonnet_5_standard_rate_any_date(self) -> None:
        assert estimate_cost_usd("claude-sonnet-5", 1_000_000, 1_000_000) == 12.0
        with patch("little_loops.pricing.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 15)
            mock_date.fromisoformat = date.fromisoformat
            assert estimate_cost_usd("claude-sonnet-5", 1_000_000, 1_000_000) == 12.0

    @pytest.mark.parametrize("model", sorted(LIVE_RATES))
    def test_batch_halves_each_rate(self, model: str) -> None:
        sync = estimate_cost_usd(model, 1_000_000, 1_000_000, 1_000_000, 1_000_000)
        batch = estimate_cost_usd(model, 1_000_000, 1_000_000, 1_000_000, 1_000_000, is_batch=True)
        assert sync is not None and batch is not None
        assert batch == sync * BATCH_DISCOUNT


class TestEstimateCostUsd:
    def test_known_model_returns_float(self) -> None:
        cost = estimate_cost_usd("claude-sonnet-4-6", 1000, 200)
        assert cost is not None
        assert cost > 0.0

    def test_unknown_model_returns_none(self) -> None:
        assert estimate_cost_usd("unknown-model-xyz", 1000, 200) is None

    def test_zero_tokens_returns_zero(self) -> None:
        cost = estimate_cost_usd("claude-sonnet-4-6", 0, 0, 0, 0)
        assert cost == 0.0

    def test_cache_read_cheaper_than_input(self) -> None:
        # 1M cache_read tokens should cost less than 1M input tokens
        cost_input = estimate_cost_usd("claude-opus-4-7", 1_000_000, 0)
        cost_cache = estimate_cost_usd("claude-opus-4-7", 0, 0, 1_000_000, 0)
        assert cost_input is not None
        assert cost_cache is not None
        assert cost_cache < cost_input

    def test_accuracy_within_15_percent(self) -> None:
        # 1M input + 200K output for sonnet-4-6 = $3.00 + $3.00 = $6.00
        cost = estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 200_000)
        assert cost is not None
        expected = 3.0 + 15.0 * 0.2  # $3.00 + $3.00
        assert abs(cost - expected) / expected < 0.15

    def test_all_four_fields_contribute(self) -> None:
        cost_all = estimate_cost_usd("claude-opus-4-7", 100, 100, 100, 100)
        cost_input_only = estimate_cost_usd("claude-opus-4-7", 100, 0, 0, 0)
        assert cost_all is not None
        assert cost_input_only is not None
        assert cost_all > cost_input_only


class TestIntroPricing:
    def test_pre_expiry_uses_intro_rate(self, synthetic_intro_pricing: str) -> None:
        with patch("little_loops.pricing.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 15)
            mock_date.fromisoformat = date.fromisoformat
            cost = estimate_cost_usd(synthetic_intro_pricing, 1_000_000, 1_000_000)
        assert cost == 2.0 + 10.0

    def test_post_expiry_uses_standard_rate(self, synthetic_intro_pricing: str) -> None:
        with patch("little_loops.pricing.date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 1)
            mock_date.fromisoformat = date.fromisoformat
            cost = estimate_cost_usd(synthetic_intro_pricing, 1_000_000, 1_000_000)
        assert cost == 3.0 + 15.0

    def test_boundary_2026_08_31_uses_intro_rate(self, synthetic_intro_pricing: str) -> None:
        with patch("little_loops.pricing.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 31)
            mock_date.fromisoformat = date.fromisoformat
            cost = estimate_cost_usd(synthetic_intro_pricing, 1_000_000, 1_000_000)
        assert cost == 2.0 + 10.0

    def test_unaffected_model_regression(self, synthetic_intro_pricing: str) -> None:
        with patch("little_loops.pricing.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 15)
            mock_date.fromisoformat = date.fromisoformat
            cost = estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert cost == 3.0 + 15.0

    def test_intro_sub_dict_has_all_rate_keys(self, synthetic_intro_pricing: str) -> None:
        for model, rates in pricing.INTRO_PRICING.items():
            for key in ("input", "output", "cache_read", "cache_creation", "expires"):
                assert key in rates, f"{model} intro pricing missing {key}"


class TestBatchDiscount:
    def test_is_batch_false_by_default(self) -> None:
        cost_default = estimate_cost_usd("claude-sonnet-4-6", 1000, 200)
        cost_explicit_false = estimate_cost_usd("claude-sonnet-4-6", 1000, 200, 0, 0, False)
        assert cost_default == cost_explicit_false

    def test_is_batch_halves_cost(self) -> None:
        cost_sync = estimate_cost_usd("claude-sonnet-4-6", 1000, 200, 50, 50)
        cost_batch = estimate_cost_usd("claude-sonnet-4-6", 1000, 200, 50, 50, is_batch=True)
        assert cost_sync is not None
        assert cost_batch is not None
        assert cost_batch == cost_sync * BATCH_DISCOUNT

    def test_is_batch_unknown_model_returns_none(self) -> None:
        assert estimate_cost_usd("unknown-model-xyz", 1000, 200, is_batch=True) is None

    def test_is_batch_zero_tokens_returns_zero(self) -> None:
        assert estimate_cost_usd("claude-sonnet-4-6", 0, 0, 0, 0, is_batch=True) == 0.0


INTRO_TOTAL = 2.0 + 10.0
STANDARD_TOTAL = 3.0 + 15.0
_M = 1_000_000


def _pin_today(day: date) -> patch[object]:  # type: ignore[type-arg]
    mock = patch("little_loops.pricing.date")
    m = mock.start()
    m.today.return_value = day
    m.fromisoformat = date.fromisoformat
    return mock


class TestEventDate:
    @pytest.mark.parametrize(
        "ts",
        ["2026-08-31T23:30:00-05:00", "2026-09-01T04:30:00Z", "2026-09-01T04:30:00"],
    )
    def test_normalises_to_utc_date(self, ts: str) -> None:
        assert _event_date(ts) == date(2026, 9, 1)

    @pytest.mark.parametrize("ts", [None, "", "garbage", "2026-13-45T00:00:00Z"])
    def test_unparseable_returns_none(self, ts: str | None) -> None:
        assert _event_date(ts) is None


class TestAsOf:
    def test_event_inside_window_after_expiry_uses_intro(
        self, synthetic_intro_pricing: str
    ) -> None:
        patcher = _pin_today(date(2026, 9, 15))
        try:
            cost = estimate_cost_usd(synthetic_intro_pricing, _M, _M, as_of=date(2026, 8, 15))
        finally:
            patcher.stop()
        assert cost == INTRO_TOTAL

    def test_event_after_expiry_inside_window_uses_standard(
        self, synthetic_intro_pricing: str
    ) -> None:
        patcher = _pin_today(date(2026, 8, 15))
        try:
            cost = estimate_cost_usd(synthetic_intro_pricing, _M, _M, as_of=date(2026, 9, 1))
        finally:
            patcher.stop()
        assert cost == STANDARD_TOTAL

    def test_as_of_none_means_today(self, synthetic_intro_pricing: str) -> None:
        patcher = _pin_today(date(2026, 9, 15))
        try:
            cost = estimate_cost_usd(synthetic_intro_pricing, _M, _M, as_of=None)
        finally:
            patcher.stop()
        assert cost == STANDARD_TOTAL


def _pin_expired_today() -> patch[object]:  # type: ignore[type-arg]
    return _pin_today(date(2026, 9, 15))


class TestEventDatePricingCallSites:
    def _record(self, db: Path, model: str, ts: str, observed_at: str | None) -> float | None:
        from little_loops.session_store import connect, ensure_db, record_usage_event

        ensure_db(db)
        record_usage_event(
            db,
            run_id="r",
            ts=ts,
            state="s",
            model=model,
            input_tokens=_M,
            output_tokens=_M,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            observed_at=observed_at,
        )
        conn = connect(db)
        try:
            return conn.execute("SELECT cost_usd FROM usage_events").fetchone()[0]
        finally:
            conn.close()

    @pytest.mark.parametrize(
        ("ts", "observed_at", "expected"),
        [
            ("2026-09-10T00:00:00Z", "2026-08-15T00:00:00Z", INTRO_TOTAL),  # observed_at wins
            ("2026-08-15T00:00:00Z", "not-a-date", INTRO_TOTAL),  # falls through to ts
            ("bad", "also-bad", STANDARD_TOTAL),  # both malformed -> today (expired)
        ],
    )
    def test_live_writer_precedence(
        self,
        tmp_path: Path,
        synthetic_intro_pricing: str,
        ts: str,
        observed_at: str,
        expected: float,
    ) -> None:
        patcher = _pin_expired_today()
        try:
            cost = self._record(tmp_path / "h.db", synthetic_intro_pricing, ts, observed_at)
        finally:
            patcher.stop()
        assert cost == expected

    def test_replay_prices_by_record_timestamp(
        self, tmp_path: Path, synthetic_intro_pricing: str
    ) -> None:
        from little_loops.session_store import connect, ensure_db
        from little_loops.session_store.writers import _backfill_usage_events

        db = tmp_path / "h.db"
        ensure_db(db)
        usage = {
            "input_tokens": _M,
            "output_tokens": _M,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }

        def line(ts: str | None) -> str:
            rec: dict[str, object] = {
                "type": "assistant",
                "sessionId": "sess",
                "message": {"model": synthetic_intro_pricing, "usage": usage},
            }
            if ts:
                rec["timestamp"] = ts
            return json.dumps(rec)

        src = sqlite3.connect(":memory:")
        src.execute("CREATE TABLE raw_events(raw_line TEXT, source_path TEXT, host TEXT)")
        src.executemany(
            "INSERT INTO raw_events VALUES(?, ?, NULL)",
            [(line("2026-08-15T00:00:00Z"), "a"), (line("junk"), "b"), (line(None), "c")],
        )
        cursor = src.execute("SELECT raw_line, source_path, host FROM raw_events")
        patcher = _pin_expired_today()
        conn = connect(db)
        try:
            _backfill_usage_events(conn, cursor)
            conn.commit()
            costs = [r[0] for r in conn.execute("SELECT cost_usd FROM usage_events ORDER BY id")]
        finally:
            conn.close()
            patcher.stop()
        assert costs == [INTRO_TOTAL, STANDARD_TOTAL, STANDARD_TOTAL]

    def test_cost_graph_prices_by_row_timestamp(
        self, tmp_path: Path, synthetic_intro_pricing: str
    ) -> None:
        from little_loops.fsm.cost_graph import CostReport

        base = {
            "state": "s",
            "model": synthetic_intro_pricing,
            "input_tokens": _M,
            "output_tokens": _M,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
        }
        p = tmp_path / "usage.jsonl"
        p.write_text(
            "\n".join(
                json.dumps({**base, "state": name, "timestamp": ts})
                for name, ts in [
                    ("inside", "2026-08-15T00:00:00Z"),
                    ("legacy", ""),
                    ("bad", "junk"),
                ]
            )
            + "\n"
        )
        patcher = _pin_expired_today()
        try:
            report = CostReport.from_usage_jsonl(p)
        finally:
            patcher.stop()
        by_state = {s.state: s.cost_usd for s in report.states}
        assert by_state == {
            "inside": INTRO_TOTAL,
            "legacy": STANDARD_TOTAL,
            "bad": STANDARD_TOTAL,
        }
