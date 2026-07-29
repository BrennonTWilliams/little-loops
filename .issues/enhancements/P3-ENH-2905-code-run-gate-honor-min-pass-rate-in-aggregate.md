---
id: ENH-2905
type: ENH
priority: P3
status: open
captured_at: '2026-07-29T00:00:00Z'
discovered_date: 2026-07-29
discovered_by: manual
relates_to:
- BUG-2902
- BUG-2894
- ENH-2896
---

# ENH-2905: code-run-gate's `aggregate` should honor `min_pass_rate` independently of exit code

## Summary

[BUG-2902] fixes `code-run-gate`'s `aggregate` state
(`scripts/little_loops/loops/oracles/code-run-gate.yaml:366`) so a non-zero
test-command exit code is finally detected (it appends `exit_code=$RC` into
`test-results.txt`, matching `build.txt`/`typecheck.txt`/`lint.txt`). That fix
covers the common case — a failing suite that exits non-zero.

It deliberately does **not** make `aggregate` read the `pass_rate=` line that
`run_test` already writes to the sidecar. The `min_pass_rate` parameter the
loop advertises (lines 40-45) therefore remains decorative: a test runner that
exits 0 while reporting a pass rate below the configured threshold (e.g. a
wrapper script that swallows the real exit status, or a `min_pass_rate` set
below 1.0 to tolerate some flakiness) will still yield `GATE_PASS`.

This issue tracks implementing that second detector.

## Current Behavior

`aggregate` only greps sidecar files for `^exit_code=[1-9]`. It never parses or
compares the `pass_rate=<n>` line `run_test` writes. `min_pass_rate` is accepted
as a context parameter but has no effect on the verdict.

## Expected Behavior

`aggregate` parses the `pass_rate=` line from `test-results.txt` (via
`grep '^pass_rate='`, not the fragile `tail -1` BUG-2902 replaces it with) and
sets `ANY_FAIL` when the parsed value is below `${context.min_pass_rate}`, in
addition to the exit-code check. The SKIP path (`SKIP test_cmd=null`) must
remain unaffected — `aggregate`'s existing `case "$FIRST" in SKIP*)` branch
short-circuits before either detector runs.

## Root Cause

Sidecar-write/consumer asymmetry, same root as BUG-2902, but for the
`pass_rate` field specifically rather than `exit_code`. Never implemented
because BUG-2902/BUG-2894 (and the earlier mis-diagnosed version of BUG-2902)
were focused on the exit-code half; this is the leftover second half, split out
so BUG-2902 could land the higher-value, lower-risk fix first.

## Proposed Solution

1. In `aggregate`, alongside the existing exit-code grep loop, add a
   `pass_rate` check specific to `test-results.txt`:
   - Extract the value with `grep '^pass_rate=' test-results.txt | cut -d= -f2`
     (or equivalent).
   - Compare against `${context.min_pass_rate}` using `python3 -c` (POSIX `[ ]`
     has no float comparison — flagged as a risk in BUG-2902's Open Questions).
   - Set `ANY_FAIL=true` if below threshold.
2. Skip the check entirely when the sidecar's first line is `SKIP*` (no test
   command configured) — mirror the existing per-file SKIP handling.
3. Skip the check when no `pass_rate=` line is present (e.g. a test runner that
   doesn't report one) rather than treating absence as a failure.

## Implementation Steps

1. Add a test: a test command that exits 0 but whose `run_test` computation
   yields a `pass_rate` below `min_pass_rate` must yield `GATE_FAILED`.
2. Add a test: a `pass_rate` at or above `min_pass_rate` (exit 0) still yields
   `GATE_PASS`.
3. Add a test: the SKIP path (no test command) is unaffected by the new
   detector.
4. Implement the `aggregate` pass-rate detector per Proposed Solution.
5. Confirm `python -m pytest scripts/tests/` exits 0.

## Impact

- **Severity**: P3 — the common failure mode (non-zero exit) is already fixed
  by BUG-2902; this closes a narrower gap (exit-0-but-below-threshold or
  thresholds below 1.0).
- **Blast radius**: same as BUG-2902 — `rn-implement`/`rn-remediate`
  delegations and direct `ll-loop run oracles/code-run-gate` callers, only for
  configs that set `min_pass_rate < 1.0` or use exit-status-swallowing test
  wrappers.
- **Risk of fix**: Low-medium — enables a previously-decorative parameter;
  expect it to newly fail runs where `min_pass_rate` was set but never
  actually enforced.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | MR-1 non-LLM evaluator requirement |
| `.claude/CLAUDE.md` | Loop Authoring rules |

## Session Log
- manual - 2026-07-29 - split from BUG-2902's Open Questions per user request

---

## Status

open
