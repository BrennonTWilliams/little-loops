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
- `.claude/CLAUDE.md:54` — add `update-docs`^ to "Code Quality" category alongside `audit-docs`^ (line confirmed: `- **Code Quality**: \`check-code\`, \`run-tests\`, \`audit-docs\`^, \`find-dead-code\``)
- `commands/help.md:114` — add full entry block in CODE QUALITY section (after `/ll:audit-docs` block ending at line 114, before the blank line preceding `GIT & RELEASE`)
- `commands/help.md:231` — add `update-docs` to the Quick Reference comma-separated list (line currently reads: `**Code Quality**: \`check-code\`, \`run-tests\`, \`audit-docs\``)

> **Note**: `.claude-plugin/plugin.json` does NOT need modification. Skill discovery is directory-based — `"skills": ["./skills"]` at `plugin.json:20` auto-discovers any new `skills/*/SKILL.md` subdirectory.

### Reusable Code
- `scripts/little_loops/issue_history/parsing.py:197` — `scan_completed_issues(completed_dir)` reads all `*.md` from `.issues/completed/`; extracts `completed_date` from `**Completed**: YYYY-MM-DD` pattern (with mtime fallback)
- `scripts/little_loops/issue_history/parsing.py:222` — `_parse_discovered_date(fm)` — extracts `discovered_date` from YAML frontmatter dict
- `scripts/little_loops/issue_discovery/extraction.py:105` — `_get_files_modified_since_commit(since_commit, target_files)` — batched `git log {since}..HEAD --name-only --pretty=format:"%H"` call; parses `\n\n`-separated blocks
- `scripts/little_loops/cli/history.py:104` — `ll-history export` subcommand. **IMPORTANT**: requires a positional `topic` string argument (e.g., `ll-history export "docs" --since=<date>`). Without a topic, you cannot invoke it. The `--since` filter (line 219–221) uses `date.fromisoformat()` and passes the date to `synthesize_docs()` where issues with `completed_date < since` are skipped. The topic-relevance scorer (`score_relevance()`) uses word intersection, so a broad topic like `""` is not valid — use the skill's own glob of `.issues/completed/` via `scan_completed_issues()` when you need all issues without topic filtering.
- `scripts/little_loops/issue_history/doc_synthesis.py:143` — `synthesize_docs(topic, issues, contents, format, min_relevance, since, issue_type, scoring)` — full pipeline: pre-filter by since/type, relevance-score by topic, sort by completed_date, render markdown. The `--since` filter is at line 179: `if since and issue.completed_date and issue.completed_date < since: continue`

### Similar Patterns
- `skills/audit-docs/SKILL.md` — canonical reference: frontmatter with `argument-hint`, `allowed-tools: Bash(git:*)`, `--fix` flag pattern; same doc-quality domain
- `skills/capture-issue/SKILL.md` — multi-line `description: |` with embedded trigger keywords; `Bash(ll-issues:*, git:*)` scoped tool permissions; `--quick` flag handling
- `skills/format-issue/SKILL.md:49-79` — `--auto`/`--dry-run`/`--fix` flag parsing bash block pattern

### Related Issues
- None — `audit-docs` is complementary, not overlapping

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**SKILL.md frontmatter structure** (model after `skills/capture-issue/SKILL.md:1-20`):
```yaml
---
description: |
  Identify stale or missing documentation based on git commits and completed issues since a given date.

  Trigger keywords: "update docs", "stale docs", "missing docs", "docs since sprint", "doc coverage", "what docs need updating", "documentation gaps"
argument-hint: "[--since <date|git-ref>] [--fix]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Edit
  - Bash(git:*, ll-history:*, ll-issues:*)
arguments:
  - name: since
    description: Change window start — date (YYYY-MM-DD) or git ref (default: last commit touching a doc file)
    required: false
  - name: fix
    description: Draft stub documentation sections inline rather than just reporting gaps
    required: false
---
```

**Default since-ref resolution** (as described in Proposed Solution):
```bash
git log --oneline -- docs/ README.md CONTRIBUTING.md CHANGELOG.md | head -1 | awk '{print $1}'
```

**Completed issues since-date** — prefer direct `scan_completed_issues()` for all-issues listing:
```bash
# Don't use ll-history export for this — it requires a topic arg and applies relevance scoring.
# Instead, use a simple glob + date filter directly in the skill:
python -c "
from little_loops.issue_history.parsing import scan_completed_issues
from pathlib import Path
import sys
issues = scan_completed_issues(Path('.issues/completed'))
since = sys.argv[1]  # YYYY-MM-DD
for i in issues:
    if i.completed_date and str(i.completed_date) >= since:
        print(i.path)
" "$SINCE_DATE"
```
Or if a topic filter is useful, `ll-history export "<topic>" --since="$SINCE_DATE"` works but includes relevance scoring.
`synthesize_docs()` date filter is at `scripts/little_loops/issue_history/doc_synthesis.py:179`.

**help.md entry format** — two locations to update:

1. Full entry block at `commands/help.md:114` (insert after `/ll:audit-docs` block in CODE QUALITY section):
```
/ll:update-docs [--since <date|git-ref>] [--fix]
    Identify stale/missing docs from git commits and completed issues since a date
    Default since: last commit touching a doc file
```

2. Quick Reference table at `commands/help.md:231` — append `update-docs` to the Code Quality list:
```
**Code Quality**: `check-code`, `run-tests`, `audit-docs`, `update-docs`
```

**audit-docs/templates.md structure** (model for update-docs/templates.md):
- `skills/audit-docs/templates.md` contains an "Issue File Template" section (frontmatter + body) for docs issues auto-created by the skill
- For `update-docs/templates.md`, provide: (a) gap report format grouped by source (git changes vs. completed issues), and (b) stub section template for inline doc drafts
- Reference from SKILL.md body using: `[templates.md](templates.md) (see "Gap Report Format" section)`

**Frontmatter `description:` format** — both single-line and multi-line (`|`) are valid:
- `audit-docs/SKILL.md:1` uses single-line: `description: Audit documentation for accuracy and completeness`
- `capture-issue/SKILL.md` uses multi-line `description: |` with embedded trigger keywords after a blank line
- Prefer multi-line `description: |` to embed trigger keywords (improves discoverability)

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
- `/ll:refine-issue` - 2026-03-15T05:08:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5bd2338a-cb49-4e75-a5ae-a3ae2b55958e.jsonl`
- `/ll:refine-issue` - 2026-03-15T04:57:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c186be22-701d-4c89-a0c1-5b746b4d0e5b.jsonl`
- `/ll:refine-issue` - 2026-03-15T04:47:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/140d76f3-1325-4291-9c9d-17c281a9d0cf.jsonl`
- `/ll:capture-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b1c90f23-ff83-489f-b756-ad36ef9940cc.jsonl`
