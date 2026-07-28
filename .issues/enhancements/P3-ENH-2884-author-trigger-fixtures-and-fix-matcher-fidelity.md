---
id: ENH-2884
title: Author trigger_fixtures for model-invocable skills (blocked on matcher fidelity)
type: ENH
priority: P3
status: done
captured_at: '2026-07-28T00:00:00Z'
completed_at: '2026-07-28T03:42:26Z'
discovered_date: 2026-07-28
labels:
- skills
- verification
relates_to:
- BUG-2879
- FEAT-1910
decision_needed: false
confidence_score: 92
outcome_confidence: 73
score_complexity: 13
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 20
---

# ENH-2884: Author trigger_fixtures for model-invocable skills

## Summary

BUG-2879 Part 1 fixed the reporting contract of `ll-verify-triggers`: unmeasured
skills no longer fail the gate, and coverage now reads `0/19 model-invocable
skill(s) declare trigger_fixtures`. This issue is BUG-2879's **Part 2** — closing
that coverage gap.

Part 2 was deliberately split out because a pilot showed it cannot land as pure
data entry: the current matcher makes realistic phrasings collide across 3–6
skills, so authoring fixtures today would flip the gate back to exit 1 for
*matcher* reasons rather than description defects — reintroducing the exact
"failing on the wrong thing" problem BUG-2879 fixed.

## Current Behavior

`_match_phrasing()` (`scripts/little_loops/cli/verify_triggers.py`) returns True
when a phrasing shares **any single token** with a skill's keyword set.
`_detect_collisions()` flags any phrasing matching more than one skill. Measured
on the current tree with the 19 model-invocable skills:

```
"generate a verification loop from FEAT-100"
  -> adversarial-verify-loop, create-eval-from-issues, create-loop, verify-issue-loop
"create an automation loop for this recurring task"
  -> adversarial-verify-loop, capture-issue, create-eval-from-issues, create-loop,
     verify-issue-loop, workflow-automation-proposer
"make an eval harness from these issues"
  -> audit-issue-conflicts, create-eval-from-issues, scope-epic
```

Every one of those is a legitimate should-fire phrasing for exactly one skill, and
every one registers as a collision.

## Expected Behavior

- The 19 model-invocable skills declare `trigger_fixtures`; coverage reads `19/19`.
- `ll-verify-triggers` exits 0 with real measurements, and collisions it reports
  correspond to genuinely ambiguous descriptions.

## Proposed Solution

Two parts, in order; the second is the data entry.

**1 — Matcher fidelity (decision needed).** Single-token OR matching is too coarse
to model host skill routing. Options to evaluate:

> **Selected:** Option A — score-based best-match, since it models actual host
> routing (one skill wins) and gives the already-implemented `_match_score()`
> its first caller, fixing the root cause instead of masking the symptom.

- **A**: score-based best-match — a phrasing "fires" the skill with the highest
  `_match_score()` (already implemented but currently unused), with collisions
  reported only on ties or near-ties.
- **B**: require a minimum token overlap (e.g. ≥2 tokens, or a normalized
  Jaccard threshold) before counting a match.
- **C**: keep OR-matching but treat collisions as a warning rather than an
  exit-code failure, since precision/recall already penalizes cross-firing via
  `should_not_fire` fixtures.

### Decision Rationale

**Selected: Option A — score-based best-match**

A host resolves a phrasing to exactly one skill (the best match), not to every
skill sharing a token — OR-matching (the current behavior) structurally cannot
model that, which is exactly why legitimate single-skill phrasings register as
collisions across 3–6 skills today. Best-match scoring fixes this at the root:
a phrasing only counts as ambiguous when two or more skills are genuinely close
in score (tie/near-tie), which is a real collision, not a matcher artifact.
`_match_score()` already exists in `verify_triggers.py` and is unused — Option
A gives it its first caller instead of adding new matching machinery.

Option B (minimum token overlap) raises the bar but doesn't change the
matching *shape* — multiple skills can still simultaneously clear a fixed
threshold, so it reduces false-collision volume without eliminating the
underlying OR-semantics mismatch. Option C doesn't touch the matcher at all;
it downgrades collisions to non-fatal, which would silently reopen the exact
"failing on the wrong thing" gap BUG-2879 Part 1 closed for the coverage
metric — now for the collision metric instead.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:------------:|:----:|:-----:|
| A — score-based best-match | 3 | 3 | 3 | 2 | 11/12 |
| B — min token overlap | 1 | 2 | 2 | 2 | 7/12 |
| C — warning-only collisions | 0 | 3 | 2 | 1 | 6/12 |

Key evidence: `_match_score()` (`scripts/little_loops/cli/verify_triggers.py:219`)
is already implemented and currently has zero callers outside its own
definition (confirmed via grep across `scripts/`) — Option A is additive
wiring of existing logic, not new matching code.

**2 — Author fixtures.** Once the matcher discriminates, populate `should_fire` /
`should_not_fire` for the 19 model-invocable skills, prioritizing the clusters the
pilot showed as most entangled: the loop cluster (`create-loop`,
`verify-issue-loop`, `adversarial-verify-loop`, `create-eval-from-issues`) and the
issue cluster (`capture-issue`, `format-issue`, `wire-issue`, `decide-issue`,
`confidence-check`, `go-no-go`).

Note `_match_score()` already exists and is currently dead code — Option A would
give it its first caller.

## Integration Map

- `scripts/little_loops/cli/verify_triggers.py` — `_match_phrasing()`,
  `_match_score()`, `_detect_collisions()`, `_run_validation()`.
- `skills/*/SKILL.md` — where `trigger_fixtures` blocks land. `commands/*.md` are
  never scanned; fixtures placed there are silently ignored.
- `scripts/tests/test_verify_triggers.py` — matcher-fidelity cases.
- `docs/reference/CLI.md` — `### ll-verify-triggers` matching semantics.

## Impact

- **Severity**: Low — the gate is honest today; it just measures nothing.
- **Blast radius**: `ll-verify-triggers`, `ll-doctor --full`, and any judgement
  about skill-description routing quality (see the ENH-2877 skill-merge audit,
  which had to discount the collision result).

## Status

done

## Resolution

Implemented both parts in order:

1. **Matcher fidelity (Option A)** — `_run_validation` now routes each phrasing
   through `_best_match_skills()`, a new best-match-with-ties helper built on
   the previously-unused `_match_score()`. A phrasing "fires" the skill(s)
   tied for the highest keyword-overlap score instead of every skill sharing
   any single token; collisions are reported only on genuine ties.
2. **Author fixtures** — all 19 model-invocable skills now declare
   `trigger_fixtures` (should_fire/should_not_fire), added as minimal-diff
   YAML block insertions preserving each file's existing frontmatter
   formatting. `ll-verify-triggers` now reports `19/19` coverage, 100%
   precision/recall across all skills, and zero cross-skill collisions
   (previously 0/19 measured).

`docs/reference/CLI.md`'s `ll-verify-triggers` section documents the new
best-match/tie semantics. Added `TestBestMatchSkills` unit tests covering
single-winner, no-match, tie, and higher-overlap-beats-single-token cases.

## Session Log
- `/ll:manage-issue` - 2026-07-28T03:41:47 - `ffff124d-ab55-48a5-a2ee-bf8728cd9689.jsonl`
- `/ll:ready-issue` - 2026-07-28T03:30:13 - `ef4bae00-05f4-4fac-9309-3d453d3e0ff8.jsonl`
- `/ll:decide-issue` - 2026-07-28T03:28:07 - `b7374718-5a39-4391-b072-e0b4f5bcea35.jsonl`
