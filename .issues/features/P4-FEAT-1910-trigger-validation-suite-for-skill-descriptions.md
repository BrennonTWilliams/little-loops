---
id: FEAT-1910
title: Trigger-validation suite for skill descriptions (should-fire / should-not-fire)
type: FEAT
priority: P4
status: in_progress
captured_at: '2026-06-03T20:59:38Z'
discovered_date: 2026-06-03
discovered_by: capture-issue
---

# FEAT-1910: Trigger-validation suite for skill descriptions (should-fire / should-not-fire)

## Summary

Add tooling — an `ll-verify-triggers` CLI and/or a built-in FSM loop — that empirically
validates whether each skill's `description` field fires correctly: it should trigger on a
set of realistic should-fire phrasings and stay silent on a set of near-miss should-NOT-fire
phrasings. Report per-skill precision/recall and exit non-zero when a description collides
with another skill's trigger space. This is the one genuine capability gap surfaced by a
review of the `revfactory/harness` plugin (its Phase 6-4 "Trigger Validation"): little-loops
generates and budgets descriptions but never tests that they actually fire as intended.

## Current Behavior

little-loops provides ~70 `/ll:*` skills sharing a dense keyword space. Existing verifier
tooling covers description generation and static constraints, but not trigger semantics:
- `ll-generate-skill-descriptions` extracts `trigger keywords:` and writes ≤100-char descriptions
  but never tests whether they fire or false-fire.
- `ll-verify-skill-budget` checks token footprint against the listing budget.
- `ll-verify-skills` enforces the 500-line SKILL.md cap.

Trigger collisions (two skills firing on the same phrasing) and silent misfires (a skill failing
to fire on a natural rephrase) go undetected.

## Expected Behavior

A new `ll-verify-triggers` CLI validates each skill's description against a set of
should-fire and should-NOT-fire phrasings. Running `ll-verify-triggers` (locally or in CI):
- Reports per-skill precision/recall
- Emits a cross-skill collision matrix
- Exits 1 when any skill falls below threshold or collides with another skill

The check integrates into CI alongside `ll-verify-skill-budget` and `ll-verify-skills`.

## Motivation

little-loops has ~70 `/ll:*` skills sharing a dense keyword space. Existing tooling only
covers *generation* and *budget*, never *firing correctness*:
- `ll-generate-skill-descriptions` extracts `trigger keywords:` and writes ≤100-char
  descriptions, but never checks whether they fire or false-fire.
- `ll-verify-skill-budget` checks token footprint against the listing budget.
- `ll-verify-skills` enforces the 500-line SKILL.md cap.
- `plugin-config-auditor` / `consistency-checker` audit frontmatter quality and
  cross-references, not trigger semantics.

**Why:** With that many skills in one namespace, trigger collisions (two skills plausibly
firing on the same phrasing, or a skill silently failing to fire on a natural rephrase) are a
live risk that nothing currently detects. ENH-493 (`done`) and ENH-1370 (`done`) shaped
description *content*; neither tests *behavior*.
**How to apply:** Treat this as a measurement harness, not a content rewriter. It reports
precision/recall and flags collisions; fixing descriptions stays a human/`improve-claude-md`
decision.

## Use Case

A maintainer adds a new skill whose description overlaps an existing one. Running
`ll-verify-triggers` (locally or in CI) reports that 3 of the new skill's should-fire phrasings
also match an existing skill (collision) and that 2 should-NOT phrasings false-fire. The
maintainer tightens the description and re-runs until precision/recall clear the threshold.

## Acceptance Criteria

- [ ] `ll-verify-triggers` CLI exists; accepts a skill set (default: all `skills/*/SKILL.md` + `commands/*.md`)
- [ ] Each skill can carry a `trigger_fixtures:` block (or sidecar file) with should-fire and should-NOT-fire phrasings
- [ ] Per-skill precision/recall is computed and reported in a table
- [ ] Cross-skill collision matrix is emitted; collisions are reported per-skill-pair
- [ ] Exit code 1 when any skill falls below threshold or has a collision; exit 0 on full pass
- [ ] Primary signal is deterministic (non-LLM), satisfying the MR-1 non-LLM evaluator pairing requirement
- [ ] CI runs `ll-verify-triggers` alongside `ll-verify-skill-budget` and `ll-verify-skills`
- [ ] Tests cover fixture parsing, precision/recall math, collision detection, and exit-code behavior

## API/Interface

- New CLI `ll-verify-triggers`:
  - Input: skill set (default: all `skills/*/SKILL.md` + `commands/*.md` with descriptions);
    each skill optionally carries a `trigger_fixtures:` block (should/should-not phrasings),
    or fixtures live in a sidecar file under the skill dir.
  - Output: per-skill precision/recall table + a collision matrix; exit 1 when any skill
    falls below threshold or collides.
- Optional built-in FSM loop variant that wraps the CLI with an `output_numeric` evaluator
  (precision/recall as the measured signal) so it satisfies the meta-loop "non-LLM evaluator
  required" rule (CLAUDE.md § Loop Authoring, MR-1).

## Implementation Steps

1. Define a fixture format: per skill, ~8–10 should-fire and ~8–10 near-miss should-NOT-fire
   phrasings (formal/casual, explicit/implicit), authored once and stored beside the skill.
2. Build the matcher: score each phrasing against all skill descriptions (reuse the same
   trigger/keyword model `ll-generate-skill-descriptions` relies on; decide LLM-judge vs.
   deterministic keyword match — prefer deterministic for the non-LLM evaluator pairing).
3. Compute precision/recall per skill and a cross-skill collision matrix.
4. Emit a report; exit 1 on threshold miss or collision.
5. Optionally wrap in an FSM loop with `output_numeric` so it runs under `ll-loop`.
6. Wire into CI alongside `ll-verify-skill-budget` / `ll-verify-skills`.

## Open Questions

1. **Deterministic vs. LLM judge for "did it fire?"** Deterministic keyword matching is
   cheaper and gives a clean non-LLM evaluator; an LLM judge is more faithful to real routing
   but mis-grades (~33–55% per CLAUDE.md) and would itself need pairing. Likely: deterministic
   primary signal, optional LLM cross-check.
2. **Fixture authoring burden.** ~16–20 phrasings × ~70 skills is a lot. Bootstrap fixtures
   from existing `trigger keywords:` lines and user message history, then curate.
3. **CLI vs. loop vs. both.** CLI is the CI primitive; the loop is the iterate-until-clean
   wrapper. Start with the CLI.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/verify_triggers.py` (new) + `pyproject.toml` entry-point
- `scripts/tests/test_verify_triggers.py` (new)
- `.claude/CLAUDE.md` § CLI Tools — add `ll-verify-triggers` to the list
- CI config — add the check next to `ll-verify-skill-budget` / `ll-verify-skills`
- `scripts/little_loops/loops/verify-triggers.yaml` (optional, if the loop variant lands)

### Similar Patterns
- `scripts/little_loops/cli/generate_skill_descriptions.py` — trigger-keyword extraction model to reuse
- `ll-verify-skill-budget` / `ll-verify-skills` — sibling CI verifiers (exit-1 discipline)
- `agents/plugin-config-auditor.md` / `agents/consistency-checker.md` — adjacent description/reference audits

### Tests
- `scripts/tests/test_verify_triggers.py` — fixture parsing, precision/recall math, collision detection, exit-code behavior

## Impact

- **Priority**: P3 — Detection capability gap; not blocking in-flight work but a live CI blind spot as the skill namespace grows.
- **Effort**: Medium — New CLI, fixture format definition, matcher logic, and CI wiring; reuses existing `generate_skill_descriptions.py` keyword extraction.
- **Risk**: Low — Additive new tooling; no changes to existing skill descriptions or CLI infrastructure.
- **Breaking Change**: No

## Labels

`feature`, `verification`, `ci`, `skills`

## Provenance

Surfaced while reviewing `https://github.com/revfactory/harness` for ideas applicable to
little-loops. Harness's Phase 6-4 validates each skill against 8–10 should-trigger and 8–10
should-NOT-trigger (near-miss) queries; this issue ports that discipline into a measurable,
CI-enforceable check that fits little-loops' non-LLM-evaluator philosophy.


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Session Log
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:format-issue` - 2026-06-03T21:04:12 - `b62e3f92-2664-4793-81e7-cf8464c74fe6.jsonl`
- `/ll:capture-issue` - 2026-06-03T20:59:38Z - `b4fa1e68-4a59-49bd-949a-5a5b7533509f.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-06-03
