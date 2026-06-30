---
id: ENH-2401
priority: P2
type: ENH
status: done
captured_at: '2026-06-30T16:27:54Z'
completed_at: '2026-06-30T16:27:54Z'
discovered_date: 2026-06-30
discovered_by: decide-issue-design-gap-analysis
labels:
- skills
- decide-issue
- auto-mode
- pipeline
confidence_score: 100
outcome_confidence: 95
---

# ENH-2401: decide-issue — recognize bullet-list options + declarative recommendations, and stop short-circuiting on absent Open Questions

## Summary

Close a design gap in `skills/decide-issue/SKILL.md` surfaced by running
`/ll:decide-issue FEAT-389 --auto` against an external project (`cards`). The
skill exited `NO_ACTIONABLE_DECISIONS` even though the issue contained two real,
author-recommended decisions — they were written as informal `- (a)/(b)/(c)`
bullet lists under `## Codebase Research Findings` with explicit `**Recommended**`
markers, a shape the skill's option scan did not cover.

Two root causes, both fixed:

1. **Phase 3b-i short-circuit.** The resolved-question filter treated an
   *absent* `## Open Questions` section the same as an all-resolved one and took
   the `NO_ACTIONABLE_DECISIONS` exit *before* the provisional-language scan ever
   ran. Since `refine-issue` commonly deposits options/recommendations in
   `## Proposed Solution` or `## Codebase Research Findings` (not Open Questions),
   absence is the common case — so the scan was routinely skipped.
2. **No coverage for bullet-list options or declarative recommendations.** Even
   after falling through, Patterns 1–3 (formal `### Option`/`**Option**`/numbered)
   and Provisional Patterns A–C (`(e.g., …)`, `TBD`, "must be replaced with") did
   not match the `- (a) … / - (b) …` + `**Recommended**: (b)` shape.

## Current Behavior (before this change)

- An issue with `decision_needed: true` and no `## Open Questions` section exits
  `NO_ACTIONABLE_DECISIONS` in `--auto` mode without scanning for inline
  decisions, leaving the pipeline blocked on a decision the author already made.
- Bullet-list options and prose recommendations are invisible to the scan.

## What Was Done

`skills/decide-issue/SKILL.md` (six edits, file 461 → 481 lines, under the
500-line `ll-verify-skills` cap):

- **Phase 3b-i fall-through:** the `NO_ACTIONABLE_DECISIONS` exit now fires *only*
  when `## Open Questions` **exists with items that are all resolved**. Absent,
  empty, or partially-unresolved sections fall through to the provisional scan.
- **Phase 3 Pattern 4 (bullet-list options):** matches `- (a) …` / `- **Option X**`
  bullets; extraction widens to `## Codebase Research Findings` /
  `## Implementation Status` when `## Proposed Solution` yields 0 options.
- **Phase 3b Provisional Pattern D (declarative recommendation):** recognizes
  `**Recommended**: (b)`, "the recommendation is now (b)", and multi-part winners
  like `(a)+(b)`; the referent must exist as a Pattern-4 bullet option.
- **Auto-mode guardrail:** Pattern-4 bullet options are *not* scored in `--auto`
  unless an explicit recommendation marker (Pattern D) names one — automation
  must not re-litigate an informal list the author may have already settled. This
  preserves the "automation cannot clear a flag it did not earn" intent.
  Interactive mode scores bullet options normally through Phases 4–7.
- **Clear-winner write-back** updated so Pattern D annotates the recommended
  bullet with a `> **Selected:** (x) — per the stated recommendation` callout.

## Acceptance Criteria

- [x] Absent/empty `## Open Questions` no longer short-circuits to
  `NO_ACTIONABLE_DECISIONS`; the provisional scan runs.
- [x] Bullet-list options (`- (a)/(b)/(c)`) are documented as Pattern 4.
- [x] Declarative recommendations are documented as Provisional Pattern D.
- [x] Auto-mode requires an explicit recommendation marker before acting on
  bullet-list options.
- [x] SKILL.md stays within the 500-line limit (`ll-verify-skills` exit 0).
- [x] Structural tests pass (`test_decide_issue_skill.py`, 44 passed).

## Files Changed

- `skills/decide-issue/SKILL.md` — Phase 3 intro + Pattern 4, Option Count Check
  auto-mode guardrail, Phase 3b-i fall-through, Provisional Pattern D, clear-winner
  write-back note.
- `scripts/tests/test_decide_issue_skill.py` — added `TestPattern4BulletOptions`
  and `TestPattern3bDeclarativeRecommendation` structural test classes (8 new tests).

## Notes

Triggered by the analysis report `decide-issue-feat-389-auto-design-gap.md`
(untracked, repo root). The report correctly diagnosed the design gap but
contained two project-leakage errors that were *not* followed: it referenced a
TypeScript test (`tests/skills/decide-issue.test.ts`) and a `__fixtures__`
snapshot harness that do not exist in little-loops — the real, structural test
is the Python file above. FEAT-389 itself lives in the `cards` project and was
not modified here; a re-run of `/ll:decide-issue FEAT-389 --auto` against that
repo would now fall through, match the bullet options + `(b)` / `(a)+(b)`
recommendations, and annotate them automatically.

## Session Log
- `hook:posttooluse-status-done` - 2026-06-30T16:28:26 - `48e542db-1351-4e66-8bb9-bed31b91d611.jsonl`
- `/ll:decide-issue (design-gap fix)` - 2026-06-30T16:27:54Z - manual session
