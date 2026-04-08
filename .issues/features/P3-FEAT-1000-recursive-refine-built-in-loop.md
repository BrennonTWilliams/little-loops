---
id: FEAT-1000
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-08
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# FEAT-1000: Recursive Refine Built-In Loop

## Summary

Add a new built-in FSM loop `recursive-refine` that refines one or more issues to readiness, with recursive breakdown: if an issue fails confidence thresholds and `issue-size-review` decomposes it into child issues, the loop automatically refines each child before returning—continuing until all issues in the tree meet their thresholds or are skipped.

## Current Behavior

`refine-to-ready-issue` processes one issue at a time. It invokes `issue-size-review` when the lifetime refine cap is reached, but does not recursively refine the child issues produced by the breakdown. Callers must manually re-invoke the loop for each child issue.

## Expected Behavior

- The loop accepts a single issue ID **or** a comma-separated list of issue IDs as input.
- For each issue, run the refine → confidence-check cycle (mirroring `refine-to-ready-issue`).
- When confidence thresholds are not met:
  - Run `/ll:issue-size-review ISSUE_ID --auto`.
  - **If the review breaks the issue into sub-issues**: collect those child IDs and recursively apply the full loop to each child before moving on.
  - **If the review does not break the issue up**: mark the issue as **Skipped** and continue to the next issue in the queue.
- Continue recursively until every issue in the entire tree (original + all descendants) either passes thresholds or is skipped.
- Emit a final summary: passed / skipped / failed counts with issue IDs.

## Motivation

Automating full-depth refinement removes the manual step of chasing down child issues after a breakdown. Users who queue a batch of issues should get a single unattended loop run that leaves every refineable issue ready, without needing to intervene when the size-review decides to decompose an issue.

## Acceptance Criteria

- `ll-loop recursive-refine --input "ISSUE_ID"` accepts a single issue ID and processes it through the refine → confidence-check cycle.
- `ll-loop recursive-refine --input "ID1,ID2,ID3"` accepts a comma-separated list and processes each issue in order.
- When confidence thresholds are not met and `issue-size-review` produces child issues, each child is prepended to the queue and processed before the next sibling.
- When `issue-size-review` does not produce child issues, the current issue is marked **Skipped** and the loop continues with the next queued item.
- The loop terminates only when every issue in the full tree (original + all descendants) has either passed thresholds or been skipped.
- Final output includes a structured summary: passed (count + IDs), skipped (count + IDs), failed (count + IDs).
- Queue state persists to `.loops/tmp/recursive-refine-queue` between iterations; skipped IDs persist to `.loops/tmp/recursive-refine-skipped`.
- The loop is auto-discovered by `ll-loop` from `scripts/little_loops/loops/` with no CLI changes required.

## Proposed Solution

Create `scripts/little_loops/loops/recursive-refine.yaml` as a new built-in loop, modeled on `refine-to-ready-issue.yaml`.

Key structural changes:
- **Queue management**: persist a work queue (e.g. `.loops/tmp/recursive-refine-queue`) initialized from the comma-separated input. Process one ID per iteration; finished IDs are removed, new child IDs are appended.
- **Recursion via queue**: rather than true recursion (which FSMs don't support), child issues are pushed onto the front of the queue so they are processed before the next sibling.
- **Skip tracking**: a `.loops/tmp/recursive-refine-skipped` file accumulates skipped IDs; the final `done` state reads both files to produce the summary.
- **Threshold evaluation**: reuse the same `shell_exit` confidence-check pattern from `refine-to-ready-issue.yaml`.
- States: `parse_input → dequeue_next → format_issue → refine_issue → wire_issue → confidence_check → size_review → enqueue_children_or_skip → check_queue → done / failed`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Recommended: delegate to `refine-to-ready-issue` as a sub-loop** instead of reimplementing confidence-check / wire / format states. Established pattern (`auto-refine-and-implement.yaml:35-39`):

```yaml
run_refine:
  loop: refine-to-ready-issue
  context_passthrough: true
  on_success: check_confidence          # sub-loop ended via `done`
  on_failure: capture_baseline          # sub-loop ended via `failed` — trigger size-review
  on_error: capture_baseline
```

After the sub-loop succeeds (`done`), verify scores with `ll-issues show --json` to distinguish confidence-pass `done` from breakdown-`done`. If scores pass → `dequeue_next`; if not → `capture_baseline` → `size_review`.

**Child ID extraction (concrete approach):** The `--auto` output does not list child IDs. Use a before/after diff of `ll-issues list --json` with `comm -13` (see Integration Map research findings). Store pre-IDs in `.loops/tmp/recursive-refine-pre-ids.txt` immediately before running `size_review`, then diff in `enqueue_or_skip`.

**Summary generation in `done`:** Skipped IDs are in `.loops/tmp/recursive-refine-skipped.txt` (one per line). "Passed" can be inferred by diffing the original queue (save it at `parse_input` to `.loops/tmp/recursive-refine-original-queue.txt`) against the skipped file.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — new loop (create)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — reference for pattern reuse (read-only)
- `scripts/little_loops/loops/README.md` — canonical built-in loop table; add `recursive-refine` to the Issue Management section (alongside `refine-to-ready-issue` and `auto-refine-and-implement`) [Wiring pass added by `/ll:wire-issue`]
- `docs/guides/LOOPS_GUIDE.md` — Issue Management loop table at lines 267–278; add `recursive-refine` row [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/ll_loop.py` — auto-discovers loops in `loops/`; no change required if naming convention is followed
- `.claude-plugin/plugin.json` — lists built-in loops; add `recursive-refine` entry

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/config_cmds.py` — imports and calls `get_builtin_loops_dir()` for `ll-loop install`; auto-discovers new loop; no code change required
- `scripts/little_loops/cli/loop/run.py` — imports `get_builtin_loops_dir()` for `--builtin` flag resolution; auto-discovers new loop; no code change required
- `scripts/little_loops/cli/loop/info.py` — imports `get_builtin_loops_dir()` for `ll-loop list`; auto-discovers new loop; no code change required
- `scripts/little_loops/fsm/executor.py` — implements `context_passthrough` and `loop:` sub-loop delegation that the new loop's `run_refine` state depends on; no code change required

### Similar Patterns
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — confidence-check, wire, lifetime-cap logic to reuse
- `scripts/little_loops/loops/` — queue-file pattern used by other multi-item loops

### Tests
- `scripts/tests/loops/test_recursive_refine.py` — new test file; cover: single ID input, list input, recursive breakdown, skip path, all-pass path

_Wiring pass added by `/ll:wire-issue`:_
- **LOCATION CORRECTION**: `scripts/tests/loops/` directory does **not exist**. Add test as a new `TestRecursiveRefineLoop` class in `scripts/tests/test_builtin_loops.py` instead, following the `TestPromptAcrossIssuesLoop` pattern at lines 709–774 (YAML fixture → assert required states, queue file references, sub-loop delegation, terminal state). Alternatively, create the `scripts/tests/loops/` directory as part of this implementation.
- `scripts/tests/test_builtin_loops.py:46-87` — `test_expected_loops_exist()` `expected` set must include `"recursive-refine"` (already noted in issue); test uses exact-set equality — the YAML existing without the name in `expected` causes immediate failure [existing, update]
- `scripts/tests/test_fsm_fragments.py:800-823` — `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration()` has a hardcoded `migration_targets` list of 10 loops; if `recursive-refine.yaml` uses `fragment: shell_exit` (it will — `dequeue_next` and `parse_input` states use `shell_exit`), must add `"recursive-refine"` to this list or the migration validation test will fail [existing, update]

### Documentation
- `docs/loops/BUILT-IN-LOOPS.md` — add `recursive-refine` entry
- `commands/create-loop.md` — mention `recursive-refine` as reference for queue-based patterns

_Wiring pass added by `/ll:wire-issue`:_
- **STALE REFERENCE**: `docs/loops/BUILT-IN-LOOPS.md` does **not exist** (the `docs/loops/` directory does not exist). The canonical built-in loop reference is `scripts/little_loops/loops/README.md` — already added to Files to Modify above.
- `docs/guides/LOOPS_GUIDE.md:267-278` — hardcoded Issue Management loop table; `recursive-refine` must be added as a row (already added to Files to Modify above)
- `docs/reference/CONFIGURATION.md:327-331` — `max_refine_count` description prose names only `refine-to-ready-issue` as the enforcing loop; update to also mention `recursive-refine` (which enforces the same limit via sub-loop delegation) [update]

### Configuration
- `context.readiness_threshold` / `context.outcome_threshold` / `context.max_refine_count` — canonical in `ll-config.json`, same as `refine-to-ready-issue`

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:332` — description string for `max_refine_count` reads "enforced by the `refine-to-ready-issue` loop"; update to mention `recursive-refine` shares the same limit via sub-loop delegation [update, low priority]
- `skills/configure/areas.md:392` — interactive configure question text describes `max_refine_count` as "enforced by the refine-to-ready-issue loop"; same update needed [update, low priority]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CORRECTION — `plugin.json` does not need modification.** Built-in loops are auto-discovered purely via `scripts/little_loops/cli/loop/_helpers.py:88-114` (`get_builtin_loops_dir().glob("*.yaml")`). There is no `loops` field in `.claude-plugin/plugin.json` and no existing loop entries to follow. Dropping the `plugin.json` entry from the "Files to Modify" list.

**REQUIRED addition — test registry must be updated:**
- `scripts/tests/test_builtin_loops.py:45-86` — `test_expected_loops_exist()` checks the exact set of built-in loop stems; must add `"recursive-refine"` or this test will fail

**Sub-loop invocation pattern (confirmed working):**
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:35-39` — canonical pattern for delegating to `refine-to-ready-issue` via `loop:` key with `context_passthrough: true`
- `scripts/little_loops/loops/issue-refinement.yaml:28-33` — same pattern; `on_success`/`on_failure` routes distinguish outcome

**Queue file pattern:**
- `scripts/little_loops/loops/prompt-across-issues.yaml:26-94` — canonical newline-delimited queue under `.loops/tmp/`, populated via `tr ',' '\n'`, consumed with `head -1`, advanced with `tail -n +2`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:18-28` — skip-list with `paste -sd ','` collapse for `--skip` argument

**Fragment library:**
- `scripts/little_loops/loops/lib/common.yaml:17-20` — `shell_exit` fragment (sets `action_type: shell` + `evaluate: type: exit_code`); used in all queue pop / flag check states

**Child ID extraction — key implementation gap:**
`/ll:issue-size-review --auto` single-line output format (`[ID] decomposed: N child issues`) does NOT include child IDs. The full output contains a `### Created Issues` section, but this is prose from Claude's response. The reliable extraction approach is a before/after diff of `ll-issues list --json`:
```bash
# Before size-review:
ll-issues list --json | python3 -c "import json,sys; print('\n'.join(i['id'] for i in json.load(sys.stdin)))" \
  | sort > .loops/tmp/recursive-refine-pre-ids.txt

# After size-review (in enqueue_or_skip state):
ll-issues list --json | python3 -c "import json,sys; print('\n'.join(i['id'] for i in json.load(sys.stdin)))" \
  | sort > .loops/tmp/recursive-refine-post-ids.txt

CHILDREN=$(comm -13 .loops/tmp/recursive-refine-pre-ids.txt .loops/tmp/recursive-refine-post-ids.txt)
```

**Tmp flag reset per issue:**
`refine-to-ready-issue.yaml:resolve_issue` (lines 16-24) reinitializes `.loops/tmp/refine-to-ready-refine-count` and `.loops/tmp/refine-to-ready-wire-done` to `0` on every call. Sub-loop invocations therefore reset these automatically — no manual cleanup needed in `recursive-refine`.

## Implementation Steps

1. Read `refine-to-ready-issue.yaml` to extract the confidence-check, wire, and refine state patterns.
2. Design queue-file schema: newline-delimited IDs in `.loops/tmp/recursive-refine-queue`; skipped IDs in `.loops/tmp/recursive-refine-skipped`.
3. Implement `parse_input` state: split comma-separated input, write initial queue.
4. Implement `dequeue_next` → `format_issue` → `refine_issue` → `wire_issue` → `confidence_check` chain (mirrors `refine-to-ready-issue` single-issue path).
5. Implement `size_review` state: invoke `/ll:issue-size-review --auto`, capture output to detect whether child issues were created.
6. Implement `enqueue_children_or_skip`: parse child IDs from size-review output; prepend to queue or append to skipped file.
7. Implement `check_queue`: if queue non-empty loop to `dequeue_next`, else go to `done`.
8. Implement `done` state: emit summary from queue (empty = all processed) + skipped file.
9. Register in `plugin.json`; add test coverage.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Concrete steps with exact file references:

1. **Read source patterns**: `scripts/little_loops/loops/refine-to-ready-issue.yaml` (all states) and `scripts/little_loops/loops/auto-refine-and-implement.yaml:18-51` (skip-list + sub-loop pattern). These are the two canonical references.

2. **Design queue files** (all under `.loops/tmp/`):
   - `recursive-refine-queue.txt` — newline-delimited pending IDs; `head -1` pop, `tail -n +2` advance (pattern: `prompt-across-issues.yaml:44-94`)
   - `recursive-refine-skipped.txt` — append-only; one ID per line (pattern: `auto-refine-and-implement.yaml:48-51`)
   - `recursive-refine-original-queue.txt` — copy of initial queue for summary diff
   - `recursive-refine-pre-ids.txt` — snapshot before `size_review` for child detection

3. **`parse_input` state**: validate `${context.input}` is non-empty (`prompt-across-issues.yaml:27-29`); split via `echo "${context.input}" | tr ',' '\n' | xargs -I{} echo {} > .loops/tmp/recursive-refine-queue.txt`; copy to `recursive-refine-original-queue.txt`; use `fragment: shell_exit` → `on_yes: dequeue_next`, `on_no: done` (empty input), `on_error: failed`.

4. **`dequeue_next` state**: `head -1 .loops/tmp/recursive-refine-queue.txt` to get current ID; exit 1 if empty → `done`; `tail -n +2` advance; `capture: current_issue_id`; use `fragment: shell_exit` (pattern: `prompt-across-issues.yaml:44-56, 84-94`).

5. **`run_refine` state**: use `loop: refine-to-ready-issue` with `context_passthrough: true` (pattern: `auto-refine-and-implement.yaml:35-39`). Route `on_success: check_passed` (verify scores), `on_failure: capture_baseline`, `on_error: capture_baseline`.

6. **`check_passed` state**: inline `evaluate: type: shell_exit` Python block reading `ll-issues show ${captured.current_issue_id.output} --json` for confidence/outcome scores (pattern: `refine-to-ready-issue.yaml:110-137`). Route `on_yes: dequeue_next`, `on_no: capture_baseline`.

7. **`capture_baseline` state**: snapshot `ll-issues list --json` IDs to `.loops/tmp/recursive-refine-pre-ids.txt` before size-review (see child ID extraction approach in Proposed Solution research findings). Use `fragment: shell_exit` → `on_yes: size_review`.

8. **`size_review` state**: `action: "/ll:issue-size-review ${captured.current_issue_id.output} --auto"`, `action_type: slash_command`, `next: enqueue_or_skip`.

9. **`enqueue_or_skip` state**: diff current `ll-issues list --json` IDs against `.loops/tmp/recursive-refine-pre-ids.txt` using `comm -13`; if children found, write them to front of queue; if none found, append current ID to skipped file. `next: dequeue_next`.

10. **`done` state**: emit structured summary — read `recursive-refine-skipped.txt` for skipped IDs; diff `recursive-refine-original-queue.txt` vs skipped to compute passed IDs; print counts.

11. **Update `scripts/tests/test_builtin_loops.py:45-86`** (`test_expected_loops_exist`): add `"recursive-refine"` to the `expected` set, or the all-loops registry test will fail immediately.

12. **Add per-loop test class** following the pattern at `scripts/tests/test_builtin_loops.py:280-376`: assert required states exist, queue file names, sub-loop invocation field, and `--auto` flag in size-review action.

**NOTE: Step 9 ("Register in `plugin.json`") from the original steps is incorrect** — no plugin.json changes are needed. Built-in loops are discovered automatically from `scripts/little_loops/loops/*.yaml` by `_helpers.py:get_builtin_loops_dir()`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

12. Update `scripts/tests/test_builtin_loops.py:48-85` — add `"recursive-refine"` to the `expected` set in `test_expected_loops_exist()`; this is a hard failure the moment `recursive-refine.yaml` is created
13. Update `scripts/tests/test_fsm_fragments.py:800-823` — add `"recursive-refine"` to the `migration_targets` list in `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration()`; required because the loop uses `fragment: shell_exit` in queue-pop states
14. Add `TestRecursiveRefineLoop` class to `scripts/tests/test_builtin_loops.py` (NOT a new file under `scripts/tests/loops/` — that directory does not exist); follow the `TestPromptAcrossIssuesLoop` pattern at lines 709–774: assert `name`, `initial`, required states, queue file references in actions, sub-loop delegation state has `loop: refine-to-ready-issue` + `context_passthrough: true`, terminal state has `terminal: true`
15. Update `scripts/little_loops/loops/README.md` — add `recursive-refine` row to the Issue Management loop table (alongside `refine-to-ready-issue` and `auto-refine-and-implement`)
16. Update `docs/guides/LOOPS_GUIDE.md:267-278` — add `recursive-refine` row to the Issue Management loop table
17. Update `docs/reference/CONFIGURATION.md:327-331` — extend `max_refine_count` description to mention `recursive-refine` shares this limit via sub-loop delegation
18. (Low priority) Update `config-schema.json:332` and `skills/configure/areas.md:392` — description strings for `max_refine_count` that currently name only `refine-to-ready-issue`

## Impact

- **Priority**: P3 - Meaningful quality-of-life improvement for batch refinement workflows; not blocking.
- **Effort**: Medium - New loop with non-trivial queue management; reuses existing patterns.
- **Risk**: Low - Self-contained YAML file; no changes to existing loops or Python core.
- **Breaking Change**: No

## Use Case

A user queues five issues for refinement before a sprint. Two of those issues are too large; `issue-size-review` breaks each into two children. Without `recursive-refine` the user must notice the breakdowns and re-run the loop four more times. With `recursive-refine`, a single invocation processes all nine resulting issues unattended and reports which passed, which were skipped, and which failed.

## API/Interface

```yaml
# Loop invocation via ll-loop
# Single issue
ll-loop recursive-refine --input "BUG-042"

# Comma-separated batch
ll-loop recursive-refine --input "BUG-042,ENH-099,FEAT-100"
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loops`, `automation`, `captured`

## Status

**Open** | Created: 2026-04-08 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aac519d4-dcc3-4649-920c-575683041b44.jsonl`
- `/ll:wire-issue` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:refine-issue` - 2026-04-08T18:55:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/451177be-c4b4-4a6a-8b1e-a1c3c0bc05ec.jsonl`
- `/ll:format-issue` - 2026-04-08T18:47:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/02736c69-81a6-4e9d-b322-20da085cbdcf.jsonl`
- `/ll:capture-issue` - 2026-04-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/77c66dec-3548-4e36-88fe-129cc8627555.jsonl`
