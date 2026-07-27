---
id: FEAT-2851
type: FEAT
priority: P2
status: open
parent: FEAT-2846
discovered_date: 2026-07-26
discovered_by: issue-size-review
blocked_by:
- FEAT-2849
labels:
- issues-cli
- dependency-graph
relates_to:
- FEAT-2842
---

# FEAT-2851: Optional --fix to backfill blocked_by from prose dependencies

## Summary

Add an opt-in `--fix` mode to `ll-issues format-check` that backfills
`blocked_by:` from confidently-matched prose dependency claims, staging a
reviewable diff rather than writing silently (the `anchor-sweep --dry-run`
posture). Decomposed from FEAT-2846; built on FEAT-2849's extractor and
gap taxonomy.

## Parent Issue

Decomposed from FEAT-2846: Detect prose dependency claims that are missing
from frontmatter. Covers Implementation Step 6 of the parent.

## Expected Behavior

`--fix` writes via `ll-issues link` (FEAT-2842) rather than editing
frontmatter directly, and defaults to a dry-run so the operator sees the
proposed edges before they're applied. This directly benefits this repo's
9 currently-drifting issues (see FEAT-2850) as an alternative or
complement to hand-fixing them.

`cmd_link()` (`scripts/little_loops/cli/issues/link.py:92-176`) is
idempotent (no-ops to `unchanged` if the edge already exists), supports
`--dry-run` (`would_link`/`would_unlink` status), and gates every write
through `_check_cycle()` — builds a `DependencyGraph` including the
prospective edge and calls `topological_sort()`, catching `ValueError` on a
cycle — before allowing a `blocked_by`/`depends_on` write. `--fix` should
invoke this (in-process or via `ll-issues link <id> --blocked-by
<target>`), not call `update_frontmatter()` directly.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/format_check.py` — add `--fix` flag,
  dry-run by default
- `scripts/little_loops/cli/issues/link.py:92-176` — `cmd_link()`, the
  target write path for confidently-matched prose deps

### Tests
- `scripts/tests/test_link_cli.py` — existing `cmd_link()` coverage; model
  for asserting `--fix` invokes the same idempotent/cycle-safe write path
- `scripts/tests/test_ll_issues_format_check.py` — add `--fix` dry-run and
  apply cases

## Implementation Steps

1. Define what counts as a "confidently-matched" prose dependency (exact ID
   match, unambiguous phrasing) versus one that should stay a reported gap
   only.
2. Implement `--fix` as dry-run by default, printing proposed
   `blocked_by`/`depends_on` edges.
3. Wire the apply path through `ll-issues link`, inheriting its
   idempotency and cycle guard.

## Acceptance Criteria

- [ ] `--fix` defaults to dry-run and prints proposed edges without
      writing.
- [ ] Applying `--fix` writes via `ll-issues link`'s cycle-safe path, not
      direct frontmatter edits.
- [ ] `--fix` is idempotent — running it twice produces no additional
      changes on the second run.

## Impact

- **Users**: backlog owners can resolve prose-dependency drift in bulk
  instead of hand-editing frontmatter for each drifting issue.
- **Risk**: Low. Dry-run default and reuse of `ll-issues link`'s existing
  cycle guard bound the blast radius.
- **Effort**: Small, once FEAT-2849 lands.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/cli/issues/link.py:92-176` | Idempotent, cycle-safe write path to reuse |

## Context

Decomposed from FEAT-2846 by `/ll:issue-size-review` (score 11/11, Very
Large); the parent issue itself notes this piece is "optional" and
separable from the core detection mechanism (FEAT-2849) and the sweep
(FEAT-2850).

## Session Log
- `/ll:issue-size-review` - 2026-07-26T00:00:00 - `52f8c37a-8768-4813-8704-c3364dbd6e28.jsonl`

---

## Status

open
