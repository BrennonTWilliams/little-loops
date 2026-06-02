---

discovered_date: "2026-04-27"
discovered_by: issue-size-review
decision_needed: false
missing_artifacts: false
size: Very Large
confidence_score: 100
outcome_confidence: 53
score_complexity: 10
score_test_coverage: 0
score_ambiguity: 25
score_change_surface: 18
parent: ENH-1298
status: done
completed_at: 2026-05-10T00:00:00Z
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — canonical anchor patterns confirmed in codebase:_

**Established anchor patterns** (from `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, `CONTRIBUTING.md`, `docs/reference/ISSUE_TEMPLATE.md`):
- Function: `` `in function foo()` `` or `` `in method ClassName.method_name()` ``
- Class: `` `in class ClassName` `` or `` `near class Bar` ``
- Section: `` `under section "Title"` `` (for markdown headings)
- Integration Map entries: `` `path/to/file.py` — calls `affected_function()` in `handle_request()` ``

**`agents/codebase-analyzer.md` Output Format example** (lines 92–138): the existing worked example uses `` `handlers/webhook.js:15-32` `` style throughout — replace with `` `handlers/webhook.js` in `handleWebhook()` `` / `` under section "Request Validation" ``.

**Exact occurrence counts confirmed by research:**
- `agents/codebase-analyzer.md`: 5 occurrences (frontmatter description ×3, body intro ×1, Important Guidelines ×1)
- `agents/codebase-pattern-finder.md`: 2 occurrences (frontmatter commentary ×1, Core Responsibilities bullet ×1)
- `skills/wire-issue/SKILL.md`: 2 literal `file:line` phrases + 3 `:N`-style template entries (caller/docs/tests templates + output report)
- `skills/manage-issue/templates.md`: 17 raw occurrences across 16 lines
- `commands/refine-issue.md`: 10 occurrences (Agent prompts ×2, Gap Detection ×2, enrichment template ×3, Research Summary ×1, Output Report ×2)

## Integration Map

### Files to Modify

- `agents/codebase-analyzer.md`
- `agents/codebase-pattern-finder.md`
- `skills/wire-issue/SKILL.md`
- `skills/manage-issue/templates.md`
- `commands/refine-issue.md`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/decide-issue/SKILL.md:157` — Phase 4 agent prompt explicitly requests "Evidence FOR…with file:line references" from `codebase-pattern-finder`; no change needed for ENH-1299 scope but will be misaligned with anchor output after this fix (ENH-1300/1301 territory)
- `commands/iterate-plan.md:69` — instructs spawned sub-agents (incl. `codebase-analyzer`) to return "specific file:line references in responses"; same misalignment risk post-fix
- `commands/iterate-plan.md:100` — maintenance instruction "Keep all file:line references accurate" in plan files
- `skills/confidence-check/SKILL.md:233` — downstream validator; checks that issues contain "specific file:line references" in the Root Cause/Problem Analysis section; after ENH-1299 the agents will produce anchor refs instead, which may cause confidence-check to flag new issues incorrectly

### Similar Patterns
- N/A — text-only edits; no code patterns to synchronize across the codebase

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1299_doc_wiring.py` — new test file to write; assert that the 5 target files no longer contain `"file:line"` after implementation; follow the pattern in `scripts/tests/test_feat1172_doc_wiring.py` (path constants via `Path(__file__).parent.parent.parent`, class per file, `assert "file:line" not in content`)
- No existing tests assert on the `file:line` strings being replaced — zero break risk across the full test suite

### Documentation
- N/A — the changed files are themselves the agent/skill prompts

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — additional files with `file:line` references found beyond the 5 in scope (for ENH-1300/ENH-1301 awareness):_

- `agents/consistency-checker.md` — "Report exact locations (file:line) for issues"
- `agents/plugin-config-auditor.md` — "Note exact issues with file:line when possible"
- `agents/prompt-optimizer.md` — multiple occurrences in prompt enhancement patterns
- `skills/audit-docs/SKILL.md` — output templates reference file:line
- `skills/confidence-check/SKILL.md` — checks for "specific file:line references" in issue analysis
- `skills/product-analyzer/SKILL.md` — "Every finding MUST cite file:line evidence"
- `hooks/prompts/continuation-prompt-template.md` — `[file:line]` placeholder slots
- `hooks/prompts/optimize-prompt-hook.md` — "Specific file:line references to include"
- `commands/iterate-plan.md` — "Request specific file:line references"

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Write `scripts/tests/test_enh1299_doc_wiring.py` — structural test asserting `"file:line"` is absent from the 5 target files post-edit; follow the pattern in `scripts/tests/test_feat1172_doc_wiring.py`

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-27_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 53/100 → LOW

### Outcome Risk Factors
- **No pre-existing automated validation for markdown prompt files**: The codebase has no unit tests for agent/skill/command `.md` files by design; the test written in Step 7 is the first. The 0/25 test-coverage score reflects the zero baseline, not a gap in the plan — the issue accounts for it. Mitigate by running the verification grep after each file edit rather than waiting until all 5 are done.
- **Spread across 4 directories**: 6 files total across `agents/`, `commands/`, `skills/`, `scripts/tests/` — each edit is isolated text replacement but the distribution increases the chance of a missed occurrence. The acceptance-criteria grep (`grep -rn "file:line" agents/ skills/wire-issue/ skills/manage-issue/ commands/refine-issue.md`) is the definitive check; run it as the final step.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-27
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1302: Fix `file:line` references in agent source files (codebase-analyzer.md, codebase-pattern-finder.md)
- ENH-1303: Fix `file:line` references in skill source files (wire-issue/SKILL.md, manage-issue/templates.md)
- ENH-1304: Fix `file:line` references in commands/refine-issue.md and add verification test

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-27T16:43:10 - `ffb785b8-11a4-4944-a15b-8d407ae45324.jsonl`
- `/ll:issue-size-review` - 2026-04-27T00:00:00Z - `ffb785b8-11a4-4944-a15b-8d407ae45324.jsonl`
- `/ll:wire-issue` - 2026-04-27T16:36:03 - `eb17a9e1-1757-445b-a0d0-e017660b091f.jsonl`
- `/ll:refine-issue` - 2026-04-27T16:31:32 - `53865c02-ff65-4dff-937f-c70478af84a7.jsonl`
- `/ll:format-issue` - 2026-04-27T16:24:32 - `55b2ae6b-cfb7-490c-a90a-55c58082ceb5.jsonl`
- `/ll:issue-size-review` - 2026-04-27T17:30:00Z - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:confidence-check` - 2026-04-27T00:00:00Z - `300897f1-2940-4fd4-853f-e9037c0ea665.jsonl`

---

**Open** | Created: 2026-04-27 | Priority: P2
