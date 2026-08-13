# Conflict-Detection Task Prompt

Companion reference for `SKILL.md` Phase 2 "Conflict Detection". Use this verbatim
as the batch Task prompt (3–5 issues per batch).

```
Analyze the following issues for semantic conflicts.

You are looking for four conflict types:

1. **Requirement conflicts** — Issue A requires X, Issue B requires not-X (contradictory requirements)
2. **Objective conflicts** — Two issues solve the same problem but with different approaches (duplicated goal)
3. **Architecture conflicts** — Incompatible technical approaches (e.g., sync vs async, different data models, conflicting API shapes)
4. **Scope overlap** — Issues that partially duplicate each other's scope (overlapping but not identical)

For EACH pair of issues in this batch, determine if a conflict exists.

Issues to analyze (read each full file before reasoning):

[For each issue in the batch:]
- **File**: [path]
- **ID**: [ISSUE-ID]
- **Type**: [BUG/FEAT/ENH/EPIC]
- **Priority**: [P0-P5]
- **Title**: [title]
- **Summary excerpt**: [first 300 chars of summary]

Return a structured list of conflicts found. For each conflict:

- conflict_type: requirement | objective | architecture | scope
- severity: high | medium | low
  - high: directly contradictory, will cause implementation failures if both proceed
  - medium: significant overlap or incompatibility requiring coordination
  - low: minor duplication or loose coupling concern
- issues: [LIST of affected ISSUE-IDs, e.g. ["FEAT-100", "FEAT-200"]]
- description: [1-2 sentence explanation of the specific conflict]
- recommendation: merge | deprecate | split | add_dependency | update_scope
  - merge: consolidate both into one issue (one closes, scope absorbed)
  - deprecate: one issue is superseded, should be closed
  - split: issues should be explicitly scoped to avoid overlap
  - add_dependency: issues can coexist but need blocked_by ordering
  - update_scope: scope notes should be added to clarify boundaries
- proposed_change: [specific action, e.g., "Close FEAT-200, add its auth-caching scope to FEAT-100"]

If no conflicts exist among this batch, return: []
```
