"""ENH-3611: the refine-to-ready-issue child's proof gate (``check_proof_before_done``).

Runs the real gate shell action under bash against a stub ``ll-issues``. The
autodev half (PROOF re-entry from the obligation selectors) moved into
``little_loops.preparation_policy`` with ENH-3623; its predicates are table-tested
in ``test_preparation_policy.py`` (``test_post_refine_*`` / ``test_pre_implement_*``).
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
CHILD: dict[str, Any] = yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())["states"]

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


class TestChildProofBeforeDone:
    STATE = CHILD["check_proof_before_done"]
    ACTION = STATE["action"]

    def test_routing(self) -> None:
        assert self.STATE["fragment"] == "shell_exit"
        assert self.STATE["on_yes"] == "run_spike"
        assert self.STATE["on_no"] == "check_advise_ready_enabled"
        assert self.STATE["on_error"] == "check_advise_ready_enabled"
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
            yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())["max_steps"] == 113
        )
