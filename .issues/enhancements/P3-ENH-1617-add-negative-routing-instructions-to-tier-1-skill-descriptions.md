---
id: ENH-1617
title: Add negative routing instructions to Tier 1 skill descriptions
type: ENH
priority: P3
captured_at: '2026-05-22T19:19:39Z'
discovered_date: 2026-05-22
discovered_by: capture-issue
status: open
parent: EPIC-1745
depends_on: [ENH-1618, ENH-1615, FEAT-948]
---

# ENH-1617: Add negative routing instructions to Tier 1 skill descriptions

## Summary

The 14 Tier 1 (LLM-discoverable) skills are all adjacent in the issue lifecycle workflow (e.g., `go-no-go`, `confidence-check`, `decide-issue`, `issue-size-review`, `ready-issue`, `verify-issues`). Without explicit "Do NOT use for X — use Y instead" disambiguation in their descriptions, Claude likely experiences routing collisions when users make ambiguous requests like "review this issue before implementing." The SEO plugin case study found that negative routing instructions reduced misrouting by ~90%.

## Current Behavior

Tier 1 skill descriptions follow the trigger-first convention ("Use when asked to...") but lack negative routing signals. For adjacent skills in the issue pipeline, this means:
- "Should I implement this?" could route to `go-no-go`, `confidence-check`, or `issue-size-review`
- "Help me decide on this issue" could route to `decide-issue`, `go-no-go`, or `ready-issue`
- "Check if this is good" could route to `verify-issues`, `ready-issue`, or `confidence-check`

## Expected Behavior

Each Tier 1 skill description includes explicit disambiguation when it has adjacent neighbors. The pattern from the SEO plugin case study:

```yaml
# Before
description: Use when asked for an adversarial go/no-go review or whether an issue is worth implementing.

# After
description: Use when asked for an adversarial go/no-go review. Do NOT use for confidence checks (use confidence-check) or implementation option selection (use decide-issue).
```

This adds ~20-40 chars per affected description while dramatically improving routing precision.

## Motivation

Adjacent Tier 1 skills share overlapping trigger language, causing routing collisions when users phrase requests ambiguously. The SEO plugin case study found that adding "Do NOT use for X — use Y instead" clauses reduced misrouting by ~90%. Without this, the 14 Tier 1 skill listing wastes resolution capacity on disambiguation that the description layer should handle.

## Proposed Solution

For each of the 14 Tier 1 skills, identify adjacent skills in the issue lifecycle pipeline, then add explicit "Do NOT use for X — use Y instead" clauses to the `description:` field in each `skills/*/SKILL.md`.

**Adjacency clusters to resolve:**
- Pre-implementation gate: `go-no-go` ↔ `confidence-check` ↔ `issue-size-review`
- Decision/selection: `decide-issue` ↔ `go-no-go` ↔ `ready-issue`
- Validation: `verify-issues` ↔ `ready-issue` ↔ `confidence-check`

Each disambiguation adds ~20-40 chars; verify total description stays within budget using `ll-verify-skill-budget` after each update.

**Note**: Complete ENH-1618 first — the audit skill consolidation determines which audit sub-skills remain Tier 1 and need routing disambiguation here.

## Implementation Steps

1. After ENH-1618 resolves, list the final set of Tier 1 skills and their current descriptions
2. Map adjacency clusters (which skills are most likely to be confused for each other)
3. Draft "Do NOT use for X — use Y instead" clauses for each skill in each cluster
4. Update `description:` in each affected `skills/*/SKILL.md`
5. Run `ll-verify-skill-budget` to confirm token budget compliance
6. Spot-check routing with 3-5 ambiguous sample prompts

## Integration Map

### Files to Modify
- `skills/*/SKILL.md` — `description:` field for each of the ~14 Tier 1 skills (exact list determined after ENH-1618)

### Dependent Files (Callers/Importers)
- `ll-verify-skill-budget` — verifies description token budget after edits

### Similar Patterns
- SEO plugin case study (referenced in Summary) — same "Do NOT use for X" pattern

### Tests
- Manual: send 3-5 ambiguous prompts to Claude and verify correct skill routing

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — routing accuracy improvement, no current bug
- **Effort**: Small — update 14 description fields with neighbor disambiguation
- **Risk**: Low — descriptions may need tuning based on observed routing behavior
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `context-engineering`, `routing`

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:format-issue` - 2026-05-24T02:22:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2328e8ba-c60a-43cf-b563-f9a69957b379.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48fbbd10-48f2-4312-a798-ccffa2afa082.jsonl`
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

## Status

**Open** | Created: 2026-05-22 | Priority: P3

---

## Tradeoff Review Note

**Reviewed**: 2026-05-24 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first — verify ENH-1618 (audit consolidation) has landed and spot-check actual routing behavior before treating descriptions as stable. The SEO ~90% misrouting reduction is an unverified external benchmark that may not transfer directly.

---

## Scope Boundaries

**Note** (added by `/ll:audit-issue-conflicts`): This issue adds negative routing instructions to the 14 Tier 1 skill descriptions, including the 5 audit skills. ENH-1618 plans to consolidate those 5 audit skills into a single meta-skill entry point (demoting 4 audit sub-skills from Tier 1). Adding routing disambiguation to audit skills before ENH-1618 resolves their Tier 1 status risks wasted work. This issue `depends_on: ENH-1618` — complete the audit consolidation decision first, then apply routing instructions only to the audit skills that remain Tier 1.
- `/ll:tradeoff-review-issues` - 2026-05-24T13:57:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0630921-fb2f-426a-a549-1a1d30e210f9.jsonl`
