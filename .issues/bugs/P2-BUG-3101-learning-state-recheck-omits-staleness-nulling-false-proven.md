---
id: BUG-3101
priority: P2
type: BUG
status: open
captured_at: '2026-08-08T04:44:28Z'
discovered_date: '2026-08-08'
discovered_by: capture-issue
discovered_commit: 2371728a
discovered_branch: main
labels:
- learning-tests
- fsm
- gates
relates_to:
- BUG-3100
- BUG-3102
- ENH-3073
---

# BUG-3101: Learning-state re-check omits staleness nulling, producing a false `proven` verdict

## Summary

`_execute_learning_state` treats a date-stale `proven` record as absent so the retry path
re-proves it (ENH-2208). That nulling is applied **once, before** the retry loop. The
re-check **inside** the loop is a bare `check_learning_test(target)` with no such treatment.

So a remedy that changes nothing returns the same still-stale `proven` record, the `while`
condition goes false, and the state emits `learning_target_proven` and routes `on_yes`. The
gate reports success for a target it never verified, and the retry budget never engages.

## Current Behavior

In `scripts/little_loops/fsm/executor.py`, `_execute_learning_state`:

```python
for target in targets:
    record = check_learning_test(target)
    # Treat a date-stale proven record as absent so the retry path
    # re-proves it (ENH-2208).
    if (
        _lt_staleness_enabled
        and record is not None
        and record.status == "proven"
        and is_record_stale(record, _lt_stale_days)
    ):
        record = None                      # <-- applied ONCE, here

    attempts = 0
    while record is None or record.status == "stale":
        if attempts >= max_retries:
            return _blocked_target("retries_exhausted", target)
        ...
        self._run_action(f"/ll:explore-api {target}", ...)
        attempts += 1
        record = check_learning_test(target)   # <-- nulling NOT re-applied

    if record.status == "refuted":
        ...
    self._emit("learning_target_proven", {...})
```

The pre-loop nulling and the in-loop re-check apply different definitions of "proven."

**Observed** — `ll-loop run ready-to-implement-gate --context "targets=ruamel.yaml"` against a
`proven` record dated `2026-06-19` (50 days old, `stale_after_days: 30`) on `2371728a`:

```
[1/50] prove (0s) -> ✦ /ll:explore-api ruamel.yaml
       [skill asked a question and returned without touching the record — BUG-3100]
       -> done
Loop completed: done (1 iterations, 25.5s)
```

One iteration, verdict `done`, record still `date: 2026-06-19`. `max_retries` is 2; neither
retry fired, because after attempt 1 the re-check returned a `proven` record and the loop
exited.

Contrast with the same record after `ll-learning-tests mark-stale` — where staleness lives in
the *status field* and so survives the re-check:

```
Loop completed: blocked (1 iterations, 51.8s)   # 2 invocations, then retries_exhausted
```

The retry machinery is correct. Only the date-staleness case is mis-evaluated, because that
form of staleness is dropped on re-read.

## Expected Behavior

The re-check inside the retry loop applies the same staleness definition as the pre-loop
check. A remedy that leaves a record date-stale consumes a retry; exhausting retries routes
`on_blocked` with `retries_exhausted`. `learning_target_proven` is emitted only for a record
that is both `proven` **and** not date-stale.

## Motivation

This is a correctness hole in a gate whose only purpose is correctness. `ready-to-implement-gate`
is what `ll-auto` runs before implementing any issue declaring `learning_tests_required` — it
exists to guarantee the agent has verified the external API it is about to build against.

Today that gate returns `done` for any target with a date-stale `proven` record, having
verified nothing. The failure is silent and indistinguishable from a real pass, so it does not
merely fail to help — it actively certifies unverified ground. Of this repo's 31 records, 7 are
date-stale right now, and every one of them would pass the gate falsely.

It also masks [[BUG-3100]]: because the verdict is `done`, the skill's refusal to re-prove
looks like success at every layer above it.

## Root Cause

`scripts/little_loops/fsm/executor.py` → `_execute_learning_state`: the ENH-2208 date-staleness
nulling is inline, immediately after the initial `check_learning_test`, rather than factored
into a helper used by both read sites. The in-loop re-read calls `check_learning_test` directly
and inherits the raw registry semantics.

## Proposed Solution

Extract the nulling into a local closure and use it at both read sites:

```python
def _fresh_record(target: str):
    """Read a record, treating a date-stale ``proven`` record as absent (ENH-2208)."""
    rec = check_learning_test(target)
    if (
        _lt_staleness_enabled
        and rec is not None
        and rec.status == "proven"
        and is_record_stale(rec, _lt_stale_days)
    ):
        return None
    return rec

for target in targets:
    record = _fresh_record(target)
    attempts = 0
    while record is None or record.status == "stale":
        if attempts >= max_retries:
            return _blocked_target("retries_exhausted", target)
        ...
        self._run_action(f"/ll:explore-api {target}", ...)
        attempts += 1
        record = _fresh_record(target)      # same definition on both reads
    ...
```

Single definition, both call sites, no signature change and no ripple beyond this function.

Note this fix alone makes the gate **correctly blocked** rather than falsely `done` — it does
not make re-proving work. That requires [[BUG-3100]]. The two should land together; fixing this
one first turns a silent false pass into a loud, accurate block, which is the right ordering if
they must be split.

## Impact

- `ready-to-implement-gate` returns `done` for unverified targets — every date-stale record.
- `ll-auto` proceeds to implement issues whose `learning_tests_required` gate never ran.
- `ll-learning-tests prove` inherits the false success and exits 0 (its own reporting gap is
  covered by [[ENH-3073]]'s `cmd_prove` hardening).
- `migrate-sdk-version` would hit the same re-check once [[BUG-3102]] lets it queue anything.

## Integration Map

- `scripts/little_loops/fsm/executor.py` — `_execute_learning_state`, both record read sites
- `scripts/little_loops/learning_tests/gate.py` — `is_record_stale`, the shared predicate
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — canonical `type: learning` consumer
- `scripts/tests/test_learning_tests_gate.py`, `scripts/tests/test_learning_state.py` — existing
  coverage for the learning state; the regression test belongs in one of these

## Acceptance Criteria

- [ ] A test drives `_execute_learning_state` with a `proven` but date-stale record and a remedy
      that leaves the record untouched, and asserts the state routes `on_blocked` with
      `retries_exhausted` — **not** `on_yes`.
- [ ] A test asserts `learning_target_proven` is not emitted for a date-stale `proven` record.
- [ ] A test asserts the remedy is invoked `max_retries` times in that scenario (today: once).
- [ ] A remedy that genuinely re-dates the record still routes `on_yes` on the following
      re-check — the fix must not break the success path.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Issues

- BUG-3100 — `/ll:explore-api` refuses to re-prove an existing record; the reason the remedy is
  a no-op. This bug is what makes that no-op invisible; fix together
- BUG-3102 — `migrate-sdk-version` queues only `status: stale` records
- ENH-2208 — introduced the date-staleness nulling that this bug applies inconsistently
- ENH-3073 — blocked by this and BUG-3100

## Status

Open. Mechanism confirmed by reading `_execute_learning_state` and by direct reproduction on
`2371728a` (verdict `done` in 1 iteration against a 50-day-old record, retries never fired).
Fix is local to one function.


## Session Log
- `/ll:capture-issue` - 2026-08-08T04:47:04 - `0c442e3b-c3d8-4743-b597-7b3551a75ba6.jsonl`
