# ENH-370: session-start.sh Config Truncation Inconsistency - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-370-session-start-config-truncation-inconsistency.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

`hooks/scripts/session-start.sh` has two code paths for outputting configuration:

1. **Merge path** (line 150): When `.claude/ll.local.md` exists, calls `merge_local_config()` which uses Python to output the **full** config via `print(config_text)` (line 94) or `print(json.dumps(merged, indent=2))` (line 82).

2. **Non-merge path** (line 153): When no local overrides exist, uses `head -50 "$CONFIG_FILE"` which **truncates** output to 50 lines.

### Key Discoveries
- The truncation happens at `hooks/scripts/session-start.sh:153`
- The current project config (`.claude/ll-config.json`) is 51 lines — meaning it's already truncated by 1 line in the non-merge path
- The Python merge path warns at 5000+ chars but never truncates
- The `echo` diagnostic on line 152 goes to stdout (not stderr), which is inconsistent with the merge path that uses `file=sys.stderr`

## Desired End State

Both code paths output the full config content without truncation.

### How to Verify
- Run `bash hooks/scripts/session-start.sh` without `.claude/ll.local.md` present and confirm full config is output
- Compare output line count with actual config file line count
- Run existing tests to confirm no regressions

## What We're NOT Doing

- Not changing the Python merge path behavior
- Not adding truncation to the Python path
- Not adding size warnings to the shell path (keeping the change minimal)

## Problem Analysis

`head -50` was likely added as a safety measure to prevent enormous configs from flooding Claude's context. However, the Python path already handles this concern better (warns at >5000 chars but doesn't truncate), and configs are typically well under 100 lines. The inconsistency means Claude sees different config content depending on an unrelated factor (local overrides existing or not).

## Solution Approach

Replace `head -50 "$CONFIG_FILE"` with `cat "$CONFIG_FILE"` on line 153. Additionally, fix the diagnostic echo on line 152 to use `>&2` for stderr consistency with the Python path.

## Code Reuse & Integration

- **Pattern to follow**: The Python merge path at lines 87-94 outputs full config with `print(config_text)` — the shell path should match this behavior using `cat`
- **Established convention**: Other hook scripts (e.g., `context-monitor.sh:115`) use `cat` for full file output

## Implementation Phases

### Phase 1: Fix Config Output

#### Overview
Replace truncated output with full output and fix stderr consistency.

#### Changes Required

**File**: `hooks/scripts/session-start.sh`
**Changes**:
1. Line 152: Add `>&2` to redirect diagnostic message to stderr (matches Python path convention)
2. Line 153: Replace `head -50` with `cat`

Before:
```bash
        echo "[little-loops] Config loaded: $CONFIG_FILE"
        head -50 "$CONFIG_FILE"
```

After:
```bash
        echo "[little-loops] Config loaded: $CONFIG_FILE" >&2
        cat "$CONFIG_FILE"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Running `bash hooks/scripts/session-start.sh` without local overrides outputs full config

## Testing Strategy

- Existing integration tests in `scripts/tests/test_hooks_integration.py` cover session-start validation behavior
- The change is a single-line shell substitution — existing tests confirm no regressions

## References

- Original issue: `.issues/enhancements/P4-ENH-370-session-start-config-truncation-inconsistency.md`
- Python full output pattern: `hooks/scripts/session-start.sh:94`
- Shell cat pattern: `hooks/scripts/context-monitor.sh:115`
