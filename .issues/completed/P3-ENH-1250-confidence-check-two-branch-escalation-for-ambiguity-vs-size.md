---
captured_at: "2026-04-22T15:44:47Z"
completed_at: 2026-04-22T16:48:03Z
discovered_date: 2026-04-22
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 75
score_complexity: 25
score_test_coverage: 0
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1250: confidence-check two-branch escalation for ambiguity vs size

## Summary

The `confidence-check` escalation section currently only suggests `/ll:issue-size-review` when readiness score is persistently low after multiple refinement passes. It should instead branch on the *reason* for the low score: a low Criterion C (Ambiguity) score signals unresolved competing options (`decision_needed: true`) and should route to `/ll:decide-issue`; a persistent broad readiness gap signals the issue is too large and should route to `/ll:issue-size-review`.

## Current Behavior

The `confidence-check` skill's `### Escalation` subsection always suggests `/ll:issue-size-review` when readiness score < 70 after 2+ prior refinement passes, regardless of *why* the score is low. No distinction is made between a low ambiguity score (unresolved competing options) and a broad readiness gap (issue too large).

## Expected Behavior

When readiness score < 70 after 2+ prior refinement passes, escalation branches on `score_ambiguity`:
- **score_ambiguity ≤ 10**: suggest `/ll:decide-issue` — competing options are blocking readiness
- **score_ambiguity > 10**: suggest `/ll:issue-size-review` — issue is too large or under-researched

## Motivation

A low Criterion C score means "multiple competing options unresolved" — this is exactly the condition `decide-issue` was built to fix. Pointing that case to `issue-size-review` instead is incorrect: it would prompt decomposition of an issue that just needs an option selected. The current single-path escalation can send users down the wrong branch.

## Proposed Solution

In `skills/confidence-check/SKILL.md`, update the `### Escalation` subsection of the output format (currently at ~line 563). Replace the single escalation bullet with a two-branch conditional:

```markdown
### Escalation (if readiness score < 70 after 2+ prior refinement passes)

- **Unresolved options (score_ambiguity ≤ 10)**: Run `/ll:decide-issue [ISSUE_ID]` — competing implementation options are blocking readiness; selecting one clears the ambiguity.
- **Issue too large (score_ambiguity > 10)**: Run `/ll:issue-size-review [ISSUE_ID]` — a persistent broad readiness gap after multiple refinement passes often signals the issue needs decomposition rather than more research.
```

The threshold `score_ambiguity ≤ 10` (out of 25) maps to the bottom two scoring tiers ("Several design decisions left open" or "Fundamental approach unclear"), which are the cases `decide-issue` is designed to resolve.

## Acceptance Criteria

- [x] `confidence-check` output includes the two-branch escalation when readiness score < 70 after 2+ passes
- [x] The branch condition uses `score_ambiguity` (Criterion C raw score, 0–25) as the discriminator
- [x] The ambiguity branch suggests `/ll:decide-issue`, not `issue-size-review`
- [x] The size branch retains the existing `issue-size-review` suggestion
- [x] Existing escalation behavior for issues with no ambiguity problem is unchanged

## Files to Modify

- `skills/confidence-check/SKILL.md` — update `### Escalation` subsection (lines 562-563) in the Output Format section
- `skills/issue-workflow/SKILL.md` — update the "Stuck on readiness?" blockquote (line 82) with the same two-branch logic

## Out of Scope

- Automatically invoking `decide-issue` from within `confidence-check`
- Changes to `decide-issue` itself
- Changes to `issue-size-review` itself — note: `skills/issue-size-review/SKILL.md:26-27` says it activates when "An issue fails /ll:confidence-check after two or more refinement passes", which is still broadly true (the size branch still routes there). A follow-up issue could tighten this to say "confidence-check routes here only for the size branch (score_ambiguity > 10)".

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md:562-563` — replace the single `### Escalation` bullet with the two-branch conditional
- `skills/issue-workflow/SKILL.md:82` — replace the single-branch blockquote with a two-branch version

### Dependent Files (Callers/Importers)
- `skills/issue-size-review/SKILL.md:26-27` — references confidence-check as a trigger; not modified but the two-branch change remains compatible with its wording
- `skills/manage-issue/SKILL.md:118-129` — uses the same bold-label two-branch bullet format (`**Score >=70**` / `**Score <70**`); use as the formatting reference

### Similar Patterns
- `skills/manage-issue/SKILL.md:118-129` — bold-label two-branch routing: `**Condition**: Run \`/ll:command\` — rationale`
- `skills/wire-issue/SKILL.md:441-443` — NEXT STEPS that already mentions both `issue-size-review` and `decide-issue` as separate conditional bullets

### Tests
- No automated tests for skill markdown files; acceptance criteria verified manually by running `/ll:confidence-check` on a low-ambiguity issue and a low-readiness issue

### Documentation
- `skills/issue-workflow/SKILL.md:82` — blockquote escalation hint; update in-scope per user decision

## Implementation Steps

1. Edit `skills/confidence-check/SKILL.md:562-563` — replace the single `### Escalation` bullet with the two-branch conditional from Proposed Solution
2. Edit `skills/issue-workflow/SKILL.md:82` — replace the single-branch blockquote with a two-branch version matching the same logic (ambiguity branch → `/ll:decide-issue`, size branch → `/ll:issue-size-review`)
3. Verify: run `/ll:confidence-check` on a sample issue with `score_ambiguity ≤ 10` and confirm output recommends `decide-issue`; run on an issue with `score_ambiguity > 10` and confirm output recommends `issue-size-review`

## Impact

- **Priority**: P3 - Low urgency; affects routing guidance only, not blocking any workflow
- **Effort**: Small - Two markdown file edits (~4 lines total)
- **Risk**: Low - Markdown-only changes to skill files; no code execution affected
- **Breaking Change**: No

## Labels

`enhancement`, `confidence-check`, `skill`, `escalation`, `ux`

## Resolution

Updated `skills/confidence-check/SKILL.md` (line 562) and `skills/issue-workflow/SKILL.md` (line 82) to replace the single-path escalation bullet with a two-branch conditional:
- `score_ambiguity ≤ 10` → `/ll:decide-issue` (competing options blocking readiness)
- `score_ambiguity > 10` → `/ll:issue-size-review` (issue too large or under-researched)

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-22T16:48:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75e3083b-5a97-4782-887e-1f6d865ffbb8.jsonl`
- `/ll:ready-issue` - 2026-04-22T16:40:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f15ef2af-4066-4740-9504-59ffa39d4d28.jsonl`
- `/ll:confidence-check` - 2026-04-22T17:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0466ea16-3c78-4f5e-9d5b-d2d5e540cdea.jsonl`
- `/ll:verify-issues` - 2026-04-22T16:18:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d65bdd0-fed7-4e46-b7c0-85e3adfa65b9.jsonl`
- `/ll:refine-issue` - 2026-04-22T16:17:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00afba49-6592-47d2-b395-66cdb26ec47d.jsonl`
- `/ll:capture-issue` - 2026-04-22T15:44:47Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff12b2b-2ed2-40bc-9248-ba889878465e.jsonl`

---
## Status

**Open** | Created: 2026-04-22 | Priority: P3
