---
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# ENH-1068: Extract rubrics for manage-issue

## Summary

Extract the inline confidence gate threshold, TDD red-phase validation table, verification checklist, and integration review PASS/WARN table from `manage-issue` into a companion `rubric.md` file, update `SKILL.md` and `templates.md` to load the rubric, and add a test file that verifies rubric existence and content.

## Parent Issue

Sibling of ENH-1055, ENH-1056, ENH-1065, ENH-1066, and ENH-1067: extends the rubric externalization sweep (established by ENH-1053) to the highest-density remaining skill.

## Motivation

`manage-issue` carries more tunable inline criteria than any other skill not yet extracted:

- **Confidence gate threshold**: `confidence_score >= config.commands.confidence_gate.readiness_threshold` is referenced inline in Phase 2.5 but the gate value itself is buried in config documentation — projects that run without confidence gates or with custom thresholds need a clear override path.
- **TDD Red Phase validation table**: Exit code check + pattern matching (`FAILED` valid; `ERROR`/`ImportError`/`SyntaxError`/`ModuleNotFoundError` invalid) is hard-coded in both `SKILL.md` and `templates.md`. Teams using non-pytest test runners have different patterns.
- **Verification checklist**: Phase 4 pass gates (tests / lint / types / build / run / custom) are listed inline. Projects with additional verification steps want to extend the list without forking the skill.
- **Integration review PASS/WARN table (Phase 4.5)**: Duplication / shared-module use / pattern conformance / integration-points — embedded in `templates.md`. Teams want to add project-specific integration checks.

## Expected Behavior

```
skills/manage-issue/SKILL.md      ← logic only; loads rubric
skills/manage-issue/templates.md  ← templates only; loads rubric for validation tables
skills/manage-issue/rubric.md     ← default criteria/thresholds
.ll/rubrics/manage-issue.md       ← project override (optional)
```

Load idiom (from `skills/review-loop/SKILL.md`):
```
Read `rubric.md` (this companion file) now — or `.ll/rubrics/manage-issue.md` if it exists (project override takes precedence).
```

## Scope

### `manage-issue`

- `skills/manage-issue/SKILL.md` — remove inline TDD red-phase validation criteria and verification checklist (Phase 4), add load-rubric directive at skill start
- `skills/manage-issue/templates.md` — remove inline integration review PASS/WARN table and Phase 0 TDD validation patterns, add load-rubric directive
- `skills/manage-issue/rubric.md` — new file with sections:
  - `## TDD Red Phase Validation` — exit code requirement, valid patterns (`FAILED`), invalid patterns (`ERROR`, `ImportError`, `SyntaxError`, `ModuleNotFoundError`), per-runner override guidance
  - `## Verification Checklist` — pass gates: tests / lint / types / build / run / custom, with notes on which are conditional on config
  - `## Integration Review Checks` — PASS/WARN table: duplication / shared-module use / pattern conformance / integration points; guidance for adding project-specific rows

**Tests:**
- `scripts/tests/test_manage_issue_skill.py` — new file: verify SKILL.md references `rubric.md`, `rubric.md` exists, contains expected section headings (`## TDD Red Phase Validation`, `## Verification Checklist`, `## Integration Review Checks`). Pattern: `scripts/tests/test_improve_claude_md_skill.py`

**Out of scope:** Confidence gate threshold value itself (that lives in `ll-config.json` under `commands.confidence_gate`); any logic changes to Phase 2.5 gate behavior; documentation updates (ENH-1057)

## Implementation Steps

1. Read `skills/manage-issue/SKILL.md` and `skills/manage-issue/templates.md` to identify exact inline rubric content boundaries
2. Create `skills/manage-issue/rubric.md` with the three sections above
3. Replace extracted content in `SKILL.md` with load-rubric directive
4. Replace extracted content in `templates.md` with load-rubric directive
5. Create `scripts/tests/test_manage_issue_skill.py` following the established test pattern
6. Run `python -m pytest scripts/tests/test_manage_issue_skill.py`

## Success Metrics

- `manage-issue` produces identical outputs before and after extraction
- Creating `.ll/rubrics/manage-issue.md` with a custom TDD pattern (e.g., `FAIL` for minitest) causes the skill to use the override instead of the default pytest patterns
- Creating `.ll/rubrics/manage-issue.md` with additional integration review rows causes Phase 4.5 to include project-specific checks
- Test file passes `python -m pytest`

## Related Issues

- ENH-1053: Parent issue (decomposed from)
- ENH-1055: Extract rubrics for confidence-check and issue-size-review (sibling)
- ENH-1056: Extract rubrics for go-no-go and audit-claude-config (sibling)
- ENH-1065: Extract rubrics for analyze-loop and review-loop (sibling)
- ENH-1066: Extract rubrics for format-issue (sibling)
- ENH-1067: Extract rubrics for audit-docs, audit-issue-conflicts, cleanup-loops, map-dependencies (sibling)
- ENH-1069: Extract rubrics for wire-issue and create-eval-from-issues (sibling)
- ENH-1057: Documentation updates (sibling — docs updated after all extraction siblings complete)

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md`
- `skills/manage-issue/templates.md`

### New Files
- `skills/manage-issue/rubric.md`
- `scripts/tests/test_manage_issue_skill.py`

### Dependent Files (Callers/Importers)
- N/A — `manage-issue` is invoked directly by users and `ll-auto`/`ll-parallel`/`ll-sprint`

### Similar Patterns
- `skills/review-loop/rubric.md` (created by ENH-1065) — most comparable: multi-section rubric with check tables
- `skills/issue-size-review/rubric.md` (created by ENH-1055) — scoring table reference
- Pattern: `scripts/tests/test_improve_claude_md_skill.py`

### Documentation
- `docs/ARCHITECTURE.md` — covered by ENH-1057

### Configuration
- N/A

---

## Impact

- **Priority**: P3 — highest-density remaining skill; TDD pattern override is the most requested customization for non-pytest projects
- **Effort**: Medium — 1 new rubric file, 2 SKILL.md-family edits, 1 test file; no Python changes
- **Risk**: Low — content-only extraction; fallback keeps behavior unchanged
- **Breaking Change**: No

## Scope Boundaries

- Does not change manage-issue's implementation phases, TDD workflow, or confidence gate logic
- Does not add new verification steps or integration checks — extraction only
- `templates.md` load-rubric directive covers only validation tables, not the full template structure

## Labels

`enhancement`, `skills`, `rubrics`, `project-tailorable`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/559a575d-8887-4985-8698-12bfda0c5f88.jsonl`
