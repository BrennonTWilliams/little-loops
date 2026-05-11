---
id: ENH-1445
priority: P2
type: ENH
parent: ENH-1442
---

# ENH-1445: Goals Discovery — Hook Warning Fix + Test Update

## Summary

Downgrade or remove the false-alarm warning in `hooks/scripts/session-start.sh` that fires when `ll-goals.md` is absent and `product.enabled: true`. After the discovery fallback introduced in ENH-1444, a missing `ll-goals.md` is valid — the hook should no longer treat it as a warning condition.

## Parent Issue

Decomposed from ENH-1442: Goals Discovery — Core Implementation (scan-product, product-analyzer, hooks, tests)

## Files to Modify

- `hooks/scripts/session-start.sh:134–143` — `validate_enabled_features()` product block; downgrade `"Warning: product.enabled is true but goals file not found"` to an informational `Note:` or remove the block entirely
- `scripts/tests/test_hooks_integration.py:1649` — `test_warns_product_without_goals`; update to assert new informational message or remove if warning block is dropped

## Implementation Steps

1. **Update `hooks/scripts/session-start.sh`** — In `validate_enabled_features()` lines 134–143: the block reads `product.enabled` + `product.goals_file`, then runs `[ ! -f "$goals_file" ]` and echoes `"[little-loops] Warning: product.enabled is true but goals file not found: $goals_file"` to stderr. Change to:
   - Option A (preferred): emit `[little-loops] Note: ll-goals.md not found — goals will be synthesized from discovered docs`
   - Option B: remove the block entirely

2. **Update `scripts/tests/test_hooks_integration.py:1649`** — `test_warns_product_without_goals` (lines 1649–1669): update assertion to match new informational message if kept, or remove the test if the warning block is dropped

3. **Verify `scripts/tests/test_hooks_integration.py:1671`** — `test_no_warnings_when_properly_configured`: stays green post-change; if Option A (Note message retained), consider whether a new assertion for the `Note:` message is needed or whether the test remains a meaningful smoke test

4. **Run tests**: `python -m pytest scripts/tests/test_hooks_integration.py -v -k "product"`

## Acceptance Criteria

- Hook no longer emits a false-alarm `Warning:` when `ll-goals.md` is absent and `product.enabled: true`
- `test_hooks_integration.py` product tests pass with updated or removed assertions

## Codebase Reference

- `hooks/scripts/session-start.sh:134–143` — current warning block
- `scripts/tests/test_hooks_integration.py:1649–1669` — `test_warns_product_without_goals`
- `scripts/tests/test_hooks_integration.py:1671` — `test_no_warnings_when_properly_configured`

## Status

**Open** | Created: 2026-05-11 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-05-11T19:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0abadba2-fa26-422a-8f2e-9ed2d2744c98.jsonl`
