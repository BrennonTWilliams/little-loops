---
id: ENH-1618
title: Consolidate audit-* skills into a single meta-skill entry point
type: ENH
priority: P4
captured_at: '2026-05-22T19:19:39Z'
discovered_date: 2026-05-22
discovered_by: capture-issue
status: cancelled
parent: EPIC-1745
depends_on: [ENH-494]
---

# ENH-1618: Consolidate audit-* skills into a single meta-skill entry point

## Summary

Five audit-related skills exist as separate Tier 1 entries (`audit-claude-config`, `audit-docs`, `audit-issue-conflicts`, `audit-loop-run`, and `ll-audit-architecture`). ENH-1398 confirmed the Claude Code API doesn't support hierarchical skill grouping, but a meta-skill pattern — a single `audit` entry point that dispatches to sub-skills — could reduce the Tier 1 count from ~5 to 1 while preserving all functionality through delegation. The SEO plugin case study validated this pattern works for domain-clustered skills.

## Current Behavior

Five audit skills each consume a Tier 1 listing slot. When a user says "audit this," Claude must choose among five descriptions. Each skill has full frontmatter and must be individually maintained. Relatedly, `analyze-history` also performs an audit-like function but is Tier 2 (disabled). There's no unified "audit" concept in the user-facing skill model.

## Expected Behavior

A single `audit` skill (Tier 1, LLM-discoverable) with a description like:
```
Use when asked to audit code, config, docs, architecture, loops, or issues. Determines audit scope and dispatches to the appropriate sub-skill.
```

The body routes to the appropriate specialized skill:
- `/ll:audit-claude-config` for plugin/config validation
- `/ll:audit-docs` for documentation accuracy and coverage
- `/ll:audit-architecture` for codebase patterns
- `/ll:audit-issue-conflicts` for conflicting requirements
- `/ll:audit-loop-run` for loop execution analysis

The existing sub-skills remain functional and user-invocable. Only the routing entry point changes.

## Motivation

Five separate `audit-*` Tier 1 entries fragment what users perceive as a single concept, consuming 5× the listing budget and requiring Claude to pick among 5 candidates for any "audit" prompt. A unified `audit` entry point reduces routing ambiguity, lowers Tier 1 count, and makes the skill surface feel coherent to users. The meta-skill pattern is validated by the SEO plugin case study (referenced in ENH-1617).

## Proposed Solution

Create `skills/audit/SKILL.md` as a new Tier 1 meta-skill. Its body reads the user's request to determine audit scope (config, docs, architecture, issues, loops) and delegates to the appropriate sub-skill:

```
/ll:audit-claude-config  → plugin/config validation
/ll:audit-docs           → documentation accuracy and coverage
/ll:audit-architecture   → codebase structural patterns
/ll:audit-issue-conflicts → conflicting requirements across issues
/ll:audit-loop-run       → loop execution analysis
```

Optionally set `llm_discoverable: false` on the 4 sub-skills to demote them to Tier 2 (user-invocable directly but not auto-discovered). Keep sub-skills independently invocable via `/ll:<name>`.

## Implementation Steps

1. Audit current trigger patterns for the 5 audit skills to identify routing overlap and distinct triggers
2. Create `skills/audit/SKILL.md` with dispatching logic (reads scope from request, routes to sub-skill)
3. Decide demote vs. keep for each sub-skill (audit-claude-config may have distinct enough triggers to stay Tier 1)
4. Update `llm_discoverable: false` on demoted sub-skills
5. Run `ll-verify-skill-budget` to confirm reduced Tier 1 count is within budget
6. Test routing: "audit architecture", "audit my config", "audit the loop", "check for issue conflicts"

## Integration Map

### Files to Modify
- `skills/audit-claude-config/SKILL.md` — optionally set `llm_discoverable: false`
- `skills/audit-docs/SKILL.md` — optionally set `llm_discoverable: false`
- `skills/audit-issue-conflicts/SKILL.md` — optionally set `llm_discoverable: false`
- `skills/audit-loop-run/SKILL.md` — optionally set `llm_discoverable: false`
- `skills/ll-audit-architecture/SKILL.md` — optionally set `llm_discoverable: false`

### Dependent Files (Callers/Importers)
- `ll-verify-skill-budget` — verifies Tier 1 count after demotion

### Similar Patterns
- N/A — new meta-skill pattern for this project; SEO plugin case study is external reference

### Tests
- Manual: 5-6 routing prompts covering each audit sub-skill ("audit my loops", "audit the docs", etc.)

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P4 — architectural improvement, not blocking; ENH-1394 and ENH-1615 address immediate budget pressure
- **Effort**: Medium — create meta-skill, optionally demote sub-skills to user-invocable-only
- **Risk**: Low — additive pattern; sub-skills remain independently invocable
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `architecture`, `context-engineering`


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-06-08_ — **NO-GO (CLOSE)**

**Deciding Factor**: The issue's core premise — that five audit skills consume five Tier 1 slots — is factually false today. Only one slot is consumed (`ll-audit-architecture`, 18 tokens), and ENH-1615 (open, P3) will eliminate it as a `ll-*` bridge stub without ENH-1618 doing anything. Adding the meta-skill after ENH-1615 lands adds a net slot — a regression vs. doing nothing.

### Key Arguments For
- Dependencies ENH-494 and ENH-977 are both `status: done` — implementation is fully unblocked in principle
- Only a two-file change; `skill_expander.py` resolves `skills/audit/SKILL.md` automatically with no plumbing changes

### Key Arguments Against
- `ll-verify-skill-budget` confirms only 1 audit Tier-1 entry today (not 5); ENH-1394 (commit `2bc2e2f2`, May 10) already demoted 4 of 5 skills before this issue was captured on May 22
- The implementation spec uses `llm_discoverable: false` — a key absent from all 63 SKILL.md files and all Python tooling; the functional key is `disable-model-invocation`, which all four demoted sub-skills already carry
- ENH-1617 (`status: cancelled`) was the sole downstream consumer driving the sequencing rationale — this work currently unblocks nothing
- The four disabled skills were intentionally removed from auto-routing by ENH-1394 due to side effects; a meta-skill surfacing them would reverse a deliberate architectural decision

### Rationale
The four audit sub-skills already carry `disable-model-invocation: true` (Tier 2) and are already excluded from the listing budget. The only Tier-1 audit entry is `ll-audit-architecture` (18 tokens), which ENH-1615 will remove as part of suppressing all 30 `ll-*` bridge stubs. After ENH-1615 lands, the audit budget is zero without ENH-1618; implementing ENH-1618 afterward adds back a slot that ENH-1615 already eliminated. This issue is overtaken by events and should be closed.

## Session Log
- `/ll:go-no-go` - 2026-06-08T00:00:00Z - `e74b10f6-368b-4cc1-a196-ec969edf8887.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:tradeoff-review-issues` - 2026-06-03T00:30:18 - `288ea8fe-1443-4178-9435-e6f8b106cc59.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:34 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:16 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:07:40 - `7409b034-0513-44ad-a2a1-f3e47126e95b.jsonl`
- `/ll:format-issue` - 2026-05-24T02:22:57 - `2328e8ba-c60a-43cf-b563-f9a69957b379.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:17 - `48fbbd10-48f2-4312-a798-ccffa2afa082.jsonl`
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

## Status

**Open** | Created: 2026-05-22 | Priority: P4

---

## Scope Boundaries

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1617 (negative routing instructions for Tier 1 skill descriptions) has been made to depend on this issue. Resolve the audit-skill consolidation in ENH-1618 first so ENH-1617 knows which audit skills remain Tier 1 and actually need routing disambiguation. If this issue is deferred or cancelled, remove the `depends_on: ENH-1618` from ENH-1617 and unblock it.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-28): `audit-issue-conflicts` MUST remain Tier 1 (exempt from demotion). FEAT-948 introduces `decisions.yaml` as a project governance layer, and FEAT-1736 adds load-bearing coupling entries that wire-issue consumes at runtime. As the governance surface grows, `audit-issue-conflicts` becomes the primary cross-validation tool for decisions.yaml configurations — demoting it to Tier 2 would make this critical validator undiscoverable at exactly the moment its surface area expands.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-29): This issue owns the **frontmatter** of `audit-claude-config/SKILL.md` (adding `llm_discoverable: false`). ENH-494 owns the **body** of the same file (extracting content into companion files). The two changes target non-overlapping sections — no merge conflict expected as long as both are aware of the shared file. ENH-494's body extraction should be applied first so this issue edits frontmatter of the already-extracted file.

---

## Tradeoff Review Note

**Reviewed**: 2026-06-02 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | MEDIUM |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first — The mandatory `audit-issue-conflicts` Tier 1 exemption (per scope boundary note from 2026-05-28) means actual benefit is 5→2 at best, not 5→1 as stated. Before implementing, explicitly scope the final Tier 1 target count post-consolidation and confirm the meta-skill dispatch pattern adds less routing friction than the current 5-skill listing.
