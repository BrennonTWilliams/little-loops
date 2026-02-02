# P3-ENH-216: Add fuzz testing for critical parsers

## Summary
While property-based tests with Hypothesis exist, no dedicated fuzz testing targets the critical parsers. Fuzz testing would find edge cases in input validation and crash safety.

## Current State
- Property-based tests: Some exist (Hypothesis configured)
- Fuzz testing: None
- Target parsers: issue_parser.py, goals_parser.py

## Proposed Fuzzing Targets
1. **Issue parser fuzzing**
   - Randomly generated issue file content
   - Malformed frontmatter
   - Invalid YAML structures
   - Unicode edge cases
   - Extremely large files

2. **Goals parser fuzzing**
   - Randomly generated goals files
   - Malformed goal definitions
   - Invalid hierarchy structures
   - Circular references

3. **Loop configuration parser fuzzing**
   - Randomly generated loop YAML
   - Invalid state machine definitions
   - Circular state references

## Acceptance Criteria
- [ ] Fuzz tests for issue_parser.py
- [ ] Fuzz tests for goals_parser.py (if exists)
- [ ] Fuzz tests for loop config parser
- [ ] Use hypothesmith or similar for Python AST fuzzing
- [ ] Document crash safety findings
- [ ] Add regression tests for any bugs found

## Implementation Notes
- Use hypothesmith for Python AST fuzzing
- Use hypothesis.strategies for structured fuzzing
- Run fuzz tests separately from unit tests (can be slow)
- Consider AFL (American Fuzzy Lop) for binary-style fuzzing
- Set appropriate iteration limits to avoid infinite loops

## Priority
P3 - Low: Fuzz testing is valuable for robustness but not critical; can be addressed after higher-priority coverage gaps.

## Related Files
- scripts/little_loops/issue_parser.py (target)
- scripts/little_loops/goals_parser.py (target)
- scripts/little_loops/fsm/schema.py (loop config parsing)

## Verification Notes
Verified 2026-02-01 - All referenced files exist. Note: parsers are directly in scripts/little_loops/, not in a parsers/ subdirectory.

## Audit Source
Test Coverage Audit - 2026-02-01
