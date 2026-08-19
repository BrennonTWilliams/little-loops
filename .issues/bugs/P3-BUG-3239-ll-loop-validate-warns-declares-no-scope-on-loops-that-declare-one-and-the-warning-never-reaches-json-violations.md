---
id: BUG-3239
type: BUG
title: ll-loop validate warns declares no scope on loops that declare one, and the
  warning never reaches --json violations
priority: P3
status: done
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T18:23:20Z'
completed_at: '2026-08-19T15:50:25Z'
confidence_score: 100
outcome_confidence: 78
score_complexity: 20
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 20
---

# BUG-3239: ll-loop validate warns declares no scope on loops that declare one, and the warning never reaches --json violations

## Summary

`ll-loop validate` prints the BUG-3107 "declares no `scope:`" warning for loops that *do* declare
a scope. The warning actually belongs to a *different* loop — an unscoped child reached by a
`loop:` + `with:` state, which `_validate_with_bindings` recursively loads with the default
`raise_on_error=True`. That nested load prints the child's warning to stderr as a side effect,
then the caller discards its returned list — so the warning reaches stderr while the validated
loop's own `--json` `violations` stays empty.

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

### Second defect in the same emission path: plain-text warnings print twice

A loop that *genuinely* declares no `scope:` emits its warning **twice** in plain-text mode —
once from `load_and_validate`'s own `logger.warning` loop, once from `cmd_validate`'s `⚠` loop
over the same returned list:

```
$ ll-loop validate oracles/verify-confidence-scores
[WARNING] scope: Loop declares no 'scope:'. ...          # structural_rules.py:1769-1770
[10:21:12] oracles/verify-confidence-scores is valid
  States: confidence_check, verify_scores_persisted, ...
  Initial: confidence_check
  Max steps: 50
  ⚠ [WARNING] scope: Loop declares no 'scope:'. ...      # config_cmds.py:93-94
```

`load_and_validate(raise_on_error=True)` both logs every warning (lines 1769-1770) *and* returns
it; `cmd_validate` then prints the returned list again (lines 93-94). This is distinct from the
misattribution bug but lives in the same emission path the fix touches, and it is why the
acceptance criterion "a scope-less loop warns exactly once" is currently failing rather than
merely unasserted.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:870` — a ninth `load_and_validate()` call site not previously enumerated, `child_fsm, _ = load_and_validate(loop_path)` with the same default `raise_on_error=True`, discarded-warnings shape as the bug's own site. Unlike the CLI call sites, this one fires at **loop run time** (every `ll-loop run` that hits a `loop:`+`with:` state dispatching into a scope-less child), not only at `ll-loop validate` time — so the fix's stderr-emission mechanism affects live loop runs, not just the validate command. [Agent 1 finding]
- `scripts/little_loops/cli/doctor.py:561` (`_loop_validity_data`) — calls `load_and_validate(..., raise_on_error=False)`, the one call site already on the non-printing branch. Iterates loop files directly rather than recursing through `_validate_with_bindings`, so it isn't itself subject to this bug, but it consumes the returned violations list per loop — spot-check that the fix doesn't change per-loop violation counts it aggregates. [Agent 2 finding]
- `scripts/little_loops/loops/workflow-generator.yaml` (~lines 350-364, ~448-463) — a live MR-1 baseline/candidate regression gate that runs `ll-loop validate <artifact> --json` and parses `violations` (errors + warning count) via `payload.get("violations", [])`, then `raise SystemExit(0 if candidate == baseline else 1)`. If the fix changes which warnings land in `violations` for artifacts with `loop:`+`with:` sub-loop references, this gate's pass/fail can shift for reasons unrelated to the validated artifact's own content. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:6249-6277` — documents a stale `load_and_validate` signature (`def load_and_validate(path: Path) -> FSMLoop`), missing `raise_on_error`, `orchestration_request_path`, the actual `tuple[FSMLoop, list[ValidationError]]` return type, and any mention of the `logger.warning()` stderr side effect. Should be corrected alongside this fix since the fix necessarily touches this function's warning-emission contract. [Agent 2 finding]
- `docs/reference/CLI.md:857` — documents the `--json` schema key as `"warnings"`; the actual emitted key is `"violations"` (`config_cmds.py:48,62,78`). Pre-existing drift, but sits in the same `--json` output-contract section this fix changes. [Agent 2 finding]
- `docs/reference/CLI.md:846` — the "No-scope (WARNING)" rule bullet doesn't mention that the warning can be misattributed from a recursively-validated child loop rather than the loop actually being validated; worth a caveat once the fix lands. [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:832`, `docs/guides/LOOPS_REFERENCE.md:2631`, `docs/generalized-fsm-loop.md:1547`, `docs/guides/EVALUATION_GUIDE.md:218,428` — repeat the same "declares no scope" warning description without the misattribution caveat; light pass if the fix changes message text. [Agent 2 finding]
- `skills/create-loop/reference.md:590` — canonical copy of the same warning-behavior sentence, build-mirrored (not hand-edited) into `.gemini/skills/create-loop/reference.md:590`, `.qwen/skills/create-loop/reference.md:590`, `.kimi-code/skills/create-loop/reference.md:590` via the adapter modules (`scripts/little_loops/adapters/{gemini,kimi,qwen}.py`). Edit only the canonical file and run the adapter sync — do not hand-edit the mirrors. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation_structural.py` `TestMissingScopeValidation` (1597-1644) — confirmed to be a gap, not coverage: builds `FSMLoop` objects entirely in-memory via `_make_fsm()`, calling `_validate_missing_scope`/`validate_fsm` directly with no `loop_dir` or on-disk child file, so it cannot reach `_validate_with_bindings`'s nested `load_and_validate()` call at all. [Agent 3 finding]
- `scripts/tests/test_fsm_validation_structural.py` `TestWithBindingValidation` (535-646) — has the closest existing `loop:`+`with:` fixture shape, but every test explicitly filters to structural-only errors (`# Only structural errors — cross-loop binding errors need load_and_validate`, line 624) and never resolves `"child"` to a real on-disk file. Template to extend, not a covering test. [Agent 3 finding]
- `scripts/tests/test_fsm_loop_paths.py:17-39` — the reusable idiom for writing a second on-disk child loop file under the same `tmp_path` `resolve_loop_path`/`_validate_with_bindings` will search; the shape a new parent+child fixture pair should follow. [Agent 3 finding]
- `scripts/tests/test_ll_loop_commands.py` `TestCmdValidate` — `test_validate_with_unreachable_state_prints_warning` and `test_validate_json_output_invalid_loop` are two separate existing tests using the same `cmd_validate(name, args, loops_dir, logger)` call shape (differing only in `args.json`) that should be combined into one new test calling both modes against the same two-file (parent scoped, child unscoped, `loop:`+`with:`) fixture to assert stderr and `--json violations` agree. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` `TestValidatorWarningBudget` / `_collect_findings` (~14563-14575) — dedups warnings into a `set[tuple[str, str, str]]`, so it would not catch a regression in duplicate-warning counting, only in presence/absence per `(loop, category, path)` key; not a suitable home for a duplicate-count assertion. [Agent 3 finding]

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

_Superseded in part by Decision 1 — the mechanism is now settled as suppression, not propagation._

1. A loop's validation output reports only that loop's own findings. Warnings from child loops recursed into by `_validate_with_bindings()` (`structural_rules.py:259-284`) reach **neither** the plain-text stderr output nor the `--json` `violations` list of the parent; they are reported when the child is itself validated.
2. `_validate_with_bindings()`'s nested `load_and_validate(loop_path)` call (line 281) passes `raise_on_error=False`, so it no longer prints to stderr as a load-time side effect while its returned warnings are discarded. Per Decision 1, the nested warnings are **not** folded into the outer `errors` list — so `cmd_validate()`'s existing `--json` shape is unchanged and no outer/nested distinction needs to be carried.
3. `ll-loop validate refine-to-ready-issue` emits no scope warning (its own scope is fine; the leak was from `oracles/verify-confidence-scores.yaml`, an unscoped child it calls with `with:`).
4. `ll-loop validate` on a loop that genuinely declares no `scope:` still warns (BUG-3107's behavior preserved) — exactly once in plain text, per Decision 2.
5. `python -m pytest scripts/tests/` passes, including new regression coverage for a scope-declaring parent loop that calls an unscoped child loop via `loop:` + `with:` (asserting zero scope warnings on the parent's own validation), and a scope-less loop (asserting exactly one, on both stderr and `--json`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

_Resolved against Decision 1 — this list reflects Option A (suppress), so the conditional items are now settled either in or out._

- **In scope.** `scripts/little_loops/fsm/executor.py:870` — `child_fsm, _ = load_and_validate(loop_path)`, same default-`raise_on_error=True`/discarded-warnings shape, but fires at loop *run* time on every `ll-loop run` that dispatches into a scope-less child. It does **not** inherit the fix automatically: it is its own call to `load_and_validate`, not a path through `_validate_with_bindings`. Apply `raise_on_error=False` here too.
- **In scope.** `scripts/little_loops/cli/loop/info.py:1502` — `child_fsm, _ = load_and_validate(child_path)` inside `cmd_show`'s `--json` + `--resolved` branch, a third site with the identical shape. Worst of the three: it leaks a child's stderr warning out of `ll-loop show --json --resolved`, a command whose whole contract is clean machine-readable output. Apply `raise_on_error=False`. Note the incidental behavior change — its `except (FileNotFoundError, ValueError): pass` currently drops `_subloop` for any child with ERROR-severity findings; under `raise_on_error=False` that child no longer raises and `_subloop` gets populated. That is an improvement (the states are still renderable), but assert it deliberately rather than discovering it.
- **In scope.** Remove the duplicate `⚠` print loop in `scripts/little_loops/cli/loop/config_cmds.py:93-94` per Decision 2.
- **Out of scope (Decision 1).** Backfilling `scope:` onto the remaining 11 scope-less `loops/oracles/*.yaml` files (`code-run-gate`, `enumerate-and-prove`, `generator-evaluator`, `generator-evaluator-cli`, `generator-evaluator-flux`, `integrate-node`, `oracle-capture-issue`, `plan-node-refine`, `plan-research-iteration`, `research-coverage`, `verify-confidence-scores`). That was only required under Option B, where child warnings would newly surface in every parent's `violations`. Under suppression no parent gains a violation, so the backfill is independent cleanup — file separately if wanted (mirrors the BUG-3124/`resolve-decision.yaml` precedent).
- **Verify only, no change expected.** `scripts/little_loops/loops/workflow-generator.yaml` (~350-364, ~448-463), its `ll-loop validate --json` baseline/candidate regression gate. Under Option A no `violations` entry is added or removed (the leaked warnings never reached `violations`), so the gate's pass/fail cannot shift. Confirm with a baseline/candidate run rather than assuming.
- **Verify only, no change expected.** `scripts/little_loops/cli/doctor.py:561` (`_loop_validity_data`) already passes `raise_on_error=False` and iterates loop files directly. Spot-check that per-loop violation counts it aggregates are unchanged.
- Update `docs/reference/API.md:6249-6277` — correct the stale `load_and_validate` signature (add `raise_on_error`, `orchestration_request_path`, the real `tuple[FSMLoop, list[ValidationError]]` return) and document the `logger.warning` stderr side effect that fires only when `raise_on_error=True`.
- Update `docs/reference/CLI.md:857` — the `--json` flag row's documented schema is wrong in three ways, not one. It claims success emits `{"valid": true, "loop": ..., "warnings": [...]}` and failure emits `{"valid": false, "loop": ..., "error": "<message>", "warnings": [...]}`. Actual (`config_cmds.py:44-50,58-64,74-83`): **both** paths emit `violations`, there is **no** `warnings` key, and there is **no** `error` key — a failure's message is carried as a single `violations` entry with `severity: "error"` and `path: "<root>"`. Rewrite the row against the code.
- `docs/reference/CLI.md:846` — the misattribution caveat is **no longer needed**: under Option A the warning can no longer be misattributed to a parent loop. Leave the rule bullet as-is unless the fix reveals other drift.
- **Out of scope (Decision 1).** `skills/create-loop/reference.md:590` and the `.gemini`/`.qwen`/`.kimi-code` mirrors, plus the adapter sync — the warning message text does not change under Option A.
- Add regression tests per the Tests subsection of the Integration Map: extend `test_fsm_loop_paths.py`'s two-file on-disk fixture idiom into a new `TestCmdValidate` test in `test_ll_loop_commands.py` combining `test_validate_with_unreachable_state_prints_warning`'s and `test_validate_json_output_invalid_loop`'s call shapes against one parent(scoped)+child(unscoped) `loop:`+`with:` fixture, asserting both modes agree and that the child's own validation warns exactly once in plain text.

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

The warning is misattributed: it is emitted by a **nested `load_and_validate()` call against a
different, referenced child loop**, not by any evaluation of the loop named on the command line.

`_validate_with_bindings(fsm, loop_dir)` (`structural_rules.py:259-284`) recurses into every
`loop:` + `with:` state's child loop via `child_fsm, _ = load_and_validate(loop_path)` (line 281),
using the default `raise_on_error=True`. That nested call's own
`for warning in all_warnings: logger.warning(str(warning))` loop (lines 1769-1770) fires as an
unconditional load-time side effect and prints the child's warning to stderr; the caller then
discards the returned list (`child_fsm, _ = ...`), so the warning never reaches the outer
`errors` list that `cmd_validate()` renders as `--json` `violations`.

Two things follow, both confirmed:

1. The rule itself is correct. `_validate_missing_scope` (`structural_rules.py:1226-1248`) is a
   plain `if fsm.scope: return []` guard, and `FSMLoop.from_dict()` (line 1742) populates
   `fsm.scope` from the merged YAML *before* `validate_fsm()` runs — so the outer loop's own
   evaluation correctly returns `[]`. There is no pre-import-merge or partially-constructed
   evaluation of the named loop; an earlier revision of this issue speculated one, and it does
   not exist.
2. The defect is in how a *child's* validation output is routed, not in the predicate and not in
   the parent's own validation. Introduced with BUG-3107, which added the warning.

Note that line 282's `except Exception: continue` already swallows child **ERROR**-severity
findings entirely (a child with an error raises `ValueError` under `raise_on_error=True` and is
silently skipped). The recursion therefore suppresses the severe findings while leaking the mild
ones — an inverted severity treatment that shapes the fix (see Decision 1).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

Full trace supporting the Root Cause above. `FSMLoop.from_dict()` (`structural_rules.py:1742`) already populates `fsm.scope` correctly from the top-level YAML before `validate_fsm()` runs, so the outer loop's own `_validate_missing_scope` call (inside `validate_fsm`, `structural_rules.py:1066`) correctly returns `[]`.

The warning instead comes from `_validate_with_bindings(fsm, loop_dir)` (`structural_rules.py:259-284`), invoked after `validate_fsm()` returns (`structural_rules.py:1753`). For `refine-to-ready-issue.yaml`'s `confidence_check` state (`loop: oracles/verify-confidence-scores` + `with:`, lines 346-349), it recursively calls `load_and_validate(loop_path)` (line 281) with the default `raise_on_error=True`, against `oracles/verify-confidence-scores.yaml` — which genuinely has no `scope:` key. That nested call's own `_validate_missing_scope` correctly warns on the child; because the nested call runs with `raise_on_error=True`, its own `for warning in all_warnings: logger.warning(str(warning))` loop (`structural_rules.py:1769-1770`) fires and prints to stderr. The caller then discards the nested return value (`child_fsm, _ = load_and_validate(loop_path)`), so this warning never reaches the outer `errors` list `cmd_validate()` returns via `--json` `violations`.

This is why `autodev.yaml` does not reproduce: it also has `loop:` + `with:` call states, but its own `loop: refine-to-ready-issue` call (line 483) has no accompanying `with:` block, so `_validate_with_bindings`'s guard (`if state.loop is None or not state.with_: continue`) skips recursing into `refine-to-ready-issue.yaml` — and therefore never transitively reaches `oracles/verify-confidence-scores.yaml`, which is only referenced from inside `refine-to-ready-issue.yaml`. The difference is not "imports vs. no imports" (both loops use `import:`); it is specifically whether a `loop:` + `with:` call state transitively reaches an unscoped child loop.

This is the identical mechanism BUG-3124 already root-caused and partially patched (by backfilling `scope:` onto `oracles/resolve-decision.yaml` specifically) — its own Deferred notes explicitly left the remaining `loops/oracles/*.yaml` sub-loops, including `verify-confidence-scores.yaml`, unfixed at the root. This issue reproduces on that unfixed remainder.

## Decisions

### Decision 1 — suppress child warnings at the recursion site; do not propagate them

`_validate_with_bindings`'s nested call becomes
`load_and_validate(loop_path, raise_on_error=False)` and continues to discard the returned
violations. A parent loop's validation reports **only the parent's own findings**. Child loops'
scope hygiene is reported when that child is itself validated.

Two mechanisms were available, and they are not cosmetically different:

- **(A) Suppress** — chosen. `raise_on_error=False` at `structural_rules.py:281` stops the
  nested call's `logger.warning` side effect at the source. The recursion keeps doing the one
  job it exists for: cross-validating `with:` bindings against the child's `parameters`.
- **(B) Propagate** — rejected. Fold the child's warnings into the parent's returned `errors`
  list so they reach `--json violations`.

**Rationale for (A) over (B):**

1. **Severity consistency.** Line 282's `except Exception: continue` already swallows child
   ERROR-severity findings outright. (B) would surface child *warnings* while child *errors*
   stay silent — strictly more incoherent than today. Making (B) coherent means also deciding
   how child errors propagate, which is a different and much larger issue.
2. **`ValidationError` has no provenance field.** A propagated child violation arrives as
   `path: "scope"` with nothing naming the loop it came from. (B) would replace one
   misattribution with another: instead of a warning that looks like the parent's, `--json`
   would carry a violation entry that *is* recorded as the parent's. Fixing that means adding a
   source-loop field to `ValidationError` and threading it through every rule and every
   consumer.
3. **Blast radius.** Under (B), every parent loop with a `loop:` + `with:` state reaching any of
   the 11 unscoped `loops/oracles/*.yaml` gains new `violations` entries. That shifts
   `TestValidatorWarningBudget`, and can flip `workflow-generator.yaml`'s baseline/candidate
   regression gate for reasons unrelated to the artifact under test. (B) is therefore only
   viable bundled with a scope backfill across those 11 oracles — scope this issue does not
   need to take on.
4. **Nothing is lost.** Per-loop scope coverage is already enforced independently:
   `ll-doctor`'s `_loop_validity_data` (`cli/doctor.py:561`) and
   `TestValidatorWarningBudget` both iterate every loop file directly. A child's missing scope
   is still caught — by the run that validates that child.

**Consequences:** the warning message text does **not** change, so
`skills/create-loop/reference.md:590` and its `.gemini`/`.qwen`/`.kimi-code` adapter mirrors need
no edit and no adapter sync. The 11-oracle scope backfill is **not** part of this issue.
`workflow-generator.yaml`'s gate is unaffected (parent `violations` counts only shrink where a
leak existed, and the leak never reached `violations` to begin with).

### Decision 2 — the duplicate plain-text warning is fixed by dropping `cmd_validate`'s `⚠` loop

Of the two emission points for a loop's own warnings, `load_and_validate`'s
`logger.warning` (`structural_rules.py:1769-1770`) is kept and `cmd_validate`'s
`for w in warnings: print(f"  ⚠ {w}")` (`config_cmds.py:93-94`) is removed.

**Rationale:** `logger.warning` is the emission every one of the eight other
`load_and_validate` callers already relies on for warning visibility; removing it would silence
warnings across `ll-loop run`, `ll-loop edit-routes`, `ll-loop show`, and friends, which is a
behavior change well beyond this bug. The `⚠` loop is local to `cmd_validate` and duplicates it. Dropping the `⚠`
loop also puts both warning channels on stderr consistently (`logger.warning`), rather than
splitting them across stderr and stdout.

## Proposed Solution

1. At `structural_rules.py:281`, change the nested call to
   `load_and_validate(loop_path, raise_on_error=False)`. This stops the child's warnings from
   reaching stderr through a load-time side effect while the returned list is discarded. The
   surrounding `try`/`except Exception: continue` stays: with `raise_on_error=False` a child
   with ERROR-severity findings no longer raises, and `_validate_with_bindings` proceeds to
   cross-validate the `with:` bindings against whatever `child_fsm.parameters` it parsed —
   which is the correct behavior and a small incidental improvement.
2. Apply the same change at `fsm/executor.py:870` and `cli/loop/info.py:1502`, the two other
   sites with the identical "default `raise_on_error=True`, discard returned warnings" shape
   (see Wiring Phase).
3. Remove `cmd_validate`'s duplicate `⚠` print loop (`config_cmds.py:93-94`) per Decision 2.
4. Correct the documentation drift listed in the Integration Map.

## Acceptance Criteria

- [x] `ll-loop validate refine-to-ready-issue` emits no scope warning on stderr, in both
      plain-text and `--json` modes.
- [x] A loop that genuinely declares no `scope:` still warns (BUG-3107's behavior preserved),
      and in plain-text mode emits that warning **exactly once** (currently twice).
- [x] For the same loop validated twice — once plain-text, once `--json` — the set of
      WARNING-severity findings on stderr equals the set of WARNING-severity entries in
      `--json` `violations`. (Asserted across two invocations: in `--json` mode
      `raise_on_error=False`, so no warning is logged during that call by construction.)
- [x] `ll-loop run` on a loop that dispatches into an unscoped child no longer prints that
      child's scope warning at run time (`executor.py:870`).
- [x] A regression test covers a two-file on-disk fixture — parent declaring `scope:`, child
      declaring none, wired by `loop:` + `with:` — asserting zero scope warnings on the
      parent's validation in both modes, and exactly one on the child's own validation in
      both modes.
- [x] `python -m pytest scripts/tests/` exits 0, including `TestValidatorWarningBudget`
      unchanged (no allowlist edits should be required under Decision 1).

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
- `/ll:manage-issue` - 2026-08-19T15:50:10 - `26efdaf5-1644-47d9-8da6-2ce07fa4e6bd.jsonl`
- `/ll:confidence-check` - 2026-08-19T15:19:58 - `a39a8786-2c1d-40b0-b8ec-3fc565838927.jsonl`
- `/ll:wire-issue` - 2026-08-19T15:17:34 - `6f435684-155f-4724-92e1-2b56419366c1.jsonl`
- `/ll:refine-issue` - 2026-08-18T14:49:23 - `1b75a5d5-cd19-4f54-9db4-f0438e3206cc.jsonl`
- `/ll:capture-issue` - 2026-08-17T18:23:56 - `66dab8b6-e923-43d4-9f0e-eccb97176e0f.jsonl`
