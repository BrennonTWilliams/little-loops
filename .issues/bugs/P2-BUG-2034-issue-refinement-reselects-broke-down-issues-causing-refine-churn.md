---
id: BUG-2034
type: BUG
priority: P2
status: open
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
relates_to:
  - BUG-2035
  - ENH-2038
---

# BUG-2034: issue-refinement re-selects broke-down issues, causing expensive refine churn

## Summary

When `refine-to-ready-issue` cannot lift an issue above its readiness/outcome
thresholds, it routes through `breakdown_issue` → `write_broke_down` → the
**`done`** terminal. The FSM runner maps a child terminal literally named `done`
to the parent's `on_yes` (`fsm/executor.py:608-610`), so the parent
`issue-refinement` treats the broken-down issue as a **success** and never
skip-lists it. Because scores remain below threshold, `ll-issues next-action`
re-emits `NEEDS_REFINE <id>` on the next cycle — repeating an expensive
`--full-rewrite` until `refine_cap` (5) is exhausted. The `refine-broke-down`
signal file already exists for this purpose but `issue-refinement` never reads it.

## Steps to Reproduce

1. Run `issue-refinement` on a project where at least one issue will be broken
   down by `refine-to-ready-issue` (scope too large / outcome unreachable).
2. Observe `refine-to-ready-issue` reach the `done` terminal and write `1` to
   `${context.run_dir}/refine-broke-down`.
3. Observe `issue-refinement` route the parent `on_yes` path (terminal == `done`)
   to `check_commit` — the issue is never skip-listed.
4. Observe `ll-issues next-action` re-emit `NEEDS_REFINE <id>` for the same issue
   (scores remain below threshold after breakdown).
5. Watch `issue-refinement.evaluate` re-select the issue and repeat the expensive
   `--full-rewrite` pass. Repeats until `refine_cap` (5) is exhausted.

Confirmed in `.loops/runs/rn-build-20260608T181251/`: FEAT-032 was re-processed
in iter-9, iter-10, and iter-11 (killed mid-third pass), with `outcome_confidence`
regressing 71→68 across passes.

## Current Behavior

1. `refine-to-ready-issue` breaks down an issue (scope too large / outcome
   unreachable) → reaches the `done` terminal and writes `1` to
   `${context.run_dir}/refine-broke-down`.
2. Runner routes parent `on_yes` (terminal name == `done`) →
   `issue-refinement.run_refine_to_ready.on_yes: check_commit`
   (`issue-refinement.yaml:29-33`). The issue is **not** skip-listed.
3. `ll-issues next-action` still returns the issue because
   `outcome_confidence < outcome_threshold` (`next_action.py:48-51`).
4. `issue-refinement.evaluate` re-selects it; goto 1. Bounded only by
   `refine_cap` (5) and `check_lifetime_limit` (max_refine_count 5).

Note: `handle_failure` (the skip-list path) is only reached when the sub-loop
reaches a **non-`done`** terminal (`failed`, via `diagnose`) or times out — i.e.
issues that fail *loudly* get skip-listed after 2 attempts, while issues that
break down *cleanly* get re-tried up to the cap. The distinction is inverted from
what's useful.

## Expected Behavior

After `run_refine_to_ready` returns, `issue-refinement` reads
`${context.run_dir}/refine-broke-down` (the child shares the parent's `run_dir`
under `context_passthrough: true` — `fsm/executor.py:553-562`). If the current
issue ID broke down, it is added to the skip-list (the `handle_failure` path) so
`next-action --skip` no longer re-selects it within the run.

## Root Cause

The runner correctly distinguishes `done` from `failed` by terminal **name**
(`fsm/executor.py:607-621`). The defect is that `refine-to-ready-issue`'s
breakdown path terminates at `done` (intentionally, so other callers like
`autodev` can route decision/missing-artifact follow-ups), making "refined to
ready" and "broke down" indistinguishable to `issue-refinement` via the verdict
alone. The `refine-broke-down` artifact is the intended disambiguator but is
unread by this caller.

## Proposed Solution

Insert a gate between `run_refine_to_ready.on_yes` and `check_commit`:

```yaml
run_refine_to_ready:
  loop: refine-to-ready-issue
  context_passthrough: true
  on_yes: check_broke_down   # was: check_commit
  on_no: handle_failure

check_broke_down:
  action: |
    ID="${captured.input.output}"
    BROKE="${context.run_dir}/refine-broke-down"
    if [ -f "$BROKE" ] && grep -q '1' "$BROKE" 2>/dev/null; then exit 0; fi
    exit 1
  action_type: shell
  evaluate:
    type: exit_code
  on_yes: handle_failure   # broke down → skip-list this issue
  on_no: check_commit      # genuine success
```

`refine-broke-down` is reset to `0` at the start of every sub-loop run
(`refine-to-ready-issue.yaml:29`), so it reflects only the issue just processed —
a keyed read is safe in the sequential `issue-refinement` loop.

## Implementation Steps

1. In `issue-refinement.yaml`: change `run_refine_to_ready.on_yes` from
   `check_commit` to `check_broke_down`.
2. Add the `check_broke_down` gate state (shell exit-code evaluator) as specified
   in Proposed Solution above.
3. Write regression test: mock a sub-loop that writes `refine-broke-down=1` and
   assert the parent routes to `handle_failure` (skip-list) rather than
   `check_commit`.
4. Smoke-test the success path: mock a sub-loop that does NOT write
   `refine-broke-down` (or writes `0`) and confirm routing reaches `check_commit`.

## Acceptance Criteria

- [ ] A broken-down issue is added to the `issue-refinement` skip-list and is not
      re-selected by `next-action --skip` within the same run.
- [ ] A genuinely refined-to-ready issue still routes to `check_commit` (no
      regression on the success path).
- [ ] Regression test: simulate a sub-loop that writes `refine-broke-down=1` and
      assert the parent skip-lists the issue.

## Scope Boundaries

- Touches `issue-refinement.yaml` only (plus a test). Does not change
  `refine-to-ready-issue`'s terminal structure (other callers depend on
  breakdown → `done`).
- Does not alter `next-action` selection logic (see BUG-2035 for the threshold
  half of the churn).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/issue-refinement.yaml` — add `check_broke_down` gate state; update `run_refine_to_ready.on_yes`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (lines 29, 361-365) — existing `refine-broke-down` signal; read-only reference, no changes required
- Other callers of `refine-to-ready-issue` (`autodev`, `greenfield-builder`, `eval-driven-development`) — unchanged; breakdown → `done` terminal is intentionally preserved for them

### Similar Patterns
- N/A — `check_broke_down` is a new cross-loop artifact gate; no similar patterns currently exist

### Tests
- `scripts/tests/` — new regression test simulating a sub-loop writing `refine-broke-down=1` and asserting the parent skip-lists the issue

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — caused a real rn-build run to be killed after burning
  multiple `--full-rewrite` passes on one issue with no progress (regression).
- **Effort**: Small — one new gate state + test.
- **Risk**: Low — additive gate on an already-correct success path.
- **Breaking Change**: No.

## Labels

`loops`, `issue-refinement`, `bug`, `captured`, `from-audit`

## Status

**Open** | Created: 2026-06-08 | Priority: P2

## Notes

If ENH-2038 (migrate rn-build `refine_seed` to `recursive-refine`) lands, this
churn is avoided for rn-build specifically — but `issue-refinement` is also used
by `eval-driven-development` and `greenfield-builder`, so this fix remains
independently warranted.


## Session Log
- `/ll:format-issue` - 2026-06-09T02:41:14 - `914690e7-fd2f-4d75-9bfa-5bb071777625.jsonl`
