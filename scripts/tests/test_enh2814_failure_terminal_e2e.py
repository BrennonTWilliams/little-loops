"""End-to-end exit-code observability for FSM failure terminals (ENH-2814).

Runs a real ``ll-loop run`` subprocess to a failure terminal and asserts the
OS-level exit code, closing the integration gap noted in ENH-2814: every unit
test above this one asserts on in-process return values, so a regression in the
CLI's exit path (or in how the executor stamps ``failure_terminal``) would go
unnoticed by them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

pytestmark = pytest.mark.skipif(
    shutil.which("ll-loop") is None,
    reason="ll-loop entry point not installed (pip install -e ./scripts)",
)

# Shell-only states so the loop runs with no host CLI / LLM involvement.
_LOOP_TEMPLATE = """\
name: {name}
description: ENH-2814 exit-code fixture
initial: check
max_steps: 5
terminal_action_ok: true
states:
  check:
    action_type: shell
    action: "exit {exit_code}"
    evaluate:
      type: exit_code
    on_yes: done
    on_no: {failure_state}
  done:
    terminal: true
  {failure_state}:
    terminal: true
{failure_decl}"""


def _run_loop(tmp_path: Path, *, exit_code: int, failure_state: str, flagged: bool) -> int:
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir(parents=True, exist_ok=True)
    name = "enh2814-fixture"
    (loops_dir / f"{name}.yaml").write_text(
        _LOOP_TEMPLATE.format(
            name=name,
            exit_code=exit_code,
            failure_state=failure_state,
            failure_decl="    failure: true\n" if flagged else "",
        )
    )
    proc = subprocess.run(
        ["ll-loop", "run", name, "--quiet"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode


def test_failure_terminal_exits_nonzero(tmp_path: Path) -> None:
    """A run landing on a `failure: true` terminal exits FAILURE_TERMINAL_EXIT_CODE."""
    rc = _run_loop(tmp_path, exit_code=1, failure_state="blocked", flagged=True)
    assert rc == FAILURE_TERMINAL_EXIT_CODE


def test_success_terminal_still_exits_zero(tmp_path: Path) -> None:
    """The success path is unchanged — reaching `done` still exits 0."""
    rc = _run_loop(tmp_path, exit_code=0, failure_state="blocked", flagged=True)
    assert rc == 0


def test_unflagged_non_done_terminal_exits_zero(tmp_path: Path) -> None:
    """A non-`done` terminal without the flag is a success, proving name-independence."""
    rc = _run_loop(tmp_path, exit_code=1, failure_state="present_result", flagged=False)
    assert rc == 0


def test_conventional_failed_name_defaults_to_flagged(tmp_path: Path) -> None:
    """A terminal named `failed` with no `failure:` key still exits nonzero.

    The backward-compat guarantee: pre-ENH-2814 loop YAML becomes observable
    without being edited.
    """
    rc = _run_loop(tmp_path, exit_code=1, failure_state="failed", flagged=False)
    assert rc == FAILURE_TERMINAL_EXIT_CODE


def test_persisted_final_status_is_failed(tmp_path: Path) -> None:
    """The archived run records final_status 'failed', not 'completed'."""
    _run_loop(tmp_path, exit_code=1, failure_state="blocked", flagged=True)
    states = list((tmp_path / ".loops").rglob("*.state.json"))
    assert states, f"no state file written under {tmp_path / '.loops'}"
    statuses = {json.loads(p.read_text()).get("status") for p in states}
    assert "failed" in statuses, statuses
