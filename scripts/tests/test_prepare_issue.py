"""Tests for the prepare-issue pass-through wrapper (ENH-3605).

Structural pins on ``prepare-issue.yaml``, execution of its shell states against a real
``ll-issues run-record`` CLI, and a per-token parity table proving the wrapper plus the
retargeted autodev routers reproduce the pre-change route and ledger rows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import load_and_validate
from little_loops.run_record import RunRecord, read_run_record, write_run_record

LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
WRAPPER = LOOPS_DIR / "prepare-issue.yaml"
AUTODEV = LOOPS_DIR / "autodev.yaml"
ID = "ENH-9705"
INNER = "refine-to-ready-issue"
OUTER = "prepare-issue"


@pytest.fixture(scope="module")
def data() -> dict:
    return yaml.safe_load(WRAPPER.read_text())


@pytest.fixture(scope="module")
def autodev() -> dict:
    return yaml.safe_load(AUTODEV.read_text())


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / kind).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".issues" / "enhancements" / f"P3-{ID}-t.md").write_text(
        f"---\nid: {ID}\ntitle: T\ntype: enhancement\nstatus: open\npriority: P3\n---\n\n# {ID}: T\n"
    )
    return tmp_path


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run"
    d.mkdir()
    return d


def _run_state(
    project: Path, states: dict, state: str, run_dir: Path
) -> subprocess.CompletedProcess:
    action = (
        states[state]["action"]
        .replace("${context.run_dir}", str(run_dir))
        .replace("${context.input:shell}", f"'{ID}'")
    )
    env = dict(os.environ)
    ll = shutil.which("ll-issues")
    if ll:
        env["PATH"] = f"{Path(ll).parent}:{env['PATH']}"
    else:  # pragma: no cover - editable installs always ship the entry point
        pytest.skip("ll-issues not on PATH")
    return subprocess.run(
        ["bash", "-c", action],
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _inner(run_dir: Path, **kw) -> None:
    write_run_record(run_dir, RunRecord(writer=INNER, issue_id=ID, **kw))


class TestStructure:
    def test_validates(self) -> None:
        fsm, _ = load_and_validate(WRAPPER)
        assert fsm.initial == "clear_record"

    def test_scope_declared_and_no_input_in_context(self, data: dict) -> None:
        assert data["scope"]
        assert "input" not in (data.get("context") or {})

    def test_loop_state_has_no_timeout_or_rate_limit_keys(self, data: dict) -> None:
        state = data["states"]["run_refine_to_ready"]
        assert state["loop"] == INNER
        assert state["context_passthrough"] is True
        for key in ("timeout", "fragment", "on_rate_limit_exhausted", "on_no"):
            assert key not in state, key
        assert state["on_yes"] == "forward_done"
        assert state["on_failure"] == "forward_stop"
        assert state["on_error"] == "mark_inner_error"

    def test_terminals_mirror_inner_type(self, data: dict) -> None:
        states = data["states"]
        assert states["failed"]["terminal"] is True and states["failed"]["failure"] is True
        assert states["done"]["terminal"] is True and "failure" not in states["done"]
        assert states["forward_done"]["next"] == "done"
        assert states["forward_done"]["on_error"] == "done"
        assert states["forward_stop"]["next"] == "failed"
        assert states["forward_stop"]["on_error"] == "failed"
        assert states["mark_inner_error"]["next"] == "failed"

    def test_every_write_uses_prepare_issue_writer(self, data: dict) -> None:
        for name, state in data["states"].items():
            action = state.get("action", "")
            for line in action.splitlines():
                if "run-record write" in line or "run-record forward" in line:
                    assert "--writer prepare-issue" in line, (name, line)

    def test_entry_clears_both_writers(self, data: dict) -> None:
        action = data["states"]["clear_record"]["action"]
        assert "run-record clear" in action
        assert f"--writer {OUTER}" in action and f"--writer {INNER}" in action


class TestExecution:
    def test_forward_preserves_record_fields(
        self, project: Path, run_dir: Path, data: dict
    ) -> None:
        _inner(
            run_dir,
            outcome="retryable_error",
            legacy_class="infra",
            child_ids=("ENH-1",),
            evidence_refs=("rate_limit_exhausted",),
            readiness=90,
            outcome_confidence=70,
        )
        assert _run_state(project, data["states"], "forward_done", run_dir).returncode == 0
        out = read_run_record(run_dir, OUTER, ID)
        assert out is not None
        assert (out.outcome, out.legacy_class, out.child_ids, out.evidence_refs) == (
            "retryable_error",
            "infra",
            ("ENH-1",),
            ("rate_limit_exhausted",),
        )
        assert (out.readiness, out.outcome_confidence) == (90, 70)

    def test_missing_inner_record_writes_nothing(
        self, project: Path, run_dir: Path, data: dict
    ) -> None:
        for state in ("forward_done", "forward_stop"):
            _run_state(project, data["states"], state, run_dir)
        assert read_run_record(run_dir, OUTER, ID) is None
        assert not (run_dir / "autodev-skipped.txt").exists()

    def test_inner_error_writes_infra_record_and_sentinel(
        self, project: Path, run_dir: Path, data: dict
    ) -> None:
        _run_state(project, data["states"], "mark_inner_error", run_dir)
        assert (run_dir / "refine-terminal-class").read_text() == "infra"
        rec = read_run_record(run_dir, OUTER, ID)
        assert rec is not None and rec.outcome == "retryable_error" and rec.legacy_class == "infra"

    def test_entry_clears_stale_records(self, project: Path, run_dir: Path, data: dict) -> None:
        _inner(run_dir, outcome="ready")
        write_run_record(run_dir, RunRecord(writer=OUTER, issue_id=ID, outcome="ready"))
        _run_state(project, data["states"], "clear_record", run_dir)
        assert read_run_record(run_dir, OUTER, ID) is None
        assert read_run_record(run_dir, INNER, ID) is None

    @pytest.mark.parametrize(
        "outcome,legacy,rows",
        [
            ("blocked", "quality", [f"{ID}  refine_failed"]),
            ("deferred", "gate_unmet", [f"{ID}  refine_failed"]),
            ("blocked", "decision_unresolved", []),
            ("blocked", "proposal_unsound", []),
            ("deferred", "spike_inconclusive", []),
            ("retryable_error", "infra", []),
            ("blocked", None, []),
        ],
    )
    def test_forward_stop_row_only_for_quality_and_gate_unmet(
        self, project: Path, run_dir: Path, data: dict, outcome: str, legacy: str | None, rows: list
    ) -> None:
        _inner(run_dir, outcome=outcome, legacy_class=legacy)
        assert _run_state(project, data["states"], "forward_stop", run_dir).returncode == 0
        ledger = run_dir / "autodev-skipped.txt"
        assert (ledger.read_text().splitlines() if ledger.exists() else []) == rows


# (inner record kwargs, terminal) -> (router state, token routed to, net refine_failed rows)
_PARITY = [
    ({"outcome": "ready"}, "done", "route_refine_success", "READY", "check_passed", 0),
    ({"outcome": "decomposed"}, "done", "route_refine_success", "DECOMPOSED", "detect_children", 0),
    ({"outcome": "cancelled"}, "done", "route_refine_success", "CANCELLED", "skip_cancelled", 0),
    (
        {"outcome": "blocked", "legacy_class": "decision_unresolved"},
        "failed",
        "route_refine_outcome",
        "BLOCKED:decision_unresolved",
        "ledger_child_stop",
        0,
    ),
    (
        {"outcome": "blocked", "legacy_class": "quality"},
        "failed",
        "route_refine_outcome",
        "BLOCKED:quality",
        "ledger_child_stop",
        1,
    ),
    (
        {"outcome": "deferred", "legacy_class": "gate_unmet"},
        "failed",
        "route_refine_outcome",
        "DEFERRED:gate_unmet",
        "ledger_child_stop",
        1,
    ),
    (
        {
            "outcome": "retryable_error",
            "legacy_class": "infra",
            "evidence_refs": ("rate_limit_exhausted",),
        },
        "failed",
        "route_refine_outcome",
        "RETRYABLE_ERROR:rate_limited",
        "finalize_rate_limited",
        0,
    ),
    (
        {"outcome": "retryable_error", "legacy_class": "infra"},
        "failed",
        "route_refine_outcome",
        "RETRYABLE_ERROR:infra",
        "skip_inflight_infra",
        0,
    ),
]


class TestAutodevParity:
    """The wrapper + retargeted routers reproduce the pre-change route and ledger rows."""

    @pytest.mark.parametrize("kw,terminal,router,token,target,rows", _PARITY)
    def test_token_route_and_ledger(
        self,
        project: Path,
        run_dir: Path,
        data: dict,
        autodev: dict,
        kw: dict,
        terminal: str,
        router: str,
        token: str,
        target: str,
        rows: int,
    ) -> None:
        _inner(run_dir, **kw)
        state = "forward_done" if terminal == "done" else "forward_stop"
        _run_state(project, data["states"], state, run_dir)
        # the router reads the forwarded record and prints the expected token
        action = autodev["states"][router]["action"].replace("\n", " ")
        cmd = action.replace("${captured.input.output:shell}", f"'{ID}'").replace(
            "${context.run_dir}", str(run_dir)
        )
        r = subprocess.run(
            ["bash", "-c", cmd], cwd=str(project), capture_output=True, text=True, timeout=60
        )
        assert r.stdout.strip() == token
        assert autodev["states"][router]["route"][token] == target
        ledger = run_dir / "autodev-skipped.txt"
        lines = ledger.read_text().splitlines() if ledger.exists() else []
        assert lines == [f"{ID}  refine_failed"] * rows

    def test_missing_routes_to_skip_inflight(self, autodev: dict) -> None:
        assert autodev["states"]["route_refine_outcome"]["route"]["MISSING"] == "skip_inflight"
        assert autodev["states"]["route_refine_success"]["route"]["MISSING"] == "check_passed"

    def test_state_count_unchanged(self, autodev: dict) -> None:
        assert autodev["states"]["refine_current"]["loop"] == OUTER
        assert autodev["states"]["refine_current"]["on_failure"] == "route_refine_outcome"
        assert autodev["states"]["refine_current"]["on_error"] == "skip_inflight_infra"
        assert "on_no" not in autodev["states"]["refine_current"]
