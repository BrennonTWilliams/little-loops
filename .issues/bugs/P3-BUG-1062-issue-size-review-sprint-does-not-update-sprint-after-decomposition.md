---
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# BUG-1062: issue-size-review --sprint does not update sprint file after decomposition

## Summary

When `/ll:issue-size-review --sprint <name>` decomposes a parent issue into child issues, the sprint definition file (`.sprints/<name>.yaml`) is not updated. The sprint retains stale references to the now-completed parent IDs, and the newly created child IDs are never added to the sprint.

## Current Behavior

After running `/ll:issue-size-review --sprint my-sprint` and approving decomposition of a parent issue:

1. Child issues are created (e.g., `ENH-1063`, `ENH-1064`)
2. The parent issue is moved to `.issues/completed/`
3. The sprint file `.sprints/my-sprint.yaml` is **unchanged** — it still lists the parent ID (now pointing to a completed/moved file) and does not contain the child IDs

## Expected Behavior

After decomposition, the sprint file should be updated to:
1. Remove the decomposed parent ID from the `issues:` list
2. Append the new child IDs in place of the parent

The sprint should remain valid and executable without manual editing.

## Motivation

The `--sprint` flag scopes the audit to sprint issues — it's reasonable to expect that the sprint is kept consistent with the outcome. A user who runs `--sprint` for pre-sprint prep will end up with a broken sprint that silently skips decomposed parents (they no longer exist in active dirs) and omits the newly created children. The failure mode is silent: `ll-sprint` will warn about missing IDs but may still proceed, hiding the gap.

## Steps to Reproduce

1. Create a sprint with at least one oversized issue: `.sprints/my-sprint.yaml`
2. Run `/ll:issue-size-review --sprint my-sprint`
3. Approve decomposition of the oversized issue
4. Inspect `.sprints/my-sprint.yaml` — it still lists the parent ID
5. Run `ll-sprint run my-sprint` — it warns that the parent ID is not found (completed)

## Proposed Solution

In **Phase 6: Execution** of the `issue-size-review` skill, after completing each decomposition, check if `SPRINT_NAME` is set and update the sprint YAML:

```python
# In skills/issue-size-review/SKILL.md Phase 5 execution block
if SPRINT_NAME:
    # Read .sprints/<SPRINT_NAME>.yaml
    # Replace parent_id entry with child_ids in the issues: list
    # Preserve ordering — insert children where the parent was
    # Write updated YAML back
    git add ".sprints/${SPRINT_NAME}.yaml"
```

The sprint YAML `issues:` list is a flat list of bare IDs. The replacement is straightforward: find the parent ID in the list, replace with the ordered child IDs. This should happen for every decomposed parent in the same sprint run.

## Integration Map

### Files to Modify
- `skills/issue-size-review/SKILL.md` — add sprint YAML update step to Phase 5

### Dependent Files (Callers/Importers)
- `.sprints/*.yaml` — sprint definition files affected at runtime
- `scripts/little_loops/sprint.py` — reads sprint YAML; benefits from fix but no code change needed

### Similar Patterns
- `ll-sprint` YAML reading in `scripts/little_loops/sprint.py` — can reference this for parse/write pattern
- Other Phase 5 git-add calls in `issue-size-review` — follow the same `git add` pattern

### Tests
- TBD — add test verifying sprint YAML is updated when `--sprint` decomposition occurs

### Documentation
- `skills/issue-size-review/SKILL.md` — Phase 5 section needs the new step documented

### Configuration
- N/A

## Implementation Steps

1. In Phase 5 of `skills/issue-size-review/SKILL.md`, add a sprint update block: after writing child issues and moving the parent to completed, if `SPRINT_NAME` is set, read the sprint YAML, replace the parent ID with the child IDs (in order), and write the file back
2. Extend the `git add` call to stage the sprint YAML change alongside issue files
3. Update the **Output Format** section to mention sprint YAML was updated in the RESULTS block
4. Verify behavior: a `--sprint` run that decomposes N parents updates the sprint so child IDs appear and parent IDs are absent

## Impact

- **Priority**: P3 - Affects correctness of sprint-scoped decomposition; silent failure
- **Effort**: Small - Single skill file edit; no Python changes needed
- **Risk**: Low - Additive change to an existing phase; sprint YAML format is simple flat list
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `issue-size-review`, `sprint`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ad93ba1-3799-4f99-80ea-185dca355ffa.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P3
