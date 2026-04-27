---
parent_issue: ENH-1298
discovered_date: "2026-04-27"
discovered_by: issue-size-review
decision_needed: false
missing_artifacts: false
size: Medium
---

# ENH-1299: Fix `file:line` references in issue-authoring pipeline source files

## Summary

Five source files in the issue-authoring pipeline actively generate or prompt for `file:line`-style references, contradicting the documented anchor-based reference policy. This issue performs pure text edits to those files — no code changes, no new modules — to stop new contamination at the root.

## Parent Issue

Decomposed from ENH-1298: Convert issue-authoring pipelines from `file:line` to anchor-based references

## Current Behavior

Five files embed `file:line` patterns in examples, prompt strings, and output templates:

1. **`agents/codebase-analyzer.md`** — `Important Guidelines` says "Always include file:line references for claims"; `Output Format` worked example uses `handlers/webhook.js:15-32` style. The `description` frontmatter also says "precise file:line references".
2. **`agents/codebase-pattern-finder.md`** — Two locations (around lines 11 and 65) say "Returns actual code snippets with file:line references" / "Include file:line references".
3. **`skills/wire-issue/SKILL.md`** — Output templates under "Callers / importers", "Documentation", and "Tests" show `path/to/caller.py:42` style.
4. **`skills/manage-issue/templates.md`** — 10+ instances of "with file:line references" and `[file:line]` placeholder slots.
5. **`commands/refine-issue.md`** — Agent 2 and Agent 3 prompt blocks, plus the `Gap Detection` table row "Which file:line contains the bug".

## Expected Behavior

All five files use anchor-based reference language:
- Examples read `in handleWebhook()`, `under section "Request Validation"`, `near class IssueParser`
- Prompt strings say "with function/class anchors (e.g. `in function foo()`, `near class Bar`)"
- Gap Detection table row reads "Which function/class contains the bug"
- `codebase-analyzer.md` description frontmatter updated to match

## Motivation

This enhancement stops future issues from being contaminated with `file:line` references at the source — the agent/skill prompts that generate them. Without this fix, each new issue refined through `refine-issue`, `wire-issue`, or `manage-issue` continues to embed raw line numbers that become stale the moment surrounding code shifts. Anchor-based references (function/class names, section headings) are stable across edits and provide more meaningful context for implementation agents.

## Proposed Solution

Pure text edits, ordered by leverage:

1. **`agents/codebase-analyzer.md`** (highest leverage — fix first):
   - Replace `Important Guidelines` rule: `"Always include file:line references for claims"` → `"Always include anchor-based references (function/class names; section headings for markdown files) — never raw line numbers"`
   - Rewrite all `file.js:N` examples in `## Output Format` to anchor style: e.g., `` `handlers/webhook.js` in `handleWebhook()` ``
   - Update `description` frontmatter: replace "precise file:line references" with "anchor-based references (function/class names)"

2. **`agents/codebase-pattern-finder.md`**:
   - Update the two "file:line references" occurrences to "anchor-based references (function/class names)"

3. **`skills/wire-issue/SKILL.md`**:
   - Update output template entries from `path/to/caller.py:42 — calls affected_function()` to `path/to/caller.py — calls affected_function() in handle_request()`

4. **`skills/manage-issue/templates.md`**:
   - Replace all "with file:line references" with "with function/class anchors (e.g. `in function foo()`, `near class Bar`)" — 10+ instances
   - Replace `[file:line]` placeholder slots with `[function/class anchor]`

5. **`commands/refine-issue.md`**:
   - Update Agent 2 and Agent 3 prompt blocks to request anchors
   - Update Gap Detection table row from "Which file:line contains the bug" to "Which function/class contains the bug"

## Integration Map

### Files to Modify

- `agents/codebase-analyzer.md`
- `agents/codebase-pattern-finder.md`
- `skills/wire-issue/SKILL.md`
- `skills/manage-issue/templates.md`
- `commands/refine-issue.md`

### Dependent Files (Callers/Importers)
- N/A — changes are to prompt text in markdown files; no code imports or calls these files

### Similar Patterns
- N/A — text-only edits; no code patterns to synchronize across the codebase

### Tests
- N/A — no test files need updating for markdown-only prompt changes

### Documentation
- N/A — the changed files are themselves the agent/skill prompts

### Configuration
- N/A

### Verification

After completing edits:
```bash
grep -rn "file:line" agents/ skills/wire-issue/ skills/manage-issue/ commands/refine-issue.md
# Should return zero matches (or only matches that are legitimate prose about the old behavior)
```

Run `refine-issue` on a sample issue and confirm output uses anchors, not `file:line` patterns.

## Implementation Steps

1. Edit `agents/codebase-analyzer.md` — update `Important Guidelines`, `Output Format` examples, and `description` frontmatter.
2. Edit `agents/codebase-pattern-finder.md` — update two occurrences.
3. Edit `skills/wire-issue/SKILL.md` — update output templates.
4. Edit `skills/manage-issue/templates.md` — replace all 10+ instances.
5. Edit `commands/refine-issue.md` — update prompts and Gap Detection table.
6. Run verification grep.

## Impact

- **Priority**: P2 — prevents ongoing contamination of newly-authored issues with stale line-number references.
- **Effort**: Small — pure text edits to markdown files, no code changes.
- **Risk**: Very low — reversible; changes only affect agent/skill prompts.
- **Breaking Change**: No — no public APIs or interfaces change.
- **Blocking**: ENH-1300 (sweeper) should be run after this to clean up already-contaminated issues. ENH-1301 (lint) can be done in any order relative to this.

## Success Metrics

- Zero `file:line` occurrences in the five target files (verified by grep).
- Running `refine-issue` or `wire-issue` on a fixture produces anchor-only output.

## Scope Boundaries

- **In scope**: Text edits to the five listed files — replace `file:line` examples, prompt strings, and placeholder slots with anchor-based equivalents.
- **Out of scope**:
  - Fixing already-contaminated issue files (covered by ENH-1300 anchor-resolver sweeper)
  - Adding lint/CI validation to block future regressions (covered by ENH-1301)
  - Any code changes or new modules
  - Files not listed in the Integration Map

## API/Interface

N/A — No public API changes. This enhancement modifies only prose/template text in agent and skill markdown files.

## Labels

`enhancement`, `reference-cleanup`, `authoring-pipeline`, `captured`

## Session Log
- `/ll:format-issue` - 2026-04-27T16:24:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55b2ae6b-cfb7-490c-a90a-55c58082ceb5.jsonl`
- `/ll:issue-size-review` - 2026-04-27T17:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

**Open** | Created: 2026-04-27 | Priority: P2
