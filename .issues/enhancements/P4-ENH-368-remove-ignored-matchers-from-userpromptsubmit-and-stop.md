---
discovered_date: 2026-02-12
discovered_by: hooks-reference-audit
---

# ENH-368: Remove silently-ignored matchers from UserPromptSubmit and Stop hooks

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

## Reference

- `docs/claude-code/hooks-reference.md` — Matcher patterns table: `UserPromptSubmit, Stop, TeammateIdle, TaskCompleted | no matcher support | always fires on every occurrence`
- `docs/claude-code/hooks-reference.md`: "UserPromptSubmit and Stop don't support matchers and always fire on every occurrence. If you add a matcher field to these events, it is silently ignored."

## Impact

- **Priority**: P4
- **Effort**: Trivial
- **Risk**: None — no behavioral change

## Labels

`enhancement`, `hooks`, `configuration`, `cleanup`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
