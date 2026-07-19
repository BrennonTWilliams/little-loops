---
id: BUG-2628
title: ll-loop run pre-flight validator falsely rejects ${context.X:shell} refs
type: BUG
priority: P2
status: done
labels:
- fsm
- cli
- loop-run
- interpolation
- captured
captured_at: '2026-07-13T16:14:24Z'
discovered_date: '2026-07-13'
discovered_by: user-report
completed_at: '2026-07-13T16:14:24Z'
---

# BUG-2628: ll-loop run pre-flight validator falsely rejects ${context.X:shell} refs

## Summary

The `ll-loop run` pre-run "required context variable" check
(`scripts/little_loops/cli/loop/run.py`) was never taught about the `:shell`
interpolation transform. Its capture regex `\$\{context\.([^}.]+)` grabs
`input:shell` as the whole variable name, and the skip-list only excused
`:default=` and trailing `?` guards. So for any loop referencing
`${context.<var>:shell}`, the validator looked up a nonexistent variable named
`<var>:shell`, reported it "missing", and returned 1 **before the loop ever
ran** — breaking the plain positional invocation
(`ll-loop run rn-implement "FEAT-123"`).

This is the same class of miss as **BUG-2553** (the validator not honoring
`:default=`/`?`), at the same lines. The interpolation engine itself
(`fsm/interpolation.py:248-250`) parses `:shell` correctly; the CLI pre-flight
just ran first and rejected the call.

## Current Behavior (before fix)

`ll-loop run rn-implement "FEAT-123"` exited 1 with:

```
Missing required context variable: 'input:shell'.
Run with: ll-loop run rn-implement --context input:shell=VALUE
```

The suggested `--context input:shell=VALUE` was a dead-end workaround: the CLI
`--context` parser does a bare `key.partition("=")`, so it set a context key
literally named `input:shell` — which `${context.input:shell}` never reads (the
engine reads `input`, then applies the shell-quote transform). The positional
`input` argument, which does map correctly into `fsm.context["input"]`, was
unreachable because the pre-flight rejected it first.

### Origin

The `:shell` suffix was added to 8 loops in commit `50f0a5c9` (2026-07-12) to
satisfy the new MR-11 lint rule (shlex-quote user-controlled values pasted into
shell bodies). The pre-flight validator's skip-list was not updated in the same
change.

### Severity / blast radius

Every loop with `${context.<uservar>:shell}` on a var not otherwise present in
context — 10 sites across 8 loops: `rn-implement.yaml`,
`refine-to-ready-issue.yaml`, `outer-loop-eval.yaml`, `prompt-across-issues.yaml`,
`cua-agent-desktop.yaml` (`description`), `loop-composer.yaml`,
`loop-composer-adaptive.yaml`, `loop-router.yaml` (`goal`).

## Expected Behavior

The pre-flight check strips the `:shell` transform suffix off the captured name
before the membership check (mirroring the engine's suffix handling), so
`${context.input:shell}` validates against the real var `input`. A genuinely
missing `${context.foo:shell}` still errors, reported under its real name `foo`
(never `foo:shell`). The positional `input` argument works as it always did.

## Root Cause

`run.py` context-variable loop: `_ctx_var_re` captures `input:shell`; the
`if ":default=" in raw or raw.endswith("?")` skip clause does not cover `:shell`;
`raw not in fsm.context` is therefore true for `input:shell` → false positive →
`return 1`.

## Resolution

`scripts/little_loops/cli/loop/run.py`:

- Strip the `:shell` suffix from the captured key before the `in fsm.context`
  check: `if raw.endswith(":shell"): raw = raw[: -len(":shell")]`. General across
  any user var (`input`/`goal`/`description`/…), so a genuinely-missing
  `${context.foo:shell}` is still caught under its real name.
- Expanded the adjacent comment block to name `:shell` alongside `:default=`/`?`
  as an engine-honored idiom the pre-flight must strip (BUG-2553 successor).

`scripts/tests/test_ll_loop_commands.py` (added to the existing BUG-2553
regression class):

- `test_shell_suffix_ref_does_not_trip_validator`: `${context.input:shell}` with
  `input` present falls through the context validator to the `required_inputs`
  layer (fires on empty value) — proving the `:shell` ref no longer trips
  pre-flight, without reaching an LLM.
- `test_missing_shell_ref_reported_under_real_name`: `${context.foo:shell}` with
  `foo` absent still errors and reports `'foo'`, never `foo:shell`.

The 8 affected loop YAMLs were **not** touched — their `:shell` usage is correct
and MR-11-compliant; the defect was entirely in the CLI pre-flight.

## Acceptance Criteria

- [x] `ll-loop run rn-implement --dry-run "FEAT-123"` no longer emits
      "Missing required context variable".
- [x] `${context.input:shell}` with `input` present passes the context validator.
- [x] A genuinely-missing `${context.foo:shell}` still errors, reported as `foo`
      (no `:shell` suffix in the message).
- [x] `python -m pytest scripts/tests/` green (14845 passed, 36 skipped);
      `ruff check` and `ruff format --check` clean on the touched files.

## Impact

Restores the documented positional-input invocation for all 8 loops that adopted
the MR-11-recommended `:shell` interpolation, removing a spurious pre-flight
rejection introduced alongside the MR-11 rollout.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-13T16:15:01 - `aaccf8a6-0e77-4d4e-b94a-c3a570a6e2a2.jsonl`
