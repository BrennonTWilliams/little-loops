---
id: BUG-3188
type: BUG
title: 'EVENT-SCHEMA.md: stale line citations and undocumented FSM executor events
  (host_pressure*, ab_comparison, api_error_retry/exhausted, state_change, issue_skipped)'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:39Z'
---

# BUG-3188: EVENT-SCHEMA.md: stale line citations and undocumented FSM executor events (host_pressure*, ab_comparison, api_error_retry/exhausted, state_change, issue_skipped)

## Summary

`/ll:audit-docs` (readme scope, 2026-08-15) found `docs/reference/EVENT-SCHEMA.md` has several stale source-line citations and is missing documentation for a whole class of FSM executor events.

## Current Behavior

- Line 996: `close_transports()` cited at `scripts/little_loops/events.py:110-115`; actual is `:109-115`.
- Line 1024: `OTelTransport` cited at `transport.py:338-492`; actual class spans `:337-500`.
- Line 1036: `WebhookTransport` cited at `transport.py:495-575`; actual class spans `:503-583`.
- Line 81: the `pre_compact` per-intent note states unconditionally that it "Returns `LLHookResult(exit_code=2, ...)`" — omits the ENH-2341 SELFCOMPACT rubric gate, where `handle()` returns `exit_code=0` (no state write, no feedback) when `rubric_cfg.enabled` and the trajectory fails the rubric.
- Line 83: the `session_end` per-intent note says it "reads no payload keys" then in the same breath says it reads `payload.cwd` — self-contradictory. It also doesn't mention this intent is bound to Claude Code's `SessionStart` event (not `SessionEnd`), per `hooks/hooks.json` and the `sweep_stale_refs.py` docstring (re-homed due to upstream `SessionEnd` timeout bug, anthropics/claude-code#32712/#41577).
- StateManager section (~755-790): missing the `state.issue_skipped` event (`StateManager` mark-skipped path, `scripts/little_loops/state.py:230-232`).
- No section or Quick Reference row exists for several FSM executor-emitted events: `host_pressure`, `host_pressure_relieved`, `host_pressure_abort` (`scripts/little_loops/fsm/host_guard.py:33-35`, emitted in `executor.py`), `host_budget_exceeded` (`host_guard.py:38`), `request_path_downgrade` (`executor.py:2829`), `ab_comparison` (`executor.py:3021`), `api_error_retry`/`api_error_exhausted` (`executor.py:3458,3467` — referenced by name elsewhere in the doc's `infra_retry` section but never documented as first-class entries), and `state_change` (emitted by the Unix-socket transport's seed callback, `transport.py:592`).

## Expected Behavior

All source-line citations match current code, and every event type actually emitted by the FSM executor and hook handlers has a documented entry (payload shape + Quick Reference row).

## Motivation

EVENT-SCHEMA.md is the contract doc for anyone building an events consumer (webhook/OTel/socket integrations). Undocumented event types mean consumers can't discover payload shapes without reading executor.py directly, defeating the doc's purpose.

## Impact

- **Priority**: P3 — line-citation drift is cosmetic; the missing event documentation is more substantive but affects an advanced/integration audience.
- **Effort**: Medium — line fixes are mechanical; new event sections require reading `host_guard.py` and the relevant `executor.py` emit sites to document payload shapes accurately.
- **Risk**: None — doc-only change.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]
