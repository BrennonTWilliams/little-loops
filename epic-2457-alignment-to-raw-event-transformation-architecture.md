Review: EPIC-2457 sub-issue alignment with the ENH-2461 architectural pattern

The pattern

ENH-2461's Resolution codifies the principle:

▎ "raw_events is the single source of truth; all else are transformations (_backfill_* parsers reading from raw_events, dispatched via rebuild())."

The boundary, per ENH-2461 itself, is the data source:
- In-band (data already in session transcript JSONL, e.g. tool calls, assistant messages, CLI invocations) → _backfill_* parser over raw_events
- Out-of-band (external systems: git, pytest, config files, in-process Python state) → legitimate direct-write sibling (record_*_event), not a pattern violation

ENH-2461's Resolution explicitly calls out five siblings that "become 'add a parser' tasks instead of 'add a table' tasks": ENH-2461, 2493, 2494, 2506, 2507, 2511.

---
Aligned to the pattern

┌──────────┬────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  Child   │ Status │                                                                                   How it aligns                                                                                    │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2461 │ done   │ The reference implementation: _backfill_usage_events() parser over raw_events, filters type == "assistant", computes cost_usd via pricing.estimate_cost_usd, wired into rebuild(). │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2581 │ done   │ The structural foundation that establishes the pattern (raw_events table, rebuild() dispatcher, compact/prune only touching raw_events).                                           │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2497 │ open   │ Additive agent_type column on tool_events — live writer at post_tool_use.py plus a _backfill_tool_events extension to extract args.get("subagent_type") from JSONL. Both write     │
│          │        │ paths keep tool_events consistent.                                                                                                                                                 │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2511 │ open   │ Same shape as ENH-2497 (batched): additive mcp_server/mcp_tool/mcp_outcome/latency_ms columns on tool_events with a _backfill_tool_events extension.                               │
└──────────┴────────┴────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

---
Called out as "should be parsers" but currently planned as direct-write — NOT aligned, needs re-scoping

ENH-2461's Resolution names these as parser tasks, but their current Integration Maps still specify direct-write siblings:

┌──────────┬────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  Child   │ Status │                                                                                      Mismatch                                                                                      │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2493 │ open   │ harness_events — record_harness_event() called from cli/harness.py:main_harness(). But ll-harness CLI invocations are already in the transcript as tool_events rows for the Bash   │
│          │        │ tool. Could be _backfill_harness_events() parsing tool_events rows where the args point at ll-harness. Currently misses the pattern.                                               │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2494 │ open   │ check_events (ruff/mypy/ruff-format) — record_check_event() from a thin Python wrapper around the lint commands. But these are also Bash tool invocations in the transcript with   │
│          │        │ parseable stdout/exit_code. Could be a parser over tool_events keyed on command basename. Currently misses the pattern.                                                            │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│          │        │ hook_events — explicit plan to wrap every handle() in hook_event_context() (a @contextmanager) and write rows from inside the hook dispatch. But the dispatcher itself already     │
│ ENH-2506 │ open   │ knows each event name and exit code; transcript doesn't carry hook telemetry but the dispatcher lives in the same process as the transcript-producing host — meaning there's a     │
│          │        │ hybrid option: write from the dispatcher (current plan) is reasonable, but a "post-hoc" hook-telemetry derivation from tool_events rows (e.g., one row per tool call + the         │
│          │        │ PostToolUse envelope) is technically possible.                                                                                                                                     │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│          │        │ context_pressure_events — explicitly opts out per its own Codebase Research Findings (line 109): "pressure rows cannot be reconstructed from raw_events because the raw transcript │
│ ENH-2507 │ open   │  does not contain the monitor's percentage readings." This is a justified opt-out (raw_events really doesn't carry the data), but worth flagging that it's a deliberate pattern    │
│          │        │ deviation with a one-line rationale.                                                                                                                                               │
└──────────┴────────┴────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

---
Out-of-band data sources — legitimately direct-write (not pattern violations)

These have data sources that don't exist in the session transcript at all. Direct-write is the only viable path:

┌──────────┬────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  Child   │ Status │                                                            Data source                                                            │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2458 │ done   │ git log (external to JSONL)                                                                                                       │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2459 │ done   │ pytest subprocess (external to JSONL)                                                                                             │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2460 │ done   │ skill hook callback (lives in process)                                                                                            │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2462 │ done   │ set-issue-status call (lives in process)                                                                                          │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2492 │ open   │ ProcessingState in state.json (Python orchestration, not in transcript)                                                           │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2495 │ open   │ lifecycle hooks (Stop/PreCompact/sweep) — fires before/during/after the session                                                   │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2496 │ open   │ merged .ll/ll-config.json (external file)                                                                                         │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2498 │ open   │ UserPromptSubmit optimize hook (in-process, with heuristic state)                                                                 │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2510 │ open   │ ll-history-context query telemetry (in-process)                                                                                   │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2504 │ open   │ verifier CLI runs — borderline: also appear as Bash tool invocations in transcript, could in principle be a parser. Worth noting. │
├──────────┼────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2512 │ open   │ read-side audit CLI runs — same borderline case as ENH-2504.                                                                      │
└──────────┴────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

---
Different surfaces — neither parsers nor direct-write tables in the strict sense

┌──────────┬────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  Child   │ Status │                                                               Surface                                                                │
├──────────┼────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2463 │ open   │ per-loop-run summary rows — loop_runs table, populated by the FSM runner at end-of-run (lives in process; can't be derived post-hoc) │
├──────────┼────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2464 │ open   │ source_session_id/source_issue_id backlinks to .ll/decisions.yaml — a YAML metadata field addition, not a DB table                   │
├──────────┼────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2465 │ open   │ periodic epic-progress snapshots — periodic scheduler write; no per-event source                                                     │
├──────────┼────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2466 │ open   │ Learning Test Registry mirror — mirror from registry (external source) into DB                                                       │
└──────────┴────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

---
Widening existing tables — inherits parent table's pattern

┌──────────┬────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  Child   │ Status │                                                                               Parent table's pattern                                                                               │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2508 │ open   │ widens commit_events with tag/release_version; uses git tag --points-at <sha> (external). Inherits ENH-2458's direct-write pattern (NOT parser-based) — consistent, not a new      │
│          │        │ violation.                                                                                                                                                                         │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2509 │ open   │ widens session_lifecycle_events with worktree discriminators. Inherits ENH-2495's lifecycle pattern.                                                                               │
├──────────┼────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ENH-2505 │ open   │ subagent_runs — Option B (SubagentStart/SubagentStop hooks) is the chosen approach. Optional _backfill_subagent_runs mentioned but the primary spec is direct-write. Mostly        │
│          │        │ consistent with ENH-2497's hook-path.                                                                                                                                              │
└──────────┴────────┴────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

---
Structural / operational (not tables)

- ENH-2580 (backfill source path) — operational, no table
- ENH-2582 (analytics.auto_collect runner) — operational, no table

---
Summary

Alignment rate: ~10 of 28 children are cleanly aligned or correctly justified as out-of-band; 4 (ENH-2493, ENH-2494, ENH-2506, ENH-2507) are flagged by ENH-2461's own Resolution as "parser tasks" but are still specified as direct-write siblings in their Integration Maps; 2 (ENH-2504, ENH-2512) are borderline cases where the transcript does carry the data but the spec opts for direct-write.

Concrete suggestions:
1. ENH-2493 / ENH-2494 — these are the most actionable gaps: ll-harness and ruff/mypy invocations are Bash tool calls already captured by _backfill_tool_events. A _backfill_harness_events / _backfill_check_events parser could read the same tool_events rows keyed on command basename, eliminating the need for two parallel producer paths.
2. ENH-2506 — document the deliberate departure from the pattern in the issue body (ENH-2507 already does this explicitly; ENH-2506 should match).
3. ENH-2504 / ENH-2512 — flag the borderline case: verifier and audit CLI runs are in the transcript; an opt-in to parser-mode would be consistent with ENH-2461's intent.