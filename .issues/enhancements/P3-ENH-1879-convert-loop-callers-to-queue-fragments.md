---
id: ENH-1879
title: Convert loop callers to queue_pop/queue_track fragments and update docs
type: ENH
priority: P3
parent: ENH-1875
size: Medium
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

7. Run `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_loops_recursive_refine.py scripts/tests/test_builtin_loops.py -v --tb=short` and confirm all pass

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

## Key Test Constraint

`scripts/tests/test_builtin_loops.py:TestAutodevLoop.test_skip_inflight_is_shell_action` (line 1509) reads raw pre-resolution YAML and asserts `state.get("action_type") == "shell"`. Retain `action_type: shell` inline in `skip_inflight` alongside `fragment: queue_track` to satisfy this test without modifying it.

## Session Log
- `/ll:issue-size-review` - 2026-06-02T12:00:00Z - `073bc8f6-ad34-4a16-9ace-92422f178aac.jsonl`
