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
- **Line(s)**: 166-168 (at scan commit: 925b8ce)
- **Anchor**: Project Structure tree section
- **Section**: Project Structure

## Current Behavior

CONTRIBUTING.md shows `cli.py` as a single file:

```
├── cli.py        # CLI entry points (ll-auto, ll-parallel, ll-messages,
│                 #   ll-loop, ll-sprint, ll-sync, ll-history,
│                 #   ll-verify-docs, ll-check-links)
```

## Expected Behavior

CONTRIBUTING.md should reflect the actual `cli/` package structure:

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

## Steps to Reproduce

1. Open `CONTRIBUTING.md` and navigate to the "Project Structure" section (line 166)
2. Compare the `cli.py` entry with the actual directory at `scripts/little_loops/cli/`
3. Observe: documentation shows a single file `cli.py` but the actual structure is a `cli/` package with 11 modules

## Actual Behavior

The Project Structure tree in CONTRIBUTING.md is outdated — it still references `cli.py` as a single file, which was split into a `cli/` package directory by ENH-344 on 2026-02-11.

## Impact

- **Priority**: P3 - Documentation inaccuracy that misleads contributors but does not block development
- **Effort**: Small - Single file edit to update the tree structure
- **Risk**: Low - Documentation-only change with no code impact

## Labels

`bug`, `documentation`, `auto-generated`

## Session Log
- `/ll:manage_issue` - 2026-02-13T06:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f19a9876-85ae-4986-a578-ae352431c67e.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `CONTRIBUTING.md`: Replaced outdated `cli.py` single-file entry (lines 166-168) with `cli/` package directory tree listing all 10 modules, following existing sub-package formatting conventions

### Verification Results
- Tests: PASS (2728 passed)
- Lint: PASS

---

## Status

**Completed** | Created: 2026-02-13 | Completed: 2026-02-13 | Priority: P3
