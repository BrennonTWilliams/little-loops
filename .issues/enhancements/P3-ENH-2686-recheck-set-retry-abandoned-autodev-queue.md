---
id: ENH-2686
title: recheck_set should retry an abandoned autodev-queue residual, not just newly-detected
  descendants
type: ENH
priority: P3
status: done
captured_at: '2026-07-19T00:06:49Z'
completed_at: '2026-07-19T00:26:55Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
decision_needed: false
confidence_score: 98
outcome_confidence: 87
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2686: recheck_set should retry an abandoned autodev-queue residual, not just newly-detected descendants

## Summary

`recheck_set` in `auto-refine-and-implement.yaml` only re-dispatches issue IDs
that are *new* relative to `auto-refine-and-implement-dispatched.txt` (a diff
via `comm -23`). That ledger is seeded with the **entire initial batch** up
front, in the `issue_set` state, before `delegate` ever runs
(`auto-refine-and-implement.yaml:153-154`). If `autodev`'s sub-loop run times
out or hits `max_steps` mid-drain and leaves issues sitting unprocessed in
`${run_dir}/autodev-queue.txt` (the scenario ENH-2657 made visible via the
`abandoned` summary.json field and `incomplete-abandoned` verdict), those IDs
are already present in `dispatched.txt` from the initial seed. `recheck_set`'s
diff therefore permanently excludes them — they can never be re-dispatched
within the same run, even though nothing actually happened to them. The run
ends up correctly labeled `incomplete-abandoned` (thanks to ENH-2657), but
recovery requires the operator to notice and manually re-run the whole scope.

## Current Behavior

- `issue_set` seeds `auto-refine-and-implement-dispatched.txt` with the full
  resolved issue list before the first `delegate` call
  (`auto-refine-and-implement.yaml:151-154`).
- `recheck_set` re-resolves the EPIC's descendant set and diffs it against
  `dispatched.txt` via `comm -23` to find genuinely new descendants
  (`auto-refine-and-implement.yaml:298-336`); anything already in
  `dispatched.txt` — including issues abandoned mid-drain — is invisible to
  this diff and is never re-added to the re-dispatch batch.
- `finalize` (ENH-2657) separately reads the residual `autodev-queue.txt` at
  the very end of the run, computes `ABANDONED`, and routes the run to the
  non-green `incomplete-abandoned` verdict — but it does not feed those IDs
  back into `recheck_set` for another dispatch cycle. Detection and recovery
  are decoupled; only detection exists today.
- Net effect: an abandoned residual queue is correctly flagged in the final
  summary but is never retried automatically, even though `recheck_set`'s
  existing re-dispatch cycle (capped at 5, `auto-refine-and-implement.yaml:294`)
  would have budget to attempt it.

## Expected Behavior

- `recheck_set` should also read `${run_dir}/autodev-queue.txt` (the same file
  ENH-2657's `finalize` step already parses) and union any non-blank residual
  IDs into the re-dispatch batch alongside newly-detected descendants, instead
  of relying solely on the `dispatched.txt` diff.
- A residual ID that gets folded back into a re-dispatch batch should not
  double-count against the existing `PARKED_RATE`/`abandoned` bookkeeping in
  `finalize` once it is actually resolved in a later cycle (drop it from the
  final abandoned set the same way already-closed IDs are excluded via the
  `closed-now-union` subtraction).
- Still bounded by the existing 5-cycle re-dispatch cap and the parent's
  clamped child timeout — no new runaway-guard machinery is required, this
  reuses infrastructure that already exists for both the cap and the
  wall-clock budget.
- An autodev run that drains its queue cleanly (no residual) is unaffected —
  this only changes behavior when `autodev-queue.txt` is non-empty at the time
  `recheck_set` runs.

## Motivation

ENH-2657 closed the *visibility* half of this problem (an abandoned mid-drain
queue no longer renders as a false green `done`), but left recovery as a
manual operator step ("re-run to drain the remainder", per its own AC
language). Since `recheck_set` already has a bounded re-dispatch mechanism
built for exactly this kind of "there's more work, send it back through
delegate" flow, extending it to also pick up the abandoned residual — rather
than only new descendants — turns a detected failure into a self-healing one
within the same run, with no new safety machinery needed.

## Proposed Solution

In `recheck_set`'s action (`auto-refine-and-implement.yaml:298-336`), after
computing `NEW` (newly-detected descendants not in `dispatched.txt`), also
read `${RUN_DIR}/autodev-queue.txt` if present and non-empty, and union its
IDs into the re-dispatch batch:

```sh
RESIDUAL=$(cat "$RUN_DIR/autodev-queue.txt" 2>/dev/null | grep -v '^[[:space:]]*$' || true)
COMBINED=$(printf '%s\n%s\n' "$NEW" "$RESIDUAL" | grep -v '^[[:space:]]*$' | sort -u)
if [ -z "$COMBINED" ]; then
  exit 1
fi
# ... existing recheck-count / dispatched.txt bookkeeping, using $COMBINED
```

`RESIDUAL` IDs were already added to `dispatched.txt` during the initial seed
(or a prior recheck cycle), so they must not be re-appended to `dispatched.txt`
a second time in a way that breaks the `comm -23` dedup for genuinely-new
descendants in later cycles — only append IDs not already present.

## Related Key Documentation

- ENH-2657 (`.issues/enhancements/P2-ENH-2657-detect-abandoned-autodev-queue-in-finalize.md`)
  — the detection half this builds on.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `issue_set`
  (dispatched-ledger seed), `delegate`, `recheck_set`, `finalize`.
- `scripts/little_loops/loops/autodev.yaml` — `autodev-queue.txt` drain/seed
  semantics.

## Impact

- **Priority justification (P3)**: narrow, additive fix to an already-bounded
  loop; only triggers on the (uncommon) mid-drain timeout/max_steps case, not
  the common path.
- **Effort**: small — reuses the residual-queue read ENH-2657 already
  introduced and the existing 5-cycle cap; no new guard infrastructure.
- **Risk**: low — a no-op when `autodev-queue.txt` is empty (the normal case).

## Status

Open — captured from a conversation investigating whether a proposed
verdict-aware `delegate` routing fix (subloop_outcome sidecar) was still worth
building. Conclusion: the generic verdict-laundering framing was largely
already mitigated (`finalize` independently reconstructs ground truth; the
5-cycle cap already bounds oscillation), but this narrower abandoned-residual
retry gap remained genuinely open.

---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-19
- **Status**: Completed

### Changes Made
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (`recheck_set`):
  after computing `NEW` (newly-detected descendants), also read
  `$RUN_DIR/autodev-queue.txt` for any non-blank residual IDs left by an
  abandoned mid-drain `autodev` sub-loop (ENH-2657's detection signal), union
  them into `COMBINED`, and re-dispatch that combined batch. Only IDs not
  already present in `dispatched.txt` are appended to it (via `comm -23`), so
  residual IDs — already seeded there from the initial batch — are not
  double-appended, preserving `comm -23` dedup in later cycles and
  `finalize`'s `PARKED_RATE` denominator.
- `scripts/tests/test_builtin_loops.py`: added
  `test_recheck_set_folds_back_abandoned_residual` (residual ID is
  re-dispatched, not double-appended to `dispatched.txt`) and
  `test_recheck_set_no_residual_no_new_exits` (a clean drain still exits 1 →
  `verify`, unaffected by this change).

No change was needed in `finalize`'s `ABANDONED` bookkeeping: `autodev-queue.txt`
is re-seeded fresh by `autodev`'s `init` state on every `delegate` re-entry, and
`dequeue_next` pops an ID off the queue file the moment it starts processing —
so a residual ID that resolves (closes or parks) in a later re-dispatch cycle
is already absent from the queue file by the time `finalize` reads it, with no
extra subtraction required.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 15422 passed, 38 skipped;
  1 pre-existing unrelated failure in
  `TestRefineToReadyIssueSubLoop::test_context_fallbacks_match_selector_defaults`,
  confirmed present on `main` before this change via `git stash`)
- Lint: PASS (`ruff check scripts/`)
- Types: PASS (`python -m mypy scripts/little_loops/`)
- Loop validation: PASS (`ll-loop validate auto-refine-and-implement`)

## Session Log
- `/ll:manage-issue` - 2026-07-19T00:26:21Z - `247eb738-9347-42db-8dda-e921e7abb69e.jsonl`
- `/ll:ready-issue` - 2026-07-19T00:16:32 - `123f26d8-1adb-4b93-a855-7cc24d596b38.jsonl`
- `/ll:capture-issue` - 2026-07-19T00:06:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/131d616b-8bc8-4181-ba3e-85addbd0ab47.jsonl`
- `/ll:confidence-check` - 2026-07-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07318bbe-02cd-47aa-b2ec-75cb18452d3e.jsonl`
