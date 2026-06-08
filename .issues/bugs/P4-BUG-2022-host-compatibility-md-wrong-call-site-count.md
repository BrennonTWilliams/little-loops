---
id: BUG-2022
title: HOST_COMPATIBILITY.md footnote says 'seven call sites' but table has six rows
status: done
priority: P4
type: BUG
created: 2026-06-08
completed_at: 2026-06-08 16:47:37+00:00
---

## Summary

The `## Orchestration CLI` section of `docs/reference/HOST_COMPATIBILITY.md` contains a footnote `[^orch]` claiming "All seven call sites now route through `scripts/little_loops/host_runner.py`", but the table above it only has six rows. `ll-sprint` is the missing seventh entry — it routes through `host_runner.py` via `parallel/worker_pool.py` → `resolve_host()`, but is absent from the table and from the prose list in the section intro.

## Current Behavior

`docs/reference/HOST_COMPATIBILITY.md`, footnote `[^orch]` (line 149):
> "All seven call sites now route through `scripts/little_loops/host_runner.py`."

The Orchestration CLI table has six rows: `ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, `ll-harness`, and `FSM evaluators / handoff`. The section intro paragraph (lines 131–132) also lists tools without `ll-sprint`.

## Expected Behavior

Either:
1. `ll-sprint` is added as a seventh row to the table (and to the intro paragraph), making the count accurate, **or**
2. The footnote is updated to say "six" if `ll-sprint` does not actually route through `host_runner.py`.

Verification: `ll-sprint` calls `ParallelOrchestrator` → `WorkerPool` → `resolve_host()` (confirmed in `scripts/little_loops/parallel/worker_pool.py` line 22), so option 1 is correct.

## Steps to Reproduce

1. Open `docs/reference/HOST_COMPATIBILITY.md`.
2. Navigate to the `## Orchestration CLI` section.
3. Count the rows in the table: six rows present.
4. Read footnote `[^orch]`: states "seven call sites."
5. Observe the mismatch.

## Fix

Add `ll-sprint` as a row in the Orchestration CLI table and add it to the section intro paragraph. The footnote count of "seven" is correct once `ll-sprint` is included.

## Location

- **File**: `docs/reference/HOST_COMPATIBILITY.md`
- **Section**: `## Orchestration CLI`, table at lines 140–147, footnote `[^orch]` at line 149, intro paragraph at lines 131–132
- **Anchor**: `## Orchestration CLI`

## Impact

- **Priority**: P4 — Documentation inaccuracy with no runtime effect; misleads readers about which tools are host-abstracted
- **Effort**: Small — Add one table row and update one prose sentence
- **Risk**: Low — Documentation-only change
- **Breaking Change**: No

## Labels

`documentation`, `correctness`, `captured`

## Source

Discovered during `/ll:audit-docs docs/reference` on 2026-06-08.

---

**Open** | Created: 2026-06-08 | Priority: P4


## Session Log
- `/ll:ready-issue` - 2026-06-08T16:46:18 - `edc88d2f-3f30-4eab-97d7-f4b9dd7d61e7.jsonl`
