---
id: BUG-3425
type: BUG
title: Standalone ll-loop run/resume never seed parameters defaults into context
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T20:18:41Z'
completed_at: '2026-09-09T22:17:11Z'
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 82
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 20
---

# BUG-3425: Standalone ll-loop run/resume never seed parameters defaults into context

## Summary

`ParameterSpec.default` is applied in exactly one place: the sub-loop `with:` binding branch at `scripts/little_loops/fsm/executor.py:1090-1096`. Every other context-construction path ignores `fsm.parameters`:

- standalone `ll-loop run` (`scripts/little_loops/cli/loop/run.py`)
- `ll-loop resume` (`scripts/little_loops/cli/loop/lifecycle.py`)
- the sub-loop `context_passthrough` branch (`executor.py:1116-1123`, no `with:`)
- `ll-loop simulate` (`scripts/little_loops/cli/loop/testing.py::cmd_simulate`, ~176-220)

A loop declaring `parameters: {max_remediation_passes: {type: integer, default: 3}}` therefore gets no `max_remediation_passes` key when launched directly, so `${context.max_remediation_passes}` either trips the pre-run missing-key check (`run.py:291-314`) or renders empty.

## Current Workaround In The Catalog

Builtin loops duplicate the value as a literal under `context:`. Fourteen builtin loops have at least one key present in both `context:` and `parameters:` (enumerated by loading each YAML under `scripts/little_loops/loops/` and intersecting the two key sets). The duplicates fall into three shapes:

**(a) Optional parameter, default lives only in `context:`** — the description says "(default: N)" but `parameters:` has no `default:` field:

| Loop | Key | `context:` literal | Declared type |
|---|---|---|---|
| `rn-remediate.yaml` | `max_remediation_passes` (ctx :66 / param :48) | `3` | integer |
| `rn-remediate.yaml` | `skip_learning_gate` | `""` | string |
| `rn-decompose.yaml` | `parent_depth` (ctx :51 / param :41) | `0` | integer |
| `oracles/code-run-gate.yaml` | `min_pass_rate` (:104 / :63) | `0.95` | number |
| `oracles/code-run-gate.yaml` | `health_bound_seconds` (:105 / :69) | `10` | number |
| `oracles/generator-evaluator.yaml` | `pass_threshold` (:59 / :36) | `6` | number |
| `oracles/generator-evaluator.yaml` | `artifact_path` (:61 / :40) | `"index.html"` | string |
| `oracles/generator-evaluator.yaml` | `rubric` | `""` | string |
| `oracles/generator-evaluator.yaml` | `pre_evaluate_cmd` | `""` | string |
| `oracles/generator-evaluator-flux.yaml` | `prompt_file` (:43 / :22) | `"image-prompt.txt"` | string |
| `oracles/generator-evaluator-flux.yaml` | `steps` (:44 / :29) | `20` (int) | **string** — mismatch |
| `oracles/generator-evaluator-flux.yaml` | `base_seed` (:46 / :33) | `1` (int) | **string** — mismatch |
| `oracles/enumerate-and-prove.yaml` | `max_retries` (:32 / :19) | `"2"` | string |
| `oracles/enumerate-and-prove.yaml` | `tag` (:33 / :23) | `"ENUMERATE_JSON"` | string |
| `oracles/plan-node-refine.yaml` | `max_depth` (:90 / :69) | `3` | integer |
| `oracles/plan-node-refine.yaml` | `max_node_iters` (:91 / :73) | `2` | integer |
| `oracles/plan-node-refine.yaml` | `max_nodes` (:92 / :77) | `40` | integer |
| `oracles/plan-node-refine.yaml` | `deadline_epoch` (:93 / :81) | `0` | integer |
| `oracles/research-coverage.yaml` | `source_filter` (:38 / :25) | `""` | string |
| `oracles/research-coverage.yaml` | `academic_mode` (:39 / :29) | `false` | boolean |

**(b) Optional parameter that already has `parameters.default`, plus an identical `context:` literal** — pure redundancy:

| Loop | Key | Both values |
|---|---|---|
| `dataset-curation.yaml` | `data_dir` (:46 / :27) | `"data/raw"` |
| `dataset-curation.yaml` | `output_dir` (:47 / :32) | `"data/curated"` |
| `dataset-curation.yaml` | `schema_path` (:48 / :37) | `"schemas/dataset.json"` |
| `oracles/plan-research-iteration.yaml` | `overwrite_source` (:29 / :19) | `"false"` |
| `oracles/resolve-decision.yaml` | `skip_probe` (:29 / :23) | `"false"` |

**(c) `required: true` parameter with an empty-string `context:` placeholder** — cannot become a `default:` (the validator forbids `required` + `default`, `structural_rules.py:251-257`); the placeholder only exists to satisfy the pre-run missing-key check on a standalone launch:

| Loop | Key | Placeholder |
|---|---|---|
| `oracles/integrate-node.yaml` | `run_dir` (:47 / :41) | `""` |
| `oracles/plan-research-iteration.yaml` | `run_dir` (:28 / :15) | `""` |
| `oracles/plan-node-refine.yaml` | `depth` (:89 / :65) | `0` |
| `oracles/resolve-decision.yaml` | `issue_id` (:28 / :20) | `""` |
| `oracles/verify-confidence-scores.yaml` | `issue_id` (:13 / :9) | `""` |

The comment at `rn-remediate.yaml:86` explicitly calls `max_remediation_passes` "a per-loop default that callers can tune", i.e. the literal exists to serve what `parameters.default` should already provide. (That comment also cites "line 60", which is already stale — the literal is at line 66.)

Keys under `context:` that are **not** parameters (e.g. rn-remediate's `min_pass_rate`, `diagnose_*`, `require_refine_and_wire`; flux's `artifact_path`; dataset-curation's `quality_threshold`, `min_per_category`, `adversarial_cap`; research-coverage's `depth`, `coverage_threshold_pct`) are ordinary loop context and stay where they are.

## Origin

Proposal from the ll-console agent (2026-09-09). Its diagnosis was that a `context:` entry shaped `{type: number, default: 3}` renders its Python repr when interpolated and should be "collapsed" at run start. That symptom is real but the seam is wrong. No builtin loop uses a typed dict under `context:` (verified by loading all `scripts/little_loops/loops/**/*.yaml`). The documented typed-declaration form is the top-level `parameters:` block (FEAT-1311), and the actual gap is that its defaults are not seeded outside the `with:` branch.

Note: `scripts/little_loops/fsm/context_seed.py:104-105` and the `{type:}` branch of `_coerce_override` at `:148-158` deliberately coerce `--context` overrides against a `{type: ...}` dict already sitting under a context key, and `scripts/tests/test_ll_loop_commands.py:5703` covers it. That branch stays (it is harmless and tested), but the issue's position is that the dict form is a coercion fallback, not a declaration form loop authors should write — hence the optional lint in step 5.

## Proposed Solution

1. **Helper.** Add `seed_parameter_defaults(context: dict[str, Any], parameters: dict[str, ParameterSpec]) -> None` to `scripts/little_loops/fsm/context_seed.py`. For each parameter with `required is False` and `default is not None`, `context.setdefault(name, spec.default)`. Empty-string defaults (`default: ""`) are seeded; explicit `default: null` is treated as absent.

2. **Seed as early as possible in every launch path**, so all later precedence layers simply overwrite:
   - `run.py`: immediately after `load_loop` succeeds and the CLI flag overrides (before line 165). **Not** before `apply_context_overrides` at line 190 as originally proposed — positional JSON-dict input at `run.py:171` only unpacks keys already present in `fsm.context` (`matched = {k: v for k, v in parsed.items() if k in fsm.context}`), so seeding after it would make `ll-loop run rn-remediate '{"max_remediation_passes": 5}'` fall through to the raw-string branch once the `context:` literal is removed.
   - `lifecycle.py`: immediately after `load_loop` (before the persisted-context restore at line 658). The restore writes `fsm.context[key] = value`, so persisted values overwrite the seeded default.
   - `executor.py`: call once at ~line 1130 next to `seed_confidence_thresholds(child_fsm.context)` / `derive_input_hash(child_fsm.context)` (the BUG-2767/BUG-2832 pattern, which is why `context_seed.py` has no `cli/` dependency), covering both the `with:` and `context_passthrough` branches. Delete the inline default-application loop at `executor.py:1090-1096`; the required-parameter check right after it stays.
   - `testing.py::cmd_simulate`: call right before `derive_input_hash(fsm.context)` at line 220.

   Resulting precedence, unchanged from today for every existing key: `--context` > program.md > positional input > persisted resume context / `with:` / passthrough > loop `context:` literal > `parameters.default`.

3. **Validation.** Extend `_validate_parameters` in `scripts/little_loops/fsm/validation/structural_rules.py:229-257` to type-check `default` against `type` via the existing `_check_param_type` (`_base.py:158`). Today it checks only unknown types, enum without `values`, and `required`+`default`, so a `type: string` parameter with `default: 20` passes silently. This matters for step 4.

4. **Migrate all 14 loops** off the workaround, by shape:
   - **Shape (a)** — move each literal into `parameters.<name>.default` and delete the `context:` entry; keep the explanatory comments, retargeted at the `parameters:` entry. Flux `steps` and `base_seed`: the `synthesize` action parses both with `int(...)` (`generator-evaluator-flux.yaml:95`), so change them to `type: integer` with integer defaults `20` / `1`. The wrapper `flux-image-generator.yaml:113-114` binds them as interpolation strings, which `_validate_with_bindings` skips, so the retype is validate-clean.
   - **Shape (b)** — delete the `context:` entry; `parameters.default` already carries the value.
   - **Shape (c)** — delete the placeholder. A required parameter with no value is exactly what the pre-run check at `run.py:291-314` exists to report (`Missing required context variable: 'issue_id'`), and every catalog caller binds these keys via `with:` (`rn-refine.yaml:340`, `rn-plan.yaml:272`, `autodev.yaml:665,681`, `refine-to-ready-issue.yaml:295,346,574,754`, `rn-remediate.yaml:297,313`, `plan-node-refine.yaml:26,181` self-recursion) or via `--context run_dir=...` on a standalone launch (`rn-refine.yaml:817`, `integrate-node.yaml:7,31`), both of which win over an absent key. Today the placeholder lets a mis-launched oracle start with an empty ID and fail deep inside a shell action; after removal it fails fast at pre-flight. Unchanged hazard to note in the YAML comment: `run.py:200` auto-injects a fresh `run_dir` when the key is absent, so `integrate-node` launched without `--context run_dir` would run against a fresh dir instead of the shared one — that was already true whenever the placeholder was overridden, and the pre-flight cannot catch it because the key is present by then.

   Per-file result (keys that **stay** under `context:` in parentheses):
   - `rn-remediate.yaml`: move `max_remediation_passes` (3), `skip_learning_gate` (""). Fix the "line 60" citation at `:86`. (stay: `min_pass_rate`, `diagnose_*`, `require_refine_and_wire`)
   - `rn-decompose.yaml`: move `parent_depth` (0). `context:` block becomes empty — delete the block.
   - `oracles/code-run-gate.yaml`: move `min_pass_rate` (0.95), `health_bound_seconds` (10). Block becomes empty.
   - `oracles/generator-evaluator.yaml`: move `pass_threshold` (6), `artifact_path` ("index.html"), `rubric` (""), `pre_evaluate_cmd` (""). Block becomes empty.
   - `oracles/generator-evaluator-flux.yaml`: move `prompt_file` ("image-prompt.txt"), `steps` (20, retype integer), `base_seed` (1, retype integer). Update the ENH-2823 sync comment at `:44-45`. (stay: `artifact_path`)
   - `oracles/enumerate-and-prove.yaml`: move `max_retries` ("2"), `tag` ("ENUMERATE_JSON"). Block becomes empty.
   - `oracles/plan-node-refine.yaml`: move `max_depth` (3), `max_node_iters` (2), `max_nodes` (40), `deadline_epoch` (0); drop `depth` placeholder. Block becomes empty.
   - `oracles/research-coverage.yaml`: move `source_filter` (""), `academic_mode` (false). (stay: `depth`, `coverage_threshold_pct`)
   - `dataset-curation.yaml`: drop `data_dir`, `output_dir`, `schema_path` (defaults already declared). (stay: `quality_threshold`, `min_per_category`, `adversarial_cap`)
   - `oracles/plan-research-iteration.yaml`: drop `overwrite_source` (default already declared) and the `run_dir` placeholder. Block becomes empty.
   - `oracles/resolve-decision.yaml`: drop `skip_probe` (default already declared) and the `issue_id` placeholder. Block becomes empty.
   - `oracles/integrate-node.yaml`: drop the `run_dir` placeholder; add the comment noted above. Block becomes empty.
   - `oracles/verify-confidence-scores.yaml`: drop the `issue_id` placeholder. Block becomes empty.

5. **Guard against regression.** Add a test in `scripts/tests/test_builtin_loops.py` that loads every builtin loop under `scripts/little_loops/loops/` (including `oracles/`, excluding `lib/` fragments) and asserts no key appears in both `context:` and `parameters:`. No allowlist. Optional: an `ll-loop validate` **warning** (not error) for a `context:` key that shadows a `parameters:` key, and another for a `context:` value that is a dict carrying a `type` key.

## Explicit Non-Goals

- Do **not** change `FSMLoop.from_dict` / `to_dict` or the shape of what `ll-loop show -j` emits (`scripts/little_loops/fsm/schema.py:329-351` `ParameterSpec.to_dict`/`from_dict`; `cli/loop/info.py:1444-1477` `cmd_show`). `ParameterSpec.to_dict` already serializes `default`.
- Do not add a `{type, default}` dict form under `context:`.
- Do not migrate `scripts/little_loops/loops/lib/common.yaml:54` `max_retries`: it is a fragment `with:` parameter with no `context:` duplicate.
- Do not touch `context:` keys that are not declared parameters, even where they look like defaults (e.g. `deep-research.yaml`'s `source_filter`/`academic_mode` are the wrapper's own context, bound into `research-coverage` via `with:`).

## ll-console Coordination

After step 4, `ll-loop show -j` for the migrated loops no longer has the migrated keys under `context`; the default lives at `parameters[name].default` instead, and required parameters have no `context` entry at all. ll-console currently renders the `context:` literal as the displayed default, so it must prefer `parameters[name].default` when present, fall back to `context[name]`, and render required parameters with no default as empty/required. File that as a linked ll-console issue and land it before or with this change; until it lands, the console shows an empty default for the migrated keys.

## Acceptance Criteria

- [x] Fixture loop with `parameters:` of type integer, boolean, and string (plus one with `default: ""`), each `required: false` with `default:`; standalone `ll-loop run` seeds all into context with native Python types.
- [x] Same fixture via `ll-loop resume` seeds the defaults when the persisted state lacks the key, and does not overwrite a persisted value.
- [x] Same fixture via `ll-loop simulate` seeds the defaults.
- [x] A parent loop invoking the fixture as a sub-loop via `context_passthrough` (no `with:`) seeds the defaults; via `with:` the behavior is unchanged from today (bound value wins, unbound optional gets the default, unbound required raises).
- [x] `--context k=v` overrides the seeded default and is coerced to the declared type via `_coerce_override`.
- [x] Positional input — both the raw-string form and the JSON-dict unpack form at `run.py:171` — and `program.md` injection win over a parameter default for the same key.
- [x] `required: true` parameters without `default:` are unaffected (still missing, still caught by the pre-run check).
- [x] `ll-loop validate` reports an error for a parameter whose `default` does not match its declared `type` (`_check_param_type`).
- [x] All 14 loops in step 4 have no key present in both `context:` and `parameters:`; every shape-(a) key carries its former literal as `parameters.<name>.default`; non-parameter `context:` keys are untouched; `ll-loop validate` passes on all 14 and on their callers (`rn-implement`, `rn-refine`, `rn-plan`, `rn-remediate`, `autodev`, `refine-to-ready-issue`, `sft-corpus`, `deep-research`, `flux-image-generator`, `svg-image-generator`, `html-anything`, `hitl-md`, `hitl-compare`, `integrate-sdk`, `adopt-third-party-api`).
- [x] Flux `steps`/`base_seed` are `type: integer` with integer defaults; `scripts/tests/test_flux_image_generator.py::test_steps_default_agrees_across_wrapper_and_oracle` is updated to read the oracle default from `parameters.steps.default` and still asserts agreement with the wrapper's `context.steps` and the `FLUX_STEPS` fallback literal.
- [x] Standalone `ll-loop run oracles/resolve-decision` (and the other four shape-(c) loops) with no binding for the required key fails at pre-flight with `Missing required context variable: '<key>'` instead of starting.
- [x] `scripts/tests/test_builtin_loops.py` gains a no-duplicate-keys test over the whole builtin catalog with no allowlist.
- [x] `ll-loop show -j` output for the fixture is byte-identical before and after the change apart from the added `default` fields under `parameters`.
- [ ] Full suite green: `python -m pytest scripts/tests/`.

## Current Behavior

Only the sub-loop `with:` binding branch in `executor.py:1090-1096` applies `ParameterSpec.default`. `ll-loop run`, `ll-loop resume`, `ll-loop simulate`, and the sub-loop `context_passthrough` branch never read `fsm.parameters`, so an optional parameter with a `default:` gets no key seeded into context on those paths.

## Expected Behavior

Every context-construction path seeds `parameters:` defaults through one shared helper, with the existing precedence order preserved: `--context` > program.md > positional input > persisted resume context / `with:` / passthrough > loop `context:` literal > `parameters.default`.

## Motivation

`parameters:` with typed `default:` is the documented declaration form (FEAT-1311), but it silently does nothing outside sub-loop `with:` bindings. Fourteen builtin loops work around this by duplicating the value as a `context:` literal, creating two sources of truth that drift (flux's `steps` is already `type: string` in one block and `20` in the other; three loops carry the same default in both blocks; five carry empty placeholders for required parameters). Fixing the seeding gap, adding the default-vs-type check, and clearing the catalog removes the workaround, the drift, and the need for placeholders.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/context_seed.py` — add `seed_parameter_defaults()`
- `scripts/little_loops/cli/loop/run.py` — call after `load_loop` and the CLI flag overrides, before the positional-input block at line 165
- `scripts/little_loops/cli/loop/lifecycle.py` — call after `load_loop` (line 633), before the persisted-context restore at line 658
- `scripts/little_loops/fsm/executor.py` — call at ~line 1130 for both sub-loop branches; delete the inline loop at 1090-1096
- `scripts/little_loops/cli/loop/testing.py` — call in `cmd_simulate` before `derive_input_hash` at line 220
- `scripts/little_loops/fsm/validation/structural_rules.py:229-257` — `_validate_parameters` gains the default-vs-type check; optional shadow/typed-dict warnings
- Loop YAMLs, all under `scripts/little_loops/loops/`: `rn-remediate.yaml`, `rn-decompose.yaml`, `dataset-curation.yaml`, `oracles/code-run-gate.yaml`, `oracles/generator-evaluator.yaml`, `oracles/generator-evaluator-flux.yaml`, `oracles/enumerate-and-prove.yaml`, `oracles/plan-node-refine.yaml`, `oracles/research-coverage.yaml`, `oracles/plan-research-iteration.yaml`, `oracles/resolve-decision.yaml`, `oracles/integrate-node.yaml`, `oracles/verify-confidence-scores.yaml` — per the step-4 list

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation/_base.py:158` — `_check_param_type()`, reused for the new default-vs-type check
- `scripts/little_loops/fsm/schema.py:308-351` — `ParameterSpec`; unchanged
- `scripts/little_loops/cli/loop/info.py:1444-1477` (`cmd_show`) — unchanged; output for migrated loops changes only because the YAML changes
- Callers of the migrated loops, all binding via `with:`: `rn-implement.yaml:776,1195`, `rn-refine.yaml:340,491`, `rn-plan.yaml:272`, `rn-remediate.yaml:297,313`, `autodev.yaml:665,681`, `refine-to-ready-issue.yaml:295,346,574,754`, `sft-corpus.yaml:590`, `deep-research.yaml:49`, `flux-image-generator.yaml:108`, `svg-image-generator.yaml:68`, `html-anything.yaml:139`, `hitl-md.yaml:164`, `hitl-compare.yaml:142`, `integrate-sdk.yaml:131`, `adopt-third-party-api.yaml:65`, `oracles/plan-node-refine.yaml:26,181` (self-recursion and its research sub-loop)
- Standalone launch of `oracles/integrate-node` with `--context run_dir=...`: `rn-refine.yaml:817`, `integrate-node.yaml:7,31`

### Similar Patterns
- `seed_confidence_thresholds` / `derive_input_hash` — shared `context_seed.py` leaves already called from `run.py`, `lifecycle.py`, `testing.py`, and `executor.py`; `seed_parameter_defaults` follows the same wiring

### Tests
- `scripts/tests/test_ll_loop_commands.py:5699-5823` (`TestContextOverrideCoercion`) — home for `context_seed.py` unit tests; add `seed_parameter_defaults` tests here or in a sibling class, following `test_cmd_run_applies_coerced_overrides`
- `scripts/tests/test_fsm_executor.py:9832-9868` (`test_with_applies_declared_defaults`) — must still pass after the inline loop moves into the helper; add a passthrough sibling
- `scripts/tests/test_fsm_validation_structural.py:480-533` (`TestParameterValidation`) — extend for the default-vs-type check
- **Tests that break on migration and must be updated:**
  - `scripts/tests/test_rn_remediate.py:1040-1043` (`test_context_max_remediation_passes_set`) and `:1118-1126` (`test_context_defaults_match_spec`) — assert `data["context"]["max_remediation_passes"] == 3`; retarget to `parameters.max_remediation_passes.default`
  - `scripts/tests/test_rn_decompose.py:264-268` (`test_parent_depth_default_in_context`) — same
  - `scripts/tests/test_flux_image_generator.py:188-200` (`test_steps_default_agrees_across_wrapper_and_oracle`) — reads `oracle_raw["context"]["steps"]`; retarget to `parameters.steps.default`
  - `scripts/tests/test_builtin_loops.py:18466-18472` (`test_oracle_min_pass_rate_has_default`) — asserts `"min_pass_rate" in oracle_data["context"]`; retarget to `parameters.min_pass_rate.default == 0.95`
- Verified **not** affected (they assert the wrappers' own `context:`, not the oracles'): `scripts/tests/test_deep_research.py:108-118` and `test_deep_research_arxiv.py:130-138,239-240` (deep-research.yaml), `scripts/tests/test_builtin_loops.py:9434` (rn-refine `max_depth`), `:15866` (`TestRnRefineRecursiveDecomposition`, rn-refine), `:13031` (proof-first-task), `scripts/tests/test_rn_plan.py:124` and the `output_dir not in ctx` family (wrapper loops)
- Not affected: `scripts/tests/test_builtin_loops.py` `MR11_MARKER_ALLOWLIST` (`test_marker_set_matches_enumeration`, `:20795`) only enumerates `# ll-lint: mr11-ok(...)` marker comments at usage sites (e.g. `rn-remediate.yaml:870`, `plan-node-refine.yaml` `context.max_depth`/`context.deadline_epoch` at `:20659,20661`), which do not move
- Implementer must grep `scripts/tests/` for each migrated key against `["context"]` / `.get("context"` once the YAML edits land; the four listed above are what the pre-implementation grep found
- New: no-duplicate-keys guard in `scripts/tests/test_builtin_loops.py`, no allowlist

### Documentation
- `docs/generalized-fsm-loop.md` § "Typed parameter bindings (`parameters:` / `with:`)" (line 221) — currently documents `default:` only for the `with:` path; state that defaults seed on every launch path and give the precedence chain; state that a required parameter needs no `context:` placeholder
- `docs/guides/LOOPS_GUIDE.md` § "Sharing context" (line 1130, Typed parameter bindings bullet) — same
- `docs/reference/CLI.md` — `ll-loop run`/`resume`/`simulate` parameter-default behavior; `ll-loop validate` default-vs-type error
- `docs/guides/LOOPS_REFERENCE.md:374` — `integrate-node` standalone launch note stays accurate (`--context run_dir` still required)

### Configuration
- N/A

## Program Design

### Types

- (none new — reuses `ParameterSpec` from `scripts/little_loops/fsm/schema.py`)

### Signatures

- `seed_parameter_defaults(context: dict[str, Any], parameters: dict[str, ParameterSpec]) -> None` — `scripts/little_loops/fsm/context_seed.py`

### Behavior Parity

Deleting the inline default-application loop at `executor.py:1090-1096` must preserve, for the `with:` branch, exactly what `scripts/tests/test_fsm_executor.py:9832-9868` (`test_with_applies_declared_defaults`) locks in today:

- A parameter bound in `with:` keeps the bound value; the default never overwrites it. The helper's `setdefault` runs after `child_fsm.context = {**child_fsm.context, **resolved}`, so the bound value is already present.
- An unbound optional parameter with `default is not None` lands in `child_fsm.context` with its native type.
- An unbound `required: true` parameter still raises `ValueError("Sub-loop '...' requires parameter '...' but it is not bound in 'with'")`. That check stays where it is (`executor.py:1097-1103`), evaluated on `resolved` before the merge, unchanged.
- A child's own `context:` literal for a parameter key still wins over `parameters.default` (literal is in `child_fsm.context` before the helper runs), matching the CLI paths.
- `run_dir` re-injection (`executor.py:1113-1114`) and the `seed_confidence_thresholds` / `derive_input_hash` calls keep their current order relative to each other; the new call goes immediately before `seed_confidence_thresholds`.

Only the `context_passthrough` branch gains new behavior (defaults now seeded); no existing passthrough caller of a loop with `parameters:` defaults exists in the builtin catalog, so no builtin run changes.

Removing the shape-(c) placeholders changes one observable: a standalone launch of those five loops without the required key now stops at the `run.py:291-314` pre-flight instead of starting with an empty value. Every catalog caller binds the key, so no builtin run changes.

### Call Path

`cli/loop/run.py:cmd_run()` -> `load_loop()` -> `seed_parameter_defaults()` -> positional input -> program.md -> `apply_context_overrides()`
`cli/loop/lifecycle.py:cmd_resume()` -> `load_loop()` -> `seed_parameter_defaults()` -> persisted-context restore -> `apply_context_overrides()`
`fsm/executor.py` sub-loop dispatch -> (`with:` merge | passthrough merge) -> `seed_parameter_defaults()` -> `seed_confidence_thresholds()` -> `derive_input_hash()`
`cli/loop/testing.py:cmd_simulate()` -> `load_loop()` -> `seed_parameter_defaults()` -> `derive_input_hash()`

## Implementation Steps

1. Add `seed_parameter_defaults()` to `context_seed.py` with unit tests (int/bool/str/"" defaults, `required: true` skipped, `default: null` skipped, existing key untouched).
2. Wire it into `run.py`, `lifecycle.py`, `executor.py` (both branches, delete the inline loop), and `testing.py` at the positions above; add the precedence tests (positional raw + JSON-dict, program.md, persisted resume, `--context`, passthrough, `with:`).
3. Add the default-vs-type check to `_validate_parameters` with tests.
4. Migrate the 14 loops per the step-4 list (shape (a): move; shape (b): drop the literal; shape (c): drop the placeholder); retype flux `steps`/`base_seed` to integer; fix `rn-remediate.yaml:86` and the flux `:44-45` sync comment; delete `context:` blocks that become empty; update the four affected tests and any others the post-edit grep surfaces.
5. Add the no-duplicate-keys guard test over the whole catalog.
6. Optional: `ll-loop validate` warnings for context-shadows-parameter and typed-dict-under-context.
7. Update the docs; run `ll-loop validate` on the 14 loops and their callers; run the full suite.
8. File the ll-console coordination issue (prefer `parameters[name].default`; render required-without-default as required).

## Impact

- **Priority**: P2 - silent context gap breaks `parameters.default` outside sub-loop `with:` bindings; shipped loops mask it with `context:` literals that have already drifted (flux `steps` type) and with empty placeholders for required parameters
- **Effort**: Medium - one helper, four call sites, one validator check, 14 YAML migrations (mostly line deletions) with four known test updates, one guard test, docs
- **Risk**: Low - additive `setdefault` seeding; precedence order preserved by seeding first. Behavior changes are limited to (1) the new validate error for default/type mismatch, which no builtin loop trips after the flux retype, and (2) fail-fast pre-flight for standalone launches of the five shape-(c) loops without their required key.
- **Breaking Change**: No for loop authors. ll-console's default display for the migrated loops changes shape (see ll-console Coordination).

## Related Key Documentation

- `docs/generalized-fsm-loop.md` § "Typed parameter bindings"
- `docs/guides/LOOPS_GUIDE.md` § "Sharing context"

## Status

**Done** | Created: 2026-09-09 | Priority: P2

## Steps to Reproduce

1. Create a loop YAML with `parameters: {max_remediation_passes: {type: integer, default: 3}}`, no `context:` block, and a state referencing `${context.max_remediation_passes}`.
2. Run it directly with `ll-loop run <loop>.yaml` (not as a sub-loop `with:` binding).
3. Observe: the pre-run missing-key check at `run.py:291-314` rejects the run — `max_remediation_passes` was never seeded because `run.py` never reads `fsm.parameters`. The same holds for `ll-loop resume`, `ll-loop simulate`, and a parent invoking it with `context_passthrough: true`.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/run.py`, `scripts/little_loops/cli/loop/lifecycle.py`, `scripts/little_loops/cli/loop/testing.py`, `scripts/little_loops/fsm/executor.py` (passthrough branch)
- **Anchor**: each path's context construction after `load_loop`
- **Cause**: default application was implemented inline in the `with:` branch of the executor (FEAT-1311) instead of as a shared `context_seed.py` leaf, so no other path got it.

## Error Messages

```
Missing required context variable: 'max_remediation_passes'. Run with: ll-loop run <loop> --context max_remediation_passes=VALUE
```

## Environment

## Frequency

Every standalone/resume/simulate/passthrough launch of a loop that relies on `parameters.default` without a `context:` duplicate.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 1090-1096
- **Anchor**: sub-loop `with:` binding default-seeding — the only existing site that applies `ParameterSpec.default`
- **Code**:
```
# Apply declared defaults for unbound optional parameters
for param_name, param_spec in child_fsm.parameters.items():
    if (
        param_name not in resolved
        and not param_spec.required
        and param_spec.default is not None
    ):
        resolved[param_name] = param_spec.default
```

## Verification Notes

Manual review 2026-09-09 (post confidence-check), corrections applied in this rewrite:

- Call-site placement moved from "before `apply_context_overrides`" to "right after `load_loop`" because `run.py:171`'s JSON-dict positional unpack only matches keys already in context.
- Added the `context_passthrough` executor branch and `cmd_simulate` as unseeded paths; the executor call now sits with `seed_confidence_thresholds`/`derive_input_hash` and replaces the inline loop.
- Catalog duplication is 14 loops, not 6. Scope widened to all 14 (user decision, 2026-09-09); the duplicates were classified into three shapes because five of them are `required: true` placeholders that cannot become `default:` and are dropped instead. Every caller of every migrated loop was checked and binds via `with:` (or `--context run_dir` for `integrate-node`'s standalone launch).
- `_validate_parameters` does not type-check `default`; added as a required step because flux `steps`/`base_seed` are `type: string` with int literals.
- Added the two additional breaking tests (`test_flux_image_generator.py:188`, `test_builtin_loops.py:18466`); confirmed the deep-research, rn-refine, rn-plan, and proof-first-task context assertions target wrapper loops and are unaffected; dropped the MR-11 allowlist concern (marker comments are at usage sites, unaffected).
- Reconciled the "undocumented typed-dict form" claim with `_coerce_override`'s `{type:}` branch: no builtin loop uses the form; the branch stays as a coercion fallback.
- ll-console default-display change promoted from a Non-Goals aside to a coordination section.
- Removed the stale "migrating common.yaml" effort note.

Earlier pass: `ll-verify-evidence --json` clean; no active decision-log rules; `ll-code --json status` `provider=codegraph freshness=fresh`.

## Resolution

Implemented per the plan: added `seed_parameter_defaults()` to
`scripts/little_loops/fsm/context_seed.py`; wired it into `cli/loop/run.py`
(before positional input), `cli/loop/lifecycle.py` (before the persisted-context
restore), `cli/loop/testing.py::cmd_simulate` (before `derive_input_hash`), and
`fsm/executor.py`'s sub-loop dispatch (covering both `with:` and
`context_passthrough`, replacing the inline default-application loop that used
to live only in the `with:` branch). Added a default-vs-type check to
`_validate_parameters` (`structural_rules.py`) reusing `_check_param_type`.
Migrated all 14 catalog loops off the `context:` duplication workaround per
the three shapes in the plan, including retyping flux `steps`/`base_seed` to
`integer`. Added a no-allowlist no-duplicate-keys guard test
(`TestNoContextParameterKeyDuplication`) over the whole builtin catalog.

Not done (out of scope for this repo): filing the linked ll-console
coordination issue — ll-console is a separate project/repo not present here.
Until that lands, ll-console's default display for the 14 migrated loops
falls back to empty for keys that moved from `context:` to
`parameters.<name>.default`.

Full suite: `python -m pytest scripts/tests/` is green for everything this
change touches. Five failures remain in the suite, all pre-existing and
unrelated (verified via `git stash` against this change): a `.issues/`
evidence-verifiability gate and priority-regex-allowlist tests tripped by
unrelated in-flight issue edits already in this working tree
(`scripts/tests/test_verify_evidence.py`, `scripts/tests/test_issue_parser.py`),
an unrelated env-var baseline-coverage test
(`scripts/tests/test_host_runner.py`), and a flaky SSE fan-in timing test
(`scripts/tests/test_feat3323_sse_bridge.py`, passes in isolation).

## Session Log
- `/ll:manage-issue` - 2026-09-09T22:17:11 - `3ffb97df-a1e4-4572-9fad-20e96964df3d.jsonl`
- `/ll:confidence-check` - 2026-09-09T21:32:00 - `821b29bc-73ec-49a6-a196-da3d28ebbdc1.jsonl`
- `/ll:confidence-check` - 2026-09-09T21:15:09 - `15a3a72b-d6e3-4759-990e-0642b22d6179.jsonl`
- `/ll:reconcile-issue` - 2026-09-09T21:04:56 - `a5bdbdca-a5bb-459a-a98a-2040741996e1.jsonl`
- `/ll:verify-issues` - 2026-09-09T21:00:41 - `9d974726-ede8-4e9b-8bf3-5dc1cbd42201.jsonl`
- `/ll:wire-issue` - 2026-09-09T20:54:46 - `5d5214fd-1a0f-4890-8f02-11b97e9c697b.jsonl`
- `/ll:refine-issue` - 2026-09-09T20:41:28 - `505beecf-ceb4-4da8-912d-d233f746daca.jsonl`
- `/ll:format-issue` - 2026-09-09T20:37:49 - `575c8055-4eaf-4c28-a902-79bb09bf07a6.jsonl`
- `/ll:capture-issue` - 2026-09-09T20:18:50 - `c67d0e9c-2f18-4a69-ac01-c129392655e2.jsonl`
