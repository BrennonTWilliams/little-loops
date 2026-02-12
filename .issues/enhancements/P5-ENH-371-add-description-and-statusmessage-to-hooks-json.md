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

## Reference

- `docs/claude-code/hooks-reference.md` — Plugin scripts: "Define plugin hooks in hooks/hooks.json with an optional top-level `description` field"
- `docs/claude-code/hooks-reference.md` — Common fields: `statusMessage | no | Custom spinner message displayed while the hook runs`

## Impact

- **Priority**: P5
- **Effort**: Trivial
- **Risk**: None

## Labels

`enhancement`, `hooks`, `configuration`, `ux`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P5
