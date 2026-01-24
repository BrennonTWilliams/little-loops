# BUG-078: Hooks Portability and Matcher Issues - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-078-hooks-portability-and-matcher-issues.md
- **Type**: bug
- **Priority**: P2 (Medium)
- **Action**: fix

## Current State Analysis

### Key Discoveries
- `hooks/hooks.json:9` - SessionStart uses inline bash command
- `hooks/hooks.json:20` - UserPromptSubmit uses inline bash command
- `hooks/hooks.json:54` - Stop uses inline bash command
- `hooks/hooks.json:28` - PreToolUse matcher is `"Write"` but script at `check-duplicate-issue-id.sh:31` checks for both Write and Edit
- `hooks/hooks.json:32,43` - PreToolUse and PostToolUse correctly use `${CLAUDE_PLUGIN_ROOT}`
- `hooks/check-duplicate-issue-id.sh:10` - Uses `set -uo pipefail` (missing `-e` flag)
- `hooks/scripts/context-monitor.sh:10` - Uses `set -euo pipefail` (correct pattern)
- `hooks/scripts/context-monitor.sh:65,72,80` - Uses `bc` command without availability check

### Current Directory Structure
```
hooks/
├── hooks.json                      # Hook configuration
├── check-duplicate-issue-id.sh     # PreToolUse script
├── scripts/
│   └── context-monitor.sh          # PostToolUse script
└── prompts/
    └── continuation-prompt-template.md
```

## Desired End State

1. All hooks use `${CLAUDE_PLUGIN_ROOT}` for script paths (portable)
2. All hooks have explicit `matcher` fields
3. PreToolUse matcher is `"Write|Edit"` to match script behavior
4. Scripts have consistent `set -euo pipefail` error handling
5. `context-monitor.sh` has `bc` fallback for portability

### How to Verify
- Start Claude Code session - SessionStart hook runs
- Submit prompt without config - UserPromptSubmit warning appears
- Edit an issue file with duplicate ID - PreToolUse blocks it
- End session - Stop cleanup runs
- Test on system without `bc` - context-monitor works (falls back to bash arithmetic)

## What We're NOT Doing

- Not changing hook timeouts - current values are reasonable
- Not restructuring the hook event types or adding new hooks
- Not changing the logic inside any scripts except for error handling fixes
- Not moving `check-duplicate-issue-id.sh` to `scripts/` subdirectory (maintaining current structure)

## Problem Analysis

### Root Causes
1. **Portability**: Inline bash commands were likely used for simplicity during initial development but prevent proper installation in non-standard locations
2. **Missing matchers**: The hooks schema doesn't require matchers, so they were omitted
3. **Matcher mismatch**: PreToolUse was added for Write operations, then script was updated to handle Edit too without updating the matcher
4. **Inconsistent error handling**: Scripts were written at different times with different patterns

## Solution Approach

Extract inline bash commands into standalone scripts in `hooks/scripts/`, update hooks.json to reference them via `${CLAUDE_PLUGIN_ROOT}`, add missing matcher fields, fix the PreToolUse matcher, and standardize error handling.

## Implementation Phases

### Phase 1: Create New Hook Scripts

#### Overview
Extract the inline bash commands from SessionStart, UserPromptSubmit, and Stop hooks into separate script files.

#### Changes Required

**File**: `hooks/scripts/session-start.sh` [CREATE]
**Changes**: New script extracted from SessionStart inline command

```bash
#!/bin/bash
#
# session-start.sh
# SessionStart hook for little-loops plugin
#
# Cleans up state from previous session and loads/displays config
#

set -euo pipefail

# Clean up state from previous session
rm -f .claude/ll-context-state.json 2>/dev/null || true

# Find config file
CONFIG_FILE=".claude/ll-config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="ll-config.json"
fi

# Display config or warning
if [ -f "$CONFIG_FILE" ]; then
    echo "[little-loops] Config loaded: $CONFIG_FILE"
    head -50 "$CONFIG_FILE"
else
    echo "[little-loops] Warning: No config found. Run /ll:init to create one."
fi
```

**File**: `hooks/scripts/user-prompt-check.sh` [CREATE]
**Changes**: New script extracted from UserPromptSubmit inline command

```bash
#!/bin/bash
#
# user-prompt-check.sh
# UserPromptSubmit hook for little-loops plugin
#
# Reminds user to initialize config if not present
#

set -euo pipefail

# Check if config file exists
if [ ! -f ".claude/ll-config.json" ] && [ ! -f "ll-config.json" ]; then
    echo "[little-loops] No config found. Run /ll:init to set up little-loops for this project."
fi
```

**File**: `hooks/scripts/session-cleanup.sh` [CREATE]
**Changes**: New script extracted from Stop inline command

```bash
#!/bin/bash
#
# session-cleanup.sh
# Stop hook for little-loops plugin
#
# Cleans up lock files, state, and git worktrees
#

set -euo pipefail

# Clean up lock and state files
rm -f .claude/.ll-lock .claude/ll-context-state.json 2>/dev/null || true

# Clean up git worktrees if present
if [ -d .worktrees ] && command -v git >/dev/null 2>&1; then
    git worktree list 2>/dev/null | grep .worktrees | awk '{print $1}' | while read -r w; do
        git worktree remove --force "$w" 2>/dev/null || true
    done
fi

echo "[little-loops] Session cleanup complete"
```

#### Success Criteria

**Automated Verification**:
- [ ] Scripts are executable: `ls -la hooks/scripts/*.sh`
- [ ] Scripts have correct shebang: `head -1 hooks/scripts/*.sh`
- [ ] Scripts pass shellcheck (if available): `shellcheck hooks/scripts/*.sh 2>/dev/null || echo "shellcheck not installed"`

**Manual Verification**:
- [ ] Review scripts match original inline command logic

---

### Phase 2: Fix Existing Scripts

#### Overview
Add `-e` flag to check-duplicate-issue-id.sh and add `bc` fallback to context-monitor.sh.

#### Changes Required

**File**: `hooks/check-duplicate-issue-id.sh`
**Changes**: Change line 10 from `set -uo pipefail` to `set -euo pipefail`

```diff
-set -uo pipefail
+set -euo pipefail
```

**File**: `hooks/scripts/context-monitor.sh`
**Changes**: Add `bc` availability check and fallback using bash arithmetic. Update lines 65, 72, and 80.

For each `bc` usage, wrap in a function that falls back to bash integer arithmetic:

```bash
# Add this helper function after line 11 (after set -euo pipefail)
# Calculate arithmetic expression - uses bc if available, else bash
calc() {
    if command -v bc &>/dev/null; then
        echo "$1" | bc 2>/dev/null || echo "0"
    else
        # Fallback to bash integer arithmetic (truncates decimals)
        # Convert float multiplier to integer operation where possible
        echo "$((${1%%.*}))" 2>/dev/null || echo "0"
    fi
}
```

Then update the `bc` usages:
- Line 65: `tokens=$(calc "$lines * $READ_PER_LINE")` or use bash: `tokens=$((lines * READ_PER_LINE))`
- Line 72: `tokens=$(calc "$output * 5")` or use bash: `tokens=$((output * 5))`
- Line 80: For the `* 0.3` case, use: `tokens=$((total_len * 3 / 10))`

The simpler approach is to replace `bc` calls directly with bash arithmetic since all multipliers can be converted to integer operations.

#### Success Criteria

**Automated Verification**:
- [ ] check-duplicate-issue-id.sh has `-e` flag: `grep "set -euo pipefail" hooks/check-duplicate-issue-id.sh`
- [ ] context-monitor.sh has no unprotected `bc` calls: `grep -n '| bc' hooks/scripts/context-monitor.sh` (should show no matches or all wrapped)

**Manual Verification**:
- [ ] Test context-monitor.sh logic still works (token estimation produces reasonable values)

---

### Phase 3: Update hooks.json

#### Overview
Update hooks.json to use `${CLAUDE_PLUGIN_ROOT}` for all scripts and add explicit matcher fields.

#### Changes Required

**File**: `hooks/hooks.json`
**Changes**: Complete rewrite with proper structure

```json
{
  "$schema": "https://claude.ai/schemas/hooks/v1",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-start.sh",
            "timeout": 5000
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/user-prompt-check.sh",
            "timeout": 3000
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
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/check-duplicate-issue-id.sh",
            "timeout": 5000
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/context-monitor.sh",
            "timeout": 5000
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-cleanup.sh",
            "timeout": 15000
          }
        ]
      }
    ]
  }
}
```

Key changes:
- SessionStart: Inline command → script, added `"matcher": "*"`
- UserPromptSubmit: Inline command → script, added `"matcher": "*"`
- PreToolUse: Changed `"matcher": "Write"` to `"matcher": "Write|Edit"`
- PostToolUse: Added `"matcher": "*"`
- Stop: Inline command → script, added `"matcher": "*"`

#### Success Criteria

**Automated Verification**:
- [ ] hooks.json is valid JSON: `python3 -c "import json; json.load(open('hooks/hooks.json'))"`
- [ ] All hooks have matcher field: `grep -c '"matcher"' hooks/hooks.json` (should be 5)
- [ ] No inline bash -c: `grep 'bash -c' hooks/hooks.json` (should return nothing)
- [ ] All commands use CLAUDE_PLUGIN_ROOT: `grep -c 'CLAUDE_PLUGIN_ROOT' hooks/hooks.json` (should be 5)

**Manual Verification**:
- [ ] JSON structure matches expected schema

---

### Phase 4: Make Scripts Executable

#### Overview
Ensure all new scripts have executable permissions.

#### Changes Required

```bash
chmod +x hooks/scripts/session-start.sh
chmod +x hooks/scripts/user-prompt-check.sh
chmod +x hooks/scripts/session-cleanup.sh
```

#### Success Criteria

**Automated Verification**:
- [ ] All scripts executable: `ls -la hooks/scripts/*.sh | grep -c "^-rwx"` (should be 4)

---

## Testing Strategy

### Unit Tests
- Verify each script runs without errors when executed directly
- Verify scripts exit with appropriate codes

### Integration Tests
1. Start new Claude Code session - SessionStart hook should run
2. Submit prompt in project without config - UserPromptSubmit warning should appear
3. Try to create issue file with duplicate ID - PreToolUse should block
4. Try to edit issue file with duplicate ID - PreToolUse should now also check (was broken before)
5. End session - Stop hook should clean up

## References

- Original issue: `.issues/bugs/P2-BUG-078-hooks-portability-and-matcher-issues.md`
- Existing portable pattern: `hooks/hooks.json:32` (PreToolUse)
- Error handling pattern: `hooks/scripts/context-monitor.sh:10`
