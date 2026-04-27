---
parent_issue: ENH-1299
discovered_date: "2026-04-27"
discovered_by: issue-size-review
decision_needed: false
missing_artifacts: false
---

# ENH-1304: Fix `file:line` references in `commands/refine-issue.md` and add verification test

## Summary

Edit `commands/refine-issue.md` to replace all `file:line`-style references with anchor-based equivalents, then write a structural test (`scripts/tests/test_enh1299_doc_wiring.py`) that asserts all five ENH-1299 target files are free of `file:line` strings.

## Parent Issue

Decomposed from ENH-1299: Fix `file:line` references in issue-authoring pipeline source files

## Current Behavior

- **`commands/refine-issue.md`**: 10 occurrences of `file:line` — Agent 2 and Agent 3 prompt blocks request `file:line` references; the `Gap Detection` table row reads "Which file:line contains the bug"; enrichment template, Research Summary, and Output Report sections use `file:line` placeholder language.

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

**Exact occurrence counts:**
- `commands/refine-issue.md`: 10 occurrences (Agent prompts ×2, Gap Detection ×2, enrichment template ×3, Research Summary ×1, Output Report ×2)

**Test pattern reference**: `scripts/tests/test_feat1172_doc_wiring.py` — path constants via `Path(__file__).parent.parent.parent`, class per file, `assert "file:line" not in content`

## Integration Map

### Files to Modify

- `commands/refine-issue.md`

### Files to Create

- `scripts/tests/test_enh1299_doc_wiring.py`

### Verification

```bash
grep -n "file:line" commands/refine-issue.md
# Should return zero matches

python -m pytest scripts/tests/test_enh1299_doc_wiring.py -v
# Should pass only after ENH-1302, ENH-1303, and this issue are all complete
```

## Implementation Steps

1. Edit `commands/refine-issue.md` — update Agent 2 and Agent 3 prompts, Gap Detection table, and all other `file:line` occurrences.
2. Write `scripts/tests/test_enh1299_doc_wiring.py` — structural test asserting zero `file:line` occurrences in all 5 target files.
3. Run verification grep.

## Impact

- **Priority**: P2
- **Effort**: Small — text edits + one new test file
- **Risk**: Very low — reversible; changes only affect command prompts
- **Breaking Change**: No
- **Note**: The test added here will fail until ENH-1302 and ENH-1303 are also complete; it serves as the acceptance gate for the full ENH-1299 scope.

## Success Metrics

- Zero `file:line` occurrences in `commands/refine-issue.md`.
- `scripts/tests/test_enh1299_doc_wiring.py` passes when run after ENH-1302 and ENH-1303 are also complete.

## Labels

`enhancement`, `reference-cleanup`, `authoring-pipeline`

## Session Log
- `/ll:issue-size-review` - 2026-04-27T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffb785b8-11a4-4944-a15b-8d407ae45324.jsonl`

---

**Open** | Created: 2026-04-27 | Priority: P2
