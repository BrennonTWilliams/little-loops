---
id: ENH-2742
title: "Verify state's classify() should distinguish \"missing npm script\" config error from real test failure"
type: ENH
priority: P3
status: open
captured_at: '2026-07-23T00:25:52Z'
discovered_date: 2026-07-23
discovered_by: audit
size: Small
labels:
- loops
- verify
- captured
---

# ENH-2742: Verify state's classify() should distinguish "missing npm script" config error from real test failure

## Summary

The FSM verify state's `classify()` returns `'failed'` for any non-zero exit
code other than 2 (`collection_error`). A missing npm script (e.g. `npm error
Missing script: "test"`) yields exit 1 with that stderr — semantically a
config/usage error, not a code defect — but it's indistinguishable from a real
test failure in `summary.json`'s `verify_verdict` field.

On this repo, every `sprint-refine-and-implement` run currently reports
`verify_verdict: "failed"` due to a `test_cmd` misconfiguration (`"npm test"`
run from repo root, where `package.json` lives in `studio/`) even though no
tests ever ran. A human reviewer can't tell "config broken" from "tests
broke" without opening `verify-detail.txt`.

## Current Behavior

```python
def classify(returncode):
    if returncode == 0: return 'passed'
    if returncode == 2: return 'collection_error'
    return 'failed'
```

## Expected Behavior

`classify()` accepts `stderr` and returns a distinct `'config_error'` verdict
when stderr indicates a missing/misconfigured script, rather than collapsing
it into `'failed'`.

## Proposed Solution

```python
def classify(returncode, stderr=""):
    if returncode == 0: return 'passed'
    if returncode == 2: return 'collection_error'
    if 'missing script' in stderr.lower(): return 'config_error'
    return 'failed'
```

**Note**: this is defense-in-depth. The simplest fix for the current repo is
correcting `test_cmd` in `.ll/ll-config.json` (tracked separately — see
P3-ENH-044, being investigated for reopening). This proposal guards against
future misconfigs of the same shape and makes `verify_verdict` a more
reliable closure signal generally.

## Implementation Steps

1. Locate the verify state's `classify()` implementation (FSM verify state
   action / supporting Python).
2. Thread `stderr` into the classification call alongside `returncode`.
3. Add the `'missing script'` (case-insensitive) match → `'config_error'`.
4. Update any downstream consumer of `verify_verdict` (e.g. `summary.json`
   writer) to pass through the new value unchanged.
5. Add a test asserting a "Missing script" stderr yields `config_error`, not
   `failed`.

## Sources

- `audit-loop-run-sprint-refine-and-implement-2026-07-18T045753.md` —
  Proposal #2 (state-level)

## Session Log
- `/ll:capture-issue` - 2026-07-23T00:25:52Z - `01b32c17-cae1-4173-b77e-b51fe2c99146.jsonl`
