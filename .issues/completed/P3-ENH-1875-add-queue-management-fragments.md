---
id: ENH-1875
title: Add queue_pop and queue_track fragments to common.yaml
type: ENH
priority: P3
parent: ENH-1777
captured_at: '2026-06-02T00:00:00Z'
discovered_date: 2026-06-02
discovered_by: issue-size-review
decision_needed: false
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
size: Very Large
status: done
---

# ENH-1875: Add queue_pop and queue_track fragments to common.yaml

## Summary

Add `queue_pop` and `queue_track` fragments to `loops/lib/common.yaml` to abstract the repeated atomic head-pop and skip-list-append shell idioms shared by `autodev.yaml`, `auto-refine-and-implement.yaml`, `sprint-refine-and-implement.yaml`, and `recursive-refine.yaml`.

## Parent Issue

Decomposed from ENH-1777: Wave 4 — Remaining Fragments, Sub-loops, and Flows

## Current Behavior

Four loops share the same atomic head-pop shell idiom: `head -1 <queue>`, `tail -n +2 <queue> > <queue>.tmp`, `mv <queue>.tmp <queue>`. Children are prepended depth-first with `{ echo "$CHILDREN"; echo "$EXISTING"; } | grep -v … > <queue>`. `recursive-refine`'s `dequeue_next` is significantly richer (depth maps, visited list, dequeued-count counter, stderr progress lines) and should not be conflated with a simple `queue_pop` fragment.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Scope correction for `queue_pop`**: Only `autodev.yaml` and `recursive-refine.yaml` use the `head -1 / tail -n +2 / mv` head-pop idiom. `auto-refine-and-implement.yaml` delegates to `ll-issues next-issue` (CLI); `sprint-refine-and-implement.yaml` iterates a YAML list with `while IFS= read -r`. Neither has a file-based mutable queue.
- **Scope for `queue_track`**: All four loops use `echo "$ID" >> <skip-file>`. Skip states: `autodev.yaml:skip_inflight`, `auto-refine-and-implement.yaml:skip_and_continue`, `sprint-refine-and-implement.yaml:skip_and_continue`, `recursive-refine.yaml` (multiple states: `enqueue_children`, `enqueue_or_skip`, `skip_missing_artifacts`, etc.).
- **Existing fragment usage**: Both `autodev.yaml:dequeue_next` and `recursive-refine.yaml:dequeue_next` already use `fragment: shell_exit`. Adding `queue_pop` is a semantic rename — fragment key provides `action_type: shell` + `evaluate: {type: exit_code}`; callers still supply `action:` themselves.

## Expected Behavior

- `queue_pop` fragment in `loops/lib/common.yaml`: `action_type: shell`, evaluate `exit_code`, supplies the atomic 3-line head-pop idiom; caller supplies queue file path via `${context.*}` and routing
- `queue_track` fragment in `loops/lib/common.yaml`: `action_type: shell`, no evaluator; appends to skip list with `>>`
- `autodev.yaml:dequeue_next` converted to use `queue_pop`
- `recursive-refine.yaml:dequeue_next` assessed — if depth-map/visited-list logic makes reuse impractical, leave with a code comment pointing to the fragment and document as known exception

## Proposed Solution

1. Add `queue_pop` fragment to `scripts/little_loops/loops/lib/common.yaml` — model after `shell_exit` fragment; supplies the atomic head-pop shell idiom; caller supplies `action` (queue file path) and routing
2. Add `queue_track` fragment to `scripts/little_loops/loops/lib/common.yaml` — `action_type: shell`, no evaluator; caller supplies `action` (skip-list path and content) and routing
3. Convert `autodev.yaml:dequeue_next` to use `queue_pop`
4. Assess `recursive-refine.yaml:dequeue_next` — if the richer logic makes fragment reuse impractical, leave intact with a comment pointing to the fragment; mark as known exception in issue resolution
5. Run `ll-loop validate` on `autodev.yaml` (and `recursive-refine.yaml` if modified)

### Fragment Design

_Added by `/ll:refine-issue` — based on codebase analysis of `loops/lib/common.yaml` fragments (`shell_exit`, `convergence_gate`):_

```yaml
# In scripts/little_loops/loops/lib/common.yaml, under fragments:

queue_pop:
  description: |
    Shell state that atomically pops the head of a queue file (head-1/tail-n+2/mv idiom).
    State must supply: action (the three-line pop shell script, plus any per-loop extras
    such as inflight sentinels or counter increments), on_yes (item popped), on_no (queue empty).
    Optionally: on_error, capture.
  action_type: shell
  evaluate:
    type: exit_code

queue_track:
  description: |
    Shell state that appends an ID to a skip or visited tracking file (echo >> idiom).
    No evaluator — this state always transitions unconditionally via next:.
    State must supply: action (echo "<ID>" >> <track-file>), next:.
  action_type: shell
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — add `queue_pop` and `queue_track` fragments (ensure `description:` field on each to pass existing fragment description test)
- `scripts/little_loops/loops/autodev.yaml` — convert `dequeue_next` to use `queue_pop`
- `scripts/little_loops/loops/recursive-refine.yaml` — convert or add comment (decide during implementation)

### Reference Pattern
- `convergence_gate` — evaluator-only fragment (no `action`)
- `shell_exit` — `action_type: shell` + `evaluate.type: exit_code`; caller supplies `action`, routing

### Dependent Files
- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments()`, `_deep_merge()` (read to understand merge semantics)

### Tests
- `scripts/tests/test_fsm_fragments.py` — add `TestQueuePopFragment` and `TestQueueTrackFragment` classes following `TestConvergenceGateFragment` pattern (schema presence + `resolve_fragments` integration test); ensure each new fragment includes `description:` field
- Ensure `test_all_common_yaml_fragments_have_description` passes for new fragments

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestAutodevLoop.test_skip_inflight_is_shell_action` (line 1509) — reads raw pre-resolution YAML and asserts `state.get("action_type") == "shell"`; will break if converting `skip_inflight` to `fragment: queue_track` removes the explicit `action_type: shell` from the state body (which the test reads before fragment resolution runs). Fix: retain `action_type: shell` inline in `skip_inflight` alongside `fragment: queue_track`, OR update this test to only assert the field when present at raw-YAML level.

### Additional `queue_track` Callers (Skip-State Conversions)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/loops/auto-refine-and-implement.yaml:skip_and_continue` — `echo >> .loops/tmp/auto-refine-and-implement-skipped.txt`; `queue_track` candidate
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:skip_and_continue` — `echo >> .loops/tmp/sprint-refine-and-implement-skipped.txt`; `queue_track` candidate
- `scripts/little_loops/loops/autodev.yaml:skip_inflight` — `echo >> ${context.run_dir}/autodev-skipped.txt`; `queue_track` candidate
- `scripts/little_loops/loops/recursive-refine.yaml` — skip appends in `enqueue_children`, `enqueue_or_skip`, `skip_missing_artifacts`, `check_decision_needed`, `check_depth`, `check_attempt_budget`; assess individually (some embed the append in larger multi-step action blocks)

### Line-Number References

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/loops/autodev.yaml:dequeue_next` — lines 56–92 (head-pop + inflight sentinel + pre-ids snapshot + flag resets; currently `fragment: shell_exit`)
- `scripts/little_loops/loops/recursive-refine.yaml:dequeue_next` — lines 74–100+ (head-pop + visited list + depth map + dequeued counter + stderr progress; currently `fragment: shell_exit`)
- Fragment invocation syntax: `fragment: queue_pop` (not `use_fragment:`) — see `fragments.py:resolve_fragments()` which looks for the `fragment:` key in each state

### Test and Documentation Anchors

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_fsm_fragments.py:TestConvergenceGateFragment` (lines 1525–1594) — exact model class for `TestQueuePopFragment` and `TestQueueTrackFragment`
- `scripts/tests/test_fsm_fragments.py:test_all_common_yaml_fragments_have_description` (line 1120) — auto-covers new fragments once `description:` field is present; no separate assertion needed
- `skills/create-loop/reference.md` (lines 1119–1129) — existing fragment catalog table (lib/common.yaml section); append two rows after `convergence_gate`

### Documentation
- `skills/create-loop/reference.md` — add fragment catalog rows for `queue_pop` and `queue_track` (what each provides vs. what caller must supply)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — contains a parallel fragment catalog table (`#### lib/common.yaml — type-pattern fragments`, mirroring `skills/create-loop/reference.md`); append two rows for `queue_pop` and `queue_track` after the `convergence_gate` row

## Implementation Steps

1. Add `queue_pop` fragment to `scripts/little_loops/loops/lib/common.yaml` — model after `shell_exit` (lines 15–21); add `action_type: shell`, `evaluate: {type: exit_code}`, and `description:` block documenting the head-pop idiom and what caller must supply
2. Add `queue_track` fragment immediately after `queue_pop` in `common.yaml` — `action_type: shell`, no `evaluate` block, `description:` block documenting the skip-list append idiom and that caller must supply `next:`
3. Convert `autodev.yaml:dequeue_next` (lines 56–92): change `fragment: shell_exit` → `fragment: queue_pop`; action block already supplies the head-pop plus extras (inflight sentinel, pre-ids snapshot, flag resets), no other changes needed
4. Assess `recursive-refine.yaml:dequeue_next` (lines 74–100+): depth-map lookup, visited-list append, dequeued-count counter, and stderr progress line make this a known exception; leave `fragment: shell_exit` intact and add a comment `# queue_pop fragment not used — see ENH-1875 for exception rationale`
5. Convert skip states to `fragment: queue_track`: `autodev.yaml:skip_inflight`, `auto-refine-and-implement.yaml:skip_and_continue`, `sprint-refine-and-implement.yaml:skip_and_continue`; change their `fragment: shell_exit` (if set) or add `fragment: queue_track` and add `next:` routing
6. Add `TestQueuePopFragment` and `TestQueueTrackFragment` classes to `scripts/tests/test_fsm_fragments.py` following `TestConvergenceGateFragment` (lines 1525–1594): schema presence, `action_type`, evaluator type, description field presence, full `resolve_fragments()` integration test
7. Add two rows to fragment catalog table in `skills/create-loop/reference.md` at line 1129 (after `convergence_gate` row)
8. Run `ll-loop validate autodev.yaml auto-refine-and-implement.yaml sprint-refine-and-implement.yaml`
9. Run `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_loops_recursive_refine.py -v --tb=short`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `docs/guides/LOOPS_GUIDE.md` — append two rows for `queue_pop` and `queue_track` to the `#### lib/common.yaml — type-pattern fragments` catalog table (parallel to `skills/create-loop/reference.md` step 7)
11. Handle `test_skip_inflight_is_shell_action` in `scripts/tests/test_builtin_loops.py` (line 1509) — retain `action_type: shell` explicitly in the `skip_inflight` state body alongside `fragment: queue_track` so this raw-YAML test continues to pass without modification

## Success Metrics

- Queue fragments eliminate duplicated temp-file operations across affected loops
- All modified loops pass `ll-loop validate`
- `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_loops_recursive_refine.py -v --tb=short` passes

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-02_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Breadth penalty (8 distinct sites, 6–15 range)**: per-site depth is local/mechanical, so the complexity score reflects surface area rather than per-site difficulty — manageable but requires disciplined tracking across all 8 files.
- **Change surface scored as Pattern A** (non-uniform substitutions: `queue_pop` vs `queue_track` vs comment-only vs new test classes vs doc rows): 8 sites places this in the "broad surface" tier (10/25). The issue mitigates this with verification commands (`ll-loop validate`, specific `pytest`) and enumerated line-number references.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-02
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1878: Add queue_pop and queue_track fragments to common.yaml + tests
- ENH-1879: Convert loop callers to queue fragments and update docs

## Session Log
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `dfdaada7-457a-4a4f-9569-5e5f58453451.jsonl`
- `/ll:wire-issue` - 2026-06-02T06:57:09 - `84243f7d-8e2e-4427-be0b-cb830dffb8d5.jsonl`
- `/ll:refine-issue` - 2026-06-02T06:51:42 - `4fb82a46-b58e-4d47-ae55-f1da15de2b03.jsonl`
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
- `/ll:issue-size-review` - 2026-06-02T12:00:00Z - `073bc8f6-ad34-4a16-9ace-92422f178aac.jsonl`
