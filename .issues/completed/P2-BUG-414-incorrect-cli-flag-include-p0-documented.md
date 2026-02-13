---
discovered_commit: a4db94ec6b2722ca97c5248450880c4528b1294d
discovered_branch: main
discovered_date: 2026-02-10T15:30:00-08:00
discovered_by: audit_docs
doc_file: README.md
---

# BUG-414: Incorrect CLI flag `--include-p0` documented in README

## Summary

Documentation issue found by `/ll:audit_docs`. The README documents a CLI flag `--include-p0` for ll-parallel that doesn't exist in the actual implementation.

## Steps to Reproduce

1. Attempt to run `ll-parallel --include-p0` as documented in README.md line 607
2. Observe the error: `unrecognized arguments: --include-p0`

## Current Behavior

The README.md documents `--include-p0` as a valid flag, but the ll-parallel argument parser does not recognize this flag, causing an error when users try to use it.

## Expected Behavior

Either:
- The flag should be removed from documentation (if the feature doesn't exist), OR
- The correct approach should be documented (using `--priority P0,P1,P2` to include P0 issues)

## Actual Behavior

Running `ll-parallel --include-p0` produces an "unrecognized arguments" error from argparse because the flag is not implemented in scripts/little_loops/cli.py.

## Location

- **File**: `README.md`
- **Line(s)**: 607
- **Section**: CLI Tools > ll-parallel

## Current Content

```bash
ll-parallel --include-p0             # Include P0 in parallel processing
```

## Problem

The `--include-p0` flag is not defined in the ll-parallel argument parser. Users who try to use this command will receive an "unrecognized arguments" error from argparse.

**Verification**:
- Searched `scripts/little_loops/cli.py` for `--include-p0` flag definition
- Searched entire codebase for any reference to `include-p0` or `include_p0`
- No such flag exists in the implementation

## Expected Content

**Option A: Remove the line** (if feature doesn't exist):
```bash
# Remove the line entirely
```

**Option B: Document the correct approach** (recommended):
```bash
ll-parallel --priority P0,P1,P2      # Process P0, P1, and P2 issues (P0 processed sequentially by default)
```

## Context

Based on `config-schema.json`, the configuration setting `parallel.p0_sequential: true` (default) means P0 issues are automatically processed sequentially for safety. The `--priority` flag can filter which priorities to process, but there's no special flag needed to "include" P0 - it's included by default unless filtered out.

## Impact

- **Severity**: Medium (causes user confusion and command errors)
- **Effort**: Small (simple documentation fix)
- **Risk**: Low (documentation-only change)

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- README.md:607: Replaced non-existent `--include-p0` flag with correct `--priority P0,P1,P2` documentation and clarifying comment about P0 sequential processing

### Verification Results
- Documentation fix verified: Incorrect flag removed from README.md
- No other references to `--include-p0` found in codebase
- Corrected line documents actual `--priority` flag behavior
