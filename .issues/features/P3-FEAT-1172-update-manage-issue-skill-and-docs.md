---
id: FEAT-1172
type: FEAT
priority: P3
status: done
completed_at: 2026-04-18T21:11:47Z
discovered_date: 2026-04-18
discovered_by: issue-size-review
parent: FEAT-1162
size: Small
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1172: Update `manage-issue` Skill and Documentation for `completed_at`

## Summary

Add an Edit-tool step for `completed_at` injection to `skills/manage-issue/SKILL.md`, add a `completed_at` row to the frontmatter fields table in `docs/reference/ISSUE_TEMPLATE.md`, and document `update_frontmatter` in `docs/reference/API.md`.

## Parent Issue

Decomposed from FEAT-1162: Add `completed_at` Timestamp in All Completion Paths (now completed, moved to `.issues/completed/P3-FEAT-1162-completed-at-timestamp-in-completion-paths.md`).

**Sibling status** (from `/ll:refine-issue` research, 2026-04-18):
- FEAT-1169 (`update_frontmatter` utility + tests) — **completed**, implementation at `scripts/little_loops/frontmatter.py:106-129`
- FEAT-1170 (sequential lifecycle injection) — **completed**, call sites at `scripts/little_loops/issue_lifecycle.py:622,698`
- FEAT-1171 (parallel orchestrator injection) — **completed**, call site at `scripts/little_loops/parallel/orchestrator.py:1183-1187` (commit `2adc7e73`)
- FEAT-1172 (this issue) — **only remaining completion path** (interactive LLM-driven)

## Motivation

The interactive completion path (manage-issue skill) runs `git mv` directly via LLM instruction. Without an explicit step in the skill instructions, the LLM will not inject `completed_at`. The documentation also needs updating so `completed_at` is a recognized, documented field.

## Implementation Steps

1. **`skills/manage-issue/SKILL.md` (Phase 5, section `### 2. Move to Completed`, heading at line 407, `git mv` block at lines 411-414)**:
   - Insert a new sub-step *before* the existing `git mv` bash block
   - Direct the LLM to use the Edit tool to add `completed_at: <ISO timestamp>` to the issue's frontmatter
   - Timestamp value is obtained via shell: `date -u +"%Y-%m-%dT%H:%M:%SZ"` (Z-suffixed ISO 8601 UTC; matches `captured_at` precedent and the Python helper `_completed_at_now()` at `scripts/little_loops/issue_lifecycle.py:32-34`)
   - The instruction should be prose + a small bash/Edit snippet, consistent with the existing `### 1.5. Append Session Log Entry` step style at line 401
   - Precedent prose pattern: `skills/capture-issue/SKILL.md:235` ("…use shell `date -u +\"%Y-%m-%dT%H:%M:%SZ\"` format…")
   - Precedent frontmatter template: `skills/capture-issue/templates.md:132-139` (shell heredoc showing the Z-suffixed timestamp inside `---` fences)

2. **`docs/reference/ISSUE_TEMPLATE.md` (Frontmatter Fields table header at line 873, `captured_at` row at line 875)**:
   - Insert a `completed_at` row immediately after the `captured_at` row
   - Row content: `| \`completed_at\` | ISO 8601 UTC datetime | — | Set when issue is moved to \`completed/\` (by \`manage-issue\` skill, \`ll-auto\`, or \`ll-parallel\`) |`
   - Update the YAML example block at lines 893-900 to include a `completed_at: 2026-03-17T15:02:41Z` line after `captured_at`
   - Follow the existing column style (Field | Type | Default | Purpose; `—` in Default column for tooling-set fields)

3. **`docs/reference/API.md` — NO CHANGE NEEDED**:
   - Research 2026-04-18 confirms `update_frontmatter` is **already documented** at `docs/reference/API.md:4735-4757` (added by completed sibling FEAT-1169).
   - The `little_loops.frontmatter` module section runs from line 4698-4757 and already contains: module intro, Public Functions table listing `update_frontmatter`, full signature/parameters/returns/example subsection (the example already uses `completed_at` as its key).
   - **This step should be removed** from the issue. Keeping it as a verification-only step: confirm docs are current before marking the issue complete.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` — insert `completed_at` injection step in `### 2. Move to Completed` (before `git mv` at lines 411-414)
- `docs/reference/ISSUE_TEMPLATE.md` — add `completed_at` row to Frontmatter Fields table (after line 875) and extend YAML example at lines 893-900

### Files NOT to Modify (already done by completed siblings)
- `docs/reference/API.md:4735-4757` — `update_frontmatter` already documented (FEAT-1169); verify only
- `scripts/little_loops/frontmatter.py:106-129` — `update_frontmatter` implementation (FEAT-1169)
- `scripts/little_loops/issue_lifecycle.py:27-34,622,698` — sequential path injection (FEAT-1170)
- `scripts/little_loops/parallel/orchestrator.py:1183-1187` — parallel path injection (FEAT-1171)

### Precedent Patterns to Follow
- `skills/capture-issue/SKILL.md:235` — prose instruction form ("use shell `date -u +\"%Y-%m-%dT%H:%M:%SZ\"` format…")
- `skills/capture-issue/templates.md:132-139` — frontmatter heredoc showing the Z-suffixed ISO 8601 UTC timestamp inline
- `docs/reference/ISSUE_TEMPLATE.md:875` — `captured_at` table row as template for the new `completed_at` row
- `docs/reference/ISSUE_TEMPLATE.md:893-900` — YAML example block structure (bare Z-suffix timestamps, no quotes)

### Callers / Integration Surface
- The interactive completion path triggered when a user runs `/ll:manage-issue` and reaches Phase 5 (see `skills/manage-issue/SKILL.md:407`). This is the only completion path not already injecting `completed_at`; the two Python-driven paths (`ll-auto`, `ll-parallel`) are covered by FEAT-1170 / FEAT-1171.

### Tests
- No automated tests planned for the skill prose — the manage-issue skill is LLM-driven prose instructions, not executable code. Verification is manual: run `/ll:manage-issue` to completion on a test issue and confirm the moved file's frontmatter contains `completed_at`.
- Completed siblings already cover the Python code paths via `scripts/tests/test_issue_lifecycle.py` and `scripts/tests/test_orchestrator.py`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1172_doc_wiring.py` — new test file to write; asserts `completed_at` appears in the frontmatter table of `docs/reference/ISSUE_TEMPLATE.md`. Follow the pattern in `scripts/tests/test_enh1138_doc_wiring.py` (reads `docs/reference/API.md` and asserts a symbol is present). [Agent 3 finding]

### Documentation
- `docs/reference/ISSUE_TEMPLATE.md` — frontmatter registry (to modify)
- `docs/reference/API.md:4735-4757` — `update_frontmatter` reference (already current)
- `CHANGELOG.md` — release note entry when FEAT-1162 family ships (per memory: do not add under `[Unreleased]`; promote during release prep)

## Acceptance Criteria

- [x] `skills/manage-issue/SKILL.md` Phase 5 instructs the LLM to inject `completed_at` (ISO 8601 UTC, Z-suffixed, from `date -u +"%Y-%m-%dT%H:%M:%SZ"`) into the issue frontmatter **before** the `git mv` at lines 411-414
- [x] Injection step follows the prose + snippet style of the adjacent `### 1.5. Append Session Log Entry` step (consistent voice)
- [x] `docs/reference/ISSUE_TEMPLATE.md` Frontmatter Fields table includes a `completed_at` row after the `captured_at` row
- [x] `docs/reference/ISSUE_TEMPLATE.md` YAML example at lines 893-900 includes `completed_at: <ISO timestamp>` after the `captured_at` line
- [x] Manual verification: this issue itself is being completed with a `completed_at` timestamp, dogfooding the new skill step
- [x] `docs/reference/API.md:4735-4757` entry for `update_frontmatter` confirmed unchanged (no action beyond verification)

## Resolution

Implemented the final completion-path update for the FEAT-1162 family:

- Added a new sub-step `### 1.6. Inject completed_at Timestamp` to `skills/manage-issue/SKILL.md` directly before the existing `### 2. Move to Completed` block. Prose mirrors the `### 1.5. Append Session Log Entry` style and includes a YAML snippet and the shell `date -u +"%Y-%m-%dT%H:%M:%SZ"` command.
- Added a `completed_at` row to the Frontmatter Fields table in `docs/reference/ISSUE_TEMPLATE.md` (immediately after `captured_at`) and extended the adjacent YAML example block to include the new field.
- Verified `docs/reference/API.md:4735-4757` is already current from FEAT-1169 — no edit required.
- Added `scripts/tests/test_feat1172_doc_wiring.py` (per wiring phase) asserting `completed_at` is present in the frontmatter table, that `completed_at` and the `date -u` command appear in the manage-issue skill, and that `update_frontmatter` remains documented in API.md.

TDD was followed: the four new doc-wiring tests failed with assertions before the edits and pass after. Full suite: 4978 passed, 5 skipped. The one ruff warning and one mypy warning found are pre-existing (unrelated files).

## Session Log

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Create `scripts/tests/test_feat1172_doc_wiring.py` — a doc-wiring test asserting that `completed_at` appears in the `docs/reference/ISSUE_TEMPLATE.md` frontmatter fields table, following the pattern in `scripts/tests/test_enh1138_doc_wiring.py`

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-18T21:12:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d491456c-76f4-49f2-b873-5e4c42016793.jsonl`
- `/ll:manage-issue` - 2026-04-18T21:11:47Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d491456c-76f4-49f2-b873-5e4c42016793.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ec44b430-72d7-40d7-80da-a4758ee0bea7.jsonl`
- `/ll:wire-issue` - 2026-04-18T21:05:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc8fa437-a5ed-4e83-a696-6f08da57756c.jsonl`
- `/ll:refine-issue` - 2026-04-18T21:01:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7ab691fc-9228-4fdb-a8dd-351434afc882.jsonl`
- `/ll:issue-size-review` - 2026-04-18T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f4fec2da-840f-48eb-a5e3-fc86007899b8.jsonl`
