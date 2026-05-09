---
captured_at: "2026-05-09T20:48:12Z"
discovered_date: 2026-05-09
discovered_by: capture-issue
---

# ENH-1398: Hierarchical Skill Grouping to Reduce Listing Budget

## Summary

Organize the 28 skills into ~6 named categories with a short category-level description each. If Claude Code supports multi-level skill listings (category → individual skills), this reduces the listing budget by ~75% and scales indefinitely as new skills are added. Requires investigation of Claude Code's plugin API to confirm feasibility.

## Current Behavior

All 28 skills are listed as a flat list in the listing budget. Each skill has its own description. The budget scales linearly with skill count: every new skill adds ~50-150 tokens to the listing footprint.

## Expected Behavior

Skills are grouped into categories (e.g., "Issue Management", "Code Quality", "Automation & Loops", "Session & Config", "Meta-Analysis", "Planning & Implementation"). The LLM sees category-level descriptions (~20-30 tokens each) in the primary listing. If it identifies a relevant category, it can request individual skill descriptions within that category.

**Proposed categories:**
- **Issue Management**: capture-issue, manage-issue, format-issue, wire-issue, ready-issue, refine-issue, verify-issues, normalize-issues, prioritize-issues, align-issues, decide-issue
- **Planning & Review**: create-sprint, review-sprint, go-no-go, confidence-check, tradeoff-review-issues, issue-size-review, map-dependencies, audit-issue-conflicts
- **Code & Docs**: check-code, run-tests, audit-docs, update-docs, audit-architecture, find-dead-code
- **Automation & Loops**: create-loop, review-loop, debug-loop-run, audit-loop-run, rename-loop, cleanup-loops, workflow-automation-proposer, loop-suggester
- **Session & Config**: init, configure, update, handoff, resume, toggle-autoprompt, help, issue-workflow
- **Analysis & Meta**: analyze-history, analyze-workflows, improve-claude-md, audit-claude-config, scan-codebase, scan-product, product-analyzer, create-eval-from-issues

## Motivation

ENH-1394 and ENH-1396 address the immediate problem with a tactical fix (tagging skills) and enforcement (budget validator). Hierarchical grouping is the architectural solution that eliminates the budget scaling problem entirely: adding 10 more skills doesn't increase the listing footprint at all if they fit into existing categories.

This is the only approach that scales past 50+ skills without ongoing manual curation.

## Proposed Solution

**Phase 1 (investigation):** Determine whether Claude Code's plugin API supports category grouping or `skill_group` frontmatter. Check plugin manifest schema and Claude Code changelog for relevant features.

**Phase 2 (if supported):** Add a `group` field to each SKILL.md frontmatter. Update the plugin manifest if required.

**Phase 3 (if not natively supported):** Consider a workaround using skill descriptions that reference group membership, or defer until the Claude Code API supports it.

## Implementation Steps

1. Investigate Claude Code plugin manifest schema for skill grouping support
2. Check Claude Code changelog/docs for `skill_group`, `category`, or equivalent frontmatter fields
3. If supported: add `group: "<Category Name>"` to all SKILL.md frontmatter files
4. Update plugin manifest if category definitions are required there
5. Test that the LLM sees category-level descriptions in listing
6. If not supported: capture a feature request for the Claude Code team and close this issue as deferred

## Integration Map

### Files to Modify
- `skills/*/SKILL.md` — add `group:` frontmatter field (if supported)
- `.claude-plugin/plugin.json` — add category definitions (if required)

### Dependent Files (Callers/Importers)
- Claude Code harness — reads skill frontmatter for listing generation

### Similar Patterns
- N/A — novel pattern; no existing example in this project

### Tests
- N/A — Claude Code harness behavior, not testable in-project

### Documentation
- `CONTRIBUTING.md` — note group field convention for new skills

### Configuration
- `.claude-plugin/plugin.json` — potentially

## Impact

- **Priority**: P4 — depends on Claude Code API support; may not be actionable today
- **Effort**: Low (if supported) to Blocked (if not)
- **Risk**: Low — additive frontmatter field
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `context-engineering`, `investigation`

## Status

**Open** | Created: 2026-05-09 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-05-09T20:48:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c428abc-6b67-47fc-b1a4-d2d8d176f6b7.jsonl`
