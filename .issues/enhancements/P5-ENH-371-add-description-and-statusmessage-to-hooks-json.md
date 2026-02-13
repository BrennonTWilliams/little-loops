---
discovered_date: 2026-02-12
discovered_by: hooks-reference-audit
---

# ENH-371: Add description and statusMessage fields to hooks.json

## Summary

`hooks/hooks.json` is missing two optional fields documented in the hooks reference:

1. **Top-level `description`**: shown in the `/hooks` menu to identify the plugin's hooks
2. **Per-hook `statusMessage`**: custom spinner text displayed while each hook runs

## Location

- **File**: `hooks/hooks.json`

## Current Behavior

No `description` field, no `statusMessage` on any hook. Users see default spinner text and no plugin attribution in `/hooks` menu.

## Expected Behavior

```json
{
  "description": "little-loops development workflow hooks",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "...",
            "statusMessage": "Loading ll config..."
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "...",
            "statusMessage": "Checking for duplicate issue IDs..."
          }
        ]
      }
    ]
  }
}
```

Suggested statusMessage values:
- SessionStart: `"Loading ll config..."`
- UserPromptSubmit: `"Checking prompt..."`
- PreToolUse (Write|Edit): `"Checking for duplicate issue IDs..."`
- PostToolUse: `"Monitoring context usage..."`
- Stop: `"Cleaning up session..."`
- PreCompact: `"Preserving task state..."`

## Additional Opportunity: `once` field

The hooks reference also documents a `once` field (`docs/claude-code/hooks-reference.md:257`): if `true`, the hook runs only once per session then is removed. This is useful for skills-only hooks (not agents). Consider whether any skill-defined hooks should use `once: true` for one-time initialization.

## Reference

- `docs/claude-code/hooks-reference.md` — Plugin scripts: "Define plugin hooks in hooks/hooks.json with an optional top-level `description` field"
- `docs/claude-code/hooks-reference.md` — Common fields: `statusMessage | no | Custom spinner message displayed while the hook runs`
- `docs/claude-code/hooks-reference.md:257` — Common fields: `once | no | If true, runs only once per session then is removed. Skills only, not agents.`

## Motivation

This enhancement would:
- Provide better plugin attribution and user feedback during hook execution
- Business value: Users see meaningful spinner text instead of generic messages, improving perceived quality and debuggability
- Technical debt: Aligns hooks.json with all documented optional fields in the hooks reference

## Implementation Steps

1. Add top-level `"description"` field to `hooks/hooks.json`
2. Add `"statusMessage"` to each hook entry with context-appropriate spinner text
3. Evaluate `"once"` field for applicable hooks (e.g., one-time initialization hooks)
4. Validate hooks.json against the hooks reference schema

## Integration Map

### Files to Modify
- `hooks/hooks.json`

### Dependent Files
- N/A

### Similar Patterns
- N/A

### Tests
- Verify spinner text appears during hook execution
- Verify plugin description appears in `/hooks` menu

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P5
- **Effort**: Trivial
- **Risk**: None

## Labels

`enhancement`, `hooks`, `configuration`, `ux`

## Blocked By

- ENH-377: remove ignored matchers from UserPromptSubmit and Stop (shared hooks.json, hooks-reference.md)

## Session Log
- /ll:format_issue --all --auto - 2026-02-13

---

## Status

**Open** | Created: 2026-02-12 | Priority: P5
