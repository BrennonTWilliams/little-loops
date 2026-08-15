"""FEAT-3145: the `tasks/get` / `tasks/cancel` poll surface for `ll-loop` runs, plus
FEAT-3151's SEP-2663 start-path interceptor.

`tasks/get`/`tasks/cancel` are registered on the lowlevel `Server` via
`Server.add_request_handler` — the mechanism proven in
`.ll/learning-tests/mcp-extension-mechanism.md` (claim 4) — rather than the SDK's
`Extension` API, which only attaches to `MCPServer(extensions=[...])` and has no
equivalent on the lowlevel `Server` `build_server()` constructs. The start path
(`TasksExtension`) is different: it wraps `tools/call` itself, which *is* reachable on the
lowlevel `Server` via the free function `compose_tool_call_handler` (FEAT-3151 Decision 1),
proven in `.ll/learning-tests/mcp-tasks-start-path.md`.

Scope: `ll-loop` only (Decision 2) — no `ll-queue` dispatch.

SEP-2663 mirroring (AC 13/8), annotated per field/method so a later swap to the official
`io.modelcontextprotocol/tasks` extension is a registration change, not a client-visible
protocol change:

- `tasks/get` mirrors `GetTaskRequest`/`GetTaskResult`.
- `tasks/cancel` mirrors `CancelTaskRequest`/`CancelTaskResult`.
- The start path mirrors `CreateTaskResult` (hand-shaped, not `types.CreateTaskResult` —
  FEAT-3151 Decision 5).
- `taskId` mirrors the spec's task handle field; here it *is* the `ll-loop` `instance_id`
  verbatim (Decision 5) rather than a server-minted handle.
- `status` mirrors the spec's task-status enum (`"working"`/`"completed"`/`"failed"`/
  `"cancelled"`); `runStatus` (this issue's own field, not spec-derived) carries the
  backend's raw `LoopState.status` verbatim alongside it, per Decision 3.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import mcp_types as types
from mcp.server.extension import Extension
from mcp.shared.exceptions import MCPError

from little_loops.mcp_server.policy import POLICY_DENIED_CODE, check_tool_call

if TYPE_CHECKING:
    from mcp.server.context import CallNext, HandlerResult, ServerRequestContext

#: FEAT-3151 Decision 2a scoping note: the only tool name the start-path interceptor
#: re-shapes. Every other tool call passes through `call_next` untouched.
START_TOOL_NAME = "loop_start"

#: Implementation-defined server-error band (-32000..-32099), parallel to
#: `policy.POLICY_DENIED_CODE` (-32001). A `taskId` that resolves to no state file is a
#: distinct failure from a malformed request (INVALID_PARAMS): Decision 5 requires the two
#: be distinguishable, never a default "running" shape.
TASK_NOT_FOUND_CODE = -32002


class TasksGetParams(types.RequestParams):
    """Wire params for `tasks/get` — mirrors SEP-2663's `GetTaskRequest`.

    `task_id` aliases to `taskId` on the wire via `MCPModel`'s camelCase
    `alias_generator` (proven against the pinned SDK by the learning test's claim 4).
    """

    task_id: str


class TasksCancelParams(types.RequestParams):
    """Wire params for `tasks/cancel` — mirrors SEP-2663's `CancelTaskRequest`."""

    task_id: str


def _loops_dir(project_root: Path) -> Path:
    """Resolve the project's `.loops` directory from the given, already-resolved root.

    ENH-3171: `project_root` is threaded in via the same factory-closure shape `transport`
    already uses — resolved once by `main_mcp`/`build_server`, not re-resolved from
    `Path.cwd()` here on every call.

    BUG-3180: goes through `get_loops_dir()`, the *joining* accessor, rather than
    `config.loops.loops_dir`, which is the raw config string (`".loops"`) and therefore
    relative. Reading the raw field here silently re-anchored every run path on the
    process cwd, undoing ENH-3171 for `loop_start`/`tasks/get`/`tasks/cancel` even
    though the resolved root was already in hand.
    """
    from little_loops.config import BRConfig

    return BRConfig(project_root).get_loops_dir()


def _not_found(task_id: str) -> MCPError:
    return MCPError(code=TASK_NOT_FOUND_CODE, message=f"no run found for taskId {task_id!r}")


def mint_start_instance_id(loop_name: str, loops_dir: Path) -> str:
    """Mint a fresh `instance_id` for a run the start path is about to spawn.

    FEAT-3151 Decision 3: does not call `_make_instance_id()` directly — its
    one-second timestamp resolution can collide when an MCP agent issues two starts
    of the same loop inside one second. Appends a short entropy suffix and
    check-and-bumps against `.running/` so the returned id is guaranteed free of
    both PID and state files at mint time.
    """
    from little_loops.cli.loop._helpers import _make_instance_id

    running_dir = loops_dir / ".running"
    base = _make_instance_id(loop_name)
    while True:
        candidate = f"{base}-{secrets.token_hex(2)}"
        if (
            not (running_dir / f"{candidate}.pid").exists()
            and not (running_dir / f"{candidate}.state.json").exists()
        ):
            return candidate


def make_tasks_get_handler(
    transport: str,
    project_root: Path,
) -> Callable[[ServerRequestContext[Any, Any], TasksGetParams], Any]:
    """Build the `tasks/get` handler, bound to the transport it is served over (FEAT-3168)

    and the resolved project root (ENH-3171).
    """

    async def handle_tasks_get(
        context: ServerRequestContext[Any, Any], params: TasksGetParams
    ) -> dict[str, Any]:
        """`tasks/get` — mirrors SEP-2663's `GetTaskResult`.

        Pure disk read: `read_run_status()` reconciles PID liveness (Decision 1) before
        reporting `"running"`, so a host never polls a run whose process died silently.

        FEAT-3151 Decision 9: when no state file exists yet (the just-spawned run's child
        has not written one), falls back to the PID file the parent wrote before returning
        — closing the start-then-immediately-poll visibility window a bare "not found"
        would otherwise open.
        """
        from little_loops.config import BRConfig

        decision = check_tool_call(transport, "tasks/get", None, config=BRConfig(project_root))
        if not decision.allowed:
            raise MCPError(code=POLICY_DENIED_CODE, message=decision.reason)

        from little_loops.cli.loop.lifecycle import read_run_status
        from little_loops.fsm.concurrency import _process_alive
        from little_loops.fsm.persistence import _read_pid_file
        from little_loops.fsm.types import ExecutionResult

        loops_dir = _loops_dir(project_root)
        disk_status = read_run_status(params.task_id, loops_dir)
        if disk_status is None:
            pid = _read_pid_file(loops_dir / ".running" / f"{params.task_id}.pid")
            if pid is not None and _process_alive(pid):
                return {"taskId": params.task_id, "status": "working", "runStatus": "starting"}
            raise _not_found(params.task_id)

        run_status = disk_status["status"]
        result: dict[str, Any] = {"taskId": params.task_id, "runStatus": run_status}

        if run_status == "running":
            result["status"] = "working"
            return result

        result["status"] = "completed" if run_status == "completed" else "failed"
        # AC 2: shape the terminal-run fields exactly as ExecutionResult.to_dict() would —
        # LoopState never stores an ExecutionResult, so this reconstructs the closest
        # equivalent from what is actually persisted (Integration Map, fsm/persistence.py).
        result.update(
            ExecutionResult(
                final_state=disk_status["current_state"],
                iterations=disk_status["iteration"],
                terminated_by=run_status,
                duration_ms=disk_status.get("accumulated_ms", 0),
                captured=disk_status.get("captured", {}),
            ).to_dict()
        )
        return result

    return handle_tasks_get


def make_tasks_cancel_handler(
    transport: str,
    project_root: Path,
) -> Callable[[ServerRequestContext[Any, Any], TasksCancelParams], Any]:
    """Build the `tasks/cancel` handler, bound to the transport it is served over (FEAT-3168)

    and the resolved project root (ENH-3171).
    """

    async def handle_tasks_cancel(
        context: ServerRequestContext[Any, Any], params: TasksCancelParams
    ) -> dict[str, Any]:
        """`tasks/cancel` — mirrors SEP-2663's `CancelTaskResult`.

        Decision 3: never bare `"cancelled"`. `resumable` and the backend's raw `runStatus`
        always ride alongside, so a host cannot mistake a resumable `user_stopped` run for a
        genuinely terminal one.

        FEAT-3151 Decision 9 applies to this half too: `cancel_run` falls back to the PID
        file when no state file exists yet, so a run started via `loop_start` is stoppable
        during its child's startup window rather than reporting task-not-found. That path
        reports `runStatus: "starting"` — the same vocabulary `handle_tasks_get` uses for
        the window — and `resumable: false`.
        """
        from little_loops.config import BRConfig

        decision = check_tool_call(transport, "tasks/cancel", None, config=BRConfig(project_root))
        if not decision.allowed:
            raise MCPError(code=POLICY_DENIED_CODE, message=decision.reason)

        from little_loops.cli.loop.lifecycle import cancel_run
        from little_loops.fsm.persistence import RESUMABLE_STATUSES
        from little_loops.logger import Logger

        # verbose=False: this handler may run under the stdio transport, where anything
        # printed to stdout corrupts JSON-RPC framing (Logger.info/.success write there).
        outcome = cancel_run(params.task_id, _loops_dir(project_root), Logger(verbose=False))
        if outcome is None:
            raise _not_found(params.task_id)

        run_status = outcome["run_status"]
        return {
            "taskId": params.task_id,
            "status": "cancelled",
            "resumable": run_status in RESUMABLE_STATUSES,
            "runStatus": run_status,
        }

    return handle_tasks_cancel


class TasksExtension(Extension):
    """FEAT-3151: the SEP-2663 start-path interceptor — mirrors `CreateTaskRequest`'s
    per-request opt-in and `CreateTaskResult`'s response shape.

    Locally authored: the pinned SDK ships no `io.modelcontextprotocol/tasks` extension
    (Program Design "Types" note). Composed onto `handle_call_tool` via
    `compose_tool_call_handler([TasksExtension()], handle_call_tool)` in
    `server.py::build_server` (Decision 1) — a free function, so this works on the
    lowlevel `Server` despite that class having no `extensions=` parameter.

    The spawn itself never happens here (Decision 2a's implementation note): `call_next`
    already ran the `loop_start` tool's handler (`tools.py::_tool_loop_start`), which
    always performs the identical detached spawn regardless of caller. This interceptor
    only decides **result shape** — reshape into a task envelope, or pass the plain
    `CallToolResult` through unchanged — evaluating three independent signals, proven
    live on the pinned SDK by `.ll/learning-tests/mcp-tasks-start-path.md`'s Step 0
    addendum:

    1. **Declared capability** — the client claimed the tasks extension in this request's
       `_meta.clientCapabilities.extensions` (Decision 2, condition 1).
    2. **Per-call opt-in** — `params.task` is set on this call (Decision 2, condition 2;
       mirrors `CreateTaskRequest`'s `task: TaskMetadata` augmentation field).
    3. **Modern protocol version** — `ctx.protocol_version` is one of the 2026-07-28-era
       per-request-envelope versions that carry the `clientCapabilities` `_meta` at all
       (Decision 6).
    """

    identifier = "io.modelcontextprotocol/tasks"

    async def intercept_tool_call(
        self,
        params: types.CallToolRequestParams,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        # Decision 2a scoping note: every tool but the start tool passes through
        # untouched, regardless of capability or params.task. Keeps AC 7 true for every
        # existing tool.
        if params.name != START_TOOL_NAME:
            return await call_next(ctx)

        # The spawn always lives in one place: inside call_next's handler dispatch.
        result = await call_next(ctx)

        from mcp.server.runner import MODERN_PROTOCOL_VERSIONS

        meta = ctx.meta or {}  # ctx.meta is Optional — a request with no `_meta` at all.
        # RequestParamsMeta is an open TypedDict, so mypy sees .get() as returning `object`;
        # the shape is proven by the Step 0 addendum in mcp-tasks-start-path.md.
        caps: dict[str, Any] = meta.get(types.CLIENT_CAPABILITIES_META_KEY) or {}  # type: ignore[assignment]
        declared = "io.modelcontextprotocol/tasks" in (caps.get("extensions") or {})
        wants_task = params.task is not None
        is_modern = ctx.protocol_version in MODERN_PROTOCOL_VERSIONS

        if not (declared and wants_task and is_modern):
            # AC 2/2b/2c: any missing signal means the plain path. Same detached spawn,
            # ordinary CallToolResult — shape differs, behavior (the run started) does not.
            return result

        # Decision 2a error pass-through: never wrap a spawn failure in a task envelope —
        # that would be a taskId for a run that does not exist (Decision 7 forbids this).
        if not isinstance(result, types.CallToolResult) or result.is_error:
            return result

        # Decision 2a extraction note: handle_call_tool attaches the payload to
        # structured_content only when it is a dict (tools.py:786-789); guard rather
        # than trust it, and never parse content[0].text.
        structured = result.structured_content
        if structured is None:
            return result

        # Same reasoning one step further in: an envelope whose taskId is null is a task
        # handle that resolves to nothing, which is the failure mode Decision 7 forbids —
        # only reachable if the start tool's payload ever stops carrying `instance_id`, so
        # fall back to the plain result rather than emitting a handle no one can poll.
        instance_id = structured.get("instance_id")
        if not instance_id:
            return result

        # SEP-2663 CreateTaskResult mirror (Decision 5): hand-built dict carrying a
        # top-level resultType, not types.CreateTaskResult (which dumps to {"task": {...}}
        # with no resultType and would fail the spec-method sieve). AC 4b: status is the
        # literal "working" — the same value handle_tasks_get maps a running run to.
        return {
            "resultType": "task",  # mirrors CreateTaskResult's discriminator
            "taskId": instance_id,  # mirrors Task.task_id (Decision 3)
            "status": "working",  # mirrors Task.status
        }
