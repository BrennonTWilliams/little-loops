# ENH-087: Consolidate Hook Scripts in scripts/ Subdirectory - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-087-consolidate-hook-scripts-in-scripts-subdirectory.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `hooks/` directory has inconsistent organization:

```
hooks/
├── check-duplicate-issue-id.sh   ← At root level (inconsistent)
├── hooks.json
├── prompts/
└── scripts/
    ├── context-monitor.sh        ← In scripts/ (consistent)
    ├── session-cleanup.sh
    ├── session-start.sh
    └── user-prompt-check.sh
```

### Key Discoveries
- `hooks/hooks.json:34` - PreToolUse references `hooks/check-duplicate-issue-id.sh` (root level)
- `hooks/hooks.json:10,22,46,58` - All other hooks reference `hooks/scripts/*.sh` (scripts subdirectory)
- The script `check-duplicate-issue-id.sh` exists and is executable at `hooks/` root

## Desired End State

All hook scripts consolidated in `hooks/scripts/`:

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

### How to Verify
- Script exists at new location with correct permissions
- hooks.json references new path
- Lint and type checks pass

## What We're NOT Doing
- Not modifying the script content itself
- Not changing any other hooks.json configurations
- Not restructuring the prompts/ directory

## Solution Approach

Simple two-step change:
1. Git move the script file to scripts/ subdirectory
2. Update the path in hooks.json

## Implementation Phases

### Phase 1: Move Script and Update Reference

#### Overview
Move script file and update hooks.json in a single atomic change.

#### Changes Required

**File**: `hooks/check-duplicate-issue-id.sh`
**Changes**: Move to `hooks/scripts/check-duplicate-issue-id.sh`

**File**: `hooks/hooks.json`
**Changes**: Update PreToolUse command path from line 34

```json
"command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check-duplicate-issue-id.sh"
```

#### Success Criteria

**Automated Verification**:
- [ ] Script exists at `hooks/scripts/check-duplicate-issue-id.sh`
- [ ] Script is executable
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Tests pass: `python -m pytest scripts/tests/`

**Manual Verification**:
- [ ] hooks.json is valid JSON
- [ ] Path in hooks.json correctly points to new location

## Testing Strategy

### Validation
- JSON parsing of hooks.json
- File existence check at new location

## References

- Original issue: `.issues/enhancements/P3-ENH-087-consolidate-hook-scripts-in-scripts-subdirectory.md`
- hooks.json: `hooks/hooks.json:34`
