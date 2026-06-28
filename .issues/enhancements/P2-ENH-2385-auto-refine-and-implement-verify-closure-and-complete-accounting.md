---
id: ENH-2385
title: auto-refine-and-implement must verify terminal closure and account for every
  scoped issue (close the gap between "refine" and "implement and close")
type: ENH
status: done
priority: P2
captured_at: '2026-06-28T00:00:00Z'
discovered_date: '2026-06-28'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- verdict
- closure
relates_to:
- BUG-2380
- BUG-2381
- BUG-2375
---

# ENH-2385: verify terminal closure + complete per-issue accounting

## Summary

`sprint-refine-and-implement` / `auto-refine-and-implement` are named for
implementing and closing issues. The machinery to do so already exists —
`ll-auto --only` implements and moves issues to `.issues/completed/`
(`complete_issue_lifecycle`), and `recursive-refine.enqueue_children` git-mv's
decomposed umbrellas into `completed/`. But the loop never **verifies** closure
and silently drops one exit path, so it cannot honestly claim "implement and
close":

1. **No closure verification.** `implement_issue` (post BUG-2381) counts
   `ll-auto` exit 0 as implemented — a proxy. Nothing asserts the issue actually
   reached `completed/`/status `done`.
2. **Silent go-no-go drop (Gap C).** `implement-issue-chain.go_no_go` routes
   `on_no → implement_next` with no record: a passed issue rejected by go-no-go
   is neither implemented, closed, nor recorded as skipped — an invisible loss.
3. **Verdict ignores closure.** `finalize` counts an `*-implemented.txt` ledger,
   not the ground-truth set of issues that actually reached `completed/` this
   run, and has no `not-closed` notion.

(Note: `decision_needed` is NOT a silent drop — `recursive-refine.check_decision_needed`
already records to both `skipped-decision.txt` and the shared `skipped.txt`, so
those issues are parked-with-reason and deduped. The audit's Finding 4 symptom
was the BUG-2381 terminal-arrival defect, now fixed.)

## Expected Behavior

- **Ground-truth closure**: snapshot `.issues/completed/` IDs at `init`; at
  `finalize`, diff to count issues that reached `completed/` during the run
  (captures both `ll-auto` leaf closures AND decomposition closures).
- **Per-issue verification**: `implement_issue` checks `completed/` after
  `ll-auto` and records the ID in `*-implemented.txt` only when actually closed.
  It re-exits with `ll-auto`'s real exit code so the rate-limit fragment's 429
  detection (which requires `exit_code != 0`) still fires.
- **not-closed derived at finalize**: `NOT_CLOSED = processed − completed`
  (computed from ground truth), so a rate-limit retry that eventually closes can
  never double-count. Processed issues are already deduped, so a not-closed issue
  is parked and drain-to-empty terminates.
- **No silent drops**: `go_no_go.on_no` records the rejected ID (with reason) to
  the skip ledger before continuing.
- **Honest verdict + drain-to-empty accounting**: `finalize` emits
  `closed` / `not_closed` / `skipped` / `errored` in `summary.json` so every
  scoped issue ends as closed or parked-with-reason; the verdict reflects real
  closures, not a proxy.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `init`
  (snapshot completed baseline + clear new ledgers); `finalize` (ground-truth
  CLOSED, NOT_CLOSED, richer summary.json + verdict).
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` —
  `implement_issue` (verify closure → implemented vs not-closed);
  `go_no_go.on_no` → new `record_rejected` state that logs the skip.

### Tests
- `scripts/tests/test_builtin_loops.py` — ground-truth finalize verdict table;
  implement_issue not-closed path; go-no-go rejection recording; init baseline
  snapshot.

## Acceptance Criteria

- [x] `finalize`'s closed count is derived from the `.issues/completed/` diff
      (ground truth), not the `*-implemented.txt` proxy alone.
- [x] Issues that `ll-auto` ran on but did NOT close are counted as `not_closed`
      (derived `processed − completed` at finalize), not as closed.
- [x] `go_no_go.on_no` routes to `record_rejected`, which records the rejected
      issue to the skip ledger (no silent drop).
- [x] `summary.json` reports `closed`, `not_closed`, `skipped`, `errored`.
- [x] `implement_issue` re-exits with `ll-auto`'s exit code (preserves 429
      detection — a regression introduced by the BUG-2381 fix).
- [x] `ll-loop validate` passes for both loops; tests green (1642 passing).

## Impact

- **Priority**: P2 — makes the loop's name truthful and its verdict trustworthy.
- **Effort**: Medium — YAML across two loop files + finalize rewrite + tests.
- **Risk**: Low-Medium — verdict semantics change; downstream only echoes the
  verdict string.
- **Breaking Change**: summary.json schema changed — `implemented` →
  `closed`, added `not_closed`. Only consumer that parses by key is the
  `audit-loop-run` skill (generalized to recognize `closed`); the sub-loop
  sidecar (`sprint-refine-and-implement`) just `cat`s the file.

## Session Log
- `audit-loop-run` - 2026-06-28 - `audit-sprint-refine-and-implement-2026-06-28.md` (Findings 2, 3, 8)

---

## Status

**Done** | Created: 2026-06-28 | Completed: 2026-06-28 | Priority: P2
