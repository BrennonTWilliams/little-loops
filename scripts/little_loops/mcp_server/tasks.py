"""FEAT-3145: the `tasks/get` / `tasks/cancel` poll surface for `ll-loop` runs.

Registered on the lowlevel `Server` via `Server.add_request_handler` — the mechanism
proven in `.ll/learning-tests/mcp-extension-mechanism.md` (claim 4) — rather than the
SDK's `Extension` API, which only attaches to `MCPServer(extensions=[...])` and has no
equivalent on the lowlevel `Server` `build_server()` constructs.

Scope: `ll-loop` only (Decision 2) — no `ll-queue` dispatch. No start path: starting a run
is FEAT-3151's territory, and nothing in this module spawns a process (AC 12).

SEP-2663 mirroring (AC 13), annotated per field/method so a later swap to the official
`io.modelcontextprotocol/tasks` extension is a registration change, not a client-visible
protocol change:

- `tasks/get` mirrors `GetTaskRequest`/`GetTaskResult`.
- `tasks/cancel` mirrors `CancelTaskRequest`/`CancelTaskResult`.
- `taskId` mirrors the spec's task handle field; here it *is* the `ll-loop` `instance_id`
  verbatim (Decision 5) rather than a server-minted handle.
- `status` mirrors the spec's task-status enum (`"working"`/`"completed"`/`"failed"`/
  `"cancelled"`); `runStatus` (this issue's own field, not spec-derived) carries the
  backend's raw `LoopState.status` verbatim alongside it, per Decision 3.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import mcp_types as types
from mcp.shared.exceptions import MCPError

if TYPE_CHECKING:
    from mcp.server.context import ServerRequestContext

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


def _loops_dir() -> Path:
    """Resolve the project's `.loops` directory fresh on every call (statelessness)."""
    from little_loops.config import BRConfig

    config = BRConfig(Path.cwd())
    return Path(config.loops.loops_dir)


def _not_found(task_id: str) -> MCPError:
    return MCPError(code=TASK_NOT_FOUND_CODE, message=f"no run found for taskId {task_id!r}")


async def handle_tasks_get(
    context: ServerRequestContext[Any, Any], params: TasksGetParams
) -> dict[str, Any]:
    """`tasks/get` — mirrors SEP-2663's `GetTaskResult`.

    Pure disk read: `read_run_status()` reconciles PID liveness (Decision 1) before
    reporting `"running"`, so a host never polls a run whose process died silently.
    """
    from little_loops.cli.loop.lifecycle import read_run_status
    from little_loops.fsm.types import ExecutionResult

    disk_status = read_run_status(params.task_id, _loops_dir())
    if disk_status is None:
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


async def handle_tasks_cancel(
    context: ServerRequestContext[Any, Any], params: TasksCancelParams
) -> dict[str, Any]:
    """`tasks/cancel` — mirrors SEP-2663's `CancelTaskResult`.

    Decision 3: never bare `"cancelled"`. `resumable` and the backend's raw `runStatus`
    always ride alongside, so a host cannot mistake a resumable `user_stopped` run for a
    genuinely terminal one.
    """
    from little_loops.cli.loop.lifecycle import cancel_run
    from little_loops.fsm.persistence import RESUMABLE_STATUSES
    from little_loops.logger import Logger

    # verbose=False: this handler may run under the stdio transport, where anything
    # printed to stdout corrupts JSON-RPC framing (Logger.info/.success write there).
    outcome = cancel_run(params.task_id, _loops_dir(), Logger(verbose=False))
    if outcome is None:
        raise _not_found(params.task_id)

    run_status = outcome["run_status"]
    return {
        "taskId": params.task_id,
        "status": "cancelled",
        "resumable": run_status in RESUMABLE_STATUSES,
        "runStatus": run_status,
    }
