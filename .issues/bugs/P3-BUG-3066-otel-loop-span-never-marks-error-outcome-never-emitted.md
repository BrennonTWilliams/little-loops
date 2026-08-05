---
discovered_commit: fc652df07b9234f2a79fb0663efd253590b170eb
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: audit-docs
status: open
labels: [observability, otel]
---

# BUG-3066: OTel loop spans never close ERROR — `loop_complete` never carries `outcome`

## Summary

`OTelTransport` decides a loop span's final status by reading an `outcome` key off the
`loop_complete` event, but no emitter ever sets that key. Every loop span therefore closes
`StatusCode.OK`, including runs that crashed, timed out, or landed on a `failure: true`
terminal. The same latent read exists in the SQLite writer.

## Current Behavior

`scripts/little_loops/transport.py:471-475`:

```python
outcome = str(event.get("outcome", ""))
...  # _OTEL_ERROR_OUTCOMES = frozenset({"error", "failed", "exhausted"})
```

`scripts/little_loops/session_store/writers.py:1941-1942` does the analogous
`state = event.get("outcome", state)`.

The only producer of `loop_complete` is `FSMExecutor._finish`
(`scripts/little_loops/fsm/executor.py:3202-3217`), whose payload is:

```python
payload = {
    "final_state": self.current_state,
    "iterations": self.iteration,
    "terminated_by": terminated_by,
    "failure_terminal": failure_terminal,
}
if error is not None:
    payload["error"] = error
```

No `outcome`. The lookup always falls through to `""`, which is not in
`_OTEL_ERROR_OUTCOMES`, so the span is marked `OK`. Only `scripts/tests/test_transport.py`
(lines 715, 751) exercises the ERROR branch, and it does so by hand-constructing an event
with an `outcome` key that production never produces — so the tests pass while the
behavior is dead.

## Expected Behavior

A loop that terminated in failure produces a span with `StatusCode.ERROR`, so OTel-based
dashboards and alerting can distinguish failed runs from successful ones.

## Proposed Solution

Two viable directions; pick one deliberately rather than patching both reads:

**Option A — read what is already emitted.** Change `transport.py` and
`writers.py` to derive status from `failure_terminal` (ENH-2814, emitted
unconditionally) and `terminated_by` (`"error"`, `"timeout"`, `"max_steps"`,
`"stall_detected"`, `"cycle_detected"`, `"host_pressure_abort"`,
`"host_budget_exceeded"`, …). No wire-format change; consumers of the JSONL stream are
unaffected. Requires deciding which `terminated_by` values count as failures — note
`failure_terminal` alone is insufficient, since it is `false` for a crash
(`terminated_by="error"`).

**Option B — emit `outcome`.** Add a derived `outcome` field to the `loop_complete`
payload in `_finish`, keeping the existing reads intact. Wire-format addition, so
`generate_schemas.py`'s `loop_complete` entry and `docs/reference/EVENT-SCHEMA.md` need the
new field too.

Option A is the smaller change and avoids adding a second, redundant encoding of failure to
the event payload.

## Impact

- **Priority**: P3 — observability-only; no runtime behavior or data loss. Matters
  to anyone routing loop telemetry into OTel and alerting on span status.
- **Effort**: Small — one predicate plus tests, once the direction is chosen.
- **Risk**: Low. The main risk is a test suite that currently passes for the wrong
  reason: `test_transport.py`'s ERROR-path tests must be rewritten to feed a
  realistic `loop_complete` payload, or the fix will look verified when it is not.

## Integration Map

- `scripts/little_loops/transport.py` — `OTelTransport` span-closing logic (~line 471)
- `scripts/little_loops/session_store/writers.py` — `outcome` fallback (~line 1941)
- `scripts/little_loops/fsm/executor.py` — `_finish()` payload (line 3202), only if Option B
- `scripts/tests/test_transport.py` — lines ~715, ~751 currently synthesize `outcome`
- `docs/reference/EVENT-SCHEMA.md` — the OTel span-closing table now documents this gap
  explicitly; update it once the behavior is fixed
- `scripts/little_loops/generate_schemas.py` + `docs/reference/schemas/loop_complete.json` —
  only if Option B

## Related Key Documentation

- [docs/reference/EVENT-SCHEMA.md](../../docs/reference/EVENT-SCHEMA.md) — `loop_complete`
  field table and the OTel span-closing table
- `thoughts/audit-docs-reference-2026-08-05.md` — the docs audit that surfaced this

---

## Status

**Open** | Created: 2026-08-05 | Priority: P3
