# ENH-010: High Auto-Correction Rate - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-010-high-auto-correction-rate.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

### Key Discoveries

1. **Template Mismatch** (`commands/scan_codebase.md:153-202` vs `commands/ready_issue.md:114-120`):
   - scan_codebase template does NOT include "Reproduction steps" section
   - ready_issue validation REQUIRES "Reproduction steps (for bugs)" at line 118
   - This causes every bug to require auto-correction to add the missing section

2. **Scanner Agent Prompts Are Generic** (`commands/scan_codebase.md:68-128`):
   - Agents are told to return "structured findings" without specifying exact section headers
   - No explicit instruction to include reproduction steps for bugs
   - No validation-aligned format specification

3. **Corrections Logged But Not Persisted** (`scripts/little_loops/issue_manager.py:439-444`):
   - Corrections are logged to console but NOT added to state
   - No metrics tracked for what types of corrections occur most frequently
   - Cannot analyze patterns to feed back into scan prompts

4. **State Dataclass Pattern** (`scripts/little_loops/state.py:17-68`):
   - ProcessingState already tracks completed, failed, timing per issue
   - Easy to extend with `corrections` field following same pattern

### Current Flow
```
scan_codebase → creates issues (missing required sections)
        ↓
ready_issue → validates, finds missing sections, auto-corrects
        ↓
issue_manager → logs "was auto-corrected" but doesn't track details
```

## Desired End State

1. **Scan creates issues that pass validation without correction** (target: <10% correction rate)
2. **Correction details are persisted** for pattern analysis
3. **Summary shows correction statistics** to track improvement over time

### How to Verify
- Run existing tests to ensure no regressions
- Check that corrections are now stored in state file
- Verify summary includes correction statistics

## What We're NOT Doing

- **Not refactoring scan_codebase entirely** - just adding missing sections to template
- **Not adding new config options** - using existing infrastructure
- **Not building analysis dashboard** - just collecting data for future analysis
- **Not modifying agent behavior** - agents already follow templates they're given

## Solution Approach

Two-pronged fix:
1. **Prevention**: Add "Reproduction Steps" section to scan_codebase template for bugs
2. **Tracking**: Extend ProcessingState to store corrections for analysis

## Implementation Phases

### Phase 1: Add Missing Template Sections

#### Overview
Add "Reproduction Steps" section to the scan_codebase issue template to align with ready_issue validation requirements.

#### Changes Required

**File**: `commands/scan_codebase.md`
**Location**: Lines 176-182 (after "## Current Behavior" and "## Expected Behavior")

Add new section after "## Expected Behavior":

```markdown
## Reproduction Steps

[For bugs only - steps to reproduce the issue]
1. [Step 1]
2. [Step 2]
3. [Observe: description of the bug]
```

Also update bug scanner prompt (lines 72-87) to request reproduction steps:

```markdown
Return structured findings with:
- Title (brief description)
- File path and line number(s)
- Code snippet showing the issue
- Severity assessment (High/Medium/Low)
- Brief explanation of the problem
- Reproduction steps (for bugs)
```

#### Success Criteria

**Automated Verification**:
- [ ] No syntax errors in scan_codebase.md (valid markdown)

**Manual Verification**:
- [ ] Template now includes "Reproduction Steps" section

---

### Phase 2: Extend State to Track Corrections

#### Overview
Add a `corrections` field to ProcessingState to track what corrections are made per issue.

#### Changes Required

**File**: `scripts/little_loops/state.py`

Add new field to ProcessingState dataclass (after line 43):

```python
corrections: dict[str, list[str]] = field(default_factory=dict)
```

Update `to_dict()` method (after line 54):
```python
"corrections": self.corrections,
```

Update `from_dict()` method (after line 67):
```python
corrections=data.get("corrections", {}),
```

**File**: `scripts/little_loops/issue_manager.py`

Update the correction logging block (around line 439-444) to store corrections:

```python
# Log and store any corrections made
if parsed.get("was_corrected"):
    self.logger.info(f"Issue {info.issue_id} was auto-corrected")
    corrections = parsed.get("corrections", [])
    for correction in corrections:
        self.logger.info(f"  Correction: {correction}")
    # Store corrections in state for pattern analysis
    if corrections:
        self.state_manager.state.corrections[info.issue_id] = corrections
```

Add new StateManager method to record corrections (after line 187):

```python
def record_corrections(self, issue_id: str, corrections: list[str]) -> None:
    """Record corrections made to an issue.

    Args:
        issue_id: Issue identifier
        corrections: List of correction descriptions
    """
    if corrections:
        self.state_manager.state.corrections[issue_id] = corrections
        self.save()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_state.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/state.py`
- [ ] Lint passes: `ruff check scripts/little_loops/state.py`

---

### Phase 3: Add Correction Summary to Output

#### Overview
Update the summary logging to include correction statistics.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`

Find the `_log_timing_summary` method and add correction stats:

```python
# Add after timing summary
state = self.state_manager.state
if state.corrections:
    total_corrected = len(state.corrections)
    total_issues = len(state.completed_issues) + len(state.failed_issues)
    correction_rate = (total_corrected / total_issues * 100) if total_issues > 0 else 0
    self.logger.info(f"Auto-corrections: {total_corrected}/{total_issues} ({correction_rate:.1f}%)")

    # Log most common correction types
    all_corrections = []
    for corrections in state.corrections.values():
        all_corrections.extend(corrections)
    if all_corrections:
        from collections import Counter
        common = Counter(all_corrections).most_common(3)
        self.logger.info("Most common corrections:")
        for correction, count in common:
            self.logger.info(f"  - {correction}: {count}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_manager.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_manager.py`

---

### Phase 4: Add Tests for New Functionality

#### Overview
Add unit tests for the new corrections tracking functionality.

#### Changes Required

**File**: `scripts/tests/test_state.py`

Add test for corrections field:

```python
def test_corrections_persistence(self) -> None:
    """Test that corrections are persisted and loaded correctly."""
    state = ProcessingState()
    state.corrections["BUG-001"] = ["Added missing section", "Updated line numbers"]
    state.corrections["ENH-002"] = ["Fixed file path"]

    data = state.to_dict()
    assert "corrections" in data
    assert data["corrections"]["BUG-001"] == ["Added missing section", "Updated line numbers"]

    loaded = ProcessingState.from_dict(data)
    assert loaded.corrections == state.corrections
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_state.py -v`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`

---

## Testing Strategy

### Unit Tests
- Test ProcessingState serialization includes corrections
- Test StateManager.record_corrections method
- Test correction statistics calculation

### Integration Tests
- Existing test suite validates parsing still works
- Ready_issue tests verify corrections are parsed correctly

## References

- Original issue: `.issues/enhancements/P2-ENH-010-high-auto-correction-rate.md`
- Scan template: `commands/scan_codebase.md:153-202`
- Validation requirements: `commands/ready_issue.md:114-120`
- State management: `scripts/little_loops/state.py:17-68`
- Correction logging: `scripts/little_loops/issue_manager.py:439-444`
