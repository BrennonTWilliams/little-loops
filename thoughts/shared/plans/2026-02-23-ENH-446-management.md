# ENH-446: Improve confidence-check to estimate outcome confidence

**Created**: 2026-02-23
**Issue**: `.issues/enhancements/P3-ENH-446-improve-confidence-check-outcome-confidence.md`
**Action**: improve

## Design Decisions

### 1. Dual-Score Approach (Option B from issue)

Add a separate Outcome Confidence assessment phase after the existing five-point readiness assessment. This keeps the existing readiness logic **completely untouched** while adding the new dimension.

Rationale: The issue's core motivation is that users confuse "ready to start" with "likely to finish." Separating scores into two dimensions provides the clearest signal.

### 2. Backward-Compatible Frontmatter

- **Keep `confidence_score`** — maps to the existing readiness score; all downstream consumers (manage-issue gate, existing issue files) continue working unchanged
- **Add `outcome_confidence`** — new field for the outcome score
- **No field renames** — avoids breaking change

This means the manage-issue Phase 2.5 confidence gate requires **zero changes**.

### 3. Four Outcome Criteria (0-25 each, max 100)

- **Complexity** (0-25): Count of files in Integration Map, scope of changes
- **Test Coverage** (0-25): Existence of test files for affected modules
- **Ambiguity** (0-25): Unresolved design decisions, TBD items, open questions
- **Change Surface** (0-25): Number of callers/dependents of modified code

### 4. Outcome Recommendation Tiers

| Score | Label |
|-------|-------|
| 80-100 | HIGH CONFIDENCE |
| 60-79 | MODERATE — expect some iteration |
| 40-59 | LOW — expect significant iteration |
| 0-39 | VERY LOW — high implementation risk |

## Changes Required

### File 1: `skills/confidence-check/SKILL.md` (primary change)

#### Change 1a: Update description frontmatter (lines 2-9)
Add mention of outcome confidence to the description.

#### Change 1b: Add Phase 2b after Phase 2 assessment (after line 258)
Insert new section: "### Phase 2b: Outcome Confidence Assessment"

Four criteria with detection methods and scoring tables:

**Criterion A: Complexity (0-25)**
- Detection: Count files in Integration Map / "Files to Modify" section; assess depth of changes (surface API vs deep internals)
- Scoring: 0-2 files = 25, 3-5 files = 18, 6-10 files = 10, 11+ files = 0

**Criterion B: Test Coverage (0-25)**
- Detection: For each file in Integration Map, check if corresponding test file exists in test directories using Glob
- Scoring: All modules tested = 25, Most tested = 18, Few tested = 10, No tests = 0

**Criterion C: Ambiguity (0-25)**
- Detection: Search issue for "TBD", "TODO", "open question", "decide", "either...or", options without resolution
- Scoring: No ambiguity = 25, Minor open questions = 18, Several design decisions left open = 10, Fundamental approach unclear = 0

**Criterion D: Change Surface (0-25)**
- Detection: For key modified functions/classes, Grep for import/call references across codebase
- Scoring: 0-2 callers = 25, 3-5 callers = 18, 6-10 callers = 10, 11+ callers = 0

#### Change 1c: Update Phase 3 (Score and Recommend) — lines 259-268
Add outcome confidence scoring alongside readiness. Show both scores with recommendation tiers.

#### Change 1d: Update Phase 4 (Update Frontmatter) — lines 270-302
Add `outcome_confidence` field to frontmatter alongside existing `confidence_score`.

#### Change 1e: Update Output Format — lines 315-344
Add outcome confidence section after the existing readiness scores. New dual-score summary:
```
READINESS SCORE:    XX/100 → [tier]
OUTCOME CONFIDENCE: XX/100 → [tier]
```

#### Change 1f: Update Batch Output Format — lines 346-376
Add `Outcome` column to results table, add outcome counts to summary.

#### Change 1g: Update Integration section — lines 378-385
Document that outcome_confidence is informational (not used by manage-issue gate).

### File 2: No other files require changes

Since we keep `confidence_score` unchanged:
- manage-issue SKILL.md — no changes needed (gate reads `confidence_score`)
- config-schema.json — no changes needed (gate threshold applies to readiness)
- config.py — no changes needed
- CLAUDE.md — already doesn't mention confidence-check by name
- plugin.json — skills loaded by directory, no description change needed
- ARCHITECTURE.md — only mentions directory name, no change needed

## Success Criteria

- [ ] Phase 2b added with four outcome criteria and scoring tables
- [ ] Phase 3 shows both readiness and outcome scores
- [ ] Phase 4 writes `outcome_confidence` to frontmatter alongside `confidence_score`
- [ ] Single-issue output shows dual scores with tier labels
- [ ] Batch output includes outcome confidence column
- [ ] Description frontmatter updated to mention outcome confidence
- [ ] Existing readiness logic unchanged (diff shows only additions)

## Risk Assessment

- **Low risk**: Purely additive changes to a single file; existing readiness scoring is untouched
- **Backward compatible**: `confidence_score` field preserved; `outcome_confidence` is a new addition
- **No downstream breakage**: manage-issue gate reads `confidence_score` which remains unchanged
