---
id: ENH-1337
type: ENH
priority: P2
status: open
discovered_date: 2026-05-02
discovered_by: research-synthesis
related: [ENH-1338, ENH-1339]
decision_needed: false
---

# ENH-1337: Add Per-Subtree Depth Limit to `recursive-refine`

## Summary

`recursive-refine` has a global `max_iterations: 500` cap but no per-subtree depth limit. A single oversized issue could decompose recursively many levels deep (parent → children → grandchildren → ...) and consume the entire global budget while siblings starve. Add a `max_depth` parameter (default 3) that tracks each issue's distance from an originally-supplied root and short-circuits further `issue-size-review` decomposition once exceeded — falling through to "skipped, decomposition depth exceeded" instead of recursing further.

## Motivation

2026 research on recursive planning agents converges on hard depth caps as a primary safeguard against unbounded replanning:

- Graph Harness frameworks separate planning/execution/recovery and enforce "strict escalation protocol that prevents unbounded replanning" ([Recursive Language Models, Prime Intellect, 2026](https://www.primeintellect.ai/blog/rlm)).
- "Every agent run needs a hard cap on the number of thought steps" — failure-mode research on recursive planning loops ([fixbrokenaiapps.com 2026](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops)).
- ReCAP and similar systems explicitly limit recursion depth before backtracking ([ReCAP, Stanford CS224R](https://cs224r.stanford.edu/projects/pdfs/CS224R_RECAP.pdf)).

Our loop currently relies entirely on `max_iterations: 500` as a defense, but iterations are consumed by *all* issues in the run combined; one runaway subtree can deny budget to siblings.

## Current Behavior

- `scripts/little_loops/loops/recursive-refine.yaml:16` sets `max_iterations: 500` global.
- No state tracks how many decomposition hops separate a given queue item from its root.
- `enqueue_children` (line 190) and `enqueue_or_skip` (line 301) prepend children unconditionally, regardless of how deep the parent already was.
- A pathological size-review that always splits 1→3 could enqueue children faster than they're refined, consuming the queue and the iteration budget.

## Expected Behavior

- New context parameter: `max_depth: 3` (configurable via `commands.recursive_refine.max_depth` in `.ll/ll-config.json`).
- `parse_input` initializes `.loops/tmp/recursive-refine-depth-map.txt` with depth `0` for each root issue.
- `enqueue_children` / `enqueue_or_skip` write `child_id depth+1` for each enqueued child.
- `dequeue_next` reads the dequeued issue's depth.
- New gate state `check_depth` (between `recheck_scores` and `run_size_review`): if current depth ≥ `max_depth`, mark the issue skipped with reason `depth-cap` and fall through to `dequeue_next` instead of running size-review.
- `done` summary distinguishes `Skipped (depth-cap)` from generic skips.

## Proposed Solution

1. Add to `context:` block: `max_depth: 3   # canonical: commands.recursive_refine.max_depth`.
2. In `parse_input`, after writing the queue, initialize:
   ```bash
   while IFS= read -r id; do echo "$id 0"; done \
     < .loops/tmp/recursive-refine-queue.txt \
     > .loops/tmp/recursive-refine-depth-map.txt
   ```
3. In `dequeue_next`, look up the dequeued ID's depth and write to `.loops/tmp/recursive-refine-current-depth.txt`.
4. Insert a new state `check_depth` immediately before `run_size_review` (replacing `recheck_scores → run_size_review` with `recheck_scores → check_depth → run_size_review`).
5. In `enqueue_children` / `enqueue_or_skip`, when prepending children, append `child_id (parent_depth + 1)` to the depth map.
6. In `done` summary, partition skipped IDs by reason file (`.loops/tmp/recursive-refine-skipped-depth.txt` vs `recursive-refine-skipped-other.txt`).

## Acceptance Criteria

- [ ] `recursive-refine.yaml` exposes `max_depth` in `context:` and reads `.ll/ll-config.json` override.
- [ ] Depth map file is created in `parse_input` and updated whenever children are enqueued.
- [ ] `check_depth` state short-circuits size-review once the current issue's depth ≥ `max_depth`, marking it `depth-cap` skipped.
- [ ] `done` summary includes a `Skipped (depth-cap N): IDs...` line when applicable.
- [ ] New test in `scripts/tests/test_loops_recursive_refine.py` (or equivalent) covers a synthetic 4-level decomposition with `max_depth: 2`.
- [ ] No regression in existing recursive-refine tests.

## Scope Boundaries

- **In scope**: depth tracking, gate state, summary partitioning, config wiring.
- **Out of scope**: per-issue retry budget (ENH-1339), cycle detection (ENH-1338) — depth ≠ cycles.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — add `max_depth` to `context:`, insert `check_depth` state, update `parse_input`/`dequeue_next`/`enqueue_children`/`enqueue_or_skip`/`done`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/ll_loop.py` — loop runner; no direct change but consumes the YAML.
- `scripts/tests/test_loops_recursive_refine.py` — exercises the loop end-to-end.

### Similar Patterns
- Other FSM loops with per-iteration counters (e.g., `scripts/little_loops/loops/refine-to-ready-issue.yaml` for state structure conventions).

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — add a 4-level synthetic decomposition fixture with `max_depth: 2`.

### Documentation
- `docs/reference/loops/recursive-refine.md` (if present) — document `max_depth` parameter.
- `config-schema.json` — add `commands.recursive_refine.max_depth`.

### Configuration
- `.ll/ll-config.json` — new optional `commands.recursive_refine.max_depth` override.

## Implementation Steps

1. Wire `max_depth` into the YAML `context:` block and `config-schema.json`, with `.ll/ll-config.json` override resolution.
2. Initialize the depth map in `parse_input` (depth `0` per root) and persist it under `.loops/tmp/`.
3. Update `dequeue_next` to look up the dequeued ID's depth and write it to `.loops/tmp/recursive-refine-current-depth.txt`.
4. Insert the `check_depth` gate state between `recheck_scores` and `run_size_review`; route over-cap items to skipped with reason `depth-cap`.
5. Update `enqueue_children` and `enqueue_or_skip` to append `child_id (parent_depth + 1)` to the depth map.
6. Partition `done`-summary skip lines by reason file and add `Skipped (depth-cap N)`.
7. Add a synthetic 4-level test in `scripts/tests/test_loops_recursive_refine.py`.

## Impact

- **Priority**: P2 — Defensive control against runaway decomposition; no current outage but real risk once size-review is exercised on large issues.
- **Effort**: Medium — One new state plus tracking files; touches several existing states but each change is small.
- **Risk**: Low — Default `max_depth: 3` is permissive enough that current runs are unaffected; new state is purely additive.
- **Breaking Change**: No — Existing loop runs without override behave identically.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `safety`

## Status

**Open** | Created: 2026-05-02 | Priority: P2

## References

- `scripts/little_loops/loops/recursive-refine.yaml` (states `parse_input`, `dequeue_next`, `enqueue_children`, `enqueue_or_skip`, `recheck_scores`, `run_size_review`, `done`).
- 2026 research: [Recursive Language Models](https://www.primeintellect.ai/blog/rlm), [The Agent Loop Problem](https://medium.com/@Modexa/the-agent-loop-problem-when-smart-wont-stop-ccbf8489180f), [ReCAP](https://cs224r.stanford.edu/projects/pdfs/CS224R_RECAP.pdf).


## Session Log
- `/ll:format-issue` - 2026-05-03T04:41:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a41e2fe5-b6da-449b-8d60-6b8ddd06d97c.jsonl`
