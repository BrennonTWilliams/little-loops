"""Sub-loop failure-dispatch reachability (ENH-2892).

`spike-gate.yaml` and `proof-first-task.yaml` both delegate to
`${context.impl_loop}` (default `general-task`) and declare an
`on_failure: impl_failed` branch. Before general-task's `failed` terminal
carried an explicit `failure: true`, that branch was provably unreachable:
`get_failure_states()` was empty for the sub-loop, so the parent's sub-loop
dispatch could only ever take `on_success`.

This closes the gap by exercising the same dispatch shape end-to-end via a
real ``ll-loop run`` subprocess: a parent loop delegates to a sub-loop that
reaches a `failure: true` terminal, and the parent must route to its
`on_failure` state, not `on_success`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("ll-loop") is None,
    reason="ll-loop entry point not installed (pip install -e ./scripts)",
)

_CHILD_LOOP = """\
name: enh2892-child
description: ENH-2892 shell-only sub-loop failure fixture
initial: check
max_steps: 5
terminal_action_ok: true
context:
  input: ""
states:
  check:
    action_type: shell
    action: "exit 1"
    evaluate:
      type: exit_code
    on_yes: done
    on_no: failed
  done:
    terminal: true
  failed:
    terminal: true
    failure: true
"""

_PARENT_LOOP = """\
name: enh2892-parent
description: ENH-2892 sub-loop dispatch fixture, mirrors spike-gate/proof-first-task
initial: run_impl
max_steps: 5
terminal_action_ok: true
context:
  impl_loop: enh2892-child
states:
  run_impl:
    loop: "${context.impl_loop}"
    with:
      input: "task"
    on_success: done
    on_failure: impl_failed
    on_error: impl_failed
  done:
    terminal: true
  impl_failed:
    terminal: true
    failure: true
"""


def test_subloop_failure_routes_parent_to_on_failure(tmp_path: Path) -> None:
    """A sub-loop reaching a `failure: true` terminal routes the parent
    to `on_failure`, not `on_success` — the spike-gate/proof-first-task shape."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir(parents=True, exist_ok=True)
    (loops_dir / "enh2892-child.yaml").write_text(_CHILD_LOOP)
    (loops_dir / "enh2892-parent.yaml").write_text(_PARENT_LOOP)

    proc = subprocess.run(
        ["ll-loop", "run", "enh2892-parent", "--quiet"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )

    states = list(loops_dir.rglob("*enh2892-parent*.state.json"))
    assert states, f"no parent state file written under {loops_dir}; stderr={proc.stderr}"
    records = [json.loads(p.read_text()) for p in states]
    assert any(r.get("current_state") == "impl_failed" for r in records), records
    assert any(r.get("status") == "failed" for r in records), records
    assert proc.returncode != 0, proc.stderr
