"""Tests for per-state token usage summary table printed by run_foreground."""

from __future__ import annotations

import json
from pathlib import Path

from little_loops.cli.loop.summary import _print_usage_summary


def _make_usage_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


class TestPrintUsageSummary:
    def test_prints_table_header(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        _make_usage_jsonl(
            usage_path,
            [
                {
                    "iteration": 0,
                    "state": "check_skill",
                    "action_type": "prompt",
                    "input_tokens": 1234,
                    "output_tokens": 567,
                    "cache_read_tokens": 890,
                    "cache_creation_tokens": 0,
                    "model": "claude-sonnet-4-6",
                    "timestamp": "2026-06-01T10:00:00Z",
                }
            ],
        )
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        assert "state" in out
        assert "invoc" in out
        assert "input" in out
        assert "output" in out
        assert "est_cost" in out

    def test_prints_state_row(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        _make_usage_jsonl(
            usage_path,
            [
                {
                    "iteration": 0,
                    "state": "check_skill",
                    "action_type": "prompt",
                    "input_tokens": 1234,
                    "output_tokens": 567,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "model": "claude-sonnet-4-6",
                    "timestamp": "2026-06-01T10:00:00Z",
                }
            ],
        )
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        assert "check_skill" in out
        assert "1234" in out
        assert "567" in out

    def test_cost_estimate_shown_for_known_model(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        _make_usage_jsonl(
            usage_path,
            [
                {
                    "iteration": 0,
                    "state": "run",
                    "action_type": "prompt",
                    "input_tokens": 1_000_000,
                    "output_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "model": "claude-sonnet-4-6",
                    "timestamp": "2026-06-01T10:00:00Z",
                }
            ],
        )
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        assert "$" in out  # some cost estimate shown

    def test_na_shown_for_unknown_model(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        _make_usage_jsonl(
            usage_path,
            [
                {
                    "iteration": 0,
                    "state": "run",
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "model": "unknown",
                    "timestamp": "2026-06-01T10:00:00Z",
                }
            ],
        )
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        assert "n/a" in out

    def test_no_output_when_file_missing(self, tmp_path: Path, capsys) -> None:
        _print_usage_summary(tmp_path / "nonexistent.jsonl")
        out = capsys.readouterr().out
        assert out == ""

    def test_no_output_when_file_empty(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        usage_path.write_text("")
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        assert out == ""

    def test_multiple_states_aggregated(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        _make_usage_jsonl(
            usage_path,
            [
                {
                    "iteration": 0,
                    "state": "state_a",
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "model": "claude-sonnet-4-6",
                    "timestamp": "",
                },
                {
                    "iteration": 0,
                    "state": "state_b",
                    "action_type": "prompt",
                    "input_tokens": 200,
                    "output_tokens": 80,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "model": "claude-sonnet-4-6",
                    "timestamp": "",
                },
                {
                    "iteration": 1,
                    "state": "state_a",
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "model": "claude-sonnet-4-6",
                    "timestamp": "",
                },
            ],
        )
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        assert "state_a" in out
        assert "state_b" in out
        # state_a should show invocations=2 and input=200
        lines = out.splitlines()
        state_a_line = next((ln for ln in lines if "state_a" in ln), None)
        assert state_a_line is not None
        assert "2" in state_a_line  # invocations
        assert "200" in state_a_line  # total input_tokens

    def test_invocations_counted_per_state(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        rows = [
            {
                "iteration": i,
                "state": "run",
                "action_type": "prompt",
                "input_tokens": 100,
                "output_tokens": 10,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "model": "claude-sonnet-4-6",
                "timestamp": "",
            }
            for i in range(3)
        ]
        _make_usage_jsonl(usage_path, rows)
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        lines = out.splitlines()
        run_line = next(
            (ln for ln in lines if "run" in ln and "---" not in ln and "state" not in ln), None
        )
        assert run_line is not None
        assert "3" in run_line


class TestEnH3719ReporterBehavior:
    """ENH-3719: the reporter prints the unknown-ID footer to stdout while
    the cost-output JSON keeps its stable shape (no diagnostic list).

    Also asserts the observed-run Sonnet 5.5 projection: a fully-priced
    row renders `$0.3201` with no footer (the rate exists in
    ``MODEL_PRICING`` so the footer is suppressed by the all-priced
    short-circuit).
    """

    def test_unknown_model_emits_footer_to_stdout_and_keeps_locked_json(
        self, tmp_path: Path, capsys
    ) -> None:
        usage_path = tmp_path / "usage.jsonl"
        json_out = tmp_path / "per-state.json"
        _make_usage_jsonl(
            usage_path,
            [
                {
                    "iteration": 0,
                    "state": "run",
                    "action_type": "prompt",
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "model": "claude-future-99",
                    "timestamp": "2026-06-01T10:00:00Z",
                },
            ],
        )
        _print_usage_summary(usage_path, cost_output_json=json_out)
        out_text = capsys.readouterr().out
        # Stdout carries the footer for human readers.
        assert "not priced" in out_text
        assert "claude-future-99" in out_text
        # JSON output keeps its locked shape — no diagnostic list in the file.
        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert set(data.keys()) == {"states", "totals"}
        # Per-state cost_usd is null (unpriced).
        assert data["states"][0]["cost_usd"] is None

    def test_observed_sonnet_5_5_projection_has_no_footer_and_renders_known_price(
        self, tmp_path: Path, capsys
    ) -> None:
        # A fully-priced row renders $0.3201 (the Sonnet 5.5 rate's exact
        # value) with no footer (the all-priced short-circuit suppresses it).
        # 14 input, 5748 output, 433686 cache-read, 70335 cache-creation
        # at $2/M, $10/M, $0.20/M, $2.50/M respectively:
        #   input:        14 * 2 / 1e6 = 0.000028
        #   output:    5_748 * 10 / 1e6 = 0.05748
        #   cache-read: 433_686 * 0.20 / 1e6 = 0.0867372
        #   cache-cre:  70_335 * 2.50 / 1e6 = 0.1758375
        #   total: 0.3200827 -> $0.3201
        usage_path = tmp_path / "usage.jsonl"
        _make_usage_jsonl(
            usage_path,
            [
                {
                    "iteration": 0,
                    "state": "run",
                    "action_type": "prompt",
                    "input_tokens": 14,
                    "output_tokens": 5748,
                    "cache_read_tokens": 433686,
                    "cache_creation_tokens": 70335,
                    "model": "claude-sonnet-5-5",
                    "timestamp": "2026-10-04T00:00:00Z",
                },
            ],
        )
        _print_usage_summary(usage_path)
        out_text = capsys.readouterr().out
        # No footer.
        assert "not priced" not in out_text
        assert "no price identifier" not in out_text
        # Known price renders.
        assert "$0.3201" in out_text
