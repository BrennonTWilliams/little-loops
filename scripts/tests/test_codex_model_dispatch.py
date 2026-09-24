"""BUG-3529: per-state / run model reaches the spawned Codex argv end to end."""

from __future__ import annotations

import io
import subprocess
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.runners import DefaultActionRunner
from little_loops.fsm.schema import EvaluateConfig
from little_loops.host_runner import CodexRunner
from tests.helpers import make_test_fsm, make_test_state


@pytest.fixture
def spawned_argv() -> Generator[list[list[str]], None, None]:
    """Force the Codex host and capture argv of every spawned process."""
    argvs: list[list[str]] = []
    popen_cls = subprocess.Popen

    def _popen(cmd: list[str], *args: Any, **kwargs: Any) -> MagicMock:
        argvs.append(list(cmd))
        proc = MagicMock(spec=popen_cls)
        proc.stdout = io.StringIO("")
        proc.stderr = io.StringIO("")
        proc.returncode = 0
        proc.poll.return_value = 0
        proc.wait.return_value = 0
        return proc

    with (
        patch("little_loops.subprocess_utils.resolve_host", return_value=CodexRunner()),
        patch("subprocess.Popen", side_effect=_popen),
        patch("selectors.DefaultSelector") as sel,
    ):
        inst = sel.return_value
        inst.__enter__.return_value = inst
        inst.__exit__.return_value = False
        inst.select.return_value = []
        inst.get_map.return_value = {}
        yield argvs


def _run(action: str, action_type: str | None, state_model: str | None, run_model: str | None):
    state = make_test_state(
        action=action,
        evaluate=EvaluateConfig(type="exit_code"),
        on_yes="done",
        on_no="done",
        model=state_model,
    )
    state.action_type = action_type  # type: ignore[assignment]
    fsm = make_test_fsm()
    fsm.states["start"] = state
    fsm.host_guard.enabled = False  # keep the vm_stat probe out of the Popen capture
    FSMExecutor(fsm, action_runner=DefaultActionRunner(), run_model=run_model).run()


_CASES = [
    ("prompt", "do the thing"),
    ("slash_command", "/ll:some-skill"),
    (None, "/ll:some-skill"),  # inferred from slash prefix
]


@pytest.mark.parametrize(("action_type", "action"), _CASES)
@pytest.mark.parametrize(
    ("state_model", "run_model", "expected"),
    [
        ("state-m", "run-m", "state-m"),
        ("state-m", None, "state-m"),
        (None, "run-m", "run-m"),
        (None, None, None),
    ],
)
def test_model_reaches_codex_argv(
    spawned_argv: list[list[str]],
    action_type: str | None,
    action: str,
    state_model: str | None,
    run_model: str | None,
    expected: str | None,
) -> None:
    _run(action, action_type, state_model, run_model)
    codex = [a for a in spawned_argv if a and a[0] == "codex"]
    assert len(codex) == 1, spawned_argv
    argv = codex[0]
    if expected is None:
        assert "--model" not in argv
    else:
        assert argv.count("--model") == 1
        assert argv[argv.index("--model") + 1] == expected
