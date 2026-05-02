---
id: FEAT-1330
type: FEAT
priority: P3
parent_issue: FEAT-1325
---

# FEAT-1330: `/ll:assess-loop` Skill — Documentation & Wiring

## Summary

Update all documentation files and wiring tests to register the new `/ll:assess-loop` skill. Bumps skill count from 27→28 across five docs, adds the skill to tables and directory listings, and adds a `TestAssessLoopCommandsWiring` class to the doc-wiring test suite. **Depends on FEAT-1329 being merged first** (the skill file must exist before doc counts and references are valid).

## Parent Issue

Decomposed from FEAT-1325: `/ll:assess-loop` Skill for Loop Effectiveness Auditing

## Implementation Steps

9. Update `README.md` — `**27 skills**` → `**28 skills**` (~line 89); add `/ll:assess-loop` row to `### Automation & Loops` table (~line 166) and full Skills table (~line 221).

10. Update `CONTRIBUTING.md` — `27 skill definitions` → `28 skill definitions` (~line 125); add `assess-loop/` entry to the `skills/` directory listing (~lines 125–150).

11. Update `docs/ARCHITECTURE.md` — `# 27 skill definitions` → `# 28 skill definitions` (~line 100); insert `assess-loop/` tree entry between `analyze-loop/` and `audit-claude-config/` (~line 103).

12. Update `.claude/CLAUDE.md` — add `assess-loop`^ to the "Automation & Loops" bullet in `## Commands & Skills`; update `skills/ # Skill definitions (27 skills)` → `(28 skills)` in `## Key Directories`.

13. Update `docs/reference/COMMANDS.md` — add `### /ll:assess-loop` full section (with verdict values `met`, `partial`, `phantom`, `degraded` and the `--no-rubric-audit` flag); add `assess-loop` to the `**See also:**` line under `### /ll:analyze-loop`; add row to Quick Reference table.

14. Update `scripts/tests/test_enh1268_doc_wiring.py` — add `TestAssessLoopCommandsWiring` class parallel to `TestAnalyzeLoopCommandsWiring`; assert that `docs/reference/COMMANDS.md` contains the `### /ll:assess-loop` section with verdict values (`met`, `partial`, `phantom`, `degraded`) and the `--no-rubric-audit` flag.

## Note on doc_counts.py

No code change needed: `scripts/little_loops/doc_counts.py:verify_documentation()` uses `rglob("SKILL.md")` so it auto-detects the new count once the three documentation files above are updated to 28.

## Files to Modify

- `README.md`
- `CONTRIBUTING.md`
- `docs/ARCHITECTURE.md`
- `.claude/CLAUDE.md`
- `docs/reference/COMMANDS.md`
- `scripts/tests/test_enh1268_doc_wiring.py`

## Acceptance Criteria

- [ ] All five documentation files updated: skill count shows 28, `/ll:assess-loop` appears in all tables/listings.
- [ ] `docs/reference/COMMANDS.md` has a full `### /ll:assess-loop` section with `--no-rubric-audit` flag and all four verdict values.
- [ ] `TestAssessLoopCommandsWiring` passes in `test_enh1268_doc_wiring.py`.
- [ ] `ll-verify-docs` passes (doc count 28 matches actual `rglob("SKILL.md")` result).

## Session Log
- `/ll:issue-size-review` - 2026-05-02T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
