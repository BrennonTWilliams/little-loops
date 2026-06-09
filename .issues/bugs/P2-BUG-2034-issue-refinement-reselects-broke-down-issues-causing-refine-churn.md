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
`issue-refinement` treats the broken-down issue as a **success**
(`run_refine_to_ready.on_yes: check_commit`) and never adds it to the skip-list.
Because the issue's scores are still below threshold, `ll-issues next-action`
re-emits `NEEDS_REFINE <id>` on the very next cycle and the loop re-selects the
same issue. This repeats — each pass running an expensive `--full-rewrite` — until
the per-issue `refine_cap` (5) is exhausted.

Observed in run `.loops/runs/rn-build-20260608T181251/`: FEAT-032 was processed in
iter-9, iter-10, and iter-11 (killed mid-third-pass), with `outcome_confidence`
*regressing* 71→68 across passes. See `audit-rn-build-feat032-2026-06-08.md`.

The `refine-broke-down` signal file already exists for exactly this purpose
(`refine-to-ready-issue.yaml:29,361-365`) but `issue-refinement` never reads it.

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

## Proposed Fix

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

## Files

- `scripts/little_loops/loops/issue-refinement.yaml` — add `check_broke_down`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:29,361-365` — existing
  `refine-broke-down` signal (read-only reference)
- `scripts/tests/` — new regression test

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
