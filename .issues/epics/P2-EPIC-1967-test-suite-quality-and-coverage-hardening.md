---
id: EPIC-1967
type: EPIC
priority: P2
status: done
captured_at: '2026-06-05T22:00:00Z'
discovered_date: 2026-06-05
discovered_by: scope-epic
relates_to:
- ENH-1963
- ENH-1964
- ENH-1965
- ENH-1966
---

# EPIC-1967: Test Suite Quality & Coverage Hardening

## Summary

Four test-quality improvements identified by a comprehensive test suite audit on 2026-06-05: consolidate 59 doc-wiring test files that exercise zero application code (ENH-1963), add snapshot/golden-file testing infrastructure as a prerequisite for safe TUI testing (ENH-1965), add CLI-layer test coverage for sprint and loop subpackages where users invoke commands (ENH-1964), and fill P1 test gaps in FSM runners, issue history analytics, and CLI modules totaling ~2,620 lines with zero dedicated tests (ENH-1966).

## Motivation

A comprehensive test suite audit found the suite has structural quality issues that inflate the count without proportionate coverage:

1. **23.4% of test files are doc-wiring noise** (ENH-1963) — they verify strings in `.md` files, not application logic, creating a false sense of thoroughness
2. **No snapshot testing infrastructure** (ENH-1965) — makes TUI regression testing fragile or impossible; blocks safe testing of the 1,981-line `cli/loop/layout.py`
3. **CLI layer has near-zero coverage** (ENH-1964) — the user-facing layer is untested while the domain model underneath is well-tested (92 tests in `test_sprint.py`, 26 integration tests)
4. **P1 modules with zero dedicated tests** (ENH-1966) — FSM runner execution path (`fsm/runners.py`, 313 lines) and analytics modules (`issue_history/debt.py`, `issue_history/quality.py`, 945 lines combined) have no test files; three CLI modules (`cli/deps.py`, `cli/history.py`, `cli/messages.py`, 1,362 lines) also uncovered

Together, these four gaps mean the 252-file test suite has blind spots where user-facing regressions would go undetected.

## Goal

When this epic is done:
- Doc-wiring tests are consolidated into ≤5 parametrized files or replaced with a lint rule
- A snapshot/golden-file testing library is integrated and usable by all CLI tests
- Sprint and loop CLI commands have test coverage for their primary user-facing paths
- `fsm/runners.py`, `issue_history/{debt,quality}.py`, and `cli/{deps,history,messages}.py` each have a dedicated test file with meaningful coverage

## Scope

### In Scope
- Consolidating or replacing doc-wiring tests (ENH-1963)
- Integrating a snapshot testing library (e.g., `syrupy` or `pytest-snapshot`) (ENH-1965)
- Adding CLI-layer tests for sprint and loop subpackages (ENH-1964)
- Adding dedicated test files for `fsm/runners.py`, `issue_history/{debt,quality}.py`, `cli/{deps,history,messages}.py` (ENH-1966)
- Test infrastructure patterns that downstream tests can adopt

### Out of Scope
- Achieving a specific numeric coverage target — these are targeted gap fills, not a coverage ratchet
- Rewriting existing tests for style — ENH-1963 is about consolidation, not line-editing every test
- Adding tests for deferred or experimental features
- Performance benchmarking tests

## Children

- **ENH-1963** — Audit and Consolidate Doc-Wiring Tests
- **ENH-1965** — Add Snapshot/Golden-File Testing for CLI Output (prerequisite for ENH-1964)
- **ENH-1964** — Add CLI Layer Tests for Sprint and Loop Subpackages (depends on ENH-1965)
- **ENH-1966** — Fill P1 Test Gaps in fsm/runners, issue_history, and CLI Modules

## Success Metrics

- **Doc-wiring**: ≤5 parametrized test files replace 59 single-purpose doc-wiring tests, or a lint rule replaces them entirely
- **Snapshot infra**: At least one CLI command has snapshot-based regression tests
- **CLI coverage**: Sprint and loop CLI commands have at least one test each for their primary user-facing paths
- **P1 gap fill**: Each of the 6 identified modules has a dedicated test file with ≥1 meaningful test
- **No regressions**: All existing tests pass; no existing coverage lost

## Dependencies

- ENH-1965 (snapshot infra) is a declared prerequisite for safe TUI rendering tests in ENH-1964
- ENH-1963 (doc-wiring consolidation) should be done first to reduce noise before coverage work
- ENH-1964 and ENH-1966 can proceed independently after ENH-1963 and ENH-1965 are complete

## Impact

- **Priority**: P2 — Structural test quality issues that affect development velocity and regression confidence
- **Effort**: Medium — ~50-150 lines of code each, plus test files and library integration
- **Risk**: Low — all changes are additive (new tests, new library); no application logic changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`epic`, `test-quality`, `test-coverage`, `test-infrastructure`, `cli`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
