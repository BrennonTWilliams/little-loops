---
id: ENH-1343
type: ENH
priority: P3

confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-03T05:31:31Z
parent: ENH-1336
status: done
---

# ENH-1343: Documentation Wiring for All 5 Signals in `/ll:analyze-loop` (COMMANDS.md, Tests, README)

## Summary

Update `docs/reference/COMMANDS.md` with all 5 effectiveness signal descriptions and the two-group output format (`Fault Signals` / `Effectiveness Signals`); update `test_enh1268_doc_wiring.py` assertions; update `README.md` Quick Reference table entry.

## Parent Issue

Decomposed from ENH-1336: Add Effectiveness Signals 4-5, Fixtures, and Documentation Wiring to `/ll:analyze-loop`

## Pre-requisites

**This child must follow**:
- ENH-1335 — establishes Step 5 output grouping in SKILL.md and its own COMMANDS.md signal entries (Signals 1-3); this child's COMMANDS.md update must build on that.
- ENH-1342 — implements Signals 4-5 in SKILL.md; COMMANDS.md should document the complete set.

## Implementation Steps

1. **COMMANDS.md update** (`docs/reference/COMMANDS.md`):
   - Add all 5 signal descriptions to the "Signal detection rules:" list under `### \`/ll:analyze-loop\``.
   - Update the "Output format:" block to show `Fault Signals (N):` / `Effectiveness Signals (M):` two-group layout (established by ENH-1335).
   - Update the Quick Reference table entry (currently line 746, text: "failure signals") to reflect effectiveness coverage — replace "failure signals" with language that covers both fault and effectiveness signals.

2. **Test wiring: `test_enh1268_doc_wiring.py`** (`scripts/tests/test_enh1268_doc_wiring.py`):
   - Update `TestAnalyzeLoopCommandsWiring` to assert `"Fault Signals"` and `"Effectiveness Signals"` grouping strings appear in the `_analyze_loop_section` slice of COMMANDS.md.
   - The 6 existing string-presence tests must remain passing.

3. **README.md update** (`README.md`):
   - Line 227, commands table: `analyze-loop`^ row — update "from failures" to match whatever language replaces "failure signals" in the COMMANDS.md Quick Reference table.

## Codebase Research Findings

**Key files**:
- `docs/reference/COMMANDS.md` — target section: `### \`/ll:analyze-loop\`` (lines 529-578); Quick Reference table entry at line 746
- `scripts/tests/test_enh1268_doc_wiring.py` — `TestAnalyzeLoopCommandsWiring._analyze_loop_section` slices from `"### \`/ll:analyze-loop\`"` to next `"\n### \`"` heading; 6 existing `assert "<string>" in section` tests
- `README.md` — line 227 (`analyze-loop`^ row, "from failures" language)

**Wiring guard**: `TestAnalyzeLoopCommandsWiring._analyze_loop_section` is the slice helper — new `"Fault Signals"` / `"Effectiveness Signals"` strings must appear within that slice range.

**Guardrail**: After COMMANDS.md edits, run `scripts/tests/test_enh1146_doc_wiring.py` to confirm `TestCommandsWiring.test_rate_limit_waiting_present` still passes (asserts `"rate_limit_waiting"` survives in COMMANDS.md).

### Added by `/ll:refine-issue` — verified codebase state (2026-05-03)

**Canonical signal list (from `skills/analyze-loop/SKILL.md:380`)** — the source of truth that COMMANDS.md must mirror:

- **Fault Signals** (BUG-class — broke the run): action failure, SIGKILL, FATAL_ERROR, evaluate failure, sub-loop verdict discarded, rate-limit exhaustion. The retry flood and slow state rules currently sit in COMMANDS.md fault list (lines 540, 542) but are categorized as Effectiveness in SKILL.md — confirm classification before moving.
- **Effectiveness Signals** (ENH-class — completed but did not do useful work): stub action (Step 2 `static_issues`), retry flood, slow state, iter-1 convergence without apply, degenerate gate, capture vacuum, numeric trajectory stall.

**The "5" in this issue's title** = the 5 NEW effectiveness signals introduced by ENH-1335 (Signals 1-3: stub action, iter-1 convergence, degenerate gate) + ENH-1342 (Signals 4-5: capture vacuum, numeric trajectory stall). Pre-existing signals like retry flood and slow state are already in COMMANDS.md and only need re-grouping.

**Exact COMMANDS.md edit locations** (verified):
- Lines 536-545: "Signal detection rules:" bullet list — append the 5 new effectiveness signal descriptions; consider adding a sub-heading or visual divider between Fault and Effectiveness rules.
- Lines 548-562: "Output format:" block — extend the example fenced code block to include `### Fault Signals (N)` and `### Effectiveness Signals (M)` headings (mirror `SKILL.md:388,394` exactly).
- Line 746: Quick Reference table cell — current text "Analyze loop execution history: synthesizes an Execution Summary (goal alignment, observed path) and extracts actionable issues from failure signals". Replace "failure signals" with language covering both groups (e.g., "fault and effectiveness signals").

**Existing test strings that must remain present** (`test_enh1268_doc_wiring.py:25-65`) — do not remove these substrings from the `### \`/ll:analyze-loop\`` slice:
1. `"Execution Summary"`
2. `"**Loop goal**"`
3. `"**Observed path**"`
4. `"**Goal alignment**"`
5. `"--resolved"`
6. `"Sub-loop verdict discarded"`

**README.md line 227 current text** (verified): `| `analyze-loop`^ | Automation & Loops | Analyze loop execution history to synthesize actionable issues from failures |` — replace "from failures" to mirror whatever language is chosen for the COMMANDS.md Quick Reference cell at line 746.

**Prerequisite status (housekeeping note)**: ENH-1335 and ENH-1342 issue files are still in `.issues/enhancements/` (not moved to `completed/`), but the underlying SKILL.md work appears complete — `skills/analyze-loop/SKILL.md` already contains Fault/Effectiveness output grouping (lines 388, 394), Step 2 `static_issues` references (line 119), and capture vacuum + numeric trajectory stall (line 380). This child can proceed; the parent housekeeping is orthogonal.

## Tests

- `scripts/tests/test_enh1268_doc_wiring.py` — new `"Fault Signals"` / `"Effectiveness Signals"` assertions; 6 existing assertions must remain passing
- `scripts/tests/test_enh1146_doc_wiring.py` — guardrail: `TestCommandsWiring.test_rate_limit_waiting_present` must pass after COMMANDS.md edits

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1268_doc_wiring.py` — `TestAssessLoopCommandsWiring` (5 assertions on the `### \`/ll:assess-loop\`` section) lives in the same file; must not break when the file is modified; its `_assess_loop_section()` slice is independent of the analyze-loop edits so no changes are needed, but preservation must be verified [Agent 1 + 3 finding]
- New test method naming convention to follow (pattern from `test_subloop_verdict_discarded_signal_present`):
  - `test_fault_signals_grouping_present` — asserts `"Fault Signals" in self._analyze_loop_section()`
  - `test_effectiveness_signals_grouping_present` — asserts `"Effectiveness Signals" in self._analyze_loop_section()` [Agent 3 finding]

## Acceptance Criteria

- [x] `docs/reference/COMMANDS.md` updated with all 5 signal descriptions and two-group output format.
- [x] `docs/reference/COMMANDS.md` Quick Reference table entry updated (no "failure signals" language).
- [x] `test_enh1268_doc_wiring.py` passes with new `"Fault Signals"` / `"Effectiveness Signals"` assertions.
- [x] 6 existing `TestAnalyzeLoopCommandsWiring` assertions still pass.
- [x] `README.md` line 227 updated to match COMMANDS.md Quick Reference language.
- [x] `TestCommandsWiring.test_rate_limit_waiting_present` guardrail still passes.

## Resolution

**Status**: Completed 2026-05-03

**Changes**:
- `docs/reference/COMMANDS.md` — `/ll:analyze-loop` section: opener mentions both fault and effectiveness; signal rules split into `_Fault Signals_` and `_Effectiveness Signals_` sub-lists; output-format fenced block extended with `### Fault Signals (N)` and `### Effectiveness Signals (M)` headings (mirrors `skills/analyze-loop/SKILL.md:388,394`). Added 5 new effectiveness signal rules: stub action (Signal 3, static `static_issues`), iter-1 convergence without apply (Signal 1), degenerate gate route distribution (Signal 2), capture vacuum (Signal 4), numeric trajectory stall (Signal 5). Quick Reference table line 746 — "from failure signals" → "from fault and effectiveness signals".
- `README.md` line 227 — "from failures" → "from fault and effectiveness signals" to mirror COMMANDS.md.
- `scripts/tests/test_enh1268_doc_wiring.py` — added `test_fault_signals_grouping_present` and `test_effectiveness_signals_grouping_present` to `TestAnalyzeLoopCommandsWiring`. All 8 analyze-loop assertions pass; 5 `TestAssessLoopCommandsWiring` assertions in same file still pass; `test_enh1146_doc_wiring.py::TestCommandsWiring::test_rate_limit_waiting_present` guardrail still passes.

**Verification**: 23 wiring assertions across `test_enh1268_doc_wiring.py` and `test_enh1146_doc_wiring.py` pass. Full test suite: 5654 passed, 2 pre-existing failures in `TestMarketplaceVersionSync` (plugin.json/marketplace.json version drift, handled by `/ll:publish` — unrelated to this issue's scope).

## Depends On

- ENH-1335 — establishes COMMANDS.md output grouping format.
- ENH-1342 — implements Signals 4-5; COMMANDS.md documents all 5.

## Scope Boundaries

- **In scope**: COMMANDS.md signal descriptions + output format; test_enh1268_doc_wiring.py assertions; README.md Quick Reference update.
- **Out of scope**: SKILL.md changes (ENH-1342); Signals 1-3 implementation (ENH-1335); `--json` flag; fixtures.

## Session Log
- `/ll:confidence-check` - 2026-05-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/496da408-31c6-46ba-9a87-5e3336048b94.jsonl`
- `/ll:wire-issue` - 2026-05-03T05:23:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f50de2fe-7597-4306-8d07-ecbda1841ebb.jsonl`
- `/ll:refine-issue` - 2026-05-03T05:18:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b44fda6f-3ef7-4991-982e-3d97f2453588.jsonl`
- `/ll:issue-size-review` - 2026-05-03T04:56:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8af1a3a1-23af-4c82-98e3-c5e3dde0272f.jsonl`
- `/ll:manage-issue` - 2026-05-03T05:31:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44b9e848-feff-4e5f-bb71-12f173ddc2a0.jsonl`
