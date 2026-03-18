---
discovered_date: 2026-03-17T00:00:00Z
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 61
---

# ENH-800: TDD mode lacks explicit skip for documentation-only issues

## Summary

`manage-issue` Phase 3a (Write Tests — Red) has no documented escape hatch for issues where testing is not applicable, such as documentation-only changes. The skip condition only checks `action=verify` or `action=plan`, leaving issues with `Tests: N/A` relying on implicit LLM judgment rather than an explicit rule.

## Motivation

When `tdd_mode: true` is set, running `manage-issue` on a documentation-only issue like ENH-795 causes Phase 3a to attempt writing failing tests against acceptance criteria such as "broken anchor corrected" or "all 10 issues resolved" — which have no meaningful unit test representation. The skill will either produce trivial/unreliable tests (e.g., `grep` for anchor text) or get stuck trying to satisfy the Red phase requirement. An explicit, documented mechanism is needed so agents don't have to reason their way around this gap.

## Proposed Solution

Add a `testable: false` frontmatter field to issue files that signals Phase 3a should be skipped entirely. Update the Phase 3a skip condition in `manage-issue` SKILL.md to check this field alongside the existing `action` checks.

**Mechanism decision**: Use the frontmatter field approach. Multiple skills (`format-issue`, `confidence-check`, `issue-size-review`) and `docs/reference/ISSUE_TEMPLATE.md` already reference a `testable` field, so this is already part of the intended schema. The `Tests: N/A` in the Integration Map `### Tests` section is unreliable freeform prose — the skill has zero logic to parse it.

**Implementation pattern to follow**: Phase 2.5 confidence gate at `skills/manage-issue/SKILL.md:154-186` — this is the canonical pattern for "read issue frontmatter field, branch on its value, log a structured message, skip phase." The `testable: false` handling should follow this exact structure.

## Implementation Steps

1. Update `skills/manage-issue/SKILL.md:192` — extend the Phase 3a skip condition to: `config.commands.tdd_mode` is `false`, OR action is `verify` or `plan`, OR issue frontmatter `testable: false`. Add a pseudocode block (modeled after the confidence gate at lines 154-186) that reads `testable` from frontmatter and logs `"⏭ Phase 3a skipped: testable: false in issue frontmatter"`.
2. Update `skills/manage-issue/templates.md:130-132` — add a note to the plan template's Phase 0 section: skip if `testable: false` in issue frontmatter.
3. Update `skills/capture-issue/templates.md:134-138` — the minimal frontmatter template emitted by capture-issue; decide whether to include `testable: true` by default (only for non-doc issues) or leave it absent (absent = testable).
4. Update `docs/reference/ISSUE_TEMPLATE.md` — document `testable: false` as a recognized frontmatter field.
5. Update `docs/reference/CONFIGURATION.md:278-282` — add to the `tdd_mode` description that per-issue `testable: false` overrides the phase for that issue.
6. Confirm `config-schema.json` does not need changes — `testable` is an issue-file field, not a config field (same as `confidence_score`).

## API/Interface

- **Issue frontmatter** (if frontmatter approach): `testable: false` — skips Phase 3a when `tdd_mode: true`
- **SKILL.md Phase 3a skip condition**: extended to include `testable: false` check

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md:192` — Phase 3a skip condition (add `testable: false` frontmatter check with pseudocode block)
- `skills/manage-issue/templates.md:130-132` — plan template Phase 0 note (add `testable: false` skip signal)
- `skills/capture-issue/templates.md:134-138` — minimal frontmatter template (decide `testable` default)
- `docs/reference/ISSUE_TEMPLATE.md` — document `testable: false` field
- `docs/reference/CONFIGURATION.md:278-282` — `tdd_mode` entry (add per-issue override note)

### Dependent Files (Callers/Importers)
- `skills/format-issue/SKILL.md` — already references `testable` field; no change needed but verify alignment
- `skills/confidence-check/SKILL.md` — already references `testable` field; verify alignment
- `skills/issue-size-review/SKILL.md` — already references `testable` field; verify alignment

### Similar Patterns
- **Canonical pattern**: Phase 2.5 confidence gate at `skills/manage-issue/SKILL.md:154-186` — exact model for "read frontmatter field → conditional skip + structured log message"
- Phase 3a current skip condition at `skills/manage-issue/SKILL.md:192`
- `config-schema.json:295-298` — `tdd_mode` schema (for reference; `testable` is NOT a config field)

### Tests
- N/A — documentation/skill-prompt change only

### Documentation
- `docs/reference/CONFIGURATION.md:278-282` — `tdd_mode` entry
- `docs/reference/ISSUE_TEMPLATE.md` — `testable` field definition

### Configuration
- N/A — `testable` is an issue-file frontmatter field, not a config field (same as `confidence_score`)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-03-17_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 61/100 → MODERATE

### Concerns
- One design decision deferred to implementation: whether `capture-issue/templates.md` should emit `testable: true` by default for non-doc issues, or treat absence as testable. Either is valid but the rule needs to be explicit.

### Outcome Risk Factors
- Zero automated test coverage — all changes are markdown prompt files. Behavioral correctness requires a manual smoke test: invoke `manage-issue` with `tdd_mode: true` on a doc-only issue and verify Phase 3a is skipped.

## Session Log
- `/ll:confidence-check` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73090a87-0698-4eeb-9d27-83936dec2511.jsonl`
- `/ll:refine-issue` - 2026-03-18T02:15:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a56e6201-d603-4920-9c45-b18975f046e7.jsonl`
- `/ll:capture-issue` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b46a31d3-3cc1-4027-98da-b1787e431d19.jsonl`
