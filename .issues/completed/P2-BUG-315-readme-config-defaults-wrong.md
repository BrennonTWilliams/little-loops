---
discovered_commit: 2347db3
discovered_branch: main
discovered_date: 2026-02-10T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-315: Config defaults wrong for 3 parallel/scan settings in README

## Summary

Documentation issue found by `/ll:audit_docs`. Three configuration default values in README.md do not match the actual defaults in `config-schema.json` and source code.

## Current Behavior

The README configuration tables show incorrect default values for three settings:
- `parallel.timeout_per_issue`: documented as `7200` (actual: `3600`)
- `parallel.worktree_copy_files`: documented as `[".claude/settings.local.json", ".env"]` (actual: `[".env"]`; `.claude/` is always copied automatically)
- `scan.focus_dirs`: documented as `["src/"]` (actual: `["src/", "tests/"]`)

## Expected Behavior

The README configuration tables should show default values matching `config-schema.json`: `3600`, `[".env"]`, and `["src/", "tests/"]` respectively.

## Steps to Reproduce

1. Open `README.md` and navigate to the configuration tables (lines 283, 289, 310)
2. Compare the documented defaults against `config-schema.json` definitions
3. Observe three mismatches

## Actual Behavior

README documents incorrect defaults that contradict the schema and runtime behavior, potentially misleading users about expected configuration values.

## Location

- **File**: `README.md`
- **Lines**: 283, 289, 310

## Discrepancies

### 1. `parallel.timeout_per_issue` (line 283)

- **README says**: `7200`
- **Schema says**: `3600`
- **Code confirms**: `3600` (config-schema.json:206-210)
- **Impact**: Users relying on the documented default get half the expected timeout

### 2. `parallel.worktree_copy_files` (line 289)

- **README says**: `[".claude/settings.local.json", ".env"]`
- **Schema says**: `[".env"]` with note: ".claude/ directory is always copied automatically"
- **Impact**: Misleading; users may add redundant `.claude/settings.local.json` entries

### 3. `scan.focus_dirs` (line 310)

- **README table says**: `["src/"]`
- **Schema says**: `["src/", "tests/"]`
- **Code confirms**: `["src/", "tests/"]` (config.py:272)
- **Note**: The full config example on README line 176 correctly shows both

## Proposed Solution

Update the three default values in the README configuration tables to match the schema.

## Impact

- **Severity**: High (actively misleading defaults)
- **Effort**: Small (3 line changes)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `README.md:283`: Fixed `parallel.timeout_per_issue` default from `7200` to `3600`
- `README.md:289`: Fixed `parallel.worktree_copy_files` default from `[".claude/settings.local.json", ".env"]` to `[".env"]` with note about automatic .claude/ copy
- `README.md:310`: Fixed `scan.focus_dirs` default from `["src/"]` to `["src/", "tests/"]`

### Verification Results
- Tests: PASS (2674 passed)
- Lint: PASS (pre-existing issues only, no new)
- Types: N/A (docs-only change)
- Integration: PASS
