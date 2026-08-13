# Examples

```bash
# Interactive mode: review each conflict and approve/reject
/ll:audit-issue-conflicts

# Scope the audit to a single EPIC's transitive children (plus the EPIC file)
/ll:audit-issue-conflicts EPIC-2457

# Scoped + auto-apply (bare NNNN is normalized to EPIC-NNNN)
/ll:audit-issue-conflicts 2457 --auto

# Scope the audit to an explicit, hand-picked set of issues (no shared EPIC needed)
/ll:audit-issue-conflicts BUG-123,ENH-456,FEAT-555

# Explicit-list scope + dry-run
/ll:audit-issue-conflicts 123,456,054 --dry-run

# Auto-apply all recommendations without prompting
/ll:audit-issue-conflicts --auto

# Report only, no changes
/ll:audit-issue-conflicts --dry-run

# Cross-theme sweep: detect conflicts across thematic boundaries
/ll:audit-issue-conflicts --cross-theme

# Cross-theme dry-run: report only, no changes
/ll:audit-issue-conflicts --dry-run --cross-theme
```

## Related Commands

- `/ll:tradeoff-review-issues` — Evaluates utility vs complexity (is it worth doing?)
- `/ll:align-issues` — Validates issues against project goals
- `/ll:map-dependencies` — Traces blocked_by relationships
- `/ll:refine-issue` — Fills knowledge gaps in a single issue
