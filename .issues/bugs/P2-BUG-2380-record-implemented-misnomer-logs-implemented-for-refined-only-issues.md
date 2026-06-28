---
id: BUG-2380
title: "record_implemented is a misnomer \u2014 it logs \"Implemented\" and writes\
  \ implemented.txt for issues that were only refined/decomposed, never shipped"
type: BUG
status: done
priority: P2
captured_at: '2026-06-28T00:00:00Z'
discovered_date: '2026-06-28'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- verdict
- naming
relates_to:
- BUG-2374
- BUG-2381
---

# BUG-2380: record_implemented is a misnomer — "Implemented" is logged for refined-only issues

## Summary

`auto-refine-and-implement.yaml`'s `record_implemented` state
(`scripts/little_loops/loops/auto-refine-and-implement.yaml:113`) is the parent
loop's success sink, fired by `implement_chain.on_success`. It:

```yaml
record_implemented:
  action: |
    echo "Implemented ${captured.input.output}"
    echo "${captured.input.output}" >> ${context.run_dir}/auto-refine-and-implement-implemented.txt
```

- ✅ Echoes "Implemented FEAT-NNN" to the run log
- ✅ Appends the **parent's** issue ID to `*-implemented.txt` (the `IMPL` counter)
- ❌ Never transitions issue status (`open → done`)
- ❌ Never produces code, tests, or shipped artifacts
- ❌ Writes the *umbrella* ID, not the IDs `ll-auto` actually ran on

In the `2026-06-28T172211` audit run, all three issues recorded as "implemented"
(FEAT-366/368/370) remained `status: open` afterward — the run only refined them
and decomposed the umbrellas into 10 children. The loop reported implementation
work it did not do.

This is the vocabulary half of the defect. The BUG-2374 fix already introduced a
`*-processed.txt` ledger (exactly the audit's recommended split), but
`record_implemented` still writes the misleading `*-implemented.txt` and emits
the "Implemented" log line, so the rename was left half-done.

## Root Cause

- **File**: `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- **Anchor**: `record_implemented` state (line ~113); `implement_chain.on_success`
  (line ~109)
- **Cause**: the state name and its `*-implemented.txt` ledger conflate "the
  parent finished delegating this issue to the sub-loop" with "this issue was
  implemented." The parent has no evidence `ll-auto` ran — see [[BUG-2381]] for
  why sub-loop terminal arrival is not proof of work.

## Expected Behavior

The parent state records that it **processed** an issue (refined + delegated),
not that it implemented it. The authoritative `*-implemented.txt` ledger — the
one `finalize` counts as `IMPL` — is written by `implement-issue-chain` only when
`ll-auto` actually runs (see [[BUG-2381]]). The parent's log line and state name
reflect refinement/delegation, not shipping.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` —
  rename `record_implemented` → `record_processed`; update
  `implement_chain.on_success` target; change the log line to honest wording
  ("Processed …"); record to `*-processed.txt` for dedup/accounting rather than
  writing `*-implemented.txt` directly (the sub-loop owns that ledger per
  [[BUG-2381]]).

### Dependent Files (Context, No Changes)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — delegates to
  this loop; reads `summary.json`/`subloop_outcome_*`, unaffected by the rename.

### Tests
- `scripts/tests/test_builtin_loops.py` — assert the renamed state exists, that
  the parent no longer writes `*-implemented.txt`, and that `ll-loop validate`
  still passes.

## Acceptance Criteria

- [ ] `record_implemented` is renamed to `record_processed`; `implement_chain.on_success`
      points to it; no dangling references to the old name remain.
- [ ] The parent state's log line no longer claims "Implemented" for issues that
      were only refined/decomposed.
- [ ] `finalize`'s `IMPL` count reflects only issues `ll-auto` actually ran on
      (depends on [[BUG-2381]]).
- [ ] `ll-loop validate auto-refine-and-implement` passes.

## Impact

- **Priority**: P2 — the loop reports implementation work it did not perform,
  misleading sprint health and any downstream consumer of `*-implemented.txt`.
- **Effort**: Small — YAML rename + log-line edit, co-implemented with [[BUG-2381]].
- **Risk**: Low.
- **Breaking Change**: No (internal artifact filenames; `summary.json` schema
  unchanged).

## Session Log
- `audit-loop-run` - 2026-06-28 - `audit-sprint-refine-and-implement-2026-06-28.md` (Finding 2)

---

## Status

**Done** | Created: 2026-06-28 | Completed: 2026-06-28 | Priority: P2
