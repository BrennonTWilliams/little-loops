---
id: BUG-1600
type: BUG
priority: P3
status: open
title: "ll-verify-docs false positive: '0 skill descriptions dropped' matched as skill count"
created: 2026-05-17
relates_to: ENH-977
---

## Problem

`ll-verify-docs` reports a spurious mismatch:

```
skills: documented=0, actual=30
  at CONTRIBUTING.md:540
```

The line at CONTRIBUTING.md:540 reads:

```
Then run `/doctor` and verify "0 skill descriptions dropped".
```

The phrase `"0 skill descriptions dropped"` is quoting `/doctor` output, not documenting a skill count. However, the regex in `doc_counts.py` is too broad and matches it as a skills count.

## Root Cause

In `scripts/little_loops/doc_counts.py`, the skills pattern is:

```python
pattern = r"(\d+)\s+\w*\s*skills?"
```

This matches `0 skill` in `"0 skill descriptions dropped"` because:
- `(\d+)` = `0`
- `\s+` = ` `
- `\w*` = `` (zero chars)
- `\s*` = `` (zero chars)
- `skills?` = `skill`

## Fix

Narrow the pattern to avoid matching when followed by ` descriptions`. Options:

1. Add a negative lookahead: `r"(\d+)\s+\w*\s*skills?(?!\s+description)"`
2. Require the count to be followed by a word boundary and not `description(s)`: anchor the match more tightly.

Also add a test case to `scripts/tests/test_doc_counts.py` covering this edge case.

## Acceptance Criteria

- [ ] `ll-verify-docs` returns exit code 0 on the current codebase with no changes to CONTRIBUTING.md
- [ ] `"0 skill descriptions dropped"` no longer matches as a skills count in the regex
- [ ] New test covers this edge case in `test_doc_counts.py`

## Verification Notes

**Verdict**: VALID — Verified 2026-05-17

- `scripts/little_loops/doc_counts.py:108` — `pattern = r"(\d+)\s+\w*\s*skills?"` confirmed; tested against `"0 skill descriptions dropped"` → matches `"0 skill"` ✓
- `CONTRIBUTING.md:540` — contains the triggering text `verify "0 skill descriptions dropped"` ✓
- No fix applied; regex still too broad.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-17): ENH-977 also modifies `scripts/little_loops/doc_counts.py` (adds `check_skill_sizes()` function). Implement this bug fix (narrowing the skills regex at line 108) **before** ENH-977 to avoid a merge conflict on the same file. Alternatively, include this fix directly in ENH-977's PR.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-17T18:46:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ebf7abce-1ef1-46c8-8cbc-56d9f857d730.jsonl`
- `/ll:verify-issues` - 2026-05-17T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
