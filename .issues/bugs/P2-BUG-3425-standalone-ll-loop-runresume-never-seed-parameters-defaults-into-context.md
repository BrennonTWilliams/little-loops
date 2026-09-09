---
id: BUG-3425
type: BUG
title: Standalone ll-loop run/resume never seed parameters defaults into context
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T20:18:41Z'
---

# BUG-3425: Standalone ll-loop run/resume never seed parameters defaults into context

## Summary

Standalone `ll-loop run` and `ll-loop resume` never apply loop-level `parameters:` defaults to the FSM context. `ParameterSpec.default` is only consumed on the sub-loop `with:` binding path (`scripts/little_loops/fsm/executor.py:1090-1096`); neither `scripts/little_loops/cli/loop/run.py` nor `scripts/little_loops/cli/loop/lifecycle.py` reads `fsm.parameters` at all. A loop declaring `parameters: {max_remediation_passes: {type: integer, default: 3}}` therefore gets no `max_remediation_passes` key in context when launched directly, so `${context.max_remediation_passes}` either trips the pre-run missing-key check (`run.py:278`) or renders empty.

## Current Workaround In The Catalog

The builtin loops duplicate the default as a literal under `context:`:

- `scripts/little_loops/loops/rn-remediate.yaml:66` — `max_remediation_passes: 3` under `context:` while the `parameters:` entry at line 48 carries only a description saying "(default: 3)" and no `default:` field.
- `scripts/little_loops/loops/rn-decompose.yaml:51` — `parent_depth: 0` under `context:` mirroring the `parameters:` entry at line 41 ("(default: 0)").
- The comment at `rn-remediate.yaml:86` explicitly calls `max_remediation_passes` "a per-loop default that callers can tune", i.e. the literal exists to serve what `parameters.default` should already provide.

## Origin

Proposal from the ll-console agent (2026-09-09). Its diagnosis was that a `context:` entry shaped `{type: number, default: 3}` renders its Python repr when interpolated and should be "collapsed" at run start. That symptom is real but the seam is wrong: typed dicts under `context:` are an undocumented form (the JSON schema's `context` is `additionalProperties: true`, no typed-entry shape). The documented typed-declaration form is the top-level `parameters:` block (FEAT-1311), and the actual gap is that its defaults are not seeded for standalone runs.

## Proposed Solution

1. Add `seed_parameter_defaults(context: dict[str, Any], parameters: dict[str, ParameterSpec]) -> None` to `scripts/little_loops/fsm/context_seed.py`. For each non-required parameter whose `default is not None`, `context.setdefault(name, spec.default)`. `setdefault` keeps precedence: positional input (run.py:165-179), `program.md` injection, and the persisted resume context (lifecycle.py:658-660) all land before it and win.
2. Call it from both `run.py` (immediately before the `apply_context_overrides` call at line 190) and `lifecycle.py` (immediately before line 665), following the same shared-helper pattern `apply_context_overrides` already uses so the two launch paths cannot diverge. Placing it before overrides means `--context k=v` still wins and `_coerce_override` sees the typed default (an `int`/`bool` instance), so coercion works without the `{type:}` dict branch.
3. Add `default:` to the `parameters:` entries currently duplicated under `context:` (rn-remediate `max_remediation_passes`, rn-decompose `parent_depth`; audit `scripts/little_loops/loops/lib/common.yaml:54` `max_retries` and any other `parameters:` entry whose description says "default:") and remove the `context:` duplicates. Keep the surrounding comments that explain caller tuning.
4. Optional lint: `ll-loop validate` warning when a `context:` value is a dict carrying a `type` key, pointing the author at `parameters:`.

## Explicit Non-Goals

- Do **not** change `FSMLoop.from_dict` / `to_dict` or what `ll-loop show -j` emits (`scripts/little_loops/fsm/schema.py:1504-1506, 1691`). ll-console renders parameter forms from the raw emitted spec (parameter metadata plus the `context:` literal as the displayed default) and depends on it staying declarative. After step 3 the default moves into the emitted `parameters[name].default`, which is already serialized by `ParameterSpec.to_dict`; ll-console should prefer that field when present.
- Do not add a `{type, default}` dict form under `context:`.

## Acceptance Criteria

- [ ] Fixture loop with `parameters:` of type integer, boolean, and string, each with `default:` and `required: false`; standalone `ll-loop run` seeds all three into context with native Python types.
- [ ] Same fixture via `ll-loop resume` seeds the defaults when the persisted state lacks the key, and does not overwrite a persisted value.
- [ ] `--context k=v` overrides the seeded default and is coerced to the declared type via `_coerce_override`.
- [ ] Positional input and `program.md` injection win over a parameter default for the same key.
- [ ] `required: true` parameters without `default:` are unaffected (still missing, still caught by the pre-run check).
- [ ] `ll-loop show -j` output for the fixture is byte-identical before and after the change apart from the added `default` fields under `parameters`.
- [ ] rn-remediate and rn-decompose carry their defaults under `parameters:` only; `ll-loop validate` passes on both.


## Current Behavior

Standalone `ll-loop run` and `ll-loop resume` never seed `parameters:` defaults into context. Only the sub-loop `with:` binding path in `executor.py:1090-1096` applies `ParameterSpec.default`. A loop declaring an optional parameter with a `default:` gets no corresponding key seeded into context when launched directly.

## Expected Behavior

All three loop-launch paths — sub-loop `with:` binding, standalone `ll-loop run`, and `ll-loop resume` — seed `parameters:` defaults into context consistently, with existing precedence (positional input, `program.md` injection, persisted resume context, `--context` overrides) still winning over the seeded default.

## Motivation

`parameters:` with typed `default:` is the documented declaration form (FEAT-1311), but it silently does nothing outside sub-loop `with:` bindings. Loop authors work around this by duplicating the default as a `context:` literal (`rn-remediate.yaml`, `rn-decompose.yaml`), which is an undocumented `context:` shape, creates two sources of truth that can drift, and is the root cause of the Python-repr-rendering symptom the ll-console agent originally reported (see Origin). Fixing the seeding gap removes the workaround and makes `parameters.default` behave consistently across all three launch paths.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/context_seed.py` — add `seed_parameter_defaults()`
- `scripts/little_loops/cli/loop/run.py` — call before the `apply_context_overrides` call at line 190
- `scripts/little_loops/cli/loop/lifecycle.py` — call before line 665
- `scripts/little_loops/loops/rn-remediate.yaml` — move `max_remediation_passes` default from `context:` (line 66) to `parameters:` (line 48)
- `scripts/little_loops/loops/rn-decompose.yaml` — move `parent_depth` default from `context:` (line 51) to `parameters:` (line 41)
- `scripts/little_loops/loops/lib/common.yaml:54` — audit `max_retries` and any other `parameters:` entry whose description says "default:"
  > ⚠ Superseded — this is a fragment `with:` param, no context: duplicate
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — same `context:`/`parameters:` duplication: `min_pass_rate` (lines 68/104) and `health_bound_seconds` (lines 72/105) [Agent 1 finding]
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — same pattern: `pass_threshold` (lines 39/59) and `artifact_path` (lines 43/61) [Agent 1 finding]
- `scripts/little_loops/loops/oracles/generator-evaluator-flux.yaml` — same pattern: `steps` (lines 32/44) and `prompt_file` (lines 28/43) [Agent 1 finding]
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml` — same pattern: `max_retries` (lines 22/32) and `tag` (lines 26/33) [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:1090-1096` — existing sub-loop `with:` binding consumer of `ParameterSpec.default`; must stay consistent with the new shared helper
- `scripts/little_loops/fsm/schema.py:1504-1506, 1691` — `ParameterSpec.to_dict` / `ll-loop show -j` emission consumed by ll-console; unaffected by this fix per Explicit Non-Goals

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/structural_rules.py:229,288-325` — iterates `fsm.parameters`/`child_fsm.parameters` during `ll-loop validate`; the optional Step-4 context-shadows-parameters lint belongs alongside this [Agent 1 finding]
- `scripts/little_loops/fsm/validation/_base.py:158` — `_check_param_type()` helper called from `structural_rules.py`; existing consumer of `ParameterSpec` [Agent 1 finding]
- `scripts/little_loops/cli/loop/info.py:1444-1477` (`cmd_show`) — concrete `ll-loop show -j` implementation (`fsm.to_dict()` → `print_json`); must stay byte-identical apart from added `default` fields per AC [Agent 1 finding]
- `scripts/little_loops/cli/loop/testing.py` (`cmd_simulate`, ~176-220) — a fourth context-construction path (`ll-loop simulate`) that builds `fsm.context` independently and calls none of `apply_context_overrides`/`seed_confidence_thresholds`/`inject_design_context`; will stay unseeded after this fix unless also wired — the issue's "three launch paths" framing misses this one [Agent 2 finding]

### Similar Patterns
- `apply_context_overrides` — the existing shared-helper pattern `seed_parameter_defaults` should follow so the two launch paths cannot diverge

### Tests
- `scripts/tests/` — new fixture loop with integer/boolean/string `parameters:` (each `default:`, `required: false`) plus tests for standalone `ll-loop run`, `ll-loop resume`, `--context` override precedence, and `required: true` parameters without `default:`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_commands.py:5699-5823` (`TestContextOverrideCoercion`) — existing home for `context_seed.py`/`apply_context_overrides` unit tests (no dedicated `test_context_seed.py` exists); new `seed_parameter_defaults` tests belong here or a sibling class, following `test_cmd_run_applies_coerced_overrides`'s pattern [Agent 3 finding]. No existing test parallels it for the `lifecycle.py:665` resume call site — new coverage needed there specifically [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py:9832-9868` (`test_with_applies_declared_defaults`) — direct sibling test (`not required and default is not None` seeding) to model new standalone-path tests on [Agent 3 finding]
- `scripts/tests/test_fsm_schema.py:2909-3049` (`TestParameterSpec`) — existing `ParameterSpec.to_dict`/`from_dict` round-trip coverage; extend for the `default` field paths this fix exercises [Agent 1 finding]
- `scripts/tests/test_fsm_validation_structural.py:480-533` (`TestParameterValidation`) — existing `_validate_parameters` coverage; extend if the Step-4 optional lint is implemented [Agent 1/3 finding]
- `scripts/tests/test_rn_remediate.py:1040-1043` (`test_context_max_remediation_passes_set`) and `:1118-1126` (`test_context_defaults_match_spec`) — assert `data["context"]["max_remediation_passes"] == 3` directly; **will break** once the `context:` literal is removed — update to the `TestConfidenceGateThresholdsNotHardcoded`-style contract (absent from `context:`, present via `parameters.max_remediation_passes.default`) [Agent 2/3 finding — tests_to_update]
- `scripts/tests/test_rn_decompose.py:264-268` (`test_parent_depth_default_in_context`) — asserts `ctx.get("parent_depth") == 0` directly; **will break** the same way [Agent 2/3 finding — tests_to_update]
- `scripts/tests/test_builtin_loops.py` — `TestMr11MarkerSet.test_marker_set_matches_enumeration` / `MR11_MARKER_ALLOWLIST` entry `("loops/rn-remediate.yaml", "context.max_remediation_passes", "ENH-3358")` ties to the usage-site marker comment at `rn-remediate.yaml:870`; adjacent to the `context:` block being trimmed — verify it still resolves, and re-check the stale line-number comment near `rn-remediate.yaml:86` [Agent 2 finding]

### Documentation
- `docs/reference/CLI.md` — `ll-loop run`/`ll-loop resume` parameter-default behavior

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` § "Typed parameter bindings (`parameters:` / `with:`)" — currently documents `default:` only for the `with:`-bound path; needs a note that standalone `run`/`resume` now also seed it [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` § "Sharing context" (Typed parameter bindings bullet) — same gap [Agent 2 finding]

### Configuration
- N/A

## Program Design

### Types

- (none new — reuses `ParameterSpec` from `scripts/little_loops/fsm/schema.py`)

### Signatures

- `seed_parameter_defaults(context: dict[str, Any], parameters: dict[str, ParameterSpec]) -> None` — `scripts/little_loops/fsm/context_seed.py`

### Call Path

`cli/loop/run.py:run()` -> `seed_parameter_defaults()` -> `apply_context_overrides()` (mirrored in `cli/loop/lifecycle.py` resume path)

## Implementation Steps

1. Add `seed_parameter_defaults()` to `scripts/little_loops/fsm/context_seed.py`
2. Call it from `run.py` (before line 190) and `lifecycle.py` (before line 665), following the `apply_context_overrides` shared-helper pattern
3. Move the duplicated `context:` literal defaults (rn-remediate, rn-decompose, common.yaml) into `parameters.default` and remove the `context:` duplicates
4. Optional: add an `ll-loop validate` lint warning when a `context:` value is a dict carrying a `type` key
5. Verify with the fixture loop against each Acceptance Criterion

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/loops/oracles/code-run-gate.yaml`, `generator-evaluator.yaml`, `generator-evaluator-flux.yaml`, `enumerate-and-prove.yaml` — move each duplicated default from `context:` to `parameters.*.default` and remove the `context:` literal, same treatment as rn-remediate/rn-decompose
- Update `scripts/tests/test_rn_remediate.py` and `scripts/tests/test_rn_decompose.py` — replace the raw-`context:`-literal assertions with the `TestConfidenceGateThresholdsNotHardcoded`-style contract (absent from `context:`, present via `parameters.*.default`, resolves via `seed_parameter_defaults`)
- Verify `scripts/tests/test_builtin_loops.py`'s `MR11_MARKER_ALLOWLIST` entry for `context.max_remediation_passes` still resolves against the trimmed `rn-remediate.yaml` `context:` block
- Decide and record whether `ll-loop simulate` (`cli/loop/testing.py::cmd_simulate`) should also call `seed_parameter_defaults` for parity across all context-construction paths, or is explicitly out of scope for this issue
- Update `docs/generalized-fsm-loop.md` and `docs/guides/LOOPS_GUIDE.md` — note that `parameters.default` now also seeds on standalone `ll-loop run`/`resume`, not just `with:` bindings

## Impact

- **Priority**: P2 - silent context gap breaks `parameters.default` outside sub-loop `with:` bindings, but shipped loops currently mask it with the `context:` literal workaround
- **Effort**: Medium - one new helper, two call sites, plus migrating rn-remediate, rn-decompose, and common.yaml off the workaround
- **Risk**: Low - purely additive seeding via `setdefault`; existing precedence order is preserved by design
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-09 | Priority: P2

## Steps to Reproduce

1. Create a loop YAML with `parameters: {max_remediation_passes: {type: integer, default: 3}}` and a state referencing `${context.max_remediation_passes}`.
2. Run it directly with `ll-loop run <loop>.yaml` (not as a sub-loop `with:` binding).
3. Observe: the pre-run missing-key check at `run.py:278` rejects the run, or the interpolation renders empty — `max_remediation_passes` was never seeded because `run.py`/`lifecycle.py` never read `fsm.parameters`.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/run.py` and `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: `run.py` before the `apply_context_overrides` call (line 190); `lifecycle.py` before line 665
- **Cause**: Only the sub-loop `with:` binding path in `executor.py:1090-1096` seeds `ParameterSpec.default` into context — neither standalone launch entry point reads `fsm.parameters` at all.

## Error Messages

## Environment

## Frequency

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 1090-1096
- **Anchor**: sub-loop `with:` binding default-seeding — the only existing call site that applies `ParameterSpec.default`
- **Code**:
```
# ParameterSpec.default is read here for sub-loop `with:` bindings only;
# run.py and lifecycle.py have no equivalent call.
```

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (line-anchor corrections below applied
in the same pass, so the issue as it now reads is up to date for those two items
— this section is a record of what was wrong and fixed, not an outstanding
action item for them; the AC-coverage gap below is a separate, unresolved
finding).

- Fixed two off-by-one anchor citations in `## Current Workaround In The
  Catalog`: `rn-remediate.yaml:65` → `:66` (the `max_remediation_passes: 3`
  context literal), `rn-decompose.yaml`'s `parameters:` entry line `42` → `41`
  (the `parent_depth:` key). All other file/line anchors in this issue
  (`run.py:190`, `run.py:278`, `lifecycle.py:665`, `executor.py:1090-1096`,
  `context_seed.py`, `structural_rules.py:229,288-325`, `_base.py:158`,
  `info.py:1444` `cmd_show`, `testing.py:176` `cmd_simulate`, all cited test
  class/function names and line numbers, and the two docs section headers)
  verified exact against current HEAD.
- `ll-verify-evidence --json` on this file: clean (`"ok": true`, 0 findings) —
  no fabricated evidence quotes.
- No active required decision-log rules (`ll-issues decisions list` returned
  no entries) — decisions check ran, no conflict.
- `ll-code --json status`: `provider=codegraph freshness=fresh` — used to
  cross-check `ParameterSpec` fields and the `_coerce_override` int/float/bool
  branches referenced by the Program Design.

**Remaining (proposal-vs-code consequence check, ENH-3250):** Acceptance
Criterion 7 ("rn-remediate and rn-decompose carry their defaults under
`parameters:` only; `ll-loop validate` passes on both") covers only 2 of the
6 loop files the Integration Map and Implementation Steps' Wiring Phase
require modifying — `code-run-gate.yaml`, `generator-evaluator.yaml`,
`generator-evaluator-flux.yaml`, and `enumerate-and-prove.yaml` have no
corresponding AC verifying their `context:`/`parameters:` duplication was
removed or that `ll-loop validate` passes on them post-migration. Separately,
the Wiring Phase explicitly defers a scope decision ("Decide and record
whether `ll-loop simulate` ... should also call `seed_parameter_defaults` ...
or is explicitly out of scope") that the issue never makes — it is neither an
AC nor listed under `## Explicit Non-Goals`, so an implementer has no forcing
function either way. Both are AC/Integration-Map coverage gaps, not claims
about current-state fact, so they don't change today's verdict — but they
should be resolved (extend AC 7 to the 4 oracle loops; add the `ll-loop
simulate` decision to Explicit Non-Goals or as a new AC) before this issue is
marked implementation-ready.

## Session Log
- `/ll:verify-issues` - 2026-09-09T21:00:41 - `9d974726-ede8-4e9b-8bf3-5dc1cbd42201.jsonl`
- `/ll:wire-issue` - 2026-09-09T20:54:46 - `5d5214fd-1a0f-4890-8f02-11b97e9c697b.jsonl`
- `/ll:refine-issue` - 2026-09-09T20:41:28 - `505beecf-ceb4-4da8-912d-d233f746daca.jsonl`
- `/ll:format-issue` - 2026-09-09T20:37:49 - `575c8055-4eaf-4c28-a902-79bb09bf07a6.jsonl`
- `/ll:capture-issue` - 2026-09-09T20:18:50 - `c67d0e9c-2f18-4a69-ac01-c129392655e2.jsonl`
