---
id: ENH-1847
title: Wire ll-history-context into refine-issue, ready-issue, and confidence-check
type: ENH
priority: P3
status: done
parent: ENH-1708
depends_on:
- ENH-1846
labels:
- enhancement
size: Medium
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-06-01 10:51:56+00:00
---

# ENH-1847: Wire ll-history-context into refine-issue, ready-issue, and confidence-check

## Summary

Add `ll-history-context` query steps to the three refinement skills so they surface "have I been told this before about this issue?" context. Includes allowed-tools sync for bridge stubs, unit tests per skill, skill-level documentation, and CHANGELOG entry.

## Current Behavior

The three refinement skills (`refine-issue`, `ready-issue`, `confidence-check`) operate without access to historical correction data. The `allowed-tools` frontmatter of `commands/refine-issue.md`, `commands/ready-issue.md`, `skills/confidence-check/SKILL.md`, and their bridge stubs (`skills/ll-refine-issue/SKILL.md`, `skills/ll-ready-issue/SKILL.md`) do not include `Bash(ll-history-context:*)`. Prior corrections surfaced by users are not visible to these skills during execution.

## Expected Behavior

After implementation each skill queries `ll-history-context {{issue_id}}` at the appropriate phase. When prior corrections exist, a `## Historical Context` block is injected into the skill's prompt context. All five files include `Bash(ll-history-context:*)` in their `allowed-tools` frontmatter. Graceful degradation: when the DB is absent or returns no matches, skills continue without the section (zero bytes added to prompt).

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

## Scope Boundaries

Explicitly out of scope for this issue:
- `ll-history-context` CLI implementation (covered by ENH-1846)
- Changes to `scripts/little_loops/history_reader.py` or the event bus / history recording pipeline
- Wiring history context into skills beyond `refine-issue`, `ready-issue`, and `confidence-check`
- New configuration options, UI changes, or modifications to the scoring model beyond the −0.1 per-correction signal

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7a. Add `scripts/tests/test_enh1847_doc_wiring.py` — new doc-wiring test file verifying `Bash(ll-history-context:*)` in the `allowed-tools` frontmatter of all 5 modified files; follow the `test_enh1362_doc_wiring.py` pattern (read frontmatter via `content[:content.index("---", 3)]`, assert `"Bash(ll-history-context:*)" in fm`)
7b. When writing new Step 2.5 in `commands/refine-issue.md`, avoid any `filename.ext:lineno` patterns in prose — `test_enh1299_doc_wiring.py` asserts these are absent from the file

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

### Files to Modify (continued)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1847_doc_wiring.py` — **new file** — verify `Bash(ll-history-context:*)` present in `allowed-tools` frontmatter of all 5 files (`commands/refine-issue.md`, `commands/ready-issue.md`, `skills/confidence-check/SKILL.md`, `skills/ll-refine-issue/SKILL.md`, `skills/ll-ready-issue/SKILL.md`); follow `test_enh1362_doc_wiring.py:TestAlignIssuesFrontmatter.test_ll_issues_in_allowed_tools()` pattern [wiring pass]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1299_doc_wiring.py` — reads `commands/refine-issue.md`, asserts no `file:line` patterns (`TestRefineIssueCommandNoFileLine`); **must not break** — ensure new Step 2.5 text contains no `filename.ext:lineno` references [existing test, may break]
- `scripts/tests/test_enh1550_doc_wiring.py` — reads `commands/ready-issue.md` and `commands/refine-issue.md`, asserts `**Status enum**:` present; **must not break** — ensure these lines are not removed during edits [existing test, may break]
- `scripts/tests/test_enh1433_doc_wiring.py` — reads `skills/confidence-check/SKILL.md`, asserts canonical vocab (`parent: EPIC-NNN` present, `parent_issue:` absent); **must not break** — no vocab changes expected [existing test, may break]

### Reference (Read-Only)
- `scripts/little_loops/history_reader.py` — underlying query functions
- `scripts/tests/test_history_reader.py` — fixture patterns to copy
- `scripts/tests/test_confidence_check_skill.py` — `_phase_text()` structural pattern for new test classes
- `scripts/tests/test_history_context_cli.py` — CLI test pattern (DB seeding via `record_correction()`, `capsys` capture, `## Historical Context` assertion)
- `scripts/tests/test_enh1362_doc_wiring.py` — `allowed-tools` frontmatter assertion pattern to follow for `test_enh1847_doc_wiring.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Current `allowed-tools` state (pre-modification):**
- `commands/refine-issue.md`: `Bash(git:*, ll-issues:*)` as one merged item — add `Bash(ll-history-context:*)` as a new separate list entry
- `commands/ready-issue.md`: `Bash(git:*)` only — add `Bash(ll-history-context:*)` as a new separate list entry
- `skills/confidence-check/SKILL.md` (lines 6–12): two split entries `Bash(find:*)` and `Bash(git:*)` — add `Bash(ll-history-context:*)` as a third split entry to match the existing pattern
- `skills/ll-refine-issue/SKILL.md`: **`allowed-tools` key is entirely absent** — must create the full `allowed-tools:` block from scratch mirroring `commands/refine-issue.md` (Step 4 says "add if absent" but the key itself does not exist)
- `skills/ll-ready-issue/SKILL.md`: **`allowed-tools` key is entirely absent** — same; must create from scratch mirroring `commands/ready-issue.md`

**Test file pre-conditions:**
- `scripts/tests/test_ready_issue_lint.py` currently has **no `PROJECT_ROOT` or `COMMAND_FILE` module-level constants** (three tests operate on inline string fixtures only) — must add `PROJECT_ROOT = Path(__file__).parent.parent.parent` and `COMMAND_FILE = PROJECT_ROOT / "commands" / "ready-issue.md"` before `TestReadyIssueHistoryContextInjection` can slice into the file
- `scripts/tests/test_refine_issue_command.py` already has `PROJECT_ROOT` and `COMMAND_FILE` at module level — no boilerplate needed for the new class

**Exact heading strings for structural test assertions (`content.index()`):**
- `commands/refine-issue.md` new step: `### 2.5 — Query Historical Context` (note em-dash `—`)
- `commands/ready-issue.md` target section: `### 2. Validate Issue Content`
- `skills/confidence-check/SKILL.md` target section: `### Phase 1: Gather Context`

**`_phase_text()` boundary pattern** (copy from `test_confidence_check_skill.py:TestConfidenceCheckPhase4CLI._phase_text()`):
- Right boundary: `content.find("\n###", start + 1)` for phase-named headings (confidence-check)
- Right boundary variant: `content.find("\n### 3.", start + 1)` for numbered steps (refine-issue Step 2.5 → next is Step 3)
- Right boundary variant: `content.find("\n### 3.", start + 1)` for ready-issue Step 2 → next is Step 3

## Impact

- **Priority**: P3 — Improves refinement quality by surfacing prior user corrections; not blocking
- **Effort**: Medium — Modifies 5 command/skill files and adds 4 test files with structural assertions
- **Risk**: Low — Additive changes only; graceful degradation if DB is absent; no changes to existing skill logic
- **Breaking Change**: No

## Notes

- This child is strictly sequential after ENH-1846 — `ll-history-context` must be installed before skill tests can call it
- `tdd_mode: true` is active — wiring (allowed-tools, bridge stub sync) belongs in this issue alongside the skill modifications; do not split them

## Session Log
- `/ll:ready-issue` - 2026-06-01T10:44:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3bcd7db2-479f-4bd7-849e-a08f485cdf0b.jsonl`
- `/ll:wire-issue` - 2026-06-01T10:39:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3577710b-49d5-4e73-b489-706d2683bcc2.jsonl`
- `/ll:refine-issue` - 2026-06-01T10:33:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/353e8d6f-0bad-4ffd-ad51-df1444d5af58.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d65087d-00c0-4a66-9066-5e5d9ee479f5.jsonl`

---

**Open** | Created: 2026-06-01 | Priority: P3
