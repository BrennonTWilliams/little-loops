"""Tests for the per-state cost table behavior (ENH-2477).

Locks the stable JSON shape for per-state cost attribution.
The CLI flag wiring is tested in test_cli_loop_background.py
(via the run_background re-exec forwarding block).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.fsm.cost_graph import CostReport


@pytest.fixture
def fixture_jsonl(tmp_path: Path) -> Path:
    """One row per state, deterministic tokens/cost."""
    p = tmp_path / "usage.jsonl"
    rows = [
        {
            "state": "research",
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_tokens": 10,
            "cache_creation_tokens": 5,
            "model": "claude-sonnet-4-5",
            "wallclock_ms": 1500,
        },
        {
            "state": "summarize",
            "input_tokens": 50,
            "output_tokens": 25,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "model": "claude-sonnet-4-5",
            "wallclock_ms": 800,
        },
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


class TestCostOutputJsonShape:
    """Lock the stable JSON shape emitted by ``--cost-output-json <path>``.

    Acceptance criterion (ENH-2477): ``ll-loop run --cost-output-json
    /tmp/per-state.json`` emits JSON whose schema is locked by tests.
    """

    def test_top_level_keys(self, tmp_path: Path, fixture_jsonl: Path) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        out = tmp_path / "per-state.json"
        report.write_json(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert set(data.keys()) == {"states", "totals"}

    def test_state_entry_locked_keys(self, tmp_path: Path, fixture_jsonl: Path) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        out = tmp_path / "per-state.json"
        report.write_json(out)
        data = json.loads(out.read_text(encoding="utf-8"))

        assert len(data["states"]) == 2
        for entry in data["states"]:
            locked_keys = {
                "state",
                "iterations",
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_creation_tokens",
                "cost_usd",
                "wallclock_ms",
            }
            assert locked_keys <= set(entry.keys())

    def test_cache_read_and_creation_broken_out_separately(
        self, tmp_path: Path, fixture_jsonl: Path
    ) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        out = tmp_path / "per-state.json"
        report.write_json(out)
        data = json.loads(out.read_text(encoding="utf-8"))

        by_state = {e["state"]: e for e in data["states"]}
        # research has cache_read=10, cache_creation=5
        assert by_state["research"]["cache_read_tokens"] == 10
        assert by_state["research"]["cache_creation_tokens"] == 5
        # summarize has cache_read=0, cache_creation=0
        assert by_state["summarize"]["cache_read_tokens"] == 0
        assert by_state["summarize"]["cache_creation_tokens"] == 0
        # Totals break them out separately.
        assert data["totals"]["cache_read_tokens"] == 10
        assert data["totals"]["cache_creation_tokens"] == 5

    def test_totals_aggregate(self, tmp_path: Path, fixture_jsonl: Path) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        out = tmp_path / "per-state.json"
        report.write_json(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        totals = data["totals"]
        # 100 + 50 = 150 input
        assert totals["input_tokens"] == 150
        # 50 + 25 = 75 output
        assert totals["output_tokens"] == 75
        # 2 iterations total
        assert totals["iterations"] == 2
        # wallclock_ms summed
        assert totals["wallclock_ms"] == 2300


class TestPrintUsageSummaryBackwardsCompat:
    """Verify the existing 8-scenario ``TestPrintUsageSummary`` contract is preserved.

    The refactor of ``_print_usage_summary`` must keep the human-readable
    table output byte-identical. The 8 existing scenarios in
    ``test_usage_reporter.py`` lock this; this class adds a smoke-level
    check via the new ``CostReport.table()`` method.
    """

    def test_table_includes_header(self, fixture_jsonl: Path) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        out = report.table()
        for col in ("state", "invoc", "input", "output", "cache", "est_cost"):
            assert col in out

    def test_table_includes_separator(self, fixture_jsonl: Path) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        out = report.table()
        # Existing _print_usage_summary prints "-" * 68
        assert "-" * 68 in out

    def test_table_includes_each_state(self, fixture_jsonl: Path) -> None:
        report = CostReport.from_usage_jsonl(fixture_jsonl)
        out = report.table()
        assert "research" in out
        assert "summarize" in out
