---
discovered_commit: 0c243a9
discovered_branch: main
discovered_date: 2026-01-06T00:00:00Z
discovered_by: audit_docs
doc_file: CONTRIBUTING.md
---

# BUG-005: Missing files in documentation structure diagrams

## Summary

Multiple project structure diagrams are missing files from the parallel directory and Python package listings.

## Location

- **Files**: CONTRIBUTING.md, scripts/README.md
- **Lines**: CONTRIBUTING.md:97-103, scripts/README.md:407-414

## Missing Files

Two files exist but are not listed in structure diagrams:

1. `scripts/little_loops/parallel/git_lock.py` - Git locking utilities (missing from CONTRIBUTING.md and scripts/README.md; already present in docs/ARCHITECTURE.md:116)
2. `scripts/little_loops/issue_discovery.py` - Issue discovery module (missing from all documentation)

## Current Content (CONTRIBUTING.md example)

```markdown
└── parallel/     # Parallel processing module
    ├── orchestrator.py
    ├── worker_pool.py
    ├── merge_coordinator.py
    ├── priority_queue.py
    ├── output_parsing.py
    └── types.py
```

## Expected Content

```markdown
└── parallel/     # Parallel processing module
    ├── orchestrator.py
    ├── worker_pool.py
    ├── merge_coordinator.py
    ├── priority_queue.py
    ├── output_parsing.py
    ├── git_lock.py
    └── types.py
```

And add `issue_discovery.py` to the main package listing in all affected files.

## Impact

- **Severity**: Low (incomplete documentation)
- **Effort**: Small (update 2 files)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P2

## Verification Notes

**Verified**: 2026-01-06

- docs/ARCHITECTURE.md already includes `git_lock.py` at line 116 - removed from scope
- CONTRIBUTING.md and scripts/README.md still missing `git_lock.py` - confirmed
- `issue_discovery.py` missing from all three documentation files - confirmed
- Updated line references for scripts/README.md (was 380-412, now 410-414)

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-06
- **Status**: Completed

### Changes Made
- CONTRIBUTING.md: Added `git_lock.py` to parallel/ section, added `issue_discovery.py` to main package section
- scripts/README.md: Added `git_lock.py` to parallel/ section, added `issue_discovery.py` to main package section
- docs/ARCHITECTURE.md: Added `issue_discovery.py` to main package section (git_lock.py already present)
- docs/API.md: Added `issue_discovery` module to module table

### Verification Results
- All four documentation files now contain `git_lock.py` in parallel/ section
- All four documentation files now contain `issue_discovery.py` in main package section
