# BUG-318: Incorrect CLI flag --include-p0 documented - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-318-incorrect-cli-flag-include-p0-documented.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The README.md documents a non-existent CLI flag `--include-p0` for ll-parallel at line 607. This flag is not defined in `scripts/little_loops/cli.py` and will cause argparse errors when users try to use it.

### Key Discoveries
- Line 607 shows: `ll-parallel --include-p0             # Include P0 in parallel processing`
- No `--include-p0` flag exists in the argparse configuration (scripts/little_loops/cli.py:139-159)
- The actual flag is `--priority` which filters by priority levels
- Config setting `parallel.p0_sequential: true` (default) means P0 issues are processed sequentially by default (config-schema.json:191-194)

## Desired End State

The README should document the correct approach:
- Remove the non-existent `--include-p0` flag
- Document that `--priority` can be used to filter which priorities to process
- Clarify that P0 issues are included by default but processed sequentially for safety

### How to Verify
- The line at 607 should show the correct `--priority` flag usage
- No references to `--include-p0` should remain in the documentation
- The comment should explain the P0 sequential processing behavior

## What We're NOT Doing

- Not implementing the `--include-p0` flag - the issue suggests fixing the docs, not adding the feature
- Not changing the default P0 sequential processing behavior
- Not modifying any code files - this is documentation only

## Problem Analysis

The documentation was written with an assumed flag that was never implemented. Users following the README will encounter argparse errors. The correct approach using `--priority` already exists but wasn't properly documented.

## Solution Approach

Replace line 607 with accurate documentation showing how to include P0 in processing using the existing `--priority` flag, with a clarifying comment about the sequential processing behavior.

## Implementation Phases

### Phase 1: Fix README Documentation

#### Overview
Replace the incorrect flag documentation with the correct approach.

#### Changes Required

**File**: `README.md`
**Line**: 607
**Changes**: Replace the incorrect `--include-p0` example with correct `--priority` usage

```markdown
ll-parallel --priority P0,P1,P2      # Process P0, P1, and P2 (P0 processed sequentially by default)
```

#### Success Criteria

**Automated Verification**:
- [ ] Grep confirms `--include-p0` is removed from README.md
- [ ] Grep confirms the corrected line exists at the appropriate location
- [ ] No other references to `include-p0` remain in the codebase

**Manual Verification**:
- [ ] The corrected line clearly explains how to include P0 issues
- [ ] The comment clarifies that P0 is processed sequentially by default

## Testing Strategy

### Verification Steps
- Search README for any remaining `--include-p0` references
- Verify the new line is present and correctly formatted
- Confirm alignment with actual CLI implementation

## References

- Original issue: `.issues/bugs/P2-BUG-318-incorrect-cli-flag-include-p0-documented.md`
- CLI implementation: `scripts/little_loops/cli.py:156-159`
- Config schema: `config-schema.json:191-194`
