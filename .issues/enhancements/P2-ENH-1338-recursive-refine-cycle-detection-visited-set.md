---
id: ENH-1338
type: ENH
priority: P2
status: open
discovered_date: 2026-05-02
discovered_by: research-synthesis
related: [ENH-1337, ENH-1339]
decision_needed: false
---

# ENH-1338: Cycle Detection / Visited-Set for `recursive-refine` Queue

## Summary

`recursive-refine` has no protection against re-enqueueing an issue ID it has already processed in the current run. If `issue-size-review` ever produces a child whose ID collides with a previously-handled parent (via stale numbering, manual re-creation, or a future sub-loop bug), the queue would loop the same ID indefinitely until `max_iterations: 500` trips. Add an explicit visited-set check in `enqueue_children` and `enqueue_or_skip` that drops any candidate child whose ID already appears in passed/skipped/in-flight tracking.

## Motivation

2026 failure-mode research on recursive planning agents identifies "Loop Drift" — when an agent misinterprets termination signals or produces repetitive actions — as a primary failure mode, with mitigations including "action-hash deduplication and loop diversity monitors" ([fixbrokenaiapps.com 2026](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops); [Cogent multi-agent failure playbook 2026](https://cogentinfo.com/resources/when-ai-agents-collide-multi-agent-orchestration-failure-playbook-for-2026)). Our queue is the loop's primary action surface and currently has no dedup.

The problem is not theoretical: `parse_input` already accepts a comma-separated user input that could contain duplicates ("ID1,ID1,ID2"); duplicates would today be processed twice with no warning, the second pass simply re-running refine on an already-passed issue.

## Current Behavior

- `parse_input` (line 32) writes the comma-split queue verbatim — no `sort -u`.
- `enqueue_children` (line 190) and `enqueue_or_skip` (line 301) prepend any new child IDs without checking whether they appear in `recursive-refine-passed.txt`, `recursive-refine-skipped.txt`, or the existing queue.
- The "Decomposed from $PARENT_ID" filter in `detect_children` is the only weak guard, and it only filters by parent-attribution; it does not deduplicate.

## Expected Behavior

- `parse_input` deduplicates the input list (`sort -u` while preserving original order is acceptable; or just `sort -u` since order is reset by depth-first prepending anyway).
- A new "visited.txt" file accumulates every ID that has been dequeued at least once in the current run.
- `dequeue_next` appends the current ID to `visited.txt` immediately on dequeue.
- `enqueue_children` / `enqueue_or_skip` filter the candidate child list against `visited.txt`, `passed.txt`, and the live queue; any collision is logged (`"WARN: refusing to re-enqueue $id (already visited / passed)"`) and dropped.
- If a `size-review` produces only already-visited children, the parent is marked `Skipped (cycle-detected)` rather than `Skipped (no further decomposition)`.

## Proposed Solution

1. In `parse_input` (line 32), pipe the comma-split through `sort -u` after trimming and add `printf '' > .loops/tmp/recursive-refine-visited.txt`.
2. In `dequeue_next` (line 56), after capturing `CURRENT`, append `echo "$CURRENT" >> .loops/tmp/recursive-refine-visited.txt`.
3. Replace the `enqueue_children` body with a python helper that:
   - Reads `recursive-refine-new-children.txt`, `recursive-refine-visited.txt`, `recursive-refine-passed.txt`, and the live queue.
   - Filters out any child whose ID is in any of those three sets.
   - Writes warnings for filtered IDs to stderr.
   - Prepends only the survivors.
4. Apply the same filter to `enqueue_or_skip` (line 301).
5. Add a new skip-reason file `.loops/tmp/recursive-refine-skipped-cycle.txt` populated when post-filter child count is 0 *and* pre-filter count was > 0.
6. Surface counts in `done`: `Skipped (cycle N): IDs...`.

## Acceptance Criteria

- [ ] `parse_input` deduplicates comma-separated input.
- [ ] `recursive-refine-visited.txt` is created in `parse_input` and appended on every `dequeue_next`.
- [ ] `enqueue_children` and `enqueue_or_skip` skip child IDs already present in visited / passed / queue and emit a stderr warning per skipped ID.
- [ ] When all proposed children of a parent are filtered as cycles, that parent is recorded with reason `cycle-detected`.
- [ ] `done` summary distinguishes cycle-detected skips.
- [ ] Unit test using a synthetic queue: feeding duplicate IDs to `parse_input` produces no double-processing.

## Scope Boundaries

- **In scope**: dedup of issue IDs across queue/visited/passed.
- **Out of scope**: detecting *content-equivalent* duplicates (different IDs, identical issue files) — that would require semantic compare and belongs in a separate proposal.
- **Out of scope**: depth caps (ENH-1337) and per-issue budgets (ENH-1339).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — `parse_input` (dedup + visited init), `dequeue_next` (visited append), `enqueue_children` and `enqueue_or_skip` (filter + warn), `done` (cycle skip surface).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/ll_loop.py` — loop runner; consumes the YAML, no direct change.
- `scripts/tests/test_loops_recursive_refine.py` — must cover dedup + cycle skip.

### Similar Patterns
- Any FSM loop using queue/visited tracking under `.loops/tmp/` (cross-check naming conventions in `scripts/little_loops/loops/*.yaml`).

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — new test feeding duplicate IDs through `parse_input` and another forcing a cycle via synthetic size-review output.

### Documentation
- `docs/reference/loops/recursive-refine.md` (if present) — note the cycle-detection guarantee.

### Configuration
- N/A — no new config keys.

## Implementation Steps

1. Update `parse_input` to dedup the comma-split queue (`sort -u` after trim) and initialize an empty `recursive-refine-visited.txt`.
2. Update `dequeue_next` to append the dequeued ID to `recursive-refine-visited.txt`.
3. Replace `enqueue_children`'s body with a Python helper that filters candidates against visited / passed / queue and emits stderr warnings per drop.
4. Apply the same filter helper to `enqueue_or_skip`.
5. Add a `recursive-refine-skipped-cycle.txt` reason file and populate it when post-filter child count is 0 but pre-filter > 0.
6. Surface `Skipped (cycle N): IDs...` in `done`.
7. Add tests for duplicate input and synthetic cycle decomposition.

## Impact

- **Priority**: P2 — Latent infinite-loop risk; currently masked by `max_iterations: 500` but pollutes summary signal.
- **Effort**: Medium — Concentrated in one YAML plus a small Python helper; tests are straightforward.
- **Risk**: Low — All filtering is additive; warn-and-drop is a strict improvement over silent re-entry.
- **Breaking Change**: No — Behavior change only triggers on duplicate/visited IDs, which today produced redundant work.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `safety`

## Status

**Open** | Created: 2026-05-02 | Priority: P2

## References

- `scripts/little_loops/loops/recursive-refine.yaml`: `parse_input`, `dequeue_next`, `enqueue_children`, `enqueue_or_skip`, `done`.
- 2026 research: [Why AI Agents Get Stuck in Loops](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops), [Multi-Agent Orchestration Failure Playbook 2026](https://cogentinfo.com/resources/when-ai-agents-collide-multi-agent-orchestration-failure-playbook-for-2026), [Infinite Agent Loop](https://www.agentpatterns.tech/en/failures/infinite-loop).


## Session Log
- `/ll:format-issue` - 2026-05-03T04:41:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a41e2fe5-b6da-449b-8d60-6b8ddd06d97c.jsonl`
