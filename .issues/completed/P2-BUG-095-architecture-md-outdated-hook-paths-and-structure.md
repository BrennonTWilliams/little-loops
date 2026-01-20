---
discovered_commit: 611d073
discovered_branch: main
discovered_date: 2026-01-20T00:00:00Z
discovered_by: audit_docs
doc_file: docs/ARCHITECTURE.md
---

# BUG-095: ARCHITECTURE.md outdated hook paths and module structure

## Summary

Documentation issue found by `/ll:audit_docs`. The `docs/ARCHITECTURE.md` file has incorrect hook paths and outdated Python module listings that don't match the current codebase.

## Location

- **File**: `docs/ARCHITECTURE.md`
- **Line(s)**: 81-85, 96-128
- **Section**: Directory Structure

## Problems

### 1. Incorrect Hook Script Path (Line 83)

**Current Content:**
```
├── hooks/
│   ├── hooks.json
│   ├── check-duplicate-issue-id.sh  # Validation script
│   └── prompts/
│       └── continuation-prompt-template.md
```

**Problem:** Shows `check-duplicate-issue-id.sh` at hooks root level, but it was moved to `hooks/scripts/` in ENH-087. The actual structure is:

```
├── hooks/
│   ├── hooks.json
│   ├── prompts/
│   │   └── continuation-prompt-template.md
│   └── scripts/
│       ├── check-duplicate-issue-id.sh
│       ├── context-monitor.sh
│       ├── precompact-state.sh
│       ├── session-cleanup.sh
│       ├── session-start.sh
│       └── user-prompt-check.sh
```

### 2. Missing Python Modules (Lines 96-128)

The `scripts/little_loops/` listing is missing several modules:
- `issue_discovery.py`
- `logo.py`
- `dependency_graph.py`
- `user_messages.py`
- `sprint.py`
- Entire `fsm/` subpackage with:
  - `schema.py`
  - `compilers.py`
  - `evaluators.py`
  - `executor.py`
  - `interpolation.py`
  - `validation.py`
  - `persistence.py`
  - `signal_detector.py`
  - `handoff_handler.py`

## Impact

- **Severity**: Medium (misleading documentation, affects developer onboarding)
- **Effort**: Small
- **Risk**: Low

## Fix Required

Update the Directory Structure section to accurately reflect:
1. Hook scripts directory structure with all scripts in `scripts/` subdirectory
2. Complete Python module listing including `fsm/` subpackage

## Verification

```bash
# Verify hooks structure
ls -la hooks/scripts/
# Should show: check-duplicate-issue-id.sh, context-monitor.sh, etc.

# Verify fsm modules exist
ls scripts/little_loops/fsm/*.py
# Should show all FSM modules
```

## Related Issues

- ENH-087 (completed): Moved hook script to scripts/ subdirectory (but docs not updated)
- BUG-083 (reopened): Command count issues in same file

## Labels

`bug`, `documentation`, `auto-generated`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-20
- **Status**: Completed

### Changes Made
- `docs/ARCHITECTURE.md`: Updated hooks/ section to show correct `scripts/` subdirectory with all 6 hook scripts
- `docs/ARCHITECTURE.md`: Added `sprint.py` module to Python package listing
- `docs/ARCHITECTURE.md`: Added complete `fsm/` subpackage with 10 modules (schema.py, compilers.py, evaluators.py, executor.py, interpolation.py, validation.py, persistence.py, signal_detector.py, handoff_handler.py)

### Verification Results
- hooks/scripts/ structure: VERIFIED (6 scripts present)
- fsm/ modules: VERIFIED (10 Python files present)
- Tests: PASS

---

## Status

**Completed** | Created: 2026-01-20 | Completed: 2026-01-20 | Priority: P2
