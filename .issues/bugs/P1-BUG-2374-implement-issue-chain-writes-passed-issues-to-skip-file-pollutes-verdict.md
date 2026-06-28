---
id: BUG-2374
title: implement-issue-chain writes passed issues to the caller skip file, polluting
  the auto-refine-and-implement verdict counter
type: BUG
status: done
priority: P1
captured_at: '2026-06-28T00:00:00Z'
discovered_date: '2026-06-28'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- oracle
- verdict
relates_to:
- BUG-2347
- ENH-2097
---

# BUG-2374: implement-issue-chain writes passed issues to the caller skip file, polluting the verdict counter

## Summary

The `implement-issue-chain` oracle (`oracles/implement-issue-chain.yaml`,
`get_passed_issues`, line 37) appends every **passed** issue ID to the caller's
`*-skipped.txt` file:

```bash
echo "$PASSED" >> "$SKIP_FILE"
echo "$PASSED" > "$IMPL_QUEUE"
```

`auto-refine-and-implement.finalize` counts `*-skipped.txt` as `SKIP`. Because
passed issues are written to *both* the implemented set and the skipped set, any
run that implements at least one issue computes `IMPL>0 && SKIP>0`, which falls
into the `partial` branch of the verdict logic — never `success`. The verdict
metric is therefore unusable: a fully successful run is permanently misreported
as `partial`.

Confirmed in the `2026-06-28` audit of `sprint-refine-and-implement` (run
`2026-06-28T172211`): FEAT-366/368/370 were all refined AND implemented, yet
`summary.json` reported `{"verdict":"partial","implemented":3,"skipped":3}` —
the three "skipped" IDs are byte-identical to the three "implemented" IDs.

## Why the obvious one-line fix is wrong

Deleting `echo "$PASSED" >> "$SKIP_FILE"` with no replacement regresses
**deduplication**. `auto-refine-and-implement.get_next_issue` consults the skip
file to avoid re-selecting an already-handled issue. For a *cleanly implemented*
issue this is redundant — `SprintManager.load_or_resolve` filters to active
statuses `{open,in_progress,blocked}` (`sprint.py:15,325`), so a `done` issue
drops out naturally. But an issue that **passes refinement yet never reaches
`done`** — go-no-go rejects it (`implement-issue-chain.yaml:69` `on_no:
implement_next` drops it silently) or `ll-auto` fails — stays active. The skip-file
entry is currently the *only* thing stopping `get_next_issue` from re-selecting,
re-refining, and re-queuing it indefinitely (bounded only by `max_steps` /
recursive-refine's visited set).

## Root Cause

- **File**: `scripts/little_loops/loops/oracles/implement-issue-chain.yaml`
- **Anchor**: `get_passed_issues` state (line ~37)
- **Cause**: a single file (`*-skipped.txt`) serves **two** distinct concerns —
  (a) dedup ("don't re-select this issue") and (b) verdict accounting ("this
  issue was not implemented"). Passed issues legitimately need (a) but must be
  excluded from (b).

## Expected Behavior

Decouple the two concerns. Passed issues are recorded in a **dedup-only**
`*-processed.txt` file (consulted by `get_next_issue`) and proceed to the impl
queue; they are NOT written to `*-skipped.txt`. `*-skipped.txt` holds only
genuine refinement-skips, so the `finalize` verdict counter is accurate.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` —
  `get_passed_issues`: write passed IDs to `${context.caller_prefix}-processed.txt`,
  not `-skipped.txt`.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` —
  `init`: also `rm -f` the `-processed.txt` file; `get_next_issue`: union both
  `-skipped.txt` and `-processed.txt` into the dedup set (Python scope path and
  bash backlog path).

### Dependent Files (Context, No Changes)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — delegates to
  `auto-refine-and-implement`; shares its run_dir/prefix, so no separate change.
- `scripts/little_loops/sprint.py` — `load_or_resolve` active-status filter
  (line 15, 325) is the redundant dedup that makes the happy-path safe.

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestImplementIssueChainOracle`
  (line ~6078): add a shell-execution regression test that runs the
  `get_passed_issues` action against a populated `recursive-refine-passed.txt`
  and asserts the passed IDs land in `*-processed.txt` and the impl queue, and
  that `*-skipped.txt` stays empty.

## Acceptance Criteria

- [ ] Given a non-empty `recursive-refine-passed.txt` and empty
      `recursive-refine-skipped.txt`, `get_passed_issues` writes the passed IDs
      to `<prefix>-impl-queue.txt` and `<prefix>-processed.txt`, and leaves
      `<prefix>-skipped.txt` empty.
- [ ] `auto-refine-and-implement.get_next_issue` does not re-select an issue
      present in `-processed.txt` (dedup preserved).
- [ ] A run that implements N issues with zero refinement-skips and zero errors
      reports `verdict=success` (not `partial`).
- [ ] `ll-loop validate auto-refine-and-implement` and
      `ll-loop validate oracles/implement-issue-chain` pass.

## Impact

- **Priority**: P1 — the verdict metric for `auto-refine-and-implement` /
  `sprint-refine-and-implement` is unusable until fixed; every successful run
  is mislabeled `partial`.
- **Effort**: Small — YAML edits across two loop files + one regression test.
- **Risk**: Low — dedup is preserved via the new `-processed.txt` channel; only
  the skip-accounting semantics change.
- **Breaking Change**: No.

## Session Log
- `audit-loop-run` - 2026-06-28 - `.loops/audits/2026-06-28-sprint-refine-and-implement-audit.md`

---

## Status

**Done** | Created: 2026-06-28 | Completed: 2026-06-28 | Priority: P1
