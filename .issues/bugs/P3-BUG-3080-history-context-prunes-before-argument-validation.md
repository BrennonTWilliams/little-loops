---
id: BUG-3080
title: ll-history-context prunes before argument validation, so malformed invocations
  exit 0 silently under automation
type: BUG
priority: P3
status: done
testable: true
discovered_by: run-forensics
discovered_date: 2026-08-06
captured_at: '2026-08-06T00:35:00Z'
completed_at: '2026-08-06T17:43:49Z'
relates_to:
- ENH-2714
- ENH-3081
- BUG-3058
labels:
- automation
- cli
- history
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- `hooks/session_start.py` audit confirmed: `handle()` in `scripts/little_loops/hooks/session_start.py:86` has a structurally identical `LL_AUTOMATION` pruning gate at `:102-124`, but no argparse-style validation guard exists anywhere in the function — it receives a pre-built `LLHookEvent` (`scripts/little_loops/hooks/types.py:20-81`) whose `from_dict()` classmethod uses `.get()` with fallbacks rather than raising on missing/malformed keys. No code path in `handle()`, before or after the gate, raises or returns a non-zero `exit_code` for a malformed event. This confirms the issue's own speculation ("very likely fine, but confirm rather than assume") — no reorder is needed at that site.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- Docstring inconsistency (pre-existing, independent of this fix): `main_history_context()`'s docstring at `history_context.py:181-183` states "1 on argument error", but `parser.error()` actually raises `SystemExit(2)` — the docstring is already wrong today regardless of the reorder.
- `cli_event_context(DEFAULT_DB_PATH, "ll-history-context", sys.argv[1:])` (`history_context.py:184`) wraps the entire function body and logs the invocation to the session history store on every branch — a malformed invocation is recorded in history today even when pruned to exit 0. The reorder doesn't change what gets logged, only the exit code/stderr the caller observes.
- Convention check: the `LL_AUTOMATION` pruning gate is confined to exactly two sites codebase-wide — `history_context.py:191-207` and `hooks/session_start.py:102-124` — no other `cli/*.py` entry point references `LL_AUTOMATION`/`automation_pruning`. Other `main_*` CLI functions (`cli/auto.py:74-86`, `cli/artifact.py:167-174`) place `parser.error(...)` validation immediately after `parser.parse_args()` with no gate interposed; the fix's post-fix ordering matches that established shape rather than introducing a new one.
- Test pattern: the dominant assertion style for malformed-arg tests in this codebase is `with pytest.raises(SystemExit) as exc_info: ...; assert exc_info.value.code == 2` (e.g. `scripts/tests/test_cli_args.py:177-179` and seven further sites). The existing `test_history_context_cli.py:18-23` (`test_missing_issue_id_exits`) currently uses the lighter `pytest.raises(SystemExit)` form without checking `.code` — the new tests this issue's Tests subsection calls for should assert `exc_info.value.code == 2` to match the dominant pattern.
- No shared helper backs the `LL_AUTOMATION` + `automation_pruning.enabled` check at either site — it's hand-duplicated with different exception-suppression idioms (`try/except Exception: pass` in `history_context.py` vs `contextlib.suppress(Exception)` in `session_start.py`). Noted as existing state only; not proposed as in-scope for this fix.

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

## Resolution

Moved the ENH-2714 automation-pruning block in `main_history_context()`
(`scripts/little_loops/cli/history_context.py`) to sit after the
mutual-exclusion/required-argument validation guards, as a pure statement
reorder — no signature or config change. Well-formed calls under
`LL_AUTOMATION=1` still prune to a silent exit 0; malformed calls (missing
`ISSUE_ID`, or `--project` + `ISSUE_ID` together) now correctly hit
`parser.error()` and exit 2 regardless of automation. Also fixed the
pre-existing docstring inaccuracy ("1 on argument error" → "2 on argument
error") and updated the gate's comment to state the ordering invariant.

Added `test_missing_issue_id_exits_under_automation`,
`test_project_and_issue_id_mutually_exclusive_under_automation`, and
`test_well_formed_call_still_prunes_under_automation` to
`test_history_context_cli.py`, and tightened existing malformed-arg
assertions to check `exc_info.value.code == 2` per the codebase's dominant
pattern. Confirmed the `hooks/session_start.py` gate needs no equivalent
change (already noted in the issue's research findings — it has no
argparse-style validation to protect).

## Status

- [x] Complete


## Session Log
- `/ll:manage-issue` - 2026-08-06T17:43:02 - `10a4dda7-3bc6-4a1f-94ff-501ee053ac5f.jsonl`
- `/ll:ready-issue` - 2026-08-06T17:33:42 - `3863ed7e-9cf2-467b-9093-f54778f2842a.jsonl`
- `/ll:confidence-check` - 2026-08-06T06:29:32 - `ef76915a-3ba4-4822-85d4-e84d2c3b1923.jsonl`
- `/ll:verify-issues` - 2026-08-06T06:27:51 - `0e1edeb1-2d67-4cea-b6d6-80a4401a3eb9.jsonl`
- `/ll:refine-issue` - 2026-08-06T06:20:58 - `23c3f239-5e25-4dcb-b1ff-eacc214882e7.jsonl`
