"""DES variant registry — see ``little_loops.observability`` docstring.

Every event type emitted to ``.ll/history.db`` (Channel A direct writers + Channel B
EventBus emits) is registered here as a frozen dataclass with a ``Literal[...]``
discriminator field. The audit walker (``audit.py``) reads the ``type`` field default
from each variant to build the allow-list of known event-type strings, then walks the
source tree to verify every emit site maps to a known variant.

Pattern reference:
    - ``scripts/little_loops/fsm/schema.py:63-78`` (EvaluateConfig.type: Literal[...])
    - ``scripts/little_loops/host_runner.py:101-104`` (@dataclass(frozen=True) convention)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal


@dataclass(frozen=True)
class DESVariant:
    """Base frozen dataclass for every registered DES variant.

    Per ``scripts/little_loops/host_runner.py:101-104`` — ``@dataclass(frozen=True)`` is
    the established value-object convention for objects that cross audit/registry
    boundaries. Concrete subclasses set ``type`` to a ``Literal[...]`` matching the
    discriminator string the audit walker captures from emit sites.
    """

    type: str  # Concrete Literal lives on each subclass.


# ---------------------------------------------------------------------------
# Channel B: EventBus-emitted events reaching .ll/history.db
# ---------------------------------------------------------------------------
#
# Every variant below corresponds to an ``self._emit(...)`` or ``event_bus.emit(...)``
# call site enumerated by the codebase inventory (see ENH-2475 issue body). Names match
# the wire-format discriminator string so the audit walker can compare directly.
# Variants in the ``loop_events`` SQLite table route through ``_LOOP_EVENT_TYPES``
# (session_store.py:133-145); ``issue.*`` events route through the ``_ISSUE_TRANSITION_MAP``
# (session_store.py:1296-1303). All other events are visible to non-SQLite transports
# (JSONL, OTel, webhook) and are persisted to ``usage.jsonl`` / ``messages.jsonl`` per-run.


@dataclass(frozen=True)
class LoopStartVariant(DESVariant):
    """FSMExecutor._emit('loop_start') — FSM loop begins execution."""

    type: Literal["loop_start"] = "loop_start"
    loop: str = ""


@dataclass(frozen=True)
class StateEnterVariant(DESVariant):
    """FSMExecutor._emit('state_enter') — FSM enters a state (also flushed variant)."""

    type: Literal["state_enter"] = "state_enter"
    state: str = ""
    iteration: int = 0


@dataclass(frozen=True)
class RouteVariant(DESVariant):
    """FSMExecutor._emit('route') — FSM routes from one state to another."""

    type: Literal["route"] = "route"
    from_state: str = ""
    to: str = ""
    reason: str = ""


@dataclass(frozen=True)
class RetryExhaustedVariant(DESVariant):
    """FSMExecutor._emit('retry_exhausted') — retry budget exhausted for a state."""

    type: Literal["retry_exhausted"] = "retry_exhausted"
    state: str = ""
    retries: int = 0


@dataclass(frozen=True)
class CycleDetectedVariant(DESVariant):
    """FSMExecutor._emit('cycle_detected') — FSM detects a repeated edge."""

    type: Literal["cycle_detected"] = "cycle_detected"
    from_state: str = ""
    to: str = ""
    count: int = 0


@dataclass(frozen=True)
class MaxStepsSummaryVariant(DESVariant):
    """FSMExecutor._emit('max_steps_summary') — loop hit the max-steps bound."""

    type: Literal["max_steps_summary"] = "max_steps_summary"


@dataclass(frozen=True)
class MaxIterationsReachedSummaryVariant(DESVariant):
    """FSMExecutor._emit('max_iterations_reached_summary') — loop hit iteration cap."""

    type: Literal["max_iterations_reached_summary"] = "max_iterations_reached_summary"


@dataclass(frozen=True)
class LoopResumeVariant(DESVariant):
    """PersistentExecutor._handle_event emits 'loop_resume' on FSM resume."""

    type: Literal["loop_resume"] = "loop_resume"


@dataclass(frozen=True)
class LoopCompleteVariant(DESVariant):
    """FSMExecutor._emit('loop_complete') — FSM loop terminates."""

    type: Literal["loop_complete"] = "loop_complete"
    final_state: str = ""
    iterations: int = 0


@dataclass(frozen=True)
class HostBudgetExceededVariant(DESVariant):
    """FSMExecutor._emit('host_budget_exceeded') — host context budget exceeded."""

    type: Literal["host_budget_exceeded"] = "host_budget_exceeded"


@dataclass(frozen=True)
class LearningBlockedVariant(DESVariant):
    """FSMExecutor._emit('learning_blocked') — learning target blocked."""

    type: Literal["learning_blocked"] = "learning_blocked"


@dataclass(frozen=True)
class LearningTargetStaleVariant(DESVariant):
    """FSMExecutor._emit('learning_target_stale') — learning target is stale."""

    type: Literal["learning_target_stale"] = "learning_target_stale"


@dataclass(frozen=True)
class LearningExploreInvokedVariant(DESVariant):
    """FSMExecutor._emit('learning_explore_invoked') — learning exploration started."""

    type: Literal["learning_explore_invoked"] = "learning_explore_invoked"


@dataclass(frozen=True)
class LearningTargetRefutedVariant(DESVariant):
    """FSMExecutor._emit('learning_target_refuted') — learning target refuted."""

    type: Literal["learning_target_refuted"] = "learning_target_refuted"


@dataclass(frozen=True)
class LearningTargetProvenVariant(DESVariant):
    """FSMExecutor._emit('learning_target_proven') — learning target proven."""

    type: Literal["learning_target_proven"] = "learning_target_proven"


@dataclass(frozen=True)
class LearningCompleteVariant(DESVariant):
    """FSMExecutor._emit('learning_complete') — all learning targets resolved."""

    type: Literal["learning_complete"] = "learning_complete"


@dataclass(frozen=True)
class ThrottleWarnVariant(DESVariant):
    """FSMExecutor._emit('throttle_warn') — host throughput dropped below warn threshold."""

    type: Literal["throttle_warn"] = "throttle_warn"


@dataclass(frozen=True)
class ThrottleHardVariant(DESVariant):
    """FSMExecutor._emit('throttle_hard') — host throughput at hard throttle threshold."""

    type: Literal["throttle_hard"] = "throttle_hard"


@dataclass(frozen=True)
class ThrottleStopVariant(DESVariant):
    """FSMExecutor._emit('throttle_stop') — host throughput at stop threshold."""

    type: Literal["throttle_stop"] = "throttle_stop"


@dataclass(frozen=True)
class StallDetectedVariant(DESVariant):
    """FSMExecutor._emit('stall_detected') — evaluator stalled for max_stall iterations."""

    type: Literal["stall_detected"] = "stall_detected"


@dataclass(frozen=True)
class PromptSizeWarnVariant(DESVariant):
    """FSMExecutor._emit('prompt_size_warn') — prompt payload exceeded threshold."""

    type: Literal["prompt_size_warn"] = "prompt_size_warn"


@dataclass(frozen=True)
class ActionStartVariant(DESVariant):
    """FSMExecutor._emit('action_start') — action invocation started."""

    type: Literal["action_start"] = "action_start"
    action: str = ""


@dataclass(frozen=True)
class ActionOutputVariant(DESVariant):
    """FSMExecutor._emit('action_output') — per-line stdout/stderr from action."""

    type: Literal["action_output"] = "action_output"


@dataclass(frozen=True)
class ActionCompleteVariant(DESVariant):
    """FSMExecutor._emit('action_complete') — action returned (carries TokenUsage)."""

    type: Literal["action_complete"] = "action_complete"
    exit_code: int = 0
    duration_ms: int = 0


@dataclass(frozen=True)
class HostSubprocRssVariant(DESVariant):
    """FSMExecutor._emit('host_subproc_rss') — host subprocess RSS measured."""

    type: Literal["host_subproc_rss"] = "host_subproc_rss"


@dataclass(frozen=True)
class MessagesAppendVariant(DESVariant):
    """FSMExecutor._emit('messages_append') — assistant message appended to run log."""

    type: Literal["messages_append"] = "messages_append"


@dataclass(frozen=True)
class EvaluateVariant(DESVariant):
    """FSMExecutor._emit('evaluate') — action result evaluated by an evaluator."""

    type: Literal["evaluate"] = "evaluate"
    type_eval: str = ""
    verdict: str = ""


@dataclass(frozen=True)
class BaselineCompleteVariant(DESVariant):
    """FSMExecutor._emit('baseline_complete') — A/B harness baseline run finished."""

    type: Literal["baseline_complete"] = "baseline_complete"


@dataclass(frozen=True)
class AbComparisonVariant(DESVariant):
    """FSMExecutor._emit('ab_comparison') — one A/B comparison item scored."""

    type: Literal["ab_comparison"] = "ab_comparison"


@dataclass(frozen=True)
class ActionErrorVariant(DESVariant):
    """FSMExecutor._emit('action_error') — action raised an exception."""

    type: Literal["action_error"] = "action_error"
    state: str = ""
    error: str = ""


@dataclass(frozen=True)
class RateLimitWaitingVariant(DESVariant):
    """FSMExecutor._emit('rate_limit_waiting') — heartbeat during rate-limit backoff."""

    type: Literal["rate_limit_waiting"] = "rate_limit_waiting"


@dataclass(frozen=True)
class HostPressureRelievedVariant(DESVariant):
    """FSMExecutor._emit('host_pressure_relieved') — host pressure dropped below threshold."""

    type: Literal["host_pressure_relieved"] = "host_pressure_relieved"


@dataclass(frozen=True)
class HostCooldownVariant(DESVariant):
    """FSMExecutor._emit('host_cooldown') — host entered cooldown."""

    type: Literal["host_cooldown"] = "host_cooldown"


@dataclass(frozen=True)
class HostPressureVariant(DESVariant):
    """FSMExecutor._emit('host_pressure') — host pressure exceeded threshold."""

    type: Literal["host_pressure"] = "host_pressure"


@dataclass(frozen=True)
class HostPressureAbortVariant(DESVariant):
    """FSMExecutor._emit('host_pressure_abort') — host pressure forced abort."""

    type: Literal["host_pressure_abort"] = "host_pressure_abort"


@dataclass(frozen=True)
class RateLimitExhaustedVariant(DESVariant):
    """FSMExecutor._emit('rate_limit_exhausted') — rate-limit retries exhausted."""

    type: Literal["rate_limit_exhausted"] = "rate_limit_exhausted"


@dataclass(frozen=True)
class RateLimitStormVariant(DESVariant):
    """FSMExecutor._emit('rate_limit_storm') — sustained rate-limit pattern detected."""

    type: Literal["rate_limit_storm"] = "rate_limit_storm"


@dataclass(frozen=True)
class ApiErrorExhaustedVariant(DESVariant):
    """FSMExecutor._emit('api_error_exhausted') — API error retries exhausted."""

    type: Literal["api_error_exhausted"] = "api_error_exhausted"


@dataclass(frozen=True)
class ApiErrorRetryVariant(DESVariant):
    """FSMExecutor._emit('api_error_retry') — API error triggered a retry."""

    type: Literal["api_error_retry"] = "api_error_retry"


@dataclass(frozen=True)
class AbSummaryVariant(DESVariant):
    """FSMExecutor._emit('ab_summary') — A/B comparison summary finalized."""

    type: Literal["ab_summary"] = "ab_summary"


@dataclass(frozen=True)
class HandoffDetectedVariant(DESVariant):
    """FSMExecutor._emit('handoff_detected') — continuation handoff signal received."""

    type: Literal["handoff_detected"] = "handoff_detected"


@dataclass(frozen=True)
class HandoffSpawnedVariant(DESVariant):
    """FSMExecutor._emit('handoff_spawned') — handoff spawned a detached session."""

    type: Literal["handoff_spawned"] = "handoff_spawned"


@dataclass(frozen=True)
class StateIssueCompletedVariant(DESVariant):
    """StateManager._emit('state.issue_completed') — issue lifecycle completed (state bus)."""

    type: Literal["state.issue_completed"] = "state.issue_completed"


@dataclass(frozen=True)
class StateIssueFailedVariant(DESVariant):
    """StateManager._emit('state.issue_failed') — issue lifecycle failed (state bus)."""

    type: Literal["state.issue_failed"] = "state.issue_failed"


@dataclass(frozen=True)
class IssueFailureCapturedVariant(DESVariant):
    """issue_lifecycle.emit('issue.failure_captured') — child issue captured from failure."""

    type: Literal["issue.failure_captured"] = "issue.failure_captured"


@dataclass(frozen=True)
class IssueClosedVariant(DESVariant):
    """issue_lifecycle.emit('issue.closed') — issue closed."""

    type: Literal["issue.closed"] = "issue.closed"


@dataclass(frozen=True)
class IssueCompletedVariant(DESVariant):
    """issue_lifecycle.emit('issue.completed') — issue marked done."""

    type: Literal["issue.completed"] = "issue.completed"


@dataclass(frozen=True)
class IssueDeferredVariant(DESVariant):
    """issue_lifecycle.emit('issue.deferred') — issue parked."""

    type: Literal["issue.deferred"] = "issue.deferred"


@dataclass(frozen=True)
class IssueSkippedVariant(DESVariant):
    """issue_lifecycle.emit('issue.skipped') — issue skipped."""

    type: Literal["issue.skipped"] = "issue.skipped"


@dataclass(frozen=True)
class IssueStartedVariant(DESVariant):
    """issue_lifecycle.emit('issue.started') — work on issue started."""

    type: Literal["issue.started"] = "issue.started"


@dataclass(frozen=True)
class ParallelWorkerCompletedVariant(DESVariant):
    """parallel/orchestrator emits 'parallel.worker_completed' on worker finish."""

    type: Literal["parallel.worker_completed"] = "parallel.worker_completed"
    issue_id: str = ""
    status: str = ""


# ---------------------------------------------------------------------------
# Channel A: Direct writers to .ll/history.db (target-table representation)
# ---------------------------------------------------------------------------
#
# These variants do not appear as emit-site strings (Channel A bypasses EventBus and
# calls INSERT directly). They are registered so that the registry documents every
# ``.ll/history.db`` write target — the F5 audit's documentation surface requires
# the full table map, not just the EventBus-visible subset.


@dataclass(frozen=True)
class ToolEventVariant(DESVariant):
    """Direct INSERT INTO ``tool_events`` (post_tool_use.py + backfill)."""

    type: Literal["tool_event"] = "tool_event"


@dataclass(frozen=True)
class FileEventVariant(DESVariant):
    """``write_file_event`` writes to ``file_events`` (post_tool_use hook)."""

    type: Literal["file_event"] = "file_event"
    op: str = ""


@dataclass(frozen=True)
class UserCorrectionVariant(DESVariant):
    """``record_correction`` writes to ``user_corrections``."""

    type: Literal["user_correction"] = "user_correction"
    source: str = ""


@dataclass(frozen=True)
class SkillEventVariant(DESVariant):
    """``record_skill_event`` / ``skill_event_context`` write to ``skill_events``."""

    type: Literal["skill_event"] = "skill_event"


@dataclass(frozen=True)
class IssueSnapshotVariant(DESVariant):
    """``record_issue_snapshot`` writes to ``issue_snapshots`` (CLI + lifecycle side-effect)."""

    type: Literal["issue_snapshot"] = "issue_snapshot"
    transition: str = ""


@dataclass(frozen=True)
class CommitEventVariant(DESVariant):
    """``record_commit_event`` writes to ``commit_events`` (post_commit + backfill)."""

    type: Literal["commit_event"] = "commit_event"


@dataclass(frozen=True)
class TestRunEventVariant(DESVariant):
    """``record_test_run_event`` writes to ``test_run_events`` (pytest plugin)."""

    type: Literal["test_run_event"] = "test_run_event"


@dataclass(frozen=True)
class CliEventVariant(DESVariant):
    """``cli_event_context`` writes to ``cli_events`` (every CLI entry point)."""

    type: Literal["cli_event"] = "cli_event"
    binary: str = ""


@dataclass(frozen=True)
class LoopEventBackfillVariant(DESVariant):
    """``_backfill_loop_events`` writes historical ``loop_events`` rows."""

    type: Literal["loop_event_backfill"] = "loop_event_backfill"


@dataclass(frozen=True)
class MessageEventVariant(DESVariant):
    """``_backfill_messages`` writes historical ``message_events`` rows."""

    type: Literal["message_event"] = "message_event"


@dataclass(frozen=True)
class AssistantMessageVariant(DESVariant):
    """``_backfill_assistant_messages`` writes historical ``assistant_messages`` rows."""

    type: Literal["assistant_message"] = "assistant_message"


@dataclass(frozen=True)
class IssueEventVariant(DESVariant):
    """``_backfill_issues`` writes historical ``issue_events`` rows."""

    type: Literal["issue_event"] = "issue_event"


@dataclass(frozen=True)
class IssueEventLifecycleVariant(DESVariant):
    """EventBus-emitted ``issue.*`` events route to ``issue_events`` (Channel B)."""

    type: Literal["issue_event_lifecycle"] = "issue_event_lifecycle"


@dataclass(frozen=True)
class CorrectionRetirementVariant(DESVariant):
    """``record_retirement`` writes to ``correction_retirements``."""

    type: Literal["correction_retirement"] = "correction_retirement"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


DES_VARIANTS: Final[tuple[type[DESVariant], ...]] = (
    # --- Channel B: EventBus-emitted ---
    LoopStartVariant,
    StateEnterVariant,
    RouteVariant,
    RetryExhaustedVariant,
    CycleDetectedVariant,
    MaxStepsSummaryVariant,
    MaxIterationsReachedSummaryVariant,
    LoopResumeVariant,
    LoopCompleteVariant,
    HostBudgetExceededVariant,
    LearningBlockedVariant,
    LearningTargetStaleVariant,
    LearningExploreInvokedVariant,
    LearningTargetRefutedVariant,
    LearningTargetProvenVariant,
    LearningCompleteVariant,
    ThrottleWarnVariant,
    ThrottleHardVariant,
    ThrottleStopVariant,
    StallDetectedVariant,
    PromptSizeWarnVariant,
    ActionStartVariant,
    ActionOutputVariant,
    ActionCompleteVariant,
    HostSubprocRssVariant,
    MessagesAppendVariant,
    EvaluateVariant,
    BaselineCompleteVariant,
    AbComparisonVariant,
    ActionErrorVariant,
    RateLimitWaitingVariant,
    HostPressureRelievedVariant,
    HostCooldownVariant,
    HostPressureVariant,
    HostPressureAbortVariant,
    RateLimitExhaustedVariant,
    RateLimitStormVariant,
    ApiErrorExhaustedVariant,
    ApiErrorRetryVariant,
    AbSummaryVariant,
    HandoffDetectedVariant,
    HandoffSpawnedVariant,
    StateIssueCompletedVariant,
    StateIssueFailedVariant,
    IssueFailureCapturedVariant,
    IssueClosedVariant,
    IssueCompletedVariant,
    IssueDeferredVariant,
    IssueSkippedVariant,
    IssueStartedVariant,
    ParallelWorkerCompletedVariant,
    # --- Channel A: Direct writers ---
    ToolEventVariant,
    FileEventVariant,
    UserCorrectionVariant,
    SkillEventVariant,
    IssueSnapshotVariant,
    CommitEventVariant,
    TestRunEventVariant,
    CliEventVariant,
    LoopEventBackfillVariant,
    MessageEventVariant,
    AssistantMessageVariant,
    IssueEventVariant,
    IssueEventLifecycleVariant,
    CorrectionRetirementVariant,
)


def _extract_type_defaults() -> frozenset[str]:
    """Collect the discriminator ``type`` default value from every variant in DES_VARIANTS."""
    out: set[str] = set()
    for variant in DES_VARIANTS:
        # Each variant declares ``type: Literal[...] = "<discriminator>"``; the
        # default is the discriminator string. Reading the field default keeps the
        # set in lock-step with the variant definitions without a parallel registry.
        type_field = variant.__dataclass_fields__.get("type")
        if type_field is None:
            continue
        default = type_field.default
        if isinstance(default, str):
            out.add(default)
    return frozenset(out)


DES_VARIANT_TYPES: Final[frozenset[str]] = _extract_type_defaults()
"""Frozenset of every registered discriminator string — the audit walker's allow-list."""
