---
discovered_commit: d937f40dbf3820b04ecaf70118377b89406be25a
discovered_branch: main
discovered_date: 2026-01-13T00:00:00Z
discovered_by: audit_docs
doc_file: README.md, docs/ARCHITECTURE.md, CONTRIBUTING.md
---

# BUG-020: Outdated agent count and missing Python modules in documentation

## Summary

Documentation audit found several inaccuracies across README.md, ARCHITECTURE.md, and CONTRIBUTING.md regarding agent counts and Python module listings.

## Locations

### Issue 1: Agent Count
- **File**: `README.md`
- **Line**: 14
- **Section**: Overview

**Current Content**:
```markdown
- **7 specialized agents** for codebase analysis
```

**Problem**: There are 8 agents in `agents/`. The `workflow-pattern-analyzer.md` agent is not counted.

**Expected Content**:
```markdown
- **8 specialized agents** for codebase analysis
```

### Issue 2: Directory Structure Missing Modules
- **File**: `docs/ARCHITECTURE.md`
- **Lines**: 95-108
- **Section**: Directory Structure

**Problem**: The `scripts/little_loops/` listing is missing:
- `logo.py` - CLI logo display
- `dependency_graph.py` - Dependency parsing and graph construction
- `user_messages.py` - User message extraction from Claude logs

### Issue 3: Agents Listing
- **File**: `docs/ARCHITECTURE.md`
- **Lines**: 72-79
- **Section**: Directory Structure (agents)

**Problem**: Shows 7 agents but `workflow-pattern-analyzer.md` is missing from the listing.

### Issue 4: CONTRIBUTING.md Structure
- **File**: `CONTRIBUTING.md`
- **Lines**: 69-106
- **Section**: Project Structure

**Problem**: Same missing modules and agents as ARCHITECTURE.md.

## Impact

- **Severity**: Medium (misleading but not blocking)
- **Effort**: Small (simple text updates)
- **Risk**: Low

## Proposed Fix

1. Update README.md line 14: "7" → "8"
2. Update docs/ARCHITECTURE.md:
   - Add missing Python modules to directory structure
   - Add `workflow-pattern-analyzer.md` to agents listing
3. Update CONTRIBUTING.md project structure to match

### Issue 5: Mermaid Diagram Agent Count
- **File**: `docs/ARCHITECTURE.md`
- **Lines**: 24-25
- **Section**: High-Level Architecture (Mermaid diagram)

**Current Content**:
```mermaid
AGT[Agents<br/>7 specialized agents]
```

**Problem**: Mermaid diagram shows "7 specialized agents" instead of 8.

**Expected Content**:
```mermaid
AGT[Agents<br/>8 specialized agents]
```

### Issue 6: README Agents Table
- **File**: `README.md`
- **Lines**: 291-301
- **Section**: Agents table

**Problem**: Agents table lists 7 agents, missing `workflow-pattern-analyzer`.

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-01-13 | Priority: P2

---

## Audit Update

- **Date**: 2026-01-13
- **By**: audit_docs (second pass)

### Additional Findings

A comprehensive documentation audit verified:

1. **Code examples**: All Python examples in API.md run correctly
2. **Links**: All markdown links resolve to valid targets
3. **File paths**: All referenced paths exist
4. **Command count**: 20 commands is accurate

The existing issues in this file cover all documentation inaccuracies found. Two additional locations were identified:
- Mermaid diagram in ARCHITECTURE.md (Issue 5)
- README agents table (Issue 6)

### Verification Checklist

Files to update when fixing:
- [x] README.md line 14: "7" → "8"
- [x] README.md agents table: add `workflow-pattern-analyzer`
- [x] docs/ARCHITECTURE.md Mermaid diagram: "7" → "8"
- [x] docs/ARCHITECTURE.md agents listing: add `workflow-pattern-analyzer.md`
- [x] docs/ARCHITECTURE.md Python modules: add `logo.py`, `dependency_graph.py`, `user_messages.py`
- [x] CONTRIBUTING.md project structure: sync with ARCHITECTURE.md

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-13
- **Status**: Completed

### Changes Made
- `README.md`: Updated agent count from 7 to 8 in overview and plugin structure, added `workflow-pattern-analyzer` to agents table
- `docs/ARCHITECTURE.md`: Updated Mermaid diagram count, agent listing count, added `workflow-pattern-analyzer.md`, added missing Python modules (`logo.py`, `dependency_graph.py`, `user_messages.py`)
- `CONTRIBUTING.md`: Updated agent count in project structure, added missing Python modules

### Verification Results
- Tests: N/A (documentation only)
- Lint: PASS
- Types: PASS
