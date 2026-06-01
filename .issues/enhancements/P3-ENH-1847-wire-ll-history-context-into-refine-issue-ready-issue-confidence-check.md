---
id: ENH-1847
title: Wire ll-history-context into refine-issue, ready-issue, and confidence-check
type: ENH
priority: P3
status: open
parent: ENH-1708
depends_on:
- ENH-1846
labels:
- enhancement
size: Medium
---

# ENH-1847: Wire ll-history-context into refine-issue, ready-issue, and confidence-check

## Summary

Add `ll-history-context` query steps to the three refinement skills so they surface "have I been told this before about this issue?" context. Includes allowed-tools sync for bridge stubs, unit tests per skill, skill-level documentation, and CHANGELOG entry.

## Parent Issue
Decomposed from ENH-1708: Wire user_corrections + FTS5 Reads into refine-issue / ready-issue / confidence-check

## Prerequisite

ENH-1846 must be complete before this issue begins — the `ll-history-context` CLI must be installed for skill tests to exercise the real tool call.

With `tdd_mode: true`, wiring (integration points, allowed-tools entries, permission hooks) belongs here alongside the skill modifications — the integration test that drives the wiring is part of the TDD cycle.

## Scope

This child covers **Implementation Steps 2, 3, 4, 6, 7, 11** from ENH-1708:

- Step 2: Modify `commands/refine-issue.md`
- Step 3: Modify `commands/ready-issue.md`
- Step 4: Modify `skills/confidence-check/SKILL.md`
- Step 6: Add per-skill tests (three test files)
- Step 7: Update SKILL.md docs for each skill
- Step 11: Update `CHANGELOG.md`

Bridge stubs (allowed-tools sync) are also in scope.

## Implementation Steps

### 1. Modify `commands/refine-issue.md`

Add Step 2.5 "Query Historical Context" between "Analyze Issue Content" and "Research Codebase":

```markdown
### Step 2.5 — Query Historical Context

Run:
```bash
HIST=$(ll-history-context {{issue_id}} 2>/dev/null || true)
```

If `$HIST` is non-empty, include the output as a `## Historical Context` section in the prompt context for Step 5a gap-filling. Cap: already enforced by the CLI (5 rows max). If DB is missing or no matches, proceed without the section.
```

Add `Bash(ll-history-context:*)` to the `allowed-tools` frontmatter.

### 2. Modify `commands/ready-issue.md`

Add DB query step to Step 2 "Validate Issue Content":

```markdown
Before running validation checks, query for prior corrections:

```bash
HIST=$(ll-history-context {{issue_id}} 2>/dev/null || true)
```

If matches exist, add each correction as a `Historical Concerns` sub-bullet in the validation checklist with severity `warning`. Graceful degradation: if DB missing, skip section silently.
```

Add `Bash(ll-history-context:*)` to `allowed-tools`.

### 3. Modify `skills/confidence-check/SKILL.md`

Add DB query in Phase 1 "Gather Context" after the issue file is loaded (currently lines 6–12 list allowed tools: `Read`, `Glob`, `Grep`, `Edit`, `Bash(find:*)`, `Bash(git:*)`):

```markdown
After loading the issue file, run:

```bash
HIST=$(ll-history-context {{issue_id}} 2>/dev/null || true)
```

Each matched correction is a −0.1 signal on the Outcome Confidence Score. Cap: at most 5 corrections included; if 0 matches, Outcome Confidence Score is unaffected.
```

Add `Bash(ll-history-context:*)` to `allowed-tools`.

### 4. Sync bridge stubs

- `skills/ll-refine-issue/SKILL.md` — verify `allowed-tools` frontmatter matches `commands/refine-issue.md`; add `Bash(ll-history-context:*)` if absent
- `skills/ll-ready-issue/SKILL.md` — same sync for `commands/ready-issue.md`

### 5. Add per-skill tests

#### `scripts/tests/test_refine_issue_command.py`

Add class `TestRefineIssueHistoryContextInjection`:
- Verify Step 2.5 instruction text is present in the Phase 2 section
- Use `_phase_text()` structural pattern from `test_confidence_check_skill.py`: index by section heading, slice to next heading, assert instruction text present

#### `scripts/tests/test_ready_issue_lint.py`

Add class `TestReadyIssueHistoryContextInjection`:
- Verify DB query instruction is present in the Step 2 validation section
- Note: this file is sparse (3 tests) — follow `test_confidence_check_skill.py` structural assertion pattern

#### `scripts/tests/test_confidence_check_skill.py`

Add class `TestConfidenceCheckHistoryContextInjection`:
- Verify Phase 1 DB query instruction and −0.1 correction signal instruction are present
- Follow existing `TestConfidenceCheckPhase4CLI._phase_text()` pattern

### 6. Update skill-level documentation

- `skills/confidence-check/SKILL.md` — document the new `## Historical Context` section in Phase 1: when it appears, the −0.1 scoring signal, and the byte-cap guarantee
- `commands/refine-issue.md` — document new Step 2.5 in the step listing
- `commands/ready-issue.md` — document the new `Historical Concerns` validation check

### 7. Update `CHANGELOG.md`

Add entry covering:
- Three skill wiring additions (refine-issue, ready-issue, confidence-check)
- `ll-history-context` CLI (from ENH-1846)

## Acceptance Criteria

- `refine-issue`, `ready-issue`, and `confidence-check` each include a `## Historical Context` section in their generated prompts when matches exist
- Each skill's `allowed-tools` includes `Bash(ll-history-context:*)`
- Bridge stubs (`ll-refine-issue`, `ll-ready-issue`) have matching `allowed-tools`
- Each skill has tests covering: matches present (via `## Historical Context` section appearing), no matches (section absent), structural assertion on the instruction text
- Each skill's documentation describes the new section and when it appears
- Per-skill prompt-byte impact when no matches: 0 bytes added (CLI returns empty)
- `CHANGELOG.md` updated

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — add Step 2.5, add `Bash(ll-history-context:*)` to allowed-tools
- `commands/ready-issue.md` — add DB query to Step 2, add `Bash(ll-history-context:*)` to allowed-tools
- `skills/confidence-check/SKILL.md` — add Phase 1 DB query, add `Bash(ll-history-context:*)` to allowed-tools
- `skills/ll-refine-issue/SKILL.md` — bridge stub allowed-tools sync
- `skills/ll-ready-issue/SKILL.md` — bridge stub allowed-tools sync
- `scripts/tests/test_refine_issue_command.py` — add `TestRefineIssueHistoryContextInjection`
- `scripts/tests/test_ready_issue_lint.py` — add `TestReadyIssueHistoryContextInjection`
- `scripts/tests/test_confidence_check_skill.py` — add `TestConfidenceCheckHistoryContextInjection`
- `CHANGELOG.md` — add entry for CLI + skill wiring

### Reference (Read-Only)
- `scripts/little_loops/history_reader.py` — underlying query functions
- `scripts/tests/test_history_reader.py` — fixture patterns to copy
- `scripts/tests/test_confidence_check_skill.py` — `_phase_text()` structural pattern for new test classes

## Notes

- This child is strictly sequential after ENH-1846 — `ll-history-context` must be installed before skill tests can call it
- `tdd_mode: true` is active — wiring (allowed-tools, bridge stub sync) belongs in this issue alongside the skill modifications; do not split them

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

**Open** | Created: 2026-06-01 | Priority: P3
