# Maintain Mode Restart Behavior Could Be Better Documented

## Type
ENH

## Priority
P5

## Status
OPEN

## Description

The `maintain` mode behavior is correct but could be clearer in the command documentation. When `maintain: true`, the loop restarts after all constraints pass, but this is implemented by setting `on_maintain` on the terminal `all_valid` state.

**Command describes (lines 424-431):**
```yaml
questions:
  - question: "Should the loop restart after all constraints pass?"
    header: "Maintain mode"
    multiSelect: false
    options:
      - label: "No - stop when all pass"
        description: "Loop terminates when all constraints are satisfied"
      - label: "Yes - continuously maintain"
        description: "Restart from first constraint after all pass (daemon mode)"
```

**Implementation (compilers.py:369-373):**
```python
states["all_valid"] = StateConfig(
    terminal=True,
    on_maintain=first_check if maintain else None,
)
```

**Evidence:**
- `commands/create_loop.md:424-431`
- `scripts/little_loops/fsm/compilers.py:369-373`

**Impact:**
Minor. The behavior is correct and the documentation is reasonably clear. Users just might not realize that `on_maintain` is the mechanism for restart.

## Files Affected
- `commands/create_loop.md`

## Recommendation
Consider adding a brief note explaining:
```
Note: Maintain mode works by setting on_maintain on the terminal state,
which causes the executor to transition back to the first constraint.
```

Or leave as-is since the current description is adequate.

## Related Issues
None


---

## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-02-01
- **Reason**: already_fixed
- **Closure**: Automated (ready_issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
