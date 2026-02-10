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

## Proposed Fix

Update the three default values in the README configuration tables to match the schema.

## Impact

- **Severity**: High (actively misleading defaults)
- **Effort**: Small (3 line changes)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2
