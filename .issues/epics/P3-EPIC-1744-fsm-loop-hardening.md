---
id: EPIC-1744
title: FSM Loop Hardening
type: EPIC
priority: P3
status: open
captured_at: "2026-05-27T00:00:00Z"
discovered_date: "2026-05-27"
discovered_by: manual
labels: [epic, loops, fsm, resilience]
relates_to: [ENH-1677, ENH-1678, ENH-1701, ENH-1735, ENH-1684, ENH-1797, FEAT-1689]
---

# EPIC-1744: FSM Loop Hardening

## Summary

Make the FSM loop executor more resilient against transient failures and more observable during runs. The five children fall into two themes: **resilience** (retry config, crash recovery, overwrite protection) and **observability** (artifact paths in run output). All five are additive, low-risk improvements to existing infrastructure with no breaking changes.

## Goal

When this epic is done, loops that encounter transient infrastructure failures (API socket disconnect, OOM) retry intelligently rather than routing to `failed`; long-running loops can resume from a checkpoint after a crash; deep-research runs are isolated by timestamp so re-runs never silently destroy prior results; and `ll-loop run` surfaces artifact paths so the user can inspect outputs in a separate terminal while a loop is running.

## Motivation

Observed pain points from production loop runs:
- `general-task` routes to `failed` on any non-zero exit even when the failure is transient (ENH-1677, ENH-1678).
- A SIGKILL during `general-task execute` (10+ min step) loses all plan-step progress (ENH-1735).
- `deep-research` silently overwrites prior run artifacts when re-run on the same topic (ENH-1684).
- `ll-loop run` shows no hint of where output files land, requiring a separate `find` (ENH-1701).

## Scope

### In scope

- Retry config wiring in `general-task.yaml` (ENH-1677)
- `retryable_exit_codes` schema + executor support (ENH-1678)
- Checkpoint/resume for `general-task` execute state (ENH-1735)
- Timestamp-suffixed run directories in `deep-research` (ENH-1684)
- Artifact-paths header in `ll-loop run` output (ENH-1701)

### Out of scope

- Retry support in loops other than `general-task` (separate follow-up after ENH-1677/1678 validate the pattern)
- Full crash-resume for loops other than `general-task`
- Structured artifact manifests or artifact registries

## Children

- **ENH-1677** — Apply retry hardening to `general-task.yaml` using existing `max_retries` fields
- **ENH-1678** — Add `retryable_exit_codes` filter to FSM state retry config (depends on ENH-1677 validating the retry wiring)
- **ENH-1735** — Persist plan step index before execute for crash recovery in `general-task` loop
- **ENH-1684** — Add timestamp suffix to `deep-research` run directory to prevent silent overwrite
- **ENH-1701** — Show artifact paths in `ll-loop run` output
- **ENH-1797** — Cost / token telemetry per FSM state in loop runs
- **FEAT-1689** — add ll-harness CLI for one-shot runner evaluation

## Implementation Order

1. **ENH-1677** first — validates that `max_retries`/`on_retry_exhausted` wiring is correct in `general-task.yaml` before ENH-1678 extends the mechanism.
2. **ENH-1678** — adds the `retryable_exit_codes` filter to the executor schema; best landed after ENH-1677 so the retry path is exercised first.
3. **ENH-1735**, **ENH-1684**, **ENH-1701** — independent of each other and of the retry children; can land in any order.

## Integration Map

### Primary Files

- `scripts/little_loops/loops/general-task.yaml` — ENH-1677, ENH-1735
- `scripts/little_loops/fsm/schema.py` + `scripts/little_loops/fsm_executor.py` — ENH-1678
- `scripts/little_loops/loops/deep-research.yaml` — ENH-1684
- `scripts/little_loops/cli/loop/__init__.py` (or `_helpers.py`) — ENH-1701

### Tests

- `scripts/tests/test_builtin_loops.py` — retry path and checkpoint assertions
- `scripts/tests/test_fsm_executor.py` — `retryable_exit_codes` filtering

## Impact

- **Priority**: P3 — real developer pain; no production blockers
- **Effort**: Small per child; Medium aggregate
- **Risk**: Low — all additive; default behaviors unchanged
- **Breaking Change**: No

## Labels

`epic`, `loops`, `fsm`, `resilience`

---

**Open** | Created: 2026-05-27 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-05-31T02:30:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
