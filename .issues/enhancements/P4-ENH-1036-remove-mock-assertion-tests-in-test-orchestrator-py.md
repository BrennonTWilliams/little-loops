---
discovered_date: 2026-04-11
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 95
---

# ENH-1036: Remove Mock-Assertion Tests in test_orchestrator.py

## Summary

`test_orchestrator.py` contains ~15–20 tests whose only assertion is `mock_X.assert_called_once()` on a constructor mock. These verify the test's own mock setup, not orchestration behavior. Also contains multiple near-identical `__init__` state verification tests. Remove the constructor-only mock tests and consolidate duplicate init tests.

## Current Behavior

~21% of `test_orchestrator.py` tests (out of 113) assert only that a mock constructor was called — e.g., `mock_wp.assert_called_once()`. These pass trivially because the test itself invokes the constructor. Additionally, multiple tests repeat near-identical `__init__` attribute verification.

## Expected Behavior

Only tests that verify real orchestration behavior (dependency wiring, error handling, state transitions) remain. Constructor-only mock tests are removed. Duplicate init tests are consolidated into a single parametrized test. Test count reduced by ~15–20.

## Motivation

Constructor-only mock assertions are tautological — they can never fail unless the test itself is broken. They give false confidence, inflate counts, and make the suite harder to audit. Removing them clarifies what the orchestrator is actually tested against.

## Proposed Solution

1. Delete tests where the sole assertion is `mock_X.assert_called_once()` or `mock_X.assert_called_once_with(...)` on a constructor mock with no other behavioral assertions.
2. Identify `__init__` state verification tests that overlap and consolidate into one `@pytest.mark.parametrize` test covering each attribute.

## Integration Map

### Files to Modify
- `scripts/tests/test_orchestrator.py`

### Dependent Files (Callers/Importers)
- N/A — test-only change

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_orchestrator.py` — the file being modified

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/test-quality-audit.md:9-13` — test count table (`~4,061` total, `87` files) becomes stale; this issue removes ~3 tests from `test_orchestrator.py` [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Constructor-only `assert_called_once` pattern in the wild:**
- `scripts/tests/test_orchestrator.py:204` — `test_init_creates_shared_git_lock` has `mock_wp.assert_called_once()` (L224) and `mock_mc.assert_called_once()` (L225) as supplementary assertions. Its real assertion is `assert orch._git_lock is not None`. The mock assertions are tautological (constructor was obviously called to build the orchestrator), but the test has a non-trivial purpose — retain the `_git_lock` assertion, drop the `mock_wp.assert_called_once()` and `mock_mc.assert_called_once()` lines.
- All other `assert_called_once` usages in the file appear inside tests with substantial behavioral assertions alongside them — they are _not_ sole-assertion tests.

**Near-identical `__init__` state verification tests in `TestOrchestratorInit`:**
- `test_init_sets_attributes` (L161): asserts `parallel_config`, `br_config`, `repo_path`, `_shutdown_requested` — 4 attributes
- `test_init_creates_empty_issue_info_dict` (L227): asserts only `_issue_info_by_id == {}`
- `test_init_creates_orchestrator_state` (L234): asserts only `isinstance(orchestrator.state, OrchestratorState)`

L227 and L234 each test a single attribute that could be folded into `test_init_sets_attributes` at L161, or into a combined parametrized attribute test.

**Clarification note:** The issue's claim of "~15–20 pure mock-assertion tests" appears to overcount. From analysis of all `assert_called_once` sites (27 occurrences across the file), only the two lines at L224-225 fit the description — and those are supplementary, not sole assertions. The higher-value target is the 3 near-identical `__init__` tests that can be merged.

## Implementation Steps

1. Grep for `assert_called_once` in `test_orchestrator.py`; identify tests where that is the only assertion
2. Delete those test functions
3. Identify groups of `__init__` tests with near-identical structure; collapse into parametrized form
4. Run `python -m pytest scripts/tests/test_orchestrator.py -v --tb=short` and confirm all remaining tests pass
5. Verify test count drops by ~15–20

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete implementation guidance:_

**Step 1 — `test_init_creates_shared_git_lock` (L204):**
Remove the two tautological lines at L224-225 (`mock_wp.assert_called_once()`, `mock_mc.assert_called_once()`). The meaningful assertion `assert orch._git_lock is not None` (L223) stays. To verify the git_lock is _passed_ to the constructors, replace with `assert mock_wp.call_args.kwargs.get("git_lock") is orch._git_lock` if that wiring matters, or drop entirely.

**Step 2 — Merge `test_init_creates_empty_issue_info_dict` (L227) and `test_init_creates_orchestrator_state` (L234) into `test_init_sets_attributes` (L161):**
Add the two attribute assertions from L232 and L239 into the existing multi-attribute test at L180-183. Both use the same `orchestrator` fixture so no setup changes needed.

**Revised count estimate:** After research, the realistic reduction is ~3 tests (2 merged into existing, 2 mock lines dropped from 1 test) rather than the originally estimated 15–20. Confirm the actual count before setting expectations in the PR.

**Test command:**
```bash
python -m pytest scripts/tests/test_orchestrator.py -v --tb=short
```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/test-quality-audit.md:9-13` — decrement the total test count by ~3 to reflect removed/merged tests

## Scope Boundaries

- **In scope**: Removing constructor-only mock assertion tests and consolidating duplicate `__init__` state verification tests in `scripts/tests/test_orchestrator.py`
- **Out of scope**: Changes to production code, changes to other test files, removing any test that asserts behavioral outcomes beyond constructor invocation

## Impact

- **Priority**: P4 - Test quality cleanup, no behavioral change
- **Effort**: Small-Medium - Requires careful review to avoid removing tests with hidden value
- **Risk**: Low - Tests only; no production code changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`test-quality`, `test_orchestrator`, `captured`

## Status

**Open** | Created: 2026-04-11 | Priority: P4

---

## Session Log
- `/ll:wire-issue` - 2026-04-11T20:12:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a526cc2e-06c1-44e3-add0-5ba3cb7b1190.jsonl`
- `/ll:refine-issue` - 2026-04-11T20:08:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2f0bc40-5233-4c1b-a17d-6bd5566483a9.jsonl`
- `/ll:format-issue` - 2026-04-11T20:03:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da64ad23-684f-4724-8a57-4063931ce01c.jsonl`
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9439fb7-57cc-417c-9114-6eea87ed8705.jsonl`
- `/ll:confidence-check` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c5c369e-95b9-4fe0-a53f-b4bd65093912.jsonl`
