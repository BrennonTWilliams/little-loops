---
discovered_commit: 68997ce18a454cb21ec487df508fed6fda5b3b68
discovered_branch: main
discovered_date: 2026-01-17T00:00:00Z
discovered_by: audit_docs
doc_file: CONTRIBUTING.md
---

# ENH-086: Add fsm subpackage to CONTRIBUTING.md project structure

## Summary

Documentation enhancement found by `/ll:audit_docs`. The project structure in CONTRIBUTING.md doesn't include the `fsm/` subpackage under `little_loops/`.

## Location

- **File**: `CONTRIBUTING.md`
- **Lines**: 71-110
- **Section**: Project Structure

## Current Content

```
└── scripts/              # Python CLI tools
    ├── pyproject.toml    # Package configuration
    ├── tests/            # Test suite
    └── little_loops/     # Main package
        ├── cli.py        # CLI entry points (ll-auto, ll-parallel, ll-messages, ll-loop)
        ├── config.py     # Configuration management
        ...
        └── parallel/     # Parallel processing module
```

## Expected Content

Add `fsm/` subpackage:

```
└── scripts/              # Python CLI tools
    ├── pyproject.toml    # Package configuration
    ├── tests/            # Test suite
    └── little_loops/     # Main package
        ├── cli.py        # CLI entry points
        ├── config.py     # Configuration management
        ...
        ├── fsm/          # FSM loop system
        │   ├── schema.py
        │   ├── compilers.py
        │   ├── evaluators.py
        │   ├── executor.py
        │   ├── interpolation.py
        │   ├── validation.py
        │   └── persistence.py
        └── parallel/     # Parallel processing module
```

## Impact

- **Severity**: Low (contributor guidance)
- **Effort**: Trivial
- **Risk**: None

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-17 | Priority: P4
