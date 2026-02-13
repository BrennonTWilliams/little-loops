---
discovered_date: 2026-02-12
discovered_by: hooks-reference-audit
---

# ENH-377: Remove silently-ignored matchers from UserPromptSubmit and Stop hooks

## Summary

Both the `UserPromptSubmit` and `Stop` entries in `hooks/hooks.json` define `"matcher": "*"`. Per the hooks reference, these events do not support matchers — the field is silently ignored. The matchers create a false impression of filtering and could confuse future maintainers.

## Location

- **File**: `hooks/hooks.json:17` (UserPromptSubmit)
- **File**: `hooks/hooks.json:53` (Stop)

## Current Behavior

```json
"UserPromptSubmit": [
  {
    "matcher": "*",  // silently ignored
    ...
  }
],
"Stop": [
  {
    "matcher": "*",  // silently ignored
    ...
  }
]
```

## Expected Behavior

Remove the `matcher` field from both entries:

```json
"UserPromptSubmit": [
  {
    "hooks": [ ... ]
  }
],
"Stop": [
  {
    "hooks": [ ... ]
  }
]
```

## Motivation

This enhancement would:
- Improve configuration clarity by removing misleading fields that are silently ignored
- Business value: Future maintainers won't be confused by `"matcher": "*"` on events that don't support matching
- Technical debt: Eliminates dead configuration that contradicts the hooks reference documentation

## Implementation Steps

1. **Remove matcher from UserPromptSubmit**: Delete `"matcher": "*"` from the UserPromptSubmit entry at `hooks/hooks.json:17`
2. **Remove matcher from Stop**: Delete `"matcher": "*"` from the Stop entry at `hooks/hooks.json:53`
3. **Validate hooks.json**: Ensure the resulting `hooks.json` is valid JSON and all hooks still trigger correctly
4. **Manual verification**: Confirm UserPromptSubmit and Stop hooks fire as expected without matcher fields

## Integration Map

- **Files to Modify**: `hooks/hooks.json`
- **Dependent Files (Callers/Importers)**: Claude Code hook event system (reads hooks.json)
- **Similar Patterns**: Other hook entries in `hooks/hooks.json` that correctly omit matchers
- **Tests**: N/A — hook configuration cleanup; verified by triggering UserPromptSubmit and Stop hooks
- **Documentation**: `docs/claude-code/hooks-reference.md`
- **Configuration**: `hooks/hooks.json`

## Reference

- `docs/claude-code/hooks-reference.md` — Matcher patterns table: `UserPromptSubmit, Stop, TeammateIdle, TaskCompleted | no matcher support | always fires on every occurrence`
- `docs/claude-code/hooks-reference.md`: "UserPromptSubmit and Stop don't support matchers and always fire on every occurrence. If you add a matcher field to these events, it is silently ignored."

## Impact

- **Priority**: P4
- **Effort**: Trivial
- **Risk**: None — no behavioral change

## Labels

`enhancement`, `hooks`, `configuration`, `cleanup`

## Blocks

- ENH-371: add description and statusMessage to hooks.json (shared hooks.json, hooks-reference.md)

## Session Log
- `/ll:format_issue --all --auto` - 2026-02-13

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
