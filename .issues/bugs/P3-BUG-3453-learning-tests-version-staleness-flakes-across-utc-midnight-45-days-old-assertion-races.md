---
id: BUG-3453
type: BUG
title: "learning-tests version staleness: test_age_stale_names_the_age + test_age_stale_still_names_days flip to <!-- ll-evidence-ok: runtime symptom of the midnight flip, not a source-code quote --> '46 days old' when pytest execution spans the test process's local midnight (UTC on the CI runner)"
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
learning_tests_required:
- pytest
---

# BUG-3453: learning-tests version staleness flakes across local midnight of the test process (45-days-old assertion races)

## Summary

`scripts/tests/test_learning_tests_version_staleness.py` hard-codes `"45 days old"` assertions at lines `:210` and `:422`. The test's `_record(age_days=45)` stamps each record's `date` field from a module-level `TODAY = datetime.date.today()` (`:26`, applied `:40`), but `scripts/little_loops/learning_tests/gate.py:164` and `:202` compute the record's age against the **live** `datetime.date.today()` at assertion time.

`datetime.date.today()` reads the **local** date of the process, so the boundary is the runner's local midnight (the CI runner is on UTC, hence the 00:00Z failure; a CDT dev machine would race at 05:00Z). When a single pytest execution spans that midnight, the live `today()` advances one day past the frozen module-level `TODAY`. The record's computed age flips from `45` to `46`, and the hard-coded assertion `assert describe_staleness(_record(age_days=45), 30) == "stale: 45 days old"` fails <!-- ll-evidence-ok: "46 days old" is a runtime symptom of the midnight flip, not a source-code quote; the test asserts "45 days old" --> with `stale: 46 days old == stale: 45 days old`.

Pre-existing on `main` since the test file was added (commit `0a4a4030`, 2026-08-09). Not previously observed because most runs do not span the runner's local midnight.

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

- A pytest run that starts before the process's local midnight and asserts after it flips `age` by +1 day relative to the module-level `TODAY`.
- The test's hard-coded `"stale: 45 days old"` literal fails.
- The test's hard-coded `"45 days old" in result.feedback` substring fails.
- Both failures emit the same date-arithmetic-mismatch signature — diagnostic, not destructive.

## Expected Behavior

- Both tests pass regardless of pytest session start time.
- The frozen `TODAY` (or its replacement) and the production code's `today()` share one source — no midnight-boundary divergence.

## Steps to Reproduce

1. Stage an environment that runs pytest across the process's local midnight (on the UTC CI runner: near `00:00Z`).
2. `python -m pytest scripts/tests/test_learning_tests_version_staleness.py -v`
3. Observe `test_age_stale_names_the_age` and `test_age_stale_still_names_days` fail with `stale: 46 days old` / `<!-- ll-evidence-ok: runtime symptom --> 46 days old in feedback`.

## Likely Root Cause

`test_learning_tests_version_staleness.py:26` pins `TODAY = datetime.date.today()` at module import time. The test fixture writer (`_record`, `:29`) applies that pinned value. The production code under test (`learning_tests/gate.py:164`, `:202`) calls `datetime.date.today()` fresh at runtime. When the runtime call happens on a later date than the import-time call, the arithmetic diverges by exactly the day-boundary delta.

This is a test-determinism race, not a source-code bug — `gate.py`'s use of live `today()` is correct in production (it should reflect the current date, not a frozen one).

## Proposed Solution

**Chosen shape: module-scoped shim freeze, test file only.** `gate.py` is not modified.

`gate.py` does `import datetime` and uses only `datetime.date.today` and `datetime.date.fromisoformat`. Replace the `datetime` name *inside `gate.py`* with a shim, so nothing process-global is mutated:

```python
FROZEN_TODAY = datetime.date(2026, 1, 15)  # fixed past date; replaces module-level TODAY


class _FrozenDate(datetime.date):
    @classmethod
    def today(cls) -> "datetime.date":
        return FROZEN_TODAY


@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "little_loops.learning_tests.gate.datetime",
        types.SimpleNamespace(date=_FrozenDate),
    )
```

- The fixture is **module-wide autouse** (not limited to the two failing classes), so every `_record(age_days=…)` and every `gate.py` clock read (`:164`, `:202`, and the `:192` → `:164` second read, plus the hook's reads) derive from `FROZEN_TODAY`. Module-level `TODAY = datetime.date.today()` is deleted; `_record` uses `FROZEN_TODAY`.
- `_FrozenDate` subclasses `datetime.date`, so `fromisoformat` keeps working (returns a `_FrozenDate`; subtraction with `date` yields a normal `timedelta`). `monkeypatch` restores on teardown.
- If `gate.py` later uses another `datetime` attribute, the shim raises `AttributeError` loudly — add the attribute to the namespace.

**Rejected: parameterize `today`** on `is_record_stale`/`describe_staleness`. It changes a documented public signature (`docs/reference/API.md:7456-7457`) for a test-only flake, and prior decision records (`.ll/decisions.d/16221a09-…`, `72e163e7-…`) already weigh against signature changes there. **Rejected: patching `gate.datetime.date`** — that attribute lives on the global stdlib module, so the patch is process-wide.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- The two shapes above differ in blast radius, not just effort: the fixture-freeze shape touches only the test file but must cope with the global-`datetime` patch constraint; the parameterize shape changes a public function signature (documented in `docs/reference/API.md:7456-7457`) and would need `describe_staleness` to pass one `today` through to `is_record_stale` so its two reads cannot diverge, plus updating the hook's call sites only if they are to pass it. Acceptance Criterion "`gate.py` continues to use live `datetime.date.today()`" is compatible with both only if the default remains the live date.
- A third property to weigh, not a recommendation: making `_record` compute age relative to the same frozen value is sufficient only if the freeze is active for the whole test including the hook invocation.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- Files to Modify: `scripts/tests/test_learning_tests_version_staleness.py` — module-level `TODAY` (:26), `_record` (:29, applies `TODAY` at :40), exact-age assertions at :210 (`TestDescribeStaleness.test_age_stale_names_the_age`) and :422 (`TestHookStaleMessage.test_age_stale_still_names_days`). These two are the only exact-string age assertions in the file; every other `age_days` test is threshold-based and a one-day shift changes none of their outcomes.
- Production clock reads: `learning_tests/gate.py` does `import datetime` (:14, no `from datetime import date`) and reads the clock in `is_record_stale` (:97, read at :164) and `describe_staleness` (:168, read at :202). `describe_staleness` also calls `is_record_stale` (:192), so one stale `describe_staleness` call reads the clock twice; the hook path reads it three times per stale package. Any freeze must cover all reads consistently.
- Hook path: `hooks/learning_tests_gate.py:gate` calls `is_record_stale` (:138) then `describe_staleness` (:145) and renders "stale: N days old" into feedback (:165-171). `_SESSION_CACHE` must be cleared by the test (the existing hook test already does).
- Other consumers of `is_record_stale` that reach the clock only through `gate.py`: `hooks/install_learning_gate.py:123`, `cli/learning_tests.py:53`, `cli/ctx_stats.py:734`, `cli/history_context.py:76`, `fsm/executor.py:1459`, `loops/migrate-sdk-version.yaml:44`, `learning_tests/release_gate.py:59`. Separately, `release_gate.py:78` makes its own `datetime.date.today()` read (Days Since Proven column).
- Same-class exposure (live `today()` inside test bodies, unpatched production clock, threshold-relative): `test_learning_tests_discoverability.py:490,497`, `test_install_learning_gate.py:54,237`, `test_cli_learning_tests.py:278,315`, `test_learning_state.py:638`, `test_release_gate.py:49,265`. Only `test_learning_tests_version_staleness.py:26` pins the clock at import time; the boundary-adjacent ones (`:490`, `:497`) are the next most exposed but a one-day shift does not flip them.
- Docs: `docs/reference/API.md:7456-7457` (`gate.is_record_stale`, `gate.describe_staleness`) — must stay accurate if a signature changes; `docs/guides/LEARNING_TESTS_GUIDE.md` "What Makes a Record Stale".

**Conventions in force**
- No clock-freezing dependency exists (`freezegun`/`time-machine` absent from `scripts/pyproject.toml`); tests that need a fixed instant substitute the clock the production module itself reads — evidence: `test_pricing.py` (`TestIntroPricing`), `test_issue_history_debt.py` (patch the module-level `date` name), `test_drift_check.py` (`_Clock` fixture over a module `_now` seam), `test_cli_loop_background.py` (~:1417, module `datetime` replaced by a frozen class). Two schools coexist: patch the imported name vs. swap an injected `_now` seam; neither is dominant.
- Production functions that accept an optional time argument exist elsewhere (`fleet_improve.utc_stamp(now=None)`, `cli/issues/create.create_issue(..., now=None)`), so a defaulted `today` parameter is within codebase norms, but nothing in `learning_tests/` has one today.
- Constraint on any patch-based freeze: `gate.datetime` is the global stdlib `datetime` module, and `datetime.date` is an immutable C type whose `today` cannot be set directly. Replacing `gate.datetime.date` mutates the module process-wide (including the test module's own `fromisoformat`/`timedelta` use), so a replacement must subclass `datetime.date`, keep `fromisoformat` working, and be restored on teardown; replacing only the `datetime` attribute inside `gate.py` scopes the effect to that module. `release_gate.py:78` is not covered by a `gate.py`-scoped freeze.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/install_learning_gate.py:47` — has its own `_SESSION_CACHE` (used `:114-134`), separate from `learning_tests_gate._SESSION_CACHE` (`:47`, used `:132-158`); a freeze fixture in the hook test must clear the right one. `test_install_learning_gate.py:69,71` clears it [Agent 1 finding]
- `scripts/little_loops/loops/migrate-sdk-version.yaml:37,44` — inline Python snippet imports and calls `is_record_stale(r, lt.stale_after_days)`; would need no change under a defaulted trailing `today` kwarg [Agent 2 finding]
- `.ll/decisions.d/16221a09-81b5-4f6b-8727-9e38f08b4c11.json`, `.ll/decisions.d/72e163e7-46bf-4580-a8ce-ba1c2daf01f1.json` — prior decision records noting a signature change would "break 7 production call sites of is_record_stale plus a 6-test class"; supports the fixture-freeze shape (no `gate.py` change) [Agent 2 finding]
- Nothing imports `TODAY` or `_record` from `test_learning_tests_version_staleness.py` (searched `scripts/`, 0 hits outside its own docstring), so replacing `TODAY` is file-local [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:15451` — helper builds `record_date` from live `datetime.date.today()`; `:15484` uses the same `today - 45 days` pattern against the unpatched production clock. Same-class exposure, threshold-relative, not flipped by a one-day shift; out of scope unless the fix is generalised [Agent 1 finding]
- `scripts/tests/test_cli_ctx_stats.py:1298,1319,1406` — live `today()` in learning-record tests exercising `cli/ctx_stats.py:734`; same-class exposure [Agent 1 finding]
- `scripts/tests/test_history_context_cli.py:495` — `fresh_date = datetime.date.today().isoformat()` exercising `cli/history_context.py:76`; same-class exposure [Agent 1 finding]
- `scripts/tests/test_learning_tests_discoverability.py:472` — additional `today` read in the `is_record_stale` helper tests, beside the known `:490,:497` edge-date tests [Agent 1 finding]
- `scripts/tests/test_learning_tests_version_staleness.py` — ~20 direct calls to `is_record_stale(rec, 30, installed_version=…, backstop_multiplier=…, version_aware=…)` (`:110-197`) and `describe_staleness(rec, 30, installed_version=…)` (`:207-220`); these break only under the parameterize shape if `today` were made required (a defaulted kwarg leaves them intact) [Agent 3 finding]
- No shared clock fixture exists in `scripts/tests/conftest.py`, so the freeze fixture must be local to the file (no freezegun/`freeze_time` anywhere in `scripts/tests/`) [Agent 1 + 3 finding]
- Freeze precedents to model on: `test_issue_history_debt.py:76-165` and `test_pricing.py:73-94` (`mock_date.today.return_value`, patch the module-level `date` name); `test_cli_loop_background.py:1422` (`monkeypatch.setattr(_helpers, "datetime", _FrozenDatetime)`); `test_feat3304_artifact_dashboard.py:892-919` (`patch("…dashboard.datetime")`, but that module uses `from datetime import …`, so it is not the same shape as `gate.py`'s `import datetime`) [Agent 3 finding]
- New-test shape for `gate.py`: `monkeypatch.setattr("little_loops.learning_tests.gate.datetime", shim)`, where `shim` exposes a `date` subclass overriding `today()` plus the real `timedelta`; it must keep `date.fromisoformat` working because `gate.py:202` calls it [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- No convention for clock-freezing exists in `docs/development/TESTING.md` or `CONTRIBUTING.md` (0 hits for freeze/frozen/`date.today`); no doc update is required for a test-only fix [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_learning_tests_version_staleness.py` — replace module-level `TODAY` (`:26`) with a per-test frozen value shared by `_record` (`:40`) and `gate.py`'s reads at `:164` and `:202`; also cover the second read via `is_record_stale` (`gate.py:192`) and the hook's third read
- Clear `learning_tests_gate._SESSION_CACHE` in the hook-test freeze path (`:400`, `:418` already do); do not confuse it with `install_learning_gate._SESSION_CACHE`
- Do not touch `release_gate.py:78` (separate `date.today()` read) unless the fix is widened beyond this file
- Optional follow-up (not part of this fix): apply the same freeze to the same-class-exposure tests listed above

## Program Design

### Types

- `FROZEN_TODAY: datetime.date` — fixed constant (`2026-01-15`) in `test_learning_tests_version_staleness.py`; replaces the import-time `TODAY` pin
- `_FrozenDate(datetime.date)` — subclass whose `today()` returns `FROZEN_TODAY`

### Signatures

- `_freeze_today(monkeypatch: pytest.MonkeyPatch) -> None` — module-wide autouse fixture that replaces the `datetime` name inside `little_loops.learning_tests.gate` with a shim namespace whose `date` is `_FrozenDate`
- `_FrozenDate.today() -> datetime.date` — classmethod on a `datetime.date` subclass; returns `FROZEN_TODAY`
- `_record(*, target: str = "requests", date: str | None = None, status: str = "proven", proven_package: str | None = None, proven_version: str | None = None, age_days: int | None = None) -> LearnTestRecord` — unchanged signature; derives `date` from the frozen value

### Call Path

`TestDescribeStaleness.test_age_stale_names_the_age` -> `describe_staleness` -> `is_record_stale` -> `_FrozenDate.today` (then `describe_staleness` -> `_FrozenDate.today` again for the rendered age)

`TestHookStaleMessage.test_age_stale_still_names_days` -> `gate` (`hooks/learning_tests_gate.py`) -> `is_record_stale` -> `_FrozenDate.today`; then `gate` -> `describe_staleness` -> `_FrozenDate.today`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- Accuracy of the Program Design above against the code: `is_record_stale` is in the hook path (called directly at `hooks/learning_tests_gate.py:138`); the `describe_staleness` call path omits the second clock read via `is_record_stale` (`gate.py:192` → `:164`); `_record` is a fixture builder, not a caller in the chain. `_freeze_today` is a proposed symbol, not yet defined. The proposed patch target `little_loops.learning_tests.gate.datetime.date` resolves but is process-global (see Integration Map → Conventions), so the freeze must preserve `fromisoformat` and restore on teardown.
- Invariant for the fix: the date `_record` stamps and every clock read inside `gate.py` during a test must derive from one value fixed for that test; production `gate.py` behavior with no test override must remain the live date.

## Acceptance Criteria

- `test_age_stale_names_the_age` passes regardless of pytest session start time.
- `test_age_stale_still_names_days` passes regardless of pytest session start time.
- `gate.py` continues to use live `datetime.date.today()` in production paths (no behavioral change for non-test callers).
- The expected age is independent of the wall clock: with `FROZEN_TODAY` fixed at a past date (`2026-01-15`), `_record(age_days=45)` renders exactly `"45 days old"` in both tests, and no `datetime.date.today()` call remains at module level in the test file.
- The freeze is scoped to `gate.py`'s `datetime` name — stdlib `datetime.date` is not mutated (`datetime.date.today()` called from the test body still returns the live date).
- No new test flake introduced for the non-staleness tests in this file (the file has 40 tests total; the 38 others must remain green under the module-wide autouse freeze).

## Impact

- **Priority**: P3 - Test-only flake; fires only when a pytest run spans UTC midnight, no production behavior affected
- **Effort**: Small - One module-wide autouse fixture + `_FrozenDate` shim (<30 lines) in a single test file; `gate.py` untouched
- **Risk**: Low - Test-only change, the other 38 tests in the file guard against regressions
- **Breaking Change**: No

## Workarounds

Until the fix lands, CI dispatch can avoid the race by not crossing the runner's local midnight (`00:00:00Z` on the UTC CI runner; this does not hold for a non-UTC runner). CI ran the affected dispatch starting `2026-09-11T23:59:00Z`; subsequent dispatches starting `2026-09-12T00:16:14Z` (post-midnight, so the race won't re-fire on the same calendar day) cleared without the flake. The flake recurs on the next UTC-midnight-spanning dispatch — this is a deferred failure, not a one-off.

## Notes

BUG-3453 is unrelated to PR #24 (CI-red + BUG-3439) and PR #26 (BUG-3449 finalize done-in-place). It is also unrelated to BUG-3450 (PATH-scrubbed `ll-issues` shellout — same root defect as BUG-3449, collapsed). Filing as a separate card so the fix has its own workstream and review trail.

Discovery: CI dispatch `34660035171` failed at `2026-09-12T00:00:08Z` (one minute after UTC midnight), which is the empirical confirmation that the race is real and timing-bound.

## Session Log
- `/ll:wire-issue` - 2026-09-20T18:06:35 - `dfde379e-92ee-423b-9352-612dbd7e60e2.jsonl`
- `/ll:refine-issue` - 2026-09-20T18:02:59 - `99b38819-b7a8-4a2f-ab59-e626b7d9bcfa.jsonl`
- `/ll:format-issue` - 2026-09-20T18:00:05 - `a1ec764a-736a-4d93-b965-dad72f2fef4e.jsonl`

---

## Status

**Open** | Created: 2026-09-12 | Priority: P3
