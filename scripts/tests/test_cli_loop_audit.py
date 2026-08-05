"""Tests for ll-loop audit (ENH-2949): deterministic run-counter parity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from little_loops.cli.loop.audit import audit_run, cmd_audit, resolve_run


def _write_run(
    loops_dir: Path,
    run_id: str,
    loop_name: str,
    events: list[dict],
    state: dict | None = None,
    summary: dict | None = None,
) -> Path:
    run_dir = loops_dir / ".history" / f"{run_id}-{loop_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "events.jsonl", "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    (run_dir / "state.json").write_text(
        json.dumps(
            state or {"loop_name": loop_name, "status": "completed", "iteration": len(events)}
        )
    )
    if summary is not None:
        (run_dir / "summary.json").write_text(json.dumps(summary))
    return run_dir


_EVENTS = [
    {"event": "state_enter", "state": "step1", "ts": "2026-01-01T00:00:00Z"},
    {"event": "action_complete", "exit_code": 0, "duration_ms": 1000},
    {"event": "state_enter", "state": "step2", "ts": "2026-01-01T00:00:02Z"},
    {"event": "action_complete", "exit_code": 0, "duration_ms": 2000},
    {"event": "evaluate", "type": "exit_code", "verdict": "yes"},
    {
        "event": "loop_complete",
        "terminated_by": "terminal",
        "failure_terminal": False,
        "iterations": 3,
    },
]


class TestResolveRun:
    def test_resolve_by_explicit_dirname(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        run_dir = _write_run(loops_dir, "2026-01-01T000000", "mytest", _EVENTS)
        resolved = resolve_run("2026-01-01T000000-mytest", None, loops_dir)
        assert resolved == run_dir

    def test_resolve_latest_picks_most_recent(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        _write_run(loops_dir, "2026-01-01T000000", "mytest", _EVENTS)
        newest = _write_run(loops_dir, "2026-02-01T000000", "mytest", _EVENTS)
        resolved = resolve_run(None, "mytest", loops_dir)
        assert resolved == newest

    def test_resolve_missing_run_raises(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            resolve_run("nope", None, loops_dir)

    def test_resolve_no_args_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            resolve_run(None, None, tmp_path / ".loops")


class TestAuditRun:
    def test_counters_match_events(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        run_dir = _write_run(loops_dir, "2026-01-01T000000", "mytest", _EVENTS)

        stats = audit_run(run_dir, max_steps=10)

        assert stats.run_id == "2026-01-01T000000"
        assert stats.loop == "mytest"
        assert stats.events_total == 6
        assert stats.events_by_type == {
            "state_enter": 2,
            "action_complete": 2,
            "evaluate": 1,
            "loop_complete": 1,
        }
        assert stats.tool_call_count == 2
        assert stats.per_state["step1"].actions_complete == 1
        assert stats.per_state["step1"].duration_s == pytest.approx(1.0)
        assert stats.per_state["step2"].duration_s == pytest.approx(2.0)
        assert stats.steps_consumed == 3
        assert stats.max_steps == 10
        assert stats.budget_utilization == pytest.approx(0.3)
        assert stats.terminated_by == "terminal"
        assert stats.failure_terminal is False

    def test_diff_stall_detected(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        events = [
            {"event": "state_enter", "state": "check", "ts": "2026-01-01T00:00:00Z"},
            {"event": "evaluate", "type": "diff_stall", "verdict": "stall"},
        ]
        run_dir = _write_run(loops_dir, "2026-01-01T000000", "mytest", events)

        stats = audit_run(run_dir)

        assert stats.diff_stall_present is True

    def test_no_max_steps_leaves_budget_utilization_none(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        run_dir = _write_run(loops_dir, "2026-01-01T000000", "mytest", _EVENTS)

        stats = audit_run(run_dir)

        assert stats.budget_utilization is None

    def test_summary_json_included_in_verdict_inputs(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        run_dir = _write_run(
            loops_dir,
            "2026-01-01T000000",
            "mytest",
            _EVENTS,
            summary={"closed": 1, "failed": 0},
        )

        stats = audit_run(run_dir)

        assert stats.verdict_inputs["summary"] == {"closed": 1, "failed": 0}

    def test_aux_mutation_scan_counts_new_files(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        run_dir = _write_run(loops_dir, "2026-01-01T000000", "mytest", _EVENTS)
        (run_dir / "helper.md").write_text("hello")

        stats = audit_run(run_dir)

        assert stats.aux_mutation_count is not None
        assert stats.aux_mutation_count >= 1

    def test_missing_events_file_returns_empty_stats(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        run_dir = loops_dir / ".history" / "2026-01-01T000000-mytest"
        run_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(json.dumps({"loop_name": "mytest"}))

        stats = audit_run(run_dir)

        assert stats.events_total == 0
        assert stats.per_state == {}

    def test_to_dict_serializable(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        run_dir = _write_run(loops_dir, "2026-01-01T000000", "mytest", _EVENTS)

        stats = audit_run(run_dir, max_steps=10)

        assert json.dumps(stats.to_dict())  # round-trips without error


class TestCmdAudit:
    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        loops_dir = tmp_path / ".loops"
        _write_run(loops_dir, "2026-01-01T000000", "mytest", _EVENTS)
        args = argparse.Namespace(
            run="2026-01-01T000000-mytest", latest=None, max_steps=10, json=True
        )

        exit_code = cmd_audit(args, loops_dir)

        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["events_total"] == 6
        assert out["budget_utilization"] == pytest.approx(0.3)

    def test_human_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        loops_dir = tmp_path / ".loops"
        _write_run(loops_dir, "2026-01-01T000000", "mytest", _EVENTS)
        args = argparse.Namespace(
            run="2026-01-01T000000-mytest", latest=None, max_steps=None, json=False
        )

        exit_code = cmd_audit(args, loops_dir)

        out = capsys.readouterr().out
        assert exit_code == 0
        assert "Audit for run: 2026-01-01T000000 (mytest)" in out

    def test_missing_run_reports_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(run="nope", latest=None, max_steps=None, json=False)

        exit_code = cmd_audit(args, loops_dir)

        assert exit_code == 1
        assert "not found" in capsys.readouterr().out
