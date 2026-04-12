---
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# ENH-1069: Extract rubrics for wire-issue and create-eval-from-issues

## Summary

Extract inline signal-to-noise filter logic and wiring categories table from `wire-issue`, and harness variant selection rules and evaluation criteria synthesis format from `create-eval-from-issues`, into companion `rubric.md` files. Update both SKILL.md files with load directives and add test files following the established pattern.

## Parent Issue

Sibling of ENH-1055 through ENH-1068: extends the rubric externalization sweep (established by ENH-1053) to two medium-density skills.

## Motivation

Both skills embed structured, tunable criteria that projects may want to adjust:

- **`wire-issue`**: Hard-codes 3 signal-to-noise skip conditions (completed issues, auto-generated artifacts, mismatched test intent) and a 7-category wiring output table. Teams with additional artifact types or custom wiring categories want to extend these lists.
- **`create-eval-from-issues`**: Hard-codes harness variant selection (1 issue → Variant A single-shot; 2+ issues → Variant B multi-item) and the YES/NO evaluation answer format template. Teams running different harness architectures want to override the variant rules.

## Expected Behavior

```
skills/wire-issue/SKILL.md               ← logic only; loads rubric
skills/wire-issue/rubric.md              ← default filter rules + categories
.ll/rubrics/wire-issue.md                ← project override (optional)

skills/create-eval-from-issues/SKILL.md  ← logic only; loads rubric
skills/create-eval-from-issues/rubric.md ← default variant rules + answer format
.ll/rubrics/create-eval-from-issues.md   ← project override (optional)
```

## Scope

### `wire-issue`

- `skills/wire-issue/SKILL.md` — remove inline signal-to-noise filter skip conditions and wiring categories table (Phase 5), add load-rubric directive
- `skills/wire-issue/rubric.md` — new file with sections:
  - `## Signal-to-Noise Filter` — 3 skip conditions: `completed/` files, auto-generated artifacts (`*.pyc`, `__pycache__`), tests with mismatched intent; guidance for adding project-specific skip patterns
  - `## Wiring Categories` — 7-row output table: Callers/Importers / Registrations-Manifests / Documentation / Tests-update / Tests-new / Config-Schema / Impl-step-gaps; guidance for adding project-specific categories

### `create-eval-from-issues`

- `skills/create-eval-from-issues/SKILL.md` — remove inline harness variant selection rules and YES/NO answer format template, add load-rubric directive
- `skills/create-eval-from-issues/rubric.md` — new file with sections:
  - `## Harness Variant Selection` — 1 issue → Variant A (`initial: execute`, single-shot); 2+ issues → Variant B (`initial: discover`, multi-item); guidance for adding custom variants
  - `## Evaluation Answer Format` — YES/NO signal format, "Answer YES only if all conditions were clearly met" template, failure response must name failed condition(s) and observation

### Tests (one file per skill)
- `scripts/tests/test_wire_issue_skill.py` — verify SKILL.md references `rubric.md`, `rubric.md` exists, contains `## Signal-to-Noise Filter` and `## Wiring Categories`
- `scripts/tests/test_create_eval_from_issues_skill.py` — verify SKILL.md references `rubric.md`, `rubric.md` exists, contains `## Harness Variant Selection` and `## Evaluation Answer Format`

Pattern: `scripts/tests/test_improve_claude_md_skill.py`

**Out of scope:** ENH-1068 (manage-issue); ENH-1070 (remaining candidates); documentation updates (ENH-1057)

## Implementation Steps

1. Read `skills/wire-issue/SKILL.md` to identify exact inline rubric content boundaries
2. Read `skills/create-eval-from-issues/SKILL.md` to identify exact inline rubric content boundaries
3. Create `skills/wire-issue/rubric.md` with the two sections above
4. Replace extracted content in `wire-issue/SKILL.md` with load-rubric directive
5. Create `skills/create-eval-from-issues/rubric.md` with the two sections above
6. Replace extracted content in `create-eval-from-issues/SKILL.md` with load-rubric directive
7. Create both test files
8. Run `python -m pytest scripts/tests/test_wire_issue_skill.py scripts/tests/test_create_eval_from_issues_skill.py`

## Success Metrics

- Both skills produce identical outputs before and after extraction
- Creating `.ll/rubrics/wire-issue.md` with an additional skip condition (e.g., `*.generated.ts`) causes `wire-issue` to skip those files in Phase 5
- Creating `.ll/rubrics/create-eval-from-issues.md` with a custom variant threshold causes harness selection to use the override
- Both test files pass `python -m pytest`

## Related Issues

- ENH-1053: Parent issue (decomposed from)
- ENH-1055: Extract rubrics for confidence-check and issue-size-review (sibling)
- ENH-1056: Extract rubrics for go-no-go and audit-claude-config (sibling)
- ENH-1065: Extract rubrics for analyze-loop and review-loop (sibling)
- ENH-1066: Extract rubrics for format-issue (sibling)
- ENH-1067: Extract rubrics for audit-docs, audit-issue-conflicts, cleanup-loops, map-dependencies (sibling)
- ENH-1068: Extract rubrics for manage-issue (sibling)
- ENH-1057: Documentation updates (sibling — docs updated after all extraction siblings complete)

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md`
- `skills/create-eval-from-issues/SKILL.md`

### New Files
- `skills/wire-issue/rubric.md`
- `skills/create-eval-from-issues/rubric.md`
- `scripts/tests/test_wire_issue_skill.py`
- `scripts/tests/test_create_eval_from_issues_skill.py`

### Dependent Files (Callers/Importers)
- N/A — both skills invoked directly by users

### Similar Patterns
- `skills/cleanup-loops/rubric.md` (created by ENH-1067) — most comparable medium-density extraction
- Pattern: `scripts/tests/test_improve_claude_md_skill.py`

### Documentation
- `docs/ARCHITECTURE.md` — covered by ENH-1057

### Configuration
- N/A

---

## Impact

- **Priority**: P3 — medium-density pair; can be split per-skill if needed
- **Effort**: Small-Medium — 2 new rubric files, 2 SKILL.md edits, 2 test files; no Python changes
- **Risk**: Low — content-only extraction for both; fallback keeps behavior unchanged
- **Breaking Change**: No

## Scope Boundaries

- Does not change wire-issue's diff analysis logic or Phase 5 output formatting beyond removing inlined criteria
- Does not change create-eval-from-issues's YAML generation logic — only extracts variant selection and answer format template
- Can be split per-skill if needed; the two skills are fully independent of each other in this batch

## Labels

`enhancement`, `skills`, `rubrics`, `project-tailorable`, `batch`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/559a575d-8887-4985-8698-12bfda0c5f88.jsonl`
