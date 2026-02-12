---
discovered_commit: 19510b2
discovered_branch: main
discovered_date: 2026-02-12T00:00:00Z
discovered_by: audit_docs
doc_file: CONTRIBUTING.md
---

# BUG-382: CONTRIBUTING.md directory trees outdated (skills, loops, docs)

## Summary

CONTRIBUTING.md project structure tree has three outdated sections: skills directory (shows 6, says 7, actually 8), loops directory (shows 5, actually 8), and docs directory (missing 3 files and 2 subdirectories).

## Location

- **File**: `CONTRIBUTING.md`
- **Line(s)**: 124-150
- **Section**: "Project Structure"

## Current Behavior

### Skills (line 130-136)

Comment says "7 skill definitions" but there are 8. Tree listing only shows 6 directories, missing:
- `confidence-check/` (pre-implementation confidence check)
- `loop-suggester/` (suggest FSM loops from message history)

### Loops (lines 124-129)

Shows 5 YAML files but there are 8. Missing:
- `sprint-execution.yaml`
- `workflow-analysis.yaml`
- `history-reporting.yaml`

### Docs (lines 138-150)

Missing from tree:
- `CONFIGURATION.md`
- `ISSUE_TEMPLATE.md`
- `MERGE-COORDINATOR.md`
- `claude-code/` subdirectory
- `demo/` subdirectory
- `research/` subdirectory

## Steps to Reproduce

1. Open `CONTRIBUTING.md` and navigate to the "Project Structure" section (lines 124-150)
2. Compare the skills/ tree listing with actual `skills/` directory contents
3. Compare the loops/ tree listing with actual `loops/*.yaml` files
4. Compare the docs/ tree listing with actual `docs/` directory contents
5. Observe: multiple entries are missing from all three sections

## Actual Behavior

- Skills comment says "7 skill definitions" but there are 8; tree shows only 6 of 8 directories
- Loops tree shows 5 of 8 YAML files
- Docs tree is missing 3 files (`CONFIGURATION.md`, `ISSUE_TEMPLATE.md`, `MERGE-COORDINATOR.md`) and 3 subdirectories (`claude-code/`, `demo/`, `research/`)

## Expected Behavior

Update skills comment to "8 skill definitions" and add missing directories. Add 3 missing loop files. Add missing docs files and subdirectories.

## Proposed Solution

Edit `CONTRIBUTING.md` Project Structure section:
1. Update skills comment from "7 skill definitions" to "8 skill definitions" and add `confidence-check/` and `loop-suggester/` to the tree
2. Add `sprint-execution.yaml`, `workflow-analysis.yaml`, and `history-reporting.yaml` to the loops tree
3. Add `CONFIGURATION.md`, `ISSUE_TEMPLATE.md`, `MERGE-COORDINATOR.md`, `claude-code/`, `demo/`, and `research/` to the docs tree

## Impact

- **Severity**: Medium (misleads contributors about project structure)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

## Session Log
- `/ll:manage_issue` - 2026-02-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ddf6ceda-e0cf-4b1c-b02f-513a1596f75c.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `CONTRIBUTING.md`: Updated loops tree from 5 to 8 YAML files (added history-reporting.yaml, sprint-execution.yaml, workflow-analysis.yaml)
- `CONTRIBUTING.md`: Updated skills comment from "7" to "8" and added confidence-check/ and loop-suggester/ directories
- `CONTRIBUTING.md`: Added 3 missing docs files (CONFIGURATION.md, ISSUE_TEMPLATE.md, MERGE-COORDINATOR.md) and 3 subdirectories (claude-code/, demo/, research/)

### Verification Results
- Tests: PASS (2695 passed)
- Lint: PASS
- Types: SKIP
- Run: SKIP
- Integration: PASS

---

## Status

**Completed** | Created: 2026-02-12 | Priority: P2
