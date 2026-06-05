---
id: ENH-1963
type: ENH
priority: P2
status: open
captured_at: "2026-06-05T21:16:36Z"
discovered_date: 2026-06-05
discovered_by: capture-issue
labels:
  - test-quality
  - captured
parent: EPIC-1967
---

# ENH-1963: Audit and Consolidate Doc-Wiring Tests

## Summary

59 doc-wiring test files (23.4% of the test suite) verify that strings appear in `.md` documentation files. These tests exercise zero application code — they inflate the test count, create a false sense of thoroughness, and add maintenance burden. Consolidate them into ≤5 parametrized test files or replace them with a lint rule.

## Context

Identified during a comprehensive test suite audit conducted by 3 parallel Explore agents (test structure, coverage gaps, quality patterns) and synthesized by a Plan agent. The audit found that nearly a quarter of all test files are doc-wiring tests that don't exercise any application logic.

## Current Behavior

- 59 test files (estimated) follow the `test_*_doc_wiring.py` or `test_*_wiring.py` naming pattern
- Each file uses string assertions to verify specific text appears in `.md` docs
- These tests pass if a string is present, fail if someone rewords a doc — producing noisy failures unrelated to code correctness
- They count toward the 9,968 total test count and 90% coverage metric, masking real coverage gaps

## Expected Behavior

- Doc-wiring verification is consolidated into ≤5 parametrized test files (e.g., one per document category)
- OR replaced with a lint rule / markdown link checker that runs separately from the unit test suite
- Doc string verification does not inflate test counts or coverage metrics
- Real test coverage metrics are honest about application code coverage

## Motivation

Doc-wiring tests create two problems simultaneously: they add maintenance toil (updating string assertions when docs change) AND they mask real test gaps by inflating the test count. Teams see "9,968 tests passing" and assume comprehensive coverage, when nearly 1/4 of those tests don't exercise any application code.

- **Maintenance burden**: 59 files that break on any doc rewording create churn unrelated to code quality
- **False confidence**: 23.4% of the test suite verifying strings in docs creates an inflated sense of test thoroughness
- **Coverage dishonesty**: The 90% line coverage figure includes these tests, hiding real gaps in application code coverage
- **CI time**: Running 59 doc-wiring test files consumes CI minutes with zero code-quality signal

## Proposed Solution

Three options identified in the audit:

**Option A: Parametrize (recommended)**
Consolidate into ≤5 parametrized test files that use a data-driven approach — e.g., a single `test_doc_wiring.py` with `@pytest.mark.parametrize` across doc/code pairs.

**Option B: Lint rule replacement**
Replace most doc-wiring tests with a markdown link checker (`ll-check-links` already exists) plus a simple pattern checker. Keep only integration-critical doc assertions as tests.

**Option C: Separate test suite**
Move doc-wiring tests to a separate `tests/doc_wiring/` directory excluded from coverage and run them as a separate CI job.

## Success Metrics

- **Before**: 59 doc-wiring test files, ~23% of test suite
- **Target**: ≤5 parametrized files or a lint rule, ≤5% of test suite
- **Coverage impact**: Honest coverage metric drops ≤2% (the portion that was doc-wiring tests masquerading as coverage)
- **CI time**: ≥30s reduction from consolidated/faster doc checks

## Scope Boundaries

- **In scope**: All test files matching `*doc_wiring*` or `*_wiring*` patterns
- **In scope**: Updating coverage configuration to exclude doc-wiring from code coverage metrics
- **Out of scope**: Structural skill tests (separate concern, tracked as ENH-1745)
- **Out of scope**: Changing what documentation says — only how we verify it

## API/Interface

No public API changes. Internal changes limited to:
- Test file reorganization (consolidation)
- Possible new pytest fixtures/parametrization helpers
- Coverage configuration (`pyproject.toml` or `.coveragerc`)

## Integration Map

### Files to Modify
- `scripts/tests/test_*_doc_wiring.py` (59 files) — consolidate into ≤5 parametrized files
- `scripts/tests/test_*_wiring.py` — same consolidation
- `pyproject.toml` — update coverage exclusions if needed

### Dependent Files (Callers/Importers)
- CI configuration that references test count or coverage thresholds
- Coverage reporting dashboards/scripts

### Similar Patterns
- Structural skill tests (`test_skill_*.py`) — similar "testing instructions, not behavior" pattern, tracked separately

### Tests
- The consolidated test files themselves are the deliverable

### Documentation
- `CONTRIBUTING.md` — update test guidelines if doc-wiring pattern changes
- `.claude/CLAUDE.md` — update test conventions

### Configuration
- `pyproject.toml` — coverage exclusions
- `.coveragerc` if present

## Implementation Steps

1. Inventory all 59 doc-wiring test files and categorize by what they verify (links, sections, frontmatter, etc.)
2. Design parametrized structure — one file per category with `@pytest.mark.parametrize`
3. Implement consolidated test files and verify they catch the same issues
4. Delete the 59 individual files
5. Update coverage configuration to ensure honest metrics
6. Run full test suite to confirm no regressions

## Backwards Compatibility

- No breaking changes to APIs or user-facing behavior
- Existing CI pipelines continue to pass
- Test count will decrease (by design), which may affect dashboards that track "total tests"

## Impact

- **Priority**: P2 — High maintenance burden + false confidence from inflated metrics
- **Effort**: Small — Straightforward consolidation with clear patterns; low technical risk
- **Risk**: Low — No production code changes; test-only refactoring
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Development setup and testing guidelines |
| [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | Test organization principles |

## Labels

`test-quality`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-05T22:11:03 - `c00441d3-195f-4810-a78d-949b98493d5c.jsonl`
- `/ll:capture-issue` - 2026-06-05T21:16:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5cc001a-5129-4d2d-807d-39a428af0331.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
