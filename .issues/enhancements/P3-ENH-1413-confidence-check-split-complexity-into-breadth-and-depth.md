---
id: ENH-1413
type: ENH
priority: P3
status: open
captured_at: '2026-05-09T00:00:00Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
blocked_by: [ENH-1412]
---

# ENH-1413: Split confidence-check Criterion A (Complexity) into Breadth × Depth

## Summary

The `confidence-check` Criterion A (Complexity, `skills/confidence-check/SKILL.md:303-318`) scores by raw file count alone — 11+ files → 0/25. This conflates two independent dimensions: *Breadth* (how many sites change) and *Depth* (how complex each site change is). A 43-file uniform substitution sweep and a 43-file architectural rewrite score identically (both 0/25), even though their implementation risk profiles are opposite. Splitting Criterion A into Breadth × Depth makes the score reflect actual complexity instead of just file count, and fixes a double-count where the same underlying breadth penalizes both Criterion A and Criterion D.

## Current Behavior

Criterion A maps file count directly to a score, with depth as a hand-wavy modifier:

| Finding | Score |
|---------|-------|
| 1-2 files, isolated change in one subsystem | 25 |
| 3-5 files, changes in one or two subsystems | 18 |
| 6-10 files, changes span multiple subsystems | 10 |
| 11+ files or deep architectural changes | 0 |

The "or deep architectural" clause is the only place depth appears, and it's an OR rather than a separate axis. As a result:

- A 43-file mechanical text substitution scores 0 (matching "11+ files").
- A 3-file deep refactor of the dependency injection core scores 18 (matching "3-5 files"), even though it's far higher risk per site.
- The current Criterion D (Change Surface) *also* scores by count of callers/dependents — so a wide sweep gets penalized on both A and D for the same underlying breadth, double-counting it in the readiness total.

The result: file count dominates the readiness score. Sweeps look harder than they are; deep narrow refactors look easier than they are.

## Expected Behavior

Criterion A becomes a 25-point composite of two sub-scores:

**Breadth (0-12 points)** — number of distinct change sites:

| Finding | Score |
|---------|-------|
| 1-2 sites | 12 |
| 3-5 sites | 9 |
| 6-15 sites | 5 |
| 16+ sites | 0 |

**Depth (0-13 points)** — per-site change complexity, judged on the typical site (not the worst):

| Finding | Score |
|---------|-------|
| Mechanical/uniform — text substitution, type-list addition, schema row, doc edit | 13 |
| Local — small function or method body, contained logic change | 9 |
| Moderate — multi-function or cross-module logic with shared state | 5 |
| Deep — architectural rewiring, control-flow restructuring, contract changes | 0 |

Total Criterion A score = Breadth + Depth.

Detection methods are documented for each axis: Breadth from the "Files to Touch" enumeration and grep counts; Depth from the language used to describe the change ("substitute" / "add row" / "rewrite" / "restructure") and from inspection of the proposed diff shape.

After this change:
- A 43-file uniform sweep (FEAT-1407): Breadth 0 + Depth 13 = **13/25** (was 0/25). Combined with ENH-1412's Pattern B credit on Criterion D, the readiness total rises to a level that matches the actual risk profile.
- A 3-file deep refactor: Breadth 9 + Depth 0 = **9/25** (was 18/25). Now correctly scores lower than its file count alone would suggest.
- A 2-file mechanical change: Breadth 12 + Depth 13 = **25/25** (was 25/25). Unchanged.

## Use Case

**Who**: A maintainer running `/ll:confidence-check` on either a wide-shallow sweep or a narrow-deep refactor.

**Context**: Today the readiness score is dominated by one number — file count. Reviewers either (a) push to decompose mechanical sweeps that don't need decomposing, or (b) wave through narrow deep refactors that should get more scrutiny. Both failure modes come from collapsing Breadth and Depth into a single axis.

**Goal**: Have Criterion A reflect that wide-shallow and narrow-deep are different shapes of work with different risk profiles, and that a uniform 43-file substitution is genuinely lower-risk than a 3-file architectural rewire.

**Outcome**: Readiness score becomes a more honest signal. Sweeps with low per-site Depth score appropriately. Deep refactors with low Breadth score appropriately low on Depth. The double-count between A (file count) and D (caller count) goes away — A measures intrinsic shape, D measures de-risking artifacts (per ENH-1412).

## Motivation

- File count is being used as a complexity proxy, but it's a bad one — it can't distinguish "43 mechanical substitutions" from "43-file architectural rewrite." Splitting into Breadth × Depth makes the rubric say what it's actually trying to measure.
- The current rubric double-counts breadth across A (file count) and D (caller count). A wide sweep gets penalized twice for the same underlying property. Splitting A and (via ENH-1412) reframing D removes the double-count: A captures shape, D captures de-risking.
- This is a structural fix, not a special-case fix. Unlike adding a Pattern A/B classifier to one criterion, Breadth × Depth applies uniformly to every issue with no detection heuristic — both axes are always meaningful.
- Composes cleanly with ENH-1412. The two refinements are independently mergeable; either one improves the rubric, both together is the end state.

## Proposed Solution

1. Edit `skills/confidence-check/SKILL.md` Criterion A (lines 303-318):
   - Replace the single scoring table with two sub-scores: Breadth (0-12) and Depth (0-13), summed for the criterion total.
   - Add detection-method guidance for each axis: Breadth from enumerated files / grep counts; Depth from change-description language and proposed-diff shape.
   - Keep the existing CLI flag `--score-complexity` unchanged — the sum is what gets persisted; the Breadth/Depth split lives in the rubric prose only.
2. Add a worked example showing two contrasting issues: a wide-shallow sweep (high Depth, low Breadth) and a narrow-deep refactor (low Depth, high Breadth).
3. Update Phase 4.5 outcome-risk-factor guidance to phrase risk in terms of the dominant axis ("deep per-site complexity" vs "broad enumeration"), so the surfaced concerns track the new dimensions.
4. Re-run `/ll:confidence-check` on FEAT-1407 (wide-shallow) and one recent narrow-deep refactor to verify both move in the expected direction.

## Implementation Steps

1. Read `skills/confidence-check/SKILL.md` and identify the exact lines for Criterion A and any cross-references.
2. Draft the dual sub-score rubric (Breadth table + Depth table) and the per-axis detection guidance. Decide point allocation (proposed: 12 + 13 = 25, but 13 + 12 also acceptable).
3. Edit SKILL.md: replace the single Criterion A scoring table with the two sub-tables; add detection guidance; add the worked example.
4. Update Phase 4.5 risk-factor language so concerns are framed by the dominant axis.
5. Verify CLI compatibility: `ll-issues set-scores --score-complexity` still receives a single integer (the sum), no schema or flag changes needed.
6. Re-run `/ll:confidence-check` on FEAT-1407 (expected: A rises from 0 to ~13) and on one narrow-deep comparator (expected: A drops from its current count-based score). Confirm no regressions on simple isolated-change issues (still 25/25).
7. Update related docs: `docs/reference/API.md` if it documents the rubric; `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` if it discusses confidence scoring.

## Scope Boundaries

**In scope:**
- Splitting Criterion A (Complexity) in `skills/confidence-check/SKILL.md` into Breadth + Depth sub-scores summing to 25.
- Detection-method guidance for each axis (Breadth from enumerated files/grep counts; Depth from change-description language and diff shape).
- One worked example contrasting wide-shallow vs. narrow-deep.
- Phase 4.5 risk-factor language refresh to reference the dominant axis.
- Verification by re-running `/ll:confidence-check` on FEAT-1407 and one narrow-deep comparator.

**Out of scope:**
- Changes to Criterion D (Change Surface) — handled by sibling ENH-1412.
- Changes to Criteria B (Test Coverage) or C (Ambiguity) — they keep their single-table pattern.
- CLI flag or schema changes — `ll-issues set-scores --score-complexity` still receives a single integer.
- Re-scoring previously scored issues — only future scoring runs use the new rubric.
- Automated tests for the rubric itself — verification is by manual re-run on comparator issues.
- Cross-criterion weighting changes — total readiness arithmetic is unchanged.

## Acceptance Criteria

- `skills/confidence-check/SKILL.md` Criterion A is split into two sub-scores (Breadth + Depth) that sum to 25.
- Each sub-score has its own detection guidance and scoring table.
- A worked example contrasts a wide-shallow change with a narrow-deep change and shows the resulting Breadth + Depth math.
- The CLI persistence flow (`ll-issues set-scores --score-complexity`) is unchanged — it still receives a single 0-25 integer.
- Re-running `/ll:confidence-check` on FEAT-1407 produces a Criterion A score >= 10 (was 0), reflecting the high-Depth credit for mechanical sweeps.
- Re-running on a narrow-deep comparator produces a Criterion A score that is *lower* than its current file-count-only score, reflecting the depth penalty.
- A simple 1-2 file isolated change still scores 25/25 — no regression on the common case.
- Phase 4.5 risk-factor phrasing references Breadth and Depth as separate concerns where applicable.

## API/Interface

No CLI/API changes. `ll-issues set-scores --score-complexity` continues to accept a single integer (the sum of Breadth + Depth). The split exists only in the LLM-applied rubric prose.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Criterion A rubric (lines 303-318), Phase 4.5 risk-phrase guidance (lines 472-492), one worked example.
- (Optional) `docs/reference/API.md` if it cross-references the rubric.
- (Optional) `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` if it discusses confidence scoring approaches.

### Dependent Files (Callers/Importers)
- TBD — the rubric is LLM-applied prose; callers are any commands/skills that invoke `/ll:confidence-check`. Spot check: `grep -r "confidence-check" skills/ commands/ docs/`.
- `scripts/little_loops/cli/issues.py` — `ll-issues set-scores --score-complexity` interface; verify unchanged.

### Similar Patterns
- ENH-1412 (sibling) refines Criterion D; this issue refines Criterion A. The two compose without conflict.
- Other criteria (B Test Coverage, C Ambiguity) follow the single-table pattern; only A gets the dual sub-score treatment in this issue.

### Tests
- TBD — no automated tests exist for the rubric itself; verification is by re-running `/ll:confidence-check` on FEAT-1407 (wide-shallow) and one narrow-deep comparator.

### Documentation
- (Optional) `docs/reference/API.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` if they document the rubric.

### Configuration
- N/A — no config schema changes.

## Impact

- **Priority**: P3 — improves the informativeness of the readiness score; not blocking, but the current state mis-scores both wide-shallow and narrow-deep changes in opposite directions.
- **Effort**: Small — single skill file edit, ~30-50 lines of rubric content; verification by re-running confidence-check on two comparator issues.
- **Risk**: Low — touches a scoring rubric the LLM applies; no infrastructure or schema changes; CLI flag unchanged; reversible.
- **Breaking Change**: No. Existing scored issues retain their stored scores; only future scoring runs are affected. The `--score-complexity` value range and meaning are unchanged from the consumer's perspective.

## Related Key Documentation

- `skills/confidence-check/SKILL.md` — primary edit target; contains Criterion A (lines 303-318) and Phase 4.5 risk-factor guidance (lines 472-492).
- `docs/reference/API.md` — may cross-reference the rubric; verify during implementation.
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — may discuss confidence scoring; verify during implementation.

## Labels

`enhancement`, `confidence-check`, `rubric`, `captured`

## Related

- ENH-1412: sibling refinement — adds a verifiability ladder to Criterion D (Change Surface). Together, ENH-1412 + ENH-1413 remove the file-count double-count between A and D: A measures intrinsic shape (Breadth × Depth), D measures de-risking artifacts (enumeration + grep + wiring test).
- FEAT-1407: the trigger case — 43-file mechanical sweep currently scoring 0/25 on Criterion A despite uniform per-site changes.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-10T14:27:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:format-issue` - 2026-05-10T03:40:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf5df682-07d1-4a83-a25a-95d380fbd8ca.jsonl`
- `/ll:capture-issue` - 2026-05-09T00:00:00Z - captured from refinement discussion on ENH-1412

---

**Open** | Created: 2026-05-09 | Priority: P3
