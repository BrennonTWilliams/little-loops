---
discovered_date: 2026-04-10
discovered_by: capture-issue
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

## Implementation Steps

1. Read current `auto-refine-and-implement.yaml` and `recursive-refine.yaml` to confirm interfaces
2. Replace the full `states:` block in `auto-refine-and-implement.yaml` with the new state machine (see Proposed Solution)
3. Update the `description:` field in the loop header to reflect recursive-refine delegation
4. Run `ll-loop validate auto-refine-and-implement` (if available) to check YAML schema
5. Dry-run: inspect `.loops/tmp/` files after a single iteration with a known decomposable issue
6. Confirm `ll-issues next-issue --skip <passed+skipped ids>` no longer returns those IDs

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

## Status

**Open** | Created: 2026-04-10 | Priority: P2

---

## Session Log
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc79d8ec-4917-4061-a148-c6ad39ee404c.jsonl`
