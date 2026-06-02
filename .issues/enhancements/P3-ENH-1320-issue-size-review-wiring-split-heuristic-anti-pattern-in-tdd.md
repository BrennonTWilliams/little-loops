---
captured_at: '2026-05-02T15:14:39Z'
completed_at: '2026-05-02T16:05:50Z'
discovered_date: '2026-05-02'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
---

# ENH-1320: Fix issue-size-review wiring split heuristic for TDD projects

## Summary

The `/ll:issue-size-review` skill frequently suggests splitting wiring (integration points) into a separate issue as a size-reduction strategy. In TDD projects this is an anti-pattern: wiring IS part of the implementation cycle because the integration test that drives the wiring must be written alongside the feature, not deferred to a follow-up issue.

## Current Behavior

`/ll:issue-size-review` flags issues that include wiring work alongside core implementation and recommends creating a separate "wiring" issue. Example output:

> "Consider splitting into: (1) core implementation, (2) wiring + docs"

## Expected Behavior

The skill should recognize that in TDD workflows, wiring belongs in the same issue as implementation because:
1. Integration tests that exercise wired behavior are part of the TDD cycle
2. Splitting wiring creates orphaned implementations that can only be tested with mocks — risking mock/prod divergence
3. Docs separation is acceptable; wiring separation is not

The skill should only suggest splitting wiring when it involves a genuinely independent subsystem (e.g., a new transport protocol, a new storage backend) that is separately testable on its own merits.

## Motivation

Splitting wiring from implementation creates artificial issue boundaries that undermine TDD's fast-feedback guarantee. The first issue passes with mock-based tests; the second wires it up; only then does the design get validated end-to-end. This defers feedback to exactly the wrong time. Doc-split suggestions remain appropriate and unaffected.

## Proposed Solution

Update the heuristic in `skills/issue-size-review/SKILL.md` (and any associated logic) to:
- **Keep**: suggest separating docs into a follow-up issue
- **Change**: only suggest separating wiring if the wiring target is a genuinely independent, separately-testable subsystem
- **Add**: a TDD-awareness note in the heuristic rationale — if the project uses TDD, wiring + tests + implementation belong together

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The skill currently has no explicit wiring-split rule.** Search of `skills/issue-size-review/SKILL.md` confirms the only `/ll:wire-issue` mention is in the Phase 5 qualitative-skip guard, which routes *away* from decomposition (the opposite of a wiring-split recommendation). When the skill produces wiring-split proposals, they emerge from generic sub-task analysis in **Phase 4 step 1** ("Identify distinct sub-tasks or concerns by analyzing... Separate sections in 'Proposed Solution'... Different files/components mentioned"), not from a named rule.
- **Fix point is Phase 4 step 2** — alongside the existing "Never split by artifact type" rule (which already protects tests and docs for newly-introduced behavior). The new TDD-aware rule should be a sibling bullet in that same block.
- **TDD detection mechanism is already established**: `config.commands.tdd_mode` (boolean, default `false`) is read by `skills/manage-issue/SKILL.md` Phase 3a. The pattern is `**Skip this phase if**: config.commands.tdd_mode is false (default)...`. The wiring-split heuristic should use the same config key — no new config introduced. This project has `tdd_mode: true` in `.ll/ll-config.json`.
- **Term-of-art language to reuse**: `"independently shippable"` (with parenthetical "could produce its own PR with tests for whatever it introduces") is the established phrase for what qualifies for splitting. `"tightly coupled scope"` and `"shared infrastructure"` describe what should NOT be split. The new rule should use these existing terms instead of introducing new vocabulary.
- **Existing "bad split" example in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`** (line 370) already names a wiring child as the bad child (`FEAT-A: wire decide-issue pipeline`), but the rationale only blames the tests/docs sibling. The doc needs to be updated to also explain *why FEAT-A on its own is problematic in TDD projects*, not just FEAT-B.

## Scope Boundaries

**In scope:**
- Wiring-split heuristic within `skills/issue-size-review/SKILL.md`

**Out of scope:**
- Docs-split recommendations — preserved as-is
- Changes to any other skill (e.g., `wire-issue`, `manage-issue`, `confidence-check`)
- Python runtime code, CLI tools, or FSM framework changes
- Retroactively updating issues that were previously split using the old heuristic
- TDD detection or awareness in any skill other than `issue-size-review`

## Integration Map

### Files to Modify
- `skills/issue-size-review/SKILL.md` — add TDD-aware sibling rule under **Phase 4: Decomposition Proposal, step 2** alongside the existing "Never split by artifact type" bullet; mirror the same prose structure. Also add a corresponding entry in `## Best Practices → ### Avoid` matching the existing "Splitting tests or documentation into a dedicated child issue..." bullet.

### Dependent Files (Callers/Importers)
- N/A — heuristic prose is inline in the skill; no shared module, helper, or runtime caller. The skill is invoked by `commands/ll:issue-size-review` (and referenced by `commands/ll:create-sprint`), but neither caller depends on heuristic internals.

### Similar Patterns
- `skills/issue-size-review/SKILL.md` → **Phase 4 step 2** "Never split by artifact type" — the *direct prose template* for the new wiring rule (same block, same paragraph style)
- `skills/issue-size-review/SKILL.md` → **Phase 4 step 4** "Ordering dependency analysis" — pattern for `If [condition] AND [second condition], add recommendation: \`[exact text]\`. Present as [role] but do not [block action].`
- `skills/manage-issue/SKILL.md` → **Phase 3a: Write Tests — Red (TDD Mode)** — established `config.commands.tdd_mode` config-read pattern (`**Skip this phase if**: config.commands.tdd_mode is false (default)...`)
- `skills/issue-size-review/SKILL.md` → **Phase 5 qualitative-skip guard** — pattern for a named guard with explicit scope, condition check, canonical emit, and absence-of-fields fallthrough

### Tests
- `scripts/tests/test_issue_size_review_skill.py` — add a new class `TestIssueSizeReviewWiringTddGuard` modeled after the existing `TestIssueSizeReviewQualitativeGuard`. Use the same read-and-assert-on-skill-text pattern: read `SKILL_FILE.read_text()`, slice with `content.index("### Phase 4: Decomposition Proposal")` + `content.find("\n### Phase 5", phase4_start)`, assert the new rule text and `tdd_mode` reference are present in Phase 4, and assert (negative) the rule does not bleed into Check Mode or Phase 3.
- Use `SKILL_FILE = PROJECT_ROOT / "skills" / "issue-size-review" / "SKILL.md"` (already defined at module scope).

### Documentation
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` (~lines 358-370) — update the "Bad split" example rationale to explain *why a wiring-only child is problematic in TDD projects* (currently the rationale only blames the tests/docs sibling). Reference `config.commands.tdd_mode` so readers know it is project-configurable.
- `docs/reference/COMMANDS.md` (~lines 256-271) — append a one-line note to the `/ll:issue-size-review` description that the skill respects `config.commands.tdd_mode` when proposing decomposition.

### Configuration
- `config.commands.tdd_mode` — existing key (`config-schema.json` ~line 377; default `false`). No new config keys are needed; reuse this switch.

## Implementation Steps

1. **Locate target block** — Open `skills/issue-size-review/SKILL.md` and locate **Phase 4: Decomposition Proposal, step 2**, specifically the bullet block containing `**Never split by artifact type**: tests and docs for a child's new behavior belong in that child...`.
2. **Add TDD-aware wiring sibling bullet** — Insert a new bullet immediately after "Never split by artifact type" using the same prose structure. Suggested wording:
   > **Never split wiring from implementation when TDD mode is configured**: If `config.commands.tdd_mode` is `true`, wiring (integration points, callers, registration hooks) belongs in the same child as the implementation that introduces it — the integration test that drives the wiring is part of the TDD cycle. The only exception: wiring into a genuinely independent, separately-testable subsystem (e.g., a new transport protocol or storage backend) that qualifies as **independently shippable** on its own.
3. **Update Best Practices → Avoid** — In `## Best Practices → ### Avoid`, add a sibling bullet to the existing "Splitting tests or documentation..." entry:
   > **Splitting wiring from the implementation that introduces it when `config.commands.tdd_mode` is `true`** — wiring is part of the TDD cycle; the integration test belongs with the wired feature, not in a follow-up issue.
4. **Add tests** — In `scripts/tests/test_issue_size_review_skill.py`, add `TestIssueSizeReviewWiringTddGuard` modeled after `TestIssueSizeReviewQualitativeGuard`:
   - `_phase4_text()` helper slicing from `### Phase 4: Decomposition Proposal` to `\n### Phase 5`
   - `test_wiring_tdd_rule_in_phase_4` — assert the new bullet text + `tdd_mode` reference present
   - `test_wiring_tdd_rule_not_in_check_mode` — negative assertion that the rule does not appear in `#### Check Mode Behavior`
   - `test_independently_shippable_exception_present` — assert the "independently shippable" escape hatch wording is present
5. **Update docs** — In `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` (~lines 358-370), expand the "Bad split" rationale to call out that `FEAT-A: wire decide-issue pipeline` is *itself* problematic when `tdd_mode` is enabled, not just `FEAT-B`. In `docs/reference/COMMANDS.md` (~lines 256-271), append a one-line note that the skill respects `config.commands.tdd_mode`.
6. **Verify docs-split is unchanged** — Confirm the existing "Never split by artifact type" rule still applies unconditionally (no `tdd_mode` predicate) and the docs-split avoidance bullet is untouched.
7. **Run tests** — `python -m pytest scripts/tests/test_issue_size_review_skill.py -v`

## Impact

- **Priority**: P3 - Guidance anti-pattern that subtly undermines TDD discipline on every size review
- **Effort**: Small - Single skill file edit with targeted heuristic refinement
- **Risk**: Low - No runtime code; skill prompt change only
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `skills`, `issue-size-review`, `tdd`, `captured`

---

## Status

**Completed** | Created: 2026-05-02 | Completed: 2026-05-02 | Priority: P3

## Resolution

- **Status**: Completed
- **Completed**: 2026-05-02
- **Approach**: Added a TDD-aware sibling rule under Phase 4 step 2 of `skills/issue-size-review/SKILL.md` ("Never split wiring from implementation when TDD mode is configured") alongside the existing "Never split by artifact type" rule, plus a matching entry in Best Practices → Avoid. Updated the "Bad split" rationale in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` to explain why a wiring-only child is itself problematic under `tdd_mode`, and appended a TDD-awareness note to `/ll:issue-size-review` in `docs/reference/COMMANDS.md`. Added `TestIssueSizeReviewWiringTddGuard` (5 tests) modeled after the existing qualitative-guard tests.

### Files Changed
- `skills/issue-size-review/SKILL.md` — Phase 4 step 2 and Best Practices → Avoid
- `scripts/tests/test_issue_size_review_skill.py` — new `TestIssueSizeReviewWiringTddGuard` class
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — Bad split rationale expanded
- `docs/reference/COMMANDS.md` — `/ll:issue-size-review` description note

### Verification
- `python -m pytest scripts/tests/test_issue_size_review_skill.py -v` — 22 passed
- `ruff check scripts/tests/test_issue_size_review_skill.py` — clean
- Full suite: 5538 passed, 3 pre-existing failures unrelated to this change (verified via `git stash` baseline)

## Session Log
- `/ll:manage-issue` - 2026-05-02T16:05:50Z - `0010190c-509e-453e-bb85-c00575d1e590.jsonl`
- `/ll:ready-issue` - 2026-05-02T16:01:39 - `0ba61d8e-debe-4a2d-a46f-8b2226966482.jsonl`
- `/ll:confidence-check` - 2026-05-02T16:30:00 - `b593866a-d3e5-4a59-9fd9-49e3382dda71.jsonl`
- `/ll:refine-issue` - 2026-05-02T15:55:52 - `fa9d0bba-4725-41a7-ae23-5a56e421a1d3.jsonl`
- `/ll:format-issue` - 2026-05-02T15:17:21 - `0d52d5c5-7c63-4dc9-9749-7c3748e3066a.jsonl`
- `/ll:capture-issue` - 2026-05-02T15:14:39Z - `19344c8e-9db2-4d37-b7f7-d6bf19e299d8.jsonl`
