---
id: ENH-1617
title: Add negative routing instructions to Tier 1 skill descriptions
type: ENH
priority: P3
captured_at: '2026-05-22T19:19:39Z'
discovered_date: 2026-05-22
discovered_by: capture-issue
status: cancelled
parent: EPIC-1745
depends_on:
- ENH-1618
- ENH-1615
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


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-06-08_ — **NO-GO (SKIP)**

**Deciding Factor**: The primary adjacency cluster `go-no-go` ↔ `confidence-check` ↔ `issue-size-review` cannot be authored as described because `issue-size-review` already has `disable-model-invocation: true` (Tier 2) — writing disambiguation to a Tier 2 skill is immediately stale, confirming the dependency concern is real, not merely bureaucratic.

### Key Arguments For
- `skills/product-analyzer/SKILL.md` line 1 already carries the exact disambiguation pattern in production, proving the convention is established and implementation is mechanical text changes within verified budget headroom (1420/2000 → 1560/2000 tokens)
- `ll-verify-triggers` (`scripts/little_loops/cli/verify_triggers.py`) is fully built infrastructure waiting for `trigger_fixtures` content — ENH-1617 would activate it as a complete routing-validation pipeline

### Key Arguments Against
- One of the three named adjacency clusters includes `issue-size-review` (`skills/issue-size-review/SKILL.md` line 4: `disable-model-invocation: true`), which is already Tier 2 — the cluster is stale as-written before implementation begins
- `ready-issue` and `verify-issues` do not exist as native Tier 1 skill directories; only `ll-ready-issue` and `ll-verify-issues` bridge stubs exist, which are slated for suppression by ENH-1615; three consecutive tradeoff reviews unanimously concluded topology must stabilize before this work proceeds

### Rationale
The issue's named adjacency clusters are factually incorrect about the current Tier 1 landscape: `issue-size-review` is already Tier 2, and `ready-issue`/`verify-issues` exist only as bridge stubs. The claimed three clusters are "clean of dependency concerns" but one already contains a demoted skill. Both blocking dependencies (ENH-1615, ENH-1618) remain open, and implementing now forces rework when ENH-1618 resolves audit skill consolidation.

## Session Log
- `/ll:go-no-go` - 2026-06-08T00:00:00Z - `373826e9-155a-427b-8b26-e6ff1266f796.jsonl`
- `/ll:tradeoff-review-issues` - 2026-06-05T22:31:17 - `6ff15632-2780-465b-907d-c2f1dc8463da.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:tradeoff-review-issues` - 2026-06-03T00:30:18 - `288ea8fe-1443-4178-9435-e6f8b106cc59.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:34 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:14 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:format-issue` - 2026-05-24T02:22:57 - `2328e8ba-c60a-43cf-b563-f9a69957b379.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:17 - `48fbbd10-48f2-4312-a798-ccffa2afa082.jsonl`
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

---

## Tradeoff Review Note (2026-06-05 Update)

**Reviewed**: 2026-06-05 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |
| Blocking bottleneck | LOW — no active issues depend on this |

### Recommendation
Update first — Still blocked on `depends_on: [ENH-1618, ENH-1615]`. Third review with no dependency progress. The final Tier 1 skill set remains unsettled until ENH-1618 resolves audit skill consolidation. Routing instructions written before neighbor topology is finalized will need rework. Consider setting a deadline: if dependencies remain open by next review cycle, re-evaluate for deferral.

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
- `/ll:tradeoff-review-issues` - 2026-05-24T13:57:35 - `f0630921-fb2f-426a-a549-1a1d30e210f9.jsonl`

---

## Tradeoff Review Note (2026-06-02 Update)

**Reviewed**: 2026-06-02 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first — Still blocked on `depends_on: [ENH-1618, ENH-1615, FEAT-948]`; the final Tier 1 skill set hasn't been stabilized by upstream dependencies. No actionable work until ENH-1618 resolves which audit skills remain Tier 1. Routing instructions written before the neighbor set is finalized will need rework.
