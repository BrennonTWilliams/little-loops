---
id: BUG-2006
title: 'rn-implement: converged-stalled + no-children dead-ends to silent skip instead
  of defer/block with reason'
type: BUG
priority: P2
status: done
captured_at: '2026-06-07T00:00:00Z'
completed_at: '2026-06-07T22:14:20Z'
discovered_date: '2026-06-07'
discovered_by: audit-loop-run
relates_to:
- BUG-1985
- BUG-1230
- ENH-1977
labels:
- rn-implement
- rn-remediate
- rn-decompose
- loop-defect
- orchestration
---

# BUG-2006: rn-implement converged-stalled + no-children dead-ends to silent skip

## Summary

When an issue cannot be made ready by remediation (rn-remediate returns
`CONVERGED_STALLED → NEEDS_DECOMPOSE`) **and** decomposition declines to split it
(rn-decompose returns `NO_CHILDREN`), `rn-implement` routes
`route_dec_no_children → skip_issue`. The issue is appended to `skipped.txt` with no
reason and no status change. This is indistinguishable from a deliberate skip, and it
silently drops work that is actually **blocked on a dependency** — the honest terminal
state for these issues is `deferred`/`blocked`, not "skipped".

In run `rn-implement-20260607T122052`, this path consumed 2 of 6 processed issues
(FEAT-2001, FEAT-2002) — 33% of the run produced no output and no actionable signal.

## Steps to Reproduce

1. Run `ll-loop run rn-implement` on a backlog containing issues with `blocked_by` frontmatter
   dependencies (e.g., FEAT-2001, FEAT-2002 — children of FEAT-1902 under EPIC-1867)
2. Observe an issue enter remediation — `rn-remediate` runs but exits `CONVERGED_STALLED`
   (scores do not move because the uncertainty is structural, not missing prose detail)
3. Observe decomposition invoked — `rn-decompose` declines with `NO_CHILDREN` (qualitative
   guard treats the issue as atomic)
4. Check `${run_dir}/skipped.txt` — the issue ID is listed with no reason string
5. Check the issue's `status:` frontmatter — unchanged (`open`), not `blocked` or `deferred`

## Current Behavior

For both FEAT-2001 and FEAT-2002 the chain was identical:

```
dequeue → run_remediation (rn-remediate)
  diagnose            → WIRE
  wire → refine                       ← remediation DID run
  check_convergence   → CONVERGED_STALLED   ← zero score delta
  emit_needs_decompose
→ run_decomposition (rn-decompose)
  size-review         → NO_CHILDREN  ← qualitative-skip guard declined to split
→ route_dec_no_children → skip_issue → [SKIP]   ← dead-end
```

Convergence evidence (zero movement across remediation passes):
- FEAT-2001: confidence 83→83, outcome 73→73 (needs 85 / 75)
- FEAT-2002: confidence 70→70, outcome 79→79 (outcome passes; confidence 15 short)

Root reason the scores didn't move: the blocker is **outcome/dependency uncertainty**,
not missing issue detail. The size-review output for FEAT-2002 states the implementation
details "can't be finalized until FEAT-2001 merges." Refining prose cannot raise
confidence when the uncertainty is structural. Both issues carry `blocked_by` dependencies
in their frontmatter (children of FEAT-1902 under EPIC-1867).

## Expected Behavior

When an issue exits remediation with `CONVERGED_STALLED` and decomposition returns `NO_CHILDREN`,
`rn-implement` should route to a defer/block state instead of `skip_issue`:

- The issue's `status` frontmatter is set to `blocked` or `deferred`
- A human-readable reason is written to a `deferred.txt` run artifact (not `skipped.txt`)
- The `report` summary distinguishes `deferred` from `skipped` counts
- A genuinely atomic issue that decompose declines for non-stall reasons still routes to
  `skip_issue` (no regression on the happy path)

## Motivation

1. **Silent data loss**: `skip_issue` writes only to `skipped.txt` with no reason. There
   is no way to tell from the run summary whether an issue was skipped because it was
   genuinely un-actionable or because the loop ran out of automated moves.
2. **Wrong terminal state**: these issues are blocked on a dependency. The correct outcome
   is `status: blocked` (or `deferred`) on the issue file with a dependency reason — making
   them re-surface naturally once the blocker merges, instead of being invisibly dropped.
3. **No human signal**: a deliberate skip and a "stuck, needs attention" skip are merged
   into one bucket, so an operator scanning the summary has no way to triage.

## Root Cause

`route_dec_no_children.on_yes` points to `skip_issue`. There is no branch that
distinguishes "decomposition genuinely found this atomic and ready-enough" from
"remediation stalled and we couldn't break it down." The loop already has a `mark_blocked`
state (writes `blocked.txt`, used by `route_rem_manual_review` on `MANUAL_REVIEW_NEEDED`),
but it is not wired into the no-children-after-stall path.

## Proposed Solution

When `NO_CHILDREN` is reached **after** a remediation stall (as opposed to a clean
decompose decline), route to a defer/block state that records the dependency reason and
sets the issue's `status` frontmatter, rather than to `skip_issue`.

Two viable approaches:

### Option A — distinguish the stall-origin in the outcome token (CHOSEN)
Have rn-remediate's **stall paths only** (convergence `CONVERGED_STALLED` and budget-exhausted)
emit a distinct token `STALLED_NEEDS_DECOMPOSE`, while the diagnose-`DECOMPOSE` path keeps emitting
plain `NEEDS_DECOMPOSE`. The parent then routes after `NO_CHILDREN` based on which token it saw in
`rem_outcome`:

In `rn-remediate.yaml`, add a stall-specific emitter and point the two stall paths at it:

```yaml
# route_conv_manual_review.on_no  → emit_stalled_needs_decompose (was emit_needs_decompose)
# check_remediation_budget.on_no  → emit_stalled_needs_decompose (was emit_needs_decompose)
# route_d_refine.on_no            → emit_needs_decompose  (UNCHANGED — genuine "too big")

emit_stalled_needs_decompose:
  action_type: shell
  action: |
    echo "STALLED_NEEDS_DECOMPOSE" > "${context.run_dir}/subloop_outcome_${context.issue_id}.txt"
  next: failed
```

The parent's `route_rem_decompose` must match **both** tokens (so a stall still triggers a
decomposition attempt):

```yaml
route_rem_decompose:
  evaluate:
    type: output_contains
    pattern: NEEDS_DECOMPOSE          # substring — also matches STALLED_NEEDS_DECOMPOSE
    source: ${captured.rem_outcome.output}
  on_yes: run_decomposition
  ...
```

Then disambiguate after `NO_CHILDREN` using the retained `rem_outcome`:

```yaml
route_dec_no_children:
  evaluate:
    type: output_contains
    pattern: NO_CHILDREN
    source: ${captured.dec_outcome.output}
  on_yes: route_dec_stalled_origin    # new: was this NO_CHILDREN preceded by a stall?
  on_no: route_dec_rate_limited
  on_error: record_failure

route_dec_stalled_origin:
  evaluate:
    type: output_contains
    pattern: STALLED_NEEDS_DECOMPOSE   # only true for convergence/budget stalls
    source: ${captured.rem_outcome.output}
  on_yes: mark_deferred         # stall → defer with reason + set status
  on_no: skip_issue             # plain NEEDS_DECOMPOSE (genuinely large, atomic) → skip is fine
  on_error: record_failure
```

Note the substring-matching subtlety: `route_rem_decompose` matches `NEEDS_DECOMPOSE` as a substring
of `STALLED_NEEDS_DECOMPOSE`, so both tokens correctly trigger a decomposition attempt; only
`route_dec_stalled_origin` distinguishes them, by matching the more specific `STALLED_NEEDS_DECOMPOSE`.

### Option B — always defer on no-children-after-stall (REJECTED — false premise)
Option B assumes *"`NEEDS_DECOMPOSE` is only emitted by rn-remediate's stall path, so every
`NO_CHILDREN` is by definition a stalled issue."* **That premise is false.** In `rn-remediate.yaml`,
`emit_needs_decompose` is reached from **three** distinct paths:

1. `route_d_refine` on_no — `diagnose` returned `DECOMPOSE` because `change_surface ≥ 15`. This is
   a *legitimate "this issue is too large, split it"* signal — **not** a stall.
2. `route_conv_manual_review` on_no — convergence detected `CONVERGED_STALLED` (a genuine stall).
3. `check_remediation_budget` on_no — remediation budget exhausted (stall-adjacent).

Under Option B, a genuinely-large-but-indivisible issue arriving via path 1 would be mislabeled
`deferred` with the reason *"likely blocked on a dependency"* — which is simply wrong, and worse
than the current silent skip because it asserts a false cause. Option B is therefore **rejected**;
the loop must distinguish the stall origin, which is exactly what Option A does. (`mark_deferred`
shell action below is shared by both options — the difference is purely how it is routed to.)

```yaml
# Shared mark_deferred state (target of Option A's route_dec_stalled_origin.on_yes):
mark_deferred:
  action: |
    ID="${captured.input.output}"
    REASON="remediation stalled (scores did not converge across passes) and decomposition \
declined to split; likely blocked on a dependency or otherwise un-actionable by automation"
    echo "$ID  $REASON" >> "${captured.run_dir.output}/deferred.txt"
    # Set issue status so it re-surfaces when the blocker clears
    ll-issues set-status "$ID" deferred 2>/dev/null || true
    echo "[DEFERRED] $ID — $REASON"
  action_type: shell
  next: dequeue_next
```

Update the `report` state to count and surface `deferred` alongside `skipped`.

**Decision: implement Option A.** It correctly routes path-1 (diagnose-`DECOMPOSE` → `NO_CHILDREN`,
a genuinely atomic-but-large issue) to `skip_issue`, and only paths 2/3 (true stalls) to
`mark_deferred`. The cost is one extra token value in `rn-remediate` and one extra routing state in
`rn-implement` — cheap relative to mislabeling issue causes.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — add `mark_deferred` and `route_dec_stalled_origin`
  states; rewire `route_dec_no_children.on_yes → route_dec_stalled_origin`; confirm
  `route_rem_decompose` still matches the `NEEDS_DECOMPOSE` substring (it does); update `report` to
  tally deferred
- `scripts/little_loops/loops/rn-remediate.yaml` — add `emit_stalled_needs_decompose`; repoint
  `route_conv_manual_review.on_no` and `check_remediation_budget.on_no` to it (leave
  `route_d_refine.on_no → emit_needs_decompose` unchanged)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` / loop docs — document deferred outcome and the
  two-token stall distinction

### Dependent Files (Callers/Importers)
- TBD — use `grep -r "rn-implement" loops/` to confirm no other loops invoke `rn-implement`
  as a sub-loop that read `skipped.txt` and would also need to read `deferred.txt`

### Similar Patterns
- `mark_blocked` state in `rn-implement.yaml` — already wired for `MANUAL_REVIEW_NEEDED`;
  `mark_deferred` should follow the same pattern

### Tests
- TBD — verify with `ll-loop run rn-implement` on a backlog containing blocked issues

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document deferred outcome behavior

### Configuration
- N/A

## Acceptance Criteria

- An issue that hits `CONVERGED_STALLED → NEEDS_DECOMPOSE → NO_CHILDREN` is recorded as
  `deferred` (not `skipped`), with a human-readable dependency reason in the run artifacts
- The issue's `status` frontmatter is updated so it re-enters the backlog naturally once
  its blocker is resolved
- The `report` summary distinguishes `deferred` from `skipped` counts
- A genuinely atomic, ready-enough issue that decompose declines for non-stall reasons
  still routes to `skip_issue` (no regression)

## Implementation Steps

Implement **Option A** (Option B is rejected — see Proposed Solution for the false-premise analysis):

1. In `rn-remediate.yaml`: add `emit_stalled_needs_decompose` (writes `STALLED_NEEDS_DECOMPOSE`,
   `next: failed`); repoint `route_conv_manual_review.on_no` and `check_remediation_budget.on_no`
   to it. Leave `route_d_refine.on_no → emit_needs_decompose` unchanged (genuine "too big" signal).
2. In `rn-implement.yaml`: confirm `route_rem_decompose` matches `NEEDS_DECOMPOSE` as a substring
   (so `STALLED_NEEDS_DECOMPOSE` still triggers `run_decomposition`).
3. Add `route_dec_stalled_origin` state (matches `STALLED_NEEDS_DECOMPOSE` against
   `${captured.rem_outcome.output}`); rewire `route_dec_no_children.on_yes → route_dec_stalled_origin`,
   with `on_yes → mark_deferred` and `on_no → skip_issue`.
4. Add `mark_deferred` state following the existing `mark_blocked` pattern; write `"$ID  $REASON"`
   to `${captured.run_dir.output}/deferred.txt` and call `ll-issues set-status "$ID" deferred`.
5. Update the `report` state to count and surface `deferred` alongside `skipped`.
6. Run `ll-loop validate rn-implement` and `ll-loop validate rn-remediate` to confirm FSM integrity
   (no dead-end / laundering violations introduced).
7. Run `ll-loop run rn-implement` on a test backlog containing (a) a dependency-blocked issue and
   (b) a genuinely-large atomic issue, to verify the deferred path and the no-regression skip path.

## Impact

- **Priority**: P2 — 33% of issues in the audit run were silently dropped; operators cannot
  distinguish stuck issues from deliberate skips
- **Effort**: Small — YAML wiring change in `rn-implement.yaml`; no new Python code required
- **Risk**: Low — adds a new routing path; does not alter any existing state transitions
- **Breaking Change**: No

## Notes

Discovered by `/ll:audit-loop-run rn-implement` on run `2026-06-07T172052`. Companion to
BUG-2003 (ID type mismatch), BUG-2004 (visited.txt double-write), ENH-2005 (verdict
laundering annotation) from the same audit.

## Resolution

**Implemented Option A** (two-token stall distinction) as specified.

`rn-remediate.yaml`:
- Added `emit_stalled_needs_decompose` (writes `STALLED_NEEDS_DECOMPOSE`, `next: failed`).
- Repointed the two stall paths to it: `route_conv_manual_review.on_no` and
  `check_remediation_budget.on_no`. Left `route_d_refine.on_no → emit_needs_decompose`
  (genuine "too large") and `route_conv_manual_review.on_error → emit_needs_decompose`
  (a pattern-match error is not evidence of a stall) unchanged.

`rn-implement.yaml`:
- Rewired `route_dec_no_children.on_yes → route_dec_stalled_origin` (new state) which
  matches `STALLED_NEEDS_DECOMPOSE` against the retained `${captured.rem_outcome.output}`:
  `on_yes → mark_deferred`, `on_no → skip_issue` (no regression on the atomic/too-large path).
- Added `mark_deferred` (follows the `mark_blocked` pattern): writes `"$ID  $REASON"` to
  `deferred.txt` and calls `ll-issues set-status "$ID" deferred`.
- `init` now seeds `deferred.txt`; `report` tallies and surfaces `deferred` in both
  `summary.json` and the human-readable line.
- `route_rem_decompose` confirmed to match `NEEDS_DECOMPOSE` as a substring, so
  `STALLED_NEEDS_DECOMPOSE` still triggers a decomposition attempt.

Docs: `docs/guides/LOOPS_GUIDE.md` updated (artifacts table, FSM flow, two-token stall note).

Tests: added `TestDeferredOnStall` (rn-implement) and stall-token assertions (rn-remediate);
updated the state-count ceiling (26→28) and the convergence/budget routing assertions.
`ll-loop validate` passes for both loops; 873 loop tests pass.

## Status

**Done** | Created: 2026-06-07 | Completed: 2026-06-07 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-06-07T20:49:00 - `8e6e4e26-f150-4e10-860a-db222eaca46f.jsonl`
