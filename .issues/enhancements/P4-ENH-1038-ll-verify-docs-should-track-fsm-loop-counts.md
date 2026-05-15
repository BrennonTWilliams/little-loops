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

## Verification Notes

**Verdict**: VALID — Verified 2026-04-11; re-verified 2026-05-14

- `doc_counts.py:19-23` — `COUNT_TARGETS` confirmed: only `commands`, `agents`, `skills` keys; no `loops` key
- Feature not yet implemented
- **Loop count (2026-05-14)**: `scripts/little_loops/loops/*.yaml` (top-level only) = **42** files. README claims 47 — drift of 5. Continues to grow without `ll-verify-docs` tracking.

## Blocks

- ENH-977

## Status

**Open** | Created: 2026-04-11 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-05-14T20:42:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-977 (add `ll-verify-skills`) both modify `scripts/little_loops/doc_counts.py` and `scripts/little_loops/cli/docs.py`. Changes are additive in different sections (ENH-1038 adds to `COUNT_TARGETS`; ENH-977 adds `check_skill_sizes()` and `main_verify_skills()`), but they should be sequenced or merged to avoid conflicts in the same PR. Related: ENH-977.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): Both ENH-1038 and ENH-977 add new logic to `scripts/little_loops/doc_counts.py` without referencing each other. ENH-1038 adds a `loops` key to `COUNT_TARGETS` and extends `extract_count_from_line`; ENH-977 adds `check_skill_sizes()` to the same module. Implement ENH-1038 after ENH-977 lands (or coordinate PR order) to avoid merge conflicts in `doc_counts.py`. Cross-reference ENH-977 in the PR description when landing this change.
