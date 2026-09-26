---
id: ENH-3527
title: Resolve model capability hints for loop execution
type: ENH
priority: P2
status: open
parent: EPIC-3563
epic: EPIC-3563
discovered_date: '2026-09-23'
labels:
- multi-host
- loops
blocked_by:
- BUG-3541
blocks:
- ENH-3547
- ENH-3548
- ENH-3533
confidence_score: 100
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
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

**Applicability.** A state-level hint applies where a model is *actually consumed at runtime*, which is narrower than where `model:` is accepted today. A state is an "LLM state" if it has either:

- a prompt-mode action — `action_type` `prompt` or `slash_command`, or no `action_type` with an action starting `/` (mirror `executor._action_mode`, `executor.py:3427`); or
- an explicit `evaluate.type == "llm_structured"`.

Do **not** reuse `_is_llm_judged` (`fsm/validation/_base.py:173`), which the `model:` WARNING rule uses (`structural_rules.py:470`). It also counts `check_semantic` (not in the evaluator enum) and `advisor_consult` (which uses advisor config), but `evaluate()` forwards `model` only to `llm_structured` (`fsm/evaluators.py:2064`). `contract` and `advisor_consult` ignore the state model. A hint on such a state could never be honored, so it is an ERROR. A shell action with an `llm_structured` evaluator is valid, and its hint governs only the evaluator. A state with neither is a validation error. When a state has both a prompt action and an LLM evaluator, the one declaration is resolved separately for each: the action against its effective request path, the evaluator against the CLI host (see below). The two may resolve to different model strings.

- **Evaluators are CLI-only.** `fsm/evaluators.py` has no SDK/batch path and never reads `request_path`: `evaluate_llm_structured` and `evaluate` always dispatch through `resolve_host().build_blocking_json`. An evaluator hint therefore always resolves against the CLI runner `resolve_host()` returns, even on a `request_path: sdk`/`batch` state. Only a prompt *action* follows `request_path` and can reach `anthropic-api`.
- **Implicit evaluator.** A prompt-mode state with no `evaluate:` block still gets an implicit `evaluate_llm_structured` verdict (`executor.py:3174`). A hint on such a state governs both the action and that implicit verdict. For example, `burst` selects the burst model for the generation and for its verdict.
- **Error, not warning (deliberate).** A literal `model:` on a state with no LLM step is only a WARNING today (`fsm-loop-schema.json` `state.model` description). A `model_hint` there is an ERROR on purpose: hints are new, so no existing loop breaks, and a hint that can never be honored contradicts the no-silent-fallback rule. Do not downgrade it to match `model:`.

Select a model declaration before resolving it, preserving the existing precedence by execution path:

| Path | Highest to lowest precedence |
|------|------------------------------|
| CLI action | State model-or-hint → run `--model` → host default |
| Evaluator (always CLI host) | State model-or-hint → effective `llm` model-or-hint → existing evaluator default |
| SDK/batch action | State model-or-hint → run `--model` → effective `llm` model-or-hint → existing API default |

`--llm-model` replaces the `llm` declaration and clears an inherited hint. This is in scope here: `cli/loop/run.py:190` currently sets only `fsm.llm.model`, so it must also set `fsm.llm.model_hint = None`, or the override produces the forbidden model-plus-hint pair. A loop whose only hint was in `llm` then runs normally, past the fail-fast guard. A run `--model` does not gain new precedence over state declarations or evaluator defaults. A hint in `llm` does not become a new CLI-action default.

Preserve the distinction between an omitted model and an explicitly supplied model during parsing and serialization. Apply `DEFAULT_LLM_MODEL` only when no declaration exists at the relevant fallback level; never inject it beside `model_hint`. Hint-only round trips must stay hint-only. Existing construction sites and no-hint behavior must remain compatible.

**`LLMConfig` representation (decided 2026-09-25).** Keep `model: str = DEFAULT_LLM_MODEL` and add `model_hint: str | None = None`. Do **not** make `model` nullable, because that would ripple through:

- `_resolve_action_model` (`executor.py:3559`, typed `str` and documented as never empty);
- the evaluator call sites `state.model or self.fsm.llm.model` (`executor.py:3174,3221`) feeding `model: str` parameters;
- the header renderers (`run.py:707`, `lifecycle.py:775,854`);
- `info.py:1528`;
- 14 `LLMConfig(...)` construction sites.

Rules:

- **Exclusivity** is checked on the raw mapping: `from_dict` raises, and the structural validator errors, when both `"model"` and `"model_hint"` keys are present. A directly constructed `LLMConfig(model="sonnet", model_hint=…)` cannot be distinguished from the default, which is acceptable.
- **Resolution:** when `model_hint` is set, it wins over `model`. The default `model` value is then inert. ENH-3547 implements this in dispatch.
- **Serialization:** `to_dict` already omits a default `model`, so a hint-only config round-trips hint-only. `to_dict` emits `model_hint` when set.
- `StateConfig.model_hint` is a plain nullable field, like `effort`.
- **`llm.model_hint` with no LLM states:** a WARNING, matching `llm.model`, not an ERROR.

### Resolve against the effective backend

Resolve `_resolve_request_path` first, including SDK/batch downgrades. Then resolve the selected declaration against that path:

- Evaluators always resolve against the CLI runner (see Applicability); the request-path rules below apply to actions.
- CLI execution uses the selected runner. Hint mappings may return host-supported aliases or concrete IDs. Existing literal values pass through unchanged; do not introduce `resolve_model_alias` into CLI dispatch.
- SDK/batch execution uses the Anthropic mapping and concrete-ID resolution, regardless of the configured CLI host. A configured Codex/Gemini host must not cause a non-Anthropic model ID to reach `build_anthropic_request`.
- A downgrade to CLI resolves the original declaration afresh for that runner. Do not reuse a model already resolved for another backend.
- Keep mappings in the runtime model-selection layer, with explicit per-backend support and parity checks against the runtime registry. Use one canonical entry for each backend model target; multiple hints can reference it so a rename does not require duplicate ID edits. Reuse the existing Anthropic alias table for its API targets.
- Missing mappings and unsupported backends produce actionable errors naming the hint and backend. An unknown hint must never return `None` and silently select the host default.

### Hint mapping (decided)

Ship built-in defaults only where the target is verified against this repo's own model tables; every other host resolves through configuration. Lineups on non-Claude hosts change too often, and too few of them are verifiable here, to hard-code.

| Backend key | `coding` | `reasoning` | `burst` | Source |
|-------------|----------|-------------|---------|--------|
| `claude-code` (CLI) | `sonnet` | `opus` | `haiku` | Built-in; host CLI aliases passed through unchanged, as literal values are today |
| `anthropic-api` (SDK/batch) | `MODEL_ALIASES["sonnet"]` | `MODEL_ALIASES["opus"]` | `MODEL_ALIASES["haiku"]` | Built-in; derived at lookup time from `MODEL_ALIASES` so the canonical ID lives in one place. Do not copy concrete IDs into the hint table or docs. BUG-3541 (done) refreshed `MODEL_ALIASES` to current IDs |
| `codex`, `gemini`, `omp`, `kimi-code`, `qwen` | — | — | — | No built-in default; config only. An unmapped hint on these hosts raises the actionable missing-mapping error |
| `opencode`, `pi` | — | — | — | Not advertised; hints error regardless of config |
| `fake`, `fake-minimal` (`TEST_ONLY_HOSTS`) | `fake-coding` | `fake-reasoning` | `fake-burst` | Built-in test-only pass-through. Needed so ENH-3547's portability proof can run a hint-bearing loop under the fake host. Each hint maps to a distinct sentinel so tests can assert *which* hint resolved. These hosts are not in `RUNTIME_HOST_CAPABILITIES` (`host_runner.py:2230`), so the resolver's backend set must add them explicitly. Not documented to end users |

**Config override (in scope).** Add `model_hints` (under `orchestration`) to `config-schema.json` and `OrchestrationConfig`:

```json
"orchestration": {
  "model_hints": {
    "codex": { "coding": "<codex-model>", "reasoning": "<codex-model>", "burst": "<small-codex-model>" },
    "claude-code": { "burst": "sonnet" }
  }
}
```

- Keys are runtime backend keys (the `RUNTIME_HOST_CAPABILITIES` host names, `TEST_ONLY_HOSTS`, and `anthropic-api`); an unknown backend key or hint name is a config validation error. Values are non-empty strings passed through as literals (no nested hint resolution), or `false` to disable.
- JSON-schema shape in `config-schema.json`: `model_hints` is an object with `propertyNames` enumerating the backend keys and `additionalProperties: false`; each backend value is an object with `properties` `coding`/`reasoning`/`burst` and `additionalProperties: false`; each hint value is `{"oneOf": [{"type": "string", "minLength": 1}, {"const": false}]}`. `null` and `true` fail schema validation.
- Per-hint merge over built-in defaults: a host entry may override one hint and inherit the rest. The value `false` disables a built-in mapping for that hint, which makes the hint error on that backend. `null` is **not** the disable sentinel. `config.core.deep_merge` removes a key set to `None` in `ll.local.md` before parsing (`config/core.py:111`). There, `null` keeps its standard meaning of "unset the `ll-config.json` value", which falls back to the built-in default or to no mapping. It cannot be rejected, and it is not an error. A `null` written directly in `ll-config.json` does reach parsing, and there it is a validation error.
- **Runtime validation home (decided 2026-09-25).** `config-schema.json` is not enforced at runtime; no jsonschema dependency exists. `OrchestrationConfig` otherwise does no validation (`config/orchestration.py:114`). `model_hints` is the exception, because a malformed entry would otherwise surface only as a confusing resolver error at dispatch. `OrchestrationConfig.from_dict` validates `model_hints` and raises `ValueError` naming the offending path for:
  - an unknown backend key;
  - an unknown hint key;
  - a non-dict backend value;
  - a `null`/`true`/empty-string hint value.

  Share the backend-key set with `resolve_model_hint`: `RUNTIME_HOST_CAPABILITIES` keys ∪ `TEST_ONLY_HOSTS` ∪ `{"anthropic-api"}`. The JSON-schema shape below remains the editor-time contract.
- `anthropic-api` values still pass through `resolve_model_alias`, so an alias such as `opus` is valid there.
- Precedence is unchanged: config supplies only the hint → model table; a literal `model:` or run `--model` beats a hint exactly as in the precedence table above.
- `ll-loop validate` resolves each declared hint against the configured host (`orchestration.host_cli` / `LL_HOST_CLI`) and emits a WARNING — not an error, because the host can differ at run time — for any hint that would fail to resolve. It checks every request path the declaration could reach, mirroring `FSMExecutor._resolve_request_path`: the state's own `request_path` override if set, else `orchestration.request_path`; plus the CLI fallback for SDK/batch (downgrade re-resolves for the CLI runner). An evaluator hint is checked against the CLI host only, whatever the state's `request_path`. States that `_resolve_request_path` always downgrades to CLI (action invokes a `/ll:` skill per `_SKILL_INVOKE_RE`, or declares `tools:` — BUG-2831) are checked for CLI only; do not warn about an `anthropic-api` mapping they can never reach. The runtime error remains authoritative.

### Supported artifact/host matrix

The implementation must publish a tested matrix, not infer support from a `--model` flag somewhere in a runner.

| Artifact / operation | Delivery requirement |
|----------------------|----------------------|
| Loop CLI actions, Claude/Codex/Gemini/OMP/Kimi/Qwen | Prove each supported runner forwards the resolved selection; mark unsupported combinations explicitly |
| Loop Codex streaming actions | Supported (BUG-3529 done); dispatch test asserts the resolved selection in argv |
| Loop blocking evaluators | CLI host only (no SDK evaluator path exists); test each runner advertised as supported, including Codex |
| Fake host (`fake`, `fake-minimal`) | Test-only built-in mapping; `FakeHostRunner` must echo `--model` into argv (ENH-3547) so dispatch tests can assert it |
| Loop Anthropic SDK/batch | Concrete Anthropic resolution, including foreign configured CLI hosts and CLI downgrade |
| Opencode/pi | Preserve unconfigured-runner behavior; do not advertise hint support |
| Native skills/agents and generated agent files | Deferred to ENH-3533; no portability claim from accepting frontmatter alone |

Do not migrate shipped skills/agents or regenerate mirrors in this issue. ENH-3533 must establish resolution timing (native invocation versus generation), stale generated-file handling after mapping changes, and an executable test for every artifact/host combination it claims to support.

### Lifecycle and model identity

Persist the requested declaration through sub-loop inheritance, detach, and resume rather than replacing it with a resolved ID. Existing override rules continue to apply. Each dispatch resolves against the effective backend and records the hint/literal requested, resolved selection, and backend **in the FSM event stream** (the existing state/action event payloads, as additive `model_requested`, `model_resolved`, `model_backend` fields) and in the run header. This issue adds no database columns; `usage_events` (ENH-3528/ENH-3538, both done) records only observed model identity in its `model` column, where NULL is bucketed as `token_provenance.UNKNOWN_MODEL_BUCKET`. Resume may resolve a changed mapping and must make the new selection visible.

**Sub-loops (decided 2026-09-24).** Matches how `run_model` is passed to child executors today (`executor.py:1268`): the run-level `--model` inherits into child loops unchanged; a parent state's `model`/`model_hint` does **not** propagate into the child. Each child state resolves against its own declaration, then the run `--model`, then the *child* loop's `llm` — never the parent's `llm`. The requested declaration (not a resolved ID) is what persists, so a child resolves afresh against the effective backend.

Keep the observed model reported by the host separate from requested/resolved selections. Missing host model identity remains unknown; do not label a requested alias as an observed model. Headers may show `hint → resolved selection`, while usage records use observed identity where available. ENH-3528 has landed; do not write requested or resolved selections into `usage_events.model`.

## Acceptance Criteria

- [ ] State and `llm` hints accept exactly `coding`, `reasoning`, and `burst`; explicit model-plus-hint, invalid hints, and inapplicable states fail validation before execution.
- [ ] Schema, parsing, serialization, and direct construction cover omitted, literal-only, and hint-only cases; implicit defaults do not create conflicts or mask hints.
- [ ] Applicability follows the runtime model reach, not `_is_llm_judged`. Prompt/slash-command actions and `llm_structured` evaluators (explicit or implicit) are valid, and shell-action + `llm_structured` states are valid. States with neither fail validation. So do `contract`- and `advisor_consult`-only states: an ERROR, deliberately stricter than `model:`'s WARNING, with tests for both evaluator types. `llm.model_hint` on a loop with no LLM states is a WARNING.
- [ ] `ll-loop run --llm-model X` on a loop with `llm.model_hint` clears the hint (`fsm.llm.model_hint is None`, `fsm.llm.model == X`), and the loop is not stopped by the guard.
- [ ] `resolve_model_hint` unit tests cover every backend key × hint (including `fake`/`fake-minimal`), unsupported backends (opencode/pi), and disabled or missing mappings; it never returns `None`.
- [ ] Canonical mapping targets avoid duplicate model IDs for hints sharing a target, and runtime-map coverage is checked by `ll-verify-host-map` tests.
- [ ] Until ENH-3547 lands, running a hint-bearing loop fails at the start of `FSMExecutor.run()`, before any state executes, with an explicit not-yet-supported error. A loop is hint-bearing if any state has `model_hint` or `fsm.llm.model_hint` is set. A test proves that a shell state preceding the hinted state never runs. No-hint behavior and literal CLI argv are unchanged.
- [ ] Built-in mappings exist only for `claude-code` and `anthropic-api`, with `anthropic-api` targets derived from `MODEL_ALIASES` (no duplicated concrete IDs). `model_hints` (under `orchestration`) is in `config-schema.json` and `OrchestrationConfig`; tests cover per-hint merge over defaults, `false` disabling a built-in hint (via both `ll-config.json` and `ll.local.md`), `null` in `ll-config.json` raising in `OrchestrationConfig.from_dict`, `null` in `ll.local.md` unsetting the `ll-config.json` value (falling back to the built-in default, not an error), unknown backend/hint keys raising in `from_dict`, `fake`/`fake-minimal` accepted as keys, and `resolve_model_hint("coding", backend="codex", overrides=...)` returning a config-only Codex mapping. The argv assertion belongs to ENH-3547, because this issue's guard stops dispatch.
- [ ] The `llm.model` JSON `default` is removed from `fsm-loop-schema.json`; the fallback to `DEFAULT_LLM_MODEL` is described in its `description` instead, and a JSON/Python parity test covers it.

Moved to split issues: precedence/dispatch/lifecycle/diagnostics/portability-proof criteria → ENH-3547; `ll-loop validate` warnings and documentation → ENH-3548.

## Scope Boundaries

- **In scope (this issue)**: loop state/evaluator declarations, the resolver and its support table, built-in `claude-code`/`anthropic-api` mappings, the `model_hints` (under `orchestration`) config override, and the pre-dispatch not-yet-supported guard.
- **Split out**: ENH-3547 (dispatch wiring, lifecycle preservation, selection diagnostics, portability proof); ENH-3548 (validate-time warnings, documentation).
- **Satisfied prerequisite**: BUG-3529 (Codex streaming `--model` forwarding) is done.
- **Deferred follow-up**: ENH-3533 — native skill/agent hints and generated-agent materialization.
- **Out of scope**: artifact migration; new hint vocabulary; built-in default mappings for non-Claude hosts; hints in advisor/compaction configuration or unrelated CLI commands; new run-level hint flags; automatic cost routing; price tables; changing host-internal model selection or reasoning effort.

## Integration Map

This issue's slice only (declaration + resolver + config). Dispatch/lifecycle files belong to ENH-3547; validate warnings and docs to ENH-3548 — see the Design sections for their shared spec.

### Files to Modify

- `scripts/little_loops/host_runner.py` — hint mappings, per-backend support, `resolve_model_hint`, public exports; preserve literal CLI forwarding and existing API alias resolution.
- `scripts/little_loops/fsm/schema.py`, `fsm/fsm-loop-schema.json` — state and `llm` declarations, exclusivity, absent-versus-default handling; remove the stale JSON `llm.model` default.
- `scripts/little_loops/fsm/validation/structural_rules.py` — declaration errors (vocabulary, exclusivity, inapplicable states).
- `scripts/little_loops/fsm/executor.py` — only the not-yet-supported guard, at the top of `FSMExecutor.run()` (`executor.py:629`). Child loops construct their own `FSMExecutor` (`executor.py:1260`), so they inherit the check.
- `scripts/little_loops/cli/loop/run.py` — `--llm-model` override (`run.py:190`) also clears `fsm.llm.model_hint`.
- `scripts/little_loops/cli/verify_host_map.py`, `fsm/__init__.py` — runtime consistency checks and public exports. Hint-support coverage must include `TEST_ONLY_HOSTS`, which check 2 currently exempts from the runtime map.
- `scripts/little_loops/config/orchestration.py` (`OrchestrationConfig`), `scripts/little_loops/config-schema.json` — `model_hints` override under `orchestration`; `docs/reference/CONFIGURATION.md` entry for the new key.

### Dependent Files and Similar Patterns

- `runner_spec.py`, `advisor.py`, `cli/{harness,advise}.py`, `cli/artifact/`, `issue_manager.py`, `parallel/worker_pool.py` consume existing model APIs; preserve literal semantics without broadening their configuration.
- `StateConfig` optional `effort`/`tamper_guard` fields illustrate round trips. `LLMConfig.model` needs additional omitted/default handling; copying a nullable state field alone is insufficient.

### Tests

- `test_fsm_schema.py`, `test_fsm_validation_structural.py` — declarations, JSON/Python parity, invalid/conflicting values, defaults.
- `test_host_runner.py`, `test_verify_host_map.py` — resolver matrix, unchanged literals, map coverage.
- `test_fsm_executor.py` — the fail-fast guard.
- Config tests for `model_hints` merge/`false`/`null`/unknown-key handling (`ll-config.json` and `ll.local.md`).

## Implementation Steps

1. Add schema/serialization tests for explicit declarations; implement hint fields without changing legacy defaults; remove the JSON `llm.model` default. Add the applicability rule as a new predicate in `structural_rules.py`, not a reuse of `_is_llm_judged`.
2. Add backend resolution and mapping-coverage tests; implement `resolve_model_hint` and built-in mappings. Add `model_hints` (schema, `OrchestrationConfig.from_dict` validation, per-hint merge) in the same step.
3. Add the not-yet-supported guard at the top of `FSMExecutor.run()`, and make `--llm-model` clear `fsm.llm.model_hint` in `cli/loop/run.py`.
4. Run focused schema/resolver/config tests, then the required local suite and lint/type checks.

## Program Design

### Types

- `ModelHint = Literal["coding", "reasoning", "burst"]`; FSM fields may use `str | None` with runtime validation to match existing schema conventions.
- `model_hint: str | None` — new optional field on both `StateConfig` and `LLMConfig`. `LLMConfig.model` stays `str = DEFAULT_LLM_MODEL`; see "`LLMConfig` representation (decided 2026-09-25)".
- `model_hints: dict[str, dict[str, str | Literal[False]]]` — new `OrchestrationConfig` field, validated in `from_dict`; backend key → hint → model, `False` disables a built-in mapping; `None` in `ll-config.json` raises.
- A model declaration represents exactly one explicit literal or hint, or no selection. Exclusivity is enforced on the raw mapping; when `model_hint` is set, it wins over the default `model`.
- A resolved selection records requested literal/hint, effective backend, and selected model string. Observed model identity is separate and optional.
- Runtime hint mappings reference canonical backend model targets. Backend support is explicit, including unsupported backends (opencode/pi).

### Signatures

- `resolve_model_hint(hint: str, *, backend: str, overrides: dict[str, dict[str, str | Literal[False]]] | None = None) -> str` — returns a usable selection or raises a validation/capability error; never returns `None`. `overrides` is the parsed config mapping, merged per hint over the built-in defaults.
  - **No `operation` parameter (decided 2026-09-24).** Since BUG-3529 every supported runner forwards `--model` for both streaming and blocking, so no backend behaves differently per operation. Support is per backend; the unsupported-selection error names the hint and backend. If a future runner supports only some operations, add the parameter then.
- `resolve_model_alias(model: str) -> str` — unchanged; remains the Anthropic API alias resolver and the source of `anthropic-api` hint targets.

### Call Path

Declaration selection and backend resolution happen after the effective request path is known:

- `FSMExecutor._resolve_request_path` → `resolve_model_hint` → `build_anthropic_request` (SDK/batch; concrete IDs via `resolve_model_alias`)
- `FSMExecutor._resolve_request_path` → `resolve_model_hint` → `CodexRunner.build_streaming` / `ClaudeCodeRunner.build_streaming` (CLI actions)
- `FSMExecutor._evaluate` → `resolve_model_hint` (CLI backend only) → `evaluate_llm_structured` / `evaluate` → `resolve_host().build_blocking_json` (evaluators)

Evaluators do not receive `orchestration_config`; they take a plain `model: str` and call `resolve_host()` themselves (`fsm/evaluators.py:1117,1227,1483`). Resolve the hint in `FSMExecutor._evaluate` (today `model=state.model or self.fsm.llm.model` at `executor.py:3174,3221`), where `self.orchestration_config` is available, against the CLI backend `resolve_host()` will return. Do not use `_resolve_request_path` here, because evaluators have no SDK path. Pass the resolved string down. Evaluator signatures stay `model: str`; do not thread config into `evaluators.py`.

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

Until ENH-3547 lands, a declared hint parses and validates, but `FSMExecutor.run()` must fail fast at run start, before any state executes, with an explicit "model_hint dispatch not yet supported" error. A per-state check is not enough: it would let earlier shell states run their side effects first. A hint-bearing loop authored in between must not run silently on the default model, which would break the no-silent-fallback rule. ENH-3547 removes this guard.

## Verification Notes

Review corrections applied on 2026-09-23: narrowed delivery to loop execution; corrected CLI alias flow; defined vocabulary, precedence, effective-backend resolution, unsupported combinations, lifecycle behavior, and model identity. Reconciled prior research/wiring notes into the directive sections rather than retaining contradictory instructions. Graph corroboration used fresh `codegraph` results for alias callers and direct source inspection. The review's 30 focused existing tests passed; they establish current behavior, not completion of the new acceptance criteria.

Review follow-up on 2026-09-23: reprioritized P0 → P2 and renamed the file to match the narrowed title; decided the hint mapping (built-in for `claude-code`/`anthropic-api` only, `model_hints` (under `orchestration`) override for all hosts); replaced the Codex streaming "unsupported" row with a dependency on BUG-3529 after confirming `codex exec [resume] --model` exists; added validate-time warnings, JSON-default removal, and a portability proof AC; split deferred skill/agent work to ENH-3533.

### Verify pass (superseded)

An earlier verify pass recorded Codex `build_streaming` doing `del model` and BUG-3529 as open. Both are obsolete: BUG-3529 is done and `CodexRunner.build_streaming` forwards `--model` (`host_runner.py` ~L1241). Do not act on the earlier record.

### Verify pass 2026-09-26

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Line anchors relocated: `executor._action_mode` `executor.py:2460` → `3427`; `_resolve_action_model` `executor.py:3570` → `3559`; `_is_llm_judged` use in the `model:` WARNING rule `structural_rules.py:468` → `470`.
- Confirmed unchanged: `run.py:190`/`707`, `executor.py:629/1268/3174/3221`, `evaluators.py:1117/1227/1483/2064`, `host_runner.py:2230` (`TEST_ONLY_HOSTS`), `config/core.py:111`, `info.py:1528`, stale JSON `llm.model` default (`fsm-loop-schema.json:1017`), `MODEL_ALIASES` current IDs, no `model_hint` anywhere yet, BUG-3529/BUG-3541 done, ENH-3533/3547/3548 backlinks present. `ll-verify-evidence`: clean. Proposal-vs-code check found no consequence gaps. No decisions-rule conflicts checked beyond the log gate.

### Pre-implementation review 2026-09-23

BUG-3529 is done: removed the `blocked_by`, and Codex streaming is now a supported row with an argv test. Changed the mapping-disable sentinel from `null` to `false`, because `config.core.deep_merge` removes `None` keys from `ll.local.md`, which would restore the built-in default. Fixed where selection diagnostics live: event payload plus header, no DB columns. Defined which request paths and operations validate-time warnings check.

### Pre-implementation review 2026-09-23 (second pass)

`anthropic-api` targets are now written as `MODEL_ALIASES[...]` lookups, not copied IDs (the table is stale; BUG-3541). Validate-time warnings now honor per-state `request_path` and skip SDK checks for states that always downgrade to CLI (BUG-2831). Evaluator hint resolution belongs in `FSMExecutor._evaluate`, with no config threaded into `evaluators.py`. The `model_hints` JSON-schema shape is now specified, and a delivery split is proposed.

### Pre-implementation review 2026-09-24

Applied the delivery split: this issue keeps declaration, resolver and config; dispatch/lifecycle moves to ENH-3547 and validate/docs to ENH-3548, with a fail-fast guard in between. Defined hint applicability (prompt action and/or LLM evaluator, resolved per operation). Made the resolver's `operation` parameter conditional on a real per-operation support table. The Design sections remain the shared spec for all three issues.

### Pre-implementation review 2026-09-24 (third pass)

Dropped `resolve_model_hint`'s `operation` parameter and the `model_operation` event field; decided sub-loop semantics; trimmed Integration Map/Steps to this issue's slice; added `blocks: ENH-3533`. BUG-3541 should land before the `anthropic-api` hint tests.

### Pre-implementation review 2026-09-25

- Added built-in test-only mappings for `fake`/`fake-minimal`, which are excluded from `RUNTIME_HOST_CAPABILITIES`. Without them, ENH-3547's fake-host portability proof would fail as an unknown backend.
- Evaluators have no SDK path (`fsm/evaluators.py` never reads `request_path`), so evaluator hints resolve against the CLI host only.
- The config criterion no longer asserts argv, which this issue's own guard prevents; argv moved to ENH-3547.
- Documented the implicit-evaluator reach and the deliberate ERROR (vs `model:`'s WARNING) for inapplicable hints.
- Removed stale `MODEL_ALIASES` text now that BUG-3541 is done.

### Pre-implementation review 2026-09-25 (second pass)

- Applicability now uses the runtime model reach: prompt/slash-command actions and `llm_structured` only. `_is_llm_judged` also admits `advisor_consult` and `check_semantic`, whose evaluators never receive the state model (`evaluators.py:2064`).
- `model_hints` validation now lives in `OrchestrationConfig.from_dict`, because `config-schema.json` is not enforced at runtime. A `null` in `ll.local.md` is standard "unset" (`deep_merge` removes it), not an error.
- The guard moved to the top of `FSMExecutor.run()` so no state executes before it fires.
- `--llm-model` clears `llm.model_hint` (`run.py:190`).
- Decided the `LLMConfig` representation: `model` stays non-nullable, exclusivity is checked on the raw mapping, and the hint wins when set.
- `llm.model_hint` with no LLM states is a WARNING.
- For ENH-3548: `ll-loop show` (`info.py:1528`) should display `model_hint`.

## Related

- ENH-3547, ENH-3548 — split pieces 2 and 3 (blocked by this issue).
- BUG-3541 (done) — refreshed `MODEL_ALIASES` `opus`/`fable` targets; `anthropic-api` hint tests assert current IDs.

## Status

**Open** | Created: 2026-09-23 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-25_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across ~8 change sites (host_runner, fsm schema/JSON schema, structural_rules, executor guard, verify_host_map, orchestration config, config-schema, CONFIGURATION.md).
- Deep per-site complexity in `LLMConfig`: omitted-vs-default handling for `model` (currently a hard `DEFAULT_LLM_MODEL` default) touches serialization, parsing, and existing construction sites; the concrete dataclass representation is left to the implementer.
- Wide blast radius: `StateConfig`, `LLMConfig`, and `OrchestrationConfig` have many construction/consumer sites, so any change to the no-hint default must be verified against existing tests.

## Session Log
- `/ll:verify-issues` - 2026-09-26T04:08:04 - `3c60f1bd-de19-4edd-8506-d4aa11e7800c.jsonl`
- `/ll:confidence-check` - 2026-09-26T03:44:04 - `ca8c81c6-3907-43f2-b123-5aad7f9c65b9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:55 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:08 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:01:43 - `d1e0cad9-5218-4c39-a990-a91f5f18af0d.jsonl`
- `/ll:wire-issue` - 2026-09-23T23:43:26 - `96fe3651-90ba-4862-a958-697a2df577cc.jsonl`
- `/ll:refine-issue` - 2026-09-23T23:20:19 - `1dd8afb6-deef-4834-bd0a-401f1160db13.jsonl`
- `/ll:format-issue` - 2026-09-23T22:58:54 - `67a10285-a4b7-4192-bd9e-23ac30a3ffd0.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers the hint declaration, resolver, and config slice only. Dispatch/lifecycle wiring belongs to ENH-3547; validate-time warnings, `haiku-gen` guidance, and documentation belong to ENH-3548. Any Integration Map, Implementation Steps, or Files to Modify entries here for those areas are shared spec, not this issue's deliverable. The `operation` parameter of `resolve_model_hint` was dropped (2026-09-24); ENH-3547/ENH-3548 follow the `(hint, *, backend, overrides=None)` signature.
