---
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# ENH-1065: Extract rubrics for analyze-loop and review-loop skills

## Summary

Extract inline signal-classification rules and check-ID tables from `analyze-loop` and `review-loop` into companion `rubric.md` files, update each SKILL.md to load the rubric, and add test files that verify the rubric files exist with expected content.

## Parent Issue

Sibling of ENH-1055 and ENH-1056: extends the rubric externalization pattern (established by ENH-1053) to the two loop-inspection skills.

## Motivation

Both skills embed tunable criteria directly in SKILL.md. `analyze-loop` hard-codes numeric triggers (3+ occurrences = BUG, 5+ re-entries = retry flood, ≥30s avg = slow state) and P2/P3/P4 priority assignments that project teams routinely want to adjust. `review-loop` hard-codes 18+ named check IDs (V-1–V-16, QC-1–QC-14, PR-1, FA-1–FA-6) with Error/Warning/Suggestion severity levels. Extracting these into companion files enables project-level overrides via `.ll/rubrics/<skill>.md` without forking the plugin.

## Expected Behavior

```
skills/analyze-loop/SKILL.md    ← logic only; loads rubric
skills/analyze-loop/rubric.md   ← default signal rules + priority assignments
.ll/rubrics/analyze-loop.md     ← project override (optional)

skills/review-loop/SKILL.md     ← logic only; loads rubric
skills/review-loop/rubric.md    ← default check-ID table + severity levels
.ll/rubrics/review-loop.md      ← project override (optional)
```

Load idiom (from `skills/review-loop/SKILL.md`):
```
Read `rubric.md` (this companion file) now — or `.ll/rubrics/<skill>.md` if it exists (project override takes precedence). You will need all criterion definitions and scoring tables.
```

## Scope

**In scope:**
- `skills/analyze-loop/SKILL.md` — remove inline signal classification rules (BUG/ENH type detection, numeric triggers, priority assignments), add load-rubric directive
- `skills/analyze-loop/rubric.md` — new file: signal classification table (issue type / trigger condition / min occurrences / priority) + deduplication logic + severity tier descriptions
- `skills/review-loop/SKILL.md` — remove inline check-ID table (V-1–V-16, QC-1–QC-14, PR-1, FA-1–FA-6) and severity level definitions, add load-rubric directive
- `skills/review-loop/rubric.md` — new file: full check-ID reference table + Error/Warning/Suggestion severity definitions
- `scripts/tests/test_analyze_loop_skill.py` — verify SKILL.md references `rubric.md`, `rubric.md` exists, contains signal classification headings
- `scripts/tests/test_review_loop_skill.py` — verify SKILL.md references `rubric.md`, `rubric.md` exists, contains check-ID table headings

**Out of scope:** format-issue (ENH-1066); medium-density batch (ENH-1067); documentation updates (ENH-1057)

## Implementation Steps

1. Read `skills/analyze-loop/SKILL.md` to identify exact signal classification content
2. Create `skills/analyze-loop/rubric.md` with signal table, priority assignments, and deduplication logic
3. Replace extracted content in `analyze-loop/SKILL.md` with load-rubric directive
4. Read `skills/review-loop/SKILL.md` to identify exact check-ID table and severity definitions
5. Create `skills/review-loop/rubric.md` with check-ID reference table and severity level descriptions
6. Replace extracted content in `review-loop/SKILL.md` with load-rubric directive
7. Create test files following pattern in `scripts/tests/test_improve_claude_md_skill.py`
8. Run `python -m pytest scripts/tests/test_analyze_loop_skill.py scripts/tests/test_review_loop_skill.py`

## Success Metrics

- `/ll:analyze-loop` produces identical issue signals after rubric extraction
- Creating `.ll/rubrics/analyze-loop.md` with custom threshold (e.g., `≥2 occurrences = BUG`) causes `analyze-loop` to use the override
- `/ll:review-loop` references all check IDs from `rubric.md` not from inline content
- Removing `.ll/rubrics/review-loop.md` falls back to default with no error
- Both new test files pass `python -m pytest`

## Related Issues

- ENH-1053: Parent issue (decomposed from)
- ENH-1055: Extract rubrics for confidence-check and issue-size-review (sibling)
- ENH-1056: Extract rubrics for go-no-go and audit-claude-config (sibling)
- ENH-1066: Extract rubrics for format-issue (sibling)
- ENH-1067: Extract rubrics for medium-density skills batch (sibling)
- ENH-1057: Documentation updates (sibling — docs updated after extraction complete)

## Integration Map

### Files to Modify
- `skills/analyze-loop/SKILL.md` — remove signal classification inline content, add load directive
- `skills/review-loop/SKILL.md` — remove check-ID table inline content, add load directive

### Dependent Files (Callers/Importers)
- N/A — skills are invoked by users directly, no Python imports

### Similar Patterns
- `skills/confidence-check/rubric.md` (created by ENH-1055) — follow exact same file structure
- `skills/review-loop/SKILL.md` already uses load-rubric idiom for its own rubric (model the directive after this)

### Tests
- `scripts/tests/test_analyze_loop_skill.py` — new file
- `scripts/tests/test_review_loop_skill.py` — new file
- Pattern: `scripts/tests/test_improve_claude_md_skill.py`

### Documentation
- `docs/ARCHITECTURE.md` — covered by ENH-1057

### Configuration
- N/A

---

## Impact

- **Priority**: P3 — quality-of-life; teams running heavy automation loops have the highest need to tune signal thresholds
- **Effort**: Small-Medium — 2 new rubric files, 2 SKILL.md edits, 2 test files; no Python changes
- **Risk**: Low — content-only extraction; fallback keeps behavior unchanged
- **Breaking Change**: No

## Scope Boundaries

- No changes to loop execution logic or Python CLI tools
- No changes to how loops write their event logs
- Does not add new check IDs or signal types — extraction only

## Labels

`enhancement`, `skills`, `rubrics`, `project-tailorable`, `loops`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e3e6bb-79d7-4b14-9468-7b82778befaa.jsonl`
