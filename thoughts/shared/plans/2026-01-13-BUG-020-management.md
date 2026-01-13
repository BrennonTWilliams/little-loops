# BUG-020: Outdated agent count and missing Python modules in documentation - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-020-outdated-counts-missing-modules-in-docs.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

Documentation across README.md, ARCHITECTURE.md, and CONTRIBUTING.md shows outdated counts and listings.

### Key Discoveries
- 8 agents exist in `agents/` directory (not 7 as documented)
- Missing agent: `workflow-pattern-analyzer.md`
- Missing Python modules: `logo.py`, `dependency_graph.py`, `user_messages.py`

## Desired End State

All documentation files accurately reflect the current state of:
- Agent count: 8
- All 8 agents listed where applicable
- All Python modules listed in directory structures

### How to Verify
- Grep for "7 specialized agents" should return 0 results
- All 8 agents appear in agent listings/tables
- Python module listings include all actual modules

## What We're NOT Doing

- Not changing any functionality - documentation only
- Not restructuring documentation files
- Not updating other numbers that are accurate (e.g., 20 commands)

## Solution Approach

Simple text updates across three files. Each change is independent and low-risk.

## Implementation Phases

### Phase 1: Update README.md

#### Overview
Fix agent count in overview, plugin structure comment, and add missing agent to table.

#### Changes Required

**File**: `README.md`

**Change 1**: Line 14 - Overview count
```markdown
# Before
- **7 specialized agents** for codebase analysis

# After
- **8 specialized agents** for codebase analysis
```

**Change 2**: Line 483 - Plugin structure comment
```markdown
# Before
├── agents/               # Agent definitions (7 agents)

# After
├── agents/               # Agent definitions (8 agents)
```

**Change 3**: Lines 294-301 - Agents table, add missing row after web-search-researcher
```markdown
# Add this row to the table
| `workflow-pattern-analyzer` | Analyze workflow patterns and dependencies |
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "7 specialized agents" README.md` returns 0
- [ ] `grep -c "workflow-pattern-analyzer" README.md` returns 1

---

### Phase 2: Update docs/ARCHITECTURE.md

#### Overview
Fix Mermaid diagram count, agents directory comment, add missing agent to list, and add missing Python modules.

#### Changes Required

**File**: `docs/ARCHITECTURE.md`

**Change 1**: Line 25 - Mermaid diagram
```markdown
# Before
        AGT[Agents<br/>7 specialized agents]

# After
        AGT[Agents<br/>8 specialized agents]
```

**Change 2**: Line 72 - Directory structure comment
```markdown
# Before
├── agents/                  # 7 specialized agents

# After
├── agents/                  # 8 specialized agents
```

**Change 3**: Lines 73-79 - Add missing agent after web-search-researcher.md
```markdown
│   ├── web-search-researcher.md
│   └── workflow-pattern-analyzer.md
```
(Change web-search-researcher.md from `└──` to `├──`)

**Change 4**: Lines 96-108 - Add missing Python modules (after subprocess_utils.py)
```markdown
        ├── subprocess_utils.py  # Subprocess handling
        ├── logo.py              # CLI logo display
        ├── dependency_graph.py  # Dependency graph construction
        ├── user_messages.py     # User message extraction
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "7 specialized agents" docs/ARCHITECTURE.md` returns 0
- [ ] `grep -c "workflow-pattern-analyzer.md" docs/ARCHITECTURE.md` returns 1
- [ ] `grep -c "logo.py" docs/ARCHITECTURE.md` returns 1
- [ ] `grep -c "dependency_graph.py" docs/ARCHITECTURE.md` returns 1
- [ ] `grep -c "user_messages.py" docs/ARCHITECTURE.md` returns 1

---

### Phase 3: Update CONTRIBUTING.md

#### Overview
Update project structure to match ARCHITECTURE.md changes.

#### Changes Required

**File**: `CONTRIBUTING.md`

**Change 1**: Line 76 - Add agents comment count (currently no count shown)
```markdown
# Before
├── agents/               # Agent definitions (*.md)

# After
├── agents/               # 8 agent definitions (*.md)
```

**Change 2**: Lines 86-98 - Add missing Python modules after logger.py
```markdown
        ├── logger.py
        ├── logo.py              # CLI logo display
        ├── dependency_graph.py  # Dependency graph construction
        ├── user_messages.py     # User message extraction
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "logo.py" CONTRIBUTING.md` returns 1
- [ ] `grep -c "dependency_graph.py" CONTRIBUTING.md` returns 1
- [ ] `grep -c "user_messages.py" CONTRIBUTING.md` returns 1

---

## Testing Strategy

### Verification Commands
```bash
# Verify no "7 specialized agents" remains
grep -r "7 specialized agents" README.md docs/ARCHITECTURE.md

# Verify workflow-pattern-analyzer appears in all agent listings
grep -c "workflow-pattern-analyzer" README.md docs/ARCHITECTURE.md

# Verify missing modules are added
grep "logo.py\|dependency_graph.py\|user_messages.py" docs/ARCHITECTURE.md CONTRIBUTING.md
```

## References

- Original issue: `.issues/bugs/P2-BUG-020-outdated-counts-missing-modules-in-docs.md`
- Agent files: `agents/*.md` (8 files confirmed)
- Python modules: `scripts/little_loops/*.py` (15 files confirmed)
