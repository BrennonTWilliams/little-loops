"""Typed read-only query package for ``.ll/history.db`` (ENH-1752).

Provides the common queries that ll skills and agents need to consume the
session database without importing ad-hoc SQL into every caller. All
functions degrade gracefully: missing/empty/corrupt databases return empty
lists, never raise.

Package layout (ENH-2775 split from the former flat ``history_reader.py``):
    _base.py:       shared internals (``_connect_readonly``,
                     ``_row_to_dataclass``, ``_stale_cutoff``,
                     ``STALE_DAYS_DEFAULT``, the fixed-name ``logger``) plus
                     the small set of re-imported cross-package names
                     (``session_store``'s ``DEFAULT_DB_PATH``/``ensure_db``/
                     ``fts_phrase``/``normalize_issue_id``,
                     ``fsm.verdicts.CANNOT_JUDGE``) every other submodule may
                     depend on
    models.py:      all dataclasses shared across 2+ query domains
                     (``UserCorrection`` ... ``ProjectDigest``); dataclasses
                     used by only one domain (e.g. ``HookEvent``,
                     ``VerdictEvent``) stay co-located with that domain's
                     submodule instead
    search.py:      full-text search, correction, and file-event queries
                     (``search_index`` FTS5, ``user_corrections``,
                     ``file_events``)
    sessions.py:     session metadata, issue events, issue effort/velocity,
                     lifecycle/handoff, worktree summaries, conversation
                     turns (``issue_events``, ``issue_sessions`` VIEW,
                     ``session_lifecycle_events``)
    context.py:      skill events, context-pressure curves, commit events,
                     prompt-opt events, learning tests
    usage.py:        tool-event and usage-event queries (``tool_events``,
                     ``usage_events``)
    subagents.py:    subagent spawn tree/retries/budget (``subagent_runs``)
    runs.py:         test-run, orchestration-run, and loop-run queries
                     (``test_run_events``, ``orchestration_runs``,
                     ``prepatch_evidence``, ``loop_runs``)
    summary_dag.py:  Summary-DAG retrieval (FEAT-1712)
    digest.py:       project-digest section providers + aggregation
                     (ENH-1907)
    hooks.py:        hook execution telemetry (ENH-2506)
    harness.py:      ll-harness / eval outcome telemetry, incl. the
                      high-confidence-abstention check (ENH-230)
    events.py:       the four small, previously-unheadered tail domains:
                      verdict events (ENH-2504), advisor consults
                      (FEAT-3300), research triage (ENH-2990), review events
                      (ENH-2512)
    formatting.py:   ``ll_grep``/``ll_expand``/``ll_describe`` message-search
                      formatting layer

Grouping rule for future readers: one submodule per backing table/view, or a
tightly-coupled cluster of small tables that share no code with any other
domain (e.g. ``context.py``'s five independent single-table query groups).
Every submodule may import from ``_base.py``/``models.py`` only, never a
sibling submodule — the package forms a DAG with those two as its only
shared leaves.

Public API:
    UserCorrection, FileEvent, SearchResult, IssueEvent, SkillEvent,
    CommitEvent, PromptOptEvent, RunEvent, OrchestrationRun, LoopRun,
    LearningTestEvent, LifecycleEvent, SubagentRun, UsageEvent,
    ContextPressureEvent, SessionRef, SummaryNode, GrepResult,
    SectionProvider, ProjectDigest:  dataclasses for query results
    HookEvent, HarnessEvent, HighConfidenceAbstention, VerdictEvent,
    AdvisorConsultRow, ConsultStats, AxisRates, ResearchTriageStats,
    ReviewEvent:                     domain-local dataclasses (see models.py
                                     note above)
    SECTION_PROVIDERS:               registry of v1 digest section providers (ENH-1907)
    find_user_corrections(topic, ...) -> list[UserCorrection]
    recent_file_events(path, ...) -> list[FileEvent]
    search(query, ...) -> list[SearchResult]
    related_issue_events(issue_id, ...) -> list[IssueEvent]
    find_session_for_issue_transition(issue_id, transition, ...) -> str | None
    recent_skill_events(skill_name, ...) -> list[SkillEvent]
    summarize_skills(since, ...) -> list[dict]
    agent_usage(since, ...) -> list[dict]
    recent_tool_events(...) -> list[dict]
    mcp_server_usage(server, ...) -> list[dict]
    mcp_failure_rate(server, tool, ...) -> list[dict]
    cost_attribution(group_by, ...) -> list[dict]
    waste_attribution(since, ...) -> list[dict] (ENH-2722)
    recent_usage_events(...) -> list[UsageEvent]
    aggregate_usage(group_by, ...) -> list[dict]
    context_pressure_curve(session_id, ...) -> list[ContextPressureEvent]
    pressure_crossings(session_id, ...) -> list[ContextPressureEvent]
    pressure_summary(session_id, ...) -> dict | None
    recent_commit_events(branch, issue_id, ...) -> list[CommitEvent]
    commit_issue_for_sha(commit_sha, ...) -> str | None (FEAT-2867)
    recent_prompt_opt_events(mode, ...) -> list[PromptOptEvent]
    prompt_opt_offer_rate(since, ...) -> float | None
    recent_learning_tests(status, ...) -> list[LearningTestEvent]
    find_learning_test(target, ...) -> LearningTestEvent | None
    recent_lifecycle_events(event, since, ...) -> list[LifecycleEvent]
    handoff_frequency(since, ...) -> int
    worktree_summary(issue_id, since, ...) -> list[dict] (ENH-2509)
    subagent_tree(session_id, ...) -> list[SubagentRun]
    subagent_retries(agent_type, since, ...) -> list[dict]
    subagent_budget(session_id, ...) -> dict | None
    recent_test_runs(branch, head_sha, ...) -> list[RunEvent]
    recent_orchestration_runs(driver, issue_id, ...) -> list[OrchestrationRun]
    aggregate_orchestration_runs(group_by, ...) -> list[dict]
    read_base_sha(issue_id, ...) -> str | None (ENH-2866)
    read_base_dirty(issue_id, ...) -> bool | None (ENH-3142)
    read_prepatch_evidence(issue_id, ...) -> dict | None (ENH-2997)
    recent_loop_runs(loop_name, ...) -> list[LoopRun]
    find_loop_run(run_id, ...) -> LoopRun | None
    aggregate_loop_runs(group_by, ...) -> list[dict]
    sessions_for_issue(issue_id, ...) -> list[SessionRef]
    issue_effort(issue_id, ...) -> dict | None
    recent_issue_velocity(limit, ...) -> list[dict]
    lookup_session_metadata(session_id, ...) -> dict
    conversation_turns(db_path, ...) -> list[list[tuple[str, str]]]
    ll_grep(pattern, ...) -> list[GrepResult]
    ll_expand(summary_id, ...) -> list[dict]
    ll_describe(node_id, ...) -> SummaryNode | None
    condensed_nodes_for_issue(issue_id, ...) -> list[SummaryNode]
    project_digest(db_path, ...) -> ProjectDigest
    render_project_context(digest, ...) -> str
    recent_hook_events(event_name, exit_code, since, ...) -> list[HookEvent]
    hook_failure_rate(event_name, since, ...) -> float | None
    hook_latency_p95(event_name, since, ...) -> float | None
    recent_harness_events(runner, target, since, ...) -> list[HarnessEvent]
    harness_eval_pass_rate(target, since, ...) -> float | None
    harness_eval_abstention_rate(target, since, ...) -> dict | None (ENH-3185 AC4)
    check_high_confidence_abstention(...) -> list[HighConfidenceAbstention] (ENH-230)
    harness_event_by_id(db_path, attempt_id) -> HarnessEvent | None (ENH-3407)
    authoritative_attempt(db_path, cell_key, repetition) -> HarnessEvent | None (ENH-3407)
    authoritative_attempts(db_path, cell_key) -> list[HarnessEvent] (ENH-3407)
    recent_verdict_events(verdict_kind, target_id, since, ...) -> list[VerdictEvent]
    verdict_pass_rate(verdict_kind, target_id, since, ...) -> list[dict]
    query_advisor_consults(db_path, ...) -> list[AdvisorConsultRow] (FEAT-3300)
    consult_stats(db_path, ...) -> ConsultStats (FEAT-3300)
    research_triage_stats(db_path) -> ResearchTriageStats (ENH-2990)
    recent_review_events(reviewer_skill, target_id, since, ...) -> list[ReviewEvent]
    review_velocity(since, ...) -> list[dict]
"""

from __future__ import annotations

from little_loops.history_reader._base import (
    STALE_DAYS_DEFAULT,
    _connect_readonly,
    _row_to_dataclass,
    _stale_cutoff,
)
from little_loops.history_reader.context import (
    commit_issue_for_sha,
    context_pressure_curve,
    find_learning_test,
    pressure_crossings,
    pressure_summary,
    prompt_opt_offer_rate,
    recent_commit_events,
    recent_learning_tests,
    recent_prompt_opt_events,
    recent_skill_events,
    summarize_skills,
)
from little_loops.history_reader.digest import (
    SECTION_PROVIDERS,
    project_digest,
    render_project_context,
)
from little_loops.history_reader.events import (
    AdvisorConsultRow,
    AxisRates,
    ConsultStats,
    ResearchTriageStats,
    ReviewEvent,
    VerdictEvent,
    consult_stats,
    query_advisor_consults,
    recent_review_events,
    recent_verdict_events,
    research_triage_stats,
    review_velocity,
    verdict_pass_rate,
)
from little_loops.history_reader.formatting import (
    ll_describe,
    ll_expand,
    ll_grep,
)
from little_loops.history_reader.harness import (
    HarnessEvent,
    HighConfidenceAbstention,
    authoritative_attempt,
    authoritative_attempts,
    check_high_confidence_abstention,
    harness_eval_abstention_rate,
    harness_eval_pass_rate,
    harness_event_by_id,
    recent_harness_events,
)
from little_loops.history_reader.hooks import (
    HookEvent,
    hook_failure_rate,
    hook_latency_p95,
    recent_hook_events,
)
from little_loops.history_reader.models import (
    CommitEvent,
    ContextPressureEvent,
    FileEvent,
    GrepResult,
    IssueEvent,
    LearningTestEvent,
    LifecycleEvent,
    LoopRun,
    OrchestrationRun,
    ProjectDigest,
    PromptOptEvent,
    RunEvent,
    SearchResult,
    SectionProvider,
    SessionRef,
    SkillEvent,
    SubagentRun,
    SummaryNode,
    UsageEvent,
    UserCorrection,
)
from little_loops.history_reader.runs import (
    aggregate_loop_runs,
    aggregate_orchestration_runs,
    find_loop_run,
    read_base_dirty,
    read_base_sha,
    read_prepatch_evidence,
    recent_loop_runs,
    recent_orchestration_runs,
    recent_test_runs,
)
from little_loops.history_reader.search import (
    find_user_corrections,
    recent_file_events,
    search,
)
from little_loops.history_reader.sessions import (
    conversation_turns,
    find_session_for_issue_transition,
    handoff_frequency,
    issue_effort,
    lookup_session_metadata,
    recent_issue_velocity,
    recent_lifecycle_events,
    related_issue_events,
    sessions_for_issue,
    worktree_summary,
)
from little_loops.history_reader.subagents import (
    subagent_budget,
    subagent_retries,
    subagent_tree,
)
from little_loops.history_reader.summary_dag import condensed_nodes_for_issue
from little_loops.history_reader.usage import (
    agent_usage,
    aggregate_usage,
    cost_attribution,
    mcp_failure_rate,
    mcp_server_usage,
    recent_tool_events,
    recent_usage_events,
    waste_attribution,
)

__all__ = [
    "SECTION_PROVIDERS",
    "AdvisorConsultRow",
    "AxisRates",
    "CommitEvent",
    "ConsultStats",
    "ContextPressureEvent",
    "FileEvent",
    "GrepResult",
    "HarnessEvent",
    "HighConfidenceAbstention",
    "HookEvent",
    "IssueEvent",
    "LearningTestEvent",
    "LifecycleEvent",
    "LoopRun",
    "OrchestrationRun",
    "ProjectDigest",
    "PromptOptEvent",
    "ResearchTriageStats",
    "ReviewEvent",
    "RunEvent",
    "SearchResult",
    "SectionProvider",
    "SessionRef",
    "SkillEvent",
    "SubagentRun",
    "SummaryNode",
    "UsageEvent",
    "UserCorrection",
    "VerdictEvent",
    "agent_usage",
    "aggregate_loop_runs",
    "aggregate_orchestration_runs",
    "aggregate_usage",
    "authoritative_attempt",
    "authoritative_attempts",
    "check_high_confidence_abstention",
    "commit_issue_for_sha",
    "condensed_nodes_for_issue",
    "consult_stats",
    "context_pressure_curve",
    "conversation_turns",
    "cost_attribution",
    "find_learning_test",
    "find_loop_run",
    "find_session_for_issue_transition",
    "find_user_corrections",
    "handoff_frequency",
    "harness_eval_abstention_rate",
    "harness_eval_pass_rate",
    "harness_event_by_id",
    "hook_failure_rate",
    "hook_latency_p95",
    "issue_effort",
    "ll_describe",
    "ll_expand",
    "ll_grep",
    "lookup_session_metadata",
    "mcp_failure_rate",
    "mcp_server_usage",
    "prompt_opt_offer_rate",
    "pressure_crossings",
    "pressure_summary",
    "project_digest",
    "query_advisor_consults",
    "read_base_dirty",
    "read_base_sha",
    "read_prepatch_evidence",
    "recent_commit_events",
    "recent_file_events",
    "recent_harness_events",
    "recent_hook_events",
    "recent_issue_velocity",
    "recent_learning_tests",
    "recent_lifecycle_events",
    "recent_loop_runs",
    "recent_orchestration_runs",
    "recent_prompt_opt_events",
    "recent_review_events",
    "recent_skill_events",
    "recent_test_runs",
    "recent_tool_events",
    "recent_usage_events",
    "recent_verdict_events",
    "related_issue_events",
    "render_project_context",
    "research_triage_stats",
    "review_velocity",
    "search",
    "sessions_for_issue",
    "subagent_budget",
    "subagent_retries",
    "subagent_tree",
    "summarize_skills",
    "verdict_pass_rate",
    "waste_attribution",
    "worktree_summary",
    # Private functions re-exported for test access and for the three
    # issue_history modules (collisions.py, rework.py, agent_quality.py) that
    # import _connect_readonly directly, plus evolution.py's _stale_cutoff.
    "STALE_DAYS_DEFAULT",
    "_connect_readonly",
    "_row_to_dataclass",
    "_stale_cutoff",
]
