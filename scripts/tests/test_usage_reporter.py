"""Tests for per-state token usage summary table printed by run_foreground."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.cli.loop._helpers import _print_usage_summary


def _make_usage_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


class TestPrintUsageSummary:
    def test_prints_table_header(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        _make_usage_jsonl(usage_path, [
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
        ])
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        assert "state" in out
        assert "invoc" in out
        assert "input" in out
        assert "output" in out
        assert "est_cost" in out

    def test_prints_state_row(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        _make_usage_jsonl(usage_path, [
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
        ])
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        assert "check_skill" in out
        assert "1234" in out
        assert "567" in out

    def test_cost_estimate_shown_for_known_model(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        _make_usage_jsonl(usage_path, [
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
        ])
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        assert "$" in out  # some cost estimate shown

    def test_na_shown_for_unknown_model(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        _make_usage_jsonl(usage_path, [
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
        ])
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
        _make_usage_jsonl(usage_path, [
            {"iteration": 0, "state": "state_a", "action_type": "prompt",
             "input_tokens": 100, "output_tokens": 50, "cache_read_tokens": 0,
             "cache_creation_tokens": 0, "model": "claude-sonnet-4-6", "timestamp": ""},
            {"iteration": 0, "state": "state_b", "action_type": "prompt",
             "input_tokens": 200, "output_tokens": 80, "cache_read_tokens": 0,
             "cache_creation_tokens": 0, "model": "claude-sonnet-4-6", "timestamp": ""},
            {"iteration": 1, "state": "state_a", "action_type": "prompt",
             "input_tokens": 100, "output_tokens": 50, "cache_read_tokens": 0,
             "cache_creation_tokens": 0, "model": "claude-sonnet-4-6", "timestamp": ""},
        ])
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        assert "state_a" in out
        assert "state_b" in out
        # state_a should show invocations=2 and input=200
        lines = out.splitlines()
        state_a_line = next((l for l in lines if "state_a" in l), None)
        assert state_a_line is not None
        assert "2" in state_a_line  # invocations
        assert "200" in state_a_line  # total input_tokens

    def test_invocations_counted_per_state(self, tmp_path: Path, capsys) -> None:
        usage_path = tmp_path / "usage.jsonl"
        rows = [
            {"iteration": i, "state": "run", "action_type": "prompt",
             "input_tokens": 100, "output_tokens": 10, "cache_read_tokens": 0,
             "cache_creation_tokens": 0, "model": "claude-sonnet-4-6", "timestamp": ""}
            for i in range(3)
        ]
        _make_usage_jsonl(usage_path, rows)
        _print_usage_summary(usage_path)
        out = capsys.readouterr().out
        lines = out.splitlines()
        run_line = next((l for l in lines if "run" in l and "---" not in l and "state" not in l), None)
        assert run_line is not None
        assert "3" in run_line
