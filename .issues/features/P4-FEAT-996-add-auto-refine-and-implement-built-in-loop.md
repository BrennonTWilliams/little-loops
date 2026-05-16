---
id: FEAT-996
type: FEAT
priority: P4
title: "Add auto-refine-and-implement built-in loop"
status: done
discovered_date: 2026-04-08
discovered_by: capture-issue
completed_at: 2026-04-08T00:00:00Z
---

# FEAT-996: Add auto-refine-and-implement built-in loop

## Summary

Promote the `auto-issue-processor.yaml` pattern — get next backlog issue → refine to ready → implement → loop — as a built-in loop named `auto-refine-and-implement`. The loop combines `refine-to-ready-issue` (sub-loop) with `ll-auto --only` into a single unattended outer loop with skip tracking.

## Current Behavior

No built-in loop combines refinement and implementation in a single outer loop. Users who want this pattern must maintain their own project-level FSM file. `ll-auto` implements issues without first refining them; `refine-to-ready-issue` refines without implementing. The combined pattern is commonly needed but not shipped.

## Expected Behavior

A built-in `auto-refine-and-implement` loop is available at `scripts/little_loops/loops/auto-refine-and-implement.yaml`. It iterates through the backlog in priority order, refines each issue via `refine-to-ready-issue`, implements it, skips issues that fail refinement, and tracks skipped issues across iterations. It has proper `category`, `description`, `timeout`, and configurable `max_iterations`.

## Motivation

The refine → implement sequence is the correct unattended automation workflow — implementing un-refined issues wastes agent cycles and produces poor results. This pattern already exists in user project files (e.g., `auto-issue-processor.yaml`) but isn't shared. Promoting it as a built-in ensures all users benefit and future improvements propagate automatically.

## Use Case

A developer has 15 unrefined backlog issues and wants to run unattended overnight automation. They run `ll-loop auto-refine-and-implement`, go to sleep, and wake up to refined and implemented issues with a `skipped.txt` log of anything that couldn't be prepared. Without this built-in, they'd need to write and maintain the FSM themselves.

## Proposed Solution

Promote `auto-issue-processor.yaml` (from a user project) with these structural changes:

1. **Add `category: issue-management`** — required for loop catalog
2. **Add `description`** — required for catalog and discovery
3. **Add `import: [lib/common.yaml]`** — consistent with other built-ins
4. **Add `timeout: 28800`** — outer loops need an upper bound (8h default)
5. **Lower `max_iterations`** to 100 (or make `context`-configurable) — 500 is excessive
6. **Replace `ll-auto --only` with `/ll:manage-issue`** in `implement_issue` — more portable inside the plugin, avoids dependency on `ll-auto` CLI being installed
7. **Rename** to `auto-refine-and-implement` — descriptive, consistent with naming conventions

Resulting structure:

```yaml
name: "auto-refine-and-implement"
category: issue-management
description: |
  For each backlog issue (priority order): refine to ready via refine-to-ready-issue,
  then implement. Skips issues that fail refinement and tracks them to avoid retrying.
  Loops until backlog is exhausted.
initial: get_next_issue
max_iterations: 100
timeout: 28800
on_handoff: spawn
import:
  - lib/common.yaml
context:
  max_issues: 100

states:
  get_next_issue: ...      # ll-issues next-issue with skip tracking
  refine_issue: ...        # loop: refine-to-ready-issue, context_passthrough: true
  implement_issue: ...     # /ll:manage-issue implement ${captured.input.output}
  skip_issue: ...          # append to skipped list, next: get_next_issue
  done:
    terminal: true
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/README.md` — add entry to loop catalog

### New Files
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — the loop itself

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — sub-loop invoked by name

### Similar Patterns
- `scripts/little_loops/loops/issue-refinement.yaml` — **closest analog**: outer loop with skip tracking + `refine-to-ready-issue` sub-loop via `context_passthrough: true`; uses `import: [lib/common.yaml]`, `capture: "input"`, comma-separated skip-list
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — sub-loop invoked by name; reads `context.input` as the injected issue ID when `context_passthrough: true` is set
- `scripts/little_loops/loops/backlog-flow-optimizer.yaml` — outer loop + sub-skill delegation reference
- `scripts/little_loops/loops/lib/cli.yaml` — has `ll_issues_next_issue` fragment, but skip tracking requires inline `get_next_issue` state (fragment insufficient)

### Tests
- `scripts/tests/fixtures/fsm/` — may want a fixture for multi-state outer loop with sub-loop delegation
- No Python changes → no unit test changes needed

### Documentation
- `scripts/little_loops/loops/README.md` — catalog entry

### Configuration
- N/A — no config schema changes needed

## Implementation Steps

1. Copy `auto-issue-processor.yaml` into `scripts/little_loops/loops/auto-refine-and-implement.yaml`
2. Apply the 7 structural fixes: `category`, `description`, `import`, `timeout`, `max_iterations`, implement action, `name`
3. **`get_next_issue` state**: keep `capture: input` (load-bearing — downstream states reference `${captured.input.output}` and `context_passthrough` forwards it as `context.input` to `refine-to-ready-issue`); update skip file path to `.loops/tmp/auto-refine-and-implement-skipped.txt`
4. **`implement_issue` state**: replace `ll-auto --only ${captured.input.output}` with a `action_type: prompt` state — `/ll:manage-issue` is a Claude Code command, not a shell binary (see `harness-single-shot.yaml:34` pattern):
   ```yaml
   implement_issue:
     action: "Run /ll:manage-issue to implement issue ${captured.input.output}."
     action_type: prompt
     capture: implement_result
     next: get_next_issue
   ```
5. **`skip_issue` state**: update `.loops/tmp/auto-issue-processor-skipped.txt` → `.loops/tmp/auto-refine-and-implement-skipped.txt`
6. Update `scripts/little_loops/loops/README.md` — add row to the **Issue Management** table: `| auto-refine-and-implement | For each backlog issue in priority order: refine to ready, then implement; skips issues that fail refinement |`
7. Smoke-test: run `ll-loop auto-refine-and-implement` against a test backlog issue

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `auto-issue-processor.yaml:33` — current `implement_issue` uses `action_type: shell` with `ll-auto --only`; this **cannot** be kept — `ll-auto` CLI dependency is fragile and `action_type: shell` cannot invoke slash commands
- `harness-single-shot.yaml:34` — established pattern for `/ll:manage-issue` as `action_type: prompt`
- `issue-refinement.yaml:33-41` — skip tracking pattern used in built-ins: comma-sep written in `handle_failure` state, consumed inline in next-issue call; cleaner than newline+paste
- `refine-to-ready-issue.yaml:19` — child loop reads `${context.input}` when injected; falls back to `ll-issues next-issue` when running standalone — `context_passthrough: true` in parent triggers this injection path
- `lib/common.yaml` — `shell_exit` fragment can simplify shell states that only evaluate exit code, but the `get_next_issue` skip-tracking logic needs to remain inline

## Acceptance Criteria

- [ ] Loop file exists at `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- [ ] Has `category: issue-management`, `description`, `timeout`, `import: [lib/common.yaml]`
- [ ] `max_iterations` ≤ 100 or configurable via `context`
- [ ] `implement_issue` state uses `/ll:manage-issue` (not raw `ll-auto`)
- [ ] Skip tracking writes to `.loops/tmp/auto-refine-and-implement-skipped.txt`
- [ ] `refine_issue` uses `loop: refine-to-ready-issue` with `context_passthrough: true`
- [ ] Loop appears in `scripts/little_loops/loops/README.md`
- [ ] Old `auto-issue-processor.yaml` in project root removed or noted as superseded

## Impact

- **Priority**: P4 — useful but not blocking; pattern already works via user project files
- **Effort**: Small — mostly copy + edit; no new Python code
- **Risk**: Low — additive only, no changes to existing loops or CLI
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`automation`, `loops`, `issue-management`, `captured`

## Resolution

Implemented in `scripts/little_loops/loops/auto-refine-and-implement.yaml`. Promoted from `auto-issue-processor.yaml` with all 7 structural fixes applied: `category`, `description`, `import`, `timeout`, `max_iterations` (100), `action_type: prompt` for implement_issue, and updated skip file path. README catalog updated. Old `auto-issue-processor.yaml` remains in project root as user reference.

## Session Log
- `/ll:manage-issue` - 2026-04-08 - implemented
- `/ll:refine-issue` - 2026-04-08T05:40:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/854f6e93-e4ac-4f1e-8b05-80b1a030ce8f.jsonl`
- `/ll:capture-issue` - 2026-04-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/76fbeb1f-5361-408b-ba48-b8f1bb2afc2f.jsonl`

---

**Open** | Created: 2026-04-08 | Priority: P4
