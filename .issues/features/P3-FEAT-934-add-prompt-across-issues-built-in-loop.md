---
discovered_date: 2026-04-03
discovered_by: capture-issue
---

# FEAT-934: Add prompt-across-issues Built-in Loop

## Summary

A new built-in loop `prompt-across-issues` that accepts an arbitrary prompt string via
the `input` parameter and runs that prompt sequentially against each open/active issue,
one at a time, using the FSM loop engine.

## Current Behavior

There is no built-in loop for bulk prompt execution across all open issues. Users who
want to run an ad-hoc command or skill against every issue must either script it
manually, use `ll-auto` (which is opinionated about processing order and issue
state), or write a custom loop YAML. There is no low-friction way to say "run
`/ll:refine-issue` (or any other prompt) on every open issue."

## Expected Behavior

Running `ll-loop run prompt-across-issues "<prompt>"` will:
1. Discover all open/active issues (all categories, excluding completed and deferred)
2. For each issue, inject the issue ID into the prompt and execute it as a Claude Code
   agent step
3. Advance to the next issue after each completes, respecting loop timeout and
   max_iterations guards
4. Report a summary of issues processed and any failures

The `input` parameter (the prompt string) is required. The loop exits with an error
if no prompt is provided.

## Motivation

Power users frequently want to run a single command across all issues (e.g.,
`/ll:normalize-issues`, `/ll:ready-issue`, or a custom refine prompt) without setting
up a full sprint or custom loop. This loop provides a zero-config way to do bulk
issue processing with the full FSM harness (timeout, retry, stall detection) but
without the opinionated structure of `ll-auto` or `ll-sprint`.

## Use Case

A developer wants to run `/ll:refine-issue` across all 15 open issues before a sprint
planning session. Instead of running it manually 15 times or writing a shell script,
they run:

```
ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}"
```

The loop discovers all open issues, runs the refine skill on each in priority order,
and prints a completion summary.

## Acceptance Criteria

- [ ] `ll-loop run prompt-across-issues "<prompt>"` discovers all open/active issues
  and runs the prompt for each, sequentially
- [ ] The `{issue_id}` placeholder in the prompt string is substituted with the
  current issue's ID (e.g., `FEAT-042`) before execution
- [ ] If `input` is empty or missing, the loop exits in the initial state with a
  descriptive error message
- [ ] Issues in `completed/` and `deferred/` directories are excluded
- [ ] Loop respects `max_iterations` and `timeout` guards from standard FSM config
- [ ] Loop is discoverable via `ll-loop list` with a clear description
- [ ] A `ll-loop test prompt-across-issues` dry-run passes without errors

## Proposed Solution

Create `scripts/little_loops/loops/prompt-across-issues.yaml` modeled on
`harness-multi-item.yaml` but simplified:

- **`discover` state**: Use `ll-issues list --json` to get open issues sorted by
  priority; pop the first issue ID into a temp file (same pattern as
  `harness-multi-item`)
- **`execute` state**: Run the `input` prompt with `{issue_id}` substituted using the
  FSM's `input` context variable; delegate to Claude Code via the standard `claude`
  action type
- **`advance` state**: Remove the processed issue from the working list and loop back
  to `discover`
- **`done` state**: Print summary of processed issues
- **`error` state**: Handle missing input or empty issue list gracefully

The loop should not include the full evaluation pipeline (check_stall, check_concrete,
etc.) by default — keep it simple. Users who need quality gates can fork
`harness-multi-item`.

## API/Interface

```yaml
# Usage
ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}"
ll-loop run prompt-across-issues "/ll:normalize-issues {issue_id} --quick"
ll-loop test prompt-across-issues  # dry-run validation

# YAML loop parameters
name: prompt-across-issues
input: "<prompt-string>"   # required; {issue_id} placeholder substituted per issue
```

The `{issue_id}` substitution is the only template variable. Prompt strings without
`{issue_id}` are valid (the raw prompt is executed unchanged for each issue).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prompt-across-issues.yaml` ← new file

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loop_runner.py` — executes loop YAML; no changes expected if
  `{issue_id}` substitution is handled via existing FSM context variable injection
- `scripts/little_loops/fsm.py` — FSM engine; verify `input` context variable is
  accessible in action templates

### Similar Patterns
- `scripts/little_loops/loops/harness-multi-item.yaml` — primary template to adapt
- `scripts/little_loops/loops/issue-refinement.yaml` — shows issue-focused loop pattern

### Tests
- `scripts/tests/test_loop_runner.py` — add dry-run test for `prompt-across-issues`
- New fixture: mock `ll-issues list --json` returning 2-3 test issues

### Documentation
- `scripts/little_loops/loops/README.md` — add entry for new loop
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — consider referencing as a simpler
  alternative to `harness-multi-item`

### Configuration
- N/A — no config changes; loop is self-contained YAML

## Implementation Steps

1. Read `harness-multi-item.yaml` and `issue-refinement.yaml` to understand
   discover/advance patterns and how `input` is threaded through FSM states
2. Verify FSM context variable injection supports `{issue_id}` substitution in action
   strings (check `fsm.py` / `loop_runner.py`)
3. Create `prompt-across-issues.yaml` with `discover → execute → advance → done/error`
   states; wire `input` substitution
4. Add `ll-loop test prompt-across-issues` dry-run test case
5. Update `loops/README.md` with new entry

## Impact

- **Priority**: P3 - Useful quality-of-life loop; no blockers, no urgency
- **Effort**: Small - New YAML file + 1 test; no engine changes expected
- **Risk**: Low - Additive only; no changes to existing loops or FSM engine
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `loops`, `captured`

---

## Session Log
- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`

---

## Status

**Open** | Created: 2026-04-03 | Priority: P3
