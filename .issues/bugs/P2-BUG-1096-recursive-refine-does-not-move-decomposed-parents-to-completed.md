---
discovered_date: 2026-04-13
discovered_by: capture-issue
---

# BUG-1096: recursive-refine does not move decomposed parents to completed

## Summary

In `recursive-refine.yaml`, when a parent issue is decomposed into child issues, the parent file is written to the skip list but never moved to `.issues/completed/`. This leaves decomposed parents as open issues. When the skip file is cleared on the next run (e.g., after fixing BUG-1095), those parents re-appear as active candidates and get re-decomposed.

## Current Behavior

After `recursive-refine` decomposes a parent issue into children:

1. Children are prepended to the queue (`enqueue_children`) or appended (`enqueue_or_skip`)
2. Parent ID is written to `.loops/tmp/recursive-refine-skipped.txt`
3. Parent issue file **remains in its active directory** (e.g., `.issues/features/`)
4. On the next run, with a fresh skip file, `ll-issues next-issue` returns the parent again
5. The parent gets re-refined and re-decomposed, creating duplicate child issues

## Expected Behavior

After decomposition, the parent issue file should be moved to `.issues/completed/` so that `ll-issues next-issue` never returns it again, regardless of skip file state.

## Root Cause

**File**: `scripts/little_loops/loops/recursive-refine.yaml`

Two states handle decomposition but neither moves the parent file:

- **`enqueue_children`** (line 183, skip-file write at line 193): handles decomposition detected by `detect_children`
  ```bash
  echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped.txt
  # Missing: mv parent file to completed/
  ```

- **`enqueue_or_skip`** (line 278, children-found branch at line 304, skip-file write at line 310): handles decomposition from explicit size-review
  ```bash
  echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped.txt
  # Missing: mv parent file to completed/
  ```

Note: The `else` branch of `enqueue_or_skip` (line 313, skip-file write at line 314 — no children found) should NOT move the parent, as the issue remains open for future retry.

## Proposed Solution

In both `enqueue_children` and the children-found branch of `enqueue_or_skip`, after writing to the skip list, find and move the parent file:

```bash
PARENT_ID="${captured.input.output}"
PARENT_FILE=$(find .issues -name "*-${PARENT_ID}-*" ! -path "*/completed/*" 2>/dev/null | head -1)
if [ -n "$PARENT_FILE" ]; then
  mkdir -p .issues/completed
  git mv "$PARENT_FILE" .issues/completed/ 2>/dev/null \
    || mv "$PARENT_FILE" .issues/completed/
fi
```

Note: `git mv` first so the move is tracked in git history; `mv` fallback handles untracked files. This mirrors `_move_issue_to_completed()` in `issue_lifecycle.py:327-353`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml`
  - `enqueue_children` state (line 183): add `find + mv` block after line 193 (skip-list write)
  - `enqueue_or_skip` state (line 278): add `find + mv` block after line 310, inside the `if [ -s .loops/tmp/recursive-refine-new-children.txt ]` branch (line 304) only — the `else` branch (line 313) must not move the file

### Similar Patterns (Reference)
- `scripts/little_loops/loops/recursive-refine.yaml:296-297` — existing `find .issues -name "*-$child_id-*" ! -path "*/completed/*"` pattern already used in `enqueue_or_skip` for child-file lookup; the parent-file `find` should use the identical glob with `"*-${PARENT_ID}-*"`
- `ll-issues` has no `complete` or `close` subcommand — shell `find + mv` is the only mechanism available in YAML loops
- `scripts/little_loops/issue_lifecycle.py:294` — `_move_issue_to_completed()` is the Python equivalent but is not callable from shell

### Dependent Issues
- BUG-1095 (`auto-refine-and-implement` exits immediately) — this fix is a prerequisite: without it, cleared skip files cause re-decomposition of parents that should be completed

### Tests
- `scripts/tests/test_builtin_loops.py:959` — `TestRecursiveRefineLoop` class; add new test methods:
  - `test_enqueue_children_moves_parent_to_completed`: assert `enqueue_children` action contains `find .issues` and `mv` targeting `completed/`
  - `test_enqueue_or_skip_moves_parent_to_completed_when_children_found`: assert the `if [ -s ...new-children.txt ]` branch contains `find .issues` and `mv` targeting `completed/`
  - `test_enqueue_or_skip_else_does_not_move_parent`: assert the shell code after the `else` does NOT contain `mv` to `completed/`
- `scripts/tests/test_next_issue.py` — verify that a file in `.issues/completed/` is excluded from `ll-issues next-issue` results (existing coverage validates the fix end-to-end)

### Documentation
- None required

## Implementation Steps

1. Open `scripts/little_loops/loops/recursive-refine.yaml` and locate `enqueue_children` at line 183
2. After line 193 (`echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped.txt`), insert the `find + mv` block:
   ```bash
   PARENT_FILE=$(find .issues -name "*-${captured.input.output}-*" ! -path "*/completed/*" 2>/dev/null | head -1)
   if [ -n "$PARENT_FILE" ]; then
     mkdir -p .issues/completed
     git mv "$PARENT_FILE" .issues/completed/ 2>/dev/null \
       || mv "$PARENT_FILE" .issues/completed/
   fi
   ```
3. Locate `enqueue_or_skip` at line 278; find the `if [ -s .loops/tmp/recursive-refine-new-children.txt ]` branch at line 304
4. After line 310 (skip-list write in the children-found branch), insert the identical `find + git mv || mv` block
5. Confirm line 313 (`else` branch — no children, skip-only) is left unchanged — no `mv` there
6. Add structural tests to `scripts/tests/test_builtin_loops.py:959` (`TestRecursiveRefineLoop`):
   - `test_enqueue_children_moves_parent_to_completed`
   - `test_enqueue_or_skip_moves_parent_to_completed_when_children_found`
   - `test_enqueue_or_skip_else_does_not_move_parent`
7. Run `python -m pytest scripts/tests/test_builtin_loops.py::TestRecursiveRefineLoop -v` to verify

## Impact

- **Priority**: P2 — Without this fix, clearing the skip file (BUG-1095) causes re-decomposition and duplicate child issues
- **Effort**: Small — Two identical shell snippets added to two states
- **Risk**: Low — Additive; the `find` is scoped to avoid already-completed files
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `recursive-refine`, `captured`

## Session Log
- `/ll:refine-issue` - 2026-04-13T14:50:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d22c48e-5d04-4aa3-8512-55595e860c13.jsonl`
- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6681d3d-2446-482f-83ae-c425d516d2ac.jsonl`

---

**Open** | Created: 2026-04-13 | Priority: P2
