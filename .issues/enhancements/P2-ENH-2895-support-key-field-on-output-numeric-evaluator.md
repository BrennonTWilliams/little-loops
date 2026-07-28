---
id: ENH-2895
type: ENH
priority: P2
status: done
captured_at: '2026-07-28T22:13:33Z'
completed_at: '2026-07-28T23:09:01Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- BUG-2893
- BUG-2894
- ENH-2896
confidence_score: 100
outcome_confidence: 84
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2895: Support an `evaluate.key` field on the output_numeric evaluator

## Summary

Add a `key: str | None` field to `EvaluateConfig` and honour it in
`evaluate_output_numeric`: when set, extract the numeric value from a
`<key>=<number>` field in the action's stdout instead of calling
`float(output.strip())` on the whole output.

Two built-in loops (`docs-sync.yaml`, `oracles/code-run-gate.yaml`) already declare
`key:` on `output_numeric` evaluators, written by independent authors who each assumed
the field did exactly this. It does not exist; it is silently dropped at load. Both
loops are broken as a result (BUG-2893, BUG-2894).

## Motivation

The pattern the field addresses is ubiquitous in shell states: a state runs a command,
computes a metric, and echoes a self-describing `metric=value` line so the run log stays
readable. Today the only ways to feed that value to `output_numeric` are:

- echo a bare, unlabelled number (loses the run-log legibility), or
- restructure the shell to emit JSON and switch to `output_json` + `path:` (more shell
  churn inside `$${}`-escaped blocks — precisely where MR-7/MR-9 escaping bugs breed).

That two authors independently reached for `key:` is direct evidence it is the
discoverable API. Implementing it fixes both existing loops with no shell surgery and
removes the sharp edge for future authors.

## Current Pain Point / Current Behavior

`evaluate_output_numeric` (`scripts/little_loops/fsm/evaluators.py`):

```python
    try:
        value = float(output.strip())
    except ValueError:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Cannot parse as number: {output[:100]}"},
        )
```

Any labelled output produces `verdict="error"`. `EvaluateConfig`
(`scripts/little_loops/fsm/schema.py`) has no `key` field, and `from_dict` discards it
silently, so the loop author gets no signal that their YAML is inert — not at load,
not at `ll-loop validate`, and not at runtime beyond a generic parse error.

## Expected Behavior / API

```yaml
    evaluate:
      type: output_numeric
      key: pass_rate
      operator: "ge"
      target: 0.95
```

Against stdout:

```
running tests...
exit_code=0
pass_rate=0.99
```

→ extracts `0.99`, compares `0.99 >= 0.95`, returns `verdict="yes"`.

Semantics to settle during implementation:

- **Match rule**: regex on `^\s*<key>\s*=\s*([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s*$`,
  or a looser in-line match permitting `exit_code=0 pass_rate=0.99` on one line.
  Recommend supporting the in-line form — `code-run-gate` emits exactly that shape.
- **Multiple matches**: take the **last** match. Shell states append progressively;
  the last write is the current value. Document this explicitly.
- **No match**: `verdict="error"` with a `details["error"]` naming the missing key
  (`"key 'pass_rate' not found in output"`) — distinguishable from a parse failure.
- **Key not set**: unchanged `float(output.strip())` behaviour. Fully backward compatible.
- **Escaping**: `re.escape` the key.

## Proposed Solution

1. `EvaluateConfig`: add `key: str | None = None`, wire into `to_dict` (emit when not
   None) and `from_dict` (`data.get("key")`), and document it in the class docstring's
   Attributes block.
2. `evaluate_output_numeric`: add a `key: str | None = None` parameter; when set, run the
   extraction described above before the `float()` call.
3. Dispatch site (`evaluators.py`, the `elif eval_type == "output_numeric":` branch):
   pass `key=config.key`.
4. Consider whether `output_json`-style `source:` interaction needs any change — `source`
   is resolved upstream in `executor.py` and should compose without special handling.

### Scope decision to make

Should `key:` also apply to `convergence` and `score_stall`, which face the same
labelled-output problem? Recommend **no** for this issue — keep the change minimal and
revisit if a concrete need appears. Record the decision either way.

## Integration Map

- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig` (field, `to_dict`, `from_dict`, docstring)
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_output_numeric` + dispatch branch
- `scripts/little_loops/loops/docs-sync.yaml` — becomes correct as written (BUG-2893)
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — still needs its echo fixed (BUG-2894)
- `docs/reference/API.md` — evaluator reference
- `.claude/CLAUDE.md` / loop-authoring docs — document the new field
- `scripts/tests/` — unit tests for extraction semantics
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `evaluateConfig` object (starts ~line 654) enumerates
  every known field explicitly and sets `"additionalProperties": false` (line 813); the new `key` field
  must be added to `properties` here too, or any schema-validating consumer of this file rejects `key:`
  even though `EvaluateConfig.from_dict` now accepts it. [`/ll:wire-issue` finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- No other production call site of `evaluate_output_numeric` exists besides the dispatch branch already
  listed — confirmed by trace; `scripts/little_loops/fsm/__init__.py` only re-exports the symbol (import +
  `__all__` entry), no call to update.
- Confirmed no other built-in loop YAML (besides `docs-sync.yaml` and `oracles/code-run-gate.yaml`) declares
  a `key:` field under an `output_numeric` evaluate block — grepped all `scripts/little_loops/loops/**/*.yaml`.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — the docs-sync structural test class (~line 9656) and the
  code-run-gate oracle structural test class (~line 9971) assert `evaluator.get("type") == "output_numeric"`
  and tier-1 membership but never exercise `evaluate.key` through the real dispatcher. Add a
  dispatch-level regression test per loop confirming `check_findings` (docs-sync) and the equivalent
  code-run-gate state now return `yes`/`no` (not `error`) against real `key=value` stdout, closing the gap
  that let BUG-2893/BUG-2894 ship unnoticed.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`EvaluateConfig`** class in `scripts/little_loops/fsm/schema.py` starts at
  the class def (line 38); its field list runs from `type` (line 74) through
  `error_patterns` (line 115); docstring `Attributes:` block is lines 44-71.
  `to_dict()` starts line 119 — each optional field is emitted with an
  `if self.<field> is not None:` guard (e.g. `path` at lines 134-135).
  `from_dict()` starts line 178 and is a **strict allowlist projection** —
  every field is read via an explicit `data.get("<name>")` call (lines
  181-206); there is no passthrough or unknown-key detection, confirming
  `key:` is silently dropped today with zero signal to the loop author.
- **`evaluate_output_numeric`** in `scripts/little_loops/fsm/evaluators.py`
  is defined at lines 242-278: `def evaluate_output_numeric(output, operator,
  target)`. Its entire body is `value = float(output.strip())` (line 261,
  inside try/except ValueError) then an operator lookup against
  `_NUMERIC_OPERATORS` (line 268/274). No key/field-extraction step exists.
- **Dispatch site** is the `elif eval_type == "output_numeric":` branch,
  lines 1827-1844 of `evaluators.py`. It resolves `config.target` (numeric,
  numeric-string, or interpolated) then calls `evaluate_output_numeric(output=output,
  operator=config.operator or "eq", target=numeric_target)` — this is the
  exact call site that needs a `key=config.key` kwarg added.
- **`source:` composes for free**: `FSMExecutor` resolves `state.evaluate.source`
  *before* calling `evaluate()` (`scripts/little_loops/fsm/executor.py` lines
  2008-2016) — `eval_input` is either the interpolated `source` template or
  raw action stdout, and that resolved string is what `output` receives.
  `key:` extraction, once added, operates on whatever `source:` already
  produced, with no special-case handling needed (confirms Proposed Solution
  step 4's "should compose without special handling").
- **No reusable extraction helper exists.** `output_json`'s `path:` analog
  (`_extract_json_path`, evaluators.py lines 281-309) does structural dict/list
  traversal on parsed JSON, not regex/text scanning — it is not reusable for
  `key=value` extraction over raw stdout. The closest existing regex-scan
  precedent in the same file is `evaluate_output_contains`'s `re.search(pattern,
  output)` (line 424).
- **`re.escape` convention** to follow for the key regex: this codebase
  consistently builds dynamic regexes as `rf"...{re.escape(x)}..."` — see
  `scripts/little_loops/issue_parser.py:149`,
  `scripts/little_loops/dependency_mapper/analysis.py:510`
  (`re.search(rf"^{re.escape(key)}\s*:", ...)`, the closest existing
  "labelled-field-in-text" extraction, though YAML-style `key:` not `key=`).
- **Existing test coverage** to extend: `scripts/tests/test_fsm_evaluators.py`
  `TestOutputNumericEvaluator` (lines 78-165) unit-tests `evaluate_output_numeric()`
  directly with only 3 positional args (no `key` case exists yet); dispatch-level
  coverage is `test_dispatch_output_numeric*` (lines 516-544). Schema round-trip
  tests live in `scripts/tests/test_fsm_schema.py` `TestEvaluateConfig` (lines
  92-192) — `test_to_dict_full`/`test_roundtrip_serialization` are the pattern
  to follow for a new `key` field.
- **Pre-existing regression test will need reconciling** (not previously
  captured in this issue): `scripts/tests/test_rn_build.py`
  `test_score_acceptance_uses_output_numeric_pass_rate` (lines 580-605) asserts
  `"key" not in evaluate` for `rn-build.yaml`'s `score_acceptance` state,
  with an inline comment explaining the loop author worked around the missing
  `key:` support by echoing a bare numeric pass rate + routing the
  human-readable breakdown to a sidecar file. This assertion encodes the
  *current absence* of `key:` support as a load-bearing constraint — it will
  need updating (or the loop author may choose to keep the bare-echo pattern
  and leave the assertion as-is) once this issue lands. Add to Implementation
  Steps: check whether `rn-build.yaml`'s `score_acceptance` state should
  switch to `key:` and reconcile this test either way.

## Implementation Steps

1. Add the `key` field to `EvaluateConfig` with serialization round-trip coverage.
2. Implement extraction in `evaluate_output_numeric`; unit-test: bare number (no key),
   labelled single line, in-line multi-field, multiple matches (last wins), missing key,
   non-numeric value, key requiring regex escaping.
3. Wire `key=config.key` at the dispatch site.
4. Update `docs/reference/API.md` and the loop-authoring reference.
5. Close out BUG-2893 and BUG-2894 against the new behaviour.
6. Reconcile `scripts/tests/test_rn_build.py::test_score_acceptance_uses_output_numeric_pass_rate`
   (lines 580-605) — it currently asserts `"key" not in evaluate` for
   `rn-build.yaml`'s `score_acceptance` state as a documented workaround for
   the missing feature; decide whether to switch that state to `key:` or
   update the test's rationale comment to reflect that `key:` is now
   available but intentionally unused there.
7. Confirm `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Add `key` to the `evaluateConfig.properties` object in `scripts/little_loops/fsm/fsm-loop-schema.json`
   (~line 654-811) — required because `additionalProperties: false` there will otherwise reject `key:`
   independently of the Python dataclass accepting it.
9. Add a dispatch-level regression test in `scripts/tests/test_builtin_loops.py` asserting `docs-sync.yaml`'s
   `check_findings` state and `oracles/code-run-gate.yaml`'s equivalent state return `yes`/`no` (not
   `error`) against real `key=value` stdout, so a future regression in `key` extraction is caught at the
   loop level, not just the unit level.

## Impact

- **Backward compatibility**: Fully compatible — behaviour is unchanged when `key` is
  absent, which is every loop except the two already broken.
- **Value**: Fixes two live built-in loop defects with no shell rewrite; removes a
  recurring authoring trap.
- **Pairs with**: ENH-2896 (reject unknown evaluate keys). ENH-2896 is the more important
  of the two — it prevents the *next* inert field. This issue only fixes the current one.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/reference/API.md` | `little_loops.fsm.evaluators` / `schema` reference to update |
| `docs/ARCHITECTURE.md` | Evaluator dispatch and verdict routing |
| `.claude/CLAUDE.md` | Loop Authoring rules and evaluator inventory |

## Resolution

Implemented as designed:

- `EvaluateConfig` (`scripts/little_loops/fsm/schema.py`) gained a `key: str | None = None`
  field, wired into `to_dict`/`from_dict` and documented in the docstring.
- `evaluate_output_numeric` (`scripts/little_loops/fsm/evaluators.py`) gained a `key`
  parameter: when set, it extracts the value from a `<key>=<number>` field via
  `re.escape`d regex (last match wins on multiple occurrences), returning
  `verdict="error"` with a message naming the key when no match is found.
- The `output_numeric` dispatch branch now passes `key=config.key`.
- `fsm-loop-schema.json`'s `evaluateConfig` object gained a `key` property (its
  `additionalProperties: false` would otherwise reject the field even though the
  dataclass accepts it).
- `docs-sync.yaml`'s `route_results` state and `oracles/code-run-gate.yaml`'s
  `run_test` state — both already declaring `key:` per BUG-2893/BUG-2894 — now
  dispatch correctly instead of silently dropping the field.
- Scope decision (per issue): `key:` was **not** extended to `convergence`/`score_stall`
  — kept minimal, per the issue's own recommendation.
- `test_rn_build.py::test_score_acceptance_uses_output_numeric_pass_rate`'s rationale
  comment was updated to reflect that `key:` now exists but is intentionally unused by
  `score_acceptance` (it already routes its breakdown to a sidecar file).
- Added unit coverage for all extraction semantics (bare number, labelled line, inline
  multi-field, multiple matches, missing key, non-numeric value, regex-escaping) plus
  schema round-trip tests and dispatch-level regression tests against the real
  `docs-sync.yaml`/`code-run-gate.yaml` evaluate configs.

`python -m pytest scripts/tests/` passes (16943 passed, 42 skipped). `ll-loop validate`
confirms both previously-broken loops are still valid.

## Session Log
- `/ll:manage-issue` - 2026-07-28T23:08:14Z - `9ed63129-861e-4bf5-8b7e-b0f89f3bb886.jsonl`
- `/ll:wire-issue` - 2026-07-28T22:53:04 - `d8188f17-397f-4d48-a22c-6f0a3d74e416.jsonl`
- `/ll:refine-issue` - 2026-07-28T22:48:29 - `1c772f63-2cee-4c82-9ee4-8c538d4c9157.jsonl`
- `/ll:verify-issues` - 2026-07-28T22:25:21 - `f37e3f6b-746f-494f-89ff-1a095c8399bf.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:13:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c5d6d08-1571-414a-8fb3-349dddc4e1fc.jsonl`

---

## Status

open
