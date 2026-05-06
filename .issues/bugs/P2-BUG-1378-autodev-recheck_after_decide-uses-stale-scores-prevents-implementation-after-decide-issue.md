---
id: BUG-1378
type: BUG
priority: P2
status: open
captured_at: 2026-05-06T21:55:00Z
discovered_date: 2026-05-06
discovered_by: user
---

# BUG-1378: autodev `recheck_after_decide` Evaluates Stale Pre-Decision Scores, Prevents Implementation

## Summary

When the autodev loop runs `/ll:decide-issue` to resolve `decision_needed`, the next state (`recheck_after_decide`) evaluates **stale** outcome/readiness scores written by the *prior* `/ll:confidence-check` — i.e. before the decision was made. If the unresolved decision was the very thing dragging outcome confidence below threshold (the typical case, since open design questions score Ambiguity 5-10/25), the issue can never pass the gate even though decide-issue just resolved that ambiguity. The loop drops the issue and exits without ever reaching `implement_current`.

## Current Behavior

Concrete trace from `ll-auto` run on ENH-1376 (2026-05-06):

1. `refine_current` sub-loop ran `/ll:confidence-check` → readiness 95/100 ✓, outcome 63/100 ✗ (Ambiguity 10/25 *explicitly* attributed to two unresolved design questions); set `decision_needed: true`.
2. `check_decision_after_refine` saw the flag → routed to `run_decide`.
3. `run_decide` ran `/ll:decide-issue --auto` → selected Approach A, resolved both open questions, set `decision_needed: false`.
4. `recheck_after_decide` ran `ll-issues check-readiness ENH-1376 --readiness 90 --outcome 75` — but this command **reads scores from frontmatter**, which still held the pre-decision values (95/63). 63 < 75 → exit 1 → `on_no: dequeue_next` → queue empty → `done`.

The very dimension that decide-issue just fixed (Ambiguity from unresolved decisions) is never recomputed, so the FSM cannot see the improvement.

## Steps to Reproduce

1. Pick an issue whose `decision_needed: true` and whose outcome confidence is held below the threshold by the unresolved decision (typical when Ambiguity scores ≤10/25 with explicit "X open design questions" wording).
2. Run `ll-loop run autodev "<ID>"`.
3. Observe: refine sub-loop completes; `run_decide` runs and clears `decision_needed`.
4. Observe: `recheck_after_decide` exits 1 because frontmatter still holds the pre-decision outcome score.
5. Observe: loop routes to `dequeue_next` → `done` without ever entering `implement_current`.

## Expected Behavior

After `/ll:decide-issue` resolves open design questions, the loop re-runs `/ll:confidence-check` so that `recheck_after_decide` evaluates fresh scores. If the resolved decision lifts outcome above threshold, the issue proceeds to `implement_current` as intended.

## Proposed Solution

Insert a new state `rerun_confidence_after_decide` between `run_decide` and `recheck_after_decide` in `scripts/little_loops/loops/autodev.yaml`. It runs `/ll:confidence-check ${captured.input.output}` so frontmatter scores are recomputed against the resolved decision before threshold gating.

```yaml
run_decide:
  fragment: with_rate_limit_handling
  action: "/ll:decide-issue ${captured.input.output} --auto"
  action_type: slash_command
  next: rerun_confidence_after_decide   # was: recheck_after_decide
  on_error: recheck_after_decide        # decide errored → no score change possible
  on_rate_limit_exhausted: done

rerun_confidence_after_decide:
  fragment: with_rate_limit_handling
  action: "/ll:confidence-check ${captured.input.output}"
  action_type: slash_command
  next: recheck_after_decide
  on_error: recheck_after_decide
  on_rate_limit_exhausted: done
```

`recheck_after_decide` is unchanged — it now reads fresh scores instead of stale ones.

### Why not the alternative

Having `/ll:decide-issue --auto` itself recompute scores was considered and rejected: it couples decide-issue to the scoring model and duplicates work when decide is invoked from non-FSM contexts. Keeping the recompute in the FSM (where we know thresholds are about to be checked) is cleaner.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — add `rerun_confidence_after_decide` state; redirect `run_decide.next`. Already validated with `ll-loop validate` after a draft edit.

### Dependent Files

- `scripts/little_loops/loops/recursive-refine.yaml` — references decide-issue but does not have `run_decide`/`recheck_after_decide` states; not affected.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — flag-checking only; not affected.

### Tests

- `scripts/tests/test_loops.py` (or equivalent FSM YAML test file) — add a state-graph assertion that `run_decide` transitions to a confidence-check state before `recheck_after_decide`. If no such test file exists, validate via `ll-loop validate` in CI (already passing).

### Similar Patterns

- The existing `confidence_check` → `verify_scores_persisted` → `retry_confidence_check` pattern in `refine-to-ready-issue.yaml:109-158` shows the established way to invoke confidence-check inside a loop. The new state mirrors the slash_command form with `with_rate_limit_handling`.

## Implementation Steps

1. Edit `scripts/little_loops/loops/autodev.yaml`:
   - Change `run_decide.next` from `recheck_after_decide` to `rerun_confidence_after_decide`.
   - Add new `rerun_confidence_after_decide` state (5 lines + docstring) routing to `recheck_after_decide`.
   - Update the docstring on `recheck_after_decide` to note scores are now fresh.
2. Run `ll-loop validate scripts/little_loops/loops/autodev.yaml` to confirm graph is valid.
3. Replay ENH-1376 (or any issue whose only blocker is decision_needed) with `ll-loop run autodev "<ID>"` and confirm it reaches `implement_current`.
4. Add a regression test or smoke run to `scripts/tests/` if a suitable harness exists.

## Impact

- **Severity**: Medium-High — autodev cannot complete any issue whose outcome score is held below threshold by an unresolved decision. This is the common case for issues with `Approach A` / `Approach B` sections, which is exactly the class of issues that would benefit most from autodev.
- **Effort**: Trivial — one new YAML state, ~12 lines.
- **Risk**: Low — additive state; failure modes route to existing paths.
- **Breaking Change**: No — autodev was failing closed (exiting `done`) on this path; the fix only adds successful completions.

## Labels

`bug`, `automation`, `fsm`, `autodev`, `confidence-check`, `decide-issue`

---

## Status

**Open** | Created: 2026-05-06 | Priority: P2

## Related Issues

- ENH-1376 — the issue whose autodev run surfaced this bug (output saved to `ll-auto-debug.txt`).
- BUG-1226 — also touches autodev `dequeue_next` / in-flight tracking; orthogonal but adjacent.
