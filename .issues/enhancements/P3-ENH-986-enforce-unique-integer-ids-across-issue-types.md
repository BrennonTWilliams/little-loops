---
discovered_date: 2026-04-07
discovered_by: capture-issue
---

# ENH-986: Enforce Unique Integer IDs Across Issue Types

## Summary

The integer portion of an issue ID must be globally unique across all issue types. Currently nothing prevents `ENH-016` and `FEAT-016` from coexisting, which constitutes an ID collision and can cause ambiguity when referencing issues by number alone.

## Current Behavior

`/ll:normalize-issues` and `ll-issues` (including `next-id`) operate per-type or do not validate cross-type uniqueness. Two issues can share the same integer ID as long as they have different type prefixes (e.g., `ENH-016` and `FEAT-016`).

## Expected Behavior

- The integer portion of every issue ID is unique across all types (bugs, features, enhancements, deferred, completed).
- `ll-issues next-id` returns the next integer not used by **any** issue regardless of type.
- `/ll:normalize-issues` detects and reports integer ID collisions as an error condition.
- Collision resolution offers renumbering one of the conflicting issues to the next available ID.

## Motivation

Issue IDs are frequently referenced in commit messages, PR descriptions, dependency chains (`depends_on`, `blocks`), and conversation. If two issues share the same integer, references like "see #016" or `--id 016` are ambiguous. The type prefix being part of the name does not protect against this in practice — the number is the meaningful identifier and must be treated as globally unique.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis (`ll-issues next-id`, `ll_issues` module, `normalize-issues` command)

### Dependent Files (Callers/Importers)
- TBD - use grep to find all places that call `next-id` or assign IDs

### Similar Patterns
- TBD - search for existing uniqueness checks in `ll_issues`

### Tests
- TBD - add test asserting `next-id` scans all types; add test for collision detection in normalize

### API/Interface
```python
# next-id should scan all active + completed + deferred directories
# normalize-issues should report cross-type collisions
```

## Implementation Steps

1. Audit `ll-issues next-id` — make it collect IDs across all issue directories (bugs, features, enhancements, completed, deferred)
2. Add collision detection to `/ll:normalize-issues` — scan all directories, group by integer ID, flag any integer appearing more than once with different type prefixes
3. Add collision resolution flow — suggest renumbering the lower-priority duplicate to the next available ID
4. Update `capture-issue` and any other ID-assignment logic to use the globally-scoped `next-id`
5. Add tests covering cross-type ID uniqueness and collision detection

## Impact

- **Priority**: P3 - Prevents silent ID collisions that corrupt dependency graphs and references
- **Effort**: Small - Mostly a scan-scope change in `next-id` and an additional validation pass in normalize
- **Risk**: Low - Read-only validation addition; renumbering is opt-in
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `issue-management`, `normalize-issues`, `ll-issues`, `captured`

---

## Status

**Open** | Created: 2026-04-07 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbefe1f9-2164-43d3-b547-be6f8fadffe4.jsonl`
