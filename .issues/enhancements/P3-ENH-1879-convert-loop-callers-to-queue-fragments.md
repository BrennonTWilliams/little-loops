---
id: ENH-1879
title: Convert loop callers to queue_pop/queue_track fragments and update docs
type: ENH
priority: P3
parent: ENH-1875
size: Medium
status: done
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-06-02 07:36:05+00:00
---

# ENH-1879: Convert loop callers to queue_pop/queue_track fragments and update docs

## Summary

Convert the `dequeue_next` and skip states in `autodev.yaml`, `auto-refine-and-implement.yaml`, and `sprint-refine-and-implement.yaml` to use the `queue_pop` and `queue_track` fragments added in ENH-1878. Also assess `recursive-refine.yaml`, update docs, and validate all modified loops.

## Parent Issue

Decomposed from ENH-1875: Add queue_pop and queue_track fragments to common.yaml

## Depends On

ENH-1878 must be merged before this issue can be started (fragments must exist in `common.yaml`).

## Implementation Steps

1. Convert `autodev.yaml:dequeue_next` (lines 56–92): change `fragment: shell_exit` → `fragment: queue_pop`; the existing action block (head-pop + inflight sentinel + pre-ids snapshot + flag resets) is already the correct caller-supplied `action`, so no further changes to the state body are needed

2. Assess `recursive-refine.yaml:dequeue_next` (lines 74–100+): the depth-map lookup, visited-list append, dequeued-count counter, and stderr progress line make this a known exception; leave `fragment: shell_exit` intact and add a code comment:
   ```yaml
   # queue_pop fragment not used — see ENH-1875 for exception rationale
   ```

3. Convert skip states to `fragment: queue_track`:
   - `autodev.yaml:skip_inflight` — add `fragment: queue_track`; **retain `action_type: shell` explicitly** in the state body alongside `fragment: queue_track` so `test_skip_inflight_is_shell_action` in `test_builtin_loops.py` (line 1509) continues to pass without modification (it reads raw pre-resolution YAML)
   - `auto-refine-and-implement.yaml:skip_and_continue` — add `fragment: queue_track`; ensure `next:` routing is present
   - `sprint-refine-and-implement.yaml:skip_and_continue` — add `fragment: queue_track`; ensure `next:` routing is present

4. Add two rows to the fragment catalog table in `skills/create-loop/reference.md` at line 1129 (after the `convergence_gate` row) for `queue_pop` and `queue_track`; document what each provides vs. what the caller must supply

5. Append two rows for `queue_pop` and `queue_track` to the `#### lib/common.yaml — type-pattern fragments` catalog table in `docs/guides/LOOPS_GUIDE.md` (parallel to `skills/create-loop/reference.md`)

6. Run `ll-loop validate autodev.yaml auto-refine-and-implement.yaml sprint-refine-and-implement.yaml` and confirm all pass

7. Update `scripts/little_loops/loops/README.md` — append `queue_pop` and `queue_track` to the fragment name list in the `lib/common.yaml` row of the fragment library table (~line 173)

8. Update `scripts/tests/test_fsm_fragments.py:TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` — add `"auto-refine-and-implement.yaml"` and `"sprint-refine-and-implement.yaml"` to the `migration_targets` list so both loops are covered by `load_and_validate` after adopting `fragment: queue_track`

9. Run `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_loops_recursive_refine.py scripts/tests/test_builtin_loops.py -v --tb=short` and confirm all pass

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Steps 4 and 5 are already done**: Both doc catalog tables were populated during ENH-1878. Do not re-add rows.
- **Step 7 fragment tests already exist**: `TestQueuePopFragment` and `TestQueueTrackFragment` in `test_fsm_fragments.py` were added in ENH-1878. Running the test suite validates the fragment definitions are correct.
- **`auto-refine-and-implement` and `sprint-refine-and-implement` use bare `.loops/tmp/` paths** (not `${context.run_dir}/`) — these are eligible for `fragment: queue_track` but the skip-file paths remain unchanged.
- **Current `skip_inflight` state body** (autodev.yaml lines 112–123): two-op shell — `echo ... >> autodev-skipped.txt` and `rm -f autodev-inflight`. Both ops must remain in `action:` after adding `fragment: queue_track`; only `action_type: shell` moves to the fragment.
- **`dequeue_next` in autodev.yaml** currently reads: `fragment: shell_exit` (not a bare `action_type: shell`). Change is `shell_exit` → `queue_pop`; the full `action:` block stays as-is.

## Success Metrics

- `autodev.yaml:dequeue_next` uses `fragment: queue_pop`
- `autodev.yaml:skip_inflight`, `auto-refine-and-implement.yaml:skip_and_continue`, `sprint-refine-and-implement.yaml:skip_and_continue` use `fragment: queue_track`
- `recursive-refine.yaml:dequeue_next` retains `fragment: shell_exit` with explanatory comment
- All three modified loops pass `ll-loop validate`
- All tests pass including `test_skip_inflight_is_shell_action`
- Fragment catalog rows added to both `skills/create-loop/reference.md` and `docs/guides/LOOPS_GUIDE.md`

## Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — convert dequeue_next + skip_inflight
- `scripts/little_loops/loops/recursive-refine.yaml` — add comment only (known exception)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — convert skip_and_continue
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — convert skip_and_continue
- `skills/create-loop/reference.md` — add two catalog rows
- `docs/guides/LOOPS_GUIDE.md` — add two catalog rows

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — change `fragment: shell_exit` → `fragment: queue_pop` in `dequeue_next`; add `fragment: queue_track` + retain `action_type: shell` inline in `skip_inflight`
- `scripts/little_loops/loops/recursive-refine.yaml` — add comment only (no structural change)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — add `fragment: queue_track` to `skip_and_continue`; remove inline `action_type: shell`
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — add `fragment: queue_track` to `skip_and_continue`; remove inline `action_type: shell`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — Fragment library table at line ~173 lists `lib/common.yaml` fragment names but does not include `queue_pop` or `queue_track`; add both entries alongside the existing fragment list [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py:TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` (line ~988) — `migration_targets` list covers `autodev.yaml` but not `auto-refine-and-implement.yaml` or `sprint-refine-and-implement.yaml`; after both adopt `fragment: queue_track`, add them to `migration_targets` to get `load_and_validate` (full fragment-resolution) coverage [Agent 3 finding]

### Already Complete (from ENH-1878)

- `skills/create-loop/reference.md` — `queue_pop` row at line 1130, `queue_track` row at line 1131 already present
- `docs/guides/LOOPS_GUIDE.md` — `queue_pop` row at line 3160, `queue_track` row at line 3161 already present
- `scripts/tests/test_fsm_fragments.py` — `TestQueuePopFragment` (line 1602) and `TestQueueTrackFragment` (line 1667) already present
- `scripts/little_loops/loops/lib/common.yaml` — `queue_pop` (lines 124–133) and `queue_track` (lines 134–140) already defined

### Dependent Files (No Changes Needed)

- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments()` merges fragments via `_deep_merge(frag_copy, state_dict)` before FSM execution; no changes needed
- `scripts/tests/test_builtin_loops.py:1509` — `test_skip_inflight_is_shell_action` reads raw pre-resolution YAML; passing requires `action_type: shell` inline in `skip_inflight`

### Similar Patterns

- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml:implement_next` — already uses `fragment: shell_exit` with the head/tail/mv idiom; conversion to `fragment: queue_pop` is out of scope here but is a candidate for a follow-on pass

## Key Test Constraint

`scripts/tests/test_builtin_loops.py:TestAutodevLoop.test_skip_inflight_is_shell_action` (line 1509) reads raw pre-resolution YAML and asserts `state.get("action_type") == "shell"`. Retain `action_type: shell` inline in `skip_inflight` alongside `fragment: queue_track` to satisfy this test without modifying it.

## Session Log
- `/ll:ready-issue` - 2026-06-02T07:33:19 - `ce54a5bc-46ff-4d46-acd1-b4b816576687.jsonl`
- `/ll:wire-issue` - 2026-06-02T07:28:04 - `280e5f97-935f-466a-9037-b413bd1e84f9.jsonl`
- `/ll:refine-issue` - 2026-06-02T07:23:24 - `dc6df14c-57fe-49dc-8445-a5206b53cab3.jsonl`
- `/ll:issue-size-review` - 2026-06-02T12:00:00Z - `073bc8f6-ad34-4a16-9ace-92422f178aac.jsonl`
- `/ll:confidence-check` - 2026-06-02T13:00:00Z - `6a04d4c3-d88e-461e-b4c3-b05efc23eead.jsonl`
