---
id: ENH-3677
type: ENH
title: Hoist the shared remote history-backend test fixture into conftest.py
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:30:36Z'
blocks:
- ENH-3657
- ENH-3658
---

# ENH-3677: Hoist the shared remote history-backend test fixture into conftest.py

## Summary

Hoist the `remote` test fixture (HranaStub + libsql `ll-config.json` + `chdir` + cache clears + `delenv("LL_HISTORY_DB")` + `remote_telemetry.reset_for_tests()` in teardown) into `scripts/tests/conftest.py` and delete the six per-file copies. Split out of the 2026-09-29 pre-implementation review of ENH-3657/ENH-3658: both plan many remote-stub tests, and BUG-3652 (landed `62ac0fc89`) did not hoist the fixture — it added a sixth copy.

## Current Behavior

The fixture is copied in `test_remote_operation_matrix.py:29`, `test_remote_hooks.py:29`, `test_libsql_backend.py:66` (plus a separate `stub` fixture), `test_remote_doctor.py:35`, `test_remote_ingestion_telemetry.py:57` and `test_remote_callers_bug3652.py:67`. The copies differ (telemetry reset, `LL_NON_INTERACTIVE` handling). `conftest.py` has none.

## Expected Behavior

One shared fixture in `conftest.py` (parametrize or add a variant if the copies differ materially); each remote test file uses it; new reader-CLI and hand-built-path remote tests (ENH-3657, ENH-3658) import it instead of adding copies.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] A single `remote` fixture lives in `scripts/tests/conftest.py`; the six copies are removed.
- [ ] Reconciled differences (telemetry reset in teardown, `LL_NON_INTERACTIVE`, the `stub` variant) are covered; all six files still pass unchanged in behavior.
- [ ] `python -m pytest scripts/tests/` passes.

## Related

- BUG-3652 (landed without hoisting), ENH-3657, ENH-3658 (blocked by this).

## Status

**Open** | Created: 2026-09-30 | Priority: P3
