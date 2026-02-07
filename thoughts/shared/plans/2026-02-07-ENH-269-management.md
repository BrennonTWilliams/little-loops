# ENH-269: Unify Feature Flag Checking - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-269-unify-feature-flag-checking.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The plugin has 8 `enabled` boolean flags across `ll-config.json`, each checked by consumers using 3+ different patterns with no centralization.

### Key Discoveries
- Shell hooks (`context-monitor.sh:20-39`, `user-prompt-check.sh:16-46`) duplicate config file resolution and `jq` feature flag checking inline
- The shared library `hooks/scripts/lib/common.sh` exists but has no config or feature flag utilities
- `user-prompt-check.sh` does NOT source `common.sh`, unlike other hooks
- `user-prompt-check.sh:43` defaults `prompt_optimization.enabled` to `false` via jq, contradicting the schema default of `true`
- `session-start.sh` performs zero validation of enabled features' sub-configuration
- Commands/skills use template interpolation + prose guard clauses with inconsistent wording
- `continuation.enabled` and `workflow.phase_gates.enabled` are never checked by any consumer

### Patterns Found
1. **Shell jq**: `jq -r '.section.enabled // false' "$CONFIG_FILE"` — used by 2 hooks
2. **Template display**: `{{config.X.enabled}}` — used by ~6 commands for display
3. **Prose guard**: "Skip this phase if X.enabled is not true" — used by ~6 commands/skills
4. **Python typed**: `config.sync.enabled` — used by `cli.py` for sync only

## Desired End State

1. A shared `ll_feature_enabled` function in `common.sh` that hooks source for consistent flag checking
2. A shared `ll_resolve_config` function in `common.sh` for config file resolution (DRY)
3. Startup validation in `session-start.sh` that warns about misconfigured enabled features
4. Consistent prose guard pattern standardized across commands/skills

### How to Verify
- Both shell hooks use the new shared functions
- `session-start.sh` warns when `sync.enabled=true` but `sync.github` is empty/missing
- Existing tests pass
- Lint and type checks pass

## What We're NOT Doing

- Not creating a formal feature flag registry — premature at 8 flags
- Not modifying the Python config layer (`config.py`, `cli.py`) — already well-typed
- Not changing `{{config.X.enabled}}` template interpolation — it works correctly for display
- Not rewriting prose guard clauses in all commands — too many files, low ROI
- Not adding a new dependency or tool

## Solution Approach

Implement options 1+2 from the issue's proposed solution: standardize the shell checking pattern via shared functions and add startup validation.

## Implementation Phases

### Phase 1: Add Shared Config Functions to `common.sh`

#### Overview
Add `ll_resolve_config` and `ll_feature_enabled` functions to `hooks/scripts/lib/common.sh`.

#### Changes Required

**File**: `hooks/scripts/lib/common.sh`
**Changes**: Add two new functions at the end of the file

```bash
# Resolve ll-config.json file path
# Usage: ll_resolve_config
# Sets: LL_CONFIG_FILE (empty string if not found)
ll_resolve_config() {
    LL_CONFIG_FILE=""
    if [ -f ".claude/ll-config.json" ]; then
        LL_CONFIG_FILE=".claude/ll-config.json"
    elif [ -f "ll-config.json" ]; then
        LL_CONFIG_FILE="ll-config.json"
    fi
}

# Check if a feature flag is enabled in ll-config.json
# Usage: ll_feature_enabled "section.enabled"
# Returns: 0 if enabled, 1 if disabled/missing/no-jq
# Requires: ll_resolve_config called first, jq available
ll_feature_enabled() {
    local flag_path="$1"

    if [ -z "$LL_CONFIG_FILE" ]; then
        return 1
    fi

    if ! command -v jq &> /dev/null; then
        return 1
    fi

    local enabled
    enabled=$(jq -r ".${flag_path} // false" "$LL_CONFIG_FILE" 2>/dev/null || echo "false")
    [ "$enabled" = "true" ]
}
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Shell syntax valid: `bash -n hooks/scripts/lib/common.sh`

---

### Phase 2: Refactor Hooks to Use Shared Functions

#### Overview
Update `context-monitor.sh` and `user-prompt-check.sh` to use the new shared functions, removing duplicated config resolution and flag checking.

#### Changes Required

**File**: `hooks/scripts/context-monitor.sh`
**Changes**: Replace inline config resolution and feature flag check (lines 19-39) with shared functions. The file already sources `common.sh`.

**File**: `hooks/scripts/user-prompt-check.sh`
**Changes**:
1. Add `source` of `common.sh` (currently missing)
2. Replace inline config resolution (lines 15-21) and flag check (lines 42-46) with shared functions

#### Success Criteria

**Automated Verification**:
- [ ] Shell syntax valid: `bash -n hooks/scripts/context-monitor.sh`
- [ ] Shell syntax valid: `bash -n hooks/scripts/user-prompt-check.sh`
- [ ] Tests pass: `python -m pytest scripts/tests/`

---

### Phase 3: Add Startup Validation to `session-start.sh`

#### Overview
Add a validation step to `session-start.sh` that checks enabled features have required sub-configuration and emits warnings.

#### Changes Required

**File**: `hooks/scripts/session-start.sh`
**Changes**: After config display, add a validation function that checks:
- `sync.enabled=true` → `sync.github` section should exist
- `documents.enabled=true` → `documents.categories` should have entries
- `product.enabled=true` → goals file should exist
- Emit `[little-loops] Warning:` messages to stderr for misconfigured features

```bash
# Validate enabled features have required sub-configuration
validate_enabled_features() {
    local config_file="$1"

    if ! command -v jq &> /dev/null; then
        return 0
    fi

    # sync.enabled requires sync.github
    local sync_enabled
    sync_enabled=$(jq -r '.sync.enabled // false' "$config_file" 2>/dev/null)
    if [ "$sync_enabled" = "true" ]; then
        local github_keys
        github_keys=$(jq -r '.sync.github // {} | keys | length' "$config_file" 2>/dev/null)
        if [ "$github_keys" = "0" ]; then
            echo "[little-loops] Warning: sync.enabled is true but sync.github is not configured" >&2
        fi
    fi

    # documents.enabled requires documents.categories
    local docs_enabled
    docs_enabled=$(jq -r '.documents.enabled // false' "$config_file" 2>/dev/null)
    if [ "$docs_enabled" = "true" ]; then
        local cat_keys
        cat_keys=$(jq -r '.documents.categories // {} | keys | length' "$config_file" 2>/dev/null)
        if [ "$cat_keys" = "0" ]; then
            echo "[little-loops] Warning: documents.enabled is true but no document categories configured" >&2
        fi
    fi

    # product.enabled requires goals file
    local product_enabled
    product_enabled=$(jq -r '.product.enabled // false' "$config_file" 2>/dev/null)
    if [ "$product_enabled" = "true" ]; then
        local goals_file
        goals_file=$(jq -r '.product.goals_file // ".claude/ll-goals.md"' "$config_file" 2>/dev/null)
        if [ ! -f "$goals_file" ]; then
            echo "[little-loops] Warning: product.enabled is true but goals file not found: $goals_file" >&2
        fi
    fi
}
```

#### Success Criteria

**Automated Verification**:
- [ ] Shell syntax valid: `bash -n hooks/scripts/session-start.sh`
- [ ] Tests pass: `python -m pytest scripts/tests/`

---

### Phase 4: Add Tests for Shared Functions

#### Overview
Add shell function tests to validate the new shared utilities work correctly.

#### Changes Required

**File**: `scripts/tests/test_shell_hooks.py` (or existing test file for hooks)
**Changes**: Add test cases that:
- Verify `ll_resolve_config` finds config in `.claude/ll-config.json`
- Verify `ll_feature_enabled` returns 0/1 correctly
- Verify startup validation warns on misconfigured features

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Test `ll_resolve_config` sets `LL_CONFIG_FILE` correctly for both paths
- Test `ll_feature_enabled` returns true/false correctly
- Test `validate_enabled_features` emits correct warnings

### Integration Tests
- Verify hooks still function with shared functions (syntax checks)
- Verify session-start outputs warnings for known misconfigurations

## References

- Original issue: `.issues/enhancements/P3-ENH-269-unify-feature-flag-checking.md`
- Shared library: `hooks/scripts/lib/common.sh:1-179`
- Config resolution duplication: `context-monitor.sh:20-28`, `user-prompt-check.sh:16-21`, `session-start.sh:16-19`
- Feature flag patterns: `context-monitor.sh:36-39`, `user-prompt-check.sh:43-46`
