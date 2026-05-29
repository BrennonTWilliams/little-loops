---
id: ENH-1618
type: ENH
priority: P4
captured_at: '2026-05-22T19:19:39Z'
discovered_date: 2026-05-22
discovered_by: capture-issue
status: open
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

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:07:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7409b034-0513-44ad-a2a1-f3e47126e95b.jsonl`
- `/ll:format-issue` - 2026-05-24T02:22:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2328e8ba-c60a-43cf-b563-f9a69957b379.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48fbbd10-48f2-4312-a798-ccffa2afa082.jsonl`
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

## Status

**Open** | Created: 2026-05-22 | Priority: P4

---

## Scope Boundaries

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1617 (negative routing instructions for Tier 1 skill descriptions) has been made to depend on this issue. Resolve the audit-skill consolidation in ENH-1618 first so ENH-1617 knows which audit skills remain Tier 1 and actually need routing disambiguation. If this issue is deferred or cancelled, remove the `depends_on: ENH-1618` from ENH-1617 and unblock it.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-28): `audit-issue-conflicts` MUST remain Tier 1 (exempt from demotion). FEAT-948 introduces `decisions.yaml` as a project governance layer, and FEAT-1736 adds load-bearing coupling entries that wire-issue consumes at runtime. As the governance surface grows, `audit-issue-conflicts` becomes the primary cross-validation tool for decisions.yaml configurations — demoting it to Tier 2 would make this critical validator undiscoverable at exactly the moment its surface area expands.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-29): This issue owns the **frontmatter** of `audit-claude-config/SKILL.md` (adding `llm_discoverable: false`). ENH-494 owns the **body** of the same file (extracting content into companion files). The two changes target non-overlapping sections — no merge conflict expected as long as both are aware of the shared file. ENH-494's body extraction should be applied first so this issue edits frontmatter of the already-extracted file.
