"""Tests for ``little_loops.fleet_improve`` — helpers behind the
``fleet-loop-improve`` built-in meta-loop."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from little_loops import fleet_improve as fi

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)
EXCLUDED = ["/abs/little-loops"]


def _sidecar(loops: dict[str, dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "generated": NOW.isoformat(),
        "window_days": None,
        "since": None,
        "until": None,
        "projects_scanned": ["/abs/p1", "/abs/p2"],
        "excluded_projects": list(EXCLUDED),
        "loops": loops,
        "shadowed": {},
    }
    data.update(overrides)
    return data


def _rec(
    runs: int, converged: int, top_outcome: str = "failed", projects: list[str] | None = None
) -> dict[str, Any]:
    return {
        "runs": runs,
        "converged": converged,
        "success_pct": round(converged / runs * 100) if runs else 0,
        "top_outcome": top_outcome,
        "outcomes": {"converged": converged, top_outcome: runs - converged},
        "projects": projects or ["/abs/p1"],
        "runs_by_project": {"/abs/p1": runs},
    }


def _write_sidecar(
    tmp_path: Path, sidecar: dict[str, Any], stamp: str = "20260904T120000Z"
) -> Path:
    path = tmp_path / f"fleet-review-{stamp}.json"
    path.write_text(json.dumps(sidecar))
    return path


def _entry(loop: str, status: str, *, recorded_at: datetime = NOW, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "loop": loop,
        "status": status,
        "recorded_at": recorded_at.isoformat(),
        "commit": "abc123" if status == "pending" else None,
        "artifact": f".loops/diagnostics/{loop}-20260901T000000Z.md",
        "harvest_stamp": "20260901T000000Z",
        "baseline": {
            "runs": 10,
            "converged": 2,
            "success_pct": 20,
            "top_outcome": "failed",
            "window_days": None,
            "excluded_projects": list(EXCLUDED),
        },
        "reason": "",
    }
    entry.update(extra)
    return entry


class FakeRunner:
    """Scripted stand-in for ``fleet_improve._run``."""

    def __init__(self, responses: dict[str, tuple[int, str]]) -> None:
        self.responses = responses
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(
        self, cmd: list[str], *, cwd: Path | None = None, timeout: int = 0
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((cmd, cwd))
        for key, (code, out) in self.responses.items():
            if key in " ".join(cmd):
                return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


VALID_REPORT = json.dumps({"loop": "x", "valid": True, "violations": []})
ONE_WARNING_REPORT = json.dumps(
    {
        "loop": "x",
        "valid": True,
        "violations": [{"severity": "warning", "path": "states.a", "message": "w"}],
    }
)
ERROR_REPORT = json.dumps(
    {
        "loop": "x",
        "valid": False,
        "violations": [{"severity": "error", "path": "states.a", "message": "boom"}],
    }
)


# --------------------------------------------------------------------------- #
# ledger
# --------------------------------------------------------------------------- #


class TestLedger:
    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert fi.read_ledger(tmp_path / "nope.jsonl") == []

    def test_round_trip_and_latest_wins(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        fi.append_ledger(ledger, _entry("a", "pending"))
        fi.append_ledger(ledger, _entry("b", "dismissed"))
        fi.append_ledger(ledger, _entry("a", "improved"))
        entries = fi.read_ledger(ledger)
        assert [e["loop"] for e in entries] == ["a", "b", "a"]
        latest = fi.latest_by_loop(entries)
        assert latest["a"]["status"] == "improved"
        assert latest["b"]["status"] == "dismissed"

    def test_malformed_line_raises(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text('{"loop": "a", "status": "pending"}\nnot json\n')
        with pytest.raises(fi.FleetImproveError, match="malformed ledger line"):
            fi.read_ledger(ledger)

    def test_line_without_loop_raises(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text('{"status": "pending"}\n')
        with pytest.raises(fi.FleetImproveError, match="no 'loop'"):
            fi.read_ledger(ledger)


# --------------------------------------------------------------------------- #
# select
# --------------------------------------------------------------------------- #


class TestSelect:
    PATHS = {
        "alpha": Path("/pkg/loops/alpha.yaml"),
        "beta": Path("/pkg/loops/beta.yaml"),
        "verify-thing": Path("/pkg/loops/oracles/verify-thing.yaml"),
    }

    def _select(
        self,
        sidecar: dict[str, Any],
        entries: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> dict[str, Any] | None:
        opts: dict[str, Any] = {
            "threshold": 50,
            "min_runs": 3,
            "dismiss_ttl_days": 30,
            "now": NOW,
            "builtin_paths": self.PATHS,
        }
        opts.update(kw)
        return fi.select_target(
            sidecar, Path("/x/fleet-review-20260904T120000Z.json"), entries or [], **opts
        )

    def test_flagged_loops_applies_runbook_rule(self) -> None:
        sidecar = _sidecar(
            {
                "alpha": _rec(10, 2),  # 20% < 50
                "beta": _rec(2, 0),  # below min_runs
                "gamma": _rec(10, 9, top_outcome="converged"),  # healthy
                "delta": _rec(4, 3, top_outcome="stalled"),  # 75% but failure top_outcome
                "eps": _rec(4, 1, top_outcome="interrupted"),  # 25% via threshold clause
            }
        )
        names = [n for n, _ in fi.flagged_loops(sidecar, threshold=50, min_runs=3)]
        assert names == ["alpha", "delta", "eps"]

    def test_flagged_loops_malformed_record_raises(self) -> None:
        sidecar = _sidecar({"alpha": {"runs": "ten"}})
        with pytest.raises(fi.FleetImproveError, match="malformed"):
            fi.flagged_loops(sidecar, threshold=50, min_runs=3)

    def test_picks_most_runs_first(self) -> None:
        sidecar = _sidecar({"alpha": _rec(5, 0), "beta": _rec(12, 1)})
        target = self._select(sidecar)
        assert target is not None
        assert target["loop"] == "beta"
        assert target["yaml_path"] == "/pkg/loops/beta.yaml"

    def test_target_shape(self) -> None:
        sidecar = _sidecar({"alpha": _rec(10, 2, projects=["/abs/p1", "/abs/p2"])})
        target = self._select(sidecar)
        assert target is not None
        assert target["projects"] == ["/abs/p1", "/abs/p2"]
        assert target["stamp"] == "20260904T120000Z"
        assert target["harvest_stamp"] == "20260904T120000Z"
        assert target["artifact"] == ".loops/diagnostics/alpha-20260904T120000Z.md"
        assert target["baseline"] == {
            "runs": 10,
            "converged": 2,
            "success_pct": 20,
            "top_outcome": "failed",
            "window_days": None,
            "excluded_projects": EXCLUDED,
        }
        assert target["tests_dir"].endswith("tests")

    def test_nested_oracle_resolves_via_builtin_paths(self) -> None:
        sidecar = _sidecar({"verify-thing": _rec(6, 0)})
        target = self._select(sidecar)
        assert target is not None
        assert target["yaml_path"] == "/pkg/loops/oracles/verify-thing.yaml"

    def test_unknown_stem_skipped(self) -> None:
        sidecar = _sidecar({"ghost": _rec(6, 0), "alpha": _rec(4, 0)})
        target = self._select(sidecar)
        assert target is not None
        assert target["loop"] == "alpha"

    def test_pending_skipped(self) -> None:
        sidecar = _sidecar({"alpha": _rec(10, 2), "beta": _rec(4, 0)})
        target = self._select(sidecar, [_entry("alpha", "pending")])
        assert target is not None
        assert target["loop"] == "beta"

    @pytest.mark.parametrize("status", sorted(fi.SKIP_TTL_STATUSES))
    def test_ttl_statuses_skipped_within_ttl(self, status: str) -> None:
        sidecar = _sidecar({"alpha": _rec(10, 2)})
        recent = NOW - timedelta(days=5)
        assert self._select(sidecar, [_entry("alpha", status, recorded_at=recent)]) is None

    @pytest.mark.parametrize("status", sorted(fi.SKIP_TTL_STATUSES))
    def test_ttl_statuses_eligible_after_ttl(self, status: str) -> None:
        sidecar = _sidecar({"alpha": _rec(10, 2)})
        old = NOW - timedelta(days=31)
        target = self._select(sidecar, [_entry("alpha", status, recorded_at=old)])
        assert target is not None and target["loop"] == "alpha"

    @pytest.mark.parametrize("status", ["improved", "regressed", "unchanged"])
    def test_measured_loops_are_eligible_again(self, status: str) -> None:
        sidecar = _sidecar({"alpha": _rec(10, 2)})
        target = self._select(sidecar, [_entry("alpha", status)])
        assert target is not None and target["loop"] == "alpha"

    def test_none_when_nothing_flagged(self) -> None:
        assert self._select(_sidecar({"alpha": _rec(10, 9, "converged")})) is None

    def test_dirty_yaml_skipped_not_fatal(self) -> None:
        """A candidate whose built-in YAML has uncommitted changes yields to the next one."""
        sidecar = _sidecar({"alpha": _rec(10, 2), "beta": _rec(4, 0)})
        logged: list[str] = []
        target = self._select(sidecar, is_dirty=lambda p: p.name == "alpha.yaml", log=logged.append)
        assert target is not None and target["loop"] == "beta"
        assert any("alpha" in m and "uncommitted" in m for m in logged)

    def test_all_dirty_yields_none(self) -> None:
        sidecar = _sidecar({"alpha": _rec(10, 2), "beta": _rec(4, 0)})
        assert self._select(sidecar, is_dirty=lambda _p: True) is None

    @pytest.mark.parametrize(
        ("porcelain", "expected"),
        [("", False), ("\n", False), (" M scripts/little_loops/loops/alpha.yaml\n", True)],
    )
    def test_yaml_is_dirty_reads_porcelain(self, porcelain: str, expected: bool) -> None:
        seen: list[list[str]] = []

        def runner(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
            seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout=porcelain, stderr="")

        assert fi.yaml_is_dirty(Path("/pkg/loops/alpha.yaml"), runner) is expected
        assert seen == [["git", "status", "--porcelain", "--", "/pkg/loops/alpha.yaml"]]

    def test_cmd_select_writes_target_and_exit_codes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(fi, "_builtin_loop_paths", lambda: self.PATHS)
        monkeypatch.setattr(fi, "utc_now", lambda: NOW)
        sidecar_path = _write_sidecar(tmp_path, _sidecar({"alpha": _rec(10, 2)}))
        run_dir = tmp_path / "run"
        ledger = tmp_path / "ledger.jsonl"
        argv = [
            "select",
            "--run-dir",
            str(run_dir),
            "--sidecar",
            str(sidecar_path),
            "--ledger",
            str(ledger),
        ]
        assert fi.main(argv) == fi.EXIT_YES
        target = json.loads((run_dir / "target.json").read_text())
        assert target["loop"] == "alpha"
        # max-fixes reached for this run -> exit 1
        (run_dir / "fixes.count").write_text("1\n")
        assert fi.main([*argv, "--max-fixes", "1"]) == fi.EXIT_NO
        # nothing flagged -> exit 1
        healthy = _write_sidecar(
            tmp_path, _sidecar({"alpha": _rec(10, 9, "converged")}), "20260904T130000Z"
        )
        assert (
            fi.main(
                [
                    "select",
                    "--run-dir",
                    str(run_dir / "b"),
                    "--sidecar",
                    str(healthy),
                    "--ledger",
                    str(ledger),
                ]
            )
            == fi.EXIT_NO
        )

    def test_cmd_select_bad_sidecar_exit_2(self, tmp_path: Path) -> None:
        bad = tmp_path / "fleet-review-x.json"
        bad.write_text("{}")
        assert (
            fi.main(["select", "--run-dir", str(tmp_path / "r"), "--sidecar", str(bad)])
            == fi.EXIT_ERROR
        )


# --------------------------------------------------------------------------- #
# measure
# --------------------------------------------------------------------------- #


class TestMeasure:
    def _measure(self, entry: dict[str, Any], sidecar: dict[str, Any], min_new_runs: int = 3):
        return fi.measure_entry(
            entry, sidecar, stamp="20260904T120000Z", min_new_runs=min_new_runs, now=NOW
        )

    def test_improved(self) -> None:
        new, note = self._measure(_entry("alpha", "pending"), _sidecar({"alpha": _rec(14, 5)}))
        assert new is not None
        assert new["status"] == "improved"
        assert new["measured"] == {
            "harvest_stamp": "20260904T120000Z",
            "new_runs": 4,
            "new_converged": 3,
            "post_success_pct": 75,
            "top_outcome": "failed",
        }
        assert "20% -> 75%" in note

    def test_regressed(self) -> None:
        new, _ = self._measure(_entry("alpha", "pending"), _sidecar({"alpha": _rec(14, 2)}))
        assert new is not None and new["status"] == "regressed"

    def test_unchanged(self) -> None:
        # baseline 20%; 5 new runs with 1 converged = 20%
        new, _ = self._measure(_entry("alpha", "pending"), _sidecar({"alpha": _rec(15, 3)}))
        assert new is not None and new["status"] == "unchanged"

    def test_not_enough_new_runs_stays_pending(self) -> None:
        new, note = self._measure(_entry("alpha", "pending"), _sidecar({"alpha": _rec(12, 3)}))
        assert new is None
        assert "2 new run(s), need 3" in note

    def test_absent_loop_stays_pending(self) -> None:
        new, note = self._measure(_entry("alpha", "pending"), _sidecar({}))
        assert new is None and "absent" in note

    def test_incomparable_window(self) -> None:
        sidecar = _sidecar({"alpha": _rec(20, 10)}, window_days=7)
        new, note = self._measure(_entry("alpha", "pending"), sidecar)
        assert new is None and "not comparable" in note

    def test_incomparable_excluded_projects(self) -> None:
        sidecar = _sidecar({"alpha": _rec(20, 10)}, excluded_projects=[])
        new, _ = self._measure(_entry("alpha", "pending"), sidecar)
        assert new is None

    def test_projects_scanned_growth_is_comparable(self) -> None:
        sidecar = _sidecar(
            {"alpha": _rec(20, 10)}, projects_scanned=["/abs/p1", "/abs/p2", "/abs/p3"]
        )
        new, _ = self._measure(_entry("alpha", "pending"), sidecar)
        assert new is not None

    def test_measure_only_pending_latest_entries(self) -> None:
        entries = [
            _entry("alpha", "pending"),
            _entry("alpha", "improved"),  # latest for alpha: not pending
            _entry("beta", "pending"),
            _entry("gamma", "dismissed"),
        ]
        sidecar = _sidecar({"alpha": _rec(30, 20), "beta": _rec(14, 5)})
        new_entries, rows = fi.measure(entries, sidecar, stamp="s", min_new_runs=3, now=NOW)
        assert [e["loop"] for e in new_entries] == ["beta"]
        assert rows == [("beta", "improved", "20% -> 75% over 4 new run(s)")]

    def test_render_table(self) -> None:
        assert fi.render_measure_table([]) == "No pending fixes to measure."
        table = fi.render_measure_table([("a", "pending", "why")])
        assert "| `a` | pending | why |" in table

    def test_cmd_measure_appends_ledger(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ledger = tmp_path / "ledger.jsonl"
        fi.append_ledger(ledger, _entry("alpha", "pending"))
        fi.append_ledger(ledger, _entry("beta", "pending"))
        sidecar_path = _write_sidecar(
            tmp_path, _sidecar({"alpha": _rec(14, 2), "beta": _rec(11, 2)})
        )
        rc = fi.main(
            [
                "measure",
                "--run-dir",
                str(tmp_path / "r"),
                "--sidecar",
                str(sidecar_path),
                "--ledger",
                str(ledger),
            ]
        )
        assert rc == fi.EXIT_YES
        latest = fi.latest_by_loop(fi.read_ledger(ledger))
        assert latest["alpha"]["status"] == "regressed"
        assert latest["beta"]["status"] == "pending"  # only 1 new run
        captured = capsys.readouterr()
        assert "| `alpha` | regressed |" in captured.out
        assert "regressed after fix" in captured.err


# --------------------------------------------------------------------------- #
# check-proposal
# --------------------------------------------------------------------------- #


def _artifact(verdict: str = "fix", proposed: str = "Change `on_no` to `retry`.") -> str:
    return "\n".join(
        [
            "# Diagnosis",
            "## Failure modes observed",
            "- [x] premature-termination",
            "## Evidence",
            "quoted",
            "## Intended contract",
            "c",
            "## Proposed change",
            proposed,
            "## Verification",
            "Deferred to fleet re-measure.",
            "## Open questions",
            "none",
            "",
            f"Verdict: {verdict}",
            "",
        ]
    )


class TestCheckProposal:
    @pytest.mark.parametrize(
        ("verdict", "token"),
        [
            ("fix", "VERDICT_FIX"),
            ("not-a-loop-bug", "VERDICT_NOT_A_LOOP_BUG"),
            ("needs-human", "VERDICT_NEEDS_HUMAN"),
        ],
    )
    def test_verdict_tokens(self, tmp_path: Path, verdict: str, token: str) -> None:
        art = tmp_path / "a.md"
        art.write_text(_artifact(verdict))
        assert fi.check_proposal(art) == token

    def test_last_verdict_wins(self, tmp_path: Path) -> None:
        art = tmp_path / "a.md"
        art.write_text(_artifact("fix") + "\nVerdict: needs-human\n")
        assert fi.check_proposal(art) == "VERDICT_NEEDS_HUMAN"

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(fi.FleetImproveError, match="not found"):
            fi.check_proposal(tmp_path / "missing.md")

    @pytest.mark.parametrize("heading", fi.ARTIFACT_SECTIONS)
    def test_each_missing_section_rejected(self, tmp_path: Path, heading: str) -> None:
        art = tmp_path / "a.md"
        art.write_text(_artifact().replace(heading, "## Something else"))
        with pytest.raises(fi.FleetImproveError, match="missing section"):
            fi.check_proposal(art)

    def test_empty_proposed_change_rejected(self, tmp_path: Path) -> None:
        art = tmp_path / "a.md"
        art.write_text(_artifact(proposed="   "))
        with pytest.raises(fi.FleetImproveError, match="empty"):
            fi.check_proposal(art)

    def test_missing_verdict_rejected(self, tmp_path: Path) -> None:
        art = tmp_path / "a.md"
        art.write_text(_artifact().replace("Verdict: fix", "Verdict: maybe"))
        with pytest.raises(fi.FleetImproveError, match="Verdict"):
            fi.check_proposal(art)

    def test_cmd_uses_target_artifact_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_dir = tmp_path / "r"
        run_dir.mkdir()
        art = tmp_path / "alpha-x.md"
        art.write_text(_artifact("not-a-loop-bug"))
        (run_dir / "target.json").write_text(json.dumps({"loop": "alpha", "artifact": str(art)}))
        assert fi.main(["check-proposal", "--run-dir", str(run_dir)]) == fi.EXIT_YES
        assert capsys.readouterr().out.strip() == "VERDICT_NOT_A_LOOP_BUG"
        art.unlink()
        assert fi.main(["check-proposal", "--run-dir", str(run_dir)]) == fi.EXIT_ERROR


# --------------------------------------------------------------------------- #
# diagnose
# --------------------------------------------------------------------------- #


class TestDiagnose:
    def _target(self, tmp_path: Path, projects: list[str]) -> dict[str, Any]:
        yaml_path = tmp_path / "alpha.yaml"
        yaml_path.write_text("name: alpha\n")
        return {
            "loop": "alpha",
            "projects": projects,
            "runs": 10,
            "converged": 2,
            "success_pct": 20,
            "top_outcome": "failed",
            "outcomes": {"failed": 8, "converged": 2},
            "yaml_path": str(yaml_path),
            "sidecar": "s.json",
            "harvest_stamp": "20260904T120000Z",
        }

    def test_runs_tools_in_each_project_and_writes_dossier(self, tmp_path: Path) -> None:
        p1 = tmp_path / "p1"
        p1.mkdir()
        p2 = tmp_path / "p2"
        p2.mkdir()
        runner = FakeRunner(
            {
                "diagnose-evaluators": (0, json.dumps({"loop": "alpha", "states": []})),
                "calibrate-budget": (0, "Insufficient history for: alpha (found 1 run(s), need 2)"),
                "validate": (0, ONE_WARNING_REPORT),
                "rev-parse": (0, "deadbeef\n"),
            }
        )
        run_dir = tmp_path / "run"
        dossier = fi.diagnose(
            self._target(tmp_path, [str(p1), str(p2), str(tmp_path / "gone")]), run_dir, runner
        )
        assert dossier == run_dir / "diagnose" / "alpha.md"
        text = dossier.read_text()
        assert "Insufficient history" in text
        assert '"states": []' in text
        assert "_project directory missing" in text
        # cwd-bound tools ran inside each existing project with --min-runs 2
        tool_calls = [
            (c, cwd) for c, cwd in runner.calls if c[0] == "ll-loop" and c[1] != "validate"
        ]
        assert {cwd for _, cwd in tool_calls} == {p1, p2}
        assert all(c[-2:] == ["--min-runs", "2"] and "--json" in c for c, _ in tool_calls)
        baseline = json.loads((run_dir / "gate-baseline.json").read_text())
        assert baseline == {"head": "deadbeef", "warnings": 1, "valid": True}

    def test_validate_not_json_raises(self, tmp_path: Path) -> None:
        runner = FakeRunner({"validate": (1, "invalid loop")})
        with pytest.raises(fi.FleetImproveError, match="did not return JSON"):
            fi.diagnose(self._target(tmp_path, []), tmp_path / "run", runner)

    def test_missing_tool_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a: Any, **_k: Any) -> None:
            raise FileNotFoundError("ll-loop")

        monkeypatch.setattr(subprocess, "run", boom)
        with pytest.raises(fi.FleetImproveError, match="command not found"):
            fi._run(["ll-loop", "validate"])


# --------------------------------------------------------------------------- #
# gate
# --------------------------------------------------------------------------- #


class TestGate:
    def _setup(
        self, tmp_path: Path, *, baseline_warnings: int = 0, with_tests: bool = True
    ) -> tuple[dict[str, Any], Path]:
        yaml_path = tmp_path / "alpha.yaml"
        yaml_path.write_text("name: alpha\nstates: {}\n")
        tests_dir = tmp_path / "tests"
        if with_tests:
            tests_dir.mkdir()
            (tests_dir / "test_builtin_loops.py").write_text("")
            (tests_dir / "test_builtin_loop_hardcode_gate.py").write_text("")
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "gate-baseline.json").write_text(
            json.dumps({"head": "x", "warnings": baseline_warnings})
        )
        return {"loop": "alpha", "yaml_path": str(yaml_path), "tests_dir": str(tests_dir)}, run_dir

    def test_no_diff_fails(self, tmp_path: Path) -> None:
        target, run_dir = self._setup(tmp_path)
        ok, detail = fi.gate(target, run_dir, FakeRunner({"git diff": (0, "")}))
        assert not ok and "no change" in detail

    def test_unparseable_yaml_fails(self, tmp_path: Path) -> None:
        target, run_dir = self._setup(tmp_path)
        Path(target["yaml_path"]).write_text("a: [unclosed\n")
        ok, detail = fi.gate(target, run_dir, FakeRunner({"git diff": (1, "")}))
        assert not ok and "no longer parses" in detail

    def test_validate_error_fails(self, tmp_path: Path) -> None:
        target, run_dir = self._setup(tmp_path)
        ok, detail = fi.gate(
            target, run_dir, FakeRunner({"git diff": (1, ""), "validate": (1, ERROR_REPORT)})
        )
        assert not ok and "boom" in detail

    def test_warning_growth_fails(self, tmp_path: Path) -> None:
        target, run_dir = self._setup(tmp_path, baseline_warnings=0)
        ok, detail = fi.gate(
            target, run_dir, FakeRunner({"git diff": (1, ""), "validate": (0, ONE_WARNING_REPORT)})
        )
        assert not ok and "warnings grew: 0 -> 1" in detail

    def test_same_warning_count_allowed(self, tmp_path: Path) -> None:
        target, run_dir = self._setup(tmp_path, baseline_warnings=1)
        runner = FakeRunner(
            {"git diff": (1, ""), "validate": (0, ONE_WARNING_REPORT), "pytest": (0, "ok")}
        )
        ok, _ = fi.gate(target, run_dir, runner)
        assert ok

    def test_pytest_failure_fails(self, tmp_path: Path) -> None:
        target, run_dir = self._setup(tmp_path)
        runner = FakeRunner(
            {
                "git diff": (1, ""),
                "validate": (0, VALID_REPORT),
                "pytest": (1, "FAILED x\n1 failed"),
            }
        )
        ok, detail = fi.gate(target, run_dir, runner)
        assert not ok and "1 failed" in detail

    def test_all_pass_runs_both_test_files(self, tmp_path: Path) -> None:
        target, run_dir = self._setup(tmp_path)
        runner = FakeRunner({"git diff": (1, ""), "validate": (0, VALID_REPORT), "pytest": (0, "")})
        ok, detail = fi.gate(target, run_dir, runner)
        assert ok and "gate passed" in detail
        pytest_calls = [c for c, _ in runner.calls if "pytest" in c]
        assert len(pytest_calls) == 1
        assert pytest_calls[0][:3] == [sys.executable, "-m", "pytest"]
        assert sum(1 for a in pytest_calls[0] if a.endswith(".py")) == 2

    def test_missing_tests_dir_skips_pytest(self, tmp_path: Path) -> None:
        target, run_dir = self._setup(tmp_path, with_tests=False)
        runner = FakeRunner({"git diff": (1, ""), "validate": (0, VALID_REPORT)})
        ok, _ = fi.gate(target, run_dir, runner)
        assert ok
        assert not any("pytest" in c for c, _ in runner.calls)


# --------------------------------------------------------------------------- #
# record
# --------------------------------------------------------------------------- #


class TestRecord:
    def test_pending_snapshots_commit_and_baseline(self) -> None:
        target = {
            "loop": "alpha",
            "artifact": "a.md",
            "harvest_stamp": "s",
            "baseline": {"runs": 1},
        }
        entry = fi.record(target, status="pending", reason="r", now=NOW, head="abc")
        assert entry["commit"] == "abc"
        assert entry["baseline"] == {"runs": 1}
        assert entry["recorded_at"] == NOW.isoformat()
        rejected = fi.record(target, status="rejected", reason="gate", now=NOW, head="abc")
        assert rejected["commit"] is None and rejected["reason"] == "gate"

    def test_cmd_record_increments_fixes_count_only_for_pending(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(fi, "git_head", lambda _runner: "abc")
        run_dir = tmp_path / "r"
        run_dir.mkdir()
        (run_dir / "target.json").write_text(json.dumps({"loop": "alpha", "baseline": {}}))
        ledger = tmp_path / "ledger.jsonl"
        base = ["record", "--run-dir", str(run_dir), "--ledger", str(ledger)]
        assert fi.main([*base, "--status", "dismissed", "--reason", "nope"]) == fi.EXIT_YES
        assert fi.read_fixes_count(run_dir) == 0
        assert fi.main([*base, "--status", "pending"]) == fi.EXIT_YES
        assert fi.read_fixes_count(run_dir) == 1
        latest = fi.latest_by_loop(fi.read_ledger(ledger))
        assert latest["alpha"]["status"] == "pending" and latest["alpha"]["commit"] == "abc"


class TestMisc:
    def test_sidecar_stamp_from_name_then_generated(self) -> None:
        assert (
            fi.sidecar_stamp(Path("fleet-review-20260903T044101Z.json"), {}) == "20260903T044101Z"
        )
        assert (
            fi.sidecar_stamp(Path("harvest.json"), {"generated": NOW.isoformat()})
            == "20260904T120000Z"
        )
        assert fi.sidecar_stamp(Path("harvest.json"), {}) == "unknown"

    def test_run_strips_ll_automation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_AUTOMATION", "1")
        seen: dict[str, Any] = {}

        def fake_run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
            seen.update(kw)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        fi._run(["true"])
        assert "LL_AUTOMATION" not in seen["env"]
