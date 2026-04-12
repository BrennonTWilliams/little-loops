---
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# ENH-1066: Extract rubrics for format-issue skill

## Summary

Extract the template compliance matrix, quality classification tags, and testable-inference keyword logic from `format-issue` into a companion `rubric.md` file, update SKILL.md to load the rubric, and add a test file that verifies the rubric exists with expected content.

## Parent Issue

Sibling of ENH-1055 and ENH-1056: extends the rubric externalization pattern (established by ENH-1053) to the issue-formatting skill.

## Motivation

`format-issue` embeds three distinct tunable artifacts directly in SKILL.md: (1) a section-alignment compliance checklist keyed to the v2.0 template structure, (2) quality classification rules with `[QUALITY]`, `[SPECIFICITY]`, and `[CONTRADICTION]` severity tags, and (3) a testable-inference keyword list (2+ matches → `testable: false`). Teams using custom issue templates or different keyword thresholds cannot adjust any of these without forking the plugin. Extracting into a companion file enables project-level overrides via `.ll/rubrics/format-issue.md`.

## Expected Behavior

```
skills/format-issue/SKILL.md    ← logic only; loads rubric
skills/format-issue/rubric.md   ← default compliance matrix + quality tags + testable keywords
.ll/rubrics/format-issue.md     ← project override (optional)
```

Load idiom (from `skills/review-loop/SKILL.md`):
```
Read `rubric.md` (this companion file) now — or `.ll/rubrics/format-issue.md` if it exists (project override takes precedence). You will need the section compliance matrix, quality tag definitions, and testable-inference keywords.
```

## Scope

**In scope:**
- `skills/format-issue/SKILL.md` — remove inline section compliance checklist, quality classification rules, and testable-inference keyword list; add load-rubric directive
- `skills/format-issue/rubric.md` — new file with three sections:
  - `## Section Compliance Matrix` — required vs optional sections keyed to template version
  - `## Quality Classification Tags` — `[QUALITY]`, `[SPECIFICITY]`, `[CONTRADICTION]` definitions with examples
  - `## Testable-Inference Keywords` — keyword list + threshold (default: 2+ matches → `testable: false`)
- `scripts/tests/test_format_issue_skill.py` — verify SKILL.md references `rubric.md`, `rubric.md` exists, contains all three section headings

**Out of scope:** changes to the v2.0 issue template itself; other rubric extractions (ENH-1065, ENH-1067); documentation updates (ENH-1057)

## Implementation Steps

1. Read `skills/format-issue/SKILL.md` to identify exact compliance checklist, quality tag rules, and keyword list content
2. Create `skills/format-issue/rubric.md` with three sections: compliance matrix, quality tags, testable keywords
3. Replace extracted content in SKILL.md with load-rubric directive
4. Create `scripts/tests/test_format_issue_skill.py` following pattern in `scripts/tests/test_improve_claude_md_skill.py`
5. Run `python -m pytest scripts/tests/test_format_issue_skill.py`

## Success Metrics

- `/ll:format-issue` produces identical section gap reports and quality tags after rubric extraction
- Creating `.ll/rubrics/format-issue.md` with a custom keyword threshold (e.g., `3+` matches) causes `format-issue` to use the override
- Test file passes `python -m pytest`

## Related Issues

- ENH-1053: Parent issue (decomposed from)
- ENH-1055: Extract rubrics for confidence-check and issue-size-review (sibling)
- ENH-1056: Extract rubrics for go-no-go and audit-claude-config (sibling)
- ENH-1065: Extract rubrics for analyze-loop and review-loop (sibling)
- ENH-1067: Extract rubrics for medium-density skills batch (sibling)
- ENH-1057: Documentation updates (sibling — docs updated after extraction complete)

## Integration Map

### Files to Modify
- `skills/format-issue/SKILL.md` — remove inline rubric content, add load directive

### Dependent Files (Callers/Importers)
- N/A — skill invoked directly by users

### Similar Patterns
- `skills/confidence-check/rubric.md` (created by ENH-1055) — follow same file structure
- `skills/issue-size-review/rubric.md` (created by ENH-1055) — table format reference

### Tests
- `scripts/tests/test_format_issue_skill.py` — new file
- Pattern: `scripts/tests/test_improve_claude_md_skill.py`

### Documentation
- `docs/ARCHITECTURE.md` — covered by ENH-1057

### Configuration
- N/A

---

## Impact

- **Priority**: P3 — teams with custom issue templates have an immediate need to override section requirements
- **Effort**: Small — 1 new rubric file, 1 SKILL.md edit, 1 test file; no Python changes
- **Risk**: Low — content-only extraction; fallback keeps behavior unchanged
- **Breaking Change**: No

## Scope Boundaries

- Does not change the v2.0 issue template structure (`templates/enh-sections.json` etc.)
- Does not add new quality tags or compliance rules — extraction only
- Does not touch `capture-issue` testable-inference logic (that skill has its own keyword detection; only `format-issue`'s copy is in scope)

## Labels

`enhancement`, `skills`, `rubrics`, `project-tailorable`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e3e6bb-79d7-4b14-9468-7b82778befaa.jsonl`
