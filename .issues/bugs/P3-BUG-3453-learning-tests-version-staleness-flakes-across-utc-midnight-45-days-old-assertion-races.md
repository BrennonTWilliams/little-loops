---
id: BUG-3453
type: BUG
title: "learning-tests version staleness: test_age_stale_names_the_age + test_age_stale_still_names_days flip to <!-- ll-evidence-ok: runtime symptom of the midnight flip, not a source-code quote --> '46 days old' when pytest execution spans UTC midnight"
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-12'
captured_at: '2026-09-12T00:25:00Z'
labels:
- tests
- flake
- timezone
- learning-tests
---

# BUG-3453: learning-tests version staleness flakes across UTC midnight (45-days-old assertion races)

## Summary

`scripts/tests/test_learning_tests_version_staleness.py` hard-codes `"45 days old"` assertions at lines `:210` and `:422`. The test's `_record(age_days=45)` stamps each record's `date` field from a module-level `TODAY = datetime.date.today()` (`:26`, applied `:40`), but `scripts/little_loops/learning_tests/gate.py:164` and `:202` compute the record's age against the **live** `datetime.date.today()` at assertion time.

When a single pytest execution spans UTC midnight, the live `today()` advances one day past the frozen module-level `TODAY`. The record's computed age flips from `45` to `46`, and the hard-coded assertion `assert describe_staleness(_record(age_days=45), 30) == "stale: 45 days old"` fails <!-- ll-evidence-ok: "46 days old" is a runtime symptom of the midnight flip, not a source-code quote; the test asserts "45 days old" --> with `stale: 46 days old == stale: 45 days old`.

Pre-existing on `main` since the test file was added (commit `0a4a4030`, 2026-08-09). Not previously observed because most CI runs do not span midnight UTC.

## Context

Reproduced empirically on CI dispatch `34660035171` (head `9aa93ce74`, started `2026-09-11T23:59:00Z`, finished `2026-09-12T00:11:07Z` — pytest execution crossed UTC midnight at `00:00:00Z`). Both staleness tests failed with the same shape:

```
FAILED scripts/tests/test_learning_tests_version_staleness.py::TestDescribeStaleness::test_age_stale_names_the_age
  AssertionError: assert <!-- ll-evidence-ok: runtime symptom, not source quote --> 'stale: 46 days old' == 'stale: 45 days old'
    - stale: 45 days old
    ?         ^
    + stale: <!-- ll-evidence-ok: runtime symptom --> 46 days old
    ?         ^

FAILED scripts/tests/test_learning_tests_version_staleness.py::TestHookStaleMessage::test_age_stale_still_names_days
  assert '45 days old' in '[ll: proof-first hint] No learning-test record found
    for "requests" (stale: <!-- ll-evidence-ok: runtime symptom --> 46 days old). ...''
```

Verified line citations:
- `test_learning_tests_version_staleness.py:26` — `TODAY = datetime.date.today()` (module-level pin)
- `test_learning_tests_version_staleness.py:40` — `date = (TODAY - datetime.timedelta(days=offset)).isoformat()` (application site of the pin)
- `test_learning_tests_version_staleness.py:210` — first hard-coded assertion
- `test_learning_tests_version_staleness.py:422` — second hard-coded assertion (HookStaleMessage)
- `learning_tests/gate.py:164` — `age_days = (datetime.date.today() - record_date).days` (live today)
- `learning_tests/gate.py:202` — `age = (datetime.date.today() - datetime.date.fromisoformat(record.date)).days` (live today, second site)

## Current Behavior

- A pytest run that starts before UTC midnight and asserts after UTC midnight flips `age` by +1 day relative to the module-level `TODAY`.
- The test's hard-coded `"stale: 45 days old"` literal fails.
- The test's hard-coded `"45 days old" in result.feedback` substring fails.
- Both failures emit the same date-arithmetic-mismatch signature — diagnostic, not destructive.

## Expected Behavior

- Both tests pass regardless of pytest session start time.
- The frozen `TODAY` (or its replacement) and the production code's `today()` share one source — no midnight-boundary divergence.

## Steps to Reproduce

1. Stage an environment that runs pytest across UTC midnight (any runner scheduled near `00:00Z`).
2. `python -m pytest scripts/tests/test_learning_tests_version_staleness.py -v`
3. Observe `test_age_stale_names_the_age` and `test_age_stale_still_names_days` fail with `stale: 46 days old` / `<!-- ll-evidence-ok: runtime symptom --> 46 days old in feedback`.

## Likely Root Cause

`test_learning_tests_version_staleness.py:26` pins `TODAY = datetime.date.today()` at module import time. The test fixture writer (`_record`, `:29`) applies that pinned value. The production code under test (`learning_tests/gate.py:164`, `:202`) calls `datetime.date.today()` fresh at runtime. When the runtime call happens on a later date than the import-time call, the arithmetic diverges by exactly the day-boundary delta.

This is a test-determinism race, not a source-code bug — `gate.py`'s use of live `today()` is correct in production (it should reflect the current date, not a frozen one).

## Proposed Solution

Freeze the clock once per test class with a `monkeypatch` fixture on `datetime.date.today()` (or a class-level autouse fixture that swaps `_record` and `gate.py`'s `date.today()` for the same value). The two staleness tests then see one consistent `today()` regardless of when pytest imported the module.

Concretely, two implementation shapes both work and don't touch `gate.py`:

1. **Fixture freeze** — add an autouse class fixture that monkeypatches `datetime.date.today` to a fixed sentinel before each test in `TestDescribeStaleness` and `TestHookStaleMessage`. The fixture's `today` is passed into `_record` so the record's `date` and the production code's runtime call share one source.
2. **Parameterize `today`** — refactor `_record` and `gate.py`'s age computation to accept an optional `today` parameter (defaulting to `datetime.date.today()`). Tests pass an explicit fixed `today`. Source is unchanged for production callers.

Either shape is <30 lines. Both keep `gate.py` semantically identical for production use (the optional `today` parameter is a backward-compatible no-op when omitted).

## Program Design

### Types

- `TODAY: datetime.date` — module-level pin in `test_learning_tests_version_staleness.py` (to be replaced by a per-test frozen value)

### Signatures

- `_freeze_today(monkeypatch: pytest.MonkeyPatch) -> datetime.date` — autouse fixture body that patches `little_loops.learning_tests.gate.datetime.date` so `today()` returns the same value `_record` uses
- `_record(*, target: str = "requests", date: str | None = None, status: str = "proven", proven_package: str | None = None, proven_version: str | None = None, age_days: int | None = None) -> LearnTestRecord` — unchanged signature; derives `date` from the frozen value

### Call Path

`TestDescribeStaleness.test_age_stale_names_the_age` -> `_record` -> `describe_staleness` -> `datetime.date.today`

`TestHookStaleMessage.test_age_stale_still_names_days` -> `_record` -> `is_record_stale` -> `datetime.date.today`

## Acceptance Criteria

- `test_age_stale_names_the_age` passes regardless of pytest session start time.
- `test_age_stale_still_names_days` passes regardless of pytest session start time.
- `gate.py` continues to use live `datetime.date.today()` in production paths (no behavioral change for non-test callers).
- CI dispatch crossing UTC midnight no longer surfaces BUG-3453.
- No new test flake introduced for the non-staleness tests in this file (the 40 other tests must remain green).

## Impact

- **Priority**: P3 - Test-only flake; fires only when a pytest run spans UTC midnight, no production behavior affected
- **Effort**: Small - One fixture (<30 lines) in a single test file; `gate.py` untouched
- **Risk**: Low - Test-only change, the other 40 tests in the file guard against regressions
- **Breaking Change**: No

## Workarounds

Until the fix lands, CI dispatch can avoid the race by not crossing `00:00:00Z`. CI ran the affected dispatch starting `2026-09-11T23:59:00Z`; subsequent dispatches starting `2026-09-12T00:16:14Z` (post-midnight, so the race won't re-fire on the same calendar day) cleared without the flake. The flake recurs on the next UTC-midnight-spanning dispatch — this is a deferred failure, not a one-off.

## Notes

BUG-3453 is unrelated to PR #24 (CI-red + BUG-3439) and PR #26 (BUG-3449 finalize done-in-place). It is also unrelated to BUG-3450 (PATH-scrubbed `ll-issues` shellout — same root defect as BUG-3449, collapsed). Filing as a separate card so the fix has its own workstream and review trail.

Discovery: CI dispatch `34660035171` failed at `2026-09-12T00:00:08Z` (one minute after UTC midnight), which is the empirical confirmation that the race is real and timing-bound.

## Session Log
- `/ll:format-issue` - 2026-09-20T18:00:05 - `a1ec764a-736a-4d93-b965-dad72f2fef4e.jsonl`

---

## Status

**Open** | Created: 2026-09-12 | Priority: P3
