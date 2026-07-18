"""Shared runner abstraction for ll-action/ll-harness/ll-loop (ENH-2668).

Extracts the runner-kind dispatch that ``ll-harness`` and ``ll-action``
previously each implemented as their own if/elif ladder into a single
``RunnerType`` enum, an ``ActionSpec`` value object describing one
invocation, and a ``run_action()`` dispatch function returning a shared
``RunnerResult``.

Modeled on :mod:`little_loops.host_runner`'s frozen-dataclass-crossing-a-
boundary + registry-backed-dispatch shape (see that module's docstring).

``RunnerType.LOOP`` is intentionally *not* handled by :func:`run_action`.
FSM loop execution (``PersistentExecutor``/``run_foreground()``) is a
stateful, resumable, multi-state engine — not a single blocking call — so
forcing it through the one-shot ``ActionSpec -> RunnerResult`` shape would
misrepresent its behavior. ``cli/loop/run.py`` builds a ``RunnerType.LOOP``
``ActionSpec`` for structural/observability parity only; it keeps calling
``PersistentExecutor`` directly for actual execution.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from little_loops.host_runner import resolve_host
from little_loops.mcp_call import call_mcp_tool

__all__ = [
    "RunnerType",
    "RunnerResult",
    "ActionSpec",
    "run_action",
]


class RunnerType(Enum):
    """The kinds of runner invocations ll-harness/ll-action/ll-loop dispatch."""

    SKILL = "skill"
    CMD = "cmd"
    MCP = "mcp"
    PROMPT = "prompt"
    DSL = "dsl"
    LOOP = "loop"


@dataclass
class RunnerResult:
    """Captured output from a runner invocation."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    error: str | None = None


@dataclass(frozen=True)
class ActionSpec:
    """Describes one runner invocation to dispatch via :func:`run_action`.

    Frozen for the same reason as :class:`~little_loops.host_runner.HostInvocation`:
    instances cross the runner/caller boundary.
    """

    name: str
    runner: RunnerType
    target: str
    args: dict[str, Any] = field(default_factory=dict)
    timeout: int = 120


def _run_skill(spec: ActionSpec) -> RunnerResult:
    """Invoke a little-loops skill via the active host CLI.

    ``args["stream_callback"]`` selects between two historical execution
    paths that predate this extraction and must remain byte-for-byte
    unchanged (ENH-2668 AC):

    - unset (ll-harness's ``skill`` runner): blocking ``subprocess.run``
      with captured stdout/stderr, suitable for pass/fail evaluation.
    - set (ll-action's ``invoke`` command): streaming execution via
      :func:`little_loops.subprocess_utils.run_claude_command`, which
      invokes the callback per output line as it arrives.
    """
    runner_args: list[str] = spec.args.get("runner_args") or []
    parts = [f"/ll:{spec.target}"] + runner_args
    prompt = " ".join(parts)
    stream_callback: Callable[[str, bool], None] | None = spec.args.get("stream_callback")

    if stream_callback is not None:
        from little_loops.subprocess_utils import run_claude_command

        command = f"/ll:{spec.target}"
        if runner_args:
            command += " " + " ".join(runner_args)
        try:
            proc = run_claude_command(
                command=command,
                timeout=spec.timeout,
                stream_callback=stream_callback,
            )
            return RunnerResult(stdout="", stderr="", exit_code=proc.returncode)
        except subprocess.TimeoutExpired:
            return RunnerResult(stdout="", stderr="", exit_code=124, timed_out=True)

    inv = resolve_host().build_streaming(prompt=prompt)
    try:
        proc = subprocess.run(
            [inv.binary, *inv.args],
            capture_output=True,
            text=True,
            timeout=spec.timeout,
            env={**os.environ, **inv.env},
        )
        return RunnerResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
    except subprocess.TimeoutExpired:
        return RunnerResult(stdout="", stderr="", exit_code=2, timed_out=True)
    except FileNotFoundError as e:
        return RunnerResult(stdout="", stderr="", exit_code=2, error=str(e))


def _run_cmd(spec: ActionSpec) -> RunnerResult:
    """Run a shell command with deadlock-safe stderr draining."""
    process = subprocess.Popen(
        ["bash", "-c", spec.target],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def _drain_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            stderr_chunks.append(line)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        assert process.stdout is not None
        for line in process.stdout:
            stdout_chunks.append(line)
        process.wait(timeout=spec.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        stderr_thread.join(timeout=5)
        return RunnerResult(
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            exit_code=2,
            timed_out=True,
        )

    stderr_thread.join(timeout=5)
    return RunnerResult(
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
        exit_code=process.returncode,
    )


def _run_mcp(spec: ActionSpec) -> RunnerResult:
    """Call an MCP tool. ``spec.target`` must already be validated ``server:tool``.

    Callers must validate ``server:tool`` shape and parse ``--args`` JSON
    themselves before dispatching — those are CLI input-validation concerns,
    not runner dispatch, and their error reporting predates (and differs
    from) the shared :class:`RunnerResult`/``_evaluate_and_report`` path.
    """
    server, tool = spec.target.split(":", 1)
    params: dict[str, Any] = spec.args.get("mcp_params") or {}
    response, exit_code = call_mcp_tool(server, tool, params, timeout=spec.timeout)
    return RunnerResult(stdout=json.dumps(response), stderr="", exit_code=exit_code)


def _run_prompt(spec: ActionSpec) -> RunnerResult:
    """Send a raw prompt to the active host CLI (blocking, JSON-mode)."""
    model: str | None = spec.args.get("model")
    inv = resolve_host().build_blocking_json(prompt=spec.target, model=model)

    try:
        proc = subprocess.run(
            [inv.binary, *inv.args],
            capture_output=True,
            text=True,
            timeout=spec.timeout,
        )
        return RunnerResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
    except subprocess.TimeoutExpired:
        return RunnerResult(stdout="", stderr="", exit_code=2, timed_out=True)
    except FileNotFoundError as e:
        return RunnerResult(stdout="", stderr="", exit_code=2, error=str(e))


_DISPATCH: dict[RunnerType, Callable[[ActionSpec], RunnerResult]] = {
    RunnerType.SKILL: _run_skill,
    RunnerType.CMD: _run_cmd,
    RunnerType.MCP: _run_mcp,
    RunnerType.PROMPT: _run_prompt,
}


def run_action(spec: ActionSpec) -> RunnerResult:
    """Dispatch an :class:`ActionSpec` to its runner and return a :class:`RunnerResult`.

    ``RunnerType.DSL`` is a batch driver over ``RunnerType.PROMPT`` (one
    ``run_action`` call per task), not an independent execution path — callers
    loop and call this function once per task. ``RunnerType.LOOP`` is not
    dispatched here at all; see the module docstring.
    """
    handler = _DISPATCH.get(spec.runner)
    if handler is None:
        raise ValueError(f"run_action() does not dispatch runner type: {spec.runner}")
    return handler(spec)
