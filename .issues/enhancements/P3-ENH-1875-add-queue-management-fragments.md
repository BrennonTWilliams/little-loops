---
id: ENH-1875
title: "Add queue_pop and queue_track fragments to common.yaml"
type: ENH
priority: P3
parent: ENH-1777
captured_at: '2026-06-02T00:00:00Z'
discovered_date: 2026-06-02
discovered_by: issue-size-review
---

# ENH-1875: Add queue_pop and queue_track fragments to common.yaml

## Summary

Add `queue_pop` and `queue_track` fragments to `loops/lib/common.yaml` to abstract the repeated atomic head-pop and skip-list-append shell idioms shared by `autodev.yaml`, `auto-refine-and-implement.yaml`, `sprint-refine-and-implement.yaml`, and `recursive-refine.yaml`.

## Parent Issue

Decomposed from ENH-1777: Wave 4 — Remaining Fragments, Sub-loops, and Flows

## Current Behavior

Four loops share the same atomic head-pop shell idiom: `head -1 <queue>`, `tail -n +2 <queue> > <queue>.tmp`, `mv <queue>.tmp <queue>`. Children are prepended depth-first with `{ echo "$CHILDREN"; echo "$EXISTING"; } | grep -v … > <queue>`. `recursive-refine`'s `dequeue_next` is significantly richer (depth maps, visited list, dequeued-count counter, stderr progress lines) and should not be conflated with a simple `queue_pop` fragment.

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

### Documentation
- `skills/create-loop/reference.md` — add fragment catalog rows for `queue_pop` and `queue_track` (what each provides vs. what caller must supply)

## Success Metrics

- Queue fragments eliminate duplicated temp-file operations across affected loops
- All modified loops pass `ll-loop validate`
- `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_loops_recursive_refine.py -v --tb=short` passes

## Session Log
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
