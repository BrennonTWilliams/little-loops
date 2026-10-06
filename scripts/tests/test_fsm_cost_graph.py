"""Tests for scripts/little_loops/fsm/cost_graph.py (ENH-2477).

Locks the stable JSON shape for per-state cost attribution.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.fsm.cost_graph import CostReport, PerStateCost


@pytest.fixture
def fixture_jsonl(tmp_path: Path) -> Path:
    """Three usage rows across two states; deterministic tokens/cost."""
    p = tmp_path / "usage.jsonl"
    rows = [
        {
            "state": "research",
            "iteration": 1,
            "action_type": "prompt",
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_tokens": 10,
            "cache_creation_tokens": 5,
            "model": "claude-sonnet-4-6",
            "timestamp": "2026-07-07T10:00:00Z",
            "wallclock_ms": 1500,
        },
        {
            "state": "research",
            "iteration": 2,
            "action_type": "prompt",
            "input_tokens": 200,
            "output_tokens": 80,
            "cache_read_tokens": 30,
            "cache_creation_tokens": 7,
            "model": "claude-sonnet-4-6",
            "timestamp": "2026-07-07T10:00:05Z",
            "wallclock_ms": 2200,
        },
        {
            "state": "summarize",
            "iteration": 3,
            "action_type": "prompt",
            "input_tokens": 50,
            "output_tokens": 25,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "model": "claude-sonnet-4-6",
            "timestamp": "2026-07-07T10:00:10Z",
            "wallclock_ms": 800,
        },
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


@pytest.fixture
def empty_jsonl(tmp_path: Path) -> Path:
    p = tmp_path / "usage.jsonl"
    p.write_text("", encoding="utf-8")
    return p


@pytest.fixture
def malformed_jsonl(tmp_path: Path) -> Path:
    p = tmp_path / "usage.jsonl"
    p.write_text("not json\n{valid: true}\n", encoding="utf-8")
    return p


class TestPerStateCost:
    """Unit tests for PerStateCost dataclass."""

    def test_defaults(self) -> None:
        c = PerStateCost(state="x")
        assert c.state == "x"
        assert c.iterations == 0
        assert c.input_tokens == 0
        assert c.output_tokens == 0
        assert c.cache_read_tokens == 0
        assert c.cache_creation_tokens == 0
        assert c.cost_usd == 0.0
        assert c.wallclock_ms == 0
        assert c.has_unknown_model is False

    def test_to_dict_exact_keys(self) -> None:
        c = PerStateCost(
            state="research",
            iterations=2,
            input_tokens=300,
            output_tokens=130,
            cache_read_tokens=40,
            cache_creation_tokens=12,
            cost_usd=0.0123,
            wallclock_ms=3700,
        )
        d = c.to_dict()
        assert set(d.keys()) == {
            "state",
            "iterations",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_creation_tokens",
            "cost_usd",
            "wallclock_ms",
        }
        assert d["state"] == "research"
        assert d["iterations"] == 2
        assert d["cache_read_tokens"] == 40
        assert d["cache_creation_tokens"] == 12

    def test_table_row_preserves_existing_column_layout(self) -> None:
        """Byte-identical column output to the existing _print_usage_summary table.

        Existing column order: state (24w left), invoc (5w right),
        input (8w right), output (8w right), cache (8w right), est_cost (10w right).
        """
        c = PerStateCost(
            state="research",
            iterations=2,
            input_tokens=300,
            output_tokens=130,
            cache_read_tokens=40,
            cache_creation_tokens=12,
            cost_usd=0.0123,
        )
        row = c.table_row()
        # Cache is the merged read+creation value: 40 + 12 = 52.
        assert "research" in row
        assert "2" in row  # invoc
        assert "300" in row  # input
        assert "130" in row  # output
        assert "52" in row  # cache (merged)
        assert "$0.0123" in row  # est_cost formatted

    def test_table_row_unknown_model_marker(self) -> None:
        c = PerStateCost(state="x", cost_usd=0.0, has_unknown_model=True)
        row = c.table_row()
        assert "n/a" in row


class TestCostReport:
    """Tests for CostReport aggregate (states + totals)."""

    def test_from_usage_jsonl_aggregates_per_state(self, fixture_jsonl: Path) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        assert len(report.states) == 2
        by_state = {s.state: s for s in report.states}
        assert by_state["research"].iterations == 2
        assert by_state["research"].input_tokens == 300
        assert by_state["research"].output_tokens == 130
        assert by_state["research"].cache_read_tokens == 40
        assert by_state["research"].cache_creation_tokens == 12
        assert by_state["research"].wallclock_ms == 3700
        assert by_state["summarize"].iterations == 1
        assert by_state["summarize"].wallclock_ms == 800

    def test_from_usage_jsonl_empty_file(self, empty_jsonl: Path) -> None:
        report = CostReport.from_usage_jsonl(empty_jsonl)
        assert report.states == []

    def test_from_usage_jsonl_skips_malformed_rows(self, malformed_jsonl: Path) -> None:
        # Should not raise; should return empty report.
        report = CostReport.from_usage_jsonl(malformed_jsonl)
        assert report.states == []

    def test_from_usage_jsonl_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "absent.jsonl"
        report = CostReport.from_usage_jsonl(missing)
        assert report.states == []

    def test_totals_aggregate_across_states(self, fixture_jsonl: Path) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        totals = report.totals
        # 100+200+50 = 350
        assert totals["input_tokens"] == 350
        # 50+80+25 = 155
        assert totals["output_tokens"] == 155
        # 10+30+0 = 40
        assert totals["cache_read_tokens"] == 40
        # 5+7+0 = 12
        assert totals["cache_creation_tokens"] == 12
        # 3 invocations total
        assert totals["iterations"] == 3
        assert "cost_usd" in totals
        assert "wallclock_ms" in totals

    def test_to_dict_top_level_shape(self, fixture_jsonl: Path) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        d = report.to_dict()
        assert set(d.keys()) == {"states", "totals"}
        assert isinstance(d["states"], list)
        assert isinstance(d["totals"], dict)
        # Each state entry must have the locked key set.
        for entry in d["states"]:
            assert {
                "state",
                "iterations",
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_creation_tokens",
                "cost_usd",
                "wallclock_ms",
            } <= set(entry.keys())

    def test_is_batch_row_applies_discount(self, tmp_path: Path) -> None:
        """FEAT-2716: a row with is_batch: true gets the 50% batch discount."""
        p = tmp_path / "usage.jsonl"
        row = {
            "state": "research",
            "iteration": 1,
            "action_type": "prompt",
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "model": "claude-sonnet-4-6",
            "timestamp": "2026-07-07T10:00:00Z",
            "wallclock_ms": 1000,
            "is_batch": True,
        }
        p.write_text(json.dumps(row) + "\n", encoding="utf-8")
        report = CostReport.from_usage_jsonl(p)
        assert len(report.states) == 1
        # (1000*3 + 200*15) / 1e6 = 0.006, halved by the batch discount = 0.003
        assert report.states[0].cost_usd == pytest.approx(0.003)

    def test_missing_is_batch_defaults_to_full_price(self, tmp_path: Path) -> None:
        """Rows without is_batch (pre-FEAT-2716 data) are priced at full rate."""
        p = tmp_path / "usage.jsonl"
        row = {
            "state": "research",
            "iteration": 1,
            "action_type": "prompt",
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "model": "claude-sonnet-4-6",
            "timestamp": "2026-07-07T10:00:00Z",
            "wallclock_ms": 1000,
        }
        p.write_text(json.dumps(row) + "\n", encoding="utf-8")
        report = CostReport.from_usage_jsonl(p)
        assert report.states[0].cost_usd == pytest.approx(0.006)

    def test_table_matches_existing_layout(self, fixture_jsonl: Path) -> None:
        """The full table() output must include the same header + separator."""
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        out = report.table()
        assert "state" in out
        assert "invoc" in out
        assert "input" in out
        assert "output" in out
        assert "cache" in out
        assert "est_cost" in out
        assert "-" * 68 in out  # the separator line from the existing function
        # Both states present.
        assert "research" in out
        assert "summarize" in out

    def test_write_json_round_trip(self, fixture_jsonl: Path, tmp_path: Path) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        out = tmp_path / "per_state.json"
        report.write_json(out)
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["states"][0]["state"] in {"research", "summarize"}
        assert loaded["totals"]["iterations"] == 3


class TestEnH3719UnpricedModelFooter:
    """ENH-3719: unpriced-model footer + diagnostic collection in CostReport.

    Tests the matrix per the issue's "Test 1: Parametrized classification
    matrix" spec. The table() footer:
      - names concrete unrecognized IDs verbatim (sorted, de-duplicated)
      - splits missing-identifier sentinels (unknown / None / "" / ws)
        into a separate line
      - includes concrete IDs even when their tokens are complete OR
        incomplete; known-priced rows do not appear
      - leaves the locked JSON shape unchanged (diagnostic lost on round-trip)
    """

    @staticmethod
    def _write_rows(tmp_path: Path, rows: list[dict]) -> Path:
        p = tmp_path / "usage.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return p

    def test_unknown_concrete_id_with_complete_tokens_is_named(self, tmp_path: Path) -> None:
        # A row whose model is unpriced but tokens are complete. The footer
        # names the ID; the row's state shows n/a.
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "research",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "claude-sonnet-4-6",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "wallclock_ms": 1500,
                },
                {
                    "state": "research",
                    "iteration": 2,
                    "action_type": "prompt",
                    "input_tokens": 200,
                    "output_tokens": 80,
                    "cache_read_tokens": 30,
                    "cache_creation_tokens": 7,
                    "model": "claude-future-99",
                    "timestamp": "2026-07-07T10:00:05Z",
                    "wallclock_ms": 2200,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        assert "claude-future-99" in report.unpriced_models
        out = report.table()
        assert "claude-future-99" in out
        assert "not priced" in out

    def test_unknown_concrete_id_with_incomplete_tokens_is_named(self, tmp_path: Path) -> None:
        # A row whose model is unpriced AND has incomplete tokens. Footer still
        # names the ID; the incomplete token behavior is unchanged.
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "research",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": None,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "claude-future-99",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "wallclock_ms": 1500,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        assert "claude-future-99" in report.unpriced_models
        assert "claude-future-99" in report.table()

    def test_known_id_with_incomplete_tokens_does_not_appear_in_footer(
        self, tmp_path: Path
    ) -> None:
        # A row with a KNOWN model but incomplete tokens: state cost is n/a,
        # but the footer does NOT name the model (the issue is the tokens,
        # not the price).
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "research",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": None,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "claude-sonnet-4-6",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "wallclock_ms": 1500,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        assert report.unpriced_models == []
        assert not report.unpriced_missing_sentinels
        out = report.table()
        assert "not priced" not in out

    def test_missing_identifier_sentinel_triggers_missing_line(self, tmp_path: Path) -> None:
        # A row with model="unknown" produces the missing-ID footer line
        # (no concrete ID was found to look up).
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "research",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "unknown",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "wallclock_ms": 1500,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        assert report.unpriced_missing_sentinels is True
        assert report.unpriced_models == []
        out = report.table()
        assert "no price identifier" in out
        assert "unknown, None" in out

    def test_string_none_sentinel_is_recognized(self, tmp_path: Path) -> None:
        # str(None) = "None" is the actual string emitted by the row
        # persistence path when JSON model is null. It must be a sentinel.
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "research",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "None",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "wallclock_ms": 1500,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        assert report.unpriced_missing_sentinels is True

    def test_empty_string_sentinel_is_recognized(self, tmp_path: Path) -> None:
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "research",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "wallclock_ms": 1500,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        assert report.unpriced_missing_sentinels is True

    def test_whitespace_sentinel_is_recognized(self, tmp_path: Path) -> None:
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "research",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "   ",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "wallclock_ms": 1500,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        assert report.unpriced_missing_sentinels is True

    def test_multiple_unpriced_ids_are_sorted_and_deduped(self, tmp_path: Path) -> None:
        # Two unpriced IDs, both appear, sorted alphabetically.
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "research",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "claude-zzz",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "wallclock_ms": 1500,
                },
                {
                    "state": "research",
                    "iteration": 2,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "claude-aaa",
                    "timestamp": "2026-07-07T10:00:05Z",
                    "wallclock_ms": 1500,
                },
                {
                    "state": "research",
                    "iteration": 3,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "claude-zzz",
                    "timestamp": "2026-07-07T10:00:10Z",
                    "wallclock_ms": 1500,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        assert report.unpriced_models == ["claude-aaa", "claude-zzz"]

    def test_mixed_priced_unpriced_preserves_null_state_cost(self, tmp_path: Path) -> None:
        # Known-priced states keep numeric cost; unknown states get null
        # cost and the run total is null too.
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "priced",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "claude-sonnet-4-6",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "wallclock_ms": 1500,
                },
                {
                    "state": "unpriced",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "claude-future-99",
                    "timestamp": "2026-07-07T10:00:05Z",
                    "wallclock_ms": 1500,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        by_state = {s.state: s for s in report.states}
        assert by_state["priced"].cost_usd is not None
        assert by_state["unpriced"].cost_usd is None
        # The whole run total cost is null because at least one state is unpriced.
        assert report.totals["cost_usd"] is None

    def test_dated_prefixed_and_suffixed_ids_appear_verbatim(self, tmp_path: Path) -> None:
        # The model's known limitation is exact-match pricing, so dated,
        # anthropic.-prefixed, and [1m]-suffixed IDs stay unpriced but
        # appear verbatim in the footer so the user can identify them.
        for variant in (
            "claude-sonnet-5-5-20261001",
            "anthropic.claude-fable-5",
            "claude-opus-5[1m]",
        ):
            p = self._write_rows(
                tmp_path,
                [
                    {
                        "state": "research",
                        "iteration": 1,
                        "action_type": "prompt",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_read_tokens": 10,
                        "cache_creation_tokens": 5,
                        "model": variant,
                        "timestamp": "2026-07-07T10:00:00Z",
                        "wallclock_ms": 1500,
                    },
                ],
            )
            report = CostReport.from_usage_jsonl(p)
            assert variant in report.unpriced_models, f"{variant} should be named"

    def test_footer_reads_same_pricing_table_as_estimator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The footer's membership check and ``estimate_cost_usd`` both read
        ``pricing.MODEL_PRICING``. Patch the table to a one-key sentinel and
        prove the report's named IDs and its priced/unpriced state costs
        both pivot off the patched table.
        """
        # Patch MODEL_PRICING in both fsm.cost_graph and little_loops.pricing
        # (the estimator uses the latter directly).
        from little_loops import pricing as pricing_mod
        from little_loops.fsm import cost_graph as cg_mod

        original_cg = cg_mod.MODEL_PRICING
        original_p = pricing_mod.MODEL_PRICING
        try:
            sentinel_pricing = {
                "sentinel-only": {
                    "input": 1.0,
                    "output": 2.0,
                    "cache_read": 0.1,
                    "cache_creation": 1.25,
                }
            }
            cg_mod.MODEL_PRICING = sentinel_pricing
            pricing_mod.MODEL_PRICING = sentinel_pricing
            p = self._write_rows(
                tmp_path,
                [
                    {
                        "state": "unpriced_state",
                        "iteration": 1,
                        "action_type": "prompt",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_read_tokens": 10,
                        "cache_creation_tokens": 5,
                        "model": "claude-sonnet-4-6",  # not in the patched table
                        "timestamp": "2026-07-07T10:00:00Z",
                        "wallclock_ms": 1500,
                    },
                    {
                        "state": "priced_state",
                        "iteration": 2,
                        "action_type": "prompt",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_read_tokens": 10,
                        "cache_creation_tokens": 5,
                        "model": "sentinel-only",  # in the patched table
                        "timestamp": "2026-07-07T10:00:05Z",
                        "wallclock_ms": 1500,
                    },
                ],
            )
            report = CostReport.from_usage_jsonl(p)
            # "claude-sonnet-4-6" is not in the patched table -> footer.
            assert "claude-sonnet-4-6" in report.unpriced_models
            # "sentinel-only" IS in the patched table -> priced.
            by_state = {s.state: s for s in report.states}
            assert by_state["priced_state"].cost_usd is not None
            assert by_state["unpriced_state"].cost_usd is None
        finally:
            cg_mod.MODEL_PRICING = original_cg
            pricing_mod.MODEL_PRICING = original_p

    def test_no_footer_when_all_priced(self, tmp_path: Path) -> None:
        # All rows priced: empty unpriced list, no missing-IDs, no footer.
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "research",
                    "iteration": 1,
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "claude-sonnet-4-6",
                    "timestamp": "2026-07-07T10:00:00Z",
                    "wallclock_ms": 1500,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        assert report.unpriced_models == []
        assert report.unpriced_missing_sentinels is False
        out = report.table()
        assert "not priced" not in out
        assert "no price identifier" not in out

    def test_empty_report_has_no_footer(self, tmp_path: Path) -> None:
        report = CostReport()
        out = report.table()
        assert "not priced" not in out

    def test_json_round_trip_drops_unpriced_diagnostics(self, tmp_path: Path) -> None:
        """ENH-3719: ``to_dict`` excludes ``unpriced_models`` and
        ``unpriced_missing_sentinels``. Round-tripping through ``read_json``
        gives a clean report with empty diagnostic fields. Stable keys
        unchanged.
        """
        p = self._write_rows(
            tmp_path,
            [
                {
                    "state": "research",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 10,
                    "cache_creation_tokens": 5,
                    "model": "claude-future-99",
                    "wallclock_ms": 1500,
                },
                {
                    "state": "summarize",
                    "input_tokens": 50,
                    "output_tokens": 25,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "model": "unknown",
                    "wallclock_ms": 800,
                },
            ],
        )
        report = CostReport.from_usage_jsonl(p)
        # Pre-write diagnostics present.
        assert report.unpriced_models == ["claude-future-99"]
        assert report.unpriced_missing_sentinels is True

        out_json = tmp_path / "report.json"
        report.write_json(out_json)
        data = json.loads(out_json.read_text(encoding="utf-8"))
        # Stable JSON shape unchanged.
        assert set(data.keys()) == {"states", "totals"}
        # Per-state entries still have the locked key set.
        for entry in data["states"]:
            assert "state" in entry and "cost_usd" in entry
        # Round-trip back to a CostReport: diagnostics lost (default empty).
        loaded = CostReport.read_json(out_json)
        assert loaded is not None
        assert loaded.unpriced_models == []
        assert loaded.unpriced_missing_sentinels is False
        # The loaded table has no footer (diagnostics gone).
        loaded_out = loaded.table()
        assert "not priced" not in loaded_out
        assert "no price identifier" not in loaded_out
