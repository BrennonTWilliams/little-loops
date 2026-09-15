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
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from little_loops.host_runner import (
    AutomationContext,
    gh_scope_extra,
    project_child_env,
    resolve_automation,
    resolve_host,
    resolve_scopes,
)
from little_loops.mcp_call import call_mcp_tool
from little_loops.subprocess_utils import _kill_process_group, usage_from_stream_lines

__all__ = [
    "RunnerType",
    "RunnerResult",
    "ActionSpec",
    "run_action",
    "scope_runner_error",
    "is_stochastic_runner",
    "DEFAULT_STOCHASTIC_SAMPLES",
]


class RunnerType(Enum):
    """The kinds of runner invocations ll-harness/ll-action/ll-loop dispatch."""

    SKILL = "skill"
    CMD = "cmd"
    MCP = "mcp"
    PROMPT = "prompt"
    DSL = "dsl"
    LOOP = "loop"


# ENH-3415 D6: whether a RunnerType's subject varies run to run (an LLM-driven
# host CLI invocation) vs. is deterministic (a subprocess/tool call with no
# LLM in the loop). DSL is "stochastic" in the sense that its per-task PROMPT
# calls are, but it already loops across tasks and resamples separately (see
# ll-harness's own --samples refusal for the dsl runner) so its own default
# stays 1. LOOP is never dispatched by run_action() and is omitted here;
# is_stochastic_runner(RunnerType.LOOP) raises KeyError, which is acceptable.
_STOCHASTIC_RUNNERS: dict[RunnerType, bool] = {
    RunnerType.SKILL: True,
    RunnerType.PROMPT: True,
    RunnerType.CMD: False,
    RunnerType.MCP: False,
    RunnerType.DSL: True,
}

DEFAULT_STOCHASTIC_SAMPLES = 3


def is_stochastic_runner(runner: RunnerType) -> bool:
    """Return whether *runner*'s subject is stochastic (ENH-3415 D6).

    Raises ``KeyError`` for ``RunnerType.LOOP``, which is never dispatched by
    :func:`run_action` and has no meaningful classification here.
    """
    return _STOCHASTIC_RUNNERS[runner]


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
    # ENH-3464: efficiency vector, parsed post hoc from captured stdout (no
    # streaming callback wiring — see subprocess_utils.usage_from_stream_lines).
    # Populated by _run_skill()'s default blocking branch and _run_prompt();
    # _run_cmd()/_run_mcp() never invoke a host CLI so stay None. None on a
    # timed-out or errored run (stdout is empty/unavailable in both cases).
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    # tool_calls counts top-level `tool_use` blocks only (SKILL path); calls
    # made inside an Agent-tool subagent never appear in the parent stream.
    # Always None on the PROMPT/DSL path (claude-code's blocking JSON mode
    # emits no tool_use blocks; codex item.* events aren't tallied).
    tool_calls: int | None = None


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
    # ENH-3234: credential-scope names (resolved against host_runner.CREDENTIAL_SCOPES)
    # naming the env vars this task's `_run_cmd()` spawn is allowed to inherit. None
    # (the default) keeps today's coarse full-inherit behavior; opt-in per spec.
    scopes: frozenset[str] | None = None


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
        usage, tool_calls = usage_from_stream_lines(proc.stdout)
        return RunnerResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            cache_read_tokens=usage.cache_read_tokens if usage else None,
            cache_creation_tokens=usage.cache_creation_tokens if usage else None,
            tool_calls=tool_calls,
        )
    except subprocess.TimeoutExpired:
        return RunnerResult(stdout="", stderr="", exit_code=2, timed_out=True)
    except FileNotFoundError as e:
        return RunnerResult(stdout="", stderr="", exit_code=2, error=str(e))


def _run_cmd(spec: ActionSpec, *, run_id: str | None = None) -> RunnerResult:
    """Run a shell command with deadline-enforced, deadlock-safe I/O draining.

    Selector-based read loop (mirrors ``fsm/runners.py``'s shell-command
    branch, BUG-2777) so ``spec.timeout`` bounds the entire call — including
    the stdout drain — not just the final ``process.wait()``. A blocking
    ``for line in process.stdout`` loop never reaches the wait() call while
    the child holds stdout open without exiting.

    BUG-3400: mirrors ``fsm/runners.py``'s ``gh``-isolation wiring so this
    (queue/CMD) dispatch path gets the same guarantees the FSM shell path
    already has — ``GH_CONFIG_DIR`` redirected to a per-spawn tempdir (and
    ``GH_TOKEN`` injected iff ``"github"`` is declared) whenever
    ``spec.scopes is not None``, plus a best-effort ``credential_scope_events``
    audit row so both dispatch paths produce identical audit trails.
    """
    assert spec.timeout is not None, "CMD runner requires a concrete timeout (BUG-2928)"

    env_allow: frozenset[str] | None = None
    if spec.scopes is not None:
        try:
            env_allow = resolve_scopes(spec.scopes)
        except ValueError as e:
            return RunnerResult(stdout="", stderr="", exit_code=2, error=str(e))

        # ENH-3204/BUG-3400: record the grant before the spawn — the record
        # describes the grant, not the outcome. Best-effort, mirrors
        # fsm/executor.py's write_credential_scope call: an audit write must
        # never fail the run.
        try:
            from little_loops.session_store import resolve_history_db, write_credential_scope

            write_credential_scope(
                resolve_history_db(),
                run_id=run_id or spec.name,
                state=spec.name,
                scopes=frozenset(spec.scopes),
                var_names=env_allow,
            )
        except Exception:
            pass  # Non-fatal (ENH-3204)

    extra: dict[str, str] = {"LL_PYTHON": sys.executable}
    gh_tmp: tempfile.TemporaryDirectory[str] | None = None
    if spec.scopes is not None:
        gh_tmp = tempfile.TemporaryDirectory(prefix="ll-gh-")
        try:
            extra.update(gh_scope_extra(Path(gh_tmp.name), with_token="github" in spec.scopes))
        except RuntimeError as exc:
            gh_tmp.cleanup()
            return RunnerResult(stdout="", stderr="", exit_code=2, error=str(exc))

    script_path: str | None = None
    try:
        # BUG-3439: write the rendered script to a temp file and spawn
        # ["bash", path] rather than ["bash", "-c", spec.target] — mirrors
        # fsm/runners.py's shell branch (same MAX_ARG_STRLEN exposure).
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            prefix="ll-action-",
            suffix=".sh",
        ) as script_file:
            script_file.write(spec.target)
            script_path = script_file.name
        process = subprocess.Popen(
            ["bash", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=project_child_env(extra=extra, env_allow=env_allow),
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
    finally:
        if gh_tmp is not None:
            gh_tmp.cleanup()
        if script_path is not None:
            try:
                Path(script_path).unlink()
            except OSError:
                pass


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
        usage, tool_calls = usage_from_stream_lines(proc.stdout)
        return RunnerResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            cache_read_tokens=usage.cache_read_tokens if usage else None,
            cache_creation_tokens=usage.cache_creation_tokens if usage else None,
            tool_calls=tool_calls,
        )
    except subprocess.TimeoutExpired:
        return RunnerResult(stdout="", stderr="", exit_code=2, timed_out=True)
    except FileNotFoundError as e:
        return RunnerResult(stdout="", stderr="", exit_code=2, error=str(e))


_DISPATCH: dict[RunnerType, Callable[[ActionSpec], RunnerResult]] = {
    RunnerType.SKILL: _run_skill,
    RunnerType.MCP: _run_mcp,
    RunnerType.PROMPT: _run_prompt,
}


def scope_runner_error(spec: ActionSpec) -> str | None:
    """Return a rejection message if *spec* declares scopes on a non-CMD runner, else None.

    ENH-3403: ``scopes`` is enforced only by ``_run_cmd()``; ``_run_skill()``,
    ``_run_prompt()``, and ``_run_mcp()`` have no equivalent ``env_allow``/
    ``gh_scope_extra()``/``write_credential_scope()`` wiring, so a declared
    ``scopes`` on those runners must fail loud rather than silently dispatch
    unscoped (the ActionSpec-side twin of ``structural_rules.py``'s FSM
    shell-only ``scopes`` check).
    """
    if spec.scopes is not None and spec.runner is not RunnerType.CMD:
        return (
            f"ActionSpec {spec.name!r} declares 'scopes' but runner is "
            f"{spec.runner.value!r}; scopes are enforced only for RunnerType.CMD"
        )
    return None


def run_action(spec: ActionSpec, *, run_id: str | None = None) -> RunnerResult:
    """Dispatch an :class:`ActionSpec` to its runner and return a :class:`RunnerResult`.

    ``RunnerType.DSL`` is a batch driver over ``RunnerType.PROMPT`` (one
    ``run_action`` call per task), not an independent execution path — callers
    loop and call this function once per task. ``RunnerType.LOOP`` is not
    dispatched here at all; see the module docstring.

    *run_id* (BUG-3400) is forwarded only to the ``RunnerType.CMD`` handler,
    which uses it as the ``credential_scope_events`` audit key when the spec
    declares scopes (falling back to ``spec.name`` when omitted). Other
    runner types have no equivalent audit wiring yet and ignore it.
    """
    if spec.runner is RunnerType.CMD:
        return _run_cmd(spec, run_id=run_id)
    handler = _DISPATCH.get(spec.runner)
    if handler is None:
        raise ValueError(f"run_action() does not dispatch runner type: {spec.runner}")
    scope_error = scope_runner_error(spec)
    if scope_error is not None:
        return RunnerResult(stdout="", stderr="", exit_code=2, error=scope_error)
    return handler(spec)
