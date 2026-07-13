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
            "model": "claude-sonnet-4-5",
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
            "model": "claude-sonnet-4-5",
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
            "model": "claude-sonnet-4-5",
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
