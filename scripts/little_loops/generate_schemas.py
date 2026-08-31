"""JSON Schema generation for all 48 LLEvent types.

Generates one JSON Schema (draft-07) file per event type to docs/reference/schemas/.
Schemas validate the flat wire format: {"event": type, "ts": timestamp, ...payload}.

Usage:
    python -m little_loops.generate_schemas [--output OUTPUT_DIR]

Or via CLI:
    ll-generate-schemas [--output OUTPUT_DIR]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Schema building helpers
# ---------------------------------------------------------------------------

_DRAFT07 = "http://json-schema.org/draft-07/schema#"

_BASE_PROPS: dict[str, Any] = {
    "event": {"type": "string", "description": "Event type identifier"},
    "ts": {"type": "string", "format": "date-time", "description": "ISO 8601 timestamp"},
    "run_id": {
        "type": "string",
        "description": (
            "Run-scoped identity, stable across a run (including pause/resume). "
            "Stamped by FSMExecutor._emit()-routed events (ENH-3345) and by every "
            "parallel.* emitter (ENH-3346); required on all parallel.* events, "
            "optional elsewhere."
        ),
    },
    "loop": {
        "type": "string",
        "description": (
            "Loop name, stamped on every FSMExecutor._emit()-routed event (ENH-3345). "
            "Not required for the same reason as run_id."
        ),
    },
}

_BASE_REQUIRED = ["event", "ts"]


def _str(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _int(description: str) -> dict[str, Any]:
    return {"type": "integer", "description": description}


def _number(description: str) -> dict[str, Any]:
    return {"type": "number", "description": description}


def _bool(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


def _nullable_str(description: str) -> dict[str, Any]:
    return {"type": ["string", "null"], "description": description}


def _nullable_bool(description: str) -> dict[str, Any]:
    return {"type": ["boolean", "null"], "description": description}


def _schema(
    event_type: str,
    title: str,
    description: str,
    extra_props: dict[str, Any],
    extra_required: list[str] | None = None,
) -> dict[str, Any]:
    """Build a complete JSON Schema dict for an event type."""
    return {
        "$schema": _DRAFT07,
        "$id": f"little-loops://event-{event_type}.json",
        "title": title,
        "description": description,
        "type": "object",
        "required": _BASE_REQUIRED + (extra_required or []),
        "properties": {**_BASE_PROPS, **extra_props},
        "additionalProperties": True,
    }


# ---------------------------------------------------------------------------
# Schema definitions — all 26 LLEvent types
# Source of truth: docs/reference/EVENT-SCHEMA.md
# ---------------------------------------------------------------------------

SCHEMA_DEFINITIONS: dict[str, dict[str, Any]] = {
    # FSM Executor (15 types)
    "loop_start": _schema(
        "loop_start",
        "Loop Start",
        "Emitted when an FSM loop begins execution.",
        {"loop": _str("Loop name")},
        ["loop"],
    ),
    "state_enter": _schema(
        "state_enter",
        "State Enter",
        "Emitted when the FSM enters a state.",
        {
            "state": _str("State name"),
            "iteration": _int("Step count (1-based); increments on every state entry"),
            "iteration_count": _int(
                "Full-pass (maintain-mode) restart count (0-based); 0 for loops without maintain"
            ),
            "flushed": _bool(
                "Present and true only when the executor flushed a pending shell-action "
                "state before honoring a wall-clock timeout (BUG-1226)."
            ),
        },
        ["state", "iteration"],
    ),
    "route": _schema(
        "route",
        "Route",
        "Emitted when the FSM transitions between states.",
        {
            "from": _str("Source state name"),
            "to": _str("Destination state name"),
            "reason": _str("Optional transition reason"),
        },
        ["from", "to"],
    ),
    "action_start": _schema(
        "action_start",
        "Action Start",
        "Emitted when a state action begins.",
        {
            "action": _str("Action name or command"),
            "is_prompt": _bool("True if action is a Claude prompt, false for shell command"),
        },
        ["action", "is_prompt"],
    ),
    "action_output": _schema(
        "action_output",
        "Action Output",
        "Emitted for each line of output from a running action.",
        {"line": _str("Output line text")},
        ["line"],
    ),
    "action_complete": _schema(
        "action_complete",
        "Action Complete",
        "Emitted when an action finishes.",
        {
            "exit_code": _int("Process exit code (0 = success)"),
            "duration_ms": _int("Execution duration in milliseconds"),
            "output_preview": _nullable_str("Short preview of output, null if none"),
            "is_prompt": _bool("True if action was a Claude prompt"),
            "session_jsonl": _nullable_str(
                "Path to Claude session JSONL file (prompt-only, null for shell commands)"
            ),
            "input_tokens": _int("Input tokens consumed (prompt/slash_command only)"),
            "output_tokens": _int("Output tokens generated (prompt/slash_command only)"),
            "cache_read_tokens": _int("Cache read tokens consumed (prompt/slash_command only)"),
            "cache_creation_tokens": _int(
                "Cache creation tokens written (prompt/slash_command only)"
            ),
            "model": _str("Model ID reported by the host CLI (prompt/slash_command only)"),
            "state": _str(
                "FSM state whose action produced this event (ENH-3240; absent on "
                "archived runs and on the non-FSM ll-action emitter)"
            ),
            "iteration": _int(
                "Executor step count when this action ran (ENH-3240; absent on "
                "archived runs and on the non-FSM ll-action emitter)"
            ),
            "stderr_preview": _nullable_str(
                "Short preview of stderr output, null if none (ENH-2469)"
            ),
            "effort": _str("Reasoning effort level applied (prompt actions only, ENH-2885)"),
            "is_batch": _bool("True if the host CLI invocation was a batch request (FEAT-2716)"),
        },
        ["exit_code", "duration_ms", "is_prompt"],
    ),
    "action_error": _schema(
        "action_error",
        "Action Error",
        "Emitted when an action raises an unhandled exception that is routed to on_error.",
        {
            "state": _str("State name whose action raised"),
            "error": _str("String representation of the raised exception"),
            "route": _str("Route taken in response to the exception (always 'on_error')"),
        },
        ["state", "error", "route"],
    ),
    "messages_append": _schema(
        "messages_append",
        "Messages Append",
        "Emitted when a state's append_to_messages field is set and the state's "
        "action completes. The interpolated message is appended to the executor's "
        "in-memory messages list and mirrored onto the event bus.",
        {
            "message": _str("The interpolated message text that was appended"),
            "state": _str("Name of the state whose append_to_messages fired"),
        },
        ["message", "state"],
    ),
    "sub_loop_worktree_attached": _schema(
        "sub_loop_worktree_attached",
        "Sub-Loop Worktree Attached",
        "Emitted when a state.worktree-configured sub-loop call (ENH-2609) "
        "successfully sets up a dedicated git worktree for the child loop.",
        {
            "branch": _str("Interpolated state.worktree branch name"),
            "path": _str("Filesystem path to the created worktree"),
        },
        ["branch", "path"],
    ),
    "sub_loop_worktree_detached": _schema(
        "sub_loop_worktree_detached",
        "Sub-Loop Worktree Detached",
        "Emitted after the child loop finishes and its dedicated worktree is "
        "torn down. Only the worktree checkout is removed; the branch is not "
        "auto-deleted.",
        {
            "branch": _str("Interpolated state.worktree branch name"),
            "path": _str("Filesystem path of the worktree that was torn down"),
        },
        ["branch", "path"],
    ),
    "sub_loop_worktree_error": _schema(
        "sub_loop_worktree_error",
        "Sub-Loop Worktree Error",
        "Emitted when setup_worktree() raises a RuntimeError while attaching a "
        "per-state worktree for a sub-loop call.",
        {
            "branch": _str("Interpolated state.worktree branch name that failed to attach"),
            "error": _str("String representation of the raised RuntimeError"),
        },
        ["branch", "error"],
    ),
    "prepatch_check_flagged": _schema(
        "prepatch_check_flagged",
        "Prepatch Check Flagged",
        "Emitted when a state's prepatch_check guard runs in 'warn' policy mode "
        "and the pre-patch evidence check returns a 'flagged' verdict.",
        {
            "state": _str("Name of the state whose prepatch check flagged"),
            "policy": _str("Configured prepatch_check policy (always 'warn' when this fires)"),
            "outcomes": _int("Count of outcomes recorded in the evidence bundle"),
        },
        ["state", "policy", "outcomes"],
    ),
    "baseline_complete": _schema(
        "baseline_complete",
        "Baseline Complete",
        "Emitted once per compared item during an A/B baseline run, after the "
        "harness arm and baseline arm both finish executing in parallel and "
        "before the blind comparator runs.",
        {
            "harness_duration_ms": _int("Wall-clock duration of the harness arm, in ms"),
            "baseline_duration_ms": _int("Wall-clock duration of the baseline arm, in ms"),
            "harness_tokens": _int("Total tokens (input + output) consumed by the harness arm"),
            "baseline_tokens": _int("Total tokens (input + output) consumed by the baseline arm"),
        },
        ["harness_duration_ms", "baseline_duration_ms", "harness_tokens", "baseline_tokens"],
    ),
    "ab_summary": _schema(
        "ab_summary",
        "AB Summary",
        "Emitted once, when the FSM executor finishes a run that collected any "
        "ab_comparison results (FEAT-1822), reporting the run-level aggregate.",
        {
            "harness_pass_rate": _number("Fraction of items where the harness arm passed (0-1)"),
            "baseline_pass_rate": _number(
                "Fraction of items where the baseline arm passed (0-1)"
            ),
            "delta": _number("Pass-rate difference (harness_pass_rate - baseline_pass_rate)"),
            "item_count": _int("Number of items included in the summary"),
        },
        ["harness_pass_rate", "baseline_pass_rate", "delta", "item_count"],
    ),
    "cost_ceiling_unknown": _schema(
        "cost_ceiling_unknown",
        "Cost Ceiling Unknown",
        "Emitted by the post-action per-state cost-ceiling check (BUG-3360) when "
        "a state with cost_ceiling configured cannot have its actual cost "
        "evaluated. Unknown cost is never treated as under budget.",
        {
            "state": _str("Name of the state whose cost could not be evaluated"),
            "reason": _str("'usage.jsonl unavailable' or 'unpriceable model'"),
        },
        ["state", "reason"],
    ),
    "cost_ceiling_warn": _schema(
        "cost_ceiling_warn",
        "Cost Ceiling Warn",
        "Emitted when a state's actual cost reaches or exceeds its configured "
        "cost_ceiling.cost_warn_at threshold. WARN-only — does not route or abort.",
        {
            "state": _str("Name of the state whose cost crossed the warn threshold"),
            "cost_usd": _number("State's actual cost in USD, rounded to 4 decimal places"),
            "cost_warn_at": _number("Configured cost_ceiling.cost_warn_at threshold"),
        },
        ["state", "cost_usd", "cost_warn_at"],
    ),
    "cost_ceiling_exceeded": _schema(
        "cost_ceiling_exceeded",
        "Cost Ceiling Exceeded",
        "Emitted when a state's actual cost exceeds its configured "
        "cost_ceiling.cost_ceiling_per_state hard limit; the executor finishes "
        "the run with terminated_by='cost_ceiling_exceeded' (BUG-3360).",
        {
            "state": _str("Name of the state whose cost exceeded the hard ceiling"),
            "cost_usd": _number("State's actual cost in USD, rounded to 4 decimal places"),
            "cost_ceiling_per_state": _number(
                "Configured hard-ceiling threshold that was exceeded"
            ),
            "action": {"type": "string", "enum": ["abort"], "description": "Always 'abort'"},
        },
        ["state", "cost_usd", "cost_ceiling_per_state", "action"],
    ),
    "evaluate": _schema(
        "evaluate",
        "Evaluate",
        "Emitted when an evaluator runs against action output.",
        {
            "type": _str("Evaluator type identifier"),
            "verdict": _str("Evaluator verdict (e.g. pass, fail, retry)"),
        },
        ["type", "verdict"],
    ),
    "retry_exhausted": _schema(
        "retry_exhausted",
        "Retry Exhausted",
        "Emitted when all retries for a state are exhausted.",
        {
            "state": _str("State name that exhausted retries"),
            "retries": _int("Number of retries attempted"),
            "next": _str("Next state the FSM transitions to"),
        },
        ["state", "retries", "next"],
    ),
    "infra_retry": _schema(
        "infra_retry",
        "Infra Retry",
        "Emitted on each in-place retry of an action that failed for infrastructure "
        "reasons rather than implementation ones — a headless host CLI exiting 143 "
        "after already emitting a stream-json result event (BUG-2731).",
        {
            "state": _str("State name that hit the infra-retry path"),
            "attempt": _int("Attempt number just made"),
            "backoff": _int("Flat backoff seconds before the retry"),
        },
        ["state", "attempt", "backoff"],
    ),
    "infra_retry_exhausted": _schema(
        "infra_retry_exhausted",
        "Infra Retry Exhausted",
        "Emitted once the infra-retry budget is spent and the executor falls through "
        "to normal verdict routing (BUG-2731).",
        {
            "state": _str("State name that exhausted infra retries"),
            "retries": _int("Total retries attempted before exhaustion"),
        },
        ["state", "retries"],
    ),
    "cycle_detected": _schema(
        "cycle_detected",
        "Cycle Detected",
        "Emitted when the same edge is traversed too many times, indicating a tight infinite loop.",
        {
            "edge": _str("Edge key (from_state->to_state) that triggered detection"),
            "from": _str("Source state of the cyclic edge"),
            "to": _str("Target state of the cyclic edge"),
            "count": _int("Number of times this edge was traversed"),
            "max": _int("Configured max_edge_revisits limit"),
        },
        ["edge", "from", "to", "count", "max"],
    ),
    "stall_detected": _schema(
        "stall_detected",
        "Stall Detected",
        'Emitted when the FSM stall detector observes `window` consecutive iterations with an identical (state, exit_code, verdict) triple. Either terminates the run (action="abort") or routes to a recovery state (action="route:<state>"). See FEAT-1637.',
        {
            "state": _str("State name whose triple repeated"),
            "exit_code": _int("Action exit code observed in the repeating triple"),
            "verdict": _str("Evaluator verdict observed in the repeating triple"),
            "consecutive": _int("Number of consecutive identical triples that fired the detector"),
            "action": _str('Either "abort" or "route:<target_state>"'),
        },
        ["state", "exit_code", "verdict", "consecutive", "action"],
    ),
    "rate_limit_exhausted": _schema(
        "rate_limit_exhausted",
        "Rate Limit Exhausted",
        "Emitted when the wall-clock rate-limit budget is spent across short + long tiers.",
        {
            "state": _str("State name that exhausted rate-limit retries"),
            "retries": _int("Total rate-limit retries attempted (short + long)"),
            "short_retries": _int("Retries attempted in the short-burst tier"),
            "long_retries": _int("Retries attempted in the long-wait tier"),
            "total_wait_seconds": _number(
                "Accumulated wall-clock seconds spent in rate-limit waits"
            ),
            "next": _nullable_str("Next state the FSM transitions to, or null if none"),
        },
        ["state", "retries"],
    ),
    "rate_limit_storm": _schema(
        "rate_limit_storm",
        "Rate Limit Storm",
        "Emitted when consecutive rate_limit_exhausted events reach the storm threshold.",
        {
            "state": _str("State name that triggered the storm threshold"),
            "count": _int("Consecutive rate_limit_exhausted count at emission time"),
        },
        ["state", "count"],
    ),
    "rate_limit_waiting": _schema(
        "rate_limit_waiting",
        "Rate Limit Waiting",
        "Heartbeat emitted every ~60s during a long-wait rate-limit sleep so UIs can show live progress.",
        {
            "state": _str("State name currently waiting on rate-limit recovery"),
            "elapsed_seconds": _number("Wall-clock seconds elapsed in the current tier's sleep"),
            "next_attempt_at": _number("Unix timestamp when this sleep is scheduled to end"),
            "total_waited_seconds": _number(
                "Accumulated wall-clock seconds across all rate-limit waits for this state"
            ),
            "budget_seconds": _int("Configured rate_limit_max_wait_seconds budget"),
            "tier": _str("Wait tier identifier (currently only 'long_wait')"),
        },
        ["state", "elapsed_seconds", "next_attempt_at"],
    ),
    "throttle_warn": _schema(
        "throttle_warn",
        "Throttle Warn",
        "Emitted when a state's tool-call count reaches warn_max within a single state visit.",
        {
            "state": _str("State name where throttle warning was triggered"),
            "count": _int("Current tool-call count at time of emission"),
            "normal_max": _int("Configured normal_max threshold for this state"),
            "warn_max": _int("Configured warn_max threshold for this state"),
            "hard_max": _int("Configured hard_max threshold for this state"),
        },
        ["state", "count", "warn_max", "hard_max"],
    ),
    "throttle_hard": _schema(
        "throttle_hard",
        "Throttle Hard",
        "Emitted when a state's tool-call count reaches hard_max, triggering transition to on_throttle_hard.",
        {
            "state": _str("State name where hard throttle was triggered"),
            "count": _int("Current tool-call count at time of emission"),
            "hard_max": _int("Configured hard_max threshold for this state"),
            "next": _str("Target state (on_throttle_hard or on_error, or null)"),
        },
        ["state", "count", "hard_max"],
    ),
    "throttle_stop": _schema(
        "throttle_stop",
        "Throttle Stop",
        "Emitted when a state's tool-call count exceeds hard_max with no on_throttle_hard target, causing a hard stop.",
        {
            "state": _str("State name where stop throttle was triggered"),
            "count": _int("Current tool-call count at time of emission"),
            "hard_max": _int("Configured hard_max threshold for this state"),
        },
        ["state", "count", "hard_max"],
    ),
    "prompt_size_warn": _schema(
        "prompt_size_warn",
        "Prompt Size Warn",
        "ENH-2486: emitted when a fully-interpolated action's char size reaches the "
        "per-loop prompt_size_guard.warn_chars threshold. WARN-only (does not route); "
        "surfaces loops that silently re-embed monotonically growing artifacts.",
        {
            "loop": _str("Loop name whose interpolated action exceeded the threshold"),
            "state": _str("State name where the oversized action was assembled"),
            "size": _int("Fully-interpolated action size in characters"),
            "threshold": _int("Configured prompt_size_guard.warn_chars threshold"),
            "est_tokens": _int("Estimated tokens (size // 4, the repo's 4-chars/token convention)"),
        },
        ["loop", "state", "size", "threshold"],
    ),
    # FEAT-1283: type=learning state dispatch events
    "learning_target_proven": _schema(
        "learning_target_proven",
        "Learning Target Proven",
        "Emitted when a target's learning-tests registry record is found with status='proven'. The state will advance to the next target (or to on_yes when all targets are proven).",
        {
            "state": _str("State name executing the learning dispatch"),
            "target": _str("Target identifier (e.g. 'Anthropic SDK streaming')"),
        },
        ["state", "target"],
    ),
    "learning_target_stale": _schema(
        "learning_target_stale",
        "Learning Target Stale",
        "Emitted when a target's registry record is missing or has status='stale', immediately before /ll:explore-api is invoked to (re-)prove it.",
        {
            "state": _str("State name executing the learning dispatch"),
            "target": _str("Target identifier"),
            "cause": _str("Why the record was treated as stale: 'missing' or 'stale'"),
        },
        ["state", "target", "cause"],
    ),
    "learning_explore_invoked": _schema(
        "learning_explore_invoked",
        "Learning Explore Invoked",
        "Emitted just before the learning state invokes /ll:explore-api for a target. Pairs with action_start/action_complete from the underlying skill invocation.",
        {
            "state": _str("State name executing the learning dispatch"),
            "target": _str("Target identifier being explored"),
            "attempt": _int("Attempt number, 1-based, capped by learning.max_retries"),
        },
        ["state", "target", "attempt"],
    ),
    "learning_target_refuted": _schema(
        "learning_target_refuted",
        "Learning Target Refuted",
        "Emitted when a target's registry record has status='refuted'. Routes to on_blocked / on_no.",
        {
            "state": _str("State name executing the learning dispatch"),
            "target": _str("Target identifier"),
        },
        ["state", "target"],
    ),
    "learning_complete": _schema(
        "learning_complete",
        "Learning Complete",
        "Emitted when every target in a learning state has been proven. The state transitions via on_yes.",
        {
            "state": _str("State name executing the learning dispatch"),
            "targets": {
                "type": "array",
                "description": "List of target identifiers that were all proven",
                "items": {"type": "string"},
            },
        },
        ["state", "targets"],
    ),
    "learning_blocked": _schema(
        "learning_blocked",
        "Learning Blocked",
        "Emitted when a learning state cannot advance: a target is refuted, or /ll:explore-api retries are exhausted without proving the target.",
        {
            "state": _str("State name executing the learning dispatch"),
            "target": _str("Target that blocked progress"),
            "reason": _str("'refuted' or 'retries_exhausted'"),
        },
        ["state", "target", "reason"],
    ),
    "handoff_detected": _schema(
        "handoff_detected",
        "Handoff Detected",
        "Emitted when a context-limit handoff is detected in a prompt action.",
        {
            "state": _str("State name where handoff was detected"),
            "iteration": _int("Iteration count at handoff"),
            "continuation": _str("Continuation prompt text"),
        },
        ["state", "iteration", "continuation"],
    ),
    "handoff_spawned": _schema(
        "handoff_spawned",
        "Handoff Spawned",
        "Emitted when a new process is spawned to continue after a handoff.",
        {
            "pid": _int("Process ID of the spawned continuation process"),
            "state": _str("State name the continuation will resume from"),
        },
        ["pid", "state"],
    ),
    "loop_complete": _schema(
        "loop_complete",
        "Loop Complete",
        "Emitted when an FSM loop finishes execution.",
        {
            "final_state": _str(
                "Name of the state at termination. Usually the last state entered; "
                "when terminated_by='timeout' this may be a state that was routed to "
                "but never entered — with one exception: if that pending state is a "
                "shell action, the executor flushes it (emits state_enter with "
                "flushed=true and runs its action) before honoring the timeout, so "
                "state_enter for final_state is always emitted before loop_complete "
                "(BUG-1226)."
            ),
            "iterations": _int("Total number of iterations executed"),
            "terminated_by": _str(
                "What caused loop termination. One of: 'terminal', 'max_steps', "
                "'max_iterations_reached', 'timeout', 'interrupted', 'user_stopped' "
                "(ENH-2522: ll-loop stop wrote user-stop.marker before signalling), "
                "'system_signal' (ENH-2522: POSIX process killed by signal N, no user "
                "marker — e.g. kernel OOM/SIGKILL), 'error', 'handoff', "
                "'cycle_detected', 'stall_detected', 'host_pressure_abort' "
                "(ENH-2452), 'host_budget_exceeded' (ENH-2453)."
            ),
            "failure_terminal": _bool(
                "True when terminated_by='terminal' and the reached terminal state is "
                "marked failure: true — the single source of truth for 'did this run "
                "fail?', keyed on the flag rather than the state's name (ENH-2814). "
                "Emitted unconditionally on every loop_complete; absent only in run "
                "archives predating ENH-2814."
            ),
            "error": _str(
                "Error message explaining why the loop crashed. "
                "Present only when terminated_by='error'."
            ),
        },
        ["final_state", "iterations", "terminated_by"],
    ),
    "max_steps_summary": _schema(
        "max_steps_summary",
        "Max Steps Summary",
        "Emitted when the step cap fires and on_max_steps is set; "
        "signals that a summary state will run before the loop terminates.",
        {
            "summary_state": _str("Name of the summary state the executor transitions to"),
            "iterations": _int("Step count at which the cap fired"),
        },
        ["summary_state", "iterations"],
    ),
    "max_iterations_reached_summary": _schema(
        "max_iterations_reached_summary",
        "Max Iterations Reached Summary",
        "Emitted when the full-pass cap fires and on_max_iterations is set; "
        "signals that a summary state will run before the loop terminates.",
        {
            "summary_state": _str("Name of the summary state the executor transitions to"),
            "iteration_count": _int("Full-pass count at which the cap fired"),
        },
        ["summary_state", "iteration_count"],
    ),
    # FSM Persistence (1 type)
    "loop_resume": _schema(
        "loop_resume",
        "Loop Resume",
        "Emitted when a previously interrupted loop resumes from a persisted checkpoint.",
        {
            "loop": _str("Loop name"),
            "from_state": _str("State the loop resumes from"),
            "iteration": _int("Iteration count at resume"),
            "from_handoff": _bool("True if resuming from a context-limit handoff"),
            "continuation_prompt": _nullable_str(
                "Continuation prompt text (only present when from_handoff is true)"
            ),
        },
        ["loop", "from_state", "iteration"],
    ),
    # StateManager (2 types)
    "state.issue_completed": _schema(
        "state.issue_completed",
        "State: Issue Completed",
        "Emitted by StateManager when an issue transitions to completed status.",
        {
            "issue_id": _str("Issue identifier"),
            "status": {"type": "string", "enum": ["completed"], "description": "Completion status"},
        },
        ["issue_id", "status"],
    ),
    "state.issue_failed": _schema(
        "state.issue_failed",
        "State: Issue Failed",
        "Emitted by StateManager when an issue transitions to failed status.",
        {
            "issue_id": _str("Issue identifier"),
            "reason": _str("Failure reason description"),
            "status": {"type": "string", "enum": ["failed"], "description": "Failure status"},
        },
        ["issue_id", "reason", "status"],
    ),
    # Issue Lifecycle (6 types)
    "issue.failure_captured": _schema(
        "issue.failure_captured",
        "Issue: Failure Captured",
        "Emitted when an issue failure is captured and persisted as a bug report.",
        {
            "issue_id": _str("Issue identifier"),
            "file_path": _str("Path to the issue file"),
            "parent_issue_id": _str("Identifier of the parent issue that failed"),
        },
        ["issue_id", "file_path", "parent_issue_id"],
    ),
    "issue.closed": _schema(
        "issue.closed",
        "Issue: Closed",
        "Emitted when an issue is closed.",
        {
            "issue_id": _str("Issue identifier"),
            "file_path": _str("Path to the issue file"),
            "close_reason": _str("Reason the issue was closed"),
        },
        ["issue_id", "file_path", "close_reason"],
    ),
    "issue.completed": _schema(
        "issue.completed",
        "Issue: Completed",
        "Emitted when an issue is successfully completed.",
        {
            "issue_id": _str("Issue identifier"),
            "file_path": _str("Path to the completed issue file"),
        },
        ["issue_id", "file_path"],
    ),
    "issue.deferred": _schema(
        "issue.deferred",
        "Issue: Deferred",
        "Emitted when an issue is deferred (parked for later).",
        {
            "issue_id": _str("Issue identifier"),
            "file_path": _str("Path to the deferred issue file"),
            "reason": _str("Reason the issue was deferred"),
        },
        ["issue_id", "file_path", "reason"],
    ),
    "issue.skipped": _schema(
        "issue.skipped",
        "Issue: Skipped",
        "Emitted when an issue is skipped during automated processing.",
        {
            "issue_id": _str("Issue identifier"),
            "file_path": _str("Path to the issue file"),
            "reason": _str("Reason the issue was skipped"),
        },
        ["issue_id", "file_path", "reason"],
    ),
    "issue.started": _schema(
        "issue.started",
        "Issue: Started",
        "Emitted when a deferred issue is undeferred and returned to active processing.",
        {
            "issue_id": _str("Issue identifier"),
            "file_path": _str("Path to the issue file"),
            "reason": _str("Reason the issue was restarted"),
        },
        ["issue_id", "file_path", "reason"],
    ),
    # Parallel Orchestrator (8 types)
    "parallel.worker_completed": _schema(
        "parallel.worker_completed",
        "Parallel: Worker Completed",
        "Emitted by the parallel orchestrator when a worker finishes processing an issue.",
        {
            "issue_id": _str("Issue identifier processed by the worker"),
            "worker_name": _str("Worker name or identifier"),
            "status": _str("Completion status (e.g. completed, failed, deferred)"),
            "duration_seconds": {"type": "number", "description": "Wall-clock time in seconds"},
        },
        ["issue_id", "worker_name", "status", "duration_seconds", "run_id"],
    ),
    "parallel.epic_branch_stale": _schema(
        "parallel.epic_branch_stale",
        "Parallel: EPIC Branch Stale",
        "Emitted by WorkerPool when a reused EPIC integration branch is found behind its "
        "resolved fork base and warned/merged/conflict-degraded (ENH-3302).",
        {
            "branch": _str("EPIC integration branch name"),
            "base": _str("Resolved fork base the branch was measured/merged against"),
            "commits_behind": {
                "type": "integer",
                "description": "git rev-list --count <branch>..<base> — commits base has that branch lacks",
            },
            "mode": _str("Configured parallel.epic_branches.refresh_on_reuse value"),
            "action": _str("warned | merged | merge_conflict"),
        },
        ["branch", "base", "commits_behind", "mode", "action", "run_id"],
    ),
    "parallel.worker_started": _schema(
        "parallel.worker_started",
        "Parallel: Worker Started",
        "Emitted by WorkerPool._process_issue immediately after worktree creation, when "
        "a worker begins processing an issue (ENH-3346).",
        {
            "worker_id": _str(
                "Worker identifier, aliased to issue_id (stable for the worker's lifetime)"
            ),
            "issue_id": _str("Issue identifier this worker is processing"),
            "worktree_path": _str("Filesystem path to the worker's git worktree"),
            "branch": _str("Git branch created for this worker"),
        },
        ["worker_id", "issue_id", "worktree_path", "branch", "run_id"],
    ),
    "parallel.worker_blocked": _schema(
        "parallel.worker_blocked",
        "Parallel: Worker Blocked",
        "Emitted by ParallelOrchestrator._process_parallel when an issue is deferred on "
        "an overlap conflict, before any worktree exists for it (ENH-3346).",
        {
            "worker_id": _str("Worker identifier, aliased to issue_id"),
            "issue_id": _str("Issue identifier that was deferred"),
            "reason": _str("Why the issue was blocked (currently only 'overlap')"),
        },
        ["worker_id", "issue_id", "reason", "run_id"],
    ),
    "parallel.worker_unblocked": _schema(
        "parallel.worker_unblocked",
        "Parallel: Worker Unblocked",
        "Emitted by ParallelOrchestrator._requeue_deferred_issues when a previously "
        "deferred issue is successfully re-queued (ENH-3346).",
        {
            "worker_id": _str("Worker identifier, aliased to issue_id"),
            "issue_id": _str("Issue identifier that was re-queued"),
        },
        ["worker_id", "issue_id", "run_id"],
    ),
    "parallel.merge_started": _schema(
        "parallel.merge_started",
        "Parallel: Merge Started",
        "Emitted at the top of MergeCoordinator._process_merge, before the circuit-"
        "breaker check, gated on retry_count == 0 (ENH-3346).",
        {
            "worker_id": _str("Worker identifier, aliased to issue_id"),
            "issue_id": _str("Issue identifier whose merge is starting"),
            "branch": _str("Worker branch being merged"),
        },
        ["worker_id", "issue_id", "branch", "run_id"],
    ),
    "parallel.merge_completed": _schema(
        "parallel.merge_completed",
        "Parallel: Merge Completed",
        "Emitted by MergeCoordinator._finalize_merge (outcome=merged) or "
        "_handle_failure (outcome=failed); fires exactly once per merge request "
        "(ENH-3346).",
        {
            "worker_id": _str("Worker identifier, aliased to issue_id"),
            "issue_id": _str("Issue identifier whose merge finished"),
            "outcome": _str("merged | failed"),
            "error": _nullable_str("Failure detail; null when outcome == 'merged'"),
        },
        ["worker_id", "issue_id", "outcome", "error", "run_id"],
    ),
    "parallel.queue_changed": _schema(
        "parallel.queue_changed",
        "Parallel: Queue Changed",
        "Emitted from inside IssuePriorityQueue's mutators after every counter-"
        "changing operation; consumers apply last-writer-wins by seq, not arrival "
        "order (ENH-3346).",
        {
            "seq": {
                "type": "integer",
                "description": "Monotonic counter incremented under the queue's lock alongside "
                "the counter snapshot; emit() runs after the lock is released, so consumers "
                "apply last-writer-wins by seq rather than arrival order",
            },
            "pending": _int("Issues waiting in the queue (qsize())"),
            "active": _int("Issues currently in progress"),
            "completed": _int("Issues completed successfully"),
            "failed": _int("Issues that failed"),
            "skipped": _int("Issues skipped"),
        },
        ["seq", "pending", "active", "completed", "failed", "skipped", "run_id"],
    ),
}


def event_type_to_filename(event_type: str) -> str:
    """Convert event type to safe filename (replace '.' with '_')."""
    return event_type.replace(".", "_") + ".json"


def generate_schemas(output_dir: Path) -> list[Path]:
    """Generate JSON Schema files for all 23 LLEvent types.

    Args:
        output_dir: Directory to write schema files into. Created if it doesn't exist.

    Returns:
        List of paths to generated files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for event_type, schema in SCHEMA_DEFINITIONS.items():
        filename = event_type_to_filename(event_type)
        path = output_dir / filename
        path.write_text(json.dumps(schema, indent=2) + "\n")
        generated.append(path)
    return generated


if __name__ == "__main__":
    import sys

    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/reference/schemas")
    paths = generate_schemas(output)
    print(f"Generated {len(paths)} schemas in {output}/")
