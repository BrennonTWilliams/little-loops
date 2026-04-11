---
discovered_commit: 958a2a63
discovered_branch: main
discovered_date: 2026-04-11T00:00:00Z
discovered_by: audit-docs
doc_file: scripts/little_loops/doc_counts.py
---

# ENH-1038: ll-verify-docs should track FSM loop counts

## Summary

Documentation count found by `/ll:audit-docs`. `ll-verify-docs` (via `doc_counts.py`) only tracks commands, agents, and skills counts. FSM loop counts documented in README.md went stale (37 documented vs 38 actual) and were not caught by `ll-verify-docs`.

## Location

- **File**: `scripts/little_loops/doc_counts.py`
- **Section**: `COUNT_TARGETS` dict

## Current Content

```python
COUNT_TARGETS = {
    "commands": ("commands", "*.md"),
    "agents": ("agents", "*.md"),
    "skills": ("skills", "SKILL.md"),
}
```

## Problem

FSM loop count (documented in README.md as "37 FSM loops") is not tracked by `ll-verify-docs`. A new loop was added without updating the README count, and the mismatch went undetected until a manual audit.

## Expected Content

Add a loop count target to `COUNT_TARGETS` pointing at the top-level YAML files in `scripts/little_loops/loops/` (excluding `lib/` subdirectory, `oracles/` subdirectory, and `README.md`):

```python
COUNT_TARGETS = {
    "commands": ("commands", "*.md"),
    "agents": ("agents", "*.md"),
    "skills": ("skills", "SKILL.md"),
    "loops": ("scripts/little_loops/loops", "*.yaml"),  # top-level only, not recursive
}
```

The README pattern to match would be `\d+\s+FSM loops?`. The `extract_count_from_line` function may need updating to handle the "FSM loops" phrasing since "loops" is not already a tracked category.

## Impact

- **Severity**: Low (count drift, not functional breakage)
- **Effort**: Small (add entry to COUNT_TARGETS, update regex matching)
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `ll-verify-docs`, `auto-generated`

---

## Status

**Open** | Created: 2026-04-11 | Priority: P4
