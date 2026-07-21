---
id: ENH-2713
type: ENH
title: Per-state model pinning in loop YAML (haiku for verdict states)
priority: P3
status: done
captured_at: '2026-07-21T02:03:13Z'
completed_at: '2026-07-21T06:00:05Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
parent: EPIC-2456
labels:
- token-cost
- fsm
- routing
relates_to:
- EPIC-2456
- ENH-2490
- ENH-2073
confidence_score: 98
outcome_confidence: 84
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2713: Per-state model pinning in loop YAML (haiku for verdict states)

## Summary

Support a per-state `model:` field in loop YAML so cheap classification states — `check_semantic` verdicts, `llm_structured` extraction — run on haiku while generator states keep the session default. This is the loop-YAML half of the deferred ENH-2490 (agent-frontmatter haiku pin) and a static precursor to Tier 4's F7-lite router: it captures most of routing's win with none of the cascade machinery.

## Motivation

Verdict states are tiny, rigidly-templated tasks currently billed at flagship rates on every iteration of every loop. Unlike ENH-2490 (deferred for lacking a quality gate), this has a built-in one: MR-1 already requires each LLM-judged state to pair with a non-LLM evaluator in its routing chain, so a wrong verdict from a cheaper model is caught by the same external signal that gates the flagship's verdicts.

## Current Behavior

**Correction from refinement**: the premise that "all FSM states within a loop run on the same model" is only true for the *evaluator* path. The *action* path already has per-state model pinning, shipped by ENH-2073 (`status: done`, `.issues/enhancements/P3-ENH-2073-fsm-per-state-model-override.md`):

- `StateConfig.model: str | None = None` already exists (`scripts/little_loops/fsm/schema.py:629`), with `to_dict`/`from_dict` round-tripping (lines 705-706, 803) and JSON-schema docs (`scripts/little_loops/fsm/fsm-loop-schema.json:556-559`).
- `FSMExecutor._run_action` (`scripts/little_loops/fsm/executor.py:1612`) already threads `model=(state.model or self.run_model) if action_mode == "prompt" else None` into the action dispatch — this is the precedence chain the issue asks for, already implemented for actions.
- `FSMExecutor._dispatch_live` (executor.py:2030, FEAT-2716 SDK/Batches path) already does `model = state.model or self.run_model or ""`.
- `ll-loop run --model` (`run_model`) and `--llm-model` CLI flags already exist (`scripts/little_loops/cli/loop/__init__.py:183-195`) with help text documenting "Per-state `model:` overrides this" for the action path.
- `validation.py:669-677` already WARNs when `model:` is set on a non-prompt/slash_command state (shell/mcp_tool/contract) — the ENH-2073 validation precedent for a new WARN rule.

**What is genuinely missing (the real gap this issue should close)**: `state.model` is NOT threaded into the *evaluator/verdict* path — `check_semantic`/`llm_structured` verdicts. In `FSMExecutor._evaluate()` (executor.py:1790):
- The default-evaluator branch (no explicit `evaluate:` block, executor.py:1822-1827) calls `evaluate_llm_structured(..., model=self.fsm.llm.model, ...)` — always the loop-level `LLMConfig.model` (default `"sonnet"`, `schema.py:23,873`), overridable only via `--llm-model`, never by `state.model`.
- The explicit `evaluate: {type: llm_structured}` branch routes through `evaluate()` in `scripts/little_loops/fsm/evaluators.py`, which at line ~1950-1963 calls `evaluate_llm_structured(...)` with **no `model=` argument at all** — it silently falls back to `evaluate_llm_structured`'s own default (`model: str = DEFAULT_LLM_MODEL`, evaluators.py:1067), ignoring both `state.model` and `--llm-model`.

So the issue's actual scope is narrower than originally written: thread `state.model` into both `_evaluate()` call sites (executor.py:1822-1827 and the `evaluators.py` explicit-evaluate branch), not add a new schema field.

## Expected Behavior

A state may declare `model: haiku`; the runner passes the mapped model id to the host invocation for that state only. Precedence: explicit `--model` flag > state `model:` > loop `model:` > session default (consistent with the `routing.precedence` rule planned for Tier 4 — this issue should not contradict [TBD-17] when it lands).

## Proposed Solution

- `model:` accepted at loop level and state level in `fsm/schema.py`; alias map (`haiku`/`sonnet`/`opus` → concrete ids) resolved through `resolve_host()`, never hard-coded literals (host-CLI abstraction policy).
- `ll-loop validate` advisory: a haiku-pinned state that is a generator (writes artifacts) rather than an evaluator gets a WARN, mirroring the ENH-2490 quality concern.
- Roll out on builtin loops' verdict states only after a before/after quality check on ≥10 runs per loop (evaluator agreement rate vs flagship).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No alias map needed/exists**: there is no `MODEL_ALIASES`-style table anywhere in `scripts/little_loops/`. Every host runner (`ClaudeCodeRunner`, `CodexRunner`, opencode, pi — `scripts/little_loops/host_runner.py`) passes the `model` string through unmodified as `--model <value>` (e.g. `build_blocking_json`, lines 314-343 for claude), relying on the underlying CLI binary to resolve short names like `"haiku"`. `evaluators.py`'s docstring for `evaluate_llm_structured()` (line ~1082) already documents "Model identifier (CLI aliases like 'sonnet' or full names)". The one exception: `host_runner.py`'s SDK/Batches direct-API path (`build_anthropic_request`, line 1349) requires a concrete model ID, not a bare alias — relevant if a verdict state's request routes through FEAT-2716's SDK/Batches path rather than a CLI subprocess.
- **Concrete threading points** (the actual implementation surface, narrower than "accept `model:` in `fsm/schema.py`" since the field already exists):
  1. `FSMExecutor._evaluate()` default-evaluator branch, `scripts/little_loops/fsm/executor.py:1822-1827` — change `model=self.fsm.llm.model` to `model=state.model or self.fsm.llm.model` (or a full `--model > state.model > loop llm.model > default` chain if `run_model`/`--llm-model` should also participate).
  2. `evaluate()` dispatcher's `llm_structured` branch, `scripts/little_loops/fsm/evaluators.py:1950-1963` — currently passes no `model=` at all to `evaluate_llm_structured(...)`; needs `model=state.model or fsm.llm.model` threaded through from the caller (`executor.py:1866-1871`).
- **Validation rule template**: `_validate_llm_evidence_contract` (MR-8, `validation.py:2128-2167`) is the closest structural analog — iterates `fsm.states.items()`, gates on `_is_llm_judged(state)` (validation.py:1594-1610, already classifies check_semantic/llm_structured/prompt-action states), appends a `ValidationSeverity.WARNING` `ValidationError`, gated by a new `FSMLoop` suppression flag following the `xxx_ok: bool = False` pattern (`schema.py:1207-1221`, e.g. `evidence_contract_ok`). The new rule needs the *inverse* condition — a generator (non-`_is_llm_judged`) state whose `model:` matches a haiku name — and must be registered via `errors.extend(_validate_xxx(fsm))` in `validate()` (call sites around `validation.py:1152-1308`).
- **Precedence is already implemented for actions, needs replicating for evaluators**: `ll-loop run --model` (`run_model`) and `--llm-model` CLI flags already exist (`cli/loop/__init__.py:183-195`); `--llm-model` currently only feeds the loop-level `fsm.llm.model` mutation (`cli/loop/run.py:159-160`), not `state.model` — so the full 4-level precedence chain the issue specifies doesn't exist end-to-end for verdict states yet even after `state.model` is threaded into `_evaluate()`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py:1822-1827` — thread `state.model` into the default-evaluator `evaluate_llm_structured(...)` call (currently `model=self.fsm.llm.model` only)
- `scripts/little_loops/fsm/executor.py:1866-1871` — pass `state.model` through to the `evaluate()` dispatcher call for the explicit-`evaluate:`-block branch
- `scripts/little_loops/fsm/evaluators.py:1950-1963` — `evaluate()`'s `llm_structured` branch: add `model=` argument to its `evaluate_llm_structured(...)` call (currently omitted entirely, silently falling back to `DEFAULT_LLM_MODEL`)
- `scripts/little_loops/fsm/validation.py` — new `_validate_haiku_pinned_generator(fsm)` WARN rule (model on `_validate_llm_evidence_contract`, `validation.py:2128-2167`), registered in `validate()` (`validation.py:1152-1308`)
- `scripts/little_loops/fsm/schema.py:1207-1221` — add a new `FSMLoop` suppression flag (e.g. `haiku_generator_ok: bool = False`) for the new rule, plus `to_dict()`/`from_dict()` entries and the "known top-level keys" allowlist (`validation.py:225-233`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:159-160` — where `--llm-model` currently mutates `fsm.llm.model`; may need to also feed into the new evaluator precedence chain
- `scripts/little_loops/cli/loop/__init__.py:183-195` — `--model`/`--llm-model` argparse definitions; help text may need updating once evaluator threading changes precedence semantics

### Similar Patterns
- `scripts/little_loops/fsm/executor.py:1612` — `FSMExecutor._run_action`'s existing `model=(state.model or self.run_model) if action_mode == "prompt" else None` — the precedence-threading pattern to mirror for the evaluator path
- `scripts/little_loops/fsm/validation.py:2128-2167` (`_validate_llm_evidence_contract`, MR-8) — structural template for the new validation rule
- `scripts/little_loops/host_runner.py:262-343` (`ClaudeCodeRunner.build_streaming`/`build_blocking_json`) — `if model: args += ["--model", model]` conditional-append pattern already used across every host runner

### Tests
- `scripts/tests/test_fsm_schema.py:2391` — `TestModelStateConfig` class (ENH-2073); model for a new test class covering the suppression-flag schema field
- `scripts/tests/test_fsm_validation.py` — `TestOverescapedShell` (lines ~3305-3404, MR-9) is the fullest template for a new `TestHaikuPinnedGenerator` class: fires-on-violation / does-not-fire-when-correct / suppressed-by-flag / wired-into-`validate_fsm()` / no-spurious-"Unknown top-level"-warning
- `scripts/tests/test_fsm_executor.py` and `scripts/tests/test_fsm_persistence.py` (lines 636, 1950, 2010, 2095) — `MockActionRunner`/evaluator mocks already carry a `model` parameter from ENH-2073; extend for evaluator-path model assertions

### Documentation
- `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md` (~line 348), `docs/reference/CLI.md` (~line 547) — state-field reference tables already document `model:` for actions (ENH-2073); need a note that it now also applies to evaluator/verdict dispatch

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — `## Loop Authoring` MR-1..MR-11 table needs a new row for the `_validate_haiku_pinned_generator` WARN rule (severity, what it catches, `haiku_generator_ok` suppression flag), following the MR-8 row's format
- `scripts/little_loops/fsm/fsm-loop-schema.json:556-559` — the state-level `model` property description currently says *"Only used for prompt-mode states... Ignored for shell/mcp_tool/contract states — a validation WARNING is emitted if set on those types"*; this becomes inaccurate once evaluator/verdict states legitimately consume `model` and needs rewording, not just a comment update
- `docs/reference/API.md` — three exact code-fenced reference blocks go stale if signatures change: the `StateConfig` dataclass listing's `model:` inline comment (currently phrased action-only), the `evaluate_llm_structured(...)` signature block (`#### Tier 2 Evaluators`), and the `evaluate(config, output, exit_code, context)` dispatcher signature block (`#### Dispatcher`) if it gains a `model` param
- `docs/reference/CONFIGURATION.md` — the `request_path` config-table row says *"the same way `State.model` overrides `run_model`"*; this analogy sentence is the discoverability point where a reader learns `state.model`'s current scope and may want a cross-reference once evaluator states are also in scope
- `docs/reference/EVENT-SCHEMA.md` — the `### evaluate` event section doesn't document the `llm_model` detail field that `evaluate_llm_structured()` already populates (`evaluators.py:1241`); pre-existing gap, natural place to document once the value can reflect a pinned override

### Tests (additional, beyond those already listed above)

_Wiring pass added by `/ll:wire-issue`:_
- No existing test asserts the actual `model=` kwarg reaching `evaluate_llm_structured` from either dispatch site — confirmed gap. Pattern to mirror: `scripts/tests/test_ll_loop_execution.py` `TestModelFlag` (lines 977-1037, `CapturingRunner` idiom: `test_run_model_used_as_fallback_for_host_action` / `test_state_model_overrides_run_model`) — same shape needed for the evaluator path (fallback to `self.fsm.llm.model` vs. `state.model` override)
- `scripts/tests/test_fsm_runners.py:479` `test_model_kwarg_forwarded` — companion lower-level unit-test pattern (patches `run_claude_command`, asserts `captured_kwargs.get("model")`)
- `scripts/tests/test_fsm_evaluators.py` `TestEvaluateDispatcherLLM` (line 1294) and its `mock_cli` fixture (line 1315, patches `evaluators.subprocess.run`) — existing test exercises `evaluate()`'s `llm_structured` branch via CLI argv inspection but never asserts the model flag; extend for model-argument assertions
- `scripts/tests/test_fsm_validation.py` `TestModelStateValidation` (ENH-2073, lines 1308-1362) — simpler WARN-without-suppression-flag template, closer topically (model-related) than `TestOverescapedShell` if the new rule doesn't need a `validate_fsm()`-level suppression flag
- `scripts/tests/test_fsm_validation.py` `TestLLMEvidenceContractValidation` (MR-8, lines 3738-3856) — closest topical template (LLM-prompt-content WARN with suppression flag + `validate_fsm()` end-to-end wiring test)

## Implementation Steps

1. Thread `state.model` into `FSMExecutor._evaluate()`'s default-evaluator branch (`executor.py:1822-1827`) and the explicit-`evaluate:`-block branch via `evaluators.py:1950-1963`, following the existing `state.model or self.run_model` fallback pattern from `_run_action` (`executor.py:1612`).
2. Add the new `_validate_haiku_pinned_generator` WARN rule to `fsm/validation.py`, modeled on `_validate_llm_evidence_contract` (MR-8), gated by a new `FSMLoop.haiku_generator_ok` suppression flag in `schema.py`.
3. Add tests: schema round-trip for the new suppression flag (`test_fsm_schema.py`), validation-rule behavior (`test_fsm_validation.py`, modeled on `TestOverescapedShell`), and executor/evaluator model-threading assertions (`test_fsm_executor.py`).
4. Pick one builtin loop with `check_semantic`/`llm_structured` verdict states (e.g. `scripts/little_loops/loops/rn-refine.yaml` or `ready-to-implement-gate.yaml`), pin its verdict states to `model: haiku`, and run the before/after evaluator-agreement check (≥10 runs) called for in Proposed Solution.
5. Verify: `python -m pytest scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py scripts/tests/test_fsm_executor.py -v`.

## Acceptance Criteria

- [x] Per-state `model:` reaches the evaluator/verdict dispatch for that state only, not just the action dispatch (action-path model pinning already ships via ENH-2073 — this AC is about closing the evaluator-path gap).
- [x] Precedence documented and tested (`--model` flag beats YAML) for the evaluator path, matching the existing action-path precedence in `_run_action`.
- [x] Validation warns on haiku-pinned generator states.
- [ ] At least one builtin loop's verdict states pinned with measured cost delta and no evaluator-agreement regression. **Deferred** — requires a live ≥10-run before/after evaluator-agreement study against the real host CLI, which is a follow-on rollout task, not a code change. Tracked as future work; the mechanism (per-state `model:` on evaluator states + the `haiku_generator_ok` WARN gate) is fully implemented and tested so this rollout can happen incrementally without further code changes.

## Resolution

Implemented the narrower scope identified by `/ll:refine-issue`: `state.model` now threads
into both `_evaluate()` call sites (the default-evaluator branch and the explicit
`evaluate: {type: llm_structured}` branch via `evaluators.evaluate()`), with the same
`state.model or <loop default>` precedence pattern `_run_action` already uses for the action
path. Added the `_validate_haiku_pinned_generator` WARN rule (`haiku_generator_ok` suppression
flag) and fixed a related false-positive: the ENH-2073 "model: ignored for shell/mcp_tool/contract
states" WARN no longer fires when the state's `model:` is legitimately consumed by an
`llm_structured`/`check_semantic` evaluate block.

The fourth AC (pin a builtin loop's verdict states and measure cost/agreement) is an
operational rollout step requiring real inference spend and iterative judgment across
multiple runs — left as explicit follow-up work rather than fabricated or skipped silently.

### Files Changed
- `scripts/little_loops/fsm/executor.py` — thread `state.model` into both `_evaluate()` branches
- `scripts/little_loops/fsm/evaluators.py` — `evaluate()` dispatcher accepts `model:` and forwards it to `evaluate_llm_structured`
- `scripts/little_loops/fsm/validation.py` — new `_validate_haiku_pinned_generator` WARN rule; fixed `_validate_state_action`'s model-ignored WARN to exempt LLM-judged evaluate blocks
- `scripts/little_loops/fsm/schema.py` — new `FSMLoop.haiku_generator_ok` suppression flag
- `scripts/little_loops/fsm/fsm-loop-schema.json` — updated `model:` state-field description
- `.claude/CLAUDE.md` — new `haiku-gen` row in the Loop Authoring rules table
- Tests: `test_fsm_schema.py`, `test_fsm_validation.py`, `test_fsm_evaluators.py`, `test_ll_loop_execution.py`

## Impact

- **Priority**: P3 — solid savings, but bounded by verdict-state share of spend; ENH-2712's data should confirm before broad rollout.
- **Effort**: Small (~60–100 LOC + tests).
- **Risk**: Low — opt-in, MR-1 pairing bounds the blast radius.

## Session Log
- `/ll:manage-issue improve` - 2026-07-21T05:59:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bcda0bd6-f7df-461b-94c6-7b8822d94245.jsonl`
- `/ll:confidence-check` - 2026-07-21T05:40:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/729e2f9f-8535-4066-a136-a54cc72ef1ac.jsonl`
- `/ll:wire-issue` - 2026-07-21T05:39:12 - `87b3f89c-17f8-4e68-a0b3-d32ad2580aae.jsonl`
- `/ll:refine-issue` - 2026-07-21T05:31:53 - `ae4c02cf-7301-4a04-a6de-dd97b42a2577.jsonl`
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P3
