---
id: BUG-3239
type: BUG
title: ll-loop validate warns declares no scope on loops that declare one, and the
  warning never reaches --json violations
priority: P3
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T18:23:20Z'
---

# BUG-3239: ll-loop validate warns declares no scope on loops that declare one, and the warning never reaches --json violations

## Summary

`ll-loop validate` prints the BUG-3107 "declares no `scope:`" warning for loops that *do* declare
a scope. The warning is emitted during loading against an FSM whose `scope` is not yet populated,
and it bypasses the returned errors list entirely — so it reaches stderr while
`load_and_validate()` reports zero warnings.

## Current Behavior

`scripts/little_loops/loops/refine-to-ready-issue.yaml` declares a scope at lines 35-37:

```yaml
scope:
  - ".issues/"
  - "${context.run_dir}"
```

Yet:

```
$ ll-loop validate refine-to-ready-issue
[WARNING] scope: Loop declares no 'scope:'. Without it, ll-loop run falls back to a repo-root
lock that false-conflicts with every other concurrently running loop. ...
[13:11:15] refine-to-ready-issue is valid
```

The contradiction is sharper in-process — the warning prints, the parsed scope is correct, and
the returned error list is empty:

```python
from pathlib import Path
from little_loops.fsm import load_and_validate
fsm, errs = load_and_validate(Path('scripts/little_loops/loops/refine-to-ready-issue.yaml'),
                              raise_on_error=False)
# stderr: [WARNING] scope: Loop declares no 'scope:'. ...
print(repr(fsm.scope))   # → ['.issues/', '${context.run_dir}']
print(errs)              # → []
```

`--json` output also reports clean, confirming the warning never enters the structured channel:

```
$ ll-loop validate refine-to-ready-issue --json
{"loop": "refine-to-ready-issue", "valid": true, "violations": []}
```

For contrast, `ll-loop validate autodev` emits no such warning, so this is not universal.

## Steps to Reproduce

1. Confirm the loop declares a scope — `scripts/little_loops/loops/refine-to-ready-issue.yaml`
   lines 35-37 contain:

   ```yaml
   scope:
     - ".issues/"
     - "${context.run_dir}"
   ```

2. Validate it:

   ```bash
   ll-loop validate refine-to-ready-issue
   ```

   Observed: `[WARNING] scope: Loop declares no 'scope:'. ...` followed by
   `refine-to-ready-issue is valid`.

3. Confirm the structured channel disagrees:

   ```bash
   ll-loop validate refine-to-ready-issue --json
   # → {"loop": "refine-to-ready-issue", "valid": true, "violations": []}
   ```

4. Confirm in-process that the parsed scope is correct while the warning still prints:

   ```bash
   python3 -c "
   from pathlib import Path
   from little_loops.fsm import load_and_validate
   fsm, errs = load_and_validate(
       Path('scripts/little_loops/loops/refine-to-ready-issue.yaml'), raise_on_error=False)
   print(repr(fsm.scope))   # → ['.issues/', '\${context.run_dir}']
   print(errs)              # → []
   "
   ```

5. Contrast with a loop that does not reproduce it:

   ```bash
   ll-loop validate autodev   # no scope warning
   ```

## Expected Behavior

`ll-loop validate` emits the missing-scope warning only for loops that actually declare no
`scope:`. For every loop, the warnings written to stderr and the entries in `--json`
`violations` describe the same set of findings.

## Motivation

BUG-3107 added this warning to shift the unscoped-repo-root-lock hazard from run time to
validate time, and BUG-3106 then applied `scope:` to 78 built-in loops to clear the resulting
warnings. A false positive undoes that investment: it re-dirties the signal on loops that were
explicitly fixed, and teaches operators that the warning is safe to ignore — which is precisely
how the original hazard returns unnoticed.

The stderr/`--json` disagreement is the more serious half: an automated consumer and a human
reading the same invocation reach opposite conclusions about whether the loop is clean.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- `scripts/little_loops/fsm/validation/structural_rules.py:259-284` — `_validate_with_bindings(fsm, loop_dir)`, the actual defect site (not `_validate_missing_scope`). For every `loop:` + `with:` state it recursively calls `load_and_validate(loop_path)` (line 281) with the default `raise_on_error=True`, then discards the returned warnings via `child_fsm, _ = ...`. The nested call's own `for warning in all_warnings: logger.warning(str(warning))` loop (lines 1769-1770) still fires unconditionally as a load-time side effect, independent of the discard — this is what leaks the child's warning to stderr while the outer call's returned/`--json` list never sees it.
- `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — has no `scope:` key. This is the actual loop whose missing scope produces the warning text; it is reached because `refine-to-ready-issue.yaml`'s `confidence_check` state (lines 346-349) is `loop: oracles/verify-confidence-scores` with a `with:` block, which is exactly the trigger condition `_validate_with_bindings` recurses on.
- `scripts/little_loops/cli/loop/config_cmds.py:14-90` — `cmd_validate()`, sole consumer wiring `raise_on_error=not as_json` (line 35). Plain-text mode (`raise_on_error=True`) triggers the outer call's own stderr loop (a no-op here since the outer loop's own scope is fine) but the nested call inside `_validate_with_bindings` always runs with `raise_on_error=True` regardless of the outer mode, so the leak reproduces identically under `--json`.
- Other `load_and_validate()` call sites sharing the same "default `raise_on_error=True`, discard returned warnings" shape (candidates for the same latent leak, not confirmed reproductions): `cli/loop/edit_routes.py:51`, `cli/loop/_helpers.py:1423`, `cli/loop/_helpers.py:1447`, `cli/loop/info.py:1502`, `cli/loop/run.py:116`.
- Prior identical-mechanism bug: `.issues/bugs/P4-BUG-3124-oracles-resolve-decision-missing-scope-doubled-warning.md` — root-caused the same `_validate_with_bindings` leak and fixed it by backfilling `scope:` onto one specific child loop (`oracles/resolve-decision.yaml`) rather than changing the collection mechanism; its own notes flag the remaining 12 `loops/oracles/*.yaml` sub-loops (including `verify-confidence-scores.yaml`) as still allowlisted rather than fixed at the root — which is why this reproduces on a different child loop.
- `scripts/tests/test_fsm_validation_structural.py:1597-1644` (`TestMissingScopeValidation`) — exercises `_validate_missing_scope`/`validate_fsm` directly against a hand-built `FSMLoop`; does not exercise the nested-load leak.
- `scripts/tests/test_builtin_loops.py` `TestValidatorWarningBudget` (~14048-14176) — calls `load_and_validate()` once per loop file directly; does not exercise `_validate_with_bindings`'s recursive path, so it cannot see a leaked child warning surfacing through a parent's validate run. Has an existing allowlist mechanism (`ALLOWLIST[(stem, "no-scope")]`, e.g. `("verify-confidence-scores", "no-scope"): {"scope"}` at line ~14113) for a loop's own no-scope warning — a different case from this issue's cross-loop leak.
- `scripts/tests/test_ll_loop_commands.py` `TestCmdValidate` (:55-224) — tests plain-text stderr output and `--json` output in separate test functions; no existing test calls `cmd_validate` twice against the same fixture to diff the two channels.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

**Signatures**
- `_validate_with_bindings(fsm: FSMLoop, loop_dir: Path) -> list[ValidationError]` — `scripts/little_loops/fsm/validation/structural_rules.py:259`. The recursive call site: `child_fsm, _ = load_and_validate(loop_path)` at line 281, using the default `raise_on_error=True` regardless of the outer call's mode, and discarding the returned warnings list.
- `load_and_validate(path: Path, raise_on_error: bool = True, orchestration_request_path: Path | None = None) -> tuple[FSMLoop, list[ValidationError]]` — `scripts/little_loops/fsm/validation/structural_rules.py:1659`. When `raise_on_error=True` and there are no ERROR-severity items, it logs every WARNING-severity item via `logger.warning(str(warning))` (lines 1769-1770) as a load-time side effect, independent of what the caller does with the returned list.
- `ValidationError.__str__` — `scripts/little_loops/fsm/validation/_base.py:15-41` — produces the exact `[WARNING] scope: ...` format seen on stderr, confirming the printed line is a `ValidationError` rendering, not an ad-hoc print.

**Call Path**
`ll-loop validate refine-to-ready-issue` -> `cmd_validate()` (`config_cmds.py:14`, `raise_on_error=not as_json`) -> outer `load_and_validate(refine-to-ready-issue.yaml)` -> `validate_fsm(fsm)` [outer `fsm.scope` truthy, `_validate_missing_scope` returns `[]`] -> `_validate_with_bindings(fsm, loop_dir)` (`structural_rules.py:259`, called at line 1753) -> for the `confidence_check` state (`loop: oracles/verify-confidence-scores` + `with:`) -> nested `load_and_validate(loop_path)` (line 281, always `raise_on_error=True`) -> nested `validate_fsm(child_fsm)` -> `_validate_missing_scope(child_fsm)` returns a WARNING (child has no `scope:`) -> nested call's own `for warning in all_warnings: logger.warning(str(warning))` loop (lines 1769-1770) prints to stderr -> nested return discarded via `child_fsm, _ = ...` -> outer `errors` list never receives it -> `cmd_validate()`'s `--json` `violations` stays empty while stderr already printed the warning.

**Decision Rules**
N/A — no new decision logic. This is a routing/collection defect (a warning is generated correctly but printed through the wrong channel and dropped from the wrong list), not a new gap kind, gate, or threshold.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

1. Every WARNING produced by a `load_and_validate()` call reachable from `cmd_validate()` — including warnings from child loops recursed into by `_validate_with_bindings()` (`structural_rules.py:259-284`) — appears in both the plain-text stderr output and the `--json` `violations` list, or in neither. No warning reaches one channel without the other.
2. `_validate_with_bindings()`'s nested `load_and_validate(loop_path)` call (line 281) no longer independently prints to stderr via its own `raise_on_error=True` default while its returned warnings are discarded; whatever mechanism is chosen (passing `raise_on_error=False` and folding the nested warnings into the outer `errors` list, or another route) must not lose the outer/nested distinction needed for `cmd_validate()`'s existing `--json` shape.
3. `ll-loop validate refine-to-ready-issue` emits no scope warning (its own scope is fine; the leak was from `oracles/verify-confidence-scores.yaml`, an unscoped child it calls with `with:`).
4. `ll-loop validate` on a loop that genuinely declares no `scope:` still warns, on both channels (BUG-3107's behavior preserved).
5. `python -m pytest scripts/tests/` passes, including new regression coverage for a scope-declaring parent loop that calls an unscoped child loop via `loop:` + `with:` (asserting zero scope warnings on the parent's own validation), and a scope-less loop (asserting exactly one, on both stderr and `--json`).

## Impact

Two distinct harms:

- **The warning is noise on correctly-scoped loops**, which trains operators to ignore it —
  defeating BUG-3107's purpose of shifting the unscoped-lock hazard to validate time. BUG-3106
  applied scope to 78 built-in loops specifically to clear these; a false positive re-dirties
  that signal.
- **stderr and the structured channel disagree.** Any consumer trusting `--json` sees
  `violations: []` while a human sees a warning. A CI-style gate and an operator reading the same
  command reach different conclusions.

## Root Cause

Undetermined at the exact call site, but bounded by two confirmed facts:

1. The rule itself is correct. `_validate_missing_scope`
   (`scripts/little_loops/fsm/validation/structural_rules.py:1226-1248`) is a plain
   `if fsm.scope: return []` guard. Given the final FSM it returns `[]` — consistent with the
   empty `errs`.
2. Therefore the printed warning comes from an *earlier* evaluation, against an FSM whose
   `scope` is still falsy — most likely a pre-import-merge or partially-constructed loop object
   during loading — and is written straight to stderr instead of being collected.

The defect is in how/when the rule is invoked and how its output is routed, not in the predicate.
Introduced with BUG-3107, which added the warning.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

Pinpointed exactly. The warning does not originate from an earlier/pre-merge evaluation of `refine-to-ready-issue.yaml` itself, as speculated above — `FSMLoop.from_dict()` (`structural_rules.py:1742`) already populates `fsm.scope` correctly from the top-level YAML before `validate_fsm()` runs, so the outer loop's own `_validate_missing_scope` call (inside `validate_fsm`, `structural_rules.py:1066`) correctly returns `[]`.

The warning instead comes from a **separate, nested `load_and_validate()` call against a different, referenced child loop**: `_validate_with_bindings(fsm, loop_dir)` (`structural_rules.py:259-284`), invoked after `validate_fsm()` returns (`structural_rules.py:1753`). For `refine-to-ready-issue.yaml`'s `confidence_check` state (`loop: oracles/verify-confidence-scores` + `with:`, lines 346-349), it recursively calls `load_and_validate(loop_path)` (line 281) with the default `raise_on_error=True`, against `oracles/verify-confidence-scores.yaml` — which genuinely has no `scope:` key. That nested call's own `_validate_missing_scope` correctly warns on the child; because the nested call runs with `raise_on_error=True`, its own `for warning in all_warnings: logger.warning(str(warning))` loop (`structural_rules.py:1769-1770`) fires and prints to stderr. The caller then discards the nested return value (`child_fsm, _ = load_and_validate(loop_path)`), so this warning never reaches the outer `errors` list `cmd_validate()` returns via `--json` `violations`.

This is why `autodev.yaml` does not reproduce: it also has `loop:` + `with:` call states, but its own `loop: refine-to-ready-issue` call (line 483) has no accompanying `with:` block, so `_validate_with_bindings`'s guard (`if state.loop is None or not state.with_: continue`) skips recursing into `refine-to-ready-issue.yaml` — and therefore never transitively reaches `oracles/verify-confidence-scores.yaml`, which is only referenced from inside `refine-to-ready-issue.yaml`. The difference is not "imports vs. no imports" (both loops use `import:`); it is specifically whether a `loop:` + `with:` call state transitively reaches an unscoped child loop.

This is the identical mechanism BUG-3124 already root-caused and partially patched (by backfilling `scope:` onto `oracles/resolve-decision.yaml` specifically) — its own Deferred notes explicitly left the remaining `loops/oracles/*.yaml` sub-loops, including `verify-confidence-scores.yaml`, unfixed at the root. This issue reproduces on that unfixed remainder.

## Proposed Solution

1. Locate the pre-final invocation of the scope check during load (the site emitting to stderr
   while `errs` stays empty) and either defer it until after import merging / full construction,
   or route its output through the same `ValidationError` collection every other rule uses.
2. Ensure every warning that reaches stderr also appears in the returned list and in `--json`
   `violations`, so the two channels cannot disagree.

## Acceptance Criteria

- [ ] `ll-loop validate refine-to-ready-issue` emits no scope warning.
- [ ] A loop that genuinely declares no `scope:` still warns (BUG-3107's behavior preserved).
- [ ] For any loop, the warnings on stderr and the entries in `--json` `violations` agree.
- [ ] A regression test covers a scope-declaring loop asserting zero scope warnings, and a
      scope-less loop asserting exactly one.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Found incidentally while auditing `refine-to-ready-issue` for an unrelated investigation
(see ENH-3238); not related to that issue's subject matter.

Related completed work: BUG-3107 (added the warning), BUG-3088 (audit of unscoped loops),
BUG-3106 (applied scope to 78 built-in loops).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-18T14:49:23 - `1b75a5d5-cd19-4f54-9db4-f0438e3206cc.jsonl`
- `/ll:capture-issue` - 2026-08-17T18:23:56 - `66dab8b6-e923-43d4-9f0e-eccb97176e0f.jsonl`
