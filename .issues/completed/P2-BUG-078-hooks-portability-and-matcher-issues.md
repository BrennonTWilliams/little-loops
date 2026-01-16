# BUG-078: Hooks Portability and Matcher Issues

## Summary

The `hooks/hooks.json` configuration has several issues affecting portability, correctness, and maintainability:
1. Inline bash commands instead of `${CLAUDE_PLUGIN_ROOT}` scripts (portability)
2. Missing `matcher` fields on several hooks
3. PreToolUse matcher mismatch (functional bug)

## Severity

**Priority:** P2 (Medium)
**Impact:** Hooks may not work correctly when plugin is installed in different locations; PreToolUse hook doesn't trigger for Edit operations as intended.

## Current Behavior

### 1. Portability Issues (Critical)

Three hooks use inline bash commands instead of `${CLAUDE_PLUGIN_ROOT}` scripts:

| Hook | Line | Issue |
|------|------|-------|
| SessionStart | 9 | Inline bash for config loading and state cleanup |
| UserPromptSubmit | 20 | Inline bash for config check |
| Stop | 54 | Inline bash for session cleanup |

These will break if the plugin is installed in non-standard locations.

### 2. Missing Matchers (High)

Several hooks are missing the `matcher` field:

| Hook | Should Be |
|------|-----------|
| SessionStart | `"matcher": "*"` |
| UserPromptSubmit | `"matcher": "*"` |
| PostToolUse | `"matcher": "*"` |
| Stop | `"matcher": "*"` |

### 3. Matcher Mismatch (High - Functional Bug)

**PreToolUse** (line 28) has matcher `"Write"` but `check-duplicate-issue-id.sh:31` checks for both:
```bash
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
```

The hook never triggers for Edit operations, so duplicate issue ID checks don't run when editing files.

### 4. Script Issues (Medium)

**check-duplicate-issue-id.sh:**
- Uses `set -uo pipefail` but missing `-e` flag

**context-monitor.sh:**
- Depends on `bc` command with no fallback for systems without it

## Expected Behavior

1. All hooks should use `${CLAUDE_PLUGIN_ROOT}` for script paths
2. All hooks should have explicit `matcher` fields
3. PreToolUse matcher should be `"Write|Edit"` to match script behavior
4. Scripts should have consistent error handling and dependency fallbacks

## Reproduction Steps

1. Install plugin in a different location than expected
2. SessionStart, UserPromptSubmit, and Stop hooks may fail
3. Edit an issue file - duplicate ID check doesn't run

## Proposed Fix

### 1. Create new hook scripts

```
hooks/
├── scripts/
│   ├── session-start.sh      # NEW - extract from inline
│   ├── user-prompt-check.sh  # NEW - extract from inline
│   ├── session-cleanup.sh    # NEW - extract from inline
│   └── context-monitor.sh    # existing
└── check-duplicate-issue-id.sh
```

### 2. Update hooks.json

```json
{
  "SessionStart": [{
    "matcher": "*",
    "hooks": [{
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-start.sh",
      "timeout": 5000
    }]
  }],
  "UserPromptSubmit": [{
    "matcher": "*",
    "hooks": [{
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/user-prompt-check.sh",
      "timeout": 3000
    }]
  }],
  "PreToolUse": [{
    "matcher": "Write|Edit",
    "hooks": [{
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/check-duplicate-issue-id.sh",
      "timeout": 5000
    }]
  }],
  "PostToolUse": [{
    "matcher": "*",
    "hooks": [{
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/context-monitor.sh",
      "timeout": 5000
    }]
  }],
  "Stop": [{
    "matcher": "*",
    "hooks": [{
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-cleanup.sh",
      "timeout": 15000
    }]
  }]
}
```

### 3. Script fixes

**check-duplicate-issue-id.sh:** Add `-e` to `set -euo pipefail`

**context-monitor.sh:** Add fallback for `bc`:
```bash
if command -v bc &>/dev/null; then
  tokens=$(echo "$lines * $READ_PER_LINE" | bc)
else
  tokens=$((lines * READ_PER_LINE))
fi
```

## Files to Modify

- `hooks/hooks.json`
- `hooks/check-duplicate-issue-id.sh`
- `hooks/scripts/context-monitor.sh`

## Files to Create

- `hooks/scripts/session-start.sh`
- `hooks/scripts/user-prompt-check.sh`
- `hooks/scripts/session-cleanup.sh`

## Testing

1. Install plugin in a different directory
2. Start Claude Code session - verify SessionStart hook runs
3. Submit a prompt without config - verify UserPromptSubmit warning
4. Edit an issue file with duplicate ID - verify PreToolUse blocks it
5. End session - verify Stop cleanup runs
6. Test on system without `bc` - verify context-monitor works

## Related

- Discovered during hooks audit using `plugin-dev:hook-development` skill

## Metadata

- **Discovered by:** Hooks audit (2026-01-16)
- **Component:** hooks

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-16
- **Status**: Completed

### Changes Made
- `hooks/hooks.json`: Replaced inline bash commands with `${CLAUDE_PLUGIN_ROOT}` script references; added `matcher` fields to all hooks; changed PreToolUse matcher from `"Write"` to `"Write|Edit"`
- `hooks/check-duplicate-issue-id.sh`: Added `-e` flag to `set -euo pipefail` for consistent error handling
- `hooks/scripts/context-monitor.sh`: Replaced `bc` command usage with bash integer arithmetic for portability
- `hooks/scripts/session-start.sh`: New script extracted from SessionStart inline command
- `hooks/scripts/user-prompt-check.sh`: New script extracted from UserPromptSubmit inline command
- `hooks/scripts/session-cleanup.sh`: New script extracted from Stop inline command

### Verification Results
- Tests: PASS (1330 tests)
- Lint: PASS (pre-existing issues unrelated to changes)
- Types: PASS (pre-existing issue with missing anthropic stubs)
- Shell syntax check: PASS (all 5 scripts)
