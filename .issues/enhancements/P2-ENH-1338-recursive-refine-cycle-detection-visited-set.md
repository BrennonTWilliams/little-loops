---
id: ENH-1338
type: ENH
priority: P2
status: done
discovered_date: 2026-05-02
completed_at: 2026-05-03T17:47:10Z
discovered_by: research-synthesis
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
relates_to: ['ENH-1337', 'ENH-1339']
---

# ENH-1338: Cycle Detection / Visited-Set for `recursive-refine` Queue

## Summary

`recursive-refine` has no protection against re-enqueueing an issue ID it has already processed in the current run. If `issue-size-review` ever produces a child whose ID collides with a previously-handled parent (via stale numbering, manual re-creation, or a future sub-loop bug), the queue would loop the same ID indefinitely until `max_iterations: 500` trips. Add an explicit visited-set check in `enqueue_children` and `enqueue_or_skip` that drops any candidate child whose ID already appears in passed/skipped/in-flight tracking.

## Motivation

2026 failure-mode research on recursive planning agents identifies "Loop Drift" — when an agent misinterprets termination signals or produces repetitive actions — as a primary failure mode, with mitigations including "action-hash deduplication and loop diversity monitors" ([fixbrokenaiapps.com 2026](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops); [Cogent multi-agent failure playbook 2026](https://cogentinfo.com/resources/when-ai-agents-collide-multi-agent-orchestration-failure-playbook-for-2026)). Our queue is the loop's primary action surface and currently has no dedup.

The problem is not theoretical: `parse_input` already accepts a comma-separated user input that could contain duplicates ("ID1,ID1,ID2"); duplicates would today be processed twice with no warning, the second pass simply re-running refine on an already-passed issue.

## Current Behavior

- `parse_input` (line 33) writes the comma-split queue verbatim — no `sort -u`.
- `enqueue_children` (line 197) and `enqueue_or_skip` (line 350) prepend any new child IDs without checking whether they appear in `recursive-refine-passed.txt`, `recursive-refine-skipped.txt`, or the existing queue.
- The "Decomposed from $PARENT_ID" filter in `detect_children` is the only weak guard, and it only filters by parent-attribution; it does not deduplicate.

## Expected Behavior

- `parse_input` deduplicates the input list (`sort -u` while preserving original order is acceptable; or just `sort -u` since order is reset by depth-first prepending anyway).
- A new "visited.txt" file accumulates every ID that has been dequeued at least once in the current run.
- `dequeue_next` appends the current ID to `visited.txt` immediately on dequeue.
- `enqueue_children` / `enqueue_or_skip` filter the candidate child list against `visited.txt`, `passed.txt`, and the live queue; any collision is logged (`"WARN: refusing to re-enqueue $id (already visited / passed)"`) and dropped.
- If a `size-review` produces only already-visited children, the parent is marked `Skipped (cycle-detected)` rather than `Skipped (no further decomposition)`.

## Proposed Solution

1. In `parse_input` (line 33), pipe the comma-split through `sort -u` after trimming and add `printf '' > .loops/tmp/recursive-refine-visited.txt`.
2. In `dequeue_next` (line 61), after capturing `CURRENT`, append `echo "$CURRENT" >> .loops/tmp/recursive-refine-visited.txt`.
3. Replace the `enqueue_children` body with a python helper that:
   - Reads `recursive-refine-new-children.txt`, `recursive-refine-visited.txt`, `recursive-refine-passed.txt`, and the live queue.
   - Filters out any child whose ID is in any of those three sets.
   - Writes warnings for filtered IDs to stderr.
   - Prepends only the survivors.
4. Apply the same filter to `enqueue_or_skip` (line 350).
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
- `scripts/little_loops/cli/loop/run.py` — loop runner (`cmd_run`); consumes the YAML, no direct change.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — outer loop that reads `recursive-refine-skipped.txt` in `get_passed_issues` for cross-loop propagation; will NOT automatically pick up `recursive-refine-skipped-cycle.txt` unless cycle-detected IDs are also appended to the shared `recursive-refine-skipped.txt`.
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — same cross-loop propagation concern as `auto-refine-and-implement.yaml`.
- `scripts/tests/test_loops_recursive_refine.py` — must cover dedup + cycle skip.

### Similar Patterns
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` `get_next_issue` — `grep -qxF "$ISSUE_ID" "$SKIP_FILE"` is the existing shell membership-check idiom for exact-line matching against newline-delimited ID files; adapt this for the visited-set filter.
- `scripts/little_loops/loops/autodev.yaml` `enqueue_children` — identical depth-first prepend pattern (`cat new-children.txt; cat queue.txt | grep -v blank`) as `recursive-refine`; both need the same visited-set guard.
- `scripts/little_loops/loops/recursive-refine.yaml` `check_depth` — uses `python3 << 'PYEOF'` heredoc for multi-line logic embedded in a YAML bash script; adopt this pattern for the set-membership filter in `enqueue_children` and `enqueue_or_skip`.

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — new test feeding duplicate IDs through `parse_input` and another forcing a cycle via synthetic size-review output.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — two breaking risks: (1) `TestRecursiveRefineLoop.test_enqueue_or_skip_else_does_not_move_parent` uses `action.split("else", 1)[1]` to isolate the else branch — inserting the visited-set python heredoc before the `if [ -s recursive-refine-new-children.txt ]` block must not push the `else` past the split point; (2) existing `TestDoneSummary` test methods (`test_depth_cap_line_shows_capped_ids`, `test_depth_cap_line_shows_none_when_no_capped_issues`) in `test_loops_recursive_refine.py` need `recursive-refine-skipped-cycle.txt` created in fixture setup or they will fail with a missing-file error once `_DONE_SCRIPT` is extended.

### Documentation
- `docs/reference/loops/recursive-refine.md` (if present) — note the cycle-detection guarantee.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — Summary output example block under `### recursive-refine` is missing the `Skipped (cycle N): IDs...` line; Notes block enumerates temp files by name but omits `recursive-refine-visited.txt` and `recursive-refine-skipped-cycle.txt`.

### Configuration
- N/A — no new config keys.

## Implementation Steps

1. In `parse_input` (line 33), pipe the comma-split through `sort -u` after trimming and add `printf '' > .loops/tmp/recursive-refine-visited.txt` alongside the existing `printf '' >` clears for `passed.txt`, `skipped.txt`, and `skipped-depth.txt`.
2. In `dequeue_next` (line 61), after `CURRENT=$(head -1 ...)` and the tail-rewrite, append `echo "$CURRENT" >> .loops/tmp/recursive-refine-visited.txt`.
3. In `enqueue_children` (line 197), after reading `recursive-refine-new-children.txt` and before prepending to the queue, add a `python3 << 'PYEOF'` heredoc (following the pattern in `check_depth`) that:
   - Reads `visited.txt`, `passed.txt`, and the live queue into a Python `set`.
   - Filters candidates against that set.
   - Writes survivors back to `recursive-refine-new-children.txt`.
   - Prints `WARN: refusing to re-enqueue $id (already visited / passed)` to stderr per dropped ID.
4. Apply the identical filter block to `enqueue_or_skip` (line 350), before the `enqueue_children`-style prepend path and the no-children skip path.
5. In `enqueue_or_skip`, when all proposed children are filtered out (post-filter count 0, pre-filter count > 0), append the parent to `recursive-refine-skipped-cycle.txt` in addition to `recursive-refine-skipped.txt` (so outer loops that only read `recursive-refine-skipped.txt` propagate the skip correctly).
6. In `done` (line 403), add a fourth output line `Skipped (cycle N): IDs...` reading from `recursive-refine-skipped-cycle.txt`, following the same `sort -u` + `grep -c` + `tr '\n' ','` pattern as the existing depth-cap line.
7. Add tests to `scripts/tests/test_loops_recursive_refine.py` following the `_bash(script, tmp_path)` / `_DONE_SCRIPT` patterns in `TestDoneSummary`:
   - `TestParseInputDedup`: write `recursive-refine-queue.txt` with duplicate IDs; assert the queue file contains each ID exactly once.
   - `TestVisitedSetFilter`: pre-populate `recursive-refine-visited.txt` with a candidate ID; assert `enqueue_children` drops it and emits the stderr `WARN` message.
   - `TestCycleSkipReason`: force post-filter count = 0 via all-visited candidates; assert parent is written to `recursive-refine-skipped-cycle.txt`.
   - `TestDoneSummaryCycle`: assert `done` emits `Skipped (cycle N): ...` line when `recursive-refine-skipped-cycle.txt` is non-empty.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `TestDoneSummary._DONE_SCRIPT` in `scripts/tests/test_loops_recursive_refine.py` — extend the class constant with the `CYCLE_SKIPPED_IDS` read block and corresponding `printf` line to mirror the updated `done` action; add `(loops_tmp / "recursive-refine-skipped-cycle.txt").write_text("")` to the fixture setup of both existing `TestDoneSummary` test methods so they don't fail with a missing-file error.
9. Add `TestVisitedSetAppend` class to `scripts/tests/test_loops_recursive_refine.py` — follows `TestDequeueDepth` pattern; pre-populate queue with one ID and create an empty `recursive-refine-visited.txt`; run `dequeue_next` bash snippet with the new `echo "$CURRENT" >> .loops/tmp/recursive-refine-visited.txt` line; assert the dequeued ID appears in `recursive-refine-visited.txt`.
10. Verify `scripts/tests/test_builtin_loops.py` `TestRecursiveRefineLoop.test_enqueue_or_skip_else_does_not_move_parent` still passes after YAML edits — insert the python visited-set filter block before `if [ -s recursive-refine-new-children.txt ]`, not inside the `if` or `else` body, to preserve the `else` branch position that the test splits on.
11. Update `docs/guides/LOOPS_GUIDE.md` — add `Skipped (cycle N): IDs...` to the Summary output example block; append `recursive-refine-visited.txt` and `recursive-refine-skipped-cycle.txt` to the Notes temp-file enumeration sentence.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Membership check idiom**: `grep -qxF "$ID" "$FILE"` (quiet, exact-line, fixed-string) is the existing shell pattern for O(n) set membership against a newline-delimited file; used in `sprint-refine-and-implement.yaml`:`get_next_issue`.
- **Python heredoc pattern**: `check_depth` state (line 304) uses `python3 << 'PYEOF' ... PYEOF` for multi-line Python embedded in YAML bash; use the same form for the candidate-filter logic.
- **Cross-loop propagation**: `auto-refine-and-implement.yaml`:`get_passed_issues` and `sprint-refine-and-implement.yaml`:`get_passed_issues` both `cat recursive-refine-skipped.txt >> <outer-loop-skipped>.txt`. Cycle-detected IDs **must also** be appended to `recursive-refine-skipped.txt` (Step 5 above) so outer loops inherit the skip without modification.

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

- `scripts/little_loops/loops/recursive-refine.yaml`: `parse_input` (line 33), `dequeue_next` (line 61), `enqueue_children` (line 197), `enqueue_or_skip` (line 350), `done` (line 403).
- 2026 research: [Why AI Agents Get Stuck in Loops](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops), [Multi-Agent Orchestration Failure Playbook 2026](https://cogentinfo.com/resources/when-ai-agents-collide-multi-agent-orchestration-failure-playbook-for-2026), [Infinite Agent Loop](https://www.agentpatterns.tech/en/failures/infinite-loop).

## Resolution

Implemented cycle detection / visited-set guard across all queue-management states in `recursive-refine.yaml`:

- `parse_input`: Added `printf '' > .loops/tmp/recursive-refine-visited.txt` to initialise the visited set each run; added `sort -u` to deduplicate comma-separated input before writing the queue.
- `dequeue_next`: Appends the dequeued ID to `recursive-refine-visited.txt` immediately after pop.
- `enqueue_children` and `enqueue_or_skip`: Both now run a `python3` heredoc filter (following the `check_depth` pattern) that builds a set from `visited.txt`, `passed.txt`, and the live queue, filters candidate children, writes survivors back, and logs a `WARN` per dropped ID. `enqueue_or_skip` additionally writes the parent to `recursive-refine-skipped-cycle.txt` when all children are filtered (pre-count > 0, post-count = 0).
- `done`: Extended with a `CYCLE_SKIPPED_IDS` tracking block and a `Skipped (cycle N): IDs...` output line.
- `docs/guides/LOOPS_GUIDE.md`: Added cycle line to summary example; added `recursive-refine-visited.txt` and `recursive-refine-skipped-cycle.txt` to the Notes temp-file list.
- `scripts/tests/test_loops_recursive_refine.py`: Updated `_DONE_SCRIPT` with cycle tracking; fixed existing `TestDoneSummary` tests to create `skipped-cycle.txt`; added `TestParseInputDedup`, `TestVisitedSetAppend`, `TestVisitedSetFilter`, `TestCycleSkipReason`, and two new `TestDoneSummary` cycle methods. All 310 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-05-03T17:47:10Z - `` (current session)
- `/ll:ready-issue` - 2026-05-03T17:37:25 - `339796a8-14ef-4a6b-a01f-1d0889b22148.jsonl`
- `/ll:confidence-check` - 2026-05-03T18:00:00 - `bf6dafe2-bae1-437a-bba3-3b9e3937c4d5.jsonl`
- `/ll:wire-issue` - 2026-05-03T17:33:14 - `bf6dafe2-bae1-437a-bba3-3b9e3937c4d5.jsonl`
- `/ll:refine-issue` - 2026-05-03T17:28:06 - `0e3e3565-4753-48d2-9c7f-53a2ce265d6e.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:54 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:format-issue` - 2026-05-03T04:41:50 - `a41e2fe5-b6da-449b-8d60-6b8ddd06d97c.jsonl`
