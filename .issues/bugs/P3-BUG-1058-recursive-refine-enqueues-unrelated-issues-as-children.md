---
id: BUG-1058
discovered_date: 2026-04-12
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
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
- `scripts/little_loops/loops/sprint-build-and-validate.yaml:117` — `refine_unresolved` state calls `loop: recursive-refine`; this bug surfaces during sprint execution as well (fixing `recursive-refine.yaml` is sufficient — no change needed here)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `refine_issue` state delegates via `loop: recursive-refine` (with `context_passthrough: true`); `get_passed_issues` state reads `recursive-refine-passed.txt` and `recursive-refine-skipped.txt`. No code change needed — these output file names are unchanged by the fix; only their content becomes more accurate (fewer false children in skipped list)

### Similar Patterns
- `skills/issue-size-review/SKILL.md:149–150` — authoritative child issue template: `## Parent Issue` section with `Decomposed from [PARENT-ID]: [Parent Title]`; confirmed present at line 16 in ENH-1055, ENH-1056, ENH-1057

### Tests
- `scripts/tests/test_builtin_loops.py:931–1068` — `TestRecursiveRefineLoop` covers `detect_children` and `enqueue_or_skip` by structural assertion (state presence, file-path prefix, routing keys); **none of these will break** from the fix
- `scripts/tests/test_fsm_fragments.py:836` — `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` includes `recursive-refine.yaml`; passes as long as YAML remains structurally valid after edits

_Wiring pass added by `/ll:wire-issue`:_
- **Test gap**: No test in `TestRecursiveRefineLoop` asserts on the action-body content of `detect_children` or `enqueue_or_skip`. The fix's core correctness — the `Decomposed from` grep filter and the `diff-ids.txt` intermediate — is completely uncovered. The pattern for action-content assertions exists at `test_builtin_loops.py:589–668` (e.g., `assert "--auto" in state.get("action", "")`). Consider adding:
  - `test_detect_children_filters_by_parent_reference` — assert `"Decomposed from"` and `"recursive-refine-diff-ids.txt"` appear in `detect_children` action
  - `test_enqueue_or_skip_filters_by_parent_reference` — same assertions for `enqueue_or_skip` action

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:~385` — describes child detection behavior ("when child issues are detected from sub-loop or size-review") without mentioning the parent-verification filter; description will be inaccurate after fix. Update the `Technique` paragraph and FSM flow notes to describe the two-step approach: `comm` → `diff-ids.txt` → parent-reference grep → `new-children.txt`

### Configuration
- None

## Implementation Steps

1. In `detect_children` (lines 156–158): change `comm -13` target from `recursive-refine-new-children.txt` to `recursive-refine-diff-ids.txt` (new intermediate file), then add the parent verification `while` loop that reads `diff-ids.txt` and writes only verified children to `recursive-refine-new-children.txt`.
2. In `enqueue_or_skip` (lines 263–265): apply the identical two-step pattern (write `comm` output to `diff-ids.txt`, then filter → `new-children.txt`).
3. Verify: run `recursive-refine` on ENH-1053; confirm queue contains only ENH-1055/1056/1057, not BUG-1054.
4. Manually create an unrelated issue mid-run and confirm it is excluded from the child queue.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/guides/LOOPS_GUIDE.md:~385` — update the child-detection description to reflect the parent-verification filter; add mention of the `recursive-refine-diff-ids.txt` intermediate file in the flow description
6. (Optional but recommended) Add `test_detect_children_filters_by_parent_reference` and `test_enqueue_or_skip_filters_by_parent_reference` to `TestRecursiveRefineLoop` in `scripts/tests/test_builtin_loops.py` — assert that `"Decomposed from"` and `"recursive-refine-diff-ids.txt"` appear in each state's action body (follow the pattern at lines 589–668)

## Impact

- **Priority**: P3 — correctness bug; incorrect queue entries cause unexpected work but do not corrupt data
- **Effort**: Small — two localized YAML edits in the same file
- **Risk**: Low — filter only removes IDs that lack the parent reference; real children always have it
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `fsm-loop`, `recursive-refine`, `captured`

## Resolution

**Fixed** | Completed: 2026-04-12

- `detect_children` (lines 156–158 → two-step): `comm -13` output now written to `recursive-refine-diff-ids.txt`; each candidate is checked for `Decomposed from <PARENT_ID>` before being accepted into `recursive-refine-new-children.txt`
- `enqueue_or_skip` (lines 263–265 → two-step): identical parent-verification filter applied
- `docs/guides/LOOPS_GUIDE.md`: **Child detection** paragraph added to `recursive-refine` section describing the two-step filter
- `scripts/tests/test_builtin_loops.py`: added `test_detect_children_filters_by_parent_reference` and `test_enqueue_or_skip_filters_by_parent_reference` to `TestRecursiveRefineLoop`; all 19 tests pass

## Status

**Closed** | Created: 2026-04-12 | Priority: P3

---

## Session Log
- `/ll:ready-issue` - 2026-04-12T16:27:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ecd44592-946d-4dee-9872-4ca45a36c433.jsonl`
- `/ll:confidence-check` - 2026-04-12T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ccb22598-046e-48ad-9add-17bd62cd4973.jsonl`
- `/ll:wire-issue` - 2026-04-12T16:22:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3d7cdb6a-cc0a-4306-8db0-90ee101b7fa4.jsonl`
- `/ll:format-issue` - 2026-04-12T16:20:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0c96e34-4bac-495e-850d-271272713698.jsonl`
- `/ll:refine-issue` - 2026-04-12T16:17:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20856766-1501-45e9-b569-cb90b08cb44e.jsonl`
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7f1a02e-5a5e-4da3-8f6c-49300c6094a5.jsonl`
- `/ll:manage-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
