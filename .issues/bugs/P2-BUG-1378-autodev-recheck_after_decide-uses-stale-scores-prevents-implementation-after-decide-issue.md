---
id: BUG-1378
type: BUG
priority: P2
status: done
captured_at: 2026-05-06 21:55:00+00:00
completed_at: 2026-05-06T23:51:01Z
discovered_date: 2026-05-06
discovered_by: user
decision_needed: false
confidence_score: 90
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

## Motivation

`autodev` is most useful for issues that have `Approach A` / `Approach B` design decisions — precisely the issues where `decision_needed: true` arises and outcome confidence is dragged down by ambiguity. The bug causes the loop to silently exit on the class of issues that would benefit most from automation, defeating the purpose of `autodev` for the hardest issues in the backlog.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `recheck_after_decide` state / `ll-issues check-readiness` action
- **Cause**: `ll-issues check-readiness` reads `readiness_score` and `outcome_score` from issue frontmatter. After `run_decide` runs `/ll:decide-issue`, the frontmatter still holds the pre-decision scores written by the earlier `/ll:confidence-check`. No re-scoring step exists between `run_decide` and `recheck_after_decide`, so the threshold gate always evaluates the stale ambiguity penalty rather than the post-decision score.

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

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/recursive-refine.yaml` — references decide-issue but does not have `run_decide`/`recheck_after_decide` states; not affected.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — flag-checking only; not affected.

### Tests

- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` (line 1045) is the harness for `autodev.yaml` state-graph assertions; follow the `test_run_wire_action_type_is_slash_command` pattern (line 1532).
  - `test_required_states_exist` (line 1061): add `"rerun_confidence_after_decide"` to the required set.
  - `test_run_decide_next_routes_to_implement_current` (line 1579): **stale** — currently asserts `next == "recheck_after_decide"` but the fix changed `run_decide.next` to `"rerun_confidence_after_decide"`; this test is broken and must be updated.
  - Add 6 new state-property tests for `rerun_confidence_after_decide` (following the `run_decide` cluster pattern): state existence/`fragment == "with_rate_limit_handling"`, `action_type == "slash_command"`, action contains `/ll:confidence-check`, `next == "recheck_after_decide"`, `on_error == "recheck_after_decide"`, `on_rate_limit_exhausted == "done"`. [2 additional properties `on_error` and `on_rate_limit_exhausted` added by wiring pass]
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` — parametrized FSM validation sweep already covers `autodev.yaml`; passes with the new state.

### Similar Patterns

- The existing `confidence_check` → `verify_scores_persisted` → `retry_confidence_check` pattern in `refine-to-ready-issue.yaml:109-158` shows the established way to invoke confidence-check inside a loop. The new state mirrors the slash_command form with `with_rate_limit_handling`.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — FSM flow diagram under "autodev — Targeted Refine-and-Implement for Specific Issues" shows `run_decide → implement_current` in 5 places without the new intermediate states; each arrow needs `→ rerun_confidence_after_decide → recheck_after_decide →` inserted. The prose block at ~line 488 ("routes directly to `run_decide` ... and then implements without decomposition") also needs updating to describe the re-scoring step. [Agent 2 finding]

### Configuration

- N/A — no config files or constants affected; the change is purely additive to the loop YAML.

## Implementation Steps

1. ~~Edit `scripts/little_loops/loops/autodev.yaml`~~ **DONE** (commit `eff2d310`):
   - ~~Change `run_decide.next` from `recheck_after_decide` to `rerun_confidence_after_decide`.~~
   - ~~Add new `rerun_confidence_after_decide` state (5 lines + docstring) routing to `recheck_after_decide`.~~
   - ~~Update the docstring on `recheck_after_decide` to note scores are now fresh.~~
2. ~~Run `ll-loop validate scripts/little_loops/loops/autodev.yaml` to confirm graph is valid.~~ **DONE** (validated in commit `eff2d310`)
3. Replay ENH-1376 (or any issue whose only blocker is decision_needed) with `ll-loop run autodev "<ID>"` and confirm it reaches `implement_current`.
4. In `scripts/tests/test_builtin_loops.py::TestAutodevLoop`:
   - Fix `test_run_decide_next_routes_to_implement_current` (line 1579): change assertion from `"recheck_after_decide"` to `"rerun_confidence_after_decide"` and update the docstring accordingly. **[TEST IS CURRENTLY FAILING — priority fix]**
   - Add `"rerun_confidence_after_decide"` to the `required` set in `test_required_states_exist` (line 1061).
   - Add 4 new state-property tests for `rerun_confidence_after_decide` (following the `test_run_wire_action_type_is_slash_command` pattern at line 1532): state existence, `action_type == "slash_command"`, action contains `/ll:confidence-check`, `next == "recheck_after_decide"`.
   - Run `python -m pytest scripts/tests/test_builtin_loops.py::TestAutodevLoop -v` to verify all pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/guides/LOOPS_GUIDE.md` — in the FSM flow diagram under "autodev — Targeted Refine-and-Implement for Specific Issues", replace each of the 5 `run_decide → implement_current` arrows with `run_decide → rerun_confidence_after_decide → recheck_after_decide → implement_current`. Update the prose block at ~line 488 to describe the re-scoring step (e.g., "routes to `run_decide` → re-scores via `/ll:confidence-check` → threshold gate → implement").
6. In `scripts/tests/test_builtin_loops.py::TestAutodevLoop`, expand the new state-property test count from 4 to 6: add `test_rerun_confidence_after_decide_on_error_routes_to_recheck_after_decide` and `test_rerun_confidence_after_decide_on_rate_limit_exhausted_routes_to_done` following the `run_decide` cluster pattern.

## Impact

- **Priority**: P2 — autodev cannot complete any issue whose outcome score is held below threshold by an unresolved decision. This is the common case for issues with `Approach A` / `Approach B` sections, which is exactly the class of issues that would benefit most from autodev.
- **Effort**: Trivial — one new YAML state, ~12 lines.
- **Risk**: Low — additive state; failure modes route to existing paths.
- **Breaking Change**: No — autodev was failing closed (exiting `done`) on this path; the fix only adds successful completions.

## Labels

`bug`, `automation`, `fsm`, `autodev`, `confidence-check`, `decide-issue`

## Session Log
- `/ll:ready-issue` - 2026-05-06T23:48:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3dd2669d-a95c-459b-a819-dbc3904c736f.jsonl`
- `/ll:wire-issue` - 2026-05-06T23:42:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fdbefc85-ec0b-4f2a-a624-65d633366c3e.jsonl`
- `/ll:refine-issue` - 2026-05-06T23:37:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef001d96-6ef8-487d-8a1c-daeba6502985.jsonl`
- `/ll:format-issue` - 2026-05-06T23:31:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8bdc0e06-85ea-43b5-8eeb-b06ffc964981.jsonl`
- `/ll:confidence-check` - 2026-05-06T23:55:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:manage-issue` - 2026-05-06T23:51:01Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

---

## Resolution

- Fixed broken test `test_run_decide_next_routes_to_implement_current`: updated assertion from `"recheck_after_decide"` to `"rerun_confidence_after_decide"` and renamed the test to match.
- Added `"rerun_confidence_after_decide"` to the required-states set in `test_required_states_exist`.
- Added 7 new state-property tests for `rerun_confidence_after_decide` (state existence, fragment, action_type, action content, next, on_error, on_rate_limit_exhausted).
- Updated `docs/guides/LOOPS_GUIDE.md`: replaced all 5 `run_decide → implement_current` arrows in the FSM diagram with `run_decide → rerun_confidence_after_decide → recheck_after_decide → implement_current`; updated the outcome-failure-triage prose to describe the re-scoring step.
- YAML change (`autodev.yaml`) was already committed in `eff2d310`.

---

## Status

**Resolved** | Created: 2026-05-06 | Completed: 2026-05-06 | Priority: P2

## Related Issues

- ENH-1376 — the issue whose autodev run surfaced this bug (output saved to `ll-auto-debug.txt`).
- BUG-1226 — also touches autodev `dequeue_next` / in-flight tracking; orthogonal but adjacent.
