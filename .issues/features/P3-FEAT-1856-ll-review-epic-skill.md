---
id: FEAT-1856
type: FEAT
priority: P3
status: open
captured_at: '2026-06-01T17:35:32Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to: [FEAT-1855, FEAT-1737]
---

# FEAT-1856: `/ll:review-epic` skill — stalled-children and scope-drift audit

## Summary

Add a `/ll:review-epic <EPIC-ID>` skill that audits an EPIC's children for (1) stalled status (open/blocked for N days with no activity), (2) scope drift (child summaries that no longer match the EPIC's stated scope), (3) missing coverage (EPIC scope mentions areas with no child issue), and (4) closure readiness (all children done → recommend marking EPIC done). Output is a structured health report plus actionable suggestions, mirroring the shape of `/ll:review-sprint`.

## Current Behavior

`/ll:confidence-check` validates that an EPIC *has* children. `/ll:link-epics` assigns parentless issues to EPICs. No skill audits whether existing children are *still aligned* with the EPIC goal or whether the EPIC has gone stale. `ll-issues epic-progress` (FEAT-1855) will report progress numerically but does not interpret or recommend.

## Expected Behavior

```
$ /ll:review-epic EPIC-1773

## EPIC-1773 Health Report

**Progress**: 8/12 done (67%) — see FEAT-1855 for raw aggregates

### Stalled children
- ENH-1641 — open 24 days, no commits referencing ID, no session-log entries since 2026-05-08
  Recommendation: defer or close

### Scope drift
- FEAT-1820 mentions "Codex CLI parity" but EPIC scope is "FSM loop simplification"
  Recommendation: reparent to EPIC-1713 (Codex parity) or detach

### Missing coverage
- EPIC scope mentions "shared fragments audit" — no child issue covers fragments/
  Recommendation: capture a new child issue

### Closure recommendation
- Not ready (4 active children)
```

Skill writes nothing without confirmation; user can run `/ll:capture-issue --parent EPIC-1773` or `/ll:manage-issue defer ENH-1641` from the recommendations.

## Motivation

EPICs accumulate children over time, and child scope drifts as the EPIC matures. Without a periodic audit, EPICs become misleading (claiming to track work they no longer cover, or missing work they should). `/ll:review-sprint` provides this for ephemeral sprints — EPICs need the long-running-container equivalent.

This pairs with FEAT-1855 (raw progress aggregation): 1855 surfaces *what* the numbers are, 1856 interprets *what to do about them*.

## Proposed Solution

Skill-only implementation (no new CLI):

1. Load EPIC file + resolve children via the same union path as FEAT-1737/FEAT-1855.
2. Compute progress aggregates via `compute_epic_progress()` (FEAT-1855 dependency).
3. **Stall detection** — read `IssueFile.captured_at` + last session-log timestamp + git log of files touching the issue ID. Flag if no activity in N days (default 14, configurable via `epics.stale_days`).
4. **Scope drift** — LLM pass: compare EPIC `## Summary` text against each child's `## Summary`. Classify each child as `on-theme` / `tangential` / `off-theme`. Return tangential/off-theme with rationale.
5. **Missing coverage** — LLM pass: parse EPIC scope, list claimed sub-areas, compare against children; flag uncovered sub-areas.
6. **Closure check** — if all children `status: done`, recommend `ll-issues set-status EPIC-NNN done`.
7. Render structured Markdown report; emit a `recommendations` list at the end that maps to specific runnable commands.

Model the skill on `skills/review-sprint/` for layout, prompts, and output shape.

## Integration Map

### Files to Modify
- `skills/review-epic/SKILL.md` (new)
- `skills/review-epic/templates.md` (new, optional — extracted prompts/output formats)
- `commands/` — N/A (skill, not command)

### Dependent Files (Callers/Importers)
- Depends on `compute_epic_progress()` from FEAT-1855
- Depends on `SprintManager.load_or_resolve()` resolution logic (FEAT-1737)

### Similar Patterns
- `skills/review-sprint/SKILL.md` — same audit-and-recommend shape; copy phase structure
- `skills/confidence-check/SKILL.md` — EPIC-aware validation precedent

### Tests
- `scripts/tests/test_skills_metadata.py` — skill front-matter validation
- Live-LLM eval (out of scope for capture; track separately)

### Documentation
- `commands/help.md` — add `/ll:review-epic` to the listing
- `.claude/CLAUDE.md` — Commands & Skills section listing
- `docs/guides/EPIC_GUIDE.md` (if created in FEAT-1855)

### Configuration
- `epics.stale_days` (default 14) — threshold for stall detection
- `epics.review.enable_scope_drift_check` (default true)

## Implementation Steps

1. **Scaffold skill** — copy `skills/review-sprint/` layout; rename + retarget.
2. **Children resolution** — reuse FEAT-1737 path; do not duplicate logic.
3. **Stall detection** — non-LLM; reads frontmatter + git log + session log.
4. **Scope drift + missing coverage** — LLM prompts; structured JSON output.
5. **Closure check** — pure: all children `done` → recommend EPIC done.
6. **Report rendering** — Markdown sections + actionable command list.
7. **Wire into `/ll:help` listing** and CLAUDE.md skills table.
8. **Configuration** — register `epics.stale_days` in `config-schema.json`.

## Impact

- **Priority**: P3 — Quality-of-life for EPIC maintainers; depends on FEAT-1855 landing first.
- **Effort**: Medium — Skill + 2 LLM passes + 1 non-LLM pass; reuses existing resolution and aggregation.
- **Risk**: Low — Read-only audit, never mutates issues.
- **Breaking Change**: No

## Use Case

Before a quarterly planning session the user runs `/ll:review-epic` on each of the 13 active EPICs. The skill flags EPIC-1713 as having drifted (4 children now belong under a sibling EPIC) and EPIC-1622 as ready to close (all children done). The user re-parents and closes accordingly in ~10 minutes instead of opening 50+ child files.

## Acceptance Criteria

- [ ] `/ll:review-epic EPIC-NNN` produces a Markdown report with progress, stalled children, scope-drift findings, missing-coverage findings, and closure recommendation.
- [ ] Stalled detection uses configurable threshold (`epics.stale_days`, default 14).
- [ ] Scope-drift classification returns `on-theme` / `tangential` / `off-theme` with rationale per child.
- [ ] Skill writes nothing without user invocation of a follow-up command (audit-only).
- [ ] Each finding maps to a concrete runnable command in the recommendations list.
- [ ] Empty EPIC (no children) emits a clear message, no LLM passes, exit clean.
- [ ] EPIC not found exits with a clear error.
- [ ] Documented in `/ll:help`, CLAUDE.md skills section, and a guide page.

## API/Interface

Skill invocation:

```bash
/ll:review-epic EPIC-NNN
/ll:review-epic EPIC-NNN --skip-drift   # non-LLM mode (fast, structural only)
```

No Python API.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `epics`, `skill`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-01T17:45:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9321137-9371-4510-85ad-95b0940c3c6f.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
