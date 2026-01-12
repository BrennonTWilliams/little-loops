# BUG-015: ready_issue verdict parsing fails on non-standard output - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-015-ready-issue-verdict-parsing-failure.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

This is a **reopened** bug. The initial fix added the "proceed to implementation" pattern, but a new unparseable pattern has appeared.

### Key Discoveries
- `output_parsing.py:86-108` - The `phrasing_map` contains CLOSE patterns at lines 93-98
- Current CLOSE patterns: "should be closed", "close this issue", "mark as closed", "already fixed", "invalid reference"
- **Missing**: Patterns for "move to completed directory" and "closure status"
- Line 92 has the pattern added in the initial fix: `(r"\bproceed\s+(to|with)\s+implementation\b", "READY")`

### New Failure Case
```
[12:54:57] ENH-641 failed: ready_issue verdict: UNKNOWN - Could not parse verdict.
Output: Would you like me to move this issue to the completed directory with the closure status, or would you prefer to review the evidence first?
```

The phrase "move this issue to the completed directory with the closure status" clearly indicates CLOSE intent but isn't matched by any existing patterns.

## Desired End State

The parser should recognize closure-related phrasings like:
- "move this issue to the completed directory" → CLOSE
- "closure status" → CLOSE

### How to Verify
- New test cases pass for the new patterns
- All existing tests continue to pass
- Running `pytest scripts/tests/test_output_parsing.py -v` shows all passing

## What We're NOT Doing

- Not changing the prompt in `commands/ready_issue.md` - the parser should be robust to LLM output variations
- Not adding a new "Strategy 7" for NEXT_STEPS inference - the phrasing_map approach is simpler and matches existing patterns
- Not converting to JSON structured output - larger change for separate enhancement

## Problem Analysis

**Root Cause**: The `phrasing_map` in `output_parsing.py:93-98` lacks patterns for "move to completed" and "closure status" phrasings that LLMs may use to indicate a CLOSE verdict.

The existing 6-strategy parsing cascade works correctly - it just needs additional patterns in the phrasing_map to recognize more CLOSE-indicating phrases.

## Solution Approach

Add two new CLOSE patterns to `phrasing_map` after line 98:
1. `(r"\bmove.*to.*completed\b", "CLOSE")` - matches "move this issue to the completed directory"
2. `(r"\bclosure\s+status\b", "CLOSE")` - matches "closure status"

## Implementation Phases

### Phase 1: Add CLOSE Patterns

#### Overview
Add two new patterns to the phrasing_map CLOSE section.

#### Changes Required

**File**: `scripts/little_loops/parallel/output_parsing.py`
**Changes**: Add two new CLOSE patterns after line 98

```python
        (r"\binvalid\s+reference\b", "CLOSE"),
        (r"\bmove.*to.*completed\b", "CLOSE"),  # "move this issue to the completed directory"
        (r"\bclosure\s+status\b", "CLOSE"),  # "closure status"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_output_parsing.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Add Test Cases

#### Overview
Add test cases for the new patterns following the existing test pattern structure.

#### Changes Required

**File**: `scripts/tests/test_output_parsing.py`
**Changes**: Add two new test methods after line 620

```python
def test_phrasing_move_to_completed_directory(self) -> None:
    """Test extracting verdict from 'move to completed directory' phrasing."""
    output = """
Would you like me to move this issue to the completed directory with the closure status, or would you prefer to review the evidence first?
"""
    result = parse_ready_issue_output(output)

    assert result["verdict"] == "CLOSE"
    assert result["should_close"] is True

def test_phrasing_closure_status(self) -> None:
    """Test extracting verdict from 'closure status' phrasing."""
    output = """
The issue should be moved with the closure status since it's already been resolved.
"""
    result = parse_ready_issue_output(output)

    assert result["verdict"] == "CLOSE"
    assert result["should_close"] is True
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_output_parsing.py -v`
- [ ] New tests specifically pass: `pytest scripts/tests/test_output_parsing.py -v -k "move_to_completed or closure_status"`

---

## Testing Strategy

### Unit Tests
- Test "move to completed directory" phrase extracts CLOSE verdict
- Test "closure status" phrase extracts CLOSE verdict
- Verify `should_close` flag is True for these patterns

### Integration Tests
- All existing verdict parsing tests continue to pass

## References

- Original issue: `.issues/bugs/P2-BUG-015-ready-issue-verdict-parsing-failure.md`
- Parser implementation: `scripts/little_loops/parallel/output_parsing.py:86-108`
- Initial fix tests: `scripts/tests/test_output_parsing.py:601-620`
- Similar pattern: line 92 `(r"\bproceed\s+(to|with)\s+implementation\b", "READY")`
