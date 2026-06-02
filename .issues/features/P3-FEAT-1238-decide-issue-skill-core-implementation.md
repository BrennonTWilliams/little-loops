---
id: FEAT-1238
priority: P3
size: Medium
parent: FEAT-1236
decision_needed: false
confidence_score: 98
outcome_confidence: 75
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 22
score_change_surface: 25
completed_at: 2026-04-21T21:58:24Z
status: done
---

# FEAT-1238: Create /ll:decide-issue skill — core implementation

## Summary

New skill at `skills/decide-issue/SKILL.md` that reads an issue, extracts all implementation options from the Proposed Solution section, spawns a `codebase-pattern-finder` subagent per option to gather codebase evidence, scores each option, selects the best, annotates the choice inline, and clears `decision_needed` from frontmatter.

## Parent Issue

Decomposed from FEAT-1236: Add /ll:decide-issue skill to resolve multiple implementation options

## Current Behavior

No `/ll:decide-issue` skill exists. When `/ll:refine-issue --auto` deposits multiple implementation options, nothing selects among them automatically.

## Expected Behavior

`/ll:decide-issue [ISSUE_ID] [--auto] [--dry-run]` extracts options, evaluates them with codebase evidence, selects the best, annotates the issue, and clears `decision_needed: true`.

## Use Case

A developer runs `/ll:refine-issue --auto` on an issue and it deposits 2+ implementation options, setting `decision_needed: true`. The developer runs `/ll:decide-issue FEAT-XXX` and the skill gathers codebase evidence for each option, scores them across consistency/simplicity/testability/risk dimensions, selects the best-fit approach, annotates the issue with the decision and a scoring rationale, and clears `decision_needed: false` — enabling the pipeline to continue to `/ll:wire-issue` or `/ll:manage-issue` without requiring the developer to manually evaluate competing approaches.

## Acceptance Criteria

- Given an issue with `decision_needed: true` and 2+ options in Proposed Solution, skill selects one and updates the issue with choice highlighted and reasoning annotated
- `decision_needed` is cleared (`false`) from frontmatter after a decision is made
- If only one option is present, skill exits cleanly without modifying the issue
- Can be run manually on any issue even without the `decision_needed` flag
- `--dry-run` flag previews the decision without modifying the issue
- Output report includes the chosen option, scoring summary, and options considered

## Proposed Solution

Create `skills/decide-issue/SKILL.md` following `skills/wire-issue/SKILL.md:1-50` as the structural template.

### Skill Structure

1. **Flag parsing**: `--auto`, `--dry-run`, issue ID argument (follow `skills/wire-issue/SKILL.md:123-202`)
2. **Issue location**: `ll-issues path [ISSUE_ID]`
3. **Option extraction**: three patterns from `commands/refine-issue.md:265-274`:
   - Numbered `1.`/`2.` list items under a "## Options" or "### Option" heading
   - `### Option A` / `### Option B` section headers
   - `**Option A**` / `**Option B**` bold inline labels
4. **Evidence gathering**: spawn one `codebase-pattern-finder` Agent per option; query for pattern existence, call site count, existing utilities
5. **Scoring per option**: consistency with existing patterns, implementation simplicity, testability, risk (0-3 per dimension, 12 max)
6. **Annotation**: mark selected option with `> **Selected:** [option title]` callout; append `### Decision Rationale` subsection with scoring table
7. **Frontmatter update**: follow `skills/confidence-check/SKILL.md:398-446` for inline `---` block replacement; set `decision_needed: false`; idempotency rule per `skills/format-issue/SKILL.md:163-175`
8. **Session log**: `ll-issues append-log [ISSUE_ID]` at end of run

### Reference Files

- `skills/wire-issue/SKILL.md:123-202` — structural template (flag parsing, issue location, Agent spawn pattern)
- `skills/confidence-check/SKILL.md:398-446` — frontmatter inline replacement pattern
- `skills/format-issue/SKILL.md:163-175` — idempotency rule
- `skills/manage-issue/SKILL.md:157-191` — HALT/WARN/PROCEED gate pattern (model for `--dry-run`)
- `.issues/completed/P2-BUG-903-*.md:65-76` — real `**Option A** / **Option B**` example for option extraction testing

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `commands/refine-issue.md:448-479` — NEXT STEPS output block and Pipeline Position section do not mention `/ll:decide-issue`; when `decision_needed: true` is set, it should direct users to run `decide-issue` next. **Unallocated: not covered by FEAT-1239 or FEAT-1240.** [Agent 1 + Agent 2]
- `skills/wire-issue/SKILL.md:438-455` — Pipeline Position section and NEXT STEPS block omit `decide-issue` between `refine-issue` and `wire-issue`. **Unallocated: not covered by any sibling issue.** [Agent 2]

### Files to Create
- `skills/decide-issue/SKILL.md` — primary deliverable (new skill file)
- `skills/decide-issue/` — new directory

### Plugin Registration
- `.claude-plugin/plugin.json:19` — uses `"skills": ["./skills"]` **auto-discovery**; no plugin.json edit needed — placing `skills/decide-issue/SKILL.md` is sufficient for registration

### Reference Files (Read-Only — Model After These)
- `skills/wire-issue/SKILL.md:1-18` — YAML frontmatter header (`description`, `model: sonnet`, `allowed-tools` list including `Agent`)
- `skills/wire-issue/SKILL.md:53-75` — flag parsing pseudocode (`--auto`, `--dry-run`, ISSUE_ID extraction via for-loop skipping `--` tokens)
- `skills/wire-issue/SKILL.md:80-88` — issue location: `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`
- `skills/wire-issue/SKILL.md:123-202` — parallel Agent spawn pattern (all agents in single message, named blocks `### Agent 1/2/3`, wait fence)
- `skills/confidence-check/SKILL.md:398-446` — frontmatter inline `---` block replacement via Edit tool (read existing block, replace entire span)
- `skills/format-issue/SKILL.md:163-175` — idempotency rule: skip write if field already has same value
- `skills/manage-issue/SKILL.md:157-191` — HALT (`✗`) / WARN (`⚠`) / PROCEED (`✓`) gate pattern; model for `--dry-run` gate behavior
- `commands/refine-issue.md:265-274` — 3 option-extraction patterns: numbered (`1.`/`2.`), section headers (`### Option A`), bold labels (`**Option A**`)

### Option Extraction Test Cases (Verify Extraction Logic Against These)
- `.issues/completed/P2-BUG-903-llm-structured-eval-1800s-timeout-causes-30-min-hang-on-api-failure.md:65-78` — `**Option A** / **Option B**` bold label pattern
- `.issues/completed/P2-BUG-579-cleanup-orphaned-worktrees-ignores-active-worktrees-guard.md:58-62` — three-option `**Option A/B/C**` pattern
- `.issues/completed/P3-ENH-746-sprint-planner-serializes-issues-ll-deps-marks-parallel-safe.md:36-39` — four-option `**Option A/B/C/D**` pattern

### Scoring Output Table Pattern
- `commands/tradeoff-review-issues.md:275-285` — `| Dimension | Score |` table format for per-option output
- `skills/confidence-check/SKILL.md:191-218` — `| Finding | Score |` per-criterion lookup table pattern

### Session Log
- `/ll:wire-issue` - 2026-04-21T21:49:55 - `4b71009e-1245-442e-8210-a12a28e421cb.jsonl`
- `/ll:refine-issue` - 2026-04-21T21:44:59 - `2df8ac52-83e1-4537-b68b-63c1c9cf06c6.jsonl`
- `skills/wire-issue/SKILL.md:367` — canonical `ll-issues append-log <path> /ll:decide-issue` invocation pattern

## Session Log
- `/ll:manage-issue` - 2026-04-21T21:58:42 - `78577e96-20d7-452e-b860-d6aa41e5a790.jsonl`
- `/ll:ready-issue` - 2026-04-21T21:53:42 - `4eb56bac-9901-4808-9ce3-1ce85ecc5f08.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `1901ce73-231e-40a8-9a01-102702314b6c.jsonl`

## Files to Create/Modify

- `skills/decide-issue/SKILL.md` — **new file** (primary deliverable)
- `commands/refine-issue.md` — update NEXT STEPS (lines 448-451) to conditionally suggest `/ll:decide-issue` when `decision_needed: true`; update Pipeline Position (lines 477-479) [unallocated wiring gap]
- `skills/wire-issue/SKILL.md` — update Pipeline Position (lines 453-455) and NEXT STEPS block (lines 438-442) to include `decide-issue` between `refine-issue` and `wire-issue` [unallocated wiring gap]

## Implementation Steps

1. Create `skills/decide-issue/` directory (via Bash)
2. Write `skills/decide-issue/SKILL.md` YAML frontmatter: `description`, `model: sonnet`, `allowed-tools` (include `Agent`) — model after `skills/wire-issue/SKILL.md:1-18`
3. Write Phase 1 (flag parsing): pseudocode for `--auto`, `--dry-run`, ISSUE_ID extraction — model after `skills/wire-issue/SKILL.md:53-75`
4. Write Phase 2 (issue location): `ll-issues path "${ISSUE_ID}"` shell block with empty-check guard — model after `skills/wire-issue/SKILL.md:80-88`
5. Write Phase 3 (option extraction): implement all 3 detection patterns from `commands/refine-issue.md:265-274`; validate output against test cases in `.issues/completed/P2-BUG-903-*.md:65-78`
6. Write Phase 4 (evidence gathering): spawn one `ll:codebase-pattern-finder` Agent per option in a **single message** — model agent spawn blocks after `skills/wire-issue/SKILL.md:123-202`
7. Write Phase 5 (scoring + selection): 4 dimensions (consistency, simplicity, testability, risk; 0–3 each, 12 max); use `| Dimension | Score |` table format from `commands/tradeoff-review-issues.md:275-285`
8. Write Phase 6 (annotation): mark selected option with `> **Selected:** [option title]` callout; append `### Decision Rationale` with per-option scoring table
9. Write Phase 7 (frontmatter update): set `decision_needed: false` via Edit tool inline `---` replacement — model after `skills/confidence-check/SKILL.md:398-446`; apply idempotency check per `skills/format-issue/SKILL.md:163-175`
10. Write Phase 8 (`--dry-run` gate): gate all writes; print preview with HALT/WARN/PROCEED sigils — model after `skills/manage-issue/SKILL.md:157-191`
11. Write Phase 9 (session log): `ll-issues append-log <path-to-issue-file> /ll:decide-issue` — model after `skills/wire-issue/SKILL.md:367`
12. Write Phase 10 (output report): `=====` bordered report with options scored, decision made, `decision_needed` status, and next steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

13. Update `commands/refine-issue.md` — add conditional `/ll:decide-issue` suggestion to NEXT STEPS output block (lines 448-451) and update Pipeline Position diagram (lines 477-479) to include `decide-issue`
14. Update `skills/wire-issue/SKILL.md` — update Pipeline Position section (lines 453-455) and NEXT STEPS block (lines 438-442) to include `decide-issue` between `refine-issue` and `wire-issue`

## Impact

- **Priority**: P3
- **Effort**: Medium — novel option-extraction and scoring logic in a new skill
- **Risk**: Low — reads and writes issue files only
- **Breaking Change**: No

## Labels

`feature`, `pipeline`, `automation`

---

**Completed** | Created: 2026-04-21 | Priority: P3

## Resolution

**Status**: Completed 2026-04-21

**Changes Made**:
- Created `skills/decide-issue/SKILL.md` — full skill with 9 phases: argument parsing, issue location, option extraction (3 patterns), parallel evidence gathering via `codebase-pattern-finder` agents, 4-dimension scoring, annotation with `> **Selected:**` callout and `### Decision Rationale` table, frontmatter update (`decision_needed: false`), session log, and output report
- Updated `commands/refine-issue.md` NEXT STEPS block to conditionally suggest `/ll:decide-issue` when `decision_needed: true` is set; updated Pipeline Position diagram to include `decide-issue`
- Updated `skills/wire-issue/SKILL.md` Pipeline Position and Before/After section to include `decide-issue` between `refine-issue` and `wire-issue`; added note to NEXT STEPS about running `decide-issue` first if `decision_needed: true`
