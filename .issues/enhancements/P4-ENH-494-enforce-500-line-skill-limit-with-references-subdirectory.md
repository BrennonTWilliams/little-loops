---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
---

# ENH-494: Enforce 500-Line SKILL.md Limit with references/ Subdirectory Pattern

## Summary

Skills should stay under 500 lines to minimize context consumption when loaded. Overflow content belongs in a `skills/<name>/references/` subdirectory that is loaded on demand. This is a direct application of progressive disclosure: skills should be cheap to load, with full reference material available but not forced into context.

## Current Behavior

Some skills (e.g., `manage-issue`, `review-sprint`, `confidence-check`) likely exceed 500 lines. All skill content is loaded into context whenever the skill is active, regardless of whether the full content is needed for the current task.

There is no `references/` subdirectory convention and no enforcement of a line limit.

## Expected Behavior

- All `SKILL.md` files remain at or under 500 lines
- Detailed reference material, examples, and extended documentation live in `skills/<name>/references/*.md`
- The `SKILL.md` links to reference files with clear "see also" pointers
- A linting check (or documentation convention) establishes 500 lines as the limit

## Motivation

Every line in a `SKILL.md` is loaded into the context window when that skill is active. Large skills consume attention budget even when only a fraction of their content is relevant. The 500-line limit is not arbitrary — it's the same progressive disclosure principle the skills themselves teach. Practicing what we preach improves both performance and credibility.

## Proposed Solution

1. Audit all 15 `skills/*/SKILL.md` files for line count: `wc -l skills/*/SKILL.md`
2. For any skill exceeding 500 lines, identify what content is "reference" vs. "operational"
3. Create `skills/<name>/references/` directories for overflow content
4. Add "See also" links in `SKILL.md` pointing to reference files
5. Document the 500-line convention in `CONTRIBUTING.md`
6. Optionally add a `ll-check-links` or similar lint check for skill size

## Scope Boundaries

- **In scope**: Auditing skill sizes, extracting overflow to `references/`, documenting the convention
- **Out of scope**: Changing skill logic or rewriting skill content substantively

## Implementation Steps

1. Run `wc -l skills/*/SKILL.md | sort -n` to identify oversized skills
2. For each violating skill, extract reference/example sections to `references/` files
3. Add `## See Also` section in `SKILL.md` with links
4. Update `CONTRIBUTING.md` with the 500-line limit and `references/` pattern
5. Optionally extend `ll-check-links` to also check skill line counts

## Integration Map

### Files to Modify
- `skills/*/SKILL.md` — oversized skills only
- `CONTRIBUTING.md` — add convention documentation

### New Files
- `skills/<name>/references/*.md` — one or more per oversized skill

### Tests
- `wc -l skills/*/SKILL.md` should show all files ≤ 500 lines

### Documentation
- `CONTRIBUTING.md` — new section on skill size limits

## Impact

- **Priority**: P4 — Incremental improvement; not blocking
- **Effort**: Low — Audit + text reorganization, no code changes
- **Risk**: Low — Reorganization only, skill behavior unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `context-engineering`, `progressive-disclosure`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4

## Blocked By

- ENH-493

- ENH-491
- FEAT-441
## Blocks

- ENH-502

- ENH-496