---
id: ENH-2161
priority: P3
type: ENH
status: open
discovered_date: 2026-06-15
discovered_by: capture-issue
captured_at: '2026-06-15T05:06:56Z'
confidence_score: 100
outcome_confidence: 63
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# ENH-2161: Consolidate Overlapping Built-in Loops

## Summary

Three groups of built-in loops share near-identical FSM shapes with only one or two variables differing between siblings. Consolidating each group into a single parameterized loop reduces maintenance surface, eliminates divergence risk, and makes the loop library easier to navigate.

## Current Behavior

The loop library contains 10 separate files across three structural duplicate groups:

- **APO family (5 files)**: `apo-beam.yaml`, `apo-contrastive.yaml`, `apo-feedback-refinement.yaml`, `apo-opro.yaml`, `apo-textgrad.yaml` — all share a generate-variants → score → route-convergence → apply FSM shape; the only variable is how each technique generates and scores candidates.
- **Deep research pair (2 files)**: `deep-research.yaml` and `deep-research-arxiv.yaml` — identical oracle delegation to `oracles/research-coverage`; differ only by `academic_mode` flag and recency-weighted scoring.
- **Generative art trio (3 files)**: `canvas-sketch-generator.yaml`, `p5js-sketch-generator.yaml`, `pixi-generative-art.yaml` — identical init → plan → generate → evaluate → score → snapshot FSM; framework name is the only variable.

Every shared bug fix or improvement requires the same change to be applied across multiple files, creating divergence risk over time.

## Motivation

The loop library has grown three clusters of structural duplicates:

| Group | Current files | Shared shape |
|---|---|---|
| APO family | apo-beam, apo-contrastive, apo-feedback-refinement, apo-opro, apo-textgrad (5) | generate variants → score → route convergence → apply |
| Deep research pair | deep-research, deep-research-arxiv (2) | delegate to `oracles/research-coverage`; differ only by source constraint |
| Generative art trio | canvas-sketch-generator, p5js-sketch-generator, pixi-generative-art (3) | init → plan → generate → evaluate → score → snapshot; framework is the only variable |

Keeping 10 files where 3 would suffice means every shared bug or improvement must be applied in multiple places.

## Expected Behavior

After consolidation:

- **APO**: a single `apo.yaml` with `context.technique: beam|contrastive|feedback-refinement|opro|textgrad`. Each technique adjusts its variant-generation prompt and scoring heuristic via a `lib/apo-technique-prompts.yaml` fragment (or inline routing). At minimum, `apo-contrastive` and `apo-feedback-refinement` (the thinnest overlap) merge first as a pilot.
- **Deep research**: a single `deep-research.yaml` with `context.source_filter: web|arxiv` (default `web`). The arxiv variant sets `academic_mode: true` when delegating to `oracles/research-coverage` and uses recency-weighted scoring.
- **Generative art**: a single `generative-art.yaml` with `context.framework: canvas|p5js|pixi`. Framework name drives the `init` and `generate` action prompts; the FSM states are otherwise identical.

`pixi-data-viz.yaml` is excluded — it targets data visualization, not generative art, so it belongs in a separate lineage.

Backward compatibility: existing `ll-loop run apo-contrastive ...` invocations must continue to work, either via symlink loop stubs (`name: apo-contrastive`, `alias_of: apo`, `context.technique: contrastive`) or a deprecation warning that redirects users.

## Integration Map

### Files to Modify

#### Deep Research Group (Step 1)
- `scripts/little_loops/loops/deep-research.yaml` — expand `with:` block on `run_research` state to use `${context.source_filter}` / `${context.academic_mode}`; add `context.source_filter: ""` and `context.academic_mode: false` defaults
- `scripts/little_loops/loops/deep-research-arxiv.yaml` — replace body with `from: deep-research` stub overriding `context.source_filter: "site:arxiv.org"` and `context.academic_mode: true`; set `visibility: internal` to hide from `ll-loop list`
- `scripts/little_loops/loops/oracles/research-coverage.yaml` — no changes; shared oracle already parameterized via `source_filter`/`academic_mode` in `parameters:` block

#### Generative Art Group (Step 2)
- `scripts/little_loops/loops/p5js-sketch-generator.yaml` — becomes the base for `generative-art.yaml`; replace framework-specific code with `${context.framework}` interpolation
- `scripts/little_loops/loops/pixi-generative-art.yaml` — near-isomorphic to p5js; becomes `from: generative-art` stub with `context.framework: pixi` and pixi-specific `evaluate`/`score`/`generate` overrides
- `scripts/little_loops/loops/canvas-sketch-generator.yaml` — has unique states (`snapshot`, `finalize`, `on_max_iterations: finalize`, true `artifact_versioning:`) absent from p5js/pixi; needs separate inheritance-based approach rather than simple stub
- `scripts/little_loops/loops/lib/common.yaml` — no changes; `diff_stall_gate` fragment shared by p5js and pixi; canvas-sketch doesn't import it

#### APO Group (Step 3)
- `scripts/little_loops/loops/apo-contrastive.yaml` — first merge candidate (Shape A); most overlap with `apo-feedback-refinement`
- `scripts/little_loops/loops/apo-feedback-refinement.yaml` — first merge candidate (Shape A); same context var names (`prompt_file`, `eval_criteria`, `quality_threshold`)
- `scripts/little_loops/loops/apo-beam.yaml` — Shape B (`generate_variants → score_variants → select_best`); already inherits from `lib/apo-base`; uses `beam_width`/`target_score` not `quality_threshold`
- `scripts/little_loops/loops/apo-opro.yaml` — Shape C; unique `init_history` → `update_history` accumulation pattern; uses `target_score`
- `scripts/little_loops/loops/apo-textgrad.yaml` — Shape D; gradient-based, operates on `examples_file` not `prompt_file`; already inherits from `lib/apo-base`
- `scripts/little_loops/loops/lib/apo-base.yaml` — extend as shared parent; currently supplies `max_iterations`, `timeout`, `on_handoff`, `done:` terminal

### FSM Engine Files (if `alias_of` is implemented as a native key)
- `scripts/little_loops/fsm/fragments.py` — add `resolve_alias()` or extend `resolve_inheritance()` to handle `alias_of:` as a delegate-and-inject pattern
- `scripts/little_loops/fsm/validation.py` — add `"alias_of"` to `KNOWN_TOP_LEVEL_KEYS` (line 148); update `is_runnable_loop()` (line 1964) to accept alias stubs as runnable
- `scripts/little_loops/fsm/schema.py` — add optional `alias_of: str | None` field to `FSMLoop` dataclass (`from_dict()` at line 1063)

> **Note**: The `alias_of` key proposed in Expected Behavior does not yet exist in the engine. The `from:` inheritance mechanism (`resolve_inheritance()` in `fragments.py`) is the practical equivalent: a stub with `from: deep-research` + a `context:` override block achieves the same runtime behavior today with no engine changes. `alias_of` is needed only for semantic clarity and `ll-loop validate` enforcement — it can be deferred or treated as a separate sub-task.

### Dependent Files (Callers / Tests to Update)
- `scripts/tests/test_builtin_loops.py` — covers all 10 loop names; must verify backward-compat after each group merge
- `scripts/tests/test_deep_research.py` — dedicated deep-research loop tests; update for parameterized `with:` block
- `scripts/tests/test_deep_research_arxiv.py` — dedicated arxiv loop tests; update for `from:` stub structure
- `scripts/tests/test_fsm_inheritance.py` — inheritance test patterns; add tests for alias-stub shape (`from:` + context override-only stubs)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py` — `load_loop()` and `load_loop_with_spec()` call `load_and_validate()`; alias stubs missing `initial`/`states` will raise `ValueError` without prior inheritance resolution [Agent 1]
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` surfaces "Unknown top-level keys" warning for `alias_of` if not in `KNOWN_TOP_LEVEL_KEYS`; **CRITICAL**: `cmd_install()` copies loop YAML as-is — copying a stub without its target loop breaks user installations; must resolve `from:`/`alias_of` chain before copying [Agent 2]
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` calls `load_and_validate()`; incomplete stubs fail unless `resolve_inheritance()` is called first [Agent 1]
- `scripts/little_loops/doc_counts.py` — `verify_documentation()` calls `is_runnable_loop()` for the loop count checked by `ll-verify-docs`; if alias stubs return `True` from `is_runnable_loop`, the documented counts in `README.md`, `CONTRIBUTING.md`, and `docs/ARCHITECTURE.md` must be updated; if `False`, the count drops and `ll-verify-docs` flags a mismatch [Agent 2]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Tests that WILL BREAK and must be updated:**
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles.test_expected_loops_exist` has a hardcoded `expected = {...}` set; adding `generative-art.yaml` or removing/renaming any of the 10 target files will cause an assertion failure; `TestP5jsSketchGeneratorLoop` and `TestPixiGenerativeArtLoop` read raw YAML and assert on `states["init"]`, `states["evaluate"]`, etc. — these break when the files become `from:` stubs [Agent 3]
- `scripts/tests/test_deep_research_arxiv.py` — `TestDeepResearchArxivYaml.test_required_states_exist`, `test_run_research_source_filter_is_arxiv`, and `test_run_research_academic_mode_is_true` all load raw YAML via `yaml.safe_load`; after Step 1 the file becomes a thin stub with no `states:`, `initial:`, or `run_research` state — all three tests fail immediately [Agent 2/3]
- `scripts/tests/test_deep_research.py` — `test_run_research_with_bindings_present` needs update to check `${context.source_filter}` interpolation token instead of hardcoded empty/false values [Agent 3]
- `scripts/tests/test_doc_counts.py` — `TestIsRunnableLoop` tests `is_runnable_loop()` behavior; if the function is extended to accept alias stubs, the negative cases (`test_missing_initial_returns_false`, `test_missing_states_and_flow_returns_false`) need review; loop count changes require updating `README.md` count [Agent 3]

**Existing test files to add new tests in:**
- `scripts/tests/test_fsm_fragments.py` — covers `resolve_inheritance()` directly; `TestDiffStallGateFragment` reads `lib/common.yaml` directly (breaks if moved); add `test_alias_of_key_no_unknown_warning` once `alias_of` is added to `KNOWN_TOP_LEVEL_KEYS` [Agent 3]
- `scripts/tests/test_fsm_validation.py` — covers `KNOWN_TOP_LEVEL_KEYS`, `is_runnable_loop`, `VALID_VISIBILITY`, `load_and_validate`; add `alias_of` key acceptance test following the `test_import_and_fragments_keys_no_warning` pattern (line 790) [Agent 3]
- `scripts/tests/test_fsm_schema.py` — covers `FSMLoop.from_dict()` and serialization roundtrips; add `test_alias_of_roundtrips_through_serialization` if `alias_of` is added as a dataclass field [Agent 3]
- `scripts/tests/test_ll_loop_commands.py` — `TestLoopListVisibilityFilter` tests `cmd_list` visibility filtering; update to verify alias stubs appear under `--internal` and are absent from default listing; follow existing `_seed()` / `test_default_hides_internal_and_example` pattern (line 712) [Agent 3]

### Documentation
- `scripts/little_loops/loops/README.md` — remove individual entries; add consolidated entries with parameter tables
- `docs/guides/LOOPS_REFERENCE.md` — **primary user-facing reference** (not mentioned in Implementation Steps below); APO section at line 1185, deep-research at line 183, art loops at lines 1617/1748/1892 — all require updates
- `docs/guides/LOOPS_GUIDE.md` — update "Choose Your Loop" decision tree (`apo-*` reference at line 86)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md` — `## deep-research` section (line ~121) with oracle parameter table for `source_filter`/`academic_mode` (lines ~449–458); must reflect the parameterized `with:` bindings after Step 1 [Agent 2]
- `docs/guides/EXAMPLES_MINING_GUIDE.md` — multiple `apo-textgrad` references (lines ~5, 9, 44, 69, 87, 95, 99, 247, 253, 255, 389, 400, 413, 591, 634, 643); file-path "See also" link at line ~643 must still resolve if `apo-textgrad.yaml` becomes a stub [Agent 2]
- `docs/generalized-fsm-loop.md` — code block at lines ~265–267 shows `apo-beam` with `from: lib/apo-base` pattern (referenced as the pattern ENH-2161 extends); line ~440 describes `is_runnable_loop()` behavior for `flow:` shorthand — may need update if function changes [Agent 2]
- `docs/reference/CLI.md` — lines ~621 and ~634 document `ll-loop list --internal` and `--examples` flags; description should note that alias stubs with `visibility: internal` surface under `--internal` [Agent 2]
- `skills/audit-loop-run/SKILL.md` — lines ~334, 337, 340 use `apo-textgrad` as the example loop in invocation examples; update if `apo-textgrad` is renamed or becomes a stub with a different canonical name [Agent 2]

## Implementation Steps

1. **Pilot the deep-research pair** (smallest merge, clearest single variable):
   - In `scripts/little_loops/loops/deep-research.yaml`: add `context.source_filter: ""` and `context.academic_mode: false` defaults; update the `with:` block on `run_research` to pass `source_filter: "${context.source_filter}"` and `academic_mode: "${context.academic_mode}"` (replacing the hardcoded values).
   - Replace `scripts/little_loops/loops/deep-research-arxiv.yaml` body with a `from: deep-research` stub that overrides only `name`, `context.source_filter: "site:arxiv.org"`, `context.academic_mode: true`, and sets `visibility: internal`.
   - Run `ll-loop validate deep-research && ll-loop validate deep-research-arxiv`; run `ll-loop run deep-research-arxiv "test topic" --dry-run` to verify stub delegation.
   - Update `scripts/tests/test_deep_research.py` and `scripts/tests/test_deep_research_arxiv.py` for the new parameterized structure.

2. **Merge the p5js/pixi art pair** (near-isomorphic; canvas-sketch needs separate handling):
   - p5js and pixi share identical FSM topology (`init → plan → generate → evaluate → score → check_stall → done/generate`) and both import `lib/common.yaml` for `diff_stall_gate`. Canvas-sketch adds `snapshot`/`finalize` states and `on_max_iterations: finalize` absent from the other two — treat it as a separate `from: generative-art` extension, not a full merge.
   - Create `generative-art.yaml` based on the p5js shape with `context.framework: p5js` default; replace framework-specific code with `${context.framework}` interpolation where it varies (CDN import, canvas/frame APIs).
   - Add stub `p5js-sketch-generator.yaml` (`from: generative-art`, `context.framework: p5js`) and `pixi-generative-art.yaml` (`from: generative-art`, `context.framework: pixi`, `evaluate`/`score`/`generate` overrides for pixi-specific logic).
   - Validate and smoke-test: `ll-loop validate generative-art && ll-loop validate p5js-sketch-generator && ll-loop validate pixi-generative-art`.

3. **Consolidate the APO family**:
   - The five APO loops span **4 distinct FSM topologies** — contrastive and feedback-refinement share Shape A (`generate → evaluate → route_convergence → apply`) and the same context var names (`prompt_file`, `eval_criteria`, `quality_threshold`). Beam (Shape B), opro (Shape C), and textgrad (Shape D) differ structurally. A single monolithic `apo.yaml` with runtime dispatch on `context.technique` requires either: (a) a prompt large enough to cover all techniques (fragile), or (b) file-sentinel states branching on technique (adds states). The pragmatic first step is Shape A only.
   - **Phase 3a**: Merge `apo-contrastive.yaml` + `apo-feedback-refinement.yaml` into `lib/apo-shape-a.yaml` (a non-runnable base inheriting from `lib/apo-base.yaml`); create `apo-contrastive.yaml` and `apo-feedback-refinement.yaml` as `from: lib/apo-shape-a` stubs with `context.technique` overrides.
   - **Phase 3b** (post-pilot): Extend the scaffold to beam, opro, textgrad once shape differences are resolved. Dispatch via technique-specific fragment library (`lib/apo-techniques.yaml`) or inline conditional prompt.
   - Validate with `ll-loop validate` on each stub; run `scripts/tests/test_builtin_loops.py` to confirm backward-compat.

4. **Update docs after each group merge**:
   - `scripts/little_loops/loops/README.md` — remove individual entries; add consolidated entries with parameter tables
   - `docs/guides/LOOPS_REFERENCE.md` — **primary user-facing catalog** (APO at line 1185, deep-research at line 183, art loops at lines 1617/1748/1892); requires the most substantive rewrite
   - `docs/guides/LOOPS_GUIDE.md` — update "Choose Your Loop" tree (line 86 `apo-*` reference)

5. **Run the full loop test suite** after each group merge: `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_deep_research.py scripts/tests/test_deep_research_arxiv.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Fix `test_deep_research_arxiv.py` before or during Step 1**: adopt the two-fixture pattern from `test_rn_plan_apo.py` — one raw-YAML fixture asserting `from: deep-research` and `visibility: internal`, one resolved fixture asserting `source_filter`/`academic_mode` presence — replacing the current raw-YAML state assertions that will break when the file becomes a stub
7. **Fix `test_builtin_loops.py` `test_expected_loops_exist`** during each group merge: update the hardcoded expected-name set to add `generative-art` (Step 2) and accommodate any stubs; update `TestP5jsSketchGeneratorLoop` and `TestPixiGenerativeArtLoop` to resolve inheritance before asserting on states
8. **Update `doc_counts.py` / documented loop counts**: after each group merge, determine whether alias stubs count as runnable loops (via `is_runnable_loop()`), then update the documented loop counts in `README.md`, `CONTRIBUTING.md`, and `docs/ARCHITECTURE.md` accordingly so `ll-verify-docs` passes
9. **Address `cmd_install()` stub behavior** in `scripts/little_loops/cli/loop/config_cmds.py`: decide whether `ll-loop install deep-research-arxiv` should (a) copy only the stub (requiring the user to also install `deep-research`), (b) auto-install the base loop transitively, or (c) be documented as unsupported for alias stubs; at minimum add a warning if the user tries to install a stub without its base
10. **Update `docs/reference/loops.md`** after Step 1: revise the `## deep-research` section and oracle parameter table (lines ~449–458) to reflect the parameterized `source_filter`/`academic_mode` `with:` bindings
11. **Update `skills/audit-loop-run/SKILL.md`** if `apo-textgrad` changes its canonical invocation name (lines ~334, 337, 340)

## Acceptance Criteria

- [ ] All 10 original loop names still work via alias stubs (backward-compatible)
- [ ] `ll-loop list` shows the consolidated names as the canonical entries (aliases hidden or annotated)
- [ ] `ll-loop validate` passes on all new and alias files
- [ ] Each consolidated loop smoke-tests cleanly via `ll-loop run <name> --dry-run`
- [ ] Loop README and LOOPS_GUIDE updated to reflect consolidated names
- [ ] No divergence between the former siblings: a fix applied to the consolidated loop covers all old variants

## Scope Boundaries

Out of scope:
- `pixi-data-viz.yaml` — targets data visualization, not generative art; belongs in a separate lineage and must not be merged into `generative-art.yaml`
- FSM runner/executor changes — consolidation relies on the existing `context.*` parameter mechanism; no changes to `ll-loop` core or the FSM evaluator
- Loops outside the three identified groups — no other loop families are candidates for this consolidation pass
- Behavioral changes — each consolidated loop must produce functionally identical output to its former siblings for a given input

## Impact

- **Priority**: P3 — Maintenance improvement; reduces long-term divergence risk across 10 files but no immediate user-facing feature gap
- **Effort**: Medium — Three sequential merges of increasing complexity (deep-research pair first, then generative art trio, then APO family); alias stubs add surface area; requires `ll-loop validate` + smoke-test cycles for each group
- **Risk**: Low — Backward-compat stubs preserve all existing `ll-loop run <name>` invocations; changes are additive (new consolidated file + alias stubs replacing originals with no executor changes)
- **Breaking Change**: No — All 10 original loop names continue to work via alias stubs

## Labels

`loop-library`, `maintenance`, `consolidation`, `enhancement`

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Related Key Documentation

- `scripts/little_loops/loops/README.md` — loop library overview (lists all 10 target loops)
- `docs/guides/LOOPS_REFERENCE.md` — **primary user-facing catalog** (APO at line 1185, deep-research at line 183, generative art at lines 1617/1748/1892); must be updated for each consolidated group
- `docs/guides/LOOPS_GUIDE.md` — user-facing loop documentation; "Choose Your Loop" tree at line 86
- `scripts/little_loops/loops/oracles/research-coverage.yaml` — shared oracle for deep-research family; already parameterized with `source_filter`/`academic_mode` `parameters:` contract
- `scripts/little_loops/fsm/fragments.py` — `resolve_inheritance()` (the `from:` mechanism used for alias stubs)
- `scripts/little_loops/fsm/validation.py` — `KNOWN_TOP_LEVEL_KEYS` (line 148), `is_runnable_loop()` (line 1964)
- `scripts/little_loops/cli/loop/info.py` — `cmd_list()` visibility filtering (lines 190–208; `visibility: internal` hides alias stubs)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-15_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Large file surface across 3 sequential group merges (16+ sites); each group's test files must be updated in the same step as the YAML change — partial-completion state breaks the suite between steps
- Breaking tests (`test_deep_research_arxiv.py`, `test_builtin_loops.py`, `TestP5jsSketchGeneratorLoop`/`TestPixiGenerativeArtLoop`) fail the moment their target files become `from:` stubs; coordinate YAML + test changes together
- `cmd_install()` design judgment (wiring step 9) should be settled before touching `config_cmds.py` to avoid backtracking

## Session Log
- `/ll:ready-issue` - 2026-06-15T20:24:05 - `91a8a5fd-314d-4c69-bb5f-935fdabebb30.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `22f89f5b-27ef-43d1-8e94-5a0b515d58b6.jsonl`
- `/ll:wire-issue` - 2026-06-15T20:15:08 - `e0b9f857-1fc5-4626-9a7d-1bb198eb7567.jsonl`
- `/ll:refine-issue` - 2026-06-15T20:04:04 - `87bf3457-ff72-4ed2-8179-8fbbe6351f4b.jsonl`
- `/ll:format-issue` - 2026-06-15T05:13:51 - `668f19ad-7b6d-4dfd-96b4-ef7487916a9b.jsonl`
- `/ll:capture-issue` - 2026-06-15T05:06:56Z
