---
id: FEAT-1902
title: Author loops/ll-auto.yaml FSM + ll-auto shim + A/B parity harness
type: FEAT
priority: P2
status: open
captured_at: 2026-06-03T19:12:39Z
discovered_date: 2026-06-03
discovered_by: scope-epic
parent: EPIC-1867
relates_to: [FEAT-1901]
---

# FEAT-1902: Author loops/ll-auto.yaml FSM + ll-auto shim + A/B parity harness

## Summary

Write `loops/ll-auto.yaml` as the FSM that replaces `AutoManager.run()` control
flow. The FSM calls Layer-0 CLIs (`ll-issues next`, `ll-issues verify-work`,
`ll-issues classify-failure`) as shell actions. Key requirements:

- Mandatory `verify_work` state backed by an `exit_code` evaluator calling
  `ll-issues verify-work <id> --baseline <sha>` — never trust the implement step's
  exit code alone. This satisfies CLAUDE.md MR-1.
- `max_iterations` derived from backlog size (not hard-coded 50, which halts after
  ~10 issues).
- Convert `ll-auto` CLI to a thin shim over `ll-loop run ll-auto`.
- Pass `ll-loop validate ll-auto` (MR-1/MR-3 clean).
- Pass `ll-loop diagnose-evaluators ll-auto` with `verify_work` verdict variance
  `p(1-p) ≥ 0.05` over ≥10 runs.
- Pass `ll-loop run ll-auto --baseline` showing the harness ≥ unguided baseline.
- **A/B parity harness**: run the same fixed backlog through legacy `ll-auto`
  (`AutoManager.run()`) and the new FSM loop; assert identical `completed/failed`
  sets and matching `history.db` event payloads. This gates merging to main.

Soft-deprecate `AutoManager.run()` for one release (do not delete yet).

Depends on FEAT-1901 (Layer 0 CLI subcommands).

## Impact

- **Priority**: P2 — critical path; the core deliverable of Layer 1
- **Effort**: Large — new FSM YAML, CLI shim refactor, parity test harness
- **Risk**: High — risk concentrated in the verify/parity gates
- **Breaking Change**: No (shim preserves CLI interface)

## Status

**Open** | Created: 2026-06-03 | Priority: P2

## Session Log
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`
