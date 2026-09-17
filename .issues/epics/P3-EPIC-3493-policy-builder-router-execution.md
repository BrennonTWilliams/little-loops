---
id: EPIC-3493
title: Policy Builder & Router Execution
type: EPIC
priority: P3
status: open
captured_at: "2026-09-16T23:04:36Z"
discovered_date: 2026-09-16
discovered_by: link-epics
relates_to: []
---

# EPIC-3493: Policy Builder & Router Execution

## Summary

Group of 8 related issues: Policy builder preview, validation, and editing correctness (browser/core), Policy-router runtime: stale LLM scores across passes and decision-table dispatch errors route to a success outcome, Policy builder skill catalog is empty in consumer projects (single-root plugin discovery), Policy builder persistence, undo/redo, and saved projects, Policy builder lifecycle layout, task presets, and execution summary, Policy builder explicit terminal destinations, scoring instructions, and gate stamping, Policy builder offline scenario suites and explanations, and Policy builder host-approved connected execution.

## Children

- **BUG-3486** — Policy builder preview, validation, and editing correctness (browser/core) (done)
- **BUG-3489** — Policy-router runtime: stale LLM scores across passes and decision-table dispatch errors route to a success outcome (done)
- **BUG-3490** — Policy builder skill catalog is empty in consumer projects (single-root plugin discovery) (done)
- **ENH-3487** — Policy builder persistence, undo/redo, and saved projects (open)
- **ENH-3491** — Policy builder lifecycle layout, task presets, and execution summary (open)
- **BUG-3499** — FSM executor: failure_terminal is False when a cap handler routes to a failure terminal (open; runtime prerequisite for ENH-3492)
- **ENH-3492** — Policy builder explicit terminal destinations, scoring instructions, and gate stamping (open)
- **FEAT-3488** — Policy builder offline scenario suites and explanations (open)
- **FEAT-3498** — Policy builder host-approved connected execution (open)
- **FEAT-3501** — Policy builder shared transition analysis and structural graph (open)


## Implementation Order

ENH-3487 → ENH-3491 → ENH-3492 → FEAT-3488 → FEAT-3498. BUG-3499 (executor `failure_terminal` for cap-routed finishes) is independent of the builder chain and must land before ENH-3492. The connected-execution split lets offline authoring and scenario suites ship without waiting for queue approval/result integration.