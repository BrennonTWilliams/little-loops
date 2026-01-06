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

- **Files**: CONTRIBUTING.md, scripts/README.md, docs/ARCHITECTURE.md
- **Lines**: CONTRIBUTING.md:97-103, scripts/README.md:380-412, docs/ARCHITECTURE.md:59-121

## Missing Files

Two files exist but are not listed in structure diagrams:

1. `scripts/little_loops/parallel/git_lock.py` - Git locking utilities
2. `scripts/little_loops/issue_discovery.py` - Issue discovery module

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
- **Effort**: Small (update 3 files)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P2
