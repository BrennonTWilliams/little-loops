---
id: FEAT-837
priority: P3
type: FEAT
status: open
discovered_date: 2026-03-20
discovered_by: capture-issue
---

# FEAT-837: ll-loop run sub-loop state shows full sub-state output

## Summary

When `ll-loop run` executes a loop that contains a state whose action is a sub-loop invocation, the CLI output for that state should stream or display the full sub-state-level output produced by the sub-loop — not just a high-level "entered sub-loop" or silent transition.

## Current Behavior

When a parent loop transitions into a state that triggers a sub-loop, the CLI output at the parent level does not surface the sub-loop's internal state transitions, action outputs, or terminal results. The sub-loop execution is effectively a black box from the perspective of the parent's CLI output.

## Expected Behavior

When the parent loop enters a sub-loop state, the CLI output should include the full output from the sub-loop execution: each state transition, action output, and terminal state should be visible in the terminal, clearly scoped/indented to indicate sub-loop depth.

## Motivation

Without sub-state output, debugging a parent loop that delegates to a sub-loop is impractical — the user cannot see what the sub-loop is doing, which states it enters, or why it terminates. This is especially painful for nested automation pipelines where the sub-loop failure mode is the primary thing to diagnose.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD

## API/Interface

```python
# Example interface/signature
```

## Implementation Steps

1. Locate where sub-loop invocation is dispatched from within the parent loop runner
2. Capture and forward sub-loop CLI output to the parent's output stream, with indentation or prefix indicating nesting depth
3. Verify output is correct for multiple levels of nesting (loop → sub-loop → sub-sub-loop)

## Impact

- **Priority**: P3 - Needed for practical debugging of nested FSM automation
- **Effort**: Small/Medium - likely a matter of forwarding stdout/stderr from the child process
- **Risk**: Low - output-only change, no behavioral side effects
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `captured`, `ll-loop`, `cli-output`, `sub-loop`

## Status

**Open** | Created: 2026-03-20 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/707beb95-6757-467e-96fe-ecc041ee03ed.jsonl`
