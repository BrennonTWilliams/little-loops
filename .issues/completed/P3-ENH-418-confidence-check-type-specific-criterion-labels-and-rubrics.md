---
discovered_date: 2026-02-13
discovered_by: capture_issue
confidence_score: 95
---

# ENH-418: Confidence check type-specific criterion labels and rubrics

## Summary

The `/ll:confidence-check` skill's Criterion 3 ("Root Cause Identified") has type-specific detection logic in its method description (bugs check for root cause sections, features check for clear requirements, enhancements check for current behavior analysis), but the criterion label, scoring rubric, and output format all use generic "root cause" language regardless of issue type. This makes the output misleading for FEAT and ENH issues where "root cause" is not the right framing.

## Current Behavior

Criterion 3 always displays as "Root cause identified" in the output table and scoring rubric, even for ENH and FEAT issues. The detection method at SKILL.md:186-189 differentiates by type internally, but three aspects remain type-agnostic:

1. **Criterion label** — always "Root cause identified" in output
2. **Scoring rubric** (SKILL.md:192-197) — uses "root cause" language universally
3. **Output format** (SKILL.md:304) — hardcodes "Root cause identified" in the table

Example: For ENH-308, the evaluator correctly assessed "what's wrong with current behavior" but framed its finding as "Clear root cause: after multi-issue wave completes..."

## Expected Behavior

Criterion 3 should adapt its label, scoring rubric descriptions, and output format based on issue type:

- **BUG**: "Root cause identified" — checks for problem analysis with file:line references
- **FEAT**: "Requirements clarity" — checks for clear, specific requirements (not just "add X")
- **ENH**: "Rationale well-understood" — checks that current behavior issues and specific changes are explained

The detection method already has this logic; the label and rubric should match.

## Motivation

Confidence check output is reviewed by users to decide whether to proceed with implementation. When the criterion label says "Root cause identified" for an enhancement, it creates confusion — the user sees a label that doesn't match what was actually evaluated. This undermines trust in the scoring and makes the output harder to interpret at a glance.

## Proposed Solution

Update `skills/confidence-check/SKILL.md` in three places:

1. **Criterion 3 header** — use a type-conditional label:
   - BUG: "Root cause identified"
   - FEAT: "Requirements clarity"
   - ENH: "Rationale well-understood"

2. **Scoring rubric table** (SKILL.md:192-197) — provide type-specific scoring descriptions:
   - BUG: Keep current "Root cause clearly identified with code references" rubric
   - FEAT: Score based on requirement specificity ("concrete requirements with scenarios" = 20, "vague add X" = 0)
   - ENH: Score based on rationale clarity ("current behavior issues explained with specific changes" = 20, "only symptoms, no analysis" = 0)

3. **Output format** (SKILL.md:304) — replace hardcoded "Root cause identified" with `[Type-specific label]` placeholder

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — criterion 3 header, scoring rubric, output format template

### Dependent Files (Callers/Importers)
- `skills/manage-issue/SKILL.md` — invokes confidence-check but doesn't parse criterion labels
- No programmatic consumers parse the criterion names

### Similar Patterns
- N/A — confidence-check is the only skill with multi-criterion scoring

### Tests
- No automated tests for skill markdown files; manual verification via `/ll:confidence-check` invocation

### Documentation
- N/A — SKILL.md is the documentation

### Configuration
- N/A

## Implementation Steps

1. Define type-specific labels and scoring rubrics for Criterion 3
2. Update the detection method section to use the type-conditional label
3. Update the scoring rubric table with type-specific descriptions
4. Update the output format template to use the type-conditional label
5. Verify by running `/ll:confidence-check` against one issue of each type

## Impact

- **Priority**: P3 - Improves clarity of an existing tool; not blocking any workflows
- **Effort**: Small - Changes confined to a single markdown file with three targeted edits
- **Risk**: Low - No code changes, only skill prompt updates; worst case is minor formatting issues
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Skill system design |
| guidelines | CONTRIBUTING.md | Skill development conventions |

## Labels

`enhancement`, `captured`, `confidence-check`, `skills`

## Session Log
- `/ll:capture_issue` - 2026-02-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cbd4788d-c02e-4e79-954d-c4280452b2f2.jsonl`
- `/ll:manage_issue` - 2026-02-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3175cea9-640a-4fd6-b826-2217f1832ff7.jsonl`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `skills/confidence-check/SKILL.md`: Updated Criterion 3 header from fixed "Root Cause Identified" to type-conditional "Problem Understanding" with BUG/FEAT/ENH-specific labels
- `skills/confidence-check/SKILL.md`: Added type-specific "What to check" descriptions for each issue type
- `skills/confidence-check/SKILL.md`: Replaced single scoring rubric with three type-specific rubric tables (BUG/FEAT/ENH)
- `skills/confidence-check/SKILL.md`: Updated output format template to use `[Type-specific Criterion 3 label]` placeholder
- `skills/confidence-check/SKILL.md`: Updated frontmatter description to reflect type-specific criterion

### Verification Results
- Tests: N/A (markdown-only change)
- Lint: PASS
- Types: PASS
- Integration: PASS

---

## Status

**Completed** | Created: 2026-02-13 | Completed: 2026-02-13 | Priority: P3
