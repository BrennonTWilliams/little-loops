---
discovered_date: 2026-02-22
discovered_by: capture-issue
---

# ENH-446: Improve confidence-check to estimate outcome confidence

## Summary

The `/ll:confidence-check` skill evaluates *precondition readiness* — whether an issue is ready to be coded (no duplicates, architecture fits, problem is understood, etc.). It does not assess *outcome confidence* — the probability that implementation will succeed without major problems. Enhance the skill to include an outcome confidence dimension, giving users a richer signal before they begin implementation.

## Current Behavior

The confidence check evaluates five precondition criteria (0–20 pts each):
1. No duplicate implementations
2. Architecture compliance
3. Problem understanding (type-specific: root cause / requirements clarity / rationale)
4. Issue well-specified
5. Dependencies satisfied

The resulting 0–100 score answers: "Is this issue ready to start?" The name "confidence check" misleads users into thinking it predicts implementation success, but it measures readiness preconditions only.

## Expected Behavior

The skill should either:
- **Option A**: Add a sixth assessment dimension (outcome confidence) alongside the existing five, with its own scoring rubric and explanation
- **Option B**: Separate the score into two sub-scores — "Readiness Score" (existing criteria) and "Outcome Confidence Score" (new)

Outcome confidence factors might include:
- **Complexity estimate**: How hard is the change? (touches many files vs. one isolated function)
- **Test coverage**: Is the area under test? (failures detectable early)
- **Historical stability**: Has this area had frequent bugs? (checked via git log)
- **Ambiguity risk**: Are there design decisions left open in the issue?
- **Change surface**: How many callers/dependents does the modified code have?

## Motivation

Users reading a 90/100 confidence score naturally conclude "this will go smoothly." When implementation hits unexpected complexity or missing tests, the high score feels deceptive. Separating precondition readiness from outcome probability gives users actionable information:
- High readiness + low outcome confidence → start, but expect iteration
- Low readiness + high outcome confidence → refine the issue before coding
- Both high → strong go signal

This also improves the `--all` batch workflow: users can triage issues not just by readiness but by implementation risk.

## Proposed Solution

Add a second assessment phase to the skill's five-point evaluation. After Phase 2 (five-point assessment), run an Outcome Confidence Assessment:

**Outcome Confidence Criteria** (suggested, requires design):
- **Complexity** (0–25): Count of files in Integration Map, depth of call chain
- **Test coverage** (0–25): Existence of test files for changed modules
- **Ambiguity** (0–25): Unresolved design decisions ("TBD" / open questions in issue)
- **Change surface** (0–25): Number of callers/dependents (grep-based)

Present both scores in output:
```
READINESS SCORE:   85/100  → PROCEED WITH CAUTION
OUTCOME CONFIDENCE: 62/100 → MODERATE RISK — expect iteration
```

The `confidence_score` frontmatter field could become two fields: `readiness_score` and `outcome_confidence`.

Alternative: keep a single composite score, but change the rubric weights to include outcome factors.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — primary change: add outcome confidence phase and output format

### Dependent Files (Callers/Importers)
- `skills/manage-issue/SKILL.md` — references confidence_score threshold (≥70 proceed); needs update if field names change
- `commands/confidence-check.md` — check if separate command file exists and needs update
- Any issue files with `confidence_score` frontmatter — field rename would invalidate cached scores

### Similar Patterns
- `skills/ready-issue/SKILL.md` — complementary skill; check for scoring patterns to reuse

### Tests
- No direct tests for skills; integration tested via usage

### Documentation
- `CLAUDE.md` skill description line for confidence-check
- `docs/ARCHITECTURE.md` if it references the scoring system
- `.claude-plugin/plugin.json` skill description

### Configuration
- N/A

## Implementation Steps

1. Design the outcome confidence rubric (criteria, point ranges, detection methods)
2. Decide on score presentation: single composite vs. dual scores vs. sub-scores
3. Update `skills/confidence-check/SKILL.md` with new Phase 2b (outcome confidence assessment)
4. Update output format section to show both dimensions
5. Update frontmatter update phase (Phase 4) for new field(s)
6. Update `skills/manage-issue/SKILL.md` threshold logic if field names change
7. Update CLAUDE.md and plugin.json descriptions

## Success Metrics

- A well-specified, simple one-file bug scores high on both dimensions
- A vague feature touching 20 files scores high readiness (if criteria met) but low outcome confidence
- Users can meaningfully distinguish "ready to start" from "likely to finish cleanly"

## Scope Boundaries

- **In scope**: Adding outcome confidence assessment to the existing skill; updating dependent references
- **Out of scope**: Historical git analysis (too slow for routine use), ML-based predictions, changes to `ready-issue` skill, modifying existing `confidence_score` values in issue files retroactively

## Impact

- **Priority**: P3 — Improves signal quality but not blocking anything
- **Effort**: Medium — Requires rubric design + skill rewrite + downstream updates
- **Risk**: Low — Additive change; existing readiness logic untouched if dual-score approach chosen
- **Breaking Change**: Yes (if field renamed) / No (if new field added alongside existing)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`, `skills`, `confidence-check`

## Verification Notes

_Verified: 2026-02-22_

**Integration Map inaccuracies found:**

1. **`skills/manage-issue/SKILL.md` threshold claim is wrong**: The issue states this file "references confidence_score threshold (≥70 proceed); needs update if field names change." In reality, `manage-issue` invokes `confidence-check` as **advisory/non-blocking** — there is no ≥70 gate. The skill description reads: "Consider running the `confidence-check` skill to validate implementation readiness. This is advisory (non-blocking)." No field rename would require updating manage-issue unless the advisory call itself is changed.

2. **Wrong path for ready-issue**: The Integration Map lists `skills/ready-issue/SKILL.md` as a "Similar Patterns" reference, but the actual file is `commands/ready-issue.md` (it is a command, not a skill with a `SKILL.md`).

3. **`commands/confidence-check.md` does not exist** (confirmed). The issue correctly frames this as "check if … exists" — no separate command file; the skill is invoked directly.

## Session Log

- `/ll:capture-issue` - 2026-02-22T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e8b8c544-019d-49cd-b615-1784045c0885.jsonl`
- `/ll:verify-issues` - 2026-02-22 - verification pass
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`

## Blocks

- ENH-448

---

## Status

**Open** | Created: 2026-02-22 | Priority: P3
