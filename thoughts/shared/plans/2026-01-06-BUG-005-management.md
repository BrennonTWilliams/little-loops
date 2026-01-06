# BUG-005: Missing files in documentation structure diagrams - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-005-missing-git-lock-in-contributing-structure.md
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The issue reports that two Python files exist but are missing from documentation structure diagrams:

1. `scripts/little_loops/parallel/git_lock.py` - Thread-safe git operations
2. `scripts/little_loops/issue_discovery.py` - Issue discovery and deduplication

### Key Discoveries
- CONTRIBUTING.md:97-103 - parallel/ section missing `git_lock.py`, main package missing `issue_discovery.py`
- scripts/README.md:407-414 - parallel/ section missing `git_lock.py`, main package missing `issue_discovery.py`
- docs/ARCHITECTURE.md:116 - Already has `git_lock.py` (correct), but main package missing `issue_discovery.py`
- docs/API.md:18-30 - Module table missing `issue_discovery`

## Desired End State

All four documentation files have complete, accurate listings of Python modules:
- `git_lock.py` listed in parallel/ sections of all files
- `issue_discovery.py` listed in main package sections of all files

### How to Verify
- Each file contains `git_lock.py` in its parallel/ directory listing
- Each file contains `issue_discovery.py` in its main package listing
- File ordering follows existing alphabetical conventions

## What We're NOT Doing

- Not restructuring documentation files beyond adding missing entries
- Not updating any other documentation sections
- Not modifying Python source code

## Solution Approach

Add missing file entries to each documentation file following existing patterns:
- Maintain alphabetical ordering within each section
- Match existing comment/description style for each file
- Keep consistent formatting

## Implementation Phases

### Phase 1: Update CONTRIBUTING.md

#### Overview
Add `git_lock.py` to parallel/ section and `issue_discovery.py` to main package section.

#### Changes Required

**File**: `CONTRIBUTING.md`

**Change 1**: Add `issue_discovery.py` after `issue_parser.py` (line 91-92)
```markdown
        ├── issue_parser.py
        ├── issue_discovery.py  # Issue discovery and deduplication
        ├── issue_lifecycle.py
```

**Change 2**: Add `git_lock.py` to parallel/ section (line 102-103)
```markdown
            ├── output_parsing.py
            ├── git_lock.py
            └── types.py
```

#### Success Criteria

**Automated Verification**:
- [ ] File contains `git_lock.py` in parallel/ section
- [ ] File contains `issue_discovery.py` in main package section

---

### Phase 2: Update scripts/README.md

#### Overview
Add `git_lock.py` to parallel/ section and `issue_discovery.py` to main package section.

#### Changes Required

**File**: `scripts/README.md`

**Change 1**: Add `issue_discovery.py` after `issue_parser.py` (line 402-403)
```markdown
        ├── issue_parser.py       # Issue discovery and parsing
        ├── issue_discovery.py    # Issue discovery and deduplication
        ├── logger.py             # Logging utilities
```

**Change 2**: Add `git_lock.py` to parallel/ section (line 413-414)
```markdown
            ├── orchestrator.py       # Main orchestrator
            ├── git_lock.py           # Thread-safe git operations
            └── output_parsing.py     # Claude output parsing
```

#### Success Criteria

**Automated Verification**:
- [ ] File contains `git_lock.py` in parallel/ section
- [ ] File contains `issue_discovery.py` in main package section

---

### Phase 3: Update docs/ARCHITECTURE.md

#### Overview
Add `issue_discovery.py` to main package section. `git_lock.py` already present at line 116.

#### Changes Required

**File**: `docs/ARCHITECTURE.md`

**Change 1**: Add `issue_discovery.py` after `issue_parser.py` (line 104-105)
```markdown
        ├── issue_parser.py      # Issue file parsing
        ├── issue_discovery.py   # Issue discovery and deduplication
        ├── issue_lifecycle.py   # Issue lifecycle operations
```

#### Success Criteria

**Automated Verification**:
- [ ] File contains `issue_discovery.py` in main package section
- [ ] File still contains `git_lock.py` in parallel/ section (no regression)

---

### Phase 4: Update docs/API.md

#### Overview
Add `issue_discovery` module entry to the module table.

#### Changes Required

**File**: `docs/API.md`

**Change 1**: Add `issue_discovery` row after `issue_parser` (line 21-22)
```markdown
| `little_loops.issue_parser` | Issue file parsing |
| `little_loops.issue_discovery` | Issue discovery and deduplication |
| `little_loops.issue_manager` | Sequential automation |
```

#### Success Criteria

**Automated Verification**:
- [ ] File contains `little_loops.issue_discovery` in module table

---

## Testing Strategy

### Verification
- Grep each file for expected entries
- Visual inspection of structure diagrams for correct ordering

## References

- Original issue: `.issues/bugs/P2-BUG-005-missing-git-lock-in-contributing-structure.md`
- Correct pattern: `docs/ARCHITECTURE.md:116` (has git_lock.py)
