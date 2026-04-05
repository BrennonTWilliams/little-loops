---
discovered_date: 2026-04-04
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# FEAT-951: `wire-issue` skill — post-refinement integration wiring pass

## Summary

Issues that have been heavily refined with `/ll:refine-issue` often still have incomplete Integration Maps: missing callers and importers, absent plugin/manifest registrations, undocumented doc coupling, and no listing of which tests need updating or writing. This skill adds a dedicated wiring pass that traces all codebase touchpoints the implementation plan must hit — beyond what `refine-issue` covers.

## Motivation

`/ll:refine-issue` fills knowledge gaps broadly (root cause, behavioral analysis, similar patterns). It does not exhaustively trace the full dependency graph of the changed code. In practice, refined issues regularly omit:

- Files that import or call the affected symbols
- Plugin/manifest registrations (`plugin.json`, `__init__.py` exports, `hooks/hooks.json`)
- Documentation that describes the changed interface
- Tests that cover or will break due to the changes
- Config/schema files that reference the changed keys

Without this wiring, implementation agents discover these touchpoints mid-flight, causing plan divergence and missed updates.

## Acceptance Criteria

- [x] New skill at `skills/wire-issue/SKILL.md`
- [x] Traces callers/importers, registrations, doc coupling, tests, and config coupling
- [x] Runs 3 parallel agents: Caller Tracer, Side-Effect Tracer, Test Gap Finder
- [x] Diffs findings against existing Integration Map — only adds what's missing
- [x] Appends a Wiring Phase to Implementation Steps when gaps are found
- [x] All appended content marked with `_Wiring pass added by /ll:wire-issue:_`
- [x] Supports `--auto` and `--dry-run` flags
- [x] Listed in pipeline position: `refine-issue → wire-issue → ready-issue → manage-issue`
- [x] Registered in CLAUDE.md Issue Refinement list and `commands/help.md`

## Integration Map

### New Files
- `skills/wire-issue/SKILL.md` — skill definition

### Files Modified
- `.claude/CLAUDE.md` — added `wire-issue`^ to Issue Refinement list; updated skill count (21→22)
- `commands/help.md` — added `/ll:wire-issue` entry after `/ll:refine-issue`; added to Issue Refinement summary

## Implementation Steps

1. Draft `skills/wire-issue/SKILL.md` with 10-phase structure following skill conventions
2. Define 3 parallel Agent prompts: Caller/Importer Tracer (codebase-locator), Side-Effect Surface Tracer (codebase-analyzer), Test Gap Finder (codebase-pattern-finder)
3. Add diff logic: compare agent findings against existing issue wiring to produce `MISSING_WIRING`
4. Define update rules: append-only to Integration Map subsections, Wiring Phase block in Implementation Steps
5. Update `CLAUDE.md` and `commands/help.md`

## Resolution

**Completed**: 2026-04-04

### Changes Made
- `skills/wire-issue/SKILL.md`: Created. 10-phase skill — parse args, locate issue, extract existing wiring context, run 3 parallel agents, diff to find gaps, interactive confirmation, update Integration Map and Implementation Steps, append session log, output report.
- `.claude/CLAUDE.md`: Added `wire-issue`^ to Issue Refinement line; updated skill count to 22.
- `commands/help.md`: Added `/ll:wire-issue` entry with description; added `wire-issue` to Issue Refinement summary line.

### Key Design Decisions
- **Separate from `refine-issue`**: `refine-issue` covers broad knowledge gaps; `wire-issue` covers wiring completeness specifically. Keeping them separate preserves single-responsibility and allows targeted re-runs.
- **Diff-first approach**: Extracts what's already in the issue before running agents so output only adds genuinely missing wiring, not duplicates.
- **3 focused agents**: Each agent has a narrowly scoped prompt (callers, side-effects, test gaps) rather than one general research agent — reduces hallucination and improves signal quality.
- **Append-only with markers**: All additions are marked `_Wiring pass added by /ll:wire-issue:_` so it's clear what was researched vs. human-authored content.

## Labels

`feature`, `skills`, `issue-workflow`

## Session Log
- `/ll:capture-issue` + implementation - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd5a2fbc-571f-40ff-8b29-84ba38e167a4.jsonl`

---

## Status

**Completed** | Created: 2026-04-04 | Closed: 2026-04-04 | Priority: P3
