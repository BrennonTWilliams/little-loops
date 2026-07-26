---
id: ENH-2834
type: ENH
title: "learning gate should invoke ready-to-implement-gate directly instead of chaining a redundant impl loop with empty task"
priority: P2
status: open
captured_at: '2026-07-26T18:09:17Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
relates_to:
- BUG-2832
- BUG-2833
- BUG-2831
- FEAT-1738
labels:
- learning-gate
- ll-auto
- proof-first-task
- efficiency
---

# ENH-2834: learning gate should invoke ready-to-implement-gate directly instead of chaining a redundant impl loop with empty task

## Summary

ll-auto's learning gate (`run_learning_gate_for_issue`, `scripts/little_loops/learning_tests/gate.py:58`) only needs a prove/refute verdict for the issue's `learning_tests_required` targets — after the gate passes, `issue_manager.py` proceeds to its own Phase 2 implementation. But the wrapper it spawns, `proof-first-task`, always chains past the gate into `run_impl` (`proof-first-task.yaml:65`), launching the `general-task` impl loop with `input: "${context.task}"` where `task` is empty (gate.py passes only `issue_file` and `targets_csv`). This is:

1. **Redundant** — any impl work done there is thrown away; ll-auto implements the issue itself afterwards.
2. **Wasteful** — a full baseline pytest run (~2.5 min) plus DoD/plan LLM calls per gated issue.
3. **Fragile** — the empty-task injection makes the child improvise a plan from ambient repo state, and any impl-side failure is mislabeled as a gate block (BUG-2833; currently guaranteed by BUG-2832). Observed in run `proof-first-task-20260726T125247`, which caused BUG-2831's spurious `gate_blocked` deferral.

## Current Behavior

`gate.py` → `ll-loop run proof-first-task --context issue_file=... --context targets_csv=...` → `gate_direct` (ready-to-implement-gate, the actual proof) → on success `run_impl` (general-task with empty task) → outcome of the *impl* loop determines the gate verdict.

## Expected Behavior

The learning gate's verdict is determined solely by the proof step. Either:

- **Option A (preferred)**: `gate.py` invokes `ready-to-implement-gate` directly: `ll-loop run ready-to-implement-gate --context targets=<csv>`. Its terminals are exactly `done`/`blocked`, so the existing exit-code mapping becomes correct by construction, and BUG-2833's conflation is structurally impossible. The `targets` are already resolved by `resolve_learning_targets()` before the call, so the JIT-extraction fallback (`assumption-firewall` path) is only needed when `targets_csv` is empty — keep routing that case through `proof-first-task`, or accept extraction inline.
- **Option B**: add a `gate_only: "true"` context flag to `proof-first-task` that routes `gate_direct`/`check_gate_blocked` success to `done` instead of `run_impl`; `gate.py` passes it.

## Motivation

Deferral is supposed to be the rarest autodev outcome. Every structural dependency between the learning gate and an unrelated impl loop widens the set of failures that masquerade as `gate_blocked`. Cutting the impl loop out of the gate path removes an entire failure class and ~3–5 minutes of wasted compute per gated issue.

## Proposed Solution

1. Implement Option A in `gate.py` when `targets` is non-empty (the ll-auto path always has resolved targets — `issue_manager.py:875` calls `resolve_learning_targets(info)` first); fall back to `proof-first-task` only for the empty-targets JIT-extraction case.
2. Keep `proof-first-task` unchanged as the opt-in gate+impl wrapper for direct users (FEAT-1738's original design), but fix its empty-task hole: when `context.task` is empty and `issue_file` is set, synthesize the task from the issue file (or fail fast) before `run_impl` — per the known empty-task-injection defect.
3. Update the docstring/comments in `gate.py` and the ENH-2319 marker contract accordingly.

## Acceptance Criteria

- [ ] With resolved targets, `run_learning_gate_for_issue` no longer spawns any impl loop; the verdict comes from `ready-to-implement-gate` (or gate-only mode) alone
- [ ] A proven-registry issue whose impl chain is broken still passes the learning gate (regression test for the BUG-2831 scenario)
- [ ] `proof-first-task` with `issue_file` set but empty `task` either synthesizes the task from the issue file or fails fast at validation — it no longer launches `general-task` with an empty task
- [ ] Gate wall-time for a proven target drops to the registry-check cost (no baseline pytest run)
- [ ] `python -m pytest scripts/tests/` passes with no new failures

## Session Log
- `/ll:capture-issue` - 2026-07-26T18:09:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad137648-1307-46a8-940f-ff28f5c2fa83.jsonl`
