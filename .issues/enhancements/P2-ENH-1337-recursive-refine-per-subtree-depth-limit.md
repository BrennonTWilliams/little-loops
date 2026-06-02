---
id: ENH-1337
type: ENH
priority: P2
status: done
discovered_date: 2026-05-02
discovered_by: research-synthesis
decision_needed: false
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
size: Very Large
relates_to: ['ENH-1338', 'ENH-1339']
completed_at: 2026-05-10T00:00:00Z
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`check_depth` gate state pattern** (model: `check_refine_limit` in `refine-to-ready-issue.yaml`):
```yaml
check_depth:
  action: |
    MAX_DEPTH=$(python3 << 'PYEOF'
    import json
    from pathlib import Path
    p = Path('.ll/ll-config.json')
    cfg = {}
    if p.exists():
        try:
            cfg = json.loads(p.read_text())
        except Exception:
            pass
    print(cfg.get('commands', {}).get('recursive_refine', {}).get('max_depth', ${context.max_depth}))
    PYEOF
    )
    [ -z "$MAX_DEPTH" ] && MAX_DEPTH=${context.max_depth}
    CURRENT_DEPTH=$(cat .loops/tmp/recursive-refine-current-depth.txt 2>/dev/null || echo 0)
    if [ "$CURRENT_DEPTH" -ge "$MAX_DEPTH" ]; then
      echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped-depth.txt
      echo 1
    else
      echo 0
    fi
  action_type: shell
  evaluate:
    type: output_numeric
    operator: lt
    target: 1
  on_yes: run_size_review
  on_no: dequeue_next
  on_error: run_size_review
```

**Depth-map lookup in `dequeue_next`** (append after the existing head/tail pop):
```bash
DEPTH=$(grep "^$CURRENT " .loops/tmp/recursive-refine-depth-map.txt 2>/dev/null | awk '{print $2}' || echo 0)
printf '%s' "$DEPTH" > .loops/tmp/recursive-refine-current-depth.txt
```

**`parse_input` additions** (after existing queue initialization):
```bash
while IFS= read -r id; do echo "$id 0"; done \
  < .loops/tmp/recursive-refine-queue.txt \
  > .loops/tmp/recursive-refine-depth-map.txt
> .loops/tmp/recursive-refine-skipped-depth.txt
```

**`enqueue_children` / `enqueue_or_skip` addition** (after prepending each child to queue):
```bash
PARENT_DEPTH=$(cat .loops/tmp/recursive-refine-current-depth.txt 2>/dev/null || echo 0)
while IFS= read -r child; do
  echo "$child $((PARENT_DEPTH + 1))" >> .loops/tmp/recursive-refine-depth-map.txt
done < .loops/tmp/recursive-refine-new-children.txt
```

**`done` state additions** (read both skip files):
```bash
DEPTH_SKIPPED_IDS=$(cat .loops/tmp/recursive-refine-skipped-depth.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' | sort -u || true)
DEPTH_COUNT=$(echo "$DEPTH_SKIPPED_IDS" | grep -c '[^[:space:]]' || echo 0)
DEPTH_LIST=$(echo "$DEPTH_SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')
printf 'Skipped (depth-cap %d): %s\n' "$DEPTH_COUNT" "$${DEPTH_LIST:-none}"
```

**`config-schema.json` addition** (model: existing `commands.confidence_gate` object at lines 351–421):
```json
"recursive_refine": {
  "type": "object",
  "description": "Configuration for the recursive-refine loop",
  "properties": {
    "max_depth": {
      "type": "integer",
      "minimum": 1,
      "default": 3,
      "description": "Maximum decomposition depth per subtree (default 3)"
    }
  }
}
```

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
- `config-schema.json` — add `commands.recursive_refine` object with `max_depth` integer property (see existing `commands.confidence_gate` object at lines 351–421 as the pattern).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/automation.py` — `CommandsConfig` dataclass (lines 152–172) must be extended with a `recursive_refine` field (new `RecursiveRefineConfig` dataclass with `max_depth: int = 3`), following the existing `ConfidenceGateConfig` pattern.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/ll_loop.py` — loop runner; no direct change but consumes the YAML.
- `scripts/tests/test_loops_recursive_refine.py` — exercises the loop end-to-end.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — calls `recursive-refine` as a sub-loop (`refine_issue` state, `with:` binding); its `get_passed_issues` state reads `.loops/tmp/recursive-refine-skipped.txt` to accumulate skips. **Depth-capped IDs must also be written to `recursive-refine-skipped.txt`** (not just `recursive-refine-skipped-depth.txt`), otherwise `get_passed_issues` misses them and they are re-queued on the next outer iteration.
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — calls `recursive-refine` as a sub-loop (`refine_issue` state, `context_passthrough: true`); same `get_passed_issues` / `recursive-refine-skipped.txt` coupling as above.
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — calls `recursive-refine` as a sub-loop (`refine_unresolved` state, `context_passthrough: true`); does not read skipped.txt directly, no breakage.

### Similar Patterns
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:check_refine_limit` — reads a counter from a tmp file, prints the value, evaluated with `output_numeric` + `operator: lt` + `target:`; exact model for the `check_depth` gate state.
- `scripts/little_loops/loops/recursive-refine.yaml:check_broke_down` — existing gate in the same loop using `output_numeric`; shows the on_yes/on_no/on_error routing convention.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:check_lifetime_limit` — Python inline config-override pattern (`cfg.get('commands', {}).get('max_refine_count', ${context.max_refine_count})`) to use in `check_depth` for reading `commands.recursive_refine.max_depth` from `.ll/ll-config.json`.

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — **file does not yet exist; must be created**. Follow the fixture pattern from `scripts/tests/test_ll_loop_execution.py:TestEndToEndExecution` and the `_make_mock_popen_factory` helper (lines 26–39) for mocking subprocess. Add a synthetic 4-level decomposition fixture with `max_depth: 2`.
- `scripts/tests/test_builtin_loops.py:TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` — will automatically validate the new `check_depth` state on the next run; no changes needed.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestRecursiveRefineLoop.test_required_states_exist` (line 1612) — **will break**: `required` set does not include `"check_depth"`; add it.
- `scripts/tests/test_builtin_loops.py:TestRecursiveRefineLoop.test_recheck_scores_on_no_routes_to_run_size_review` (line 1777) — **will break**: asserts `recheck_scores.on_no == "run_size_review"`; after inserting `check_depth`, update to assert `== "check_depth"`.
- `scripts/tests/test_builtin_loops.py:TestRecursiveRefineLoop.test_recheck_scores_on_error_routes_to_run_size_review` (line 1784) — **will break**: same situation; update to assert `on_error == "check_depth"`.
- `scripts/tests/test_config_schema.py` — **new test needed**: `TestConfigSchema.test_recursive_refine_in_schema` — assert `commands.recursive_refine` key exists with `max_depth` (`type: integer`, `minimum: 1`, `default: 3`), following the `test_commands_rate_limits_block` pattern (line 56).

### Documentation
- `docs/reference/loops/recursive-refine.md` (if present) — document `max_depth` parameter.
- `config-schema.json` — add `commands.recursive_refine.max_depth`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — 4 sub-changes needed: (1) add `max_depth` row to the "Required context variables" table (section `recursive-refine`); (2) update the FSM flow diagram to show `recheck_scores → check_depth → run_size_review`; (3) add `Skipped (depth-cap N): ...` line to the summary output example block; (4) add the three new tmp files (`recursive-refine-depth-map.txt`, `recursive-refine-current-depth.txt`, `recursive-refine-skipped-depth.txt`) to the "Notes" tmp-file list.
- `docs/reference/CONFIGURATION.md` — add a row for `commands.recursive_refine.max_depth` to the `### commands` table (line ~336), with default `3` and config path.

### Configuration
- `.ll/ll-config.json` — new optional `commands.recursive_refine.max_depth` override.

## Implementation Steps

1. Wire `max_depth` into the YAML `context:` block and `config-schema.json`, with `.ll/ll-config.json` override resolution.
2. Initialize the depth map in `parse_input` (depth `0` per root) and persist it under `.loops/tmp/`.
3. Update `dequeue_next` to look up the dequeued ID's depth and write it to `.loops/tmp/recursive-refine-current-depth.txt`.
4. Insert the `check_depth` gate state between `recheck_scores` and `run_size_review`; route over-cap items to skipped with reason `depth-cap`.
5. Update `enqueue_children` and `enqueue_or_skip` to append `child_id (parent_depth + 1)` to the depth map.
6. Partition `done`-summary skip lines by reason file and add `Skipped (depth-cap N)`. **Note**: depth-capped IDs must also be appended to `recursive-refine-skipped.txt` (in addition to `recursive-refine-skipped-depth.txt`) so that outer-loop callers (`auto-refine-and-implement`, `sprint-refine-and-implement`) accumulate them correctly in `get_passed_issues`.
7. Add a synthetic 4-level test in `scripts/tests/test_loops_recursive_refine.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/config/automation.py` — add `RecursiveRefineConfig` dataclass with `max_depth: int = 3` and extend `CommandsConfig` with a `recursive_refine: RecursiveRefineConfig` field, following the `ConfidenceGateConfig` pattern.
9. Update `scripts/tests/test_builtin_loops.py` — fix 3 breaking tests: add `"check_depth"` to `test_required_states_exist` required set; update `test_recheck_scores_on_no_routes_to_run_size_review` and `test_recheck_scores_on_error_routes_to_run_size_review` to assert `== "check_depth"`.
10. Add `TestConfigSchema.test_recursive_refine_in_schema` to `scripts/tests/test_config_schema.py`.
11. Update `docs/guides/LOOPS_GUIDE.md` — context-variables table, FSM flow diagram, summary output example, tmp-file list.
12. Update `docs/reference/CONFIGURATION.md` — add `commands.recursive_refine.max_depth` row to the `### commands` table.

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

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-03
- **Reason**: Issue too large for single session

### Decomposed Into
- ENH-1344: Implement per-subtree depth limit in `recursive-refine` (YAML, config schema, Python config, all tests)
- ENH-1345: Document `max_depth` parameter in guides and reference (docs only, depends on ENH-1344)

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-03T15:44:10 - `9f5908fa-e7cf-482b-a91b-52624eb2a99c.jsonl`
- `/ll:issue-size-review` - 2026-05-03T00:00:00 - `9f5908fa-e7cf-482b-a91b-52624eb2a99c.jsonl`
- `/ll:confidence-check` - 2026-05-03T17:00:00 - `8b01ba85-e44e-43fc-a0a9-22d8ec116b3c.jsonl`
- `/ll:wire-issue` - 2026-05-03T15:36:56 - `2bfe7ba9-90e4-4b2f-909d-e4508c1b4461.jsonl`
- `/ll:refine-issue` - 2026-05-03T15:30:00 - `d1e1f2e2-5a68-43cc-a7e0-9ee4146c15bd.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:54 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:format-issue` - 2026-05-03T04:41:50 - `a41e2fe5-b6da-449b-8d60-6b8ddd06d97c.jsonl`
