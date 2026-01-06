---
discovered_commit: 861b670
discovered_branch: main
discovered_date: 2026-01-06T00:00:00Z
discovered_by: audit_docs
doc_file: scripts/README.md
---

# BUG-006: Incorrect test path in scripts/README.md

## Summary

The Contributing section in scripts/README.md has an incorrect path for running tests.

## Location

- **File**: scripts/README.md
- **Line**: 419

## Current Content

```markdown
4. Run tests: `pytest little-loops/scripts/tests/`
```

## Problem

The path `little-loops/scripts/tests/` is incorrect. When working from the repository root, the correct path is `scripts/tests/`. The `little-loops/` prefix assumes you're in a parent directory.

## Expected Content

```markdown
4. Run tests: `pytest scripts/tests/`
```

## Impact

- **Severity**: Low (confusing for contributors)
- **Effort**: Trivial (one line fix)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P3
