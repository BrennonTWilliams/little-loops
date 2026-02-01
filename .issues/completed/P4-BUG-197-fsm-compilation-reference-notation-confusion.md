# FSM Compilation Reference Uses Potentially Confusing Notation

## Type
BUG

## Priority
P4

## Status
COMPLETED

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `commands/create_loop.md`: Added notation legend explaining arrow notation (→) and its mapping to YAML syntax

### Verification Results
- Documentation: PASS (markdown renders correctly)
- No code changes required

## Description

The FSM Compilation Reference in `/ll:create_loop` uses arrow notation (→) for transitions that could be confused with the `route:` table syntax.

**Reference shows (lines 685-748):**
```
evaluate:
  - on_success → done
  - on_failure → fix
  - on_error → fix
```

**But there are two ways to specify routes:**

1. **Shorthand** (shown in reference):
   ```yaml
   on_success: done
   on_failure: fix
   on_error: fix
   ```

2. **Full routing table:**
   ```yaml
   route:
     success: done
     failure: fix
     _: fix  # default
   ```

**Evidence:**
- `commands/create_loop.md:685-748` - FSM Compilation Reference
- `scripts/little_loops/fsm/compilers.py:179-186` - Actual compilation uses shorthand

**Impact:**
Minor confusion. Users familiar with the `route:` table syntax may be confused by the arrow notation which looks different from actual YAML.

## Files Affected
- `commands/create_loop.md`

## Expected Behavior
Use notation that clearly matches actual YAML syntax, or add a note explaining the notation mapping.

## Actual Behavior
Arrow notation is used without explicit mapping to YAML syntax.

## Recommendation
Add a small legend explaining:
```
→ means "transitions to"
on_success → done  is equivalent to  on_success: done
```

## Related Issues
None
