---
captured_at: "2026-04-22T21:44:08Z"
discovered_date: 2026-04-22
discovered_by: capture-issue
status: done
completed_at: 2026-04-22T00:00:00Z
---

# BUG-1259: `ll-issues clusters` inflates cluster via conflicting blocked-by sources

## Summary

`ll-issues clusters` merges what should be two separate connected components into one because the issue parser combines frontmatter `blocked_by:` fields with `## Blocked By` body sections — and ENH-977 has conflicting data in each source. The body section references ENH-494 (semantically correct: ENH-977 was split from ENH-494), while the frontmatter references ENH-1092 (an unrelated rename issue). The parser merges both, creating a spurious edge that bridges the {ENH-1092, ENH-977} pair into the main 19-issue cluster, producing a misleading 21-issue cluster.

## Current Behavior

`ll-issues clusters` reports Cluster 1 as 21 issues, including ENH-1092 ("Rename /ll:configure to /ll:settings") in the same cluster as unrelated dependency chains (FEAT-1002, FEAT-1116, FEAT-918, etc.).

The merge path is: `ENH-1092 → ENH-977 → ENH-494 → ENH-753 → (main cluster)`. ENH-977 picks up ENH-494 as a blocker from its `## Blocked By` body section even though the frontmatter says `blocked_by: [ENH-1092]`.

## Expected Behavior

ENH-1092 and ENH-977 should form their own 2-issue cluster. The main dependency chain (ENH-753, FEAT-1002, FEAT-1116, FEAT-918, and their dependents) should be a separate 19-issue cluster.

## Motivation

Incorrect cluster membership misleads sprint planning and dependency analysis. An inflated cluster suggests false coupling between unrelated work streams and makes it harder to understand the real dependency structure.

## Steps to Reproduce

1. Run `ll-issues clusters`
2. Observe Cluster 1 contains 21 issues including ENH-1092
3. Check ENH-977's frontmatter: `blocked_by: [ENH-1092]`
4. Check ENH-977's body: `## Blocked By` section lists `ENH-494`
5. Parser merges both, creating the spurious ENH-977 → ENH-494 edge

## Root Cause

- **File**: `scripts/little_loops/issue_parser.py`
- **Anchor**: `in IssueParser._parse_blocked_by / from_file` (around line 426)
- **Cause**: The parser reads `blocked_by` from two sources and concatenates them: (1) the `## Blocked By` markdown body section via `_parse_blocked_by()`, and (2) the `blocked_by` frontmatter field. When both exist with different values, the result is a union of both sets. ENH-977's body section is stale (predates the frontmatter migration), so it creates a spurious edge.

## Proposed Solution

Two complementary fixes:

1. **Data fix**: Update ENH-977's frontmatter to reflect accurate blockers (`blocked_by: [ENH-494]` or `[ENH-494, ENH-1092]` if both apply), and/or remove the stale `## Blocked By` body section to eliminate the conflict.

2. **Parser fix** (optional, defensive): When both frontmatter and body section provide `blocked_by` values, prefer the frontmatter (newer canonical format) and warn if they conflict, rather than silently merging both.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — dual-source merge logic (around line 426–436)
- `.issues/enhancements/P4-ENH-977-add-ll-verify-skills-cli-lint-command.md` — stale body section

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/clusters.py` — consumes `DependencyGraph` built from parsed issues
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()` trusts the merged `blocked_by` lists

### Similar Patterns
- `scripts/little_loops/issue_parser.py` line 429: same dual-source merge applies to `blocks:` field

## Implementation Steps

1. Fix ENH-977's frontmatter `blocked_by` to match the body section (or remove the body section)
2. Optionally add a warning in `issue_parser.py` when frontmatter and body section disagree on `blocked_by`
3. Verify with `ll-issues clusters` that ENH-1092/ENH-977 form a separate 2-issue cluster

## Impact

- **Priority**: P3 — Misleading output but no data loss
- **Effort**: Small — data fix is one-liner; parser fix is a few lines
- **Risk**: Low
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `issue-parser`, `clusters`, `captured`

## Status

**Completed** | Created: 2026-04-22 | Closed: 2026-04-22 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-22T21:44:08Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7542f113-71e7-4fa6-a71a-914c65cf0077.jsonl`
