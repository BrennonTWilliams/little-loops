---
id: ENH-2884
title: "Author trigger_fixtures for model-invocable skills (blocked on matcher fidelity)"
type: ENH
priority: P3
status: open
captured_at: '2026-07-28T00:00:00Z'
discovered_date: 2026-07-28
labels:
- skills
- verification
relates_to:
- BUG-2879
- FEAT-1910
decision_needed: true
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

- **A**: score-based best-match — a phrasing "fires" the skill with the highest
  `_match_score()` (already implemented but currently unused), with collisions
  reported only on ties or near-ties.
- **B**: require a minimum token overlap (e.g. ≥2 tokens, or a normalized
  Jaccard threshold) before counting a match.
- **C**: keep OR-matching but treat collisions as a warning rather than an
  exit-code failure, since precision/recall already penalizes cross-firing via
  `should_not_fire` fixtures.

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

open
