---
id: BUG-2381
title: auto-refine-and-implement counts implement-issue-chain terminal arrival as
  implementation success even when the sub-loop did no work
type: BUG
status: done
priority: P2
captured_at: '2026-06-28T00:00:00Z'
discovered_date: '2026-06-28'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- oracle
- verdict
relates_to:
- BUG-2374
- BUG-2380
- BUG-1017
- ENH-2005
---

# BUG-2381: sub-loop terminal arrival is counted as implementation success

## Summary

`auto-refine-and-implement.implement_chain` routes `on_success → record_implemented`
(`scripts/little_loops/loops/auto-refine-and-implement.yaml:105-109`). The
`on_success` verdict fires whenever the `implement-issue-chain` sub-loop reaches
its terminal `done` state — but `done` is reachable by three paths, only one of
which represents real work:

| Path | Meaning |
|---|---|
| `get_passed_issues.on_no → done` | **nothing to do** — no passed issues queued |
| `implement_next.on_no → done` | queue drained (after work) **or** empty |
| normal completion of all queued items | **work done** |

The first path is a "nothing-to-do" exit, yet the parent treats it identically
to real completion and fires `record_implemented`.

In the `2026-06-28T172211` audit run, FEAT-370 traced as: refinement **failed**
(confidence check) → classified `decision_needed` →
`recursive-refine-passed.txt` was **empty** → `get_passed_issues` exited 1 →
`on_no: done`. The parent's `on_success` then fired and logged
"Implemented FEAT-370" for an issue that was never refined, never queued, and
never sent to `ll-auto`.

## Root Cause

- **File**: `scripts/little_loops/loops/auto-refine-and-implement.yaml`
  (`implement_chain.on_success`) and
  `scripts/little_loops/loops/oracles/implement-issue-chain.yaml`
  (`get_passed_issues.on_no`, `implement_next.on_no`, `implement_issue`).
- **Cause**: the FSM routing verdict (`done` reached → `on_success`) is a
  *control-flow* signal, not a *work-happened* signal. The parent has no channel
  telling it whether `ll-auto` actually ran. This is the same class as
  [[BUG-1017]] (sub-loop terminal name not resolved to an outcome) and the
  laundering documented in [[ENH-2005]].

## Expected Behavior

`implement-issue-chain` writes an authoritative ledger of issues it **actually
ran `ll-auto` on** (sentinel artifact, per the audit's Finding-3 recommendation
#2): `${context.run_dir}/${context.caller_prefix}-implemented.txt`, appended in
the `implement_issue` state. `auto-refine-and-implement.finalize` counts that
file as `IMPL`. A "nothing-to-do" terminal arrival writes nothing, so it does not
inflate the implemented count or the verdict. Pairs with [[BUG-2380]], which
stops the parent from writing `*-implemented.txt` on terminal arrival.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` —
  `implement_issue`: append the implemented ID to
  `${context.run_dir}/${context.caller_prefix}-implemented.txt` after the
  `ll-auto`/already-complete branch.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` —
  `record_processed` (renamed in [[BUG-2380]]) no longer writes
  `*-implemented.txt`; `finalize` keeps counting `*-implemented.txt`, now
  populated only by the sub-loop.

### Dependent Files (Context, No Changes)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — reads
  `summary.json`; benefits from the now-honest `IMPL` count.

### Tests
- `scripts/tests/test_builtin_loops.py` — shell-execution regression: run
  `implement_issue` and assert the ID lands in `*-implemented.txt`; run the
  "nothing-to-do" path (`get_passed_issues` with empty passed file) and assert
  `*-implemented.txt` stays empty.

## Acceptance Criteria

- [ ] `implement-issue-chain.implement_issue` appends the implemented ID to
      `<prefix>-implemented.txt`.
- [ ] A `get_passed_issues.on_no → done` (nothing-to-do) terminal arrival
      results in **no** new line in `<prefix>-implemented.txt`.
- [ ] `finalize`'s `IMPL` count equals the number of issues `ll-auto` actually
      ran on (not the number of sub-loop invocations).
- [ ] `ll-loop validate auto-refine-and-implement` and
      `ll-loop validate oracles/implement-issue-chain` pass.

## Impact

- **Priority**: P2 — the `IMPL` counter (and therefore the run verdict) is
  inflated by every nothing-to-do delegation, masking phantom/no-op runs as
  successful.
- **Effort**: Small — one append in the sub-loop + the [[BUG-2380]] parent edit.
- **Risk**: Low.
- **Breaking Change**: No.

## Session Log
- `audit-loop-run` - 2026-06-28 - `audit-sprint-refine-and-implement-2026-06-28.md` (Finding 3)

---

## Status

**Done** | Created: 2026-06-28 | Completed: 2026-06-28 | Priority: P2
