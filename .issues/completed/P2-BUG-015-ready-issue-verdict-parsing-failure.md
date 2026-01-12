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
**Completed** | Created: 2026-01-11 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-11
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/output_parsing.py`: Added pattern `(r"\bproceed\s+(to|with)\s+implementation\b", "READY")` to `phrasing_map` at line 92
- `scripts/tests/test_output_parsing.py`: Added two test cases for "proceed to implementation" and "proceed with implementation" phrasings

### Verification Results
- Tests: PASS (480 tests)
- Lint: PASS
- Types: PASS
