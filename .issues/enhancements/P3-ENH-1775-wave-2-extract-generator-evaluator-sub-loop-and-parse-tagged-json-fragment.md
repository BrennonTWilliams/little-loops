---
captured_at: '2026-05-29T01:01:55Z'
discovered_date: 2026-05-28
discovered_by: capture-issue
parent: EPIC-1773
confidence_score: 100
outcome_confidence: 70
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
implementation_order_risk: true
---

# ENH-1775: Wave 2 — Extract `generator-evaluator` Sub-loop and Add `parse_tagged_json` Fragment

## Summary

Extract the most-duplicated multi-state pattern in the codebase — the `generate → evaluate (Playwright) → score (LLM rubric) → iterate` cycle used by 5 harness loops — into a standalone `generator-evaluator` sub-loop. Also add a `parse_tagged_json` fragment to unify the tagged-JSON-line parsing pattern shared by 3 integration loops.

## Current Behavior

**Generator-Evaluator pattern** — 5 harness loops each reimplement the full cycle inline:

- `html-website-generator.yaml`
- `svg-image-generator.yaml`
- `html-anything.yaml`
- `hitl-md.yaml`
- `hitl-compare.yaml`

Each duplicates: Playwright screenshot invocation, CAPTURED/ALL_PASS output_contains routing, critique.md writeback, and the multi-criterion weighted rubric scoring pattern with structured output.

**Tagged JSON parsing** — 3 integration loops each contain a near-identical python3 heredoc that parses a tagged JSON line from LLM output:

- `adopt-third-party-api.yaml` — parses `ENUMERATE_JSON:` tag
- `integrate-sdk.yaml` — parses `ENUMERATE_JSON:` tag
- `assumption-firewall.yaml` — parses `ASSUMPTIONS_JSON:` tag

Each duplicates the python3 invocation, line-splitting, tag-matching, and JSON extraction.

## Expected Behavior

**`generator-evaluator` sub-loop** at `loops/oracles/generator-evaluator.yaml`:

Accepts parameters: generate prompt, rubric criteria, pass_threshold, design_tokens_context, run_dir. The 5 parent loops become thin wrappers that supply these inputs and delegate to the sub-loop.

**`parse_tagged_json` fragment** in `loops/lib/common.yaml`:

```yaml
parse_tagged_json:
  action_type: shell
  action: |
    python3 -c "
    import sys, json
    text = sys.stdin.read()
    for line in text.splitlines():
        if '${context.json_tag}:' in line:
            print(line.split('${context.json_tag}:', 1)[1].strip())
            break
    "
```

Callers set `context.json_tag` (e.g., `ENUMERATE_JSON`, `ASSUMPTIONS_JSON`).

## Motivation

The generator-evaluator cycle is the most-repeated multi-state pattern in the entire codebase. A bug in the Playwright invocation or rubric scoring currently requires fixing 5 separate files. The tagged-JSON parsing pattern is identical across 3 loops but differed only in the tag string — a clear case for parameterization.

## Proposed Solution

1. Design `generator-evaluator` sub-loop with parameterized inputs
2. Extract the sub-loop to `loops/oracles/generator-evaluator.yaml`
3. Convert all 5 harness loops to delegate to the sub-loop
4. Add `parse_tagged_json` fragment to `loops/lib/common.yaml`
5. Convert all 3 integration loops to use the fragment
6. Run `ll-loop validate` on all modified loops and the new sub-loop
7. Run `python -m pytest scripts/tests/ -v --tb=short`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Sub-loop Composition Mechanism

The FSM engine supports sub-loop invocation via the `loop:` key on a `StateConfig` (`scripts/little_loops/fsm/schema.py:384`). The executor's `_execute_sub_loop()` method (`executor.py:494`) handles the full lifecycle:

1. **Resolution** — interpolates the loop name, resolves to file path via `resolve_loop_path()` (`cli/loop/_helpers.py:820`)
2. **Loading** — calls `load_and_validate()` which resolves `from:` inheritance, `flow:` shorthand, and `fragment:` references before parsing into `FSMLoop`
3. **Context binding** — `with:` bindings merge parent expressions into child parameters (with declared defaults for unbound optional params); or `context_passthrough: true` passes all parent context + captured outputs
4. **Execution** — creates a child `FSMExecutor` sharing the parent's `action_runner` and circuit breaker; clamps child timeout to parent's remaining wall-clock budget
5. **Routing** — child `done` terminal → `on_yes`; other terminal → `on_no`; error → `on_error` (or `on_no` if unset)

Validation check: `_validate_with_bindings()` (`validation.py:297`) cross-validates `with:` keys against the child loop's declared `parameters:` block. Required-but-unbound parameters are flagged as ERROR. Unknown keys are ERROR.

The existing oracle sub-loop (`oracles/oracle-capture-issue.yaml`) provides a template to model after: uses `context:` for parameter defaults, `on_handoff: spawn`, `max_iterations: 1`. The `generator-evaluator` differs in being iterative (multi-pass generate→evaluate→score→iterate).

#### Fragment Resolution Pipeline

Fragments are resolved at **parse time** (before the FSM engine sees the data) in `fragments.py:resolve_fragments()`:

1. **Load imports** — `import:` paths resolved relative to the loop file directory; later imports override earlier for same name
2. **Merge local** — loop's own `fragments:` block takes precedence over imports
3. **Expand references** — for each state with `fragment: <name>`, deep-merge the fragment into the state (fragment is base, state fields override), then consume the `fragment:` key
4. **Strip metadata** — `description` on a fragment is stripped before merge (metadata-only, not a state field)

Key implication for the `parse_tagged_json` fragment design: fragment fields containing `${context.json_tag}` are resolved at runtime via `interpolate()` — no special fragment-scoped context namespace is needed. The fragment provides `action_type: shell` and the `action:` heredoc; callers supply `context.json_tag` and the evaluate/routing fields.

The expected behavior section's fragment definition (python3 one-liner) shifts the existing heredoc pattern (`python3 << 'PYEOF' ... PYEOF` with `reversed()` scanning) to a simpler stdin-based approach. The original heredoc pattern scans lines in **reverse** for the tagged last line; the proposed stdin approach scans **forward** for `'${context.json_tag}:' in line`. Both are equivalent for single-match scenarios, but the forward-scan version is simpler and avoids the heredoc boundary syntax that complicates YAML embedding (no `<< 'PYEOF'` delimiter that interacts with YAML indentation).

#### Generator-Evaluator Variation Analysis

All 5 harness loops share the `generate → evaluate (Playwright) → score (LLM rubric) → iterate` cycle. The variations that must be parameterized:

| Feature | html-website-generator | svg-image-generator | html-anything | hitl-md | hitl-compare |
|---------|----------------------|---------------------|---------------|---------|--------------|
| Pre-generate states | `plan` | `init`→`plan` | `init`→`plan` | `init`→`segment` | `init`→`identify`→`prune` |
| Run dir source | `${context.run_dir}` | `${captured.run_dir.output}` | `${captured.run_dir.output}` | `${captured.run_dir.output}` | `${captured.run_dir.output}` |
| Pass threshold | `${context.pass_threshold}` (dfl 6) | `${context.pass_threshold}` (dfl 6) | `${context.pass_threshold}` (dfl 7) | Hardcoded per-criterion | Hardcoded per-criterion |
| Criteria count | 4 (weighted avg) | 4 (weighted avg) | Dynamic from rubric.md | 6 (individual thresholds) | 5 (individual thresholds) |
| Evaluate `on_error` | (unset) | `generate` | `score` | `generate` | `score` |
| Evaluate `on_no` | `generate` | `generate` | `score` | `score` | `score` |
| Score `on_error` | (unset) | `diagnose` | `diagnose` | `failed` | `failed` |
| Max iterations | 30 | 20 | 20 | 20 | 20 |
| Timeout | 14400s | 7200s | 7200s | 7200s | 7200s |

The sub-loop interface must abstract over: (a) whether run_dir comes from `context.` or `captured.`, (b) whether pass_threshold is global or per-criterion, (c) whether criteria are fixed or dynamic, (d) evaluate error routing behavior, (e) post-score terminal states (some have `diagnose`/`failed`/`finalize`). The pre-generate states (plan, segment, identify, prune) stay in the parent wrappers — they are NOT part of the extracted cycle.

The Playwright `evaluate` state is structurally identical across all 5 loops — only the file URL path and `on_error` target differ. The `score` state varies only in the rubric text (criteria names, weights, thresholds) and `on_error` target.

#### Tagged-JSON Parsing Pattern

All 3 integration loops share an identical algorithm:
1. `reversed(output.split('\n'))` — scan lines in reverse for the tagged last line
2. `line.startswith(tag)` — match the tag prefix
3. `line[len(tag):]` — strip prefix to get JSON payload
4. `json.loads(found)` — parse and validate
5. `print(json.dumps({...}))` — re-emit clean JSON to stdout
6. Evaluate via `output_json` with `path: ".count"`, `operator: gt`, `target: 0`

Tag strings per loop: `ENUMERATE_JSON:` (adopt-third-party-api, integrate-sdk), `ASSUMPTIONS_JSON:` (assumption-firewall).

All three also share an identical `flatten_targets` state that converts the JSON targets list to a comma-separated string for the `ready-to-implement-gate` sub-loop — a separate candidate for future fragment extraction.

## Integration Map

### Files to Modify
- `loops/oracles/generator-evaluator.yaml` — new sub-loop
- `loops/html-website-generator.yaml` — convert to thin wrapper
- `loops/svg-image-generator.yaml` — convert to thin wrapper
- `loops/html-anything.yaml` — convert to thin wrapper
- `loops/hitl-md.yaml` — convert to thin wrapper
- `loops/hitl-compare.yaml` — convert to thin wrapper
- `loops/lib/common.yaml` — add `parse_tagged_json` fragment
- `loops/adopt-third-party-api.yaml` — convert parse_enumeration state
- `loops/integrate-sdk.yaml` — convert parse_enumeration state
- `loops/assumption-firewall.yaml` — convert extract_assumptions state
- `loops/lib/cli.yaml` — add `ll_commit` fragment (absorbed from ENH-1774)
- `loops/lib/harness.yaml` — add `playwright_screenshot` fragment (absorbed from ENH-1774; new file, does not exist yet)
- `loops/dead-code-cleanup.yaml` — convert `commit` state to use `ll_commit` fragment (absorbed from ENH-1774)
- `loops/test-coverage-improvement.yaml` — convert `commit` state to use `ll_commit` fragment (absorbed from ENH-1774)
- `loops/backlog-flow-optimizer.yaml` — convert `commit` state to use `ll_commit` fragment (absorbed from ENH-1774)
- `loops/issue-staleness-review.yaml` — convert `commit` state to use `ll_commit` fragment (absorbed from ENH-1774)
- `loops/docs-sync.yaml` — convert `commit` state to use `ll_commit` fragment (absorbed from ENH-1774)
- `loops/incremental-refactor.yaml` — convert `commit_step` state to use `ll_commit` fragment (absorbed from ENH-1774; differs structurally: uses `slash_command` not `prompt`, state named `commit_step` not `commit`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop_cmd.py` — `ll-loop validate` must resolve oracle sub-loops and new fragment
- `scripts/little_loops/fsm/executor.py:494` — `_execute_sub_loop()` resolves, loads, and runs child FSMs; `with:` bindings merge parent context into child parameters
- `scripts/little_loops/fsm/fragments.py:64` — `resolve_fragments()` expands `fragment:` references at parse time via deep-merge; `resolve_inheritance()` at line 147 handles `from:` templates
- `scripts/little_loops/fsm/validation.py:1164` — `load_and_validate()` calls fragment resolution before `FSMLoop.from_dict()`; `_validate_with_bindings()` cross-validates sub-loop `with:` keys against child `parameters:`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py` — imports `FSMExecutor, ExecutionResult`; affected if sub-loop execution lifecycle changes
- `scripts/little_loops/extension.py` — imports `FSMExecutor` (TYPE_CHECKING guard); affected if executor interface changes
- `scripts/little_loops/doc_counts.py` — `is_runnable_loop()` used for loop counting; new oracle sub-loop must be recognized
- `scripts/little_loops/cli/loop/testing.py` — imports `DefaultActionRunner, SimulationActionRunner, FSMExecutor`; affected if executor interfaces change
- `scripts/little_loops/fsm/__init__.py` — re-exports `FSMExecutor`, `load_and_validate`, `StateConfig`, `FSMLoop` in `__all__`; no changes needed but awareness required
- `scripts/little_loops/cli/loop/_helpers.py:820` — `resolve_loop_path()` resolves sub-loop names to file paths; new `oracles/generator-evaluator.yaml` resolves via built-in path
- `scripts/little_loops/cli/loop/lifecycle.py:440,586` — calls `resolve_loop_path()` during lifecycle operations; path-agnostic, no changes needed

### Similar Patterns
- `svg-textgrad.yaml` — may also use generator-evaluator pattern; evaluate for conversion
- `loops/oracles/oracle-capture-issue.yaml` — existing oracle sub-loop to model after; uses `context:` block for parameter defaults, `on_handoff: spawn`, `max_iterations: 1`
- `loops/loop-router.yaml:334` — `dispatch` state demonstrates `loop:` + `with:` + `capture:` + `on_yes/on_no/on_error` routing
- `loops/outer-loop-eval.yaml:55` — `run_sub_loop` state demonstrates the same `loop:` + `with:` pattern
- `loops/lib/apo-base.yaml` — template inheritance via `from:` + `states:` deep-merge (not applicable here, but shows the composition spectrum)

### Tests
- `scripts/tests/test_builtin_loops.py` — per-loop structural test classes: `TestHtmlWebsiteGeneratorLoop:2640`, `TestSvgImageGeneratorLoop:2718`, `TestHtmlAnythingLoop:3130`, `TestHitlCompareLoop:3302`, `TestHitlMdLoop:3467`, `TestAssumptionFirewallLoop:3826`, `TestAdoptThirdPartyApiLoop:3878`, `TestIntegrateSdkLoop:3923`
- `scripts/tests/test_fsm_fragments.py` — fragment resolution tests; class `TestResolveFragmentsImport` validates import order and override semantics
- `scripts/tests/test_fsm_executor.py` — executor tests including sub-loop execution
- `scripts/tests/test_fsm_validation.py` — validation tests including sub-loop parameter cross-validation
- `scripts/tests/test_fsm_inheritance.py` — inheritance/template composition tests

_Wiring pass added by `/ll:wire-issue` — tests that will need updating:_

- `scripts/tests/test_fsm_fragments.py:TestCommonYamlNewFragments:523` — needs `parse_tagged_json` presence test added
- `scripts/tests/test_fsm_fragments.py:TestCliYamlFragments:824` — needs `ll_commit` fragment test added; `test_all_fragments_are_shell_type:879` and `test_all_fragments_have_exit_code_evaluate:886` iterate ALL fragments and will assert on new `ll_commit`
- `scripts/tests/test_fsm_fragments.py:TestDescriptionStrippedFromFragments:978` — `test_all_common_yaml_fragments_have_description:1068` and `test_all_cli_yaml_fragments_have_description:1082` require `description:` on every new fragment
- `scripts/tests/test_fsm_fragments.py` — **new test class needed** for `playwright_screenshot` fragment in the new `lib/harness.yaml` library (follow `TestCommonYamlNewFragments:523` pattern)
- `scripts/tests/test_builtin_loops.py` — **new test class needed** `TestGeneratorEvaluatorOracle` for `oracles/generator-evaluator.yaml` (follow `TestReadyToImplementGateLoop:3779` pattern for sub-loop structure, or `TestRefineToReadyIssueSubLoop:605` for parameter+context assertions)
- `scripts/tests/test_builtin_loops.py` — **5 harness loop test classes will need significant restructuring** when `generate`/`evaluate`/`score` states are deleted and replaced with `loop:` delegation: `TestHtmlWebsiteGeneratorLoop:2640`, `TestSvgImageGeneratorLoop:2718`, `TestHtmlAnythingLoop:3130`, `TestHitlCompareLoop:3302`, `TestHitlMdLoop:3467`
- `scripts/tests/test_builtin_loops.py` — **6 ll_commit target loops have no dedicated test classes** (only generic coverage from `TestBuiltinLoopFiles`); minimal structural tests should be added: `dead-code-cleanup.yaml`, `test-coverage-improvement.yaml`, `backlog-flow-optimizer.yaml`, `issue-staleness-review.yaml`, `docs-sync.yaml`, `incremental-refactor.yaml`
- `scripts/tests/test_builtin_loops.py` — 3 integration loop test classes (`TestAssumptionFirewallLoop:3826`, `TestAdoptThirdPartyApiLoop:3878`, `TestIntegrateSdkLoop:3923`) do NOT assert on action content of parse states → likely will NOT break from fragment conversion, but verify
- `scripts/tests/test_ll_loop_commands.py` — subdirectory loop listing tests (lines 400-485) must include new `oracles/generator-evaluator.yaml`
- `scripts/tests/test_doc_counts.py` — `test_oracle_capture_issue_is_runnable:122` shows the pattern; may need a corresponding `test_generator_evaluator_is_runnable` assertion

### Documentation
- `skills/create-loop/reference.md` — sub-loop documentation with `context_passthrough` and verdict aliases
- `docs/guides/LOOPS_GUIDE.md` — loop authoring guide with generator-evaluator architecture and fragment tables

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md:1658` — mandates evaluate `on_no` routing rules; references `context_passthrough`, `loop:`, `with:`, `parameters:`, fragment composition
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:743-744` — references `html-website-generator` and `svg-image-generator` as GAN-style harness examples; needs updating after thin-wrapper conversion
- `docs/claude-code/harness-design-long-running-apps.md:57` — references generator-evaluator architecture
- `docs/reference/API.md` — references `context_passthrough`, `StateConfig`; may need fragment table updates
- `docs/reference/loops.md` — may need fragment table and sub-loop listing updates
- `docs/reference/CONFIGURATION.md:527` — references `glyphs.sub_loop` badge; awareness but no change needed
- `docs/ARCHITECTURE.md:112` — references `loops/` directory composable as sub-loops; awareness but no change needed
- `skills/create-loop/loop-types.md:1330,1341` — `context_passthrough` usage examples; awareness but no change needed
- No user-facing docs changes needed

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:815-847` — `loops` property with `loops_dir` and `glyphs.sub_loop`; no changes needed for sub-loop or fragment additions (existing schema fully supports `loop:`, `with:`, `context_passthrough`)
- `scripts/little_loops/fsm/schema.py:384-386` — `StateConfig.loop`, `.context_passthrough`, `.with_` fields already exist; `ParameterSpec:180-220` already sufficient for sub-loop parameter contracts
- `scripts/little_loops/fsm/validation.py:101-133` — `KNOWN_TOP_LEVEL_KEYS` already includes `fragments`, `import`, `from`, `flow`, `parameters`, `state_defs`; no new top-level keys needed

## Implementation Steps

1. **Design sub-loop interface** — Declare `parameters:` on the new sub-loop (following the pattern in `oracles/oracle-capture-issue.yaml` and `recursive-refine.yaml:19-23`). Required params: `run_dir` (path), `generate_prompt` (string), rubric criteria list with weights/thresholds. Optional: `pass_threshold` (number, default 6), `max_iterations` (number, default 20), `timeout` (number, default 7200). Output: captured critique and final screenshot path.
2. **Extract `generator-evaluator` sub-loop** to `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — Compose the evaluate state from the `playwright_screenshot` fragment (ENH-1774 scope addition; `loops/lib/harness.yaml`). Use `from: lib/harness` or `import:` + `fragment:` to avoid inlining Playwright logic. Define `on_handoff: spawn`. The sub-loop's internal states: `generate` (prompt) → `evaluate` (shell: playwright_screenshot fragment) → `score` (prompt: LLM rubric, `output_contains: "ALL_PASS"`) → iterate back to `generate` on no, terminal `done` on yes.
3. **Add `parse_tagged_json` fragment** to `scripts/little_loops/loops/lib/common.yaml` — Add under the `fragments:` block alongside existing `shell_exit`, `retry_counter`, `llm_gate`, `with_rate_limit_handling`, `with_throttle`, `numeric_gate`. Fragment provides `action_type: shell` and the python3 stdin-based parser. Callers supply `context.json_tag` and the evaluate/routing fields.
4. **Convert 5 harness loops** to thin wrappers — Each wrapper keeps its pre-generate states (plan/segment/identify/prune) and prepends a `loop:` state that delegates to `oracles/generator-evaluator` with `with:` bindings for its specific rubric, threshold, and run_dir. Remove the inline `generate`, `evaluate`, and `score` states. Model after `loop-router.yaml:334` (`dispatch` state) and `outer-loop-eval.yaml:55` (`run_sub_loop` state). Files: `html-website-generator.yaml`, `svg-image-generator.yaml`, `html-anything.yaml`, `hitl-md.yaml`, `hitl-compare.yaml`.
5. **Convert 3 integration loops** to use `parse_tagged_json` fragment — Replace the inline `python3 << 'PYEOF' ... PYEOF` heredoc in each parse state with `fragment: parse_tagged_json`. Set `context.json_tag` to the appropriate tag string (`ENUMERATE_JSON` or `ASSUMPTIONS_JSON`). The evaluate/routing fields stay on the state (fragment only provides action_type + action). Files: `adopt-third-party-api.yaml:58` (`parse_enumeration`), `integrate-sdk.yaml:117` (`parse_enumeration`), `assumption-firewall.yaml:53` (`parse_assumptions`).
6. **Validate all loops** — `ll-loop validate scripts/little_loops/loops/oracles/generator-evaluator.yaml` and each modified parent. Validation checks include: `with:` key mismatch detection (`validation.py:331-341`), required parameter binding (`validation.py:344-354`), fragment resolution (`fragments.py:64`), unreachable state warnings (`validation.py:837-846`). Fix any ERROR-severity issues.
7. **Run regression suite** — `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_fragments.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_validation.py -v --tb=short`. Verify all 8 modified loops' test classes pass, fragment resolution tests pass, and executor sub-loop tests pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Create `playwright_screenshot` fragment** in `scripts/little_loops/loops/lib/harness.yaml` — New fragment library file (does not exist yet). Fragment provides `action_type: shell` with the Playwright screenshot command extracted from the 5 harness loops. The `generator-evaluator` sub-loop's `evaluate` state composes from this fragment. Callers supply the file URL path via context. Follow the fragment definition pattern in `lib/common.yaml` (description + action_type + action + evaluator). The `_BUILTIN_LOOPS_DIR` constant at `fragments.py:38` resolves to `scripts/little_loops/loops/`, so `import: lib/harness.yaml` in a loop YAML resolves to `scripts/little_loops/loops/lib/harness.yaml` via the fallback at `fragments.py:96-98`.

9. **Create `ll_commit` fragment** in `scripts/little_loops/loops/lib/cli.yaml` — Add under the existing `fragments:` block alongside `ll_auto`, `ll_check_links`, `ll_issues_list`, etc. Fragment provides `action_type: prompt` with a parameterized `/ll:commit` call. Note: `incremental-refactor.yaml` differs structurally from the other 5 targets — uses `slash_command` action_type and state named `commit_step` not `commit`. The fragment must handle both, or `incremental-refactor.yaml` overrides action_type at the state level via deep-merge (fragment provides base, state fields override). The fragment MUST have a `description:` field (enforced by `TestDescriptionStrippedFromFragments.test_all_cli_yaml_fragments_have_description:1082` in `test_fsm_fragments.py`). The `test_all_fragments_are_shell_type:879` and `test_all_fragments_have_exit_code_evaluate:886` tests iterate ALL cli.yaml fragments — verify `ll_commit` passes both.

10. **Convert 6 loops to use `ll_commit` fragment** — Replace inline commit states with `fragment: ll_commit` in: `dead-code-cleanup.yaml:94-99`, `test-coverage-improvement.yaml:198-204`, `backlog-flow-optimizer.yaml:126-131`, `issue-staleness-review.yaml:67-72`, `docs-sync.yaml:57-62`, `incremental-refactor.yaml:34-37`. The first 5 use `action_type: prompt` with prose wrapping; `incremental-refactor.yaml` uses `action_type: slash_command` with literal `"/ll:commit"` — handle the structural variance at the state override level.

11. **Update `test_builtin_loops.py` harness loop tests** — `TestHtmlWebsiteGeneratorLoop:2640`, `TestSvgImageGeneratorLoop:2718`, `TestHtmlAnythingLoop:3130`, `TestHitlCompareLoop:3302`, `TestHitlMdLoop:3467` all assert on `generate`, `evaluate`, `score` state existence, action content, evaluator types, and routing. These tests will break when those states are replaced by `loop:` delegation. Restructure each test class to assert: (a) pre-generate states retained, (b) correct `loop:` target (`oracles/generator-evaluator`), (c) correct `with:` bindings for rubric/threshold/run_dir, (d) correct routing from the delegating state (on_yes → done/finalize, on_no → retry/failed). Follow the delegation-testing pattern from `TestAssumptionFirewallLoop:3840` (`test_run_gate_delegates_to_ready_to_implement_gate`).

12. **Add new test classes** — (a) `TestGeneratorEvaluatorOracle` in `test_builtin_loops.py` following `TestReadyToImplementGateLoop:3779` (compact structural: states, evaluators, terminals, routing); (b) `parse_tagged_json` fragment test in `test_fsm_fragments.py` following `TestCommonYamlNewFragments:523` pattern; (c) `playwright_screenshot` fragment test class in `test_fsm_fragments.py` for the new `lib/harness.yaml` library (verify fragment exists, correct action_type, resolves from file); (d) minimal structural test classes for the 6 ll_commit target loops (currently only generic coverage from `TestBuiltinLoopFiles`).

13. **Update documentation** — (a) `docs/guides/LOOPS_GUIDE.md` — add `parse_tagged_json`, `ll_commit`, and `playwright_screenshot` to fragment tables; add `generator-evaluator` to oracle sub-loop listing; (b) `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:743-744` — update references from inline harness loops to the new thin-wrapper + sub-loop architecture; (c) `skills/create-loop/reference.md` — add new fragments to fragment catalog; (d) `docs/reference/loops.md` — update fragment and sub-loop tables; (e) `docs/generalized-fsm-loop.md:1658` — verify the evaluate routing rule still applies after sub-loop extraction.

14. **Extended validation** — `ll-loop validate` on all 6 ll_commit target loops after conversion. Verify `ll-loop fragments cli` and `ll-loop fragments common` list the new fragments. Verify `ll-loop show oracles/generator-evaluator --resolved` displays the internal states. Verify sub-loop resolution: `resolve_loop_path("oracles/generator-evaluator", ...)` resolves to `scripts/little_loops/loops/oracles/generator-evaluator.yaml`.

15. **Full regression** — `python -m pytest scripts/tests/ -v --tb=short` — verify no regressions across all test files (not just the subset in step 7). Pay special attention to: `test_fsm_fragments.py` (fragment iteration tests may break), `test_ll_loop_commands.py:400-485` (subdirectory listing must include new oracle), `test_doc_counts.py` (runnable loop count may need updating).

## Note on Scope Absorption from ENH-1774

The `ll_commit` fragment (6 loops) and `playwright_screenshot` fragment (5 harness loops → 1 sub-loop) were absorbed from ENH-1774 (Wave 1) during `/ll:audit-issue-conflicts` conflict resolution. Implementation steps 8-10, 12c-12d, and the 8 files added to Files to Modify cover this absorbed scope. The 6 loops that inline `/ll:commit` but are explicitly NOT converted in this wave: `issue-discovery-triage.yaml`, `eval-driven-development.yaml`, `greenfield-builder.yaml`, `sprint-build-and-validate.yaml`, `issue-refinement.yaml` — these are candidate targets for future waves (ENH-1777 or later).

## Scope Boundary with ENH-1776 (Wave 3)

The `generator-evaluator` sub-loop's internal `score` state MUST be designed as a single identifiable target for ENH-1776's `ll_rubric_score` fragment extraction. The `parse_tagged_json` fragment's interface (context variable name `json_tag`, action type `shell`, output shape) becomes a contract that ENH-1776's `enumerate-prove-flow` sub-loop will consume via `fragment: parse_tagged_json`. Coordinate with ENH-1776 implementation to avoid breaking these forward-dependencies.

## API/Interface

N/A — Internal loop composition interfaces only. Sub-loop parameters and fragment YAML contract are detailed in Expected Behavior.

## Success Metrics

- `generator-evaluator` sub-loop eliminates 5 duplicate generate→evaluate→score→iterate cycles
- `parse_tagged_json` fragment eliminates 3 duplicate python3 heredoc parsing states
- `playwright_screenshot` fragment eliminates 5 duplicate Playwright screenshot implementations
- `ll_commit` fragment eliminates 6 duplicate commit-state implementations
- New sub-loop passes `ll-loop validate` independently
- All 14 modified loops pass `ll-loop validate` (5 harness + 3 integration + 6 ll_commit targets)
- Test suite passes with no regressions (including new fragment tests and restructured harness loop tests)

## Scope Boundaries

- Sub-loop extraction and fragment addition only — no behavioral changes to the generate/evaluate/score cycle
- The sub-loop is an oracle (called by parent loops), not a standalone runnable loop
- Only the listed loops; `svg-textgrad.yaml` conversion is out of scope for this wave

## Impact

- **Priority**: P3 — High ROI but non-urgent; significant deduplication but no user-facing impact
- **Effort**: Medium — Sub-loop extraction requires careful interface design to avoid breaking 5 callers
- **Risk**: Medium — Sub-loop extraction is the most complex refactoring in the epic; the 5 harness loops have subtle differences that must be parameterized correctly
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Loop composition and sub-loop delegation |
| guidelines | .claude/CLAUDE.md | Loop authoring conventions, meta-loop design rules |

## Labels

`enhancement`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-29_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- Wide enumeration: 18+ files touched across loops, tests, docs, and lib — high chance of missing a conversion site or introducing a reference error
- Interface design risk: the generator-evaluator sub-loop must abstract over 5 callers with non-trivial variations in pass_threshold semantics (global vs. per-criterion), run_dir sourcing (context vs. captured), and error routing (different on_error targets). Design errors cascade to all 5 wrappers
- Test gap: 6 ll_commit target loops have no dedicated test classes — regressions in these loops may go undetected. New test classes must be added for generator-evaluator, playwright_screenshot fragment, and the 6 ll_commit targets
- Co-deliverable ordering: implement tests first so the validation chain is in place before loop refactoring — lib/harness.yaml must be created before the sub-loop can validate

## Session Log
- `/ll:confidence-check` - 2026-05-29T19:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad84c1f4-e1cb-4d1e-9db8-e1661e645a49.jsonl`
- `/ll:refine-issue` - 2026-05-29T06:15:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86848890-e72e-4e0f-b94e-c336729af630.jsonl`
- `/ll:format-issue` - 2026-05-29T01:15:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29882a14-54b1-4f76-8bb9-fe34f236114f.jsonl`
- `/ll:capture-issue` - 2026-05-29T01:01:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17b05161-9ff0-48f9-baaf-69470f937b48.jsonl`
- `/ll:wire-issue` - 2026-05-29T19:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/<session>.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-28): The `generator-evaluator` sub-loop embeds rubric scoring (`ll_rubric_score` equivalent) as part of its evaluate-score-iterate cycle. ENH-1776 (Wave 3) extracts `ll_rubric_score` as a standalone fragment — it MUST target this sub-loop's internal `score` state rather than the 5 parent wrapper loops, since those wrappers no longer contain inline rubric states after Wave 2. The `parse_tagged_json` fragment and Wave 3's `enumerate-prove-flow` share `adopt-third-party-api.yaml` and `integrate-sdk.yaml` as integration targets; the flow MUST compose from the fragment rather than inlining its own parse logic.

---

## Scope Addition

**Source**: Merged from ENH-1774 (Wave 1) during `/ll:audit-issue-conflicts` conflict resolution.

The following fragments from ENH-1774 are now part of this wave:

- **`ll_commit` fragment** in `loops/lib/cli.yaml` — eliminates 6 duplicate commit-state implementations across `dead-code-cleanup.yaml`, `test-coverage-improvement.yaml`, `backlog-flow-optimizer.yaml`, `issue-staleness-review.yaml`, `docs-sync.yaml`, and `incremental-refactor.yaml`.
- **`playwright_screenshot` fragment** in `loops/lib/harness.yaml` — eliminates 5 duplicate Playwright screenshot implementations. The `generator-evaluator` sub-loop MUST compose from this fragment rather than inlining its own screenshot logic.

The Integration Map, Implementation Steps, and caller conversion plan from ENH-1774 are absorbed here.

## Status

**Open** | Created: 2026-05-28 | Priority: P3
