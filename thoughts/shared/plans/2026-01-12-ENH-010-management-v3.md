# ENH-010: High Auto-Correction Rate - Third Fix Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-010-high-auto-correction-rate.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve
- **Reopened**: 2026-01-12 (auto-correction rate still at 33%, target is <10%)

## Current State Analysis

### Previous Fixes
1. **First fix (Jan 9)**: Added "Reproduction Steps" to bug template and scanner prompt
2. **Second fix (Jan 12)**: Added "Current behavior", "Expected behavior", "Proposed solution" to enhancement scanner prompt

### Remaining Problem
Auto-correction rate decreased from 56% to 33% but still above target of 10%. Analysis shows:

1. **Parallel processing does NOT capture correction details** - only logs "was auto-corrected" without specifics
2. **Sequential processing captures details** but parallel is more commonly used
3. **Cannot analyze patterns** without capturing what corrections are being made

### Key Discoveries
- `parallel/worker_pool.py:283` extracts `was_corrected` but not `corrections` list from `ready_parsed`
- `parallel/types.py:52-84` `WorkerResult` has `was_corrected: bool` but no `corrections: list[str]` field
- `parallel/orchestrator.py:486-487` only logs the boolean, not the correction details
- `issue_manager.py:467-475` (sequential) properly logs and stores each correction
- BUG-643 validation notes show corrections are primarily **code reference accuracy** issues (file paths, line numbers)

### Root Cause Analysis
Looking at BUG-643's corrections:
1. Updated proposed solution file path (file path didn't exist)
2. Clarified fix approach (content accuracy)
3. Updated Phase 3 to reflect actual codebase structure (structural accuracy)

These are **code reference validation issues** where:
- scan_codebase identifies a location but doesn't verify it exists
- The scanner creates issues with hypothetical file paths or incorrect line numbers
- ready_issue auto-corrects these by verifying against actual codebase

## Desired End State

1. **Observability**: Capture detailed corrections in parallel processing to enable pattern analysis
2. **Prevention**: Add code reference verification to scan_codebase to catch issues before creating them
3. **Target**: Auto-correction rate < 10%

### How to Verify
- Check parallel processing logs show specific corrections made
- Correction patterns can be analyzed from state data
- Future scan runs produce more accurate issues

## What We're NOT Doing

- Not changing ready_issue validation rules (they're correct)
- Not changing the Bug Scanner (already fixed)
- Not adding extensive new test infrastructure
- Not blocking scan on reference validation (just warning/correcting)

## Problem Analysis

The scan sub-agents (codebase-analyzer) are finding issues but often:
1. Guessing at file paths (e.g., "src/blender_agents/workflows/validation.py" when actual is "src/blender_agents/spec/sor_validation.py")
2. Estimating line numbers without verification
3. Creating proposed solutions that reference non-existent functions

The ready_issue command then has to auto-correct these inaccuracies.

## Solution Approach

Two-pronged approach:
1. **Observability (Phase 1)**: Add corrections tracking to parallel processing
2. **Prevention (Phase 2)**: Add reference verification guidance to scanner prompts

## Implementation Phases

### Phase 1: Add Corrections Tracking to Parallel Processing

#### Overview
Extend `WorkerResult` to include corrections list and log them in orchestrator.

#### Changes Required

**File**: `scripts/little_loops/parallel/types.py`
**Changes**: Add `corrections` field to WorkerResult

```python
@dataclass
class WorkerResult:
    # ... existing fields ...
    was_corrected: bool = False
    corrections: list[str] = field(default_factory=list)  # NEW
    # ... existing fields ...
```

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Lines**: ~283, ~358
**Changes**: Extract and pass corrections list

```python
# Line ~283: Extract corrections
was_corrected = ready_parsed.get("was_corrected", False)
corrections = ready_parsed.get("corrections", [])  # NEW

# Line ~358: Pass corrections to result
return WorkerResult(
    # ... existing fields ...
    was_corrected=was_corrected,
    corrections=corrections,  # NEW
)
```

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Lines**: ~486-487
**Changes**: Log correction details and store in state

```python
if result.was_corrected:
    self.logger.info(f"{result.issue_id} was auto-corrected during validation")
    for correction in result.corrections:
        self.logger.info(f"  Correction: {correction}")
    # Store corrections in state for pattern analysis
    if result.corrections:
        self.state.corrections[result.issue_id] = result.corrections
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Add Reference Verification Guidance to Scanners

#### Overview
Update scanner prompts to instruct sub-agents to verify code references before reporting.

#### Changes Required

**File**: `commands/scan_codebase.md`
**Lines**: ~68-88 (Bug Scanner), ~90-111 (Enhancement Scanner), ~113-131 (Feature Scanner)
**Changes**: Add verification instruction to each scanner

Add to Bug Scanner prompt (after line 87):
```markdown
IMPORTANT: Before reporting each finding, verify:
- File paths exist in the codebase (use Read tool to confirm)
- Line numbers are accurate (check the file)
- Code snippets match the current code
Only report issues you have VERIFIED exist.
```

Add to Enhancement Scanner prompt (after line 110):
```markdown
IMPORTANT: Before reporting each finding, verify:
- File paths exist in the codebase (use Read tool to confirm)
- Line numbers are accurate (check the file)
- Any referenced functions/classes exist
Only report verified findings with accurate references.
```

Add to Feature Scanner prompt (after line 130):
```markdown
IMPORTANT: Before reporting each finding, verify:
- File paths exist in the codebase (use Read tool to confirm)
- Any TODOs or comments you reference are still present
- Line numbers are accurate
Only report verified findings.
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 3: Add Tests for Corrections Tracking

#### Overview
Add unit tests for the new corrections field in WorkerResult and orchestrator handling.

#### Changes Required

**File**: `scripts/tests/test_worker_pool.py`
**Changes**: Add test for corrections extraction

```python
def test_worker_result_includes_corrections(self):
    """Test that WorkerResult captures corrections from ready_issue."""
    # Test that corrections are properly passed through
    ...
```

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add test for corrections logging

```python
def test_orchestrator_logs_corrections(self):
    """Test that orchestrator logs correction details."""
    # Verify corrections are logged and stored in state
    ...
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] New tests verify corrections tracking behavior

---

## Testing Strategy

### Unit Tests
- Test WorkerResult serialization includes corrections
- Test orchestrator stores corrections in state
- Test corrections logging output

### Integration Tests
- Future scan_codebase runs should produce issues with verified references
- Parallel processing logs should show specific corrections when they occur

## References

- Original issue: `.issues/enhancements/P2-ENH-010-high-auto-correction-rate.md`
- Previous plans: `thoughts/shared/plans/2026-01-09-ENH-010-management.md`, `thoughts/shared/plans/2026-01-12-ENH-010-management.md`
- BUG-643 example corrections: `.issues/completed/P1-BUG-643-*.md` (lines 342-356)
- Sequential corrections handling: `scripts/little_loops/issue_manager.py:467-475`
- Parallel processing gap: `scripts/little_loops/parallel/orchestrator.py:486-487`
