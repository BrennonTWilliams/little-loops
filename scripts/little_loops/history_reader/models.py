"""Dataclasses for history_reader query results (ENH-2775 split from the
former flat ``history_reader.py``).

Every read-only query function across the package returns instances of these
dataclasses (or plain ``list[dict]``/``dict`` for ad-hoc aggregations). This
module holds no query logic and depends on nothing else in the package.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

__all__ = [
    "CommitEvent",
    "ContextPressureEvent",
    "FileEvent",
    "GrepResult",
    "IssueEvent",
    "LearningTestEvent",
    "LifecycleEvent",
    "LoopRun",
    "OrchestrationRun",
    "ProjectDigest",
    "PromptOptEvent",
    "RunEvent",
    "SearchResult",
    "SectionProvider",
    "SessionRef",
    "SkillEvent",
    "SubagentRun",
    "SummaryNode",
    "UsageEvent",
    "UserCorrection",
]


@dataclass
class UserCorrection:
    ts: str
    session_id: str | None
    content: str
    source: str | None


@dataclass
class FileEvent:
    ts: str
    session_id: str | None
    path: str | None
    op: str | None
    issue_id: str | None
    git_sha: str | None


@dataclass
class SearchResult:
    content: str
    kind: str
    ref: str
    anchor: str
    ts: str
    score: float


@dataclass
class IssueEvent:
    ts: str
    issue_id: str | None
    transition: str | None
    discovered_by: str | None
    issue_type: str | None
    priority: str | None
    session_id: str | None = None


@dataclass
class SkillEvent:
    """A skill_events row including completion columns (ENH-2460).

    ``exit_code``/``success``/``duration_ms`` are ``None`` for rows recorded
    at dispatch time only (the user_prompt_submit hook) or written before the
    v15 migration.
    """

    ts: str
    session_id: str | None
    skill_name: str | None
    args: str | None
    exit_code: int | None = None
    success: int | None = None
    duration_ms: int | None = None


@dataclass
class CommitEvent:
    """A commit_events row (ENH-2458)."""

    ts: str
    commit_sha: str
    parent_sha: str | None
    message: str
    author: str | None
    branch: str | None
    issue_id: str | None
    files_json: str | None


@dataclass
class PromptOptEvent:
    """A prompt_opt_events row (ENH-2498)."""

    ts: str
    session_id: str | None
    mode: str | None
    offered: int | None
    bypass_reason: str | None
    raw_len: int | None
    optimized_len: int | None
    optimized_text: str | None
    accepted: int | None


@dataclass
class RunEvent:
    """A test_run_events row (ENH-2459)."""

    ts: str
    ended_at: str | None
    total: int | None
    passed: int | None
    failed: int | None
    errored: int | None
    skipped: int | None
    duration_s: float | None
    failing_names_json: str | None
    env_label: str | None
    head_sha: str | None
    branch: str | None
    command: str | None

    @property
    def pass_rate(self) -> float | None:
        """Fraction of collected tests that passed, or None when total is 0/unknown."""
        if not self.total:
            return None
        return (self.passed or 0) / self.total


@dataclass
class OrchestrationRun:
    """A per-issue orchestration outcome from ll-auto/parallel/sprint (ENH-2492)."""

    run_id: str
    driver: str
    issue_id: str
    status: str
    failure_reason: str | None
    duration_s: float | None
    wave: str | None
    pr_url: str | None
    started_at: str | None
    ended_at: str | None
    head_sha: str | None
    branch: str | None
    base_sha: str | None = None
    base_dirty: int | None = None


@dataclass
class LoopRun:
    """A ``loop_runs`` row — one summary per completed FSM loop run (ENH-2463)."""

    run_id: str
    loop_name: str
    started_at: str | None
    ended_at: str | None
    final_state: str | None
    iterations: int | None
    terminated_by: str | None
    error: str | None
    evaluator_score: float | None
    diagnostics_path: str | None
    head_sha: str | None
    branch: str | None
    failure_terminal: int | None = None


@dataclass
class LearningTestEvent:
    """A ``learning_test_events`` row — mirror of a Learning Test Registry
    record (``.ll/learning-tests/<slug>.md``, the ``LearnTestRecord`` dataclass
    in ``little_loops.learning_tests``). Not to be confused with that
    registry-file dataclass; this is the DB-side mirror row (ENH-2466)."""

    ts: str
    record_id: str
    target: str | None
    status: str | None
    assertions_json: str | None
    date: str | None
    raw_output_path: str | None


@dataclass
class LifecycleEvent:
    """A ``session_lifecycle_events`` row — a session-lifecycle / handoff
    transition (``handoff_needed``, ``compaction``, ``stale_ref_sweep``, plus
    ENH-2509's ``worktree_*`` discriminators sharing this table) (ENH-2495)."""

    id: int
    ts: str
    session_id: str | None
    event: str
    detail: dict | None
    head_sha: str | None
    branch: str | None


@dataclass
class SubagentRun:
    """A ``subagent_runs`` row — one Task/Agent spawn (ENH-2505).

    ``agent_id`` is spawn-local (scoped to ``parent_session_id``, not a
    ``sessions.session_id``); a subagent's transcript is a nested file
    (``<parent-transcript-dir>/subagents/agent-<id>.jsonl``), not a top-level
    session row.
    """

    ts: str
    parent_session_id: str | None
    agent_id: str | None
    agent_type: str | None
    agent_transcript_path: str | None
    started_at: str | None
    ended_at: str | None
    status: str | None


@dataclass
class UsageEvent:
    """A ``usage_events`` row — real LLM token counts per assistant turn (ENH-2461).

    Column names mirror the Anthropic API usage fields. ``state`` is always
    ``None`` on parser-written rows (the transcript stream carries no FSM-state
    boundary); ``cost_usd`` is ``None`` when the model is not in the pricing
    table.
    """

    ts: str
    session_id: str | None
    model: str | None
    state: str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None
    cost_usd: float | None


@dataclass
class ContextPressureEvent:
    """A ``context_pressure_events`` row — one context-window pressure sample (ENH-2507).

    Written by ``context-monitor.sh`` on every sampled ``PostToolUse``.
    ``threshold_crossed``/``crossed_level`` are populated only on the row
    where a new level (``"50"``/``"75"``/``"80"``/``"90"``/``"100"``) was
    first reached; other rows carry ``0``/``None``.
    """

    ts: str
    session_id: str | None
    used_pct: float | None
    used_tokens_est: int | None
    threshold_crossed: int | None
    crossed_level: str | None
    head_sha: str | None
    branch: str | None


@dataclass
class SessionRef:
    """A session that co-occurred with an issue's active period (ENH-1711)."""

    issue_id: str | None
    session_id: str | None
    jsonl_path: str | None
    first_message_ts: str | None
    last_message_ts: str | None


@dataclass
class SummaryNode:
    """A summary_nodes row from the LCM-style compaction DAG (FEAT-1712)."""

    id: int
    kind: str
    content: str
    tokens: int | None
    parent_id: int | None
    session_id: str | None
    ts_start: str | None
    ts_end: str | None
    created_at: str
    level: int | None


@dataclass
class GrepResult:
    """A message_event regex match with its covering summary node context (FEAT-1712)."""

    message_event_id: int
    session_id: str | None
    ts: str
    content: str
    summary_id: int | None
    summary_kind: str | None


@dataclass(frozen=True)
class SectionProvider:
    """Config-addressable digest section with query and render logic (ENH-1907)."""

    name: str
    query: Callable  # (conn, *, cutoff: str, cap: int) -> list
    default_cap: int
    render: Callable  # (rows: list) -> list[str]


@dataclass
class ProjectDigest:
    """Aggregated project-context snapshot from history.db (ENH-1907)."""

    sections: list[tuple[str, list[str]]]  # [(name, markdown_lines), ...] in config order
    days: int = 7

    @property
    def empty(self) -> bool:
        return all(not lines for _, lines in self.sections)
