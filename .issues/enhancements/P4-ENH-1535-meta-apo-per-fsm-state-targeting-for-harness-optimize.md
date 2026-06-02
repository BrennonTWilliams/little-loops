---
id: ENH-1535
type: ENH
priority: P4
captured_at: '2026-05-17T01:43:21Z'
discovered_date: '2026-05-17'
discovered_by: capture-issue
status: done
relates_to:
- FEAT-1120
- FEAT-766
- FEAT-849
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# ENH-1535: Meta-APO — Per-FSM-State Targeting for harness-optimize

## Summary

Extend `harness-optimize.yaml` (FEAT-1120) to support a per-FSM-state targeting mode, so the `action:` prompt of an individual state inside a loop YAML can be optimized in isolation against a state-scoped example set. Today `harness-optimize` treats targets as whole files via globs; this is fine for `SKILL.md` / `CLAUDE.md` but the wrong shape for loop YAMLs, where each state has its own contract (input fields, output fields, downstream consumers) and each state should be APO'd against state-specific labeled examples — not against a single rollup score for the whole loop.

## Current Behavior

`harness-optimize` mutates target files end-to-end and gates acceptance on a numeric benchmark score for the whole artifact. Pointing it at `scripts/little_loops/loops/apo-textgrad.yaml` would let the mutator rewrite any part of the YAML against one global score — there is no way to:

- Isolate a single state's `action:` block as the mutable surface
- Supply per-state labeled examples (e.g., `(test_results.output) → expected gradient text` for `compute_gradient`)
- Score state-local quality (gradient usefulness, refinement faithfulness) instead of full-loop convergence

## Expected Behavior

`harness-optimize` accepts a structured target spec for loop YAMLs:

```yaml
targets:
  - file: scripts/little_loops/loops/apo-textgrad.yaml
    states:
      - name: compute_gradient
        examples_file: .ll/meta-apo/compute_gradient.json
        eval: lib/judge-gradient-quality.yaml
      - name: apply_gradient
        examples_file: .ll/meta-apo/apply_gradient.json
        eval: lib/judge-refinement-faithfulness.yaml
```

For each listed state:

1. Extract the `action:` block via the YAML parser (preserve surrounding state config).
2. Treat that block as the `prompt_file` analogue, with the supplied `examples_file` as labeled I/O.
3. Run the eval fragment to score outputs (state-local, not whole-loop).
4. Accept the mutation only if state-local score rises; otherwise revert.
5. Persist the mutated `action:` block back into the YAML state in place, preserving formatting.

Trajectory is kept per-state under `.ll/runs/harness-optimize/<run-id>/states/<state-name>/trajectory.jsonl`.

## Motivation

**Why**: The current `apo-textgrad` loop has three prompt blocks (`test_on_examples`, `compute_gradient`, `apply_gradient`) that each have a tight, well-defined contract. Treating them as one opaque file (the only option today) discards the structural information that makes per-state APO tractable — and conflates noise from one state's failures into another's score. The cleanest place to gain this is by extending `harness-optimize` rather than building a new loop, because mutation/score/revert/commit plumbing is already in place.

**How to apply**: Reach for this when a maintainer wants to tune the loop's own state prompts (meta-APO). Skip if the artifact is a single-prompt file (skill, agent, CLAUDE.md) — `harness-optimize`'s existing whole-file mode is already correct for those.

## Proposed Solution

Extend the existing `harness-optimize` loop rather than forking a new loop, since mutation/score/revert/commit plumbing is already in place. Two pieces to add:

1. **Schema extension** — add optional `targets[].states[]` to the loop config (see API/Interface). When `states:` is omitted, today's whole-file behavior is preserved.
2. **YAML state-block round-trip helper** — small helper in `scripts/little_loops/loops/` that uses `ruamel.yaml` (round-trip mode) to extract a named state's `action:` block, hand it to the mutator as the prompt-under-test, and write the result back in place while preserving sibling keys and formatting. Avoid regex on `action: |` blocks (brittle under indentation changes).

Existing utilities to reuse:

- `harness-optimize.yaml` runtime — mutation/accept/revert state machine
- `ruamel.yaml` round-trip parser (already used elsewhere in the loops package)
- The trajectory writer (extend to key by state name)
- Eval fragment loader used by existing `harness-optimize` runs

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/harness-optimize.yaml` — schema and state-mode wiring; adapt `propose`/`apply` states for state-mode; update trajectory path states
- `scripts/little_loops/loops/` — new state-block extractor/replacer helper (Python module)
- `scripts/little_loops/fsm/schema.py` — add `TargetStateSpec` and `TargetFileSpec` dataclasses; extend `FSMLoop.from_dict()` to parse new top-level `targets:` key
- `scripts/little_loops/fsm/validation.py` — add `"targets"` to `KNOWN_TOP_LEVEL_KEYS`; add validation rules for `states[]` entries (require `name`, `examples_file`, `eval`; reject `states:` when `file` is not a `.yaml` loop config)
- `scripts/little_loops/loops/pyproject.toml` (or equivalent) — add `ruamel.yaml` to package dependencies (currently absent from codebase; needed for round-trip block-scalar preservation)
- `scripts/little_loops/fsm/__init__.py` — add `TargetStateSpec` and `TargetFileSpec` to the import block from `little_loops.fsm.schema` and to the `__all__` list so they are accessible as public API [Agent 2 wiring finding]
- `scripts/little_loops/fsm/fsm-loop-schema.json` — hand-maintained JSON Schema for loop YAMLs; has `"additionalProperties": false` at root (line 200); must add a `targets` property definition or any IDE/editor tooling that validates `harness-optimize.yaml` against this schema will reject the new key [Agent 2 wiring finding — critical]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/apo-textgrad.yaml` — canonical first consumer; once state-mode lands this loop becomes the meta-APO target
- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments()` and `resolve_inheritance()` use `yaml.safe_load`; not modified, but the new helper should not use `yaml.safe_load` for write-back (loses `|` block scalar formatting)
- `scripts/little_loops/fsm/fragments.py` in `_deep_merge()` — deep-merge logic referenced by fragment expansion; state-block helper should not depend on this

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — re-exports all public FSM symbols via `__all__`; `TargetStateSpec` and `TargetFileSpec` must be added to the import block (lines 124–135) and `__all__` list (lines 151–210) so `from little_loops.fsm import TargetFileSpec` does not raise `ImportError` [Agent 1 finding]
- `scripts/little_loops/cli/loop/_helpers.py` — calls `load_and_validate()` in `load_loop()` and `load_loop_with_spec()`; will pick up the new schema validation behavior automatically; no change required but is a runtime consumer of the updated validator [Agent 1 finding]
- `scripts/little_loops/cli/loop/config_cmds.py` — calls `load_and_validate()` in `cmd_validate()`; will emit unknown-key WARNING for `targets:` until `KNOWN_TOP_LEVEL_KEYS` is updated [Agent 2 finding]
- `scripts/little_loops/cli/loop/run.py` — calls `load_and_validate()` in `cmd_run()`; same unknown-key warning exposure [Agent 2 finding]

### Similar Patterns
- Whole-file mutation path inside `harness-optimize` — state-mode should mirror its accept/revert structure, not invent a parallel one
- `scripts/little_loops/frontmatter.py` in `update_frontmatter()` — canonical regex-boundary + `yaml.safe_load` + `yaml.dump` pattern for in-place YAML block replacement; the state-block helper should use the same approach but with `ruamel.yaml` to preserve block scalar formatting of `action: |` multi-line strings

### Tests
- `scripts/tests/test_harness_optimize.py` — existing file; add 2-state fixture loop covering: extraction, isolated mutation, state-local score gating, in-place rewrite preserves siblings; confirm existing whole-file tests still pass

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_harness_optimize.py` — two existing tests **will break** when trajectory path changes: `TestHarnessOptimizeStates.test_trajectory_path_in_accepted_state` (line 146) and `test_trajectory_path_in_rejected_state` (line 152) assert the substring `"harness-optimize-trajectory.jsonl"` in the state action text; update both to assert the new per-state path pattern instead [Agent 3 finding]
- `scripts/tests/test_fsm_schema.py` — new tests needed: (1) `TargetStateSpec.from_dict()` and `TargetFileSpec.from_dict()` round-trip; (2) `FSMLoop.from_dict()` with a `targets:` key populates the new field and defaults to `[]` when absent; (3) a `test_known_keys_no_warning`-style test confirming a YAML with `targets:` produces zero unknown-key warnings after the frozenset update — follow the pattern of `TestLoadAndValidateIntegration.test_commands_key_no_warning` (line 1636) [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — new test needed: validation rejects a `targets[].states[]` entry where the sibling `file:` is not a `.yaml` extension (the rule added in validation.py Step 3) [Agent 3 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — document state-mode as opt-in under `harness-optimize`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md` — the `## harness-optimize` section has two couplings: (1) the "Trajectory" subsection hardcodes the old path `.loops/tmp/harness-optimize-trajectory.jsonl`; (2) the "Context Variables" table describes `targets` only as a space-separated string — needs a state-mode row or note [Agent 2 finding]

### Configuration
- N/A — no new global config; targeting lives in the loop YAML itself

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`ruamel.yaml` is not in the codebase**: All YAML reads use `yaml.safe_load` (PyYAML). `yaml.safe_load` + `yaml.dump` round-tripping loses `action: |` literal block scalar formatting — multi-line action strings become flow-style or quoted. `ruamel.yaml` must be added as an explicit dependency; using plain PyYAML for write-back will silently corrupt formatting.
- **`KNOWN_TOP_LEVEL_KEYS` in `validation.py`**: Unknown top-level keys produce a `WARNING` severity `ValidationError`. Adding `"targets"` to this frozenset is required to avoid spurious warnings when the new key is present.
- **Schema dataclasses in `schema.py`**: `FSMLoop.from_dict()` and `StateConfig.from_dict()` are the parse entry points. The new top-level `targets:` array needs a dedicated `TargetFileSpec(file, glob, states)` dataclass and a `TargetStateSpec(name, examples_file, eval_fragment)` dataclass, parsed inside `FSMLoop.from_dict()`.
- **`propose` + `apply` state prompts need state-mode variants**: In whole-file mode, `propose` asks Claude to output the complete revised file content; `apply` asks Claude to write it to disk. In state-mode, `propose` must be constrained to output only the new `action:` block text for one specific state; `apply` must use the YAML state-block helper (not direct file write) to write it back in-place.
- **Trajectory path is hardcoded** at `.loops/tmp/harness-optimize-trajectory.jsonl` in states `write_trajectory_accepted`, `write_trajectory_rejected`, and `load_directive`. The proposed `.ll/runs/harness-optimize/<run-id>/states/<state-name>/trajectory.jsonl` requires a run-id generation mechanism (none currently exists). Consider using `$(date +%s)` or a UUID in a shell action to seed the run-id in `context`.
- **`load_directive` resume logic** reads the trajectory path via `jq` to restore the last accepted commit SHA. For state-mode, each per-state trajectory is at a different path — the resume logic must be updated to find and restore the last accepted SHA for each state independently.

## Implementation Steps

1. **Add `ruamel.yaml` dependency** — add `ruamel.yaml` to `scripts/pyproject.toml` (currently absent; required for round-trip block-scalar preservation in step 2).
2. **Extend schema dataclasses** in `scripts/little_loops/fsm/schema.py`:
   - Add `TargetStateSpec(name: str, examples_file: str, eval_fragment: str)` dataclass
   - Add `TargetFileSpec(file: str | None, glob: str | None, states: list[TargetStateSpec])` dataclass
   - Extend `FSMLoop.from_dict()` to parse optional top-level `targets:` array into `list[TargetFileSpec]`
3. **Extend schema validation** in `scripts/little_loops/fsm/validation.py`:
   - Add `"targets"` to `KNOWN_TOP_LEVEL_KEYS` frozenset
   - In `load_and_validate()`, add a validation pass: reject `states:` entries where sibling `file` is not a `.yaml` loop config path
4. **Write YAML state-block round-trip helper** at `scripts/little_loops/loops/yaml_state_editor.py` (or similar):
   - `extract_action(loop_yaml_path: Path, state_name: str) -> str` — use `ruamel.yaml` `YAML(typ="rt")` to load the file, return the `states[state_name]["action"]` string
   - `replace_action(loop_yaml_path: Path, state_name: str, new_action: str) -> None` — load with `ruamel.yaml`, set `states[state_name]["action"]`, write back in-place preserving block scalars and surrounding keys
5. **Add state-mode wiring to `harness-optimize.yaml`** — for each listed state, fork the `propose`→`apply`→`score`→`gate`→`commit/revert` cycle to pass state-name and `examples_file` as context, and call the YAML state-block helper in the `apply` state instead of direct file write.
6. **Update trajectory path** — generate a run-id (e.g., `RUN_ID=$(date +%s%N)` in `load_directive`) and write per-state trajectory to `.ll/runs/harness-optimize/${RUN_ID}/states/${state_name}/trajectory.jsonl`; update `load_directive` resume logic to locate the correct per-state path via `find .ll/runs/harness-optimize -name trajectory.jsonl -path "*/states/${state_name}/*"`.
7. **Update accept/revert logic** — `commit_and_log` and `revert_and_log` states must operate on the specific loop YAML file (not the space-separated `context.targets` string); `git add <loop-yaml-file>` / `git restore <loop-yaml-file>` per accepted/rejected state.
8. **Add tests to `scripts/tests/test_harness_optimize.py`** — follow inline YAML string fixture pattern from `test_ll_loop_execution.py:TestEndToEndExecution`; write a 2-state fixture loop YAML to `tmp_path`, call `load_and_validate()`, assert: extraction returns correct action text, `replace_action()` modifies only the target state's action, sibling keys and other states are unchanged, state-local score gating is independent.
9. **Document the mode** in `docs/guides/LOOPS_GUIDE.md` under the `harness-optimize` section — whole-file mode remains default, state-mode is opt-in via `targets[].states[]`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **Export new dataclasses from `fsm/__init__.py`** — after Step 2, add `TargetStateSpec` and `TargetFileSpec` to the import block from `little_loops.fsm.schema` and to the `__all__` list; without this `from little_loops.fsm import TargetFileSpec` raises `ImportError`
11. **Update `fsm/fsm-loop-schema.json`** — after Step 3, add a `targets` property definition to the hand-maintained JSON Schema (has `"additionalProperties": false` at root); this is IDE/editor tooling only (not enforced at runtime) but will flag `harness-optimize.yaml` as invalid in editors without the update
12. **Update `test_harness_optimize.py` trajectory assertions before changing the YAML** — `test_trajectory_path_in_accepted_state` (line 146) and `test_trajectory_path_in_rejected_state` (line 152) assert the substring `"harness-optimize-trajectory.jsonl"`; update these as part of Step 6 (trajectory path change) to assert the new per-state path pattern
13. **Add `TargetStateSpec`/`TargetFileSpec` tests to `test_fsm_schema.py`** — after Step 2, add: round-trip tests for both dataclasses; `FSMLoop.from_dict()` with `targets:` key; `test_known_keys_no_warning`-style test for `targets:`; follow the pattern of `TestLoadAndValidateIntegration.test_commands_key_no_warning` (line 1636)
14. **Update `docs/reference/loops.md`** — after Step 6 and Step 9, update the "Trajectory" subsection (old `.loops/tmp/harness-optimize-trajectory.jsonl` path) and the "Context Variables" table (`targets` entry) to reflect state-mode

## API/Interface

New optional field on `targets[]` entries:

```yaml
targets:
  - file: <path>            # existing
    glob: <pattern>         # existing
    states:                 # NEW — only valid when file is a *.yaml loop config
      - name: <state-name>
        examples_file: <path>
        eval: <fragment-path>
```

Backwards compatible: omitting `states:` retains today's whole-file behavior.

## Related Key Documentation

| Doc | Why relevant |
|-----|--------------|
| `docs/guides/LOOPS_GUIDE.md` | Where `harness-optimize` is documented; needs the new state-mode section |
| `scripts/little_loops/loops/harness-optimize.yaml` | The loop being extended |
| `scripts/little_loops/loops/apo-textgrad.yaml` | Canonical first consumer of state-mode |

## Scope Boundaries

In scope:
- New optional `targets[].states[]` schema on existing `harness-optimize` loop config
- Per-state extraction, mutation, scoring, accept/revert, and trajectory writing
- One canonical consumer: `apo-textgrad.yaml` (used as the fixture for the integration test)

Out of scope:
- Changing whole-file `harness-optimize` semantics (must remain the default and unchanged for existing runs)
- Building a separate "meta-APO" loop YAML — this is an extension, not a new loop
- Cross-state coupling logic (e.g., joint optimization, shared budgets across states) — each listed state is optimized independently in v1
- New evaluators or judges — state-mode reuses whatever the user passes via `eval:`
- Surface-level prompt mutation strategies (TextGrad/critique-and-refine choice) — orthogonal to targeting

## Impact

- **Priority**: P4 — quality-of-life for maintainers tuning loop prompts; no user-facing feature, no incident driving it
- **Effort**: Medium — schema + ruamel.yaml round-trip helper + per-state trajectory keying + 2-state fixture test. Mutation/accept/revert plumbing is reused unchanged
- **Risk**: Low — opt-in via new optional `states:` key; whole-file path is untouched. Main risk is `ruamel.yaml` round-trip formatting drift, mitigated by the in-place-rewrite test
- **Breaking Change**: No — omitting `states:` retains today's whole-file behavior

## Labels

`enhancement`, `loops`, `harness-optimize`, `meta-apo`, `captured`

## Acceptance Criteria

- [ ] `targets[].states[]` schema parses and validates (rejects when sibling `file` is not a `.yaml` loop config)
- [ ] State-mode extracts each named `action:` block, mutates it in isolation, and writes it back preserving surrounding YAML
- [ ] Score gating is per-state — one state regressing does not revert another state's accepted mutation in the same iteration
- [ ] Trajectory files land at `.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl`
- [ ] Existing whole-file `harness-optimize` runs are unchanged (no regression in `test_harness_optimize.py`)
- [ ] Test exercises a 2-state fixture loop end-to-end and asserts only the targeted state's `action:` text changes

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-17_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **12-site change surface with harness-optimize.yaml as the complex hub** — the propose→apply→score→gate cycle fork for state-mode is the hardest part; plan focused implementation time for that state machine extension before tackling the simpler schema/validation additions
- **Trajectory path change has 3 known update sites** — `test_trajectory_path_in_accepted_state` (line 146) and `test_trajectory_path_in_rejected_state` (line 152) assert the old path string; `load_directive` resume logic must be updated atomically with Step 6 or tests will fail mid-implementation
- **ruamel.yaml round-trip block-scalar edge cases** — formatting preservation of multi-line `action: |` strings may need iteration; the `yaml_state_editor.py` in-place-rewrite test (Step 8) is the primary gate for this behavior

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-17
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1552: harness-optimize State-Mode — Schema & Validation Foundation
- ENH-1553: harness-optimize State-Mode — YAML State-Block Round-Trip Helper
- ENH-1554: harness-optimize State-Mode — State Machine Extension & Docs

## Session Log
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `e5cf22fe-a508-4b58-ace6-dd0a2c4187a3.jsonl`
- `/ll:wire-issue` - 2026-05-17T09:39:43 - `622b6864-3c71-469d-a504-d1afbd23be9e.jsonl`
- `/ll:refine-issue` - 2026-05-17T09:33:30 - `4c5ca43d-502c-4a2a-8565-2153945c1188.jsonl`
- `/ll:format-issue` - 2026-05-17T01:46:58 - `9c6e016f-d3b2-4f3e-a2c1-6c7553275998.jsonl`

- `/ll:capture-issue` - 2026-05-17T01:43:21Z - `1ff744fb-fd2c-4c52-b59d-5acb13e9557a.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `5878e1ca-ba39-436b-8cca-4e8f73c71910.jsonl`

---

## Status

- **Status**: open
- **Discovered**: 2026-05-17
