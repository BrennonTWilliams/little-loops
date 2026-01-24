---
discovered_date: 2026-01-23
discovered_by: capture_issue
---

# ENH-123: Preview compiled FSM before saving

## Summary

The `/ll:create_loop` wizard shows the paradigm YAML before saving, but users can't see the actual FSM states and transitions that will be created. This makes it hard to verify the loop logic is correct.

## Context

Identified from conversation analyzing why created loops don't work. The wizard shows high-level paradigm YAML but this gets compiled into a more complex FSM with states, evaluators, and routing. Users can't verify the compiled structure is correct.

## Current Behavior

Step 4 of the wizard (`commands/create_loop.md:369-394`) shows:

```yaml
paradigm: goal
name: "fix-types"
goal: "Type checks pass"
tools:
  - "mypy src/"
  - "/ll:check_code fix"
```

Users confirm this, but the actual compiled FSM has:
- `evaluate` state with `on_success="done"`, `on_failure="fix"`
- `fix` state with `next="evaluate"`
- `done` terminal state

## Expected Behavior

Before saving, show both the paradigm YAML AND the compiled FSM structure:

```
Here's your loop configuration:

## Paradigm YAML
[paradigm yaml]

## Compiled FSM
States: evaluate → fix → done
Transitions:
  evaluate: success→done, failure→fix, error→fix
  fix: (unconditional)→evaluate
  done: [terminal]
Initial: evaluate
```

## Proposed Solution

1. After generating paradigm YAML in the wizard, call the appropriate compiler function conceptually
2. Display a human-readable summary of states and transitions
3. Show routing for each state so users can verify "if X fails, it goes to Y"

This could be as simple as a text diagram or table showing the state machine.

## Impact

- **Priority**: P3 (helps users understand and verify loops)
- **Effort**: Low (format existing data for display)
- **Risk**: Low (display-only change)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| commands | commands/create_loop.md | Wizard implementation |
| architecture | scripts/little_loops/fsm/compilers.py | Compilation logic to expose |

## Labels

`enhancement`, `create-loop`, `ux`, `captured`

---

## Status

**Open** | Created: 2026-01-23 | Priority: P3
