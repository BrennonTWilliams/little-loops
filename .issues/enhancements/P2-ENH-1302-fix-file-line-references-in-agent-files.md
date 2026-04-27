---
parent_issue: ENH-1299
discovered_date: "2026-04-27"
discovered_by: issue-size-review
decision_needed: false
missing_artifacts: true
confidence_score: 80
outcome_confidence: 60
score_complexity: 25
score_test_coverage: 0
score_ambiguity: 25
score_change_surface: 10
---

# ENH-1302: Fix `file:line` references in agent source files

## Summary

Edit `agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md` to replace all `file:line`-style references with anchor-based equivalents (function/class names, section headings).

## Parent Issue

Decomposed from ENH-1299: Fix `file:line` references in issue-authoring pipeline source files

## Current Behavior

- **`agents/codebase-analyzer.md`**: `Important Guidelines` says "Always include file:line references for claims"; `Output Format` worked example uses `handlers/webhook.js:15-32` style; `description` frontmatter says "precise file:line references" (5 total occurrences).
- **`agents/codebase-pattern-finder.md`**: Two locations say "Returns actual code snippets with file:line references" / "Include file:line references".

## Expected Behavior

- `codebase-analyzer.md`: `Important Guidelines` updated to "Always include anchor-based references (function/class names; section headings for markdown files) — never raw line numbers"; `Output Format` examples rewritten to `` `handlers/webhook.js` in `handleWebhook()` `` / `` under section "Request Validation" `` style; `description` frontmatter updated to "anchor-based references (function/class names)".
- `codebase-pattern-finder.md`: Both "file:line references" occurrences updated to "anchor-based references (function/class names)".

## Proposed Solution

1. **`agents/codebase-analyzer.md`** (highest leverage):
   - Replace `Important Guidelines` rule: `"Always include file:line references for claims"` → `"Always include anchor-based references (function/class names; section headings for markdown files) — never raw line numbers"`
   - Rewrite all `file.js:N` examples in `## Output Format` to anchor style: e.g., `` `handlers/webhook.js` in `handleWebhook()` ``
   - Update `description` frontmatter: replace "precise file:line references" with "anchor-based references (function/class names)"

2. **`agents/codebase-pattern-finder.md`**:
   - Update the two "file:line references" occurrences to "anchor-based references (function/class names)"

### Codebase Research Findings

**Established anchor patterns** (from `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, `CONTRIBUTING.md`, `docs/reference/ISSUE_TEMPLATE.md`):
- Function: `` `in function foo()` `` or `` `in method ClassName.method_name()` ``
- Class: `` `in class ClassName` `` or `` `near class Bar` ``
- Section: `` `under section "Title"` `` (for markdown headings)

**Exact occurrence counts:**
- `agents/codebase-analyzer.md`: 5 occurrences (frontmatter description ×3, body intro ×1, Important Guidelines ×1)
- `agents/codebase-pattern-finder.md`: 2 occurrences (frontmatter commentary ×1, Core Responsibilities bullet ×1)

## Integration Map

### Files to Modify

- `agents/codebase-analyzer.md`
- `agents/codebase-pattern-finder.md`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `commands/refine-issue.md` — spawns both agents with `"Return ... with specific file:line references"` in invocation prompts (ENH-1304 scope)
- `skills/manage-issue/SKILL.md` + `skills/manage-issue/templates.md` — spawns both agents; `templates.md` has prompt strings and `[file:line reference]` template slots (ENH-1303 scope)
- `skills/wire-issue/SKILL.md` — spawns both agents; Agent 2 and Agent 3 prompts request `file:line` output (ENH-1303 scope)
- `skills/decide-issue/SKILL.md` — spawns `codebase-pattern-finder` in Phase 4; prompt requests `(with file:line references)` (residual — not in ENH-1299 decomposition)
- `commands/scan-codebase.md` — spawns `codebase-analyzer` in Bug/Enhancement/Feature scanners; no `file:line` in invocation prompts
- `commands/ready-issue.md` — references `codebase-analyzer` for verifying code claims; no `file:line` in invocation prompts
- `commands/audit-architecture.md` — references `codebase-analyzer`; no `file:line` in invocation prompts
- `skills/audit-claude-config/SKILL.md` — spawns `codebase-analyzer`; no `file:line` in invocation prompts
- `commands/iterate-plan.md` — caller-side guideline: "Request specific file:line references in responses" and "Keep all file:line references accurate" (residual — not in ENH-1299 decomposition)
- `scripts/tests/test_decide_issue_skill.py` — asserts `"codebase-pattern-finder"` string present in `decide-issue/SKILL.md`; not broken by ENH-1302

### Residual Coupling (Out-of-Scope for ENH-1302)

_Wiring pass added by `/ll:wire-issue`:_ These are callers not addressed by the ENH-1299 decomposition. They retain `file:line` language after all sibling issues complete.
- `skills/decide-issue/SKILL.md:157` — `(with file:line references)` in evidence format for `codebase-pattern-finder` invocation
- `commands/iterate-plan.md:69` — `"Request specific file:line references in responses"` guideline
- `skills/confidence-check/SKILL.md:233` — scores BUG issues lower if they lack `"specific file:line references"` in Root Cause (would penalize anchor-based output from these agents)

### Tests

- `scripts/tests/test_enh1299_doc_wiring.py` (written by ENH-1304) — includes assertions for these two files
- `scripts/tests/test_decide_issue_skill.py` — `TestCodebasePatternFinderSpawn.test_codebase_pattern_finder_agent_referenced()` — will not break (asserts agent name string, not output format)

### Test Pattern Reference

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1172_doc_wiring.py` — structural template for `test_enh1299_doc_wiring.py`
- `scripts/tests/test_enh1130_doc_wiring.py:28-33` — absence-assertion pattern: `assert "old-token" not in content`

### Verification

```bash
grep -n "file:line" agents/codebase-analyzer.md agents/codebase-pattern-finder.md
# Should return zero matches
```

## Implementation Steps

1. Edit `agents/codebase-analyzer.md` — update `Important Guidelines`, `Output Format` examples, and `description` frontmatter.
2. Edit `agents/codebase-pattern-finder.md` — update two occurrences.

## Impact

- **Priority**: P2
- **Effort**: Small — pure text edits to 2 markdown files
- **Risk**: Very low — reversible; changes only affect agent prompts
- **Breaking Change**: No

## Success Metrics

- Zero `file:line` occurrences in `agents/codebase-analyzer.md` and `agents/codebase-pattern-finder.md`.

## Labels

`enhancement`, `reference-cleanup`, `authoring-pipeline`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-27_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 60/100 → MODERATE

### Concerns
- **Implementation already done**: Working-tree diff confirms both agent files have been updated — `grep "file:line"` returns zero matches. This issue may be implementable as a commit-and-close rather than a fresh implementation pass.
- **Readiness score (80) is below the project gate (85)**: `ll-config.json` sets `readiness_threshold: 85`; the manage-issue Phase 2.5 gate will block on this score.

### Outcome Risk Factors
- **Test coverage absent**: `test_enh1299_doc_wiring.py` is not yet created (scoped to ENH-1304). Until that file exists, regressions in anchor-based content across both agent files will not be caught automatically.
- **Broad caller surface**: 9 files spawn these agents; while output-format changes don't break callers, inconsistent anchor conventions in agent responses could subtly affect downstream issue quality.

## Session Log
- `/ll:wire-issue` - 2026-04-27T16:51:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e616bd9b-4432-48b3-b18e-6c0f71f08fcf.jsonl`
- `/ll:refine-issue` - 2026-04-27T16:47:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87e6eb14-61d0-4dc8-b978-a8a586e5b376.jsonl`
- `/ll:issue-size-review` - 2026-04-27T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffb785b8-11a4-4944-a15b-8d407ae45324.jsonl`
- `/ll:confidence-check` - 2026-04-27T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f3e56e4-6893-43df-9f38-74cd82af6d81.jsonl`

---

**Open** | Created: 2026-04-27 | Priority: P2
