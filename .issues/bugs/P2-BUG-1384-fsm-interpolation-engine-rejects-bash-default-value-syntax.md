---
id: BUG-1384
type: BUG
priority: P2
status: active
captured_at: "2026-05-09T01:55:56Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
---

# BUG-1384: FSM interpolation engine rejects bash default-value syntax in escaped variables

## Problem Statement

The FSM loop YAML files use `$${...}` as an escape sequence intended to produce a literal `${...}` for the shell (preventing the interpolation engine from treating it as a variable reference). However, the interpolation engine in `interpolation.py` is incorrectly treating `$${DEPTH:-0}` as a variable reference and failing with:

```
Invalid variable: ${DEPTH:-0} (expected namespace.path)
```

This causes `recursive-refine` to fail on its first state transition, which in the FSM-based sprint mode produces an infinite retry loop (observed: 191 iterations before SIGKILL).

## Root Cause

**File**: `scripts/little_loops/fsm/interpolation.py`

The escape logic is supposed to work in three steps:
1. Replace `$${` with a placeholder
2. Match and resolve remaining `${namespace.path}` references
3. Restore the placeholder as `${`

The bug is in one of these steps: either the placeholder replacement in step 1 is not running before the `${...}` regex match, or the `replace_var()` function is being called on the unescaped form before the placeholder swap occurs.

**Affected YAML**: `scripts/little_loops/loops/recursive-refine.yaml` (line 88):
```yaml
printf '%s' "$${DEPTH:-0}" > .loops/tmp/recursive-refine-current-depth.txt
```

## Impact

- `ll-loop run recursive-refine` fails immediately on first state transition
- `ll-sprint` in FSM mode enters an infinite retry loop (191+ iterations, requires SIGKILL)
- Any FSM loop YAML that uses bash default-value syntax (`:-`) or other bash parameter expansions in escaped `$${...}` blocks will fail

## Expected Behavior

`$${DEPTH:-0}` should pass through the interpolation engine unchanged and reach the shell as `${DEPTH:-0}`, which bash then evaluates as "value of DEPTH, or 0 if unset".

## Implementation Steps

1. Read `interpolation.py` and trace the three-step escape sequence
2. Identify where the regex match for `${...}` is running before or instead of the placeholder substitution
3. Fix the ordering or the regex so `$${}` sequences are fully protected before variable resolution
4. Add a unit test: `interpolate("printf '$${DEPTH:-0}'", {})` should return `"printf '${DEPTH:-0}'"` without raising

## Suggested Investigation

```python
# In interpolation.py, look for the escape sequence handling
# It should look roughly like:
text = text.replace('$${', PLACEHOLDER)       # step 1
text = VAR_PATTERN.sub(replace_var, text)     # step 2
text = text.replace(PLACEHOLDER, '${')        # step 3

# If step 2 runs before step 1, or if VAR_PATTERN matches PLACEHOLDER,
# that is the bug.
```

Check also whether `replace_var()` itself applies the three-step logic or delegates to a top-level function that does.

## Verification

1. Run `ll-loop run recursive-refine BUG-635` after the fix
2. Confirm no `"Invalid variable"` error in the FSM event log
3. Confirm the shell command receives `${DEPTH:-0}` literally and evaluates it correctly

## Related Issues

- BUG-1381, BUG-1382, BUG-1383: parallel sprint error capture (separate failure mode, same sprint run)

## Session Log
- `/ll:capture-issue` - 2026-05-09T01:55:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
