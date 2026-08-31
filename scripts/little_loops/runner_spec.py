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
``PersistentExecutor`` directly for actual execution. ``ll-queue run``
(FEAT-2906) similarly never calls :func:`run_action` for ``LOOP`` entries —
it intercepts them beforehand and drives each through a subprocess
``ll-loop run`` shell-out (``cli/queue.py:_run_loop_entry``), not
``PersistentExecutor`` in-process.
"""

from __future__ import annotations

import json
import selectors
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from little_loops.host_runner import (
    AutomationContext,
    project_child_env,
    resolve_automation,
    resolve_host,
)
from little_loops.mcp_call import call_mcp_tool
from little_loops.subprocess_utils import _kill_process_group

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
    # FEAT-2878: ordered tool-call trace (dicts with "index"/"name"/"input"
    # keys, mirroring subprocess_utils.ToolCall) captured live during a
    # trace-mode SKILL/PROMPT run. None for every non-trace-mode run — a
    # defaulted field appended after `error`, so all existing keyword-only
    # construction sites (see Decision 1's call-site survey) are unaffected.
    tool_trace: list[dict[str, Any]] | None = None


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
    timeout: int | None = 120


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

    ``args["trace_mode"]`` (FEAT-2878, Decision 2) is a third mode, layered
    on top rather than a new ``RunnerType`` member: when True, the skill runs
    via the same streaming path as ``stream_callback``, but additionally
    captures an ordered tool-call trace (via
    :func:`little_loops.subprocess_utils.run_claude_command`'s
    ``on_tool_call``) into the returned :class:`RunnerResult`'s
    ``tool_trace``. ``args["workspace_root"]`` (``Path | str``), when set,
    is forwarded as ``working_dir`` and as ``workspace_root`` so a
    ``workspace_sandboxed`` host confines tool access to it.
    """
    assert spec.timeout is not None, "SKILL runner requires a concrete timeout (BUG-2928)"

    runner_args: list[str] = spec.args.get("runner_args") or []
    parts = [f"/ll:{spec.target}"] + runner_args
    prompt = " ".join(parts)
    stream_callback: Callable[[str, bool], None] | None = spec.args.get("stream_callback")
    trace_mode: bool = bool(spec.args.get("trace_mode"))

    # ENH-3097: automation= is the collapsed value, but the two legacy
    # spec.args keys stay live — this is the issue's only externally-facing
    # compatibility surface (no in-tree producer sets either key; consumers
    # are out-of-tree ll-harness/ll-action/extension runners). Fold via the
    # shared shim rather than reimplementing the merge inline.
    automation_arg: AutomationContext | None = spec.args.get("automation")

    # ENH-2714: opt-in automation-context static-prefix pruning profile, threaded
    # through from the caller (ll-harness/ll-action/ll-loop) so those CLIs don't
    # silently bypass pruning outside the FSM executor path. None (default)
    # preserves full unpruned behavior. Deprecated — prefer spec.args["automation"].
    automation_profile: str | None = spec.args.get("automation_profile")

    # FEAT-3078: opt-in hard-disable of tool-level background tasks, threaded
    # through the same args-dict origination as automation_profile above.
    # Deprecated — prefer spec.args["automation"].
    disable_background_tasks: bool = bool(spec.args.get("disable_background_tasks", False))

    automation = resolve_automation(
        automation_arg,
        automation_profile,
        disable_background_tasks,
        caller="_run_skill()",
    )

    # ENH-3130: grace period before escalating a timeout SIGTERM to SIGKILL,
    # threaded through the same args-dict origination as automation_profile
    # above. 0 (default) preserves the historical immediate-SIGKILL behavior.
    timeout_kill_grace_seconds: float = float(spec.args.get("timeout_kill_grace_seconds", 0.0))

    if trace_mode:
        from little_loops.subprocess_utils import ToolCall, run_claude_command

        command = f"/ll:{spec.target}"
        if runner_args:
            command += " " + " ".join(runner_args)
        workspace_root_arg = spec.args.get("workspace_root")
        workspace_root = Path(workspace_root_arg) if workspace_root_arg else None
        trace: list[ToolCall] = []
        try:
            proc = run_claude_command(
                command=command,
                timeout=spec.timeout,
                working_dir=workspace_root,
                stream_callback=stream_callback,
                automation=automation,
                tools=spec.args.get("tools"),
                on_tool_call=trace.append,
                workspace_root=workspace_root,
                timeout_kill_grace_seconds=timeout_kill_grace_seconds,
            )
            return RunnerResult(
                stdout="",
                stderr="",
                exit_code=proc.returncode,
                tool_trace=[{"index": c.index, "name": c.name, "input": c.input} for c in trace],
            )
        except subprocess.TimeoutExpired:
            return RunnerResult(
                stdout="",
                stderr="",
                exit_code=124,
                timed_out=True,
                tool_trace=[{"index": c.index, "name": c.name, "input": c.input} for c in trace],
            )

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
                automation=automation,
                timeout_kill_grace_seconds=timeout_kill_grace_seconds,
            )
            return RunnerResult(stdout="", stderr="", exit_code=proc.returncode)
        except subprocess.TimeoutExpired:
            return RunnerResult(stdout="", stderr="", exit_code=124, timed_out=True)

    inv = resolve_host().build_streaming(
        prompt=prompt,
        automation=automation,
    )
    try:
        proc = subprocess.run(
            [inv.binary, *inv.args],
            capture_output=True,
            text=True,
            timeout=spec.timeout,
            env=project_child_env(inv),
        )
        return RunnerResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
    except subprocess.TimeoutExpired:
        return RunnerResult(stdout="", stderr="", exit_code=2, timed_out=True)
    except FileNotFoundError as e:
        return RunnerResult(stdout="", stderr="", exit_code=2, error=str(e))


def _run_cmd(spec: ActionSpec) -> RunnerResult:
    """Run a shell command with deadline-enforced, deadlock-safe I/O draining.

    Selector-based read loop (mirrors ``fsm/runners.py``'s shell-command
    branch, BUG-2777) so ``spec.timeout`` bounds the entire call — including
    the stdout drain — not just the final ``process.wait()``. A blocking
    ``for line in process.stdout`` loop never reaches the wait() call while
    the child holds stdout open without exiting.
    """
    assert spec.timeout is not None, "CMD runner requires a concrete timeout (BUG-2928)"

    process = subprocess.Popen(
        ["bash", "-c", spec.target],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=project_child_env(extra={"LL_PYTHON": sys.executable}),
    )
    deadline = time.time() + spec.timeout

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    sel = selectors.DefaultSelector()
    if process.stdout is not None:
        sel.register(process.stdout, selectors.EVENT_READ, data="stdout")
    if process.stderr is not None:
        sel.register(process.stderr, selectors.EVENT_READ, data="stderr")

    timed_out = False
    try:
        while sel.get_map():
            remaining = deadline - time.time()
            if remaining <= 0:
                timed_out = True
                break
            ready = sel.select(timeout=min(1.0, remaining))
            if not ready:
                continue
            for key, _mask in ready:
                line = key.fileobj.readline()  # type: ignore[union-attr]
                if line:
                    if key.data == "stdout":
                        stdout_chunks.append(line)
                    else:
                        stderr_chunks.append(line)
                else:
                    sel.unregister(key.fileobj)
    finally:
        sel.close()

    if timed_out:
        _kill_process_group(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return RunnerResult(
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            exit_code=2,
            timed_out=True,
        )

    process.wait(timeout=5)
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
    assert spec.timeout is not None, "MCP runner requires a concrete timeout (BUG-2928)"

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
            env=project_child_env(inv),
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
