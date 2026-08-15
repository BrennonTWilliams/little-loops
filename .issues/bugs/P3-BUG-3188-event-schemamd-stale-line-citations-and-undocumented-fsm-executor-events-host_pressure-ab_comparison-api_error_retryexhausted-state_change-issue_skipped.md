---
id: BUG-3188
type: BUG
title: 'EVENT-SCHEMA.md: stale line citations and undocumented FSM executor events
  (host_pressure*, ab_comparison, api_error_retry/exhausted, state_change, issue_skipped)'
priority: P3
status: done
testable: false
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:39Z'
completed_at: '2026-08-15T19:31:32Z'
---

# BUG-3188: EVENT-SCHEMA.md: stale line citations and undocumented FSM executor events (host_pressure*, ab_comparison, api_error_retry/exhausted, state_change, issue_skipped)

## Summary

`/ll:audit-docs` (readme scope, 2026-08-15) found `docs/reference/EVENT-SCHEMA.md` has several stale source-line citations and is missing documentation for a whole class of FSM executor events.

## Current Behavior

- Line 996: `close_transports()` cited at `scripts/little_loops/events.py:110-115`; actual is `:109-115`.
- Line 1024: `OTelTransport` cited at `transport.py:338-492`; actual class spans `:337-500`.
- Line 1036: `WebhookTransport` cited at `transport.py:495-575`; actual class spans `:503-583`.
  - Note: the file is `scripts/little_loops/transport.py`, **not** `scripts/little_loops/events/transport.py` — confirm the doc's path prefix while editing.
- Line 81: the `pre_compact` per-intent note states unconditionally that it "Returns `LLHookResult(exit_code=2, ...)`" — omits the ENH-2341 SELFCOMPACT rubric gate, where `handle()` returns `exit_code=0` (no state write, no feedback) when `rubric_cfg.enabled` and the trajectory fails the rubric.
- Line 83: the `session_end` per-intent note says it "reads no payload keys" then in the same breath says it reads `payload.cwd` — self-contradictory. It also doesn't mention this intent is bound to Claude Code's `SessionStart` event (not `SessionEnd`), per `hooks/hooks.json` and the `sweep_stale_refs.py` docstring (re-homed due to upstream `SessionEnd` timeout bug, anthropics/claude-code#32712/#41577).
- StateManager section (~755-790): missing the `state.issue_skipped` event (`StateManager` mark-skipped path, `scripts/little_loops/state.py:230-232`).
- No section or Quick Reference row exists for several FSM executor-emitted events: `host_pressure`, `host_pressure_relieved`, `host_pressure_abort` (`scripts/little_loops/fsm/host_guard.py:33-35`, emitted in `executor.py`), `host_budget_exceeded` (`host_guard.py:38`), `request_path_downgrade` (`executor.py:2829`), `ab_comparison` (`executor.py:3021`), `api_error_retry`/`api_error_exhausted` (`executor.py:3458,3467` — referenced by name elsewhere in the doc's `infra_retry` section but never documented as first-class entries), and `state_change` (emitted by the Unix-socket transport's seed callback, `transport.py:592`).

## Expected Behavior

Every event type actually emitted by the FSM executor and hook handlers has a documented
entry (payload shape + Quick Reference row), and source citations no longer go stale.

### Fix the citations by removing the line numbers, not by correcting them (amended 2026-08-15)

**Do not** simply rewrite `:338-492` → `:337-500`. Every citation in this issue was
accurate when it was written; they drifted because `executor.py` and `transport.py` are
among the most-edited files in the repo (`executor.py`: 199 edits in the trailing 7 days).
Correcting the integers re-arms the same failure on the next refactor and guarantees this
issue gets re-filed.

Convert each citation to a **symbol anchor** instead — the convention ENH-1298 already
established for issue pipelines:

| Instead of | Write |
|---|---|
| `scripts/little_loops/events.py:110-115` | `EventBus.close_transports()` in `scripts/little_loops/events.py` |
| `transport.py:338-492` | `OTelTransport` in `scripts/little_loops/transport.py` |
| `transport.py:495-575` | `WebhookTransport` in `scripts/little_loops/transport.py` |
| `transport.py:592` | the socket seed callback in `UnixSocketTransport` |
| `executor.py:2829` / `:3021` / `:3458,3467` | the `request_path_downgrade` / `ab_comparison` / `api_error_retry` emit sites in `scripts/little_loops/fsm/executor.py` |
| `host_guard.py:33-35` / `:38` | the `host_pressure*` / `host_budget_exceeded` constants in `scripts/little_loops/fsm/host_guard.py` |
| `scripts/little_loops/state.py:230-232` | the mark-skipped path in `StateManager` |

A symbol name survives every edit that doesn't rename or delete the symbol, and a rename
that breaks the reference is a change someone is already reviewing. Keep line numbers only
where no enclosing symbol exists.

## Acceptance Criteria

- [ ] No `path.py:NNN` line-number citation remains in the sections this issue touches; each is replaced by a symbol anchor per the table above.
- [ ] `EVENT-SCHEMA.md` documents `host_pressure`, `host_pressure_relieved`, `host_pressure_abort`, `host_budget_exceeded`, `request_path_downgrade`, `ab_comparison`, `api_error_retry`, `api_error_exhausted`, `state_change`, and `state.issue_skipped` — each with a payload shape and a Quick Reference row.
- [ ] Line 81's `pre_compact` note records the ENH-2341 SELFCOMPACT rubric gate (`exit_code=0` when the trajectory fails the rubric).
- [ ] Line 83's `session_end` note is internally consistent (it *does* read `payload.cwd`) and states that the intent is bound to Claude Code's `SessionStart` event, with the upstream-bug rationale.
- [ ] `transport.py` citations use the correct path (`scripts/little_loops/transport.py`).

## Motivation

EVENT-SCHEMA.md is the contract doc for anyone building an events consumer (webhook/OTel/socket integrations). Undocumented event types mean consumers can't discover payload shapes without reading executor.py directly, defeating the doc's purpose.

## Impact

- **Priority**: P3 — line-citation drift is cosmetic; the missing event documentation is more substantive but affects an advanced/integration audience.
- **Effort**: Medium — line fixes are mechanical; new event sections require reading `host_guard.py` and the relevant `executor.py` emit sites to document payload shapes accurately.
- **Risk**: None — doc-only change.


## Status

**Open** | Created: 2026-08-15 | Priority: P3
