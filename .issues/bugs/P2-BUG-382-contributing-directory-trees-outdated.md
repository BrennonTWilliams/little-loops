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

## Problem

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

## Expected Content

Update skills comment to "8 skill definitions" and add missing directories. Add 3 missing loop files. Add missing docs files and subdirectories.

## Impact

- **Severity**: Medium (misleads contributors about project structure)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P2
