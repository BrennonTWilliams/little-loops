# BUG-076: Duplicate Plugin Manifests with Missing Component Paths - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P1-BUG-076-duplicate-plugin-manifests-missing-component-paths.md`
- **Type**: bug
- **Priority**: P1
- **Action**: fix

## Current State Analysis

Two `plugin.json` files exist:

1. **Root `plugin.json`** (complete but non-canonical):
   - Location: `/plugin.json`
   - Has all component paths: commands, skills, agents, hooks
   - Paths use `./` relative to repo root

2. **`.claude-plugin/plugin.json`** (canonical but incomplete):
   - Location: `/.claude-plugin/plugin.json`
   - Missing: commands, skills, agents paths
   - Only has hooks path (but incorrectly specified as `./hooks/hooks.json`)

### Key Discoveries
- `marketplace.json` at `.claude-plugin/marketplace.json:13` has `"source": "./"` pointing to `.claude-plugin/`
- Component directories exist at repo root: `commands/` (21 files), `skills/` (3 files), `agents/` (8 files), `hooks/`
- No component directories exist inside `.claude-plugin/`
- Current hooks path in `.claude-plugin/plugin.json:17` would resolve incorrectly

## Desired End State

Single `plugin.json` at `.claude-plugin/plugin.json` with:
- All metadata preserved
- Component paths correctly pointing to repo root using `../` prefix

### How to Verify
- Root `plugin.json` no longer exists
- `.claude-plugin/plugin.json` contains all component paths with `../` prefix
- Plugin loads correctly in new Claude Code session

## What We're NOT Doing

- Not moving component directories into `.claude-plugin/`
- Not changing `marketplace.json`
- Not modifying actual commands, skills, agents, or hooks
- Not changing documentation references to `plugin.json`

## Problem Analysis

The plugin has duplicate manifests due to incomplete migration to the `.claude-plugin/` convention. The canonical location (`.claude-plugin/plugin.json`) lacks component path registrations and has an incorrect hooks path that would resolve to a non-existent location.

## Solution Approach

1. Update `.claude-plugin/plugin.json` to include all component paths with `../` prefix to reach repo root
2. Delete root `plugin.json`
3. Verify paths resolve correctly

## Implementation Phases

### Phase 1: Update .claude-plugin/plugin.json

#### Overview
Add missing component paths and fix existing hooks path to use parent-relative paths.

#### Changes Required

**File**: `.claude-plugin/plugin.json`
**Changes**: Add commands, skills, agents paths; fix hooks path

Current:
```json
{
  "name": "ll",
  "version": "1.0.0",
  "description": "Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing",
  "author": {
    "name": "little-loops"
  },
  "license": "MIT",
  "homepage": "https://github.com/BrennonTWilliams/little-loops",
  "keywords": [
    "development",
    "workflow",
    "issue-management",
    "automation",
    "code-quality"
  ],
  "hooks": "./hooks/hooks.json"
}
```

Target:
```json
{
  "name": "ll",
  "version": "1.0.0",
  "description": "Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing",
  "author": {
    "name": "little-loops"
  },
  "license": "MIT",
  "homepage": "https://github.com/BrennonTWilliams/little-loops",
  "keywords": [
    "development",
    "workflow",
    "issue-management",
    "automation",
    "code-quality"
  ],
  "commands": "../commands/",
  "skills": "../skills/",
  "agents": "../agents/",
  "hooks": "../hooks/hooks.json"
}
```

#### Success Criteria

**Automated Verification**:
- [ ] File `.claude-plugin/plugin.json` contains `"commands": "../commands/"`
- [ ] File `.claude-plugin/plugin.json` contains `"skills": "../skills/"`
- [ ] File `.claude-plugin/plugin.json` contains `"agents": "../agents/"`
- [ ] File `.claude-plugin/plugin.json` contains `"hooks": "../hooks/hooks.json"`

---

### Phase 2: Delete Root plugin.json

#### Overview
Remove the duplicate manifest from repo root.

#### Changes Required

**File**: `plugin.json` (root)
**Changes**: Delete file

```bash
git rm plugin.json
```

#### Success Criteria

**Automated Verification**:
- [ ] File `plugin.json` does not exist at repo root

---

### Phase 3: Verify Resolution

#### Overview
Confirm paths in manifest resolve to actual directories.

#### Success Criteria

**Automated Verification**:
- [ ] `commands/` directory exists at repo root
- [ ] `skills/` directory exists at repo root
- [ ] `agents/` directory exists at repo root
- [ ] `hooks/hooks.json` file exists at repo root

**Manual Verification**:
- [ ] Start new Claude Code session
- [ ] Verify `/ll:help` lists all commands
- [ ] Verify agents are available via Task tool

## Testing Strategy

### Validation
- Check that all relative paths from `.claude-plugin/plugin.json` resolve to existing directories
- Verify JSON is valid after edit

## References

- Original issue: `.issues/bugs/P1-BUG-076-duplicate-plugin-manifests-missing-component-paths.md`
- Marketplace config: `.claude-plugin/marketplace.json:13`
- Root manifest: `plugin.json`
- Canonical manifest: `.claude-plugin/plugin.json`
