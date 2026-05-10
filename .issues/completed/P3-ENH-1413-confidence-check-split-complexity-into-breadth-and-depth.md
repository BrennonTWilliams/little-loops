---
id: ENH-1413
type: ENH
priority: P3
status: open
captured_at: '2026-05-09T00:00:00Z'
completed_at: '2026-05-10T15:12:20Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
blocked_by: []
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1413: Split confidence-check Criterion A (Complexity) into Breadth × Depth

## Summary

The `confidence-check` Criterion A (Complexity, `skills/confidence-check/SKILL.md:316-331`) scores by raw file count alone — 11+ files → 0/25. This conflates two independent dimensions: *Breadth* (how many sites change) and *Depth* (how complex each site change is). A 43-file uniform substitution sweep and a 43-file architectural rewrite score identically (both 0/25), even though their implementation risk profiles are opposite. Splitting Criterion A into Breadth × Depth makes the score reflect actual complexity instead of just file count, and fixes a double-count where the same underlying breadth penalizes both Criterion A and Criterion D.

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

1. Edit `skills/confidence-check/SKILL.md` Criterion A (lines 316-331):
   - Replace the single scoring table with two sub-scores: Breadth (0-12) and Depth (0-13), summed for the criterion total.
   - Add detection-method guidance for each axis: Breadth from enumerated files / grep counts; Depth from change-description language and proposed-diff shape.
   - Keep the existing CLI flag `--score-complexity` unchanged — the sum is what gets persisted; the Breadth/Depth split lives in the rubric prose only.
2. Add a worked example showing two contrasting issues: a wide-shallow sweep (high Depth, low Breadth) and a narrow-deep refactor (low Depth, high Breadth).
3. Update Phase 4.5 outcome-risk-factor guidance to phrase risk in terms of the dominant axis ("deep per-site complexity" vs "broad enumeration"), so the surfaced concerns track the new dimensions.
4. Re-run `/ll:confidence-check` on FEAT-1407 (wide-shallow) and one recent narrow-deep refactor to verify both move in the expected direction.

## Implementation Steps

1. Read `skills/confidence-check/SKILL.md` Criterion A at **lines 316-331** (header at line 316, scoring table at lines 326-331) and Phase 4.5 at **lines 447-492** (risk-factor template block at lines 476-478); note internal cross-references to Criterion A at lines 431 and 440.
2. Draft the dual sub-score rubric (Breadth table + Depth table) and the per-axis detection guidance. Decide point allocation (proposed: 12 + 13 = 25, but 13 + 12 also acceptable).
3. Edit SKILL.md lines 316-331: replace the single Criterion A scoring table with two sub-tables using the Criterion D pattern at lines 367-397 as the structural template (`**What to check** → **Detection method** → **Scoring** (apply the table matching...):`).
4. Add a worked example using the `### Criterion D Pattern A vs Pattern B` example at lines 696-713 as the format template: named `### Criterion A Breadth × Depth` heading → two contrast scenarios with `Criterion | Score | Rationale` tables.
5. Update Phase 4.5 risk-factor language (lines 476-478 template block) so Outcome Risk Factors phrase concerns by dominant axis ("deep per-site complexity" vs "broad enumeration").
6. Add `TestCriterionABreadthDepthSplit` class to `scripts/tests/test_confidence_check_skill.py` following the `TestCriterionDDualPattern` pattern (lines 210-230): use `content.index("#### Criterion A:")` and `content.find("\n####", start + 1)` to bound the section; assert both Breadth and Depth sub-tables present and sum to 25.
7. Verify CLI compatibility: `ll-issues set-scores --score-complexity` (`set_scores.py:40-41`) still receives a single integer (the sum); no schema or flag changes needed.
8. Re-run `/ll:confidence-check` on FEAT-1407 (expected: A rises from 0 to ~13) and on one narrow-deep comparator (expected: A drops). Confirm no regressions on simple isolated-change issues (still 25/25).
9. Verify optional docs: `docs/reference/API.md:569` and `docs/reference/ISSUE_TEMPLATE.md:888` describe `score_complexity` as "Criterion A – Complexity (0-25)"; no update needed since field name, range, and semantics are unchanged.

### Wiring Phase (added by `/ll:wire-issue`)

_Constraint identified by wiring analysis:_

10. **Preserve `#### Criterion A:` heading exactly** — the new `TestCriterionABreadthDepthSplit` class uses `content.index("#### Criterion A:")` as its section anchor (mirroring `TestCriterionDDualPattern`). Only the body prose and scoring tables below the heading change; do not rename or reformat the heading line itself. [Agent 3]

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
- `skills/confidence-check/SKILL.md` — Criterion A rubric (**lines 316-331**, not 303-318), Phase 4.5 risk-factor template (**lines 476-478**), new worked example in `## Examples` section after line 713.
- `scripts/tests/test_confidence_check_skill.py` — add `TestCriterionABreadthDepthSplit` class following `TestCriterionDDualPattern` pattern (lines 210-230).
- `docs/reference/API.md:569` — no rubric content reproduced; field description unchanged. **No update needed.**
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — references `score_ambiguity` by name in escalation logic but does not reproduce Criterion A table. **No update needed.**

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/set_scores.py:40-41` — accepts `--score-complexity` as a single integer (`updates["score_complexity"] = args.score_complexity`); **no change needed** — stored value remains 0–25
- `scripts/little_loops/cli/issues/__init__.py:488-493` — `--score-complexity` argparse definition (`type=int`, `help="Complexity dimension score (0–25)"`); **no change needed**
- `scripts/little_loops/cli/issues/refine_status.py:543` — displays `cmplx` legend as "Criterion A – Complexity (0–25)"; **no change needed** (integer contract unchanged)
- `scripts/little_loops/issue_parser.py:243` — `IssueInfo.score_complexity: int | None = None`; **no change needed**
- `skills/issue-size-review/SKILL.md:232` — qualitative-skip guard uses `score_complexity ≥ 18`; remains valid after the rubric change (mechanical sweeps score 13–25; architectural narrows drop below 18, which is correct — they should not be skipped)
- `scripts/little_loops/frontmatter.py` — `update_frontmatter()` persists the integer; **no change needed**

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/show.py` — displays `score_complexity` in issue detail view; **no change needed** — integer contract unchanged [Agent 1]
- `scripts/little_loops/config/features.py` — `VALID_NEXT_ISSUE_SORT_KEYS` frozenset includes `"score_complexity"`; **no change needed** [Agent 1]
- `config-schema.json` — enumerates `"score_complexity"` as valid sort key (line 172) and refine-status column (line 821); **no change needed** [Agent 1]

### Similar Patterns
- `skills/confidence-check/SKILL.md:367-397` — Criterion D dual-pattern scoring (added by ENH-1412) is the **direct structural template**: same `**What to check** → **Detection method** → **Scoring** (apply the table matching the detected pattern):` layout with two bold-labeled sub-tables under one criterion heading
- `skills/confidence-check/SKILL.md:696-713` — `### Criterion D Pattern A vs Pattern B` worked example is the **template for the new Criterion A Breadth × Depth worked example**; format: named `### Criterion X` heading → `**Bold label — descriptor** (context):` → table with `Criterion | Score | Rationale` columns
- `skills/confidence-check/SKILL.md:217-271` — Criterion 3 type-fork dual-scoring: alternative model using `**Scoring** (use the table matching the issue type):` preamble

### Tests
- `scripts/tests/test_confidence_check_skill.py` — existing structural tests; already has `TestCriterionDDualPattern` class (lines 210-230, added by ENH-1412) as the **direct template** for a new `TestCriterionABreadthDepthSplit` class; use `content.index("#### Criterion A:")` and `content.find("\n####", start + 1)` to bound the section and assert: (a) both Breadth and Depth sub-tables present, (b) total point allocation is 12+13=25, (c) both detection methods documented
- `scripts/tests/test_set_scores_cli.py` — tests `--score-complexity` CLI flag; **no changes needed** (integer contract unchanged)
- `scripts/tests/test_issue_size_review_skill.py:97` — asserts `"score_complexity ≥ 18"` appears in issue-size-review skill; **no changes needed**
- Manual verification: re-run `/ll:confidence-check` on FEAT-1407 (expected Criterion A ≥ 10) and one narrow-deep comparator

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_status.py` — tests refine-status `cmplx` column display; asserts on field values only, not rubric text. **No changes needed.** [Agent 3]
- `scripts/tests/test_issue_parser.py` — tests `score_complexity` frontmatter parsing. **No changes needed.** [Agent 3]
- `scripts/tests/test_issues_cli.py` — integration tests for score field display. **No changes needed.** [Agent 3]
- `scripts/tests/test_action.py` — tests confidence-check discoverability; uses synthetic `tmp_path` SKILL.md, not the real file. **No changes needed.** [Agent 3]
- `scripts/tests/test_builtin_loops.py` — tests FSM loop routing to confidence-check state; no SKILL.md content assertions. **No changes needed.** [Agent 3]

### Documentation
- (Optional) `docs/reference/API.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` if they document the rubric.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — line 580 describes `cmplx` column as "complexity score 0–25"; line 808 documents `--score-complexity N` as "Complexity dimension score (0–25)". **No update needed** — field name, range, and semantics unchanged. [Agent 2]
- `docs/reference/ISSUE_TEMPLATE.md:888` — describes `score_complexity` as "Outcome criterion A – Complexity"; **no update needed** per Implementation Step 9 (field name and range unchanged). [Agent 2]

### Configuration
- N/A — no config schema changes.

## Impact

- **Priority**: P3 — improves the informativeness of the readiness score; not blocking, but the current state mis-scores both wide-shallow and narrow-deep changes in opposite directions.
- **Effort**: Small — single skill file edit, ~30-50 lines of rubric content; verification by re-running confidence-check on two comparator issues.
- **Risk**: Low — touches a scoring rubric the LLM applies; no infrastructure or schema changes; CLI flag unchanged; reversible.
- **Breaking Change**: No. Existing scored issues retain their stored scores; only future scoring runs are affected. The `--score-complexity` value range and meaning are unchanged from the consumer's perspective.

## Related Key Documentation

- `skills/confidence-check/SKILL.md` — primary edit target; Criterion A at **lines 316-331** (header line 316, table lines 326-331); Phase 4.5 at lines 447-492 (risk-factor template at lines 476-478); worked example section starts after line 695.
- `skills/confidence-check/SKILL.md:367-397` — Criterion D (ENH-1412) is the structural template for the dual-table pattern.
- `docs/reference/API.md:569` — `score_complexity` field doc; no rubric prose reproduced; **no update needed**.
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:327-347` — describes confidence scoring workflow; does not reproduce Criterion A table; **no update needed**.

## Labels

`enhancement`, `confidence-check`, `rubric`, `captured`

## Related

- ENH-1412: sibling refinement — adds a verifiability ladder to Criterion D (Change Surface). Together, ENH-1412 + ENH-1413 remove the file-count double-count between A and D: A measures intrinsic shape (Breadth × Depth), D measures de-risking artifacts (enumeration + grep + wiring test).
- FEAT-1407: the trigger case — 43-file mechanical sweep currently scoring 0/25 on Criterion A despite uniform per-site changes.

## Resolution

**Status**: Completed 2026-05-10

**Changes made**:
- `skills/confidence-check/SKILL.md`: Replaced Criterion A single scoring table with Breadth (0-12) + Depth (0-13) dual sub-tables, each with detection-method guidance; total still sums to 25
- `skills/confidence-check/SKILL.md`: Updated Phase 4.5 Outcome Risk Factors template to phrase risks by dominant axis ("deep per-site complexity" or "broad enumeration across N sites")
- `skills/confidence-check/SKILL.md`: Added `### Criterion A Breadth × Depth` worked example section with three contrasting scenarios (wide-shallow sweep, narrow-deep refactor, simple isolated change)
- `scripts/tests/test_confidence_check_skill.py`: Added `TestCriterionABreadthDepthSplit` class (7 tests) verifying both sub-tables present, point allocations correct, detection methods documented, and heading preserved

**Verification**: 38/38 tests pass.

## Session Log
- `/ll:ready-issue` - 2026-05-10T15:10:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3df7078e-72a1-4ab2-b539-bb557bb199d9.jsonl`
- `/ll:confidence-check` - 2026-05-10T16:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/02d9be03-0bf7-45dc-a4c1-c4c909b96c8d.jsonl`
- `/ll:wire-issue` - 2026-05-10T15:05:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f599406-cbb2-481e-9eb7-64801ff604df.jsonl`
- `/ll:refine-issue` - 2026-05-10T14:58:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87b169e7-5eaf-4702-a6c2-f5adc1a32387.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T14:27:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:format-issue` - 2026-05-10T03:40:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf5df682-07d1-4a83-a25a-95d380fbd8ca.jsonl`
- `/ll:capture-issue` - 2026-05-09T00:00:00Z - captured from refinement discussion on ENH-1412
- `/ll:manage-issue` - 2026-05-10T15:12:20Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3df7078e-72a1-4ab2-b539-bb557bb199d9.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P3
