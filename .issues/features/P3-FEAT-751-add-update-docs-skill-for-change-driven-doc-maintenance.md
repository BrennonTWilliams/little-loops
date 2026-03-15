---
discovered_date: 2026-03-14
discovered_by: capture-issue
---

# FEAT-751: Add update-docs skill for change-driven doc maintenance

## Summary

`/ll:audit-docs` audits docs for static accuracy but has no awareness of what recently changed. There is no skill to identify which documentation is stale or missing based on git commits and completed issues since the last documentation update.

## Current Behavior

`/ll:audit-docs` performs a static audit — it validates docs against the current codebase state (file paths exist, API signatures match, counts are correct). It has no concept of "what changed since docs were last updated" and cannot identify documentation gaps introduced by recent feature work.

## Expected Behavior

A new `/ll:update-docs` skill identifies documentation that needs to be written or updated by analyzing:
1. **Git commits** since the last documentation change — which source files changed, what modules were affected
2. **Completed issues** since a given date — what features/bugs/enhancements were shipped that may require new or updated docs

The skill produces a prioritized list of documentation gaps with specific change context, then offers to draft stub sections or create issues for each gap.

## Use Case

After closing a sprint, a developer runs `/ll:update-docs --since=sprint-start` to catch up documentation on everything shipped. The skill shows: "ENH-740 added a new `--elide` flag to `ll-loop show` — no documentation mentions this flag." The developer can then draft the docs inline or create a doc issue.

## Acceptance Criteria

- [ ] `--since=<date|git-ref>` argument determines the change window (default: last commit touching a doc file)
- [ ] Parses `git log --since=<ref>` on non-doc source files to identify changed modules/components
- [ ] Scans `.issues/completed/` filtered by completion date to identify recently shipped work
- [ ] Cross-references changes against existing doc files to identify coverage gaps
- [ ] Produces a prioritized list: "these completed issues have no doc coverage", "these changed files have potentially stale docs"
- [ ] Offers to draft stub documentation sections inline or create issues for each gap
- [ ] Does not overlap with `audit-docs` — this skill detects *missing/new* coverage, not incorrect existing content

## Proposed Solution

### Skill: `skills/update-docs/SKILL.md`

**Arguments:**
- `--since=<date|git-ref>` — change window start (default: last doc file commit)
- `--fix` — draft stub sections inline rather than just reporting gaps

**Process:**

1. **Determine since-ref**: If not provided, run `git log --oneline -- docs/ README.md CONTRIBUTING.md | head -1` to find last doc commit hash
2. **Collect changed source**: `git log --since=<ref> --name-only --pretty="" -- <src_dir>` → group changed files by module
3. **Collect completed issues**: Scan `.issues/completed/` for files modified after the since-ref date
4. **Build change inventory**: For each changed module/file and each completed issue, extract: what changed, what it does, what docs it would affect
5. **Cross-reference docs**: For each change, search doc files for coverage of that module/feature
6. **Report gaps**: Prioritized list grouped by source (git changes vs. completed issues)
7. **Offer action**: For each gap — draft stub, create issue, or skip

### Watermark support (optional enhancement)
Store last-run timestamp in `.claude/ll-update-docs.watermark` so subsequent runs auto-advance the window.

## Scope Boundaries

- **In scope**: Detecting missing/stale docs from recent changes; drafting stubs; creating doc issues
- **Out of scope**: Fixing incorrect existing content (that's `audit-docs`); validating code examples

## Implementation Steps

1. Create `skills/update-docs/SKILL.md` with process above
2. Create `skills/update-docs/templates.md` for gap report format and stub templates
3. Add `update-docs` to `skills/` list in `CLAUDE.md` and `.claude-plugin/plugin.json`
4. Register skill in plugin manifest and help output

## Integration Map

### Files to Create
- `skills/update-docs/SKILL.md` — main skill definition
- `skills/update-docs/templates.md` — gap report and stub templates

### Files to Modify
- `.claude-plugin/plugin.json` — register new skill
- `.claude/CLAUDE.md` — add to skills list
- `commands/help.md` or help skill — surface new command

### Similar Patterns
- `skills/audit-docs/SKILL.md` — same doc-quality domain, complementary scope
- `skills/capture-issue/SKILL.md` — similar "scan and create issues" flow

### Related Issues
- None — `audit-docs` is complementary, not overlapping

## Impact

- **Priority**: P3 - High-value for sprint close / pre-release doc catch-up; not blocking
- **Effort**: Medium — New skill file + templates; git log and issue scanning are straightforward
- **Risk**: Low — Read-only analysis; writes only to issue files with user approval
- **Breaking Change**: No

## Labels

`feature`, `docs`, `skill`, `git-history`, `workflow`

---

## Status

**Open** | Created: 2026-03-14 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b1c90f23-ff83-489f-b756-ad36ef9940cc.jsonl`
