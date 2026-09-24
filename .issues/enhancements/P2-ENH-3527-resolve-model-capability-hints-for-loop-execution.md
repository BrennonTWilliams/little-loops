---
id: ENH-3527
title: Resolve model capability hints for loop execution
type: ENH
priority: P2
status: open
discovered_date: '2026-09-23'
labels:
- multi-host
- loops
blocks:
- ENH-3547
- ENH-3548
---

# Resolve model capability hints for loop execution

## Summary

Introduce a closed `model_hint` vocabulary for loop states and evaluator defaults, resolved against the actual execution backend through built-in defaults plus a per-host `model_hints` (under `orchestration`) config override. Preserve existing literal model IDs and CLI aliases. This issue delivers loop execution first; skill and agent frontmatter adaptation is ENH-3533 because accepting a key does not establish that the host will honor it.

## Current Behavior

- `StateConfig.model` overrides the run model for CLI actions. Evaluators use `state.model or fsm.llm.model`; SDK/batch actions use `state.model or run_model or fsm.llm.model`.
- `LLMConfig.model` defaults to `DEFAULT_LLM_MODEL` (`sonnet`). Its deserializer currently supplies that default immediately; a hint-only configuration must not acquire a conflicting explicit model.
- CLI runners generally pass aliases through unchanged. `resolve_model_alias` is called by `advisor.rank_model` and `build_anthropic_request`, not by CLI builders. The API path requires concrete Anthropic IDs.
- `CodexRunner.build_streaming` and its blocking path both forward `--model` (BUG-3529, done; `codex exec` and `codex exec resume` accept it). Opencode/pi are unconfigured runtime runners. A mapping entry alone cannot establish model-selection support.
- Claude skills and agents are served natively without an LL model-resolution step. Codex agent TOML is generated ahead of execution, and `emit_agent` copies `model` from frontmatter. `main_verify_skills` checks file sizes, not model selection.
- No shipped loop under `scripts/little_loops/loops/` declares `model:` today, so no built-in loop exercises per-state model selection on any host.
- `fsm-loop-schema.json` gives `llm.model` a JSON `default` of `claude-sonnet-4-20250514`, which is stale versus `DEFAULT_LLM_MODEL` (`sonnet`) and would be injected beside a hint by any default-applying JSON-schema tool.

## Expected Behavior

A supported loop execution path resolves an optional hint into a backend-valid model selection before dispatch. Unsupported hint selections fail explicitly before a subprocess/API request rather than silently using another model. Moving a hint-bearing loop between supported backends requires no artifact edit. Runs without hints retain their current precedence, argv, and defaults.

## Design

### Vocabulary

| Hint | Selection intent |
|------|------------------|
| `coding` | General implementation, editing, and tool-driven development |
| `reasoning` | Difficult analysis, planning, or review where reasoning capability takes priority |
| `burst` | Short, bounded classification or extraction where responsiveness and low resource use take priority |

These are selection preferences, not guarantees of quality, latency, price, or reasoning effort. Multiple hints may map to the same model. `effort` remains independent. A `burst` selection on a generation state receives the same advisory scrutiny as the existing `haiku-gen` guidance; vocabulary errors are validation errors.

### Declaration and precedence

Add optional `model_hint` to `StateConfig` and `LLMConfig`; do not overload `model` or existing CLI `--model` strings with hint semantics. At either declaration level, explicitly supplying both `model` and `model_hint` is an error. Unknown values, empty hints, and hints on non-LLM states are errors.

**Applicability.** A state-level hint follows the same reach as `state.model` does today: it applies to a prompt-mode action (`executor.py:2658`, `action_mode == "prompt"`) and to an LLM evaluator (`executor.py:3174,3221`). A state is an "LLM state" if it has either. A shell action with an `llm_structured` evaluator is valid, and its hint governs only the evaluator. A state with neither is a validation error. When a state has both a prompt action and an LLM evaluator, the one declaration is resolved separately for each: the action against the streaming operation of its effective path, the evaluator against blocking. The two may resolve to different model strings.

Select a model declaration before resolving it, preserving the existing precedence by execution path:

| Path | Highest to lowest precedence |
|------|------------------------------|
| CLI action | State model-or-hint → run `--model` → host default |
| Evaluator | State model-or-hint → effective `llm` model-or-hint → existing evaluator default |
| SDK/batch action | State model-or-hint → run `--model` → effective `llm` model-or-hint → existing API default |

`--llm-model` replaces the `llm` declaration and clears an inherited hint. A run `--model` does not gain new precedence over state declarations or evaluator defaults. A hint in `llm` does not become a new CLI-action default.

Preserve the distinction between an omitted model and an explicitly supplied model during parsing and serialization. Apply `DEFAULT_LLM_MODEL` only when no declaration exists at the relevant fallback level; never inject it beside `model_hint`. Hint-only round trips must stay hint-only. Existing construction sites and no-hint behavior must remain compatible.

### Resolve against the effective backend

Resolve `_resolve_request_path` first, including SDK/batch downgrades. Then resolve the selected declaration against that path:

- CLI execution uses the selected runner and its operation (`streaming` or `blocking`). Hint mappings may return host-supported aliases or concrete IDs. Existing literal values pass through unchanged; do not introduce `resolve_model_alias` into CLI dispatch.
- SDK/batch execution uses the Anthropic mapping and concrete-ID resolution, regardless of the configured CLI host. A configured Codex/Gemini host must not cause a non-Anthropic model ID to reach `build_anthropic_request`.
- A downgrade to CLI resolves the original declaration afresh for that runner. Do not reuse a model already resolved for another backend.
- Keep mappings in the runtime model-selection layer, with explicit operation support and parity checks against the runtime registry. Use one canonical entry for each backend model target; multiple hints can reference it so a rename does not require duplicate ID edits. Reuse the existing Anthropic alias table for its API targets.
- Missing mappings and unsupported operations produce actionable errors naming the hint, backend, and operation. An unknown hint must never return `None` and silently select the host default.

### Hint mapping (decided)

Ship built-in defaults only where the target is verified against this repo's own model tables; every other host resolves through configuration. Lineups on non-Claude hosts change too often, and too few of them are verifiable here, to hard-code.

| Backend key | `coding` | `reasoning` | `burst` | Source |
|-------------|----------|-------------|---------|--------|
| `claude-code` (CLI) | `sonnet` | `opus` | `haiku` | Built-in; host CLI aliases passed through unchanged, as literal values are today |
| `anthropic-api` (SDK/batch) | `MODEL_ALIASES["sonnet"]` | `MODEL_ALIASES["opus"]` | `MODEL_ALIASES["haiku"]` | Built-in; derived at lookup time from `MODEL_ALIASES` so the canonical ID lives in one place. Do not copy concrete IDs into the hint table or docs. `MODEL_ALIASES` is itself stale (`opus → claude-opus-5`, `fable → claude-fable-5`); refreshing it is tracked separately (see Related) and is not a blocker here |
| `codex`, `gemini`, `omp`, `kimi-code`, `qwen` | — | — | — | No built-in default; config only. An unmapped hint on these hosts raises the actionable missing-mapping error |
| `opencode`, `pi` | — | — | — | Not advertised; hints error regardless of config |

**Config override (in scope).** Add `model_hints` (under `orchestration`) to `config-schema.json` and `OrchestrationConfig`:

```json
"orchestration": {
  "model_hints": {
    "codex": { "coding": "<codex-model>", "reasoning": "<codex-model>", "burst": "<small-codex-model>" },
    "claude-code": { "burst": "sonnet" }
  }
}
```

- Keys are runtime backend keys (the `RUNTIME_HOST_CAPABILITIES` host names plus `anthropic-api`); an unknown backend key or hint name is a config validation error. Values are non-empty strings passed through as literals (no nested hint resolution), or `false` to disable.
- JSON-schema shape in `config-schema.json`: `model_hints` is an object with `propertyNames` enumerating the backend keys and `additionalProperties: false`; each backend value is an object with `properties` `coding`/`reasoning`/`burst` and `additionalProperties: false`; each hint value is `{"oneOf": [{"type": "string", "minLength": 1}, {"const": false}]}`. `null` and `true` fail schema validation.
- Per-hint merge over built-in defaults: a host entry may override one hint and inherit the rest. The value `false` disables a built-in mapping for that hint, which makes the hint error on that backend. `null` is **not** the disable sentinel: `config.core.deep_merge` treats `None` in `ll.local.md` as key removal, which would silently restore the built-in default, and a `null` written directly in `ll-config.json` would reach the resolver as a value — the two files would disagree. A `null` value is therefore a config validation error.
- `anthropic-api` values still pass through `resolve_model_alias`, so an alias such as `opus` is valid there.
- Precedence is unchanged: config supplies only the hint → model table; a literal `model:` or run `--model` beats a hint exactly as in the precedence table above.
- `ll-loop validate` resolves each declared hint against the configured host (`orchestration.host_cli` / `LL_HOST_CLI`) and emits a WARNING — not an error, because the host can differ at run time — for any hint that would fail to resolve. It checks every request path the declaration could reach, mirroring `FSMExecutor._resolve_request_path`: the state's own `request_path` override if set, else `orchestration.request_path`; plus the CLI fallback for SDK/batch (downgrade re-resolves for the CLI runner). States that `_resolve_request_path` always downgrades to CLI (action invokes a `/ll:` skill per `_SKILL_INVOKE_RE`, or declares `tools:` — BUG-2831) are checked for CLI only; do not warn about an `anthropic-api` mapping they can never reach. Evaluator hints are checked for the blocking operation, action hints for streaming. The runtime error remains authoritative.

### Supported artifact/host matrix

The implementation must publish a tested matrix, not infer support from a `--model` flag somewhere in a runner.

| Artifact / operation | Delivery requirement |
|----------------------|----------------------|
| Loop CLI actions, Claude/Codex/Gemini/OMP/Kimi/Qwen | Prove each supported runner forwards the resolved selection; mark unsupported combinations explicitly |
| Loop Codex streaming actions | Supported (BUG-3529 done); dispatch test asserts the resolved selection in argv |
| Loop blocking evaluators | Test each runner/operation advertised as supported, including Codex |
| Loop Anthropic SDK/batch | Concrete Anthropic resolution, including foreign configured CLI hosts and CLI downgrade |
| Opencode/pi | Preserve unconfigured-runner behavior; do not advertise hint support |
| Native skills/agents and generated agent files | Deferred to ENH-3533; no portability claim from accepting frontmatter alone |

Do not migrate shipped skills/agents or regenerate mirrors in this issue. ENH-3533 must establish resolution timing (native invocation versus generation), stale generated-file handling after mapping changes, and an executable test for every artifact/host combination it claims to support.

### Lifecycle and model identity

Persist the requested declaration through sub-loop inheritance, detach, and resume rather than replacing it with a resolved ID. Existing override rules continue to apply. Each dispatch resolves against the effective backend and records the hint/literal requested, resolved selection, backend, and operation **in the FSM event stream** (the existing state/action event payloads, as additive `model_requested`, `model_resolved`, `model_backend`, `model_operation` fields) and in the run header. This issue adds no database columns; `usage_events` stays owned by ENH-3528/ENH-3538 and records only observed model identity. Resume may resolve a changed mapping and must make the new selection visible.

Keep the observed model reported by the host separate from requested/resolved selections. Missing host model identity remains unknown; do not label a requested alias as an observed model. Headers may show `hint → resolved selection`, while usage records use observed identity where available. Coordinate this contract with ENH-3528 without introducing a hard dependency: both changes must work independently.

## Acceptance Criteria

- [ ] State and `llm` hints accept exactly `coding`, `reasoning`, and `burst`; explicit model-plus-hint, invalid hints, and inapplicable states fail validation before execution.
- [ ] Schema, parsing, serialization, and direct construction cover omitted, literal-only, and hint-only cases; implicit defaults do not create conflicts or mask hints.
- [ ] Applicability follows `state.model`'s reach: prompt actions and LLM evaluators; shell-action + LLM-evaluator states are valid; states with neither fail validation.
- [ ] `resolve_model_hint` unit tests cover every backend key × hint, unsupported backends (opencode/pi), and disabled or missing mappings; it never returns `None`.
- [ ] Canonical mapping targets avoid duplicate model IDs for hints sharing a target, and runtime-map coverage is checked by `ll-verify-host-map` tests.
- [ ] Until ENH-3547 lands, executing a hint-bearing state fails before dispatch with an explicit not-yet-supported error; no-hint behavior and literal CLI argv are unchanged.
- [ ] Built-in mappings exist only for `claude-code` and `anthropic-api`, with `anthropic-api` targets derived from `MODEL_ALIASES` (no duplicated concrete IDs). `model_hints` (under `orchestration`) is in `config-schema.json` and `OrchestrationConfig`; tests cover per-hint merge over defaults, `false` disabling a built-in hint (via both `ll-config.json` and `ll.local.md`), `null` rejected, unknown backend/hint keys rejected, and a config-only Codex mapping reaching argv.
- [ ] The `llm.model` JSON `default` is removed from `fsm-loop-schema.json`; the fallback to `DEFAULT_LLM_MODEL` is described in its `description` instead, and a JSON/Python parity test covers it.

Moved to split issues: precedence/dispatch/lifecycle/diagnostics/portability-proof criteria → ENH-3547; `ll-loop validate` warnings and documentation → ENH-3548.

## Scope Boundaries

- **In scope (this issue)**: loop state/evaluator declarations, the resolver and its support table, built-in `claude-code`/`anthropic-api` mappings, the `model_hints` (under `orchestration`) config override, and the pre-dispatch not-yet-supported guard.
- **Split out**: ENH-3547 (dispatch wiring, lifecycle preservation, selection diagnostics, portability proof); ENH-3548 (validate-time warnings, documentation).
- **Satisfied prerequisite**: BUG-3529 (Codex streaming `--model` forwarding) is done.
- **Deferred follow-up**: ENH-3533 — native skill/agent hints and generated-agent materialization.
- **Out of scope**: artifact migration; new hint vocabulary; built-in default mappings for non-Claude hosts; hints in advisor/compaction configuration or unrelated CLI commands; new run-level hint flags; automatic cost routing; price tables; changing host-internal model selection or reasoning effort.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — runtime mappings, operation support, resolver, public exports; preserve literal CLI forwarding and existing API alias resolution.
- `scripts/little_loops/fsm/schema.py`, `fsm/fsm-loop-schema.json` — state and `llm` declarations, exclusivity, absent-versus-default handling; align the stale JSON `llm.model` default with Python behavior.
- `scripts/little_loops/fsm/validation/structural_rules.py`, `fsm/validation/evaluator_rules.py` — declaration errors and hint-aware generation guidance.
- `scripts/little_loops/fsm/executor.py`, `fsm/evaluators.py`, `fsm/runners.py`, `subprocess_utils.py` — all dispatch seams, effective-backend ordering, selection/observed-model diagnostics.
- `scripts/little_loops/cli/loop/{run,lifecycle,runner,header,info}.py`, `fsm/persistence.py` — overrides, detach, resume, headers, and serialized intent; inspect persistence before changing its format.
- `scripts/little_loops/cli/verify_host_map.py`, `fsm/__init__.py` — runtime consistency checks and any required public exports.
- `scripts/little_loops/config/orchestration.py` (`OrchestrationConfig`), `scripts/little_loops/config-schema.json` — new hint-mapping config override under `orchestration`; `docs/reference/CONFIGURATION.md`.
- `scripts/little_loops/fsm/validation/` — validate-time resolution WARNING against the configured host.

### Dependent Files and Similar Patterns

- `runner_spec.py`, `advisor.py`, `cli/{harness,advise}.py`, `cli/artifact/`, `issue_manager.py`, `parallel/worker_pool.py` consume existing model APIs; preserve literal semantics without broadening their configuration.
- `StateConfig` optional `effort`/`tamper_guard` fields illustrate round trips. `LLMConfig.model` needs additional omitted/default handling; copying a nullable state field alone is insufficient.
- `adapters/codex.py`, `cli/adapt_agents_for_codex.py`, native `skills/` and `agents/` are follow-up research points, not mandatory edits for this delivery.

### Tests

- `test_fsm_schema.py`, `test_fsm_validation_structural.py`, `test_fsm_validation_evaluator_rules.py` — declarations, JSON/Python parity, invalid/conflicting values, defaults and lint.
- `test_fsm_executor.py`, `test_fsm_evaluators.py`, `test_fsm_runners.py`, `test_ll_loop_execution.py`, `test_ll_loop_parsing.py` — precedence, all dispatch paths, backend downgrade, sub-loops/detach/resume.
- `test_host_runner.py`, `test_host_runner_dispatch.py`, `test_verify_host_map.py`, `conformance/test_host_conformance.py` — supported operation matrix, unchanged literals, map coverage, Anthropic-only API selection.
- `test_fake_host.py`, `test_cli_harness.py`, `test_cli_advise.py`, `test_subprocess_utils.py` — compatibility and requested/resolved/observed identity. Fake-host coverage must assert the forwarded selection rather than accepting an ignored parameter as proof.
- `test_wiring_reference_docs.py` — public API/doc coverage. Adapter/mirror tests belong to the deferred artifact work unless shared changes actually affect them.

### Documentation

`docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/reference/{API,CLI,HOST_COMPATIBILITY}.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, and relevant runtime-map prose in `docs/ARCHITECTURE.md`.

## Implementation Steps

1. Add schema/serialization tests for explicit declarations and the precedence matrix; implement hint fields without changing legacy defaults.
2. Add backend/operation resolution and mapping-coverage tests. Preserve literal CLI aliases and isolate Anthropic ID conversion to its API path. Add `model_hints` (under `orchestration`) (schema, `OrchestrationConfig`, merge over built-in defaults) in the same step.
3. Wire actions and both evaluator dispatch sites after effective-path selection; cover SDK/batch downgrade and unsupported operations before launching requests.
4. Preserve declarations through overrides, sub-loops, detach, and resume. Add requested/resolved/observed diagnostics without fabricating observed identity.
5. Update validation, host-map checks, headers, and the documented support matrix. Keep skill/agent adaptation explicitly deferred.
6. Run focused schema, dispatch, lifecycle, and compatibility tests; then the required local suite and applicable lint/type checks.

## Program Design

### Types

- `ModelHint = Literal["coding", "reasoning", "burst"]`; FSM fields may use `str | None` with runtime validation to match existing schema conventions.
- `model_hint: str | None` — new optional field on both `StateConfig` and `LLMConfig`.
- `model_hints: dict[str, dict[str, str | Literal[False]]]` — new `OrchestrationConfig` field; backend key → hint → model, `False` disables a built-in mapping; `None` is rejected.
- A model declaration represents exactly one explicit literal or hint, or no selection. It must retain omission until fallback selection; choose its concrete dataclass representation without changing existing no-hint public behavior.
- A resolved selection records requested literal/hint, effective backend, operation, and selected model string. Observed model identity is separate and optional.
- Runtime hint mappings reference canonical backend model targets. Operation support is explicit, including unsupported combinations.

### Signatures

- `resolve_model_hint(hint: str, *, backend: str, operation: str, overrides: dict[str, dict[str, str | Literal[False]]] | None = None) -> str` — returns a usable selection or raises a validation/capability error; never returns `None`. `overrides` is the parsed config mapping, merged per hint over the built-in defaults.
  - **`operation` must earn its place.** Since BUG-3529, every supported runner forwards `--model` for both streaming and blocking, so no current backend behaves differently per operation. Keep the parameter only if the per-operation support table is real data that `ll-verify-host-map` checks and that marks opencode/pi (and any future partial runner) unsupported per operation. Otherwise drop it and represent support per backend; the unsupported-selection error then names the hint and backend only.
- `resolve_model_alias(model: str) -> str` — unchanged; remains the Anthropic API alias resolver and the source of `anthropic-api` hint targets.

### Call Path

Declaration selection and backend resolution happen after the effective request path is known:

- `FSMExecutor._resolve_request_path` → `resolve_model_hint` → `build_anthropic_request` (SDK/batch; concrete IDs via `resolve_model_alias`)
- `FSMExecutor._resolve_request_path` → `resolve_model_hint` → `CodexRunner.build_streaming` / `ClaudeCodeRunner.build_streaming` (CLI actions)
- `FSMExecutor._evaluate` → `resolve_model_hint` → `evaluate_llm_structured` / `evaluate` → `resolve_host().build_blocking_json` (evaluators)

Evaluators do not receive `orchestration_config`; they take a plain `model: str` and call `resolve_host()` themselves (`fsm/evaluators.py:1117,1227,1483`). Resolve the hint in `FSMExecutor._evaluate` (today `model=state.model or self.fsm.llm.model` at `executor.py:3174,3221`), where `self.orchestration_config` is available, against the same backend `resolve_host()` will return, and pass the resolved string down. Evaluator signatures stay `model: str`; do not thread config into `evaluators.py`.

Host-observed model identity is recorded separately after dispatch.

## Impact

- **Priority**: P2 — a portability enhancement with no current breakage; no shipped loop declares a model today.
- **Effort**: Medium to high — multiple dispatch and lifecycle paths, with native artifact adaptation explicitly deferred.
- **Risk**: Medium — default injection, precedence, unsupported operations, and backend mismatches can silently select the wrong model.
- **Breaking Change**: No for existing no-hint artifacts; new hint declarations have explicit validation and support constraints.

### Delivery split (applied 2026-09-24)

Split along the three seams, landed in order. The Design sections above stay authoritative for all three issues.

1. **This issue** — declaration + resolver + config: `model_hint` fields, parse/serialize/omission handling, JSON-schema default removal, `resolve_model_hint`, built-in mappings, `orchestration.model_hints`.
2. **ENH-3547** — dispatch + lifecycle + diagnostics: CLI/evaluator/SDK/batch wiring, downgrade re-resolution, sub-loop/detach/resume, event-payload fields, portability proof.
3. **ENH-3548** — `ll-loop validate` warnings, support-matrix docs, `haiku-gen` guidance.

Until ENH-3547 lands, a declared hint parses and validates, but `FSMExecutor` must fail fast before dispatch with an explicit "model_hint dispatch not yet supported" error. A hint-bearing loop authored in between must not run silently on the default model, which would break the no-silent-fallback rule. ENH-3547 removes this guard.

## Verification Notes

Review corrections applied on 2026-09-23: narrowed delivery to loop execution; corrected CLI alias flow; defined vocabulary, precedence, effective-backend resolution, unsupported combinations, lifecycle behavior, and model identity. Reconciled prior research/wiring notes into the directive sections rather than retaining contradictory instructions. Graph corroboration used fresh `codegraph` results for alias callers and direct source inspection. The review's 30 focused existing tests passed; they establish current behavior, not completion of the new acceptance criteria.

Review follow-up on 2026-09-23: reprioritized P0 → P2 and renamed the file to match the narrowed title; decided the hint mapping (built-in for `claude-code`/`anthropic-api` only, `model_hints` (under `orchestration`) override for all hosts); replaced the Codex streaming "unsupported" row with a dependency on BUG-3529 after confirming `codex exec [resume] --model` exists; added validate-time warnings, JSON-default removal, and a portability proof AC; split deferred skill/agent work to ENH-3533.

### Verify pass (superseded)

An earlier verify pass recorded Codex `build_streaming` doing `del model` and BUG-3529 as open. Both are obsolete: BUG-3529 is done and `CodexRunner.build_streaming` forwards `--model` (`host_runner.py` ~L1241). Do not act on the earlier record.

### Pre-implementation review 2026-09-23

BUG-3529 is done: removed the `blocked_by`, and Codex streaming is now a supported row with an argv test. Changed the mapping-disable sentinel from `null` to `false`, because `config.core.deep_merge` removes `None` keys from `ll.local.md`, which would restore the built-in default. Fixed where selection diagnostics live: event payload plus header, no DB columns. Defined which request paths and operations validate-time warnings check.

### Pre-implementation review 2026-09-23 (second pass)

`anthropic-api` targets are now written as `MODEL_ALIASES[...]` lookups, not copied IDs (the table is stale; BUG-3541). Validate-time warnings now honor per-state `request_path` and skip SDK checks for states that always downgrade to CLI (BUG-2831). Evaluator hint resolution belongs in `FSMExecutor._evaluate`, with no config threaded into `evaluators.py`. The `model_hints` JSON-schema shape is now specified, and a delivery split is proposed.

### Pre-implementation review 2026-09-24

Applied the delivery split: this issue keeps declaration, resolver and config; dispatch/lifecycle moves to ENH-3547 and validate/docs to ENH-3548, with a fail-fast guard in between. Defined hint applicability (prompt action and/or LLM evaluator, resolved per operation). Made the resolver's `operation` parameter conditional on a real per-operation support table. The Design sections remain the shared spec for all three issues.

## Related

- ENH-3547, ENH-3548 — split pieces 2 and 3 (blocked by this issue).
- BUG-3541 — `MODEL_ALIASES` `opus`/`fable` targets are superseded IDs; not a blocker.

## Status

**Open** | Created: 2026-09-23 | Priority: P2

## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:55 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:08 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:01:43 - `d1e0cad9-5218-4c39-a990-a91f5f18af0d.jsonl`
- `/ll:wire-issue` - 2026-09-23T23:43:26 - `96fe3651-90ba-4862-a958-697a2df577cc.jsonl`
- `/ll:refine-issue` - 2026-09-23T23:20:19 - `1dd8afb6-deef-4834-bd0a-401f1160db13.jsonl`
- `/ll:format-issue` - 2026-09-23T22:58:54 - `67a10285-a4b7-4192-bd9e-23ac30a3ffd0.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers the hint declaration, resolver, and config slice only. Dispatch/lifecycle wiring belongs to ENH-3547; validate-time warnings, `haiku-gen` guidance, and documentation belong to ENH-3548. Any Integration Map, Implementation Steps, or Files to Modify entries here for those areas are shared spec, not this issue's deliverable. The `operation` parameter of `resolve_model_hint` must be settled here before ENH-3547/ENH-3548 (which hard-code it) start.
