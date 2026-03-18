---
discovered_date: 2026-03-17T00:00:00Z
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 68
testable: false
---

# ENH-802: auto-detect and set `testable: false` for doc-only issues across the issue pipeline

## Summary

No skill in the issue pipeline automatically infers and sets `testable: false` for documentation-only issues. Users must manually edit the issue file to add this field — error-prone and easy to forget under `tdd_mode: true`. The gap spans three pipeline stages: initial capture (`capture-issue`), structural formatting (`format-issue`), and the pre-implementation gate (`ready-issue`).

## Context

**Conversation mode**: Identified from conversation discussing ENH-800 resolution. ENH-800 explicitly left `capture-issue/templates.md` unchanged because "absence means testable; only `testable: false` is ever set explicitly." However, the mechanism for *setting* `testable: false` was left entirely manual, creating a gap for automated capture workflows.

The gap was initially scoped to `capture-issue` only, but analysis of the full issue pipeline revealed that doc-only issues can enter the system through multiple paths (conversation mode, external authoring, direct file creation) and persist across pipeline stages. A defense-in-depth approach across `capture-issue`, `format-issue`, and `ready-issue` is more robust.

## Motivation

With `tdd_mode: true` enabled, forgetting to set `testable: false` on a doc-only issue causes `manage-issue` Phase 3a to attempt writing meaningless tests (e.g., `grep` for anchor text) — the exact problem ENH-800 was designed to prevent. Auto-detecting across the pipeline closes the gap regardless of how an issue entered the system, without requiring post-capture manual edits.

## Current Behavior

- `capture-issue` always emits frontmatter with only `discovered_date` and `discovered_by`. No signal in the issue description triggers `testable: false`.
- `format-issue` performs frontmatter and structural gap analysis but does not check for `testable` on doc-only issues.
- `ready-issue` validates metadata and auto-corrects issues but does not check for missing `testable: false` on doc-only issues.

Net result: capturing "Fix broken anchor in LOOPS_GUIDE.md" produces an issue with no `testable` field at every pipeline stage; `manage-issue` treats it as testable and will attempt Phase 3a.

## Expected Behavior

At each pipeline stage, if an issue's title and description contain strong doc-only signals and `testable` is absent, the skill sets `testable: false` in the frontmatter and logs an inference message. Example signals: "doc", "docs", "documentation", "fix link", "broken anchor", "readme", "changelog", "spelling", "typo", "update guide".

The same keyword heuristic (2+ signal matches) is applied consistently across all three skills. Issues that already have `testable: false` are never overwritten.

## Proposed Solution

Add a shared keyword-based heuristic across three pipeline skills that scans the issue title and description for doc-only signals and conditionally adds `testable: false` to the frontmatter.

**Heuristic threshold**: Require 2+ signal keyword matches to reduce false positives (e.g., "update guide" alone shouldn't trigger if the issue is about a code update that also touches a guide).

**Signal keywords**: "doc", "docs", "documentation", "broken link", "broken anchor", "readme", "changelog", "spelling", "typo", "guide", "fix link"

**Pipeline defense-in-depth**:
- `capture-issue` — set at creation (catches the majority of cases)
- `format-issue` — set during structural alignment (catches issues authored outside `capture-issue`)
- `ready-issue` — auto-correct before implementation gate (final safety net for any issues that slipped through)

## Implementation Steps

1. **`skills/capture-issue/SKILL.md:235`** — After the frontmatter spec ("Always include YAML frontmatter with `discovered_date` and `discovered_by: capture-issue`"), add a `testable` inference step modeled after the type/priority keyword lists at lines 71–80:
   - Check title + description for doc-only signal keywords
   - If 2+ signals match: set `testable: false` in frontmatter, log: `"ℹ️ Set testable: false (inferred: documentation-only issue)"`
   - Otherwise: omit `testable` from frontmatter (absence = testable)
2. **`skills/capture-issue/templates.md:137`** — add `testable: false` as an optional frontmatter field (with comment explaining it is only emitted when the heuristic fires) between `discovered_by: capture-issue` and the closing `---`
3. **`skills/format-issue/SKILL.md:169`** — After the Step 2 batch loop block, before `### 2.5. Template v2.0 Section Alignment`, add a `testable` inference step:
   - Only run if `testable` field is absent from the existing frontmatter
   - Apply the same 2+ keyword heuristic against title + description
   - If triggered: add `testable: false` to frontmatter and include it in the gap report output
   - Also update the "CHANGES APPLIED" output block in `skills/format-issue/templates.md` (~line 325) to include a `testable` inference category
4. **`commands/ready-issue.md:244`** — After item 5 ("Add verification notes documenting changes"), add new item 6 for the `testable` metadata check (pushing current items 6/7 to 7/8):
   - Only run if `testable` field is absent from the existing frontmatter
   - Apply the same 2+ keyword heuristic against title + description
   - If triggered: add `testable: false` to frontmatter and record `[content_fix] Added testable: false (inferred: documentation-only issue)` in CORRECTIONS_MADE (see line 342–354 for format); use verdict CORRECTED (line 258)

## API/Interface

- Emitted/corrected frontmatter: `testable: false` conditionally added when doc-only signals detected; omitted otherwise
- No new flags or config keys; behavior is automatic and idempotent (existing `testable: false` is never overwritten)

## Integration Map

### Files to Modify
- `skills/capture-issue/SKILL.md` — Phase 4 inference step (add `testable` detection block)
- `skills/capture-issue/templates.md` — template structure (add optional `testable: false` field)
- `skills/format-issue/SKILL.md` — Step 2 frontmatter analysis (add `testable` inference when field is absent)
- `commands/ready-issue.md` — Step 5 auto-correction (add `testable` metadata check and CORRECTIONS_MADE entry)

### Tests
- N/A — skill-prompt changes only

### Documentation
- `docs/reference/ISSUE_TEMPLATE.md` — already documents `testable: false`; no change needed

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact insertion points (with line numbers):**

- `skills/capture-issue/SKILL.md:235` — after the line "Always include YAML frontmatter with `discovered_date` and `discovered_by: capture-issue`"; the type/priority inference pattern to model after is at lines 71–80 (keyword lists → default fallback → inferred value)
- `skills/capture-issue/templates.md:137` — insert `testable: false` (with comment) between `discovered_by: capture-issue` and the closing `---`
- `skills/format-issue/SKILL.md:169` — end of the Step 2 batch loop block; insert the inference step before the `### 2.5. Template v2.0 Section Alignment` heading; note: `format-issue` has no existing frontmatter gap detection — all current gap analysis is section-based (Step 3 uses `templates/{type}-sections.json` checklists); also update the "CHANGES APPLIED" output block in `skills/format-issue/templates.md` around line 325 to add a `testable` inference category
- `commands/ready-issue.md:244` — after item 5 ("Add verification notes documenting changes") and before the save instruction on line 245; becomes new item 6, pushing save and session-log to items 7 and 8; verdict instruction is at line 258

**Pseudocode pattern to model the inference block after** (`manage-issue/SKILL.md:192-205`):
```
READ testable from issue YAML frontmatter
IF testable is false:
  LOG: "⏭ Phase 3a skipped: testable: false in issue frontmatter"
  SKIP to Phase 3b
ELSE (testable is absent or true):
  PROCEED with Phase 3a
```
Use the same READ/IF/ELSE structure; the setter variant fires on the heuristic match rather than reading an existing value.

**`CORRECTIONS_MADE` format** for `ready-issue` (`commands/ready-issue.md:342-354`): the correction category prefix is `[content_fix]`; existing example: `[content_fix] Added missing ## Expected Behavior section`. The ENH-802-specified entry `[content_fix] Added testable: false (inferred: documentation-only issue)` matches this format exactly.

**`manage-issue` consumer** (read-only reference): `skills/manage-issue/SKILL.md:190-205` — already implemented; shows the consuming side of the semantic contract (absence = testable, `false` = skip Phase 3a).

## Scope Boundaries

- **In scope**: Keyword-based heuristic in `capture-issue` Phase 4, `format-issue` Step 2, and `ready-issue` Step 5; `capture-issue` template structure update
- **Out of scope**: ML-based classification; reading integration map sections (issue doesn't exist yet at capture time); applying to conversation mode differently than direct mode; `refine-issue` (knowledge gaps, not frontmatter); `manage-issue` (consumer, not setter)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `capture-issue`, `format-issue`, `ready-issue`, `tdd-mode`, `frontmatter`

---

## Status

**Open** | Created: 2026-03-17 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-03-18T03:49:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f3f1b7c-1a67-49db-8bab-4ef369788578.jsonl`
- `/ll:refine-issue` - 2026-03-18T03:41:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/091e39b0-ea1d-46cf-bdb2-857825824d3b.jsonl`
- `/ll:capture-issue` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0873aba7-6e24-4b9d-bf58-565ee42ebe88.jsonl`
- `/ll:confidence-check` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc742b74-08bf-4de2-8645-d69303ab8e64.jsonl`
