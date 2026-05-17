---
id: ENH-1551
type: enhancement
priority: P3
status: open
parent: ENH-1539
size: Small
---

# ENH-1551: Status one-shot cleanup pass for non-canonical values in .issues/

## Summary

Run a targeted rewrite of existing `.issues/**/*.md` files that contain non-canonical `status:` values (`completed`, `in`, `proven`, or any truncation), committing them as a single normalization pass and verifying the result with grep.

## Parent Issue

Decomposed from ENH-1539: Normalize status synonyms and document canonical enum

## Proposed Solution

### 1. Identify all non-canonical values

```bash
grep -rn "^status: " .issues/ | grep -v "status: open\|status: in_progress\|status: blocked\|status: deferred\|status: done\|status: cancelled" | sort
```

Expected output (~5-10 files at time of writing): `status: completed`, `status: proven`, and possibly truncations.

### 2. Rewrite script

Write a short Python script (or inline `sed`) that applies the same `STATUS_SYNONYMS` map to on-disk files:

```python
import re, pathlib

SYNONYMS = {
    "complete": "done", "completed": "done", "finished": "done", "closed": "done",
    "in-progress": "in_progress", "in progress": "in_progress", "wip": "in_progress",
    "proven": "done",  # one-off stray value found in snapshot
}

issues_root = pathlib.Path(".issues")
for f in issues_root.rglob("*.md"):
    text = f.read_text()
    updated = re.sub(
        r"^(status: )(\S+)$",
        lambda m: m.group(1) + SYNONYMS.get(m.group(2), m.group(2)),
        text,
        flags=re.MULTILINE,
    )
    if updated != text:
        f.write_text(updated)
        print(f"Normalized: {f}")
```

### 3. Run and commit

```bash
python scripts/normalize_status.py  # or inline
git add .issues/
git commit -m "chore(issues): normalize non-canonical status synonyms to canonical values"
```

Commit message should note: "one-shot rewrite; parser now normalizes on read so this won't recur".

### 4. Verify

```bash
grep -rn "^status: " .issues/ | grep -oE "status: [a-z_]+" | sort -u
```

Expected output (exactly these 6):
```
status: blocked
status: cancelled
status: deferred
status: done
status: in_progress
status: open
```

## Prerequisite

ENH-1549 should be merged first so the parser already normalizes on read and future files self-heal. This cleanup pass then brings the on-disk state into alignment with what parsers already see.

## Files to Modify

- `scripts/normalize_status.py` (temporary script — delete after running, or commit as a one-off migration tool)
- `N` files in `.issues/**/*.md` with non-canonical status values

## Acceptance Criteria

1. `grep -rn "^status: " .issues/` output contains only the 6 canonical values
2. No `status: completed`, `status: proven`, or truncations remain in `.issues/`
3. Single clean commit with descriptive message

## Impact

- **Effort**: Minimal — 1 script run + 1 commit
- **Risk**: Low — semantic no-op (value meaning is preserved)
- **Dependency**: ENH-1549 (core normalization) should precede this for on-disk self-healing going forward

## Session Log
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e994b5a7-bd67-4e1b-8e86-ff8daad14873.jsonl`
