---
id: BUG-1278
type: BUG
priority: P3
status: open
discovered_date: 2026-04-24
discovered_by: capture-issue
captured_at: "2026-04-24T21:18:45Z"
related: [BUG-1277]
decision_needed: false
---

# BUG-1278: `confidence-check` Does Not Set `decision_needed: true` When Unresolved Decisions Found

## Summary

`/ll:confidence-check` identifies unresolved design decisions and records them in the "Outcome Risk Factors" prose section, but does not set `decision_needed: true` in the issue frontmatter. The autodev loop's decision gate reads the frontmatter flag — not the notes — so the decision is never surfaced to the loop.

## Current Behavior

When `/ll:confidence-check` detects an unresolved decision (e.g., "whether `_throttle_counts` survives loop resume is flagged as an open decision — resolve before implementing"), it:
1. Records the risk in `## Confidence Check Notes` prose ✓
2. Leaves `decision_needed: false` in the frontmatter ✗

The autodev loop's `decide_current` state (autodev.yaml:184) checks `d.get('decision_needed') == 'true'`. It sees `false` and skips `run_decide`, proceeding directly to implementation or size review.

Observed in: ENH-1115 confidence check, which noted "Persistence decision unresolved" but left `decision_needed: false`.

## Expected Behavior

When `/ll:confidence-check` identifies an unresolved decision that it explicitly flags as needing resolution before implementation, it should set `decision_needed: true` in the issue frontmatter alongside the prose note.

Signal phrases that should trigger the flag:
- "open decision"
- "unresolved decision"
- "resolve before implementing"
- "decision point" (in the context of an unresolved choice)

## Root Cause

The `confidence-check` skill (`skills/confidence-check/SKILL.md`) documents how to compute readiness and outcome scores and write the risk prose, but has no instruction to update `decision_needed` in frontmatter when it surfaces a decision-class risk factor.

## Acceptance Criteria

- When confidence-check notes an unresolved design decision that must be resolved before implementation, it sets `decision_needed: true` in the issue frontmatter
- When no such decision is found, `decision_needed` remains unchanged
- Updated skill instructions tested against ENH-1115 (retrospectively produces `decision_needed: true`)

## Scope Boundaries

- **In scope**: `skills/confidence-check/SKILL.md` instructions; frontmatter update step
- **Out of scope**: How decisions are resolved (`/ll:decide-issue`); other frontmatter fields written by confidence-check

## Implementation Steps

1. In `skills/confidence-check/SKILL.md`, add a post-scoring step: after writing Outcome Risk Factors, scan for decision-class risks; if any are flagged as requiring resolution before implementation, update `decision_needed: true` in frontmatter using `sed` or a Python snippet
2. Document the signal phrases that qualify as decision-class risks
3. Add a note to the skill output indicating when `decision_needed` was flipped

## Impact

- **Priority**: P3 — causes autodev to skip the decision gate for issues that genuinely need it
- **Risk**: Low — only changes frontmatter; no behavioral change to the rest of the skill

## Labels

`bug`, `confidence-check`, `decision-needed`, `skills`

## Status

**Open** | Created: 2026-04-24 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-24T21:18:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82f88b14-6ac1-4d64-a028-6d67f78c0498.jsonl`
