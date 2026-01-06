---
discovered_commit: 0c243a9
discovered_branch: main
discovered_date: 2026-01-06T00:00:00Z
discovered_by: audit_docs
doc_file: CONTRIBUTING.md
---

# BUG-005: Missing git_lock.py in CONTRIBUTING.md structure diagram

## Summary

The project structure diagram in CONTRIBUTING.md is missing `git_lock.py` from the parallel directory listing.

## Location

- **File**: CONTRIBUTING.md
- **Lines**: 97-103

## Current Content

```markdown
└── parallel/     # Parallel processing module
    ├── orchestrator.py
    ├── worker_pool.py
    ├── merge_coordinator.py
    ├── priority_queue.py
    ├── output_parsing.py
    └── types.py
```

## Problem

The file `scripts/little_loops/parallel/git_lock.py` exists but is not listed in the structure diagram.

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

## Impact

- **Severity**: Low (incomplete documentation)
- **Effort**: Trivial (add one line)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P2
