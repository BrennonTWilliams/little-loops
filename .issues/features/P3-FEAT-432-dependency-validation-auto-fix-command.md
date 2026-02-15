---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# FEAT-432: ll-deps fix command to auto-repair broken dependency references

## Summary

The `validate_dependencies()` function detects broken references, stale completed refs, missing backlinks, and cycles. However, there's no automated fix mechanism — users must manually edit issue files. Add a `ll-deps fix` command that repairs issues automatically.

## Current Behavior

`ll-deps analyze` detects problems but only reports them. Users must manually open each issue file and fix broken references, remove stale completed references, and add missing backlinks.

## Expected Behavior

`ll-deps fix` automatically repairs detected issues:
- Remove broken references (refs to non-existent issues)
- Update stale references (remove refs to completed issues)
- Add missing backlinks (if A blocks B, ensure B lists A in Blocked By)

> **Scope note (2026-02-14)**: Cycle auto-fix is explicitly out of scope — there is no single "correct" fix for dependency cycles, and heuristic choices could make the graph worse. Cycles should be reported by `ll-deps analyze` and resolved manually. This command handles the ~70% of validation issues (broken refs, stale refs, missing backlinks) that have unambiguous fixes.

## Motivation

Dependency graphs degrade over time as issues are completed, deleted, or renamed. Manual cleanup is tedious and error-prone. Auto-fix keeps the graph healthy with zero effort, improving sprint planning accuracy.

## Use Case

After completing several issues in a sprint, a developer runs `ll-deps fix` to clean up stale references. The command removes completed-issue references, adds missing backlinks discovered during the sprint, and reports what was changed. The developer reviews the changes with `git diff` before committing.

## Acceptance Criteria

- `ll-deps fix` removes references to non-existent issue files
- `ll-deps fix` removes references to issues in `.issues/completed/`
- `ll-deps fix` adds missing backlinks (bidirectional consistency)
- `ll-deps fix --dry-run` previews changes without modifying files
- Changes are reported to the user (file modified, what changed)

## Proposed Solution

Add a `fix` subcommand to `ll-deps`:

```python
def fix_dependencies(issues_dir: Path, dry_run: bool = False) -> list[str]:
    """Auto-repair broken dependency references."""
    validations = validate_dependencies(issues_dir)
    changes = []
    for v in validations:
        if v.type == "broken_ref":
            # Remove the broken reference from the issue file
            remove_dependency_ref(v.issue_path, v.broken_ref, dry_run)
            changes.append(f"Removed broken ref {v.broken_ref} from {v.issue_id}")
        elif v.type == "stale_ref":
            remove_dependency_ref(v.issue_path, v.stale_ref, dry_run)
            changes.append(f"Removed stale ref {v.stale_ref} from {v.issue_id}")
        elif v.type == "missing_backlink":
            add_dependency_ref(v.target_path, v.source_id, dry_run)
            changes.append(f"Added backlink {v.source_id} to {v.target_id}")
    return changes
```

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_mapper.py` — add fix functions
- `scripts/little_loops/cli/deps.py` — add `fix` subcommand

### Dependent Files (Callers/Importers)
- N/A

### Similar Patterns
- `validate_dependencies()` already detects the issues to fix

### Tests
- `scripts/tests/test_dependency_mapper.py` — add fix tests

### Documentation
- Update CLI help text

### Configuration
- N/A

## Implementation Steps

1. Add file-editing functions to `dependency_mapper.py`
2. Add `fix` subcommand to `ll-deps` CLI
3. Implement `--dry-run` mode
4. Add tests with fixture issue files
5. Test end-to-end with real issue directory

## Impact

- **Priority**: P3 - Reduces manual toil for dependency maintenance
- **Effort**: Medium - New subcommand with file editing
- **Risk**: Low - `--dry-run` default and git diff provide safety net
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `dependencies`, `cli`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P3
