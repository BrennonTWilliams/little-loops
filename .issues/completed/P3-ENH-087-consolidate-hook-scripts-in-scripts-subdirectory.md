# ENH-087: Consolidate Hook Scripts in scripts/ Subdirectory

## Summary

The `hooks/` directory has inconsistent organization with one script at the root level while others are properly placed in the `scripts/` subdirectory.

## Current State

```
hooks/
├── check-duplicate-issue-id.sh   ← At hooks/ root (inconsistent)
├── hooks.json
├── prompts/
└── scripts/
    ├── context-monitor.sh        ← In scripts/ subdirectory (correct)
    ├── session-cleanup.sh
    ├── session-start.sh
    └── user-prompt-check.sh
```

The `hooks.json` references this inconsistency (see lines 28-38 vs 40-50):
- PreToolUse uses `hooks/check-duplicate-issue-id.sh` (root level)
- All other hooks use `hooks/scripts/*.sh` (scripts subdirectory)

## Proposed Enhancement

Move `check-duplicate-issue-id.sh` to the `scripts/` subdirectory for consistency:

```
hooks/
├── hooks.json
├── prompts/
└── scripts/
    ├── check-duplicate-issue-id.sh  ← Moved here
    ├── context-monitor.sh
    ├── session-cleanup.sh
    ├── session-start.sh
    └── user-prompt-check.sh
```

## Implementation

1. Move the script:
   ```bash
   git mv hooks/check-duplicate-issue-id.sh hooks/scripts/
   ```

2. Update `hooks/hooks.json` PreToolUse command path:
   ```json
   "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check-duplicate-issue-id.sh"
   ```

## Benefits

- Consistent directory organization
- All hook scripts in one location for easier maintenance
- Cleaner `hooks/` root directory

## References

- `hooks/hooks.json:34` - PreToolUse command path reference
- `hooks/check-duplicate-issue-id.sh` - Script to be moved
- Plugin structure best practices

## Discovered By

Plugin structure audit using `plugin-dev:plugin-structure` skill

## Labels

- `hooks`
- `organization`
- `low-effort`

## Status

Completed

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-17
- **Status**: Completed

### Changes Made
- `hooks/check-duplicate-issue-id.sh`: Moved to `hooks/scripts/check-duplicate-issue-id.sh`
- `hooks/hooks.json`: Updated PreToolUse command path to `hooks/scripts/check-duplicate-issue-id.sh`

### Verification Results
- Tests: PASS
- JSON validation: PASS
- Script executable: PASS
