---
id: BUG-3080
title: ll-history-context prunes before argument validation, so malformed invocations
  exit 0 silently under automation
type: BUG
priority: P3
status: open
testable: true
discovered_by: run-forensics
discovered_date: 2026-08-06
captured_at: '2026-08-06T00:35:00Z'
relates_to:
- ENH-2714
- ENH-3081
- BUG-3058
labels:
- automation
- cli
- history
---

# BUG-3080: `ll-history-context` prunes before argument validation, so malformed invocations exit 0 silently under automation

## Summary

The ENH-2714 automation-pruning gate in `cli/history_context.py` is placed
*before* the CLI's argument-validation guards. Under `LL_AUTOMATION=1` a
malformed invocation — no `ISSUE_ID`, or `--project` *and* `ISSUE_ID` together —
returns **exit 0 with no output** instead of `parser.error()`'s exit 2.

That is precisely the environment where nobody is reading stderr, so a typo or a
bad interpolation in a loop YAML or skill body looks identical to a successful
no-op. The failure it should surface is the one it hides.

## Steps to Reproduce

```bash
# Correctly rejected interactively:
ll-history-context                        # exit 2, "one of ISSUE_ID or --project is required"
ll-history-context BUG-1 --project        # exit 2, "mutually exclusive"

# Silently accepted under automation:
LL_AUTOMATION=1 ll-history-context        # exit 0, no output
LL_AUTOMATION=1 ll-history-context BUG-1 --project   # exit 0, no output
```

Equivalently, in the test suite:

```bash
LL_AUTOMATION=1 python -m pytest scripts/tests/test_history_context_cli.py \
  -k "test_missing_issue_id_exits or test_project_and_issue_id_mutually_exclusive"
```

Both fail — they expect `SystemExit(2)` and get a clean return. (They pass on
`main` only because `scripts/tests/conftest.py` now scrubs `LL_AUTOMATION`; the
production defect is unaffected by that test-side fix.)

## Current Behavior

`scripts/little_loops/cli/history_context.py:191-207`, immediately after
`parser.parse_args()`:

```python
if _os.environ.get("LL_AUTOMATION"):
    _pruning_gate_enabled = True
    try:
        _pruning_gate_enabled = _BRConfig(Path.cwd()).history.automation_pruning.enabled
    except Exception:
        pass
    if _pruning_gate_enabled:
        return 0
```

The mutual-exclusion and required-argument guards are at `:209-213`, *after* it.
The secondary gate `history.automation_pruning.enabled` defaults to `True`
(`config/features.py:1034-1041`), so no config is needed to trigger this.

Note the gate's own comment at `:195` says it "mirrors the `--for-skill` guard
immediately below" — but that guard is at `:239-245`, which is **after**
validation. The cited precedent argues for the opposite placement.

## Expected Behavior

Argument validation runs first. A malformed invocation exits 2 with its
diagnostic on stderr regardless of `LL_AUTOMATION`; only a *well-formed*
invocation is pruned to a silent exit 0.

Pruning is a decision about how much output a valid call produces. It is not a
license to accept calls that are invalid.

## Root Cause

ENH-2714 introduced the gate as an early return placed for cheapness — bail
before doing any work — and "any work" was read to include argparse's own
validation. The distinction between *suppressing output* and *suppressing
errors* was not drawn.

## Proposed Solution

Move the pruning block from `:191-207` to sit immediately **after** the
validation guards at `:209-213`, and before the `--project` branch at `:215`.
This is a pure statement reorder within `main_history_context`; no signature,
config, or behavioral change for well-formed calls.

Update the `:192-196` comment to state the ordering invariant and why it matters
(errors are not prunable), so the block is not hoisted back later.

Consider the same audit for `hooks/session_start.py:110-123` — that gate has no
argument surface to validate, so it is very likely fine, but confirm rather than
assume.

## Program Design

No new types, functions, or signatures — the fix is a statement reorder inside an
existing function body.

### Signatures

- `main_history_context() -> int` — `scripts/little_loops/cli/history_context.py:180`.
  Unchanged signature; the pruning block moves within it.

### Call Path

`ll-history-context` (console script, `scripts/pyproject.toml:98`) →
`little_loops.cli:main_history_context` → `_build_parser()` →
`parser.parse_args()` → **[pruning gate, `:191-207` — moves]** →
validation guards (`:209-213`) → `--project` branch (`:215`) → `--for-skill`
guard (`:239-245`) → digest rendering.

Post-fix ordering: `parse_args()` → validation guards → pruning gate →
`--project` branch. The gate lands between `:213` and `:215`, which places it
ahead of all rendering work (preserving the cheap-exit intent) and behind all
argument validation (fixing the defect).

The `--for-skill` guard at `:239-245` already sits after validation and is
unaffected; post-fix the two guards are consistently ordered, which is what the
gate's `:195` comment claims today but does not do.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/history_context.py` — move the block at `:191-207`
  below `:213`; rewrite the comment at `:192-196`.

### Tests

- `scripts/tests/test_history_context_cli.py` — add coverage asserting
  `SystemExit(2)` for both malformed forms **with `LL_AUTOMATION=1` explicitly
  set** via `monkeypatch.setenv`, alongside a case asserting a well-formed call
  still prunes to exit 0. The autouse scrub in `scripts/tests/conftest.py:725`
  means the var must be set deliberately in the test body.

### Documentation

- `docs/reference/CLI.md` — if it documents `ll-history-context` exit codes,
  note that validation errors are not suppressed under automation.

## Impact

- **Priority**: P3 — no incorrect output is produced; the harm is a masked
  diagnostic in exactly the context where diagnostics are scarcest. No
  user-visible defect on well-formed calls.
- **Effort**: Small — a statement reorder plus three tests.
- **Risk**: Low — well-formed calls take an identical path; only the malformed
  ones change, and they change from silently-wrong to correctly-loud.
- **Breaking Change**: No. Any caller relying on exit 0 for a malformed
  invocation was already broken.

## Related Issues

- ENH-2714 — introduced the pruning gate and its placement.
- ENH-3081 — the other residual from the same investigation (inherited
  `LL_AUTOMATION` cannot be cleared by an explicit opt-out).
- BUG-3058 — prior work on the same env signal.

## Status

- [ ] Not started
