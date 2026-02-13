---
discovered_commit: 925b8ce
discovered_branch: main
discovered_date: 2026-02-13T00:00:00Z
discovered_by: audit_docs
doc_file: CONTRIBUTING.md
---

# BUG-406: CONTRIBUTING.md project tree shows `cli.py` but actual structure is `cli/` package

## Summary

CONTRIBUTING.md Project Structure section shows `cli.py` as a single file with a comment listing entry points, but the actual structure is a `cli/` package directory containing 11 modules (`__init__.py`, `auto.py`, `docs.py`, `history.py`, `loop.py`, `messages.py`, `next_id.py`, `parallel.py`, `sprint.py`, `sync.py`).

## Location

- **File**: `CONTRIBUTING.md`
- **Line(s)**: 166-168
- **Section**: Project Structure

## Current Content

```
├── cli.py        # CLI entry points (ll-auto, ll-parallel, ll-messages,
│                 #   ll-loop, ll-sprint, ll-sync, ll-history,
│                 #   ll-verify-docs, ll-check-links)
```

## Expected Content

```
├── cli/                  # CLI entry points
│   ├── __init__.py
│   ├── auto.py           # ll-auto
│   ├── docs.py           # ll-verify-docs, ll-check-links
│   ├── history.py        # ll-history
│   ├── loop.py           # ll-loop
│   ├── messages.py       # ll-messages
│   ├── next_id.py        # ll-next-id
│   ├── parallel.py       # ll-parallel
│   ├── sprint.py         # ll-sprint
│   └── sync.py           # ll-sync
```

## Impact

- **Severity**: Medium (misleads contributors about project structure)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-13 | Priority: P3
