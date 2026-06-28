---
id: ENH-2376
title: add a 'partial-with-errors' verdict to auto-refine-and-implement.finalize so
  ERR>0 is not laundered into plain 'partial'
type: ENH
status: open
priority: P3
captured_at: '2026-06-28T00:00:00Z'
discovered_date: '2026-06-28'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- verdict
relates_to:
- BUG-2374
---

# ENH-2376: add a 'partial-with-errors' verdict to auto-refine-and-implement.finalize

## Summary

`auto-refine-and-implement.record_error` (`auto-refine-and-implement.yaml:121-129`)
writes a crashed issue to both `*-errored.txt` and `*-skipped.txt`. The `finalize`
verdict logic then treats a run with `IMPL>0 && ERR>0` as plain `partial` —
indistinguishable from a clean partial where some issues were merely skipped. The
`ERR>0` signal (a sub-loop crash) is lost.

```bash
if   [ "$ERR" -gt 0 ] && [ "$IMPL" -eq 0 ]; then VERDICT=phantom
elif [ "$IMPL" -gt 0 ] && [ "$ERR" -eq 0 ] && [ "$SKIP" -eq 0 ]; then VERDICT=success
elif [ "$IMPL" -gt 0 ]; then VERDICT=partial   # ← ERR>0 collapses here too
else VERDICT=no-op
fi
```

## Expected Behavior

Add a distinct `partial-with-errors` (or `degraded`) verdict for
`IMPL>0 && ERR>0`, so callers and audits can tell a clean partial run from one
that experienced a sub-loop crash.

```bash
if   [ "$ERR" -gt 0 ] && [ "$IMPL" -eq 0 ]; then VERDICT=phantom
elif [ "$IMPL" -gt 0 ] && [ "$ERR" -gt 0 ]; then VERDICT=partial-with-errors
elif [ "$IMPL" -gt 0 ] && [ "$SKIP" -eq 0 ]; then VERDICT=success
elif [ "$IMPL" -gt 0 ]; then VERDICT=partial
else VERDICT=no-op
fi
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize`
  verdict ladder.

### Dependent Files (Context)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — recovers the
  verdict from `subloop_outcome_auto-refine-and-implement.txt`; verify it does
  not pattern-match only the known verdict strings.

### Tests
- `scripts/tests/test_builtin_loops.py` — add a `finalize` shell-execution test
  for the `IMPL>0 && ERR>0` case asserting `partial-with-errors`.

## Acceptance Criteria

- [ ] A run with `IMPL>0 && ERR>0` reports `verdict=partial-with-errors`.
- [ ] Existing `success` / `partial` / `phantom` / `no-op` cases are unchanged.
- [ ] Any parent consumer of the verdict string handles the new value.

## Impact

- **Priority**: P3 — cosmetic/signal-preservation; current `partial` is
  technically correct but lossy.
- **Effort**: Small.
- **Risk**: Low — verify no downstream consumer hard-codes the verdict set.

## Session Log
- `audit-loop-run` - 2026-06-28 - `.loops/audits/2026-06-28-sprint-refine-and-implement-audit.md`

---

## Status

**Open** | Created: 2026-06-28 | Priority: P3
