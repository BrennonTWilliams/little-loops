# BUG-015: ready_issue verdict parsing fails on non-standard output - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-015-ready-issue-verdict-parsing-failure.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `parse_ready_issue_output()` function in `scripts/little_loops/parallel/output_parsing.py` uses 6 fallback strategies to extract verdicts from LLM output. When all strategies fail, it returns `verdict: "UNKNOWN"`, causing parallel processing to mark issues as failed.

### Key Discoveries
- Root cause at `output_parsing.py:86-107`: The `phrasing_map` is missing the pattern "proceed to implementation"
- The command prompt at `commands/ready_issue.md:220` instructs the LLM to use "Proceed to implementation with: `/ll:manage-issue`" in the `## NEXT_STEPS` section
- When the LLM follows this template but skips the `## VERDICT` section, all 6 parsing strategies fail
- Test patterns for phrasings are at `test_output_parsing.py:541-600` - no test exists for "proceed to implementation"

### Patterns to Follow
- Existing phrasing tests at lines 541-600 use simple output strings without structured sections
- Pattern tuples follow format: `(r"\bword\s+pattern\b", "VERDICT")`
- Related pattern at line 89: `(r"\bready\s+for\s+implementation\b", "READY")`

## Desired End State

When LLM output contains phrases like "Proceed to implementation" or "proceed with implementation", the parser should extract `verdict: "READY"` instead of `verdict: "UNKNOWN"`.

### How to Verify
- New test case passes for "proceed to implementation" phrasing
- All existing tests continue to pass
- Regex pattern correctly matches variations like "Proceed to implementation", "proceed with implementation"

## What We're NOT Doing

- Not restructuring the 6-strategy parsing approach (working as designed)
- Not adding a Strategy 7 for NEXT_STEPS section parsing (would add complexity)
- Not changing the prompt format (issue is parser robustness, not prompt clarity)
- Not adding JSON structured output (larger change, deferred)

## Problem Analysis

The LLM sometimes follows the `## NEXT_STEPS` template from the command prompt without including an explicit `## VERDICT` section. The phrase "Proceed to implementation" clearly indicates readiness but is not in the `phrasing_map`.

**Root cause**: Missing pattern in `phrasing_map` at `output_parsing.py:86-107`.

## Solution Approach

Add the missing pattern `(r"\bproceed\s+(to|with)\s+implementation\b", "READY")` to the `phrasing_map` list, alongside existing READY patterns. This is a minimal, targeted fix that:
1. Reuses existing Strategy 4 scanning logic
2. Maintains pattern organization by verdict type
3. Gets tested by existing test infrastructure
4. Handles both "proceed to implementation" and "proceed with implementation"

## Implementation Phases

### Phase 1: Add Missing Pattern

#### Overview
Add the pattern for "proceed to/with implementation" to the phrasing_map in `_extract_verdict_from_text()`.

#### Changes Required

**File**: `scripts/little_loops/parallel/output_parsing.py`
**Changes**: Add new pattern after line 91 (after existing READY patterns)

Insert after line 91:
```python
        (r"\bproceed\s+(to|with)\s+implementation\b", "READY"),
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_output_parsing.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/output_parsing.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/output_parsing.py`

---

### Phase 2: Add Test Case

#### Overview
Add a test case for the new "proceed to implementation" pattern, following the existing phrasing test pattern.

#### Changes Required

**File**: `scripts/tests/test_output_parsing.py`
**Changes**: Add new test method after `test_phrasing_corrections_made` (around line 600)

```python
    def test_phrasing_proceed_to_implementation(self) -> None:
        """Test extracting verdict from 'proceed to implementation' phrasing."""
        output = """
## NEXT_STEPS
Proceed to implementation with: `/ll:manage-issue enhancement ENH-616`
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_phrasing_proceed_with_implementation(self) -> None:
        """Test extracting verdict from 'proceed with implementation' phrasing."""
        output = """
The issue is well-structured. Proceed with implementation.
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_output_parsing.py::TestParseReadyIssueOutput::test_phrasing_proceed_to_implementation -v`
- [ ] New tests pass: `python -m pytest scripts/tests/test_output_parsing.py::TestParseReadyIssueOutput::test_phrasing_proceed_with_implementation -v`
- [ ] All tests pass: `python -m pytest scripts/tests/test_output_parsing.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_output_parsing.py`

---

### Phase 3: Full Verification

#### Overview
Run full test suite and linting to ensure no regressions.

#### Success Criteria

**Automated Verification**:
- [ ] Full test suite passes: `python -m pytest scripts/tests/ -v`
- [ ] Full lint passes: `ruff check scripts/`
- [ ] Type checking passes: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test "proceed to implementation" (exact bug case)
- Test "proceed with implementation" (variation)
- Verify existing phrasing tests still pass
- Verify word boundary works (won't match "proceed to implementation-ready")

### Integration Tests
- Existing workflow tests should continue to pass

## References

- Original issue: `.issues/bugs/P2-BUG-015-ready-issue-verdict-parsing-failure.md`
- Parser function: `scripts/little_loops/parallel/output_parsing.py:55-113`
- Phrasing map: `scripts/little_loops/parallel/output_parsing.py:86-107`
- Similar patterns: `output_parsing.py:89` - `ready for implementation`
- Test patterns: `scripts/tests/test_output_parsing.py:541-600`
