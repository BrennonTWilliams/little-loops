"""ENH-3633: opt-in ``advise_ready`` consult gate on refine-to-ready-issue's done path.

Runs the real gate/consult/veto shell actions under bash against a stub
``ll-issues`` (mirrors ``test_autodev_proof_reentry.py``'s ``_Stub``), plus the
recursive-refine veto-skip gate.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

LOOPS = Path(__file__).parent.parent / "little_loops" / "loops"
CHILD: dict[str, Any] = yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())
CHILD_STATES: dict[str, Any] = CHILD["states"]
RR: dict[str, Any] = yaml.safe_load((LOOPS / "recursive-refine.yaml").read_text())
RR_STATES: dict[str, Any] = RR["states"]
AUTODEV: dict[str, Any] = yaml.safe_load((LOOPS / "autodev.yaml").read_text())

ID = "ENH-1"


class _Stub:
    """``ll-issues`` stub: dispatches on ``$1``, logs every call."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.bin = root / "bin"
        self.bin.mkdir()
        (root / "cwd").mkdir()
        (self.bin / "ll-issues").write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> "{root}/calls"\n'
            'case "$1" in\n'
            f'  advise-consult) cat "{root}/token" 2>/dev/null || echo SKIPPED;;\n'
            f'  show) cat "{root}/show.json" 2>/dev/null || echo "{{}}"; exit "$(cat "{root}/show_rc" 2>/dev/null || echo 0)";;\n'
            "  run-record) exit 0;;\n"
            "  *) exit 0;;\n"
            "esac\n"
        )
        (self.bin / "ll-issues").chmod(0o755)

    def put(self, name: str, value: str) -> None:
        (self.root / name).write_text(value)

    def calls(self) -> list[str]:
        f = self.root / "calls"
        return f.read_text().splitlines() if f.exists() else []

    def run(
        self, action: str, run_dir: Path, extra_subs: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        subs = {
            "context.run_dir": str(run_dir),
            "captured.issue_id.output:shell": ID,
            "captured.input.output:shell": ID,
            "captured.input.output": ID,
            "context.advise_ready:shell": "''",
        }
        subs.update(extra_subs or {})
        script = re.sub(r"\$\{([^}]+)\}", lambda m: subs[m.group(1)], action)
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=self.root / "cwd",
        )


@pytest.fixture
def stub(tmp_path: Path) -> _Stub:
    return _Stub(tmp_path)


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run"
    d.mkdir()
    return d


class TestFlagDeclaration:
    def test_advise_ready_only_in_parameters_never_context(self) -> None:
        assert "advise_ready" not in (CHILD.get("context") or {})
        assert CHILD["parameters"]["advise_ready"]["default"] == ""
        assert "advise_ready" not in (RR.get("context") or {})
        assert RR["parameters"]["advise_ready"]["default"] == ""

    def test_autodev_declares_flag_empty_in_context(self) -> None:
        assert AUTODEV["context"]["advise_ready"] == ""


class TestCheckAdviseReadyEnabled:
    STATE = CHILD_STATES["check_advise_ready_enabled"]
    ACTION = STATE["action"]

    def test_routing(self) -> None:
        assert self.STATE["fragment"] == "shell_exit"
        assert self.STATE["on_yes"] == "run_advise_ready"
        assert self.STATE["on_no"] == "write_done_record"
        assert self.STATE["on_error"] == "write_done_record"

    def test_retargeted_from_check_proof_before_done(self) -> None:
        proof = CHILD_STATES["check_proof_before_done"]
        assert proof["on_no"] == "check_advise_ready_enabled"
        assert proof["on_error"] == "check_advise_ready_enabled"

    def test_flag_empty_is_off(self, stub: _Stub, run_dir: Path) -> None:
        result = stub.run(self.ACTION, run_dir)
        assert result.returncode == 1

    def test_flag_set_is_on(self, stub: _Stub, run_dir: Path) -> None:
        result = stub.run(self.ACTION, run_dir, {"context.advise_ready:shell": "1"})
        assert result.returncode == 0


class TestRunAdviseReady:
    STATE = CHILD_STATES["run_advise_ready"]
    ACTION = STATE["action"]

    def test_route_keys_exact(self) -> None:
        assert set(self.STATE["route"]) == {"PROCEED", "SKIPPED", "VETO", "_", "_error"}
        assert self.STATE["route"]["PROCEED"] == "write_done_record"
        assert self.STATE["route"]["SKIPPED"] == "write_done_record"
        assert self.STATE["route"]["VETO"] == "record_advisor_veto"
        assert self.STATE["route"]["_"] == "write_done_record"
        assert self.STATE["route"]["_error"] == "write_done_record"

    def test_declares_timeout(self) -> None:
        assert self.STATE.get("timeout")

    def test_calls_advise_consult_with_write_note(self) -> None:
        assert "advise-consult" in self.ACTION
        assert "--write-note" in self.ACTION
        assert "--run-dir" in self.ACTION

    @pytest.mark.parametrize("token", ["PROCEED", "SKIPPED", "VETO"])
    def test_prints_helper_token_verbatim(self, stub: _Stub, run_dir: Path, token: str) -> None:
        stub.put("token", token)
        result = stub.run(self.ACTION, run_dir)
        assert result.returncode == 0
        assert result.stdout.strip().splitlines()[-1] == token


class TestRecordAdvisorVeto:
    STATE = CHILD_STATES["record_advisor_veto"]
    ACTION = STATE["action"]

    def test_routing(self) -> None:
        assert self.STATE["next"] == "failed"
        assert self.STATE["on_error"] == "failed"

    def test_writes_run_record_gate_unmet(self, stub: _Stub, run_dir: Path) -> None:
        stub.put("show.json", json.dumps({"issue_id": "ENH-1"}))
        result = stub.run(self.ACTION, run_dir)
        assert result.returncode == 0, result.stderr
        calls = stub.calls()
        assert any(
            "run-record write" in c
            and "--legacy-class gate_unmet" in c
            and "--evidence-refs advise-ENH-1.json" in c
            for c in calls
        ), calls

    def test_appends_raw_id_to_advisor_vetoed(self, stub: _Stub, run_dir: Path) -> None:
        stub.put("show.json", json.dumps({"issue_id": "ENH-1"}))
        stub.run(self.ACTION, run_dir)
        assert (run_dir / "advisor-vetoed").read_text().splitlines() == [ID]

    def test_canonical_id_resolution_for_non_canonical_input(
        self, stub: _Stub, run_dir: Path
    ) -> None:
        """A raw '3633'-style captured ID still resolves the helper's canonical file name."""
        stub.put("show.json", json.dumps({"issue_id": "ENH-1"}))
        result = stub.run(self.ACTION, run_dir, {"captured.issue_id.output:shell": "1"})
        assert result.returncode == 0
        calls = stub.calls()
        assert any("--evidence-refs advise-ENH-1.json" in c for c in calls), calls

    def test_show_failure_falls_back_to_raw_id(self, stub: _Stub, run_dir: Path) -> None:
        stub.put("show_rc", "1")
        result = stub.run(self.ACTION, run_dir)
        assert result.returncode == 0
        calls = stub.calls()
        assert any(f"--evidence-refs advise-{ID}.json" in c for c in calls), calls

    def test_echoes_advisor_veto_with_recommendation(self, stub: _Stub, run_dir: Path) -> None:
        stub.put("show.json", json.dumps({"issue_id": "ENH-1"}))
        (run_dir / "advise-ENH-1.json").write_text(
            json.dumps({"recommendation": "VETO the API shape is unresolved"})
        )
        result = stub.run(self.ACTION, run_dir)
        assert f"[ADVISOR_VETO] {ID} - VETO the API shape is unresolved" in result.stdout

    def test_echoes_without_recommendation_when_payload_missing(
        self, stub: _Stub, run_dir: Path
    ) -> None:
        stub.put("show.json", json.dumps({"issue_id": "ENH-1"}))
        result = stub.run(self.ACTION, run_dir)
        assert result.returncode == 0
        assert f"[ADVISOR_VETO] {ID}" in result.stdout


class TestMaxStepsRaised:
    def test_max_steps_113(self) -> None:
        assert CHILD["max_steps"] == 113


class TestRecursiveRefineVetoSkip:
    def test_run_refine_retargeted(self) -> None:
        run_refine = RR_STATES["run_refine"]
        assert run_refine["on_failure"] == "check_advisor_veto"
        assert run_refine["on_error"] == "check_advisor_veto"

    def test_check_advisor_veto_routing(self) -> None:
        state = RR_STATES["check_advisor_veto"]
        assert state["fragment"] == "shell_exit"
        assert state["on_yes"] == "skip_advisor_veto"
        assert state["on_no"] == "gate_recursion"
        assert state["on_error"] == "gate_recursion"

    def test_skip_advisor_veto_next(self) -> None:
        assert RR_STATES["skip_advisor_veto"]["next"] == "dequeue_next"

    def test_vetoed_id_routes_to_skip(self, stub: _Stub, run_dir: Path) -> None:
        (run_dir / "advisor-vetoed").write_text(f"{ID}\n")
        result = stub.run(RR_STATES["check_advisor_veto"]["action"], run_dir)
        assert result.returncode == 0

    def test_non_vetoed_id_falls_through(self, stub: _Stub, run_dir: Path) -> None:
        (run_dir / "advisor-vetoed").write_text("ENH-999\n")
        result = stub.run(RR_STATES["check_advisor_veto"]["action"], run_dir)
        assert result.returncode == 1

    def test_missing_marker_file_falls_through(self, stub: _Stub, run_dir: Path) -> None:
        result = stub.run(RR_STATES["check_advisor_veto"]["action"], run_dir)
        assert result.returncode != 0

    def test_skip_advisor_veto_writes_both_files_never_size_review(
        self, stub: _Stub, run_dir: Path
    ) -> None:
        action = RR_STATES["skip_advisor_veto"]["action"]
        assert "run_size_review" not in action
        result = stub.run(action, run_dir)
        assert result.returncode == 0
        assert ID in (run_dir / "recursive-refine-skipped-vetoed.txt").read_text()
        assert ID in (run_dir / "recursive-refine-skipped.txt").read_text()
