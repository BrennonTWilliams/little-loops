# ENH-010: High Auto-Correction Rate - Implementation Plan (Fourth Fix)

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-010-high-auto-correction-rate.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

This is the **fourth reopening** of this issue. Previous fixes addressed:
1. Missing "Reproduction Steps" section in bug template
2. Missing enhancement fields in scanner prompts
3. Added corrections tracking and verification instructions to scanners

Despite these fixes, the auto-correction rate spiked to **73%** (11 out of 15 issues).

### Key Discoveries from Research

**Correction patterns from the log** (ENH-010:328-361):
- File path corrections (e.g., `analysis_ops.py` → `scene/scene_snapshot.py`)
- Line number updates (e.g., `110→479, 187→673, 55→349`)
- Related issue status updates (marking issues as COMPLETED)
- Clarifications about code artifacts (templates vs specfiles)

**Root cause**: Temporal drift between scan time (T0) and validation time (T1)
- Issues are created referencing code state at T0
- During parallel processing, other workers modify code
- By T1, line numbers have shifted, files may have moved, related issues have completed
- Scanner verification at T0 cannot prevent T1 corrections

### Patterns Found in Codebase
- `ready_issue.md:70-108`: Deep validation with sub-agents (--deep flag)
- `parallel/types.py:193`: OrchestratorState stores corrections
- FEAT-030: Dependency graph uses dynamic resolution at runtime

## Desired End State

1. **Reduce auto-correction rate from 73% to under 20%** (realistic target given parallel processing)
2. **Use stable references** instead of volatile line numbers where possible
3. **Remove stale related-issue status** from scanned issues (resolve dynamically)
4. **Enable tracking** to identify which correction types remain after this fix

### How to Verify
- Run `ll-parallel` on a target repo and check correction rate in summary
- Review correction patterns in the log output
- Target: under 20% auto-correction rate

## What We're NOT Doing

- **Not implementing lazy validation** - Would require significant architectural changes to defer validation until just before implementation
- **Not removing line numbers entirely** - They're still useful; we'll add stable references as supplements
- **Not changing the validation strictness** - Corrections are valuable; we're reducing the need for them
- **Not refactoring the entire scan/validate flow** - Incremental improvements only

## Problem Analysis

The 73% correction rate breaks down into these patterns (from log analysis):

| Pattern | Frequency | Cause |
|---------|-----------|-------|
| Line number drift | High | Code modified by other workers during parallel processing |
| File path changes | Medium | Files renamed/moved during processing |
| Related issue status stale | Medium | Issues completed during same run appear as "open" |
| Content clarifications | Low | Scanner misunderstood code relationships |

The first three patterns are **temporal drift** issues - the scanner captures state that becomes stale.

## Solution Approach

### Strategy 1: Add Stable Function/Class Anchors

Instead of relying solely on line numbers (which drift), add stable anchors:
- Function names
- Class names
- Unique code patterns (specific strings that won't change)

**Example**: Instead of just `line 42`, also include `in function process_issue()`.

### Strategy 2: Remove Related Issue Status from Scanned Issues

The scanner currently includes "related issues" with their status. During parallel processing, these statuses become stale. Solution:
- Scanner should NOT include related issue status in issue files
- Let ready_issue resolve related issue status dynamically at validation time

### Strategy 3: Use Commit-Anchored References

Include the commit hash with line references so ready_issue can detect when the code has changed since the issue was created.

### Strategy 4: Classify Corrections for Future Analysis

Categorize corrections into types to enable more targeted future fixes:
- `line_drift`: Line numbers changed
- `file_moved`: File path changed
- `issue_status`: Related issue status updated
- `content_fix`: Content accuracy correction

## Implementation Phases

### Phase 1: Update Scanner Templates for Stable Anchors

#### Overview
Modify scan_codebase.md to include stable function/class anchors alongside line numbers.

#### Changes Required

**File**: `commands/scan_codebase.md`
**Changes**: Update Location section in issue template (lines 186-195)

Current template:
```markdown
## Location

- **File**: `path/to/file.py`
- **Line(s)**: 42-45
- **Permalink**: [View on GitHub](...)
- **Code**:
```

New template:
```markdown
## Location

- **File**: `path/to/file.py`
- **Line(s)**: 42-45 (at scan time: [COMMIT_HASH_SHORT])
- **Anchor**: `in function process_issue()` or `in class IssueManager` or `near string "specific marker"`
- **Permalink**: [View on GitHub](...)
- **Code**:
```

Also update scanner prompts to request anchors:

**Bug Scanner** (lines 81-87): Add "Stable anchor (function name, class name, or unique nearby string)"

**Enhancement Scanner** (lines 109-116): Add "Stable anchor (function name, class name, or unique nearby string)"

**Feature Scanner** (lines 137-142): Add "Stable anchor (function name, class name, or unique nearby string)"

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] Run `/ll:scan_codebase` on a test directory and verify new issues include Anchor field

---

### Phase 2: Remove Related Issue Status from Scanner Output

#### Overview
Prevent scanner from including stale related-issue status that causes corrections.

#### Changes Required

**File**: `commands/scan_codebase.md`
**Changes**: Add instruction to scanner prompts to NOT include related issue status

Add to each scanner prompt (Bug Scanner ~line 87, Enhancement Scanner ~line 116, Feature Scanner ~line 142):

```markdown
IMPORTANT: Do NOT include related issue IDs or their status in findings.
Related issues will be resolved dynamically during validation.
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] Verify scanner prompts include the new instruction

---

### Phase 3: Update ready_issue to Use Anchors for Validation

#### Overview
Modify ready_issue to use stable anchors when validating/correcting code references.

#### Changes Required

**File**: `commands/ready_issue.md`
**Changes**: Update code reference validation (lines 121-124) to use anchors

Add new section after line 124:

```markdown
#### Using Stable Anchors

If line numbers are outdated but anchor exists:
1. Search for the anchor (function/class name or unique string)
2. Find current line numbers for that anchor
3. Update line references automatically
4. Note in CORRECTIONS_MADE: "Updated line N -> M using anchor 'function_name'"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] Verify ready_issue.md includes anchor-based correction guidance

---

### Phase 4: Add Correction Classification

#### Overview
Categorize corrections by type for better analysis.

#### Changes Required

**File**: `commands/ready_issue.md`
**Changes**: Update CORRECTIONS_MADE format (lines 208-212)

New format:
```markdown
## CORRECTIONS_MADE
- [line_drift] Updated line 42 -> 45 in src/module.py reference
- [file_moved] Updated path from old/path.py to new/path.py
- [issue_status] Related issue ENH-042 marked as completed
- [content_fix] Clarified that X affects Y not Z
- [Or "None" if no corrections needed]
```

**File**: `scripts/little_loops/parallel/output_parsing.py`
**Changes**: Update correction parsing to extract category (around line 295)

Current:
```python
if line.startswith("- ") and line != "- None":
    corrections.append(line[2:])
```

New:
```python
if line.startswith("- ") and line != "- None":
    correction_text = line[2:]
    # Extract category if present: [category] text
    if correction_text.startswith("[") and "]" in correction_text:
        category_end = correction_text.index("]")
        category = correction_text[1:category_end]
        text = correction_text[category_end + 2:]  # Skip "] "
        corrections.append(f"[{category}] {text}")
    else:
        corrections.append(correction_text)
```

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Update correction statistics to group by category (around lines 596-617)

Add category breakdown:
```python
# Group corrections by category
from collections import defaultdict
by_category: dict[str, int] = defaultdict(int)
for corrections in self.state.corrections.values():
    for correction in corrections:
        if correction.startswith("[") and "]" in correction:
            category = correction[1:correction.index("]")]
            by_category[category] += 1
        else:
            by_category["uncategorized"] += 1

if by_category:
    self.logger.info("Corrections by type:")
    for category, count in sorted(by_category.items(), key=lambda x: -x[1]):
        self.logger.info(f"  - {category}: {count}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Run a parallel processing session and verify correction categories appear in summary

---

## Testing Strategy

### Unit Tests
- `test_output_parsing.py`: Add test for parsing categorized corrections
- `test_orchestrator.py`: Add test for category breakdown in statistics

### Integration Tests
- Run `ll-parallel` on a test repo and verify:
  - New issues include Anchor field
  - Corrections are categorized in output
  - Correction rate is reported with category breakdown

## References

- Original issue: `.issues/enhancements/P2-ENH-010-high-auto-correction-rate.md`
- Previous plans: `thoughts/shared/plans/2026-01-09-ENH-010-management.md`, `2026-01-12-ENH-010-management.md`, `2026-01-12-ENH-010-management-v3.md`
- ready_issue command: `commands/ready_issue.md:70-108` (deep validation pattern)
- Output parsing: `scripts/little_loops/parallel/output_parsing.py:289-295`
- Correction statistics: `scripts/little_loops/parallel/orchestrator.py:596-617`
