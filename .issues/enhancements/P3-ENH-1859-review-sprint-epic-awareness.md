---
id: ENH-1859
type: ENH
priority: P3
status: open
captured_at: '2026-06-01T17:35:32Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to: [FEAT-1737, FEAT-1855, FEAT-1856]
---

# ENH-1859: `/ll:review-sprint` EPIC awareness — flag sprints that bypass EPIC critical path

## Summary

Extend `/ll:review-sprint` to detect when a sprint includes children of one or more EPICs and audit the sprint against the EPIC's critical path. Flag sprints that touch EPIC-X children but skip its known blockers, or that include children of competing EPICs without coordination.

## Current Behavior

`/ll:review-sprint` audits a sprint as a flat issue list. It identifies stale issues, dependency conflicts inside the sprint, and rough sizing concerns. It has no EPIC awareness — a sprint that contains 3 children of EPIC-1773 but skips the critical-path blocker is rated identically to a sprint that includes the blocker.

`ll-sprint <EPIC-ID>` (FEAT-1737, done) resolves an entire EPIC as a sprint, but explicitly-curated sprints can include EPIC children without surfacing the relationship.

## Expected Behavior

When auditing a sprint, the skill also produces an EPIC-context section:

```
## EPIC context

This sprint touches 2 EPICs:

### EPIC-1773 (Audit & simplify FSM loops)
- Sprint includes: ENH-1820, ENH-1774
- EPIC blocker not in sprint: ENH-1641 (24d stalled, blocks ENH-1820)
  Recommendation: add ENH-1641 to the sprint or defer ENH-1820

### EPIC-1713 (Codex CLI parity)
- Sprint includes: FEAT-1737
- All EPIC critical-path children included or done
```

## Motivation

Sprints derived from EPICs (via FEAT-1737) inherit the EPIC's dependency structure automatically. Manually curated sprints often don't — users pick the "interesting" children and skip the blocker, causing waves to stall mid-sprint. Surfacing this at review time prevents the mid-sprint surprise.

## Proposed Solution

In `skills/review-sprint/SKILL.md`, add a new audit phase:

1. **Identify EPIC touchpoints** — for each issue in the sprint, read `IssueFile.parent`; group by EPIC.
2. **For each touched EPIC**, fetch its full active-children set (FEAT-1737 union path).
3. **Compute the delta** — children in the sprint vs. children in the EPIC. For each child *not* in the sprint, check if any child *in* the sprint is `blocked_by` it.
4. **Render EPIC-context section** in the report with per-EPIC findings.
5. **Add recommendations** — concrete edit commands (`ll-sprint edit <name> --add ENH-1641`).

Resolution reuses FEAT-1737. Per-EPIC progress can leverage FEAT-1855's aggregation if available; not required.

## Integration Map

### Files to Modify
- `skills/review-sprint/SKILL.md` — add EPIC-context audit phase
- `skills/review-sprint/templates.md` — output section template

### Dependent Files (Callers/Importers)
- Reads from `SprintManager.load_or_resolve()` resolution (FEAT-1737)
- Optionally consumes `compute_epic_progress()` (FEAT-1855)

### Similar Patterns
- `skills/review-sprint/SKILL.md` existing dependency-conflict detection — same structural audit shape
- `skills/issue-size-review/SKILL.md` — sprint-shape input precedent

### Tests
- Snapshot test for the new EPIC-context section
- Integration test for sprint touching multiple EPICs

### Documentation
- `docs/guides/SPRINT_GUIDE.md` — note EPIC awareness in review section

### Configuration
- N/A (always on; cheap structural check)

## Implementation Steps

1. **Read sprint members** — already done by review-sprint.
2. **Resolve EPIC parents** — `IssueFile.parent` per sprint member; dedup to EPIC set.
3. **Per-EPIC child lookup** — reuse FEAT-1737 resolution.
4. **Compute deltas and blocker analysis** — pure logic.
5. **Render report section + recommendations**.
6. **Tests**.
7. **Docs**.

## Impact

- **Priority**: P3 — Quality-of-life for sprint planning; depends on FEAT-1737 (already done) and is more useful with FEAT-1855 / FEAT-1856 landed.
- **Effort**: Small — Pure extension to existing skill; no new dependencies.
- **Risk**: Low — Audit-only; never edits sprint files.
- **Breaking Change**: No

## Success Metrics

- Sprints touching ≥1 EPIC get an EPIC-context section in every review.
- Sprints that skip critical-path blockers are flagged with a concrete fix-up command.

## Scope Boundaries

- No automatic sprint editing — recommendations only.
- No new EPIC scoring or progress logic here (defer to FEAT-1855).
- No changes to `/ll:create-sprint` (that's covered by EPIC-aware planning if separately captured).

## API/Interface

No new flags. Behavior change only:

```
/ll:review-sprint <sprint-name>
# now includes "## EPIC context" section when applicable
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `epics`, `sprint`, `skill`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-01T17:45:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac3a8d0e-1e74-47b1-9d58-b8dbb8f453b4.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
