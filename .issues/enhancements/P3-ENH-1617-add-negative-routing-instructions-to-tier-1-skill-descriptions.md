---
captured_at: '2026-05-22T19:19:39Z'
discovered_date: 2026-05-22
discovered_by: capture-issue
status: open
depends_on: ENH-1618
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

## Impact

- **Priority**: P3 — routing accuracy improvement, no current bug
- **Effort**: Small — update 14 description fields with neighbor disambiguation
- **Risk**: Low — descriptions may need tuning based on observed routing behavior
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `context-engineering`, `routing`

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48fbbd10-48f2-4312-a798-ccffa2afa082.jsonl`
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

## Status

**Open** | Created: 2026-05-22 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue adds negative routing instructions to the 14 Tier 1 skill descriptions, including the 5 audit skills. ENH-1618 plans to consolidate those 5 audit skills into a single meta-skill entry point (demoting 4 audit sub-skills from Tier 1). Adding routing disambiguation to audit skills before ENH-1618 resolves their Tier 1 status risks wasted work. This issue `depends_on: ENH-1618` — complete the audit consolidation decision first, then apply routing instructions only to the audit skills that remain Tier 1.
