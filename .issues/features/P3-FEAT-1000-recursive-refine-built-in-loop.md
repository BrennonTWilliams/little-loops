---
id: FEAT-1000
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-08
discovered_by: capture-issue
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

## Proposed Solution

Create `scripts/little_loops/loops/recursive-refine.yaml` as a new built-in loop, modeled on `refine-to-ready-issue.yaml`.

Key structural changes:
- **Queue management**: persist a work queue (e.g. `.loops/tmp/recursive-refine-queue`) initialized from the comma-separated input. Process one ID per iteration; finished IDs are removed, new child IDs are appended.
- **Recursion via queue**: rather than true recursion (which FSMs don't support), child issues are pushed onto the front of the queue so they are processed before the next sibling.
- **Skip tracking**: a `.loops/tmp/recursive-refine-skipped` file accumulates skipped IDs; the final `done` state reads both files to produce the summary.
- **Threshold evaluation**: reuse the same `shell_exit` confidence-check pattern from `refine-to-ready-issue.yaml`.
- States: `parse_input → dequeue_next → format_issue → refine_issue → wire_issue → confidence_check → size_review → enqueue_children_or_skip → check_queue → done / failed`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — new loop (create)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — reference for pattern reuse (read-only)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/ll_loop.py` — auto-discovers loops in `loops/`; no change required if naming convention is followed
- `.claude-plugin/plugin.json` — lists built-in loops; add `recursive-refine` entry

### Similar Patterns
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — confidence-check, wire, lifetime-cap logic to reuse
- `scripts/little_loops/loops/` — queue-file pattern used by other multi-item loops

### Tests
- `scripts/tests/loops/test_recursive_refine.py` — new test file; cover: single ID input, list input, recursive breakdown, skip path, all-pass path

### Documentation
- `docs/loops/BUILT-IN-LOOPS.md` — add `recursive-refine` entry
- `commands/create-loop.md` — mention `recursive-refine` as reference for queue-based patterns

### Configuration
- `context.readiness_threshold` / `context.outcome_threshold` / `context.max_refine_count` — canonical in `ll-config.json`, same as `refine-to-ready-issue`

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
- `/ll:capture-issue` - 2026-04-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/77c66dec-3548-4e36-88fe-129cc8627555.jsonl`
