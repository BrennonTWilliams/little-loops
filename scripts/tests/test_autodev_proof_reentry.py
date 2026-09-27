"""ENH-3611: PROOF re-entry in autodev's obligation selectors + the child's proof gate.

Runs the real selector / gate shell actions under bash against a stub ``ll-issues``.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

LOOPS = Path(__file__).parent.parent / "little_loops" / "loops"
AUTODEV: dict[str, Any] = yaml.safe_load((LOOPS / "autodev.yaml").read_text())["states"]
CHILD: dict[str, Any] = yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())["states"]

LOW_OUTCOME = ["select_obligation_post_refine", "select_obligation_post_size_review"]
ID = "ENH-1"


class _Stub:
    """``ll-issues`` stub: per-flag ``flag_<name>`` files hold the check-flag exit code."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.bin = root / "bin"
        self.bin.mkdir()
        (root / "cwd").mkdir()
        (self.bin / "ll-issues").write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> "{root}/calls"\n'
            'case "$1" in\n'
            f'  check-flag) f="{root}/flag_$3"; [ -f "$f" ] && exit "$(cat "$f")"; exit 1;;\n'
            f'  check-gate) cat "{root}/gate" 2>/dev/null; exit "$(cat "{root}/gate_rc" 2>/dev/null || echo 0)";;\n'
            f'  next-obligation) cat "{root}/obligation" 2>/dev/null || echo NONE;;\n'
            f'  refine-status) printf \'{{"refine_count": %s}}\' "$(cat "{root}/refine_count" 2>/dev/null || echo 0)";;\n'
            "  *) exit 0;;\n"
            "esac\n"
        )
        (self.bin / "ll-issues").chmod(0o755)

    def flag(self, name: str, rc: int) -> None:
        (self.root / f"flag_{name}").write_text(str(rc))

    def put(self, name: str, value: str) -> None:
        (self.root / name).write_text(value)

    def calls(self) -> list[str]:
        f = self.root / "calls"
        return f.read_text().splitlines() if f.exists() else []

    def run(self, action: str, run_dir: Path) -> subprocess.CompletedProcess[str]:
        subs = {
            "context.run_dir": str(run_dir),
            "captured.input.output:shell": ID,
            "captured.issue_id.output:shell": ID,
            "context.readiness_threshold:shell": "85",
            "context.outcome_threshold:shell": "65",
        }
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


def _spikeable(stub: _Stub) -> None:
    stub.flag("spike_needed", 0)  # set; spike_attempted stays unset (exit 1)
    stub.put("obligation", "PROOF:absent\n")


@pytest.mark.parametrize("name", LOW_OUTCOME)
class TestLowOutcomeProofReentry:
    def test_reenters_once_then_falls_through(self, stub: _Stub, run_dir: Path, name: str) -> None:
        _spikeable(stub)
        (run_dir / "autodev-staged.txt").write_text(f"OTHER-1\n{ID}\n")
        first = stub.run(AUTODEV[name]["action"], run_dir)
        assert first.stdout.strip() == "PROOF", first.stderr
        assert (run_dir / f"autodev-reentry-PROOF-{ID}").read_text() == "1"
        assert (run_dir / "autodev-staged.txt").read_text().splitlines() == ["OTHER-1"]
        second = stub.run(AUTODEV[name]["action"], run_dir)
        assert second.stdout.strip() == "PROOF:absent"  # raw token → `_`

    def test_refuted_registry_target_does_not_mask_spikeable(
        self, stub: _Stub, run_dir: Path, name: str
    ) -> None:
        _spikeable(stub)
        stub.put("obligation", "PROOF:refuted\n")
        assert stub.run(AUTODEV[name]["action"], run_dir).stdout.strip() == "PROOF"

    @pytest.mark.parametrize("setup", ["attempted", "not_needed", "budget", "capped"])
    def test_child_cannot_spike_is_not_reentered(
        self, stub: _Stub, run_dir: Path, name: str, setup: str
    ) -> None:
        _spikeable(stub)
        if setup == "attempted":
            stub.flag("spike_attempted", 0)
        elif setup == "not_needed":
            stub.flag("spike_needed", 1)
        elif setup == "budget":
            (run_dir / f"spike-runs-{ID}").write_text("2")
        else:
            stub.put("refine_count", "5")
        result = stub.run(AUTODEV[name]["action"], run_dir)
        assert result.stdout.strip() == "PROOF:absent"
        assert not list(run_dir.glob("autodev-reentry-*"))

    def test_next_obligation_gets_waiver_and_tier1_skips_once(
        self, stub: _Stub, run_dir: Path, name: str
    ) -> None:
        _spikeable(stub)
        stub.run(AUTODEV[name]["action"], run_dir)
        nxt = [c for c in stub.calls() if c.startswith("next-obligation")]
        assert len(nxt) == 1
        assert "--honor-waiver" in nxt[0]
        for tier1 in (
            "FORMAT",
            "VERIFY",
            "HEDGES",
            "PLACEHOLDERS",
            "ACCEPTANCE_CRITERIA",
            "DESIGN",
        ):
            assert f"--skip {tier1}" in nxt[0]

    def test_non_proof_token_passes_through(self, stub: _Stub, run_dir: Path, name: str) -> None:
        stub.put("obligation", "SCORES:outcome_below\n")
        stub.flag("spike_needed", 0)
        assert stub.run(AUTODEV[name]["action"], run_dir).stdout.strip() == "SCORES:outcome_below"


class TestPreImplementProofReentry:
    ACTION = AUTODEV["select_obligation_pre_implement"]["action"]

    def test_open_gate_reenters_once(self, stub: _Stub, run_dir: Path) -> None:
        stub.put("gate", "structured_proof")
        (run_dir / "autodev-staged.txt").write_text(f"{ID}\n")
        assert stub.run(self.ACTION, run_dir).stdout.strip() == "PROOF"
        assert (run_dir / "autodev-staged.txt").read_text() == ""
        again = stub.run(self.ACTION, run_dir)
        assert again.stdout.strip() == "NONE"  # marker spent → next-obligation

    @pytest.mark.parametrize("setup", ["waived", "attempted", "budget", "capped"])
    def test_guard_terms_fall_through(self, stub: _Stub, run_dir: Path, setup: str) -> None:
        stub.put("gate", "structured_proof")
        if setup == "waived":
            stub.flag("outcome_gate_waived", 0)
        elif setup == "attempted":
            stub.flag("spike_attempted", 0)
        elif setup == "budget":
            (run_dir / f"spike-runs-{ID}").write_text("2")
        else:
            stub.put("refine_count", "5")
        assert stub.run(self.ACTION, run_dir).stdout.strip() == "NONE"

    def test_waiver_helper_error_falls_through(self, stub: _Stub, run_dir: Path) -> None:
        stub.put("gate", "structured_proof")
        stub.flag("outcome_gate_waived", 2)
        assert stub.run(self.ACTION, run_dir).stdout.strip() == "NONE"

    @pytest.mark.parametrize(
        "verdict", ["structured_open", "prose", "none", "structured_satisfied"]
    )
    def test_other_verdicts_fall_through(self, stub: _Stub, run_dir: Path, verdict: str) -> None:
        stub.put("gate", verdict)
        assert stub.run(self.ACTION, run_dir).stdout.strip() == "NONE"

    def test_gate_helper_error_falls_through(self, stub: _Stub, run_dir: Path) -> None:
        stub.put("gate", "structured_proof")
        stub.put("gate_rc", "2")
        assert stub.run(self.ACTION, run_dir).stdout.strip() == "NONE"

    def test_decision_flag_wins_over_proof(self, stub: _Stub, run_dir: Path) -> None:
        stub.put("gate", "structured_proof")
        stub.flag("decision_needed", 0)
        assert stub.run(self.ACTION, run_dir).stdout.strip() == "DECISION"


class TestChildProofBeforeDone:
    STATE = CHILD["check_proof_before_done"]
    ACTION = STATE["action"]

    def test_routing(self) -> None:
        assert self.STATE["fragment"] == "shell_exit"
        assert self.STATE["on_yes"] == "run_spike"
        assert self.STATE["on_no"] == "write_done_record"
        assert self.STATE["on_error"] == "write_done_record"
        assert CHILD["check_decision_before_done"]["on_no"] == "check_proof_before_done"
        assert CHILD["check_decision_before_done"]["on_error"] == "check_proof_before_done"

    def test_spikes_structured_proof_and_spends_budget(self, stub: _Stub, run_dir: Path) -> None:
        stub.put("gate", "structured_proof")
        assert stub.run(self.ACTION, run_dir).returncode == 0
        assert (run_dir / f"spike-runs-{ID}").read_text() == "1"

    @pytest.mark.parametrize(
        "verdict", ["structured_open", "prose", "none", "structured_satisfied"]
    )
    def test_token_match_not_exit_code(self, stub: _Stub, run_dir: Path, verdict: str) -> None:
        stub.put("gate", verdict)  # check-gate exits 0 for in-force verdicts
        assert stub.run(self.ACTION, run_dir).returncode == 1
        assert not (run_dir / f"spike-runs-{ID}").exists()

    @pytest.mark.parametrize(
        "setup", ["attempted", "budget", "attempted_probe_error", "gate_error"]
    )
    def test_guards_never_spike(self, stub: _Stub, run_dir: Path, setup: str) -> None:
        stub.put("gate", "structured_proof")
        if setup == "attempted":
            stub.flag("spike_attempted", 0)
        elif setup == "budget":
            (run_dir / f"spike-runs-{ID}").write_text("2")
        elif setup == "attempted_probe_error":
            stub.flag("spike_attempted", 2)
        else:
            stub.put("gate_rc", "2")
        assert stub.run(self.ACTION, run_dir).returncode == 1

    def test_max_steps_raised(self) -> None:
        assert (
            yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())["max_steps"] == 110
        )
