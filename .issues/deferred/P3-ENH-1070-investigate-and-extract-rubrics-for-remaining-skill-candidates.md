---
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# ENH-1070: Investigate and extract rubrics for remaining skill candidates

## Summary

Read `ready-issue`, `refine-issue`, `review-sprint`, and `verify-issues` to determine whether each contains extractable inline rubric content, then extract and externalize any tunable criteria found following the established `rubric.md` pattern.

## Parent Issue

Final sweep of the rubric externalization initiative (ENH-1053). These four skills were identified as probable candidates during the ENH-1068/1069 analysis but were not fully read.

## Motivation

The rubric externalization sweep (ENH-1055 through ENH-1069) covered all skills with confirmed inline rubrics. Four skills remain unread but are plausible candidates:

- **`ready-issue`**: Literally an issue-readiness assessment — likely has readiness criteria that may overlap with `confidence-check` (ENH-1055) or define a distinct checklist.
- **`refine-issue`**: Has quality criteria for what counts as "refined" — completeness thresholds, specificity requirements — but criteria may be open-ended prose rather than a structured table.
- **`review-sprint`**: Sprint health check — may have health scoring dimensions or severity thresholds.
- **`verify-issues`**: Issue verification — may have accuracy criteria but likely lightweight.

Each skill should be read before committing to extraction, to avoid creating a rubric file for content that is either already prose-only or too thin to be worth externalizing.

## Expected Behavior

For each skill with extractable rubric content found:

```
skills/<skill>/SKILL.md   ← logic only; loads rubric
skills/<skill>/rubric.md  ← default criteria/thresholds
.ll/rubrics/<skill>.md    ← project override (optional)
```

For each skill with no extractable content: document the finding in the issue resolution notes and close as "not applicable."

## Scope

### Phase 1: Investigation (required before any extraction)

For each of the four skills:
1. Read `skills/<skill>/SKILL.md`
2. Identify any inline: scoring tables, numeric thresholds, severity levels, classification categories, quality checklists
3. Assess extraction value: is the content structured enough to be project-tunable?
4. Record finding per skill

### Phase 2: Extract (only for skills with confirmed extractable content)

For each skill where content is found:
- Create `skills/<skill>/rubric.md` with appropriate sections
- Update `SKILL.md` with load-rubric directive
- Create `scripts/tests/test_<skill>_skill.py` following `scripts/tests/test_improve_claude_md_skill.py`
- Run tests

**Out of scope:** ENH-1068 (manage-issue); ENH-1069 (wire-issue, create-eval-from-issues); documentation updates (ENH-1057)

## Implementation Steps

1. Read all four SKILL.md files: `ready-issue`, `refine-issue`, `review-sprint`, `verify-issues`
2. For each: record whether extractable rubric content exists and what it is
3. For skills with content: create `rubric.md`, update `SKILL.md`, create test file
4. For skills without content: note "no extractable rubric" in resolution
5. Run tests for any skills that were extracted
6. Update this issue with per-skill findings before closing

## Success Metrics

- All four skills are read and assessed
- Any found rubrics produce identical skill outputs before and after extraction
- All created test files pass `python -m pytest`
- Skills with no extractable content are documented and ruled out

## Related Issues

- ENH-1053: Parent issue (decomposed from)
- ENH-1055: Extract rubrics for confidence-check and issue-size-review (sibling)
- ENH-1056: Extract rubrics for go-no-go and audit-claude-config (sibling)
- ENH-1065: Extract rubrics for analyze-loop and review-loop (sibling)
- ENH-1066: Extract rubrics for format-issue (sibling)
- ENH-1067: Extract rubrics for audit-docs, audit-issue-conflicts, cleanup-loops, map-dependencies (sibling)
- ENH-1068: Extract rubrics for manage-issue (sibling)
- ENH-1069: Extract rubrics for wire-issue and create-eval-from-issues (sibling)
- ENH-1057: Documentation updates (sibling — docs updated after all extraction siblings complete)

## Integration Map

### Files to Investigate (read before modifying)
- `skills/ready-issue/SKILL.md`
- `skills/refine-issue/SKILL.md`
- `skills/review-sprint/SKILL.md`
- `skills/verify-issues/SKILL.md`

### Potential New Files (conditional on Phase 1 findings)
- `skills/ready-issue/rubric.md` (if content found)
- `skills/refine-issue/rubric.md` (if content found)
- `skills/review-sprint/rubric.md` (if content found)
- `skills/verify-issues/rubric.md` (if content found)
- Corresponding test files in `scripts/tests/`

### Dependent Files (Callers/Importers)
- N/A — all four skills are invoked directly by users

### Similar Patterns
- `skills/cleanup-loops/rubric.md` (created by ENH-1067) — medium-density reference
- Pattern: `scripts/tests/test_improve_claude_md_skill.py`

### Documentation
- `docs/ARCHITECTURE.md` — covered by ENH-1057

### Configuration
- N/A

---

## Impact

- **Priority**: P3 — completes the sweep; actual effort depends on Phase 1 findings
- **Effort**: Small — if no skills have extractable content, this closes quickly; up to Medium if all four do
- **Risk**: Low — investigation-first approach prevents over-extraction
- **Breaking Change**: No

## Scope Boundaries

- Does not extract content that is open-ended prose or inherently non-tunable
- Scope of extraction (per skill) determined by Phase 1 findings, not assumed upfront
- If `ready-issue` delegates entirely to `confidence-check`, note the delegation and close that skill as "not applicable"

## Labels

`enhancement`, `skills`, `rubrics`, `project-tailorable`, `investigation`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/559a575d-8887-4985-8698-12bfda0c5f88.jsonl`
