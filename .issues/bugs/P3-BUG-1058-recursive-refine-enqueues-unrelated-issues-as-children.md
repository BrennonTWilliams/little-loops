---
id: BUG-1058
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# BUG-1058: recursive-refine enqueues unrelated issues as children via naive list diff

## Summary

The `recursive-refine` FSM loop uses `comm -13` list-diffing to detect child issues created during parent refinement. Any issue created anywhere in the system between the baseline snapshot and the post-refinement snapshot is unconditionally treated as a child of the parent being refined — regardless of whether it was actually decomposed from that parent.

Observed: BUG-1054 (`discovered_by: capture-issue`) was independently created on the same day ENH-1053's real children (ENH-1055/1056/1057, `discovered_by: issue-size-review`) were created. The diff picked up BUG-1054 as a "new" ID and enqueued it as if it were a child of ENH-1053.

## Current Behavior

In both `detect_children` and `enqueue_or_skip` states, all IDs in `comm -13 pre-ids post-ids` are unconditionally accepted as children of the current parent. There is no check that a new issue was actually decomposed from that parent.

## Expected Behavior

Only issues whose file contains `Decomposed from <PARENT_ID>:` (written by `issue-size-review` when it creates child issues) should be accepted as children of that parent. Unrelated issues created concurrently must be ignored.

## Motivation

Incorrect child enqueuing causes the refinement loop to process unrelated issues as if they are sub-tasks of the current parent, polluting the queue and potentially triggering inappropriate refinement passes on issues that were never intended to be in scope.

## Steps to Reproduce

1. Start `recursive-refine` on a parent issue (e.g., ENH-1053).
2. While the loop is running refinement, create or allow an unrelated issue to be created (e.g., via `capture-issue`).
3. Observe that the unrelated issue is enqueued as a child in `detect_children` or `enqueue_or_skip`.

## Root Cause

- **File**: `scripts/little_loops/loops/recursive-refine.yaml`
- **Anchor**: `detect_children` state (lines 142–169) and `enqueue_or_skip` state (lines 251–282)
- **Cause**: Both states compute `comm -13 pre-ids post-ids` and write all results to `recursive-refine-new-children.txt` without filtering by parent reference. The assumption that "any new ID = child of current parent" is violated whenever concurrent issue creation occurs.

## Location

- **File**: `scripts/little_loops/loops/recursive-refine.yaml`
- **Lines**: 148–165 (`detect_children` action), 255–265 (`enqueue_or_skip` action)
- **Anchor**: `detect_children` and `enqueue_or_skip` states

## Proposed Solution

Add a **parent verification filter** after each `comm` diff in both states. For each candidate child ID, locate its issue file and check for `Decomposed from <PARENT_ID>` before accepting it.

Child issues created by `issue-size-review` consistently include this line in a `## Parent Issue` section:
```
Decomposed from ENH-1053: <title>
```

Filter logic (bash):
```bash
PARENT_ID="${captured.input.output}"
while IFS= read -r child_id; do
  child_file=$(find .issues -name "*-${child_id}-*" ! -path "*/completed/*" 2>/dev/null | head -1)
  if [ -n "$child_file" ] && grep -q "Decomposed from ${PARENT_ID}" "$child_file"; then
    echo "$child_id"
  fi
done < .loops/tmp/recursive-refine-diff-ids.txt \
  > .loops/tmp/recursive-refine-new-children.txt
```

This replaces the direct `comm` output being written to `new-children.txt` in both states.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — only file changed; two state actions updated

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/recursive-refine.yaml` is self-contained; no external callers

### Similar Patterns
- `issue-size-review` loop: writes `Decomposed from <PARENT_ID>:` in child issue `## Parent Issue` section — this is the authoritative signal to use as filter key

### Tests
- `scripts/tests/` — no test changes needed; this is a loop YAML fix, not a Python change

### Documentation
- None required

### Configuration
- None

## Implementation Steps

1. In `detect_children` action (lines 148–165): after writing `recursive-refine-diff-ids.txt` via `comm`, add the parent verification `while` loop to filter candidates and write verified results to `recursive-refine-new-children.txt`.
2. In `enqueue_or_skip` action (lines 255–265): apply the identical parent verification filter after the `comm` diff.
3. Verify: run `recursive-refine` on ENH-1053; confirm queue contains only ENH-1055/1056/1057, not BUG-1054.
4. Manually create an unrelated issue mid-run and confirm it is excluded from the child queue.

## Impact

- **Priority**: P3 — correctness bug; incorrect queue entries cause unexpected work but do not corrupt data
- **Effort**: Small — two localized YAML edits in the same file
- **Risk**: Low — filter only removes IDs that lack the parent reference; real children always have it
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `fsm-loop`, `recursive-refine`, `captured`

## Status

**Open** | Created: 2026-04-12 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7f1a02e-5a5e-4da3-8f6c-49300c6094a5.jsonl`
