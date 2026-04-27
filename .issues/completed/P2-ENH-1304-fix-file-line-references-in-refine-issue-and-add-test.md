---
parent_issue: ENH-1299
discovered_date: "2026-04-27"
discovered_by: issue-size-review
decision_needed: false
missing_artifacts: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-04-27T18:43:56Z
---

# ENH-1304: Fix `file:line` references in `commands/refine-issue.md` and add verification test

## Summary

Edit `commands/refine-issue.md` to replace all `file:line`-style references with anchor-based equivalents, then write a structural test (`scripts/tests/test_enh1299_doc_wiring.py`) that asserts all five ENH-1299 target files are free of `file:line` strings.

## Parent Issue

Decomposed from ENH-1299: Fix `file:line` references in issue-authoring pipeline source files

## Current Behavior

- **`commands/refine-issue.md`**: 11 anti-patterns — 9 occurrences of `file:line` and 2 `SKILL.md:NNN-NNN` range references. Agent 2 and Agent 3 prompt blocks request `file:line` references; the `Gap Detection` table row reads "Which file:line contains the bug"; enrichment template, Research Summary, and Output Report sections use `file:line` placeholder language. Two additional line-range references (`skills/confidence-check/SKILL.md:398-446` and `skills/format-issue/SKILL.md:163-175`) need to be replaced with section anchors.

## Expected Behavior

- `commands/refine-issue.md`: Agent 2 and Agent 3 prompts updated to request function/class anchors; `Gap Detection` table row reads "Which function/class contains the bug"; all other `file:line` references updated to anchor-based equivalents.
- `scripts/tests/test_enh1299_doc_wiring.py`: New test asserting that all 5 target files (`agents/codebase-analyzer.md`, `agents/codebase-pattern-finder.md`, `skills/wire-issue/SKILL.md`, `skills/manage-issue/templates.md`, `commands/refine-issue.md`) contain zero `file:line` occurrences.

## Proposed Solution

1. **`commands/refine-issue.md`** (10 occurrences):
   - Update Agent 2 and Agent 3 prompt blocks to request anchors instead of `file:line` references
   - Update Gap Detection table row from "Which file:line contains the bug" to "Which function/class contains the bug"
   - Update enrichment template, Research Summary, and Output Report `file:line` language to anchor equivalents

2. **`scripts/tests/test_enh1299_doc_wiring.py`** (new file):
   - Follow the pattern in `scripts/tests/test_feat1172_doc_wiring.py` (path constants via `Path(__file__).parent.parent.parent`, class per file, `assert "file:line" not in content`)
   - Assert `"file:line"` is absent from all 5 target files

### Codebase Research Findings

**Established anchor patterns** (from `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`):
- Function: `` `in function foo()` `` or `` `in method ClassName.method_name()` ``
- Class: `` `in class ClassName` `` or `` `near class Bar` ``

**Exact occurrence counts (corrected — 11 total):**
- `commands/refine-issue.md`: 9 `file:line` + 2 `SKILL.md:NNN-NNN` = 11 anti-patterns

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Complete occurrence table:**

| Line | Anti-pattern | Section | Replacement |
|------|-------------|---------|-------------|
| 150 | `file:line references` | Agent 2 prompt | `file path and anchor references (e.g., function names, class names)` |
| 170 | `file:line references` | Agent 3 prompt | `file path and anchor references (e.g., function names, class names)` |
| 186 | `file:line` (table cell) | Gap Detection — BUGs table | `file and function/class` |
| 213 | `file:line references` | Gap Detection rule text | `file path and anchor references` |
| 272 | `SKILL.md:398-446` | Option-Count Detection note | `skills/confidence-check/SKILL.md` in section "Phase 4: Update Frontmatter" |
| 276 | `SKILL.md:163-175` | Idempotency note | `skills/format-issue/SKILL.md` in section "2.5a. Testable Inference (doc-only detection)" |
| 302 | `file:line reference` | Preservation Rule example block | `file path and anchor reference` |
| 303 | `file:line reference` | Preservation Rule example block | `file path and anchor reference` |
| 320 | `file:line` | Research Summary output template | `file in function/class anchor` |
| 429 | `file:line reference` | Output Report SECTIONS ENRICHED block | `file path and anchor reference` |
| 440 | `file:line reference` | Output Report DRY RUN PREVIEW block | `file path and anchor reference` |

**Test pattern reference**: `scripts/tests/test_feat1172_doc_wiring.py` — path constants via `Path(__file__).parent.parent.parent`, class per file, `assert "file:line" not in content`

**Other existing doc-wiring test files to consult:**
- `scripts/tests/test_enh1130_doc_wiring.py` — uses `not in` pattern for absence assertions
- `scripts/tests/test_enh1268_doc_wiring.py` — uses section-scoped helper methods
- `scripts/tests/test_enh1138_doc_wiring.py`, `test_enh1146_doc_wiring.py` — standard multi-class pattern

## Integration Map

### Files to Modify

- `commands/refine-issue.md`

### Files to Create

- `scripts/tests/test_enh1299_doc_wiring.py`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_issue_command.py` — reads `commands/refine-issue.md` via `COMMAND_FILE = PROJECT_ROOT / "commands" / "refine-issue.md"` and asserts on section headings (`"### 5a. Fill Gaps with Research Findings"`, `"Option-Count Detection"`, `"Idempotency"`, etc.). These headings are not among the 11 anti-patterns being removed, so no update is needed — but verify after editing that its assertions still pass. [Agent 1 finding]

### Verification

```bash
grep -n "file:line" commands/refine-issue.md
# Should return zero matches

python -m pytest scripts/tests/test_enh1299_doc_wiring.py -v
# Should pass only after ENH-1302, ENH-1303, and this issue are all complete

python -m pytest scripts/tests/test_refine_issue_command.py -v
# Should continue to pass — verify no accidental breakage
```

## Implementation Steps

1. Edit `commands/refine-issue.md` (11 anti-patterns):
   - Lines 150, 170: Update Agent 2 and Agent 3 prompts to request `file path and anchor references (e.g., function names, class names)`
   - Line 186: Update Gap Detection BUGs table row to `file and function/class`
   - Line 213: Update Gap Detection rule text to `file path and anchor references`
   - Line 272: Replace `skills/confidence-check/SKILL.md:398-446` with anchor: `skills/confidence-check/SKILL.md` in section "Phase 4: Update Frontmatter"
   - Line 276: Replace `skills/format-issue/SKILL.md:163-175` with anchor: `skills/format-issue/SKILL.md` in section "2.5a. Testable Inference (doc-only detection)"
   - Lines 302, 303, 320, 429, 440: Replace remaining `file:line reference` strings with `file path and anchor reference`
2. Write `scripts/tests/test_enh1299_doc_wiring.py` — follow `test_feat1172_doc_wiring.py` pattern: `PROJECT_ROOT = Path(__file__).parent.parent.parent`, one class per target file, `assert "file:line" not in content`.
3. Run `grep -n "file:line\|SKILL\.md:[0-9]" commands/refine-issue.md` — should return zero matches.

## Impact

- **Priority**: P2
- **Effort**: Small — text edits + one new test file
- **Risk**: Very low — reversible; changes only affect command prompts
- **Breaking Change**: No
- **Note**: The test added here will fail until ENH-1302 and ENH-1303 are also complete; it serves as the acceptance gate for the full ENH-1299 scope.

## Success Metrics

- Zero `file:line` occurrences in `commands/refine-issue.md`.
- `scripts/tests/test_enh1299_doc_wiring.py` passes when run after ENH-1302 and ENH-1303 are also complete.

## Scope Boundaries

- Only `commands/refine-issue.md` is modified (no other command or agent files)
- Only the 11 identified anti-patterns are replaced; no section restructuring or rewrites
- The new test (`test_enh1299_doc_wiring.py`) asserts absence of `file:line` in exactly the 5 ENH-1299 target files; no additional scope
- Does not fix `file:line` references in other pipeline files — those are ENH-1302 (agents) and ENH-1303 (skills)
- Does not update `scripts/tests/test_refine_issue_command.py` unless section headings break (expected: no changes needed)

## Labels

`enhancement`, `reference-cleanup`, `authoring-pipeline`

## Session Log
- `/ll:manage-issue` - 2026-04-27T18:43:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-04-27T18:41:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4b62644-f4af-461c-a0ff-08313901945c.jsonl`
- `/ll:wire-issue` - 2026-04-27T18:35:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67265d08-b297-43f4-b705-889e30253317.jsonl`
- `/ll:refine-issue` - 2026-04-27T18:31:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac506ecf-0d87-45f2-991d-52d96f5f9589.jsonl`
- `/ll:issue-size-review` - 2026-04-27T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffb785b8-11a4-4944-a15b-8d407ae45324.jsonl`
- `/ll:confidence-check` - 2026-04-27T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/90714593-20ef-48ad-9b7e-1cf4e4248415.jsonl`

## Resolution

- Replaced all 11 `file:line` anti-patterns in `commands/refine-issue.md` with anchor-based equivalents (function/class names or section anchors)
- Created `scripts/tests/test_enh1299_doc_wiring.py` asserting zero `file:line` occurrences across all 5 ENH-1299 target files
- All 17 tests pass (5 new + 12 existing regression tests)

---

**Completed** | Created: 2026-04-27 | Priority: P2
