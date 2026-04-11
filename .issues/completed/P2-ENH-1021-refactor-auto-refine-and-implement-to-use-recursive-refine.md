---
discovered_date: 2026-04-10
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 93
---

# ENH-1021: Refactor auto-refine-and-implement to use recursive-refine

## Summary

Replace the `refine-to-ready-issue` sub-loop call in `auto-refine-and-implement` with `recursive-refine`. This adds automatic issue decomposition: when an issue is too large, `recursive-refine` decomposes it via `issue-size-review` and recursively refines all child issues (depth-first). The outer loop must then handle the fact that one input issue can produce 0-N implementable issues.

## Current Behavior

`auto-refine-and-implement` calls `refine-to-ready-issue` for each backlog issue — a flat, single-issue refinement with no decomposition. If an issue is too large, it is skipped without being broken down.

## Expected Behavior

`auto-refine-and-implement` calls `recursive-refine` for each backlog issue. `recursive-refine` either produces a list of ready-to-implement issues (in `.loops/tmp/recursive-refine-passed.txt`) or decomposes the issue into child issues (recorded in `.loops/tmp/recursive-refine-skipped.txt`). The outer loop then implements each passed issue in order before moving to the next backlog issue.

## Motivation

`recursive-refine` already exists and handles large-issue decomposition. Wiring it into `auto-refine-and-implement` removes the need for manual decomposition before automation can process an issue, making the end-to-end pipeline fully autonomous for oversized issues.

## Success Metrics

- `recursive-refine` sub-loop invoked for each backlog issue (replaces flat `refine-to-ready-issue` call)
- Issues in `recursive-refine-passed.txt` are queued for implementation and added to the outer skip list
- Decomposed parent issues (in `recursive-refine-skipped.txt`) are added to the outer skip list and not re-queued
- `ll-loop validate auto-refine-and-implement` passes with no schema errors after the change

## Scope Boundaries

- **In scope**: Replacing the `refine_issue` state and all downstream states in `auto-refine-and-implement.yaml` with the new recursive-refine delegation state machine
- **Out of scope**: Changes to `recursive-refine.yaml` (read-only reference); changes to the Python executor or loop runner; changes to other loop YAML files; modifications to `ll-issues next-issue` behavior

## Proposed Solution

Replace the `refine_issue` state (and all downstream states) in `auto-refine-and-implement.yaml` with the new state machine below. Only `auto-refine-and-implement.yaml` needs to change; `recursive-refine.yaml` is read-only.

### What `recursive-refine` returns

`recursive-refine` resets both files at `parse_input` and populates them during its run:

- `.loops/tmp/recursive-refine-passed.txt` — issues that met confidence thresholds (ready to implement)
- `.loops/tmp/recursive-refine-skipped.txt` — parent issues that were decomposed, or issues with no further decomposition possible

Terminal state `done` → `on_success`; terminal state `failed` (parse error / no input) → `on_failure`.

### New State Machine

```
get_next_issue
  ├─(yes)→ refine_issue
  └─(no/error)→ done

refine_issue  [loop: recursive-refine, context_passthrough: true]
  ├─(success)→ get_passed_issues
  └─(failure/error)→ skip_and_continue → get_next_issue

get_passed_issues  [fragment: shell_exit]
  Reads recursive-refine-{passed,skipped}.txt:
    - skipped.txt entries → outer skip list
    - passed.txt entries  → outer skip list AND impl queue
  ├─(yes: queue non-empty)→ implement_next
  └─(no/error: queue empty)→ get_next_issue

implement_next  [fragment: shell_exit, capture: impl_id]
  Pops head of impl queue
  ├─(yes: got ID)→ implement_issue
  └─(no/error: empty)→ get_next_issue

implement_issue  [action: ll-auto --only ${captured.impl_id.output}]
  └─(next)→ implement_next

skip_and_continue  [action_type: shell]
  Adds captured.input.output to outer skip list
  └─(next)→ get_next_issue

done  [terminal]
```

**Key design notes:**
- `get_passed_issues` adds passed IDs to the outer skip list (prevents re-implementation if a child ID resurfaces on a future `get_next_issue` call)
- `skip_and_continue` only fires when `recursive-refine` hits its `failed` terminal (parse error — input was empty); it correctly uses `captured.input.output` since `impl_id` is not yet captured
- `implement_issue` uses `captured.impl_id.output`, not `captured.input.output`
- `implement_next` loops back to itself (via `implement_issue`) until the queue is drained, then returns to `get_next_issue`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — only file that changes

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/recursive-refine.yaml` — sub-loop being called (read-only reference)

### Similar Patterns
- `scripts/little_loops/loops/recursive-refine.yaml` — pattern for reading passed/skipped output files
- `scripts/little_loops/loops/issue-refinement-loop.yaml` — existing use of sub-loop delegation pattern

### Tests
- `scripts/tests/test_builtin_loops.py:test_all_validate_as_valid_fsm` — validates all built-in loops including `auto-refine-and-implement`; will catch schema errors in the updated YAML automatically
- `scripts/tests/test_builtin_loops.py:TestRecursiveRefine` (lines 785–921) — model for adding a `TestAutoRefineAndImplement` class with structural assertions for the new state machine (see Implementation Steps)

### New Output Files
- `.loops/tmp/auto-refine-and-implement-impl-queue.txt` — written by `get_passed_issues`, consumed by `implement_next`; new file created by this change (does not exist today)

### Documentation
- N/A - No documentation specifically covers `auto-refine-and-implement` internals

### Configuration
- N/A - No configuration changes required

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/executor.py:336-343` — `context_passthrough` mechanism: when `true`, parent's `self.captured` entries are flattened to their `.output` strings and merged into the child's `context`. So `captured.input.output` (issue ID from `get_next_issue`) becomes `context.input` in `recursive-refine`, which is exactly what `parse_input` reads via `${context.input}`.
- `scripts/little_loops/fsm/executor.py:367-381` — sub-loop routing: child `done` terminal → `on_yes` (= `on_success`); child `failed` terminal → `on_no` (= `on_failure`); runtime error → `on_error`. Confirmed: `recursive-refine`'s two terminals (`done`, `failed`) correctly map to `on_success: get_passed_issues` and `on_failure: skip_and_continue`.
- `scripts/little_loops/fsm/schema.py:301-302` — `on_success`/`on_failure` are aliases for `on_yes`/`on_no`; resolved at parse time (no runtime overhead).
- `scripts/little_loops/loops/recursive-refine.yaml:36-37` — both output files are reset at `parse_input` on every invocation, so `get_passed_issues` always reads a fresh snapshot for the current input issue.
- `scripts/tests/test_builtin_loops.py:785-921` — `TestRecursiveRefine` is the test class pattern to follow if adding `TestAutoRefineAndImplement`; covers state presence, terminal correctness, routing, and file path conventions.

## Implementation Steps

1. Read current `auto-refine-and-implement.yaml` and `recursive-refine.yaml` to confirm interfaces
2. Replace the full `states:` block in `auto-refine-and-implement.yaml` with the new state machine (see Proposed Solution)
3. Update the `description:` field in the loop header to reflect recursive-refine delegation
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` — `test_all_validate_as_valid_fsm` and `test_all_parse_as_yaml` will catch any schema errors in the updated YAML
5. Optionally add a `TestAutoRefineAndImplement` class in `test_builtin_loops.py` (model after `TestRecursiveRefine` at line 785) to assert the new state names, routing, and file paths
6. Dry-run: inspect `.loops/tmp/` files after a single iteration with a known decomposable issue
7. Check that after `recursive-refine` runs: passed issues appear in `.loops/tmp/auto-refine-and-implement-impl-queue.txt`, skipped issues appear in `.loops/tmp/auto-refine-and-implement-skipped.txt`
8. Confirm `ll-issues next-issue --skip <passed+skipped ids>` no longer returns those IDs

### Complete Replacement YAML

```yaml
name: "auto-refine-and-implement"
category: issue-management
description: |
  For each backlog issue (priority order): recursively refine via recursive-refine
  (which handles decomposition into child issues), then implement all issues that
  passed refinement. Skips issues that fail refinement or are decomposed, tracking
  them to avoid retrying. Loops until backlog is exhausted.
initial: get_next_issue
max_iterations: 100
timeout: 28800
on_handoff: spawn
import:
  - lib/common.yaml
context:
  max_issues: 100

states:
  get_next_issue:
    action: |
      mkdir -p .loops/tmp
      SKIPPED=""
      if [ -f .loops/tmp/auto-refine-and-implement-skipped.txt ]; then
        SKIPPED=$(paste -sd ',' .loops/tmp/auto-refine-and-implement-skipped.txt)
      fi
      if [ -n "$SKIPPED" ]; then
        ll-issues next-issue --skip "$SKIPPED"
      else
        ll-issues next-issue
      fi
    action_type: shell
    capture: input
    on_yes: refine_issue
    on_no: done
    on_error: done

  refine_issue:
    loop: recursive-refine
    context_passthrough: true
    on_success: get_passed_issues
    on_failure: skip_and_continue
    on_error: skip_and_continue

  get_passed_issues:
    action: |
      SKIP_FILE=".loops/tmp/auto-refine-and-implement-skipped.txt"
      IMPL_QUEUE=".loops/tmp/auto-refine-and-implement-impl-queue.txt"

      if [ -s .loops/tmp/recursive-refine-skipped.txt ]; then
        grep -v '^[[:space:]]*$' .loops/tmp/recursive-refine-skipped.txt >> "$SKIP_FILE"
      fi

      PASSED=""
      if [ -s .loops/tmp/recursive-refine-passed.txt ]; then
        PASSED=$(grep -v '^[[:space:]]*$' .loops/tmp/recursive-refine-passed.txt)
      fi

      if [ -n "$PASSED" ]; then
        echo "$PASSED" >> "$SKIP_FILE"
        echo "$PASSED" > "$IMPL_QUEUE"
        exit 0
      else
        printf '' > "$IMPL_QUEUE"
        exit 1
      fi
    fragment: shell_exit
    on_yes: implement_next
    on_no: get_next_issue
    on_error: get_next_issue

  implement_next:
    action: |
      IMPL_QUEUE=".loops/tmp/auto-refine-and-implement-impl-queue.txt"
      if [ ! -s "$IMPL_QUEUE" ]; then
        exit 1
      fi
      CURRENT=$(head -1 "$IMPL_QUEUE")
      tail -n +2 "$IMPL_QUEUE" > "$IMPL_QUEUE.tmp"
      mv "$IMPL_QUEUE.tmp" "$IMPL_QUEUE"
      echo "$CURRENT"
    fragment: shell_exit
    capture: impl_id
    on_yes: implement_issue
    on_no: get_next_issue
    on_error: get_next_issue

  implement_issue:
    action: "ll-auto --only ${captured.impl_id.output}"
    action_type: shell
    next: implement_next

  skip_and_continue:
    action: |
      echo "Skipping ${captured.input.output} after refinement failure"
      echo "${captured.input.output}" >> .loops/tmp/auto-refine-and-implement-skipped.txt
    action_type: shell
    next: get_next_issue

  done:
    terminal: true
```

## Impact

- **Priority**: P2 - Closes the manual-decomposition gap in the automation pipeline
- **Effort**: Small - single YAML file replacement, no Python changes
- **Risk**: Low - `recursive-refine` interface is stable and the new state machine is self-contained
- **Breaking Change**: No

## API/Interface

```yaml
# recursive-refine output files (read by get_passed_issues):
# .loops/tmp/recursive-refine-passed.txt  — one issue ID per line
# .loops/tmp/recursive-refine-skipped.txt — one issue ID per line
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `automation`, `captured`

## Resolution

**Status**: Completed | Resolved: 2026-04-10

### Changes Made
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — replaced `refine-to-ready-issue` sub-loop with `recursive-refine` delegation; added `get_passed_issues`, `implement_next`, and `implement_issue` states for queue-based implementation of passed issues; renamed `skip_issue` → `skip_and_continue` to match new design; updated description
- `scripts/tests/test_builtin_loops.py` — added `TestAutoRefineAndImplementLoop` class with 12 structural tests covering state presence, routing, capture names, file paths, and recursive-refine output file references

### Verification
- `python -m pytest scripts/tests/test_builtin_loops.py -v` — 113 passed (includes `test_all_validate_as_valid_fsm`, `test_all_parse_as_yaml`, and all new `TestAutoRefineAndImplementLoop` tests)

## Status

**Completed** | Created: 2026-04-10 | Priority: P2

---

## Session Log
- `/ll:ready-issue` - 2026-04-11T01:38:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d21145c2-9202-4f18-b67c-e656a4a4c0f7.jsonl`
- `/ll:refine-issue` - 2026-04-11T01:25:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a8cafa8-27b4-42c4-bb1a-96ff79bd0cf7.jsonl`
- `/ll:format-issue` - 2026-04-11T01:18:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3ded44bb-5172-425c-a697-6c2aede69b6a.jsonl`
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc79d8ec-4917-4061-a148-c6ad39ee404c.jsonl`
- `/ll:confidence-check` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b72b78fc-5cf9-40eb-a054-5c72aa47ca1a.jsonl`
- `/ll:manage-issue` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
