---
captured_at: '2026-06-04T23:51:49Z'
discovered_date: 2026-06-04
discovered_by: capture-issue
confidence_score: 99
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1952: template expansion failure on unescaped `${DIFF_SIZE:-0}` in adversarial-redesign loop

## Summary

The `svg_diff` state in `adversarial-redesign` contains an unescaped Bash default-value expression `${DIFF_SIZE:-0}` which the loop runner's template engine will interpret as a namespace path reference (`DIFF_SIZE:-0`) and reject with `Invalid variable: ${DIFF_SIZE:-0} (expected namespace.path)`. This is the same root cause as BUG-1951 — the template engine treats all `${...}` patterns as namespace paths and doesn't recognize Bash `:-` default-value syntax. The `$$` escape sequence exists specifically to pass literal `${...}` through to the shell.

## Current Behavior

The `svg_diff` state action body at line 153 uses:

```bash
if [ "${DIFF_SIZE:-0}" -le 100 ]; then
```

When the template engine encounters this during action expansion, it tries to resolve `${DIFF_SIZE:-0}` as `namespace.path` — but `DIFF_SIZE:-0` contains no dot separator (and even if it did, `:-0` isn't a valid path). The expansion fails before the shell script ever executes, and the state routes to `on_error` → `critic`.

## Expected Behavior

The template engine should pass `${DIFF_SIZE:-0}` through verbatim so Bash can evaluate the default-value expression. This requires using the double-dollar escape:

```bash
if [ "$${DIFF_SIZE:-0}" -le 100 ]; then
```

The `$$` escape is converted to a literal `$` by the template engine (`interpolation.py:218-241`), emitting `${DIFF_SIZE:-0}` into the shell script where Bash handles it correctly.

## Motivation

The same regression class as BUG-1951 — any loop with an unescaped Bash `${VAR:-default}` in an action body will fail at the template expansion layer before the shell ever runs. The `adversarial-redesign` loop's `svg_diff` convergence check is unreachable until this is fixed. Discovered during the BUG-1951 duplicate-pattern audit.

## Steps to Reproduce

1. Run `ll-loop run adversarial-redesign "<any concept>"`
2. Wait for the loop to enter the `svg_diff` state (after `score_gate` → `on_yes`)
3. Observe: action error fires with `Invalid variable: ${DIFF_SIZE:-0} (expected namespace.path)`
4. Loop routes to `on_error` → `critic` instead of correctly evaluating convergence

## Error Messages

```
Invalid variable: ${DIFF_SIZE:-0} (expected namespace.path)
```

(from `scripts/little_loops/fsm/interpolation.py:227-228`)

## Root Cause

- **File**: `scripts/little_loops/loops/adversarial-redesign.yaml`
- **Anchor**: `svg_diff` state action body (line 153)
- **Cause**: The template engine's `VARIABLE_PATTERN` matches all `${...}` sequences and validates them as `namespace.path` references. Bash default-value syntax (`${VAR:-default}`) uses `:-` which violates the `namespace.path` format. The `$$` escape exists but was not used here.

## Proposed Solution

Escape the literal shell variable so the template engine passes it through verbatim:

```bash
# In svg_diff state action body, change line 153:
if [ "${DIFF_SIZE:-0}" -le 100 ]; then
# to:
if [ "$${DIFF_SIZE:-0}" -le 100 ]; then
```

The `$$` escape sequence is already used extensively in `recursive-refine.yaml`, `autodev.yaml`, `html-website-generator.yaml`, and within `rn-implement.yaml` (line 183: `$${ID}`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/adversarial-redesign.yaml` — `svg_diff` state action body (line 153)

### Dependent Files (Callers/Importers)
- N/A — only the action body string changes; no external callers of this loop's internals

### Similar Patterns
- `scripts/little_loops/loops/rn-implement.yaml:97` — BUG-1951 (`${DEPTH:-0}` → fix applied separately)
- All other loops with `${VAR:-default}` syntax already use `$$` escaping:
  - `recursive-refine.yaml:90` (`$${DEPTH:-0}`) ✓ correct
  - `autodev.yaml:588-589` (`$${PASSED_LIST:-none}`) ✓ correct
  - `html-website-generator.yaml:165` (`$${VISION_BASE_URL:-}`) ✓ correct

### Tests
- N/A — no existing test file for the `adversarial-redesign` loop

### Documentation
- N/A — no docs reference this specific action body

### Configuration
- N/A

## Implementation Steps

1. Edit `scripts/little_loops/loops/adversarial-redesign.yaml`, line 153: `${DIFF_SIZE:-0}` → `$${DIFF_SIZE:-0}`
2. Run `ll-loop validate adversarial-redesign` to confirm no schema violations
3. Run `ll-loop run adversarial-redesign "<test-concept>"` to verify the fix reaches `svg_diff` without template expansion error
4. Audit for any remaining unescaped patterns: `grep -rn '\${[A-Za-z_]\+:' scripts/little_loops/loops/ | grep -v '\$\$'`

## Impact

- **Priority**: P2 — Same regression class as BUG-1951; breaks the `adversarial-redesign` loop at the convergence check; limited to one specific loop
- **Effort**: Small — Single-character change (`$` → `$$`) in one action body line
- **Risk**: Low — Non-breaking; only affects template expansion of this one variable reference; `$$` escaping is already used extensively across loops; shell behavior is well-understood
- **Breaking Change**: No

## Related Key Documentation

| Document | Section | Relevance |
|----------|---------|-----------|
| `docs/ARCHITECTURE.md` | FSM & Interpolation | Template expansion engine design and `$$` escape mechanism |
| `docs/reference/API.md` | `little_loops.fsm` | `interpolate()` function and variable resolution |

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-06-04 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-06-04T23:55:24 - `bc897ad4-963d-4d5d-abcd-f141af857f9e.jsonl`
- `/ll:capture-issue` - 2026-06-04T23:51:49Z - `8826ca14-a9b9-4717-b939-4425b44d5d7c.jsonl`
- `/ll:confidence-check` - 2026-06-04T23:59:00Z - `ae5d31ae-12d3-4754-b1fc-370c3fd2d8f5.jsonl`
