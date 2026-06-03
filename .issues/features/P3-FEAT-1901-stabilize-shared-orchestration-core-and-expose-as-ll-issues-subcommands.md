---
id: FEAT-1901
title: Stabilize shared orchestration core and expose as ll-issues subcommands
type: FEAT
priority: P3
status: open
captured_at: 2026-06-03T19:12:39Z
discovered_date: 2026-06-03
discovered_by: scope-epic
parent: EPIC-1867
relates_to: []
---

# FEAT-1901: Stabilize shared orchestration core and expose as ll-issues subcommands

## Summary

Wrap the shared orchestration modules — `DependencyGraph.get_ready_issues()`,
`verify_work_was_done()`/`verify_issue_completed()`, and `classify_failure`/`create_issue_from_failure` —
into a documented, test-gated internal library. Expose each as a new `ll-issues` subcommand:

- `ll-issues next --json --respect-deps [--priority …] [--skip …]` wrapping `DependencyGraph.get_ready_issues()` + filters
- `ll-issues verify-work <id> --baseline <sha>` wrapping `verify_work_was_done()` + `verify_issue_completed()`; exit 0 = real work, 1 = none
- `ll-issues classify-failure --rc <n> < err.txt` wrapping `classify_failure`/`create_issue_from_failure`

This is the **behavior-neutral Layer 0 prerequisite** for EPIC-1867. No existing behavioral changes — only wrapping and exposing. Existing tests gate it. The `verify-work` subcommand is the non-LLM evaluator the Layer-1 FSM needs to satisfy CLAUDE.md MR-1.

## Impact

- **Priority**: P3 — prerequisite for Layer 1 but low risk; behavior-neutral
- **Effort**: Small — wrapping existing code, no new logic
- **Risk**: Low — no behavioral changes; existing tests gate it
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-03 | Priority: P3

## Session Log
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`
