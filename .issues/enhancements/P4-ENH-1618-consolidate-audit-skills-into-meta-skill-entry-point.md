---
captured_at: '2026-05-22T19:19:39Z'
discovered_date: 2026-05-22
discovered_by: capture-issue
status: open
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

## Impact

- **Priority**: P4 — architectural improvement, not blocking; ENH-1394 and ENH-1615 address immediate budget pressure
- **Effort**: Medium — create meta-skill, optionally demote sub-skills to user-invocable-only
- **Risk**: Low — additive pattern; sub-skills remain independently invocable
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `architecture`, `context-engineering`

## Session Log
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

## Status

**Open** | Created: 2026-05-22 | Priority: P4
