---
discovered_commit: 8ebfe0b
discovered_date: 2026-01-11
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# BUG-015: ready_issue verdict parsing fails on non-standard output

## Summary

The ready_issue command's verdict parsing fails when the LLM returns advice text that doesn't contain a clearly parseable verdict (READY, NOT_READY, or CLOSE). This causes parallel processing to mark issues as failed even when the underlying issue may be valid.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 1
**Affected External Issues**: ENH-616

### Sample Log Output

```
[22:01:25] ENH-616 failed: ready_issue verdict: UNKNOWN - Could not parse verdict. Output: ## NEXT_STEPS
Proceed to implementation with: `/ll:manage_issue enhancement ENH-616`

The issue is well-structured with:
- Clear discovery context from `/cl:audit_abstractions`
- Specific file locatio...
```

## Current Behavior

1. ready_issue runs and the LLM provides advice text
2. The verdict parser attempts to extract READY/NOT_READY/CLOSE from the output
3. When the output contains advice like "## NEXT_STEPS" without a clear verdict keyword, parsing fails
4. The issue is marked as failed with `verdict: UNKNOWN`
5. In parallel processing, this counts as a failure even though the LLM indicated the issue was ready

## Expected Behavior

1. The verdict parser should be more robust in extracting intent from LLM output
2. When output contains phrases like "Proceed to implementation" or "issue is well-structured", it should be interpreted as READY
3. Clear guidance should be given to the LLM to always start with a verdict keyword
4. Consider structured output (JSON) for more reliable parsing

## Affected Components

- **Tool**: ll-parallel, ll-auto (uses ready_issue)
- **Prompt**: `commands/ready_issue.md` (command prompt with output format)
- **Parser**: `scripts/little_loops/parallel/output_parsing.py` (verdict parsing logic)

## Investigation Findings

1. **Verdict parsing location**: `scripts/little_loops/parallel/output_parsing.py` - `parse_ready_issue_output()` function (lines 193-383)
2. **Prompt format**: `commands/ready_issue.md` clearly requests `## VERDICT` section with explicit keyword (lines 177-179)
3. **Parser strategies**: Uses 6 strategies in order:
   - Strategy 1: Look for `## VERDICT` section header
   - Strategy 2: Old format `VERDICT: READY` pattern
   - Strategy 3: Lines containing "verdict" with verdict keywords
   - Strategy 4: Scan entire output for verdict keywords
   - Strategy 5: Clean output and retry extraction
   - Strategy 6: Infer from `READY_FOR` section
4. **Heuristic patterns** (lines 86-107): Includes patterns like "ready for implementation", "should be closed", but **missing "proceed to implementation"**

**Root cause**: The phrase "Proceed to implementation" is not in the `phrasing_map` patterns (line 86-107), so when the LLM skips the `## VERDICT` section and uses this phrase in `## NEXT_STEPS`, the parser returns UNKNOWN.

## Proposed Fix Options

1. **Parser improvement** (recommended, minimal change):
   - Add `(r"\bproceed\s+to\s+implementation\b", "READY")` to `phrasing_map` in `output_parsing.py:86-107`
   - Also add `(r"\bimplementation\s+ready\b", "READY")` for similar patterns

2. **Prompt strengthening**:
   - Add explicit instruction in `commands/ready_issue.md` to ALWAYS include `## VERDICT` section first
   - Example: "CRITICAL: Your response MUST start with `## VERDICT` followed by exactly one of: READY, CORRECTED, NOT_READY, CLOSE"

3. **Structured output**: Request JSON response with explicit verdict field (larger change, more reliable)

4. **NEXT_STEPS inference** (Strategy 7):
   - In `parse_ready_issue_output()`, add strategy: if `NEXT_STEPS` section contains "manage_issue" and no CLOSE indicators, infer READY

## Impact

- **Severity**: Medium (P2)
- **Frequency**: 1 occurrence in this run, but likely affects other runs
- **Data Risk**: Low - issues are incorrectly marked as failed but not lost

## Reproduction Steps

1. Have an issue that ready_issue evaluates as valid
2. If the LLM responds with advice text instead of starting with a verdict keyword
3. Observe the UNKNOWN verdict failure

---

## Status
**Reopened** | Created: 2026-01-11 | Priority: P2 | Reopened: 2026-01-12

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-11
- **Status**: Completed (initial fix)

### Changes Made
- `scripts/little_loops/parallel/output_parsing.py`: Added pattern `(r"\bproceed\s+(to|with)\s+implementation\b", "READY")` to `phrasing_map` at line 92
- `scripts/tests/test_output_parsing.py`: Added two test cases for "proceed to implementation" and "proceed with implementation" phrasings

### Verification Results
- Tests: PASS (480 tests)
- Lint: PASS
- Types: PASS

---

## Reopened

- **Date**: 2026-01-12
- **By**: /analyze_log
- **Reason**: New unparseable verdict pattern discovered

### New Evidence

**Log File**: `ll-parallel-blender-agents-debug.log`
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 1
**Affected External Issues**: ENH-641

```
[12:54:57] ENH-641 failed: ready_issue verdict: UNKNOWN - Could not parse verdict. Output: Would you like me to move this issue to the completed directory with the closure status, or would you prefer to review the evidence first?...
```

### Analysis

The previous fix added the "proceed to implementation" pattern. However, a new unparseable pattern has appeared:

**New pattern**: `"Would you like me to move this issue to the completed directory with the closure status"`

This appears to be:
1. The LLM asking a clarification question instead of returning a verdict
2. The LLM suggesting the issue should be CLOSED (moved to completed) but phrasing it as a question
3. Possibly a CLOSE verdict that wasn't clearly stated

**Observations**:
1. The phrase "move this issue to the completed directory" implies CLOSE verdict
2. The phrase "closure status" confirms intent to close
3. The LLM is asking for confirmation instead of stating the verdict directly

**Root cause**: The prompt may be allowing the LLM to ask questions instead of making a verdict decision, OR this is a valid CLOSE verdict that the parser doesn't recognize.

### Proposed Additional Fixes

1. **Add pattern for closure language**:
   - `(r"\bmove.*to.*completed\b", "CLOSE")`
   - `(r"\bclosure\s+status\b", "CLOSE")`

2. **Prompt strengthening**:
   - Add explicit instruction: "Do NOT ask the user questions. Make a verdict decision based on the available information."

3. **Parser enhancement**:
   - Add strategy to detect question patterns and treat them as UNKNOWN requiring human review

---

## Second Resolution

- **Action**: fix
- **Completed**: 2026-01-12
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/output_parsing.py`: Added two CLOSE patterns to `phrasing_map`:
  - `(r"\bmove.*to.*completed\b", "CLOSE")` - matches "move this issue to the completed directory"
  - `(r"\bclosure\s+status\b", "CLOSE")` - matches "closure status"
- `scripts/tests/test_output_parsing.py`: Added two test cases:
  - `test_phrasing_move_to_completed_directory` - verifies "move to completed" extracts CLOSE
  - `test_phrasing_closure_status` - verifies "closure status" extracts CLOSE

### Verification Results
- Tests: PASS (493 tests)
- Lint: PASS
- Types: PASS
