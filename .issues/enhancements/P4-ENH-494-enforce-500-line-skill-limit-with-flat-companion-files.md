---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
confidence_score: 98
outcome_confidence: 71
---

# ENH-494: Enforce 500-Line SKILL.md Limit with Flat Companion Files

## Summary

Skills should stay under 500 lines to minimize context consumption when loaded. Overflow content belongs in flat companion files alongside `SKILL.md` in `skills/<name>/` — the established pattern already used by 11 of 25 skills. This is a direct application of progressive disclosure: skills should be cheap to load, with full reference material available but not forced into context.

## Current Behavior

Some skills (e.g., `manage-issue`, `review-sprint`, `confidence-check`) likely exceed 500 lines. All skill content is loaded into context whenever the skill is active, regardless of whether the full content is needed for the current task.

There is no enforced line limit, and the existing flat companion-file pattern is not consistently applied to oversized skills.

## Expected Behavior

- All `SKILL.md` files remain at or under 500 lines
- Overflow content lives in flat companion files directly in `skills/<name>/` alongside `SKILL.md`
- The `SKILL.md` links to companion files with clear "see also" pointers
- A linting check (or documentation convention) establishes 500 lines as the limit

## Motivation

Every line in a `SKILL.md` is loaded into the context window when that skill is active. Large skills consume attention budget even when only a fraction of their content is relevant. The 500-line limit is not arbitrary — it's the same progressive disclosure principle the skills themselves teach. Practicing what we preach improves both performance and credibility.

## Proposed Solution

1. Audit all skills for line count: `wc -l skills/*/SKILL.md`
2. For any skill exceeding 500 lines, identify what content is "reference" vs. "operational"
3. Extract overflow to flat companion files in `skills/<name>/` (e.g., `scoring.md`, `templates.md`)
4. Add "See also" links in `SKILL.md` pointing to companion files
5. Document the 500-line convention in `CONTRIBUTING.md`
6. Optionally add a `ll-verify-skills` lint command to enforce the limit in CI

## Scope Boundaries

- **In scope**: Auditing skill sizes, extracting overflow to flat companion files, documenting the convention
- **Out of scope**: Changing skill logic or rewriting skill content substantively

## Implementation Steps

1. ~~Run `wc -l skills/*/SKILL.md | sort -n` to identify oversized skills~~ (**Done — see Research Findings below**)
2. Extract overflow content per skill using the flat companion-file pattern:
   - `audit-claude-config`: extract `SKILL.md:231–407` (Task 3 sub-agent prompt) + `SKILL.md:261–315` (settings table) → new companion file
   - `confidence-check`: extract `SKILL.md:189–385` (scoring criteria) + `SKILL.md:530–615` (output templates) → new companion file
   - `init`: extract `SKILL.md:130–201` (Display Summary template), `SKILL.md:505–550` (CLAUDE.md blocks), `SKILL.md:554–583` (Completion Message) → new companion file
   - `manage-issue`: remove duplicated Arguments block at `SKILL.md:449–516`
3. Add inline `See [companion.md](companion.md) for <description>` links at each extraction point (follow pattern from `format-issue/SKILL.md:190` or `review-loop/SKILL.md:69`); add `## Additional Resources` terminal section (follow `create-loop/SKILL.md:295–299`)
4. Update `CONTRIBUTING.md:436–462` ("Adding Skills" section) with 500-line limit, companion-file naming convention, and referencing patterns
### Wiring Phase (added by `/ll:wire-issue`)

5. Update `docs/ARCHITECTURE.md:104–106,115–116,136–138` — add new companion filenames to the verbose file-level directory tree for `audit-claude-config/`, `confidence-check/`, and `init/`
6. Add companion file existence tests (follow `test_improve_claude_md_skill.py:29–34` pattern) asserting that all 3 new companion files exist on disk after implementation

_The `ll-verify-skills` CLI lint command is tracked separately in ENH-977 (blocked by this issue)._

### Codebase Research Findings

_Added by `/ll:refine-issue` — Skill line count audit (updated 2026-04-07):_

**Current line counts (descending):**
```
711  skills/audit-claude-config/SKILL.md  ← EXCEEDS by 211 lines
660  skills/confidence-check/SKILL.md     ← EXCEEDS by 160 lines  (+60 since 2026-04-02)
617  skills/init/SKILL.md                 ← EXCEEDS by 117 lines  (+33 since 2026-04-02)
516  skills/manage-issue/SKILL.md         ← EXCEEDS by 16 lines
480  skills/wire-issue/SKILL.md
431  skills/format-issue/SKILL.md
422  skills/go-no-go/SKILL.md
421  skills/review-loop/SKILL.md
377  skills/capture-issue/SKILL.md
371  skills/issue-size-review/SKILL.md
361  skills/configure/SKILL.md
350  skills/analyze-loop/SKILL.md
338  skills/audit-docs/SKILL.md
324  skills/create-loop/SKILL.md
298  skills/workflow-automation-proposer/SKILL.md
292  skills/create-eval-from-issues/SKILL.md
284  skills/update/SKILL.md
284  skills/cleanup-loops/SKILL.md
280  skills/product-analyzer/SKILL.md
275  skills/update-docs/SKILL.md
262  skills/rename-loop/SKILL.md
207  skills/map-dependencies/SKILL.md
197  skills/improve-claude-md/SKILL.md
172  skills/issue-workflow/SKILL.md
135  skills/analyze-history/SKILL.md
```

**4 skills exceed 500 lines:**
- `audit-claude-config/SKILL.md` (711L) — extract Task 3 sub-agent prompt body (`skills/audit-claude-config/SKILL.md:231–407`, ~177L) and recognized-settings-key table (`SKILL.md:261–315`, ~55L) to a companion file
- `confidence-check/SKILL.md` (660L) — extract Phase 2 scoring criteria tables (`SKILL.md:189–385`, ~196L) and output format templates (`SKILL.md:530–615`, ~86L) to a companion file
- `init/SKILL.md` (617L) — extract Display Summary template (`SKILL.md:130–201`, ~73L), CLAUDE.md content blocks (`SKILL.md:505–550`, ~46L), and Completion Message template (`SKILL.md:554–583`, ~30L) to a companion file; `interactive.md` is already extracted
- `manage-issue/SKILL.md` (516L) — only 16 lines over; duplicated Arguments block at `SKILL.md:449–516` (~67L) is the primary target; `templates.md` already handles most overflow

**No companion files exist yet for the 4 oversized skills** — this PR establishes them.

### Companion File Pattern (Decided: Flat)

_Added by `/ll:refine-issue` 2026-04-07 — codebase pattern analysis. Decision applied 2026-04-07._

**Decision**: Use the established flat pattern — supplemental files live directly in `skills/<name>/` alongside `SKILL.md`. This is already used by **11 of 25 skills**:

| Skill | Companion Files |
|-------|----------------|
| `audit-claude-config/` | `report-template.md` |
| `audit-docs/` | `templates.md` |
| `capture-issue/` | `templates.md` |
| `configure/` | `areas.md`, `show-output.md` |
| `create-loop/` | `templates.md`, `loop-types.md`, `reference.md` |
| `format-issue/` | `templates.md` |
| `improve-claude-md/` | `algorithm.md` |
| `init/` | `interactive.md` |
| `manage-issue/` | `templates.md` |
| `review-loop/` | `reference.md` |
| `update-docs/` | `templates.md` |

**Established referencing conventions** (two patterns in use):
- `See [filename.md](filename.md) for <description>` — inline at the step where content is needed (used by `format-issue/SKILL.md:190`, `capture-issue/SKILL.md:184`, `configure/SKILL.md:154`, `init/SKILL.md:125`)
- `Read [filename.md](filename.md) now` — imperative read instruction (used by `review-loop/SKILL.md:69`)
- `## Additional Resources` terminal section (used by `create-loop/SKILL.md:295–299`, `init/SKILL.md:587–590`)

## Integration Map

### Files to Modify
- `skills/audit-claude-config/SKILL.md` — extract Task 3 sub-agent prompt (`SKILL.md:231–407`) and settings table (`SKILL.md:261–315`)
- `skills/confidence-check/SKILL.md` — extract scoring criteria (`SKILL.md:189–385`) and output templates (`SKILL.md:530–615`)
- `skills/init/SKILL.md` — extract Display Summary template (`SKILL.md:130–201`), CLAUDE.md blocks (`SKILL.md:505–550`), Completion Message (`SKILL.md:554–583`)
- `skills/manage-issue/SKILL.md` — remove duplicated Arguments block at `SKILL.md:449–516`
- `CONTRIBUTING.md:436–462` — "Adding Skills" section; add 500-line limit and companion-file convention (currently documents directory structure only, no size guidance)

### New Files
- `skills/audit-claude-config/<companion>.md` — Task 3 sub-agent prompt + settings table
- `skills/confidence-check/<companion>.md` — scoring criteria + output templates
- `skills/init/<companion>.md` — Display Summary template, CLAUDE.md blocks, Completion Message

### Dependent Files (Callers/Importers)

_No code-level callers. SKILL.md files are consumed directly by Claude Code when skills are activated._

### Tests
- `wc -l skills/*/SKILL.md` should show all files ≤ 500 lines after implementation
- New (required): companion file existence tests following `test_improve_claude_md_skill.py:29–34` pattern — assert that `skills/audit-claude-config/<companion>.md`, `skills/confidence-check/<companion>.md`, and `skills/init/<companion>.md` exist on disk
- `scripts/tests/test_skill_expander.py:238–261` — `TestExpandSkillAgainstRealManageIssue` reads the real `skills/manage-issue/SKILL.md`; passes unchanged after trimming (no config tokens removed), but monitor if any new companion file introduces unresolved `{{config.*}}` references

### Documentation
- `CONTRIBUTING.md:436–462` — "Adding Skills" section; insert 500-line limit, companion-file naming convention, and referencing pattern

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:104–106` — verbose file-level directory tree lists `audit-claude-config/` companion files by name (`report-template.md`); add new companion filename when created
- `docs/ARCHITECTURE.md:115–116` — tree shows `confidence-check/` as `└── SKILL.md` only; update to two-item list with new companion file
- `docs/ARCHITECTURE.md:136–138` — tree shows `init/` with `SKILL.md` + `interactive.md`; add new companion file as third entry


## Impact

- **Priority**: P4 — Incremental improvement; not blocking
- **Effort**: Low — Audit + text reorganization, no code changes
- **Risk**: Low — Reorganization only, skill behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `CONTRIBUTING.md` | Development conventions — target file for 500-line limit and companion-file pattern documentation |

## Labels

`enhancement`, `skills`, `context-engineering`, `progressive-disclosure`

## Session Log
- `/ll:confidence-check` - 2026-04-07T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/130838b8-fd77-4b29-856d-341e6961f971.jsonl`
- `/ll:wire-issue` - 2026-04-07T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/88123d93-05ff-43e6-a74f-96331f455d15.jsonl`
- `/ll:confidence-check` - 2026-04-07T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/418318f8-5c1d-44e5-ba71-c29bc3d183f0.jsonl`
- `/ll:refine-issue` - 2026-04-07T20:50:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/88123d93-05ff-43e6-a74f-96331f455d15.jsonl`
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:verify-issues` - 2026-04-03T02:58:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:verify-issues` - 2026-04-01T17:45:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:tradeoff-review-issues` - 2026-03-22T05:05:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7a58662a-8ea7-4c74-bb16-c6d77d559e08.jsonl`
- `/ll:verify-issues` - 2026-03-22T02:49:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45cffc78-99fd-4e36-9bcb-32d53f60d9c2.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Completed skill line count audit; 2 skills exceed 500 lines: audit-claude-config (708) and confidence-check (524)
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; still blocked by ENH-493, ENH-491, FEAT-441
- `/ll:verify-issues` - 2026-03-03 - Updated line counts: confidence-check 524→533, manage-issue 447→500 (now AT limit). Removed ENH-491 and FEAT-441 from Blocked By (both completed)
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c629849-3bc7-41ac-bef7-db62aeeb8917.jsonl`
- `/ll:refine-issue` - 2026-03-03T23:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` - Linked `CONTRIBUTING.md` to Related Key Documentation
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl` — VALID: audit-claude-config (708 lines) and confidence-check (533 lines) still exceed 500; removed stale Blocks refs ENH-502 and ENH-496 (both completed)
- `/ll:refine-issue` + `/ll:confidence-check` - 2026-03-06 - Re-assessed knowledge gaps: none new. Line counts re-confirmed (708, 533). `references/` pattern is clear; implementation steps fully specified. Raised confidence_score 80→86 (all research done, no open unknowns) and outcome_confidence 68→72 (slight residual uncertainty from ENH-493 blocker — reorganization needs to align with trigger description style before splitting content).
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: audit-claude-config(708L), confidence-check(533L) exceed limit
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: audit-claude-config (708L) and confidence-check (533L) still exceed 500-line limit; no `references/` subdirs exist
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl` — NEEDS_UPDATE: removed FEAT-638 (missing) and ENH-668 (completed) from Blocked By; updated confidence-check line count 533→554

---

## Verification Notes

- **Date**: 2026-04-02
- **Verdict**: NEEDS_UPDATE
- ENH-493 is now COMPLETED (in `completed/`) — removed from Blocked By. Issue is now unblocked.
- **4 skills** exceed 500 lines: `audit-claude-config/SKILL.md` = **711** (was 708), `confidence-check/SKILL.md` = **600** (was 604, decreased), `init/SKILL.md` = **584** (was 581), `manage-issue/SKILL.md` = **516** (was 513). No companion files exist for these 4 skills yet.

## Status

**Open** | Created: 2026-02-24 | Priority: P4

---

## Tradeoff Review Note

**Reviewed**: 2026-02-26 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - Only 2 skills exceed the 500-line limit (audit-claude-config: 708, confidence-check: 524), making scope smaller than expected. However, the `references/` subdirectory pattern needs to be defined and documented before extracting content. Blocked by ENH-493 (trigger descriptions), ENH-491, and FEAT-441. Implement after those resolve and the pattern convention is established in CONTRIBUTING.md.

## Blocked By

---

## Tradeoff Review Note (2026-03-03 Update)

**Reviewed**: 2026-03-03 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first — Implement ENH-493 (rewrite skill descriptions as trigger documents) first. Only after trigger descriptions are finalized should content be split into `references/` directories, so that reorganized reference material matches the new description style. Scope remains well-bounded (only 2 skills exceed 500 lines). Implementation is straightforward once ENH-493 resolves.

## Tradeoff Review Note (2026-03-22 Update)

**Reviewed**: 2026-03-22 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - Blocked by ENH-493 (rewrite skill descriptions as trigger documents). Content must be split into `references/` directories only after the trigger description style is finalized, so reorganized reference material is consistent with the new description style. Scope has grown to 3 violating skills (audit-claude-config: 708L, confidence-check: 604L, manage-issue: 513L). Implementation is straightforward once ENH-493 resolves.

## Blocks

- ENH-977: Add `ll-verify-skills` CLI lint command