---
id: ENH-3548
type: ENH
title: Validate-time model hint warnings and hint documentation
priority: P3
status: done
parent: EPIC-3563
epic: EPIC-3563
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:15Z'
completed_at: '2026-09-29T00:05:10Z'
verify_verdict: VALID
labels:
- multi-host
- loops
confidence_score: 90
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3548: Validate-time model hint warnings and hint documentation

## Summary

Add `ll-loop validate` warnings for model hints that will not resolve, and document the hint vocabulary, support matrix and precedence. This is piece 3 of ENH-3527's delivery split (its criteria 8 and 10); design details are in ENH-3527 → Config override.

## Current Behavior

- `ll-loop validate` checks `model_hint` vocabulary and exclusivity (ENH-3527) but does not check whether a hint resolves for the configured host.
- No doc describes the hint vocabulary, support matrix and precedence together. Partial coverage exists in `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md` and `docs/reference/EVENT-SCHEMA.md` (see Integration Research).

## Expected Behavior

- `ll-loop validate` mirrors the run-start preflight (`FSMExecutor._preflight_model_hints`) per state, not per declared hint: for each state, take the consumer paths `_model_consumer_paths` would return (static downgrade causes only), select the declaration `_resolve_model` would select for each path, resolve it with `resolve_model_hint`, and emit a WARNING (not an error) on `ModelHintError`.
- **Host source**: the CLI backend is `resolve_host().name` — the same call `_resolve_model` makes at run time (`LL_HOST_CLI`, `LL_HOOK_HOST`, then the `_PROBE_ORDER` PATH probe). Validate does **not** read `orchestration.host_cli` directly, so `validate` and `run` always agree about the same loop. If `resolve_host()` raises `HostNotConfigured`, validate passes `host_cli=None` and skips resolution warnings. (That `ll-loop run` ignores `orchestration.host_cli` is tracked separately as BUG-3644; once that is fixed, validate follows automatically because it calls the same function.)
- **Declaration selection per path** (mirrors `_resolve_model`; `--model` is unknowable at validate time and treated as absent):
  - `cli` path (prompt action on `cli`, or the CLI fallback of an `sdk`/`batch` state): the state's `model_hint` only. `llm.model_hint` is never a CLI-action default, so it is **not** checked on the CLI fallback.
  - `sdk` path (effective `request_path` `sdk`/`batch` — the state's `request_path` if set, else `orchestration.request_path`): the state's `model_hint`, else `llm.model_hint` when the state declares no `model`. Resolved against `anthropic-api`.
  - `evaluator` path (explicit `llm_structured`, or the implicit verdict on a prompt state, only when `next` is unset and `llm.enabled`): the state's `model_hint`, else `llm.model_hint` when the state declares no `model` (`_resolve_model` takes `state.model` first on every path, so a literal `model:` state never falls back to `llm.model_hint` here). Resolved against the CLI host only — `fsm/evaluators.py` has no SDK path, so a shell action + `llm_structured` state with `request_path: sdk` must not warn about `anthropic-api`.
- **Prompt-mode gate**: the `cli`/`sdk` paths exist only when the state's action is prompt-mode (`_model_consumer_paths` checks `_action_mode(state) == "prompt"`): `action_type` `prompt`/`slash_command`, or `action_type` unset and the action starts with `/`. `_consumes_model_hint` (`structural_rules.py`) has this test inline but also returns True for `llm_structured`, so factor out an `_is_prompt_action(state)` helper and use it in both.
- **Out-of-vocabulary hints are skipped**: resolution runs only for hints in `MODEL_HINTS`. `resolve_model_hint` raises "unknown model_hint" for any other value, which would duplicate ENH-3527's vocabulary ERROR as a WARNING.
- An `sdk`/`batch` state is checked against both `anthropic-api` and (for a state-level hint) the CLI host, because the environmental downgrades (`anthropic` not importable, no credentials) are unknowable at validate time. The CLI-fallback warning text says so ("if the sdk path downgrades to cli").
- States that always downgrade to CLI (a `/ll:` skill action per `_SKILL_INVOKE_RE`, or `tools:` per BUG-2831) are checked for CLI only.
- Terminal, sub-loop (`loop:`) and `human_approval` states consume no model and are never checked.
- A `type: learning` state (with `learning:` set) has exactly one path, the **CLI host**, and **no evaluator path** (`_model_consumer_paths` returns early). Its implicit `/ll:explore-api` remedy is a `/ll:` skill, so it always downgrades to CLI regardless of `request_path` — treat it like any other CLI-only `/ll:` state and never check it against `anthropic-api`. This matches the executor only once BUG-3646 lands (it builds the remedy copy with `action` set, via `_learning_remedy_state`, so `_SKILL_INVOKE_RE` matches); this issue was `blocked_by` BUG-3646 so the mirror would be written once, against the fixed behavior. **Post-completion note (2026-09-28):** this issue landed before BUG-3646, and the shipped learning branch mirrors the unfixed executor. BUG-3646 now owns the CLI-only mirror (see Resolution → Known gap).
- Warning messages name the fix, e.g. `set orchestration.model_hints.<backend>.<hint> in .ll/ll-config.json`.
- An unresolvable `llm.model_hint` warns **once per (hint, backend)** at `path=llm.model_hint`, not once per consuming state. State-level warnings use `path=states.<name>.model_hint` with the `[state: <name>]` prefix and an `(ENH-3548)` tag.
- When `host_cli` is `None` (the in-process callers below, or no host found), resolution warnings are skipped. Vocabulary and exclusivity errors from ENH-3527 still fire. `model_hints=None` means built-in mappings only; it does not by itself skip warnings.
- `haiku-gen` (`_validate_haiku_pinned_generator`) also flags a generator state whose own `model_hint` is `burst`, keeping the `_is_llm_judged` skip and `haiku_generator_ok` suppression. This check is host-independent (the `burst` intent is "cheap/fast" on every backend), so it also fires for in-process callers.

### Known limitations (document, do not fix)

- A run-time `--model` overrides state/`llm` hints on the `cli` and `sdk` paths; validate cannot see it, so it may warn about a hint that the actual run never resolves.
- A plugin-contributed evaluator registered under the name `llm_structured` (`_contributed_evaluators`) is invisible to validation, which checks it as the built-in evaluator.
- Plugin-contributed action types (`_contributed_actions`, mode `"contributed"`) are likewise invisible; validation classifies them by the static `action_type`/`/`-prefix rules only.
- Not covered by `haiku-gen`: `llm.model_hint: burst` reaching `sdk` generator states, and `llm.model` naming haiku. The existing rule does not inspect `llm.model` either; both remain out of scope.

## Scope Boundaries

- **In scope**: validate-time WARNINGs, `haiku-gen` guidance, documentation.
- **Out of scope**: runtime dispatch (ENH-3547); new vocabulary; `cli/doctor.py`'s fleet-wide `load_and_validate` sweep (deferred — see Call Path); making `ll-loop run` honor `orchestration.host_cli` (BUG-3644), **including** its doc/schema text: `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (~486) and `config-schema.json` (`orchestration`, `orchestration.host_cli` descriptions) already claim `LL_HOST_CLI` > `orchestration.host_cli` > probe, which BUG-3644's selected Option B makes true — do not "correct" them here. New hint docs describe the host as "the same host `ll-loop run` uses" and link to the `resolve_host` reference rather than restating the precedence.

## Decisions

- **Host source** — `resolve_host()` (env + probe), identical to run time. Rationale: validate-time warnings must predict what `_preflight_model_hints` will do; reading `orchestration.host_cli` directly would make `validate` and `run` disagree while BUG-3644 is open.
- **Invalid config in `cmd_validate`** — an invalid `orchestration.model_hints` (the `ValueError` from `_validate_model_hints` at `BRConfig` construction) is reported as a validate error with exit 1, not swallowed. Rationale: `ll-loop run` fails on the same config, so a passing `validate` would be misleading. Move the `BRConfig` read inside the error handling (it sits before the `try:` today) and cover it with a test.
- **Warning budget** — no `TestValidatorWarningBudget` category pattern for hint-resolution warnings. Rationale: they depend on the host, so a ratchet would be machine-dependent, and no built-in loop declares `model_hint`.
- **ARCH-121 exemption** — no `*_ok` suppression flag for hint-resolution warnings. Rationale: the warning depends on the machine's host and config, so a flag in the loop file would hide it on every host rather than the one where it fires; the fix is in `orchestration.model_hints`, not the loop file; ENH-3527's hint rules set the same precedent. The extended `haiku-gen` rule keeps its existing `haiku_generator_ok` flag. Recorded in `.ll/decisions` (see Session Log).

## Program Design

### Types

- No new types.

### Signatures

- `resolve_model_hint(hint, *, backend, overrides=None) -> str` — from ENH-3527; validation catches its error and emits a WARNING.
- `validate_fsm(fsm: FSMLoop, orchestration_request_path: str | None = None, *, host_cli: str | None = None, model_hints: dict[str, dict[str, str | Literal[False]]] | None = None) -> list[ValidationError]` — extends the existing signature in `structural_rules.py` with the two keyword args; `host_cli=None` skips resolution warnings.
- `load_and_validate(...)` — gains the same two keyword args and forwards them, mirroring how `orchestration_request_path` is threaded today.
- `cli/logs.py`'s `_validate_builtin_loop(...)` helper — the fleet-review call site in `_cmd_fleet_review()` does not call `load_and_validate` directly; it goes through this wrapper. The wrapper's own signature must also gain `host_cli`/`model_hints` (with defaults) and forward them to its `load_and_validate` call, or the two new kwargs stop at the wrapper boundary.
- A new `_validate_model_hint_resolution(fsm, *, orchestration_request_path, host_cli, model_hints) -> list[ValidationError]` in `structural_rules.py`, called from `validate_fsm` — mirrors `FSMExecutor._model_consumer_paths` (static downgrade causes only) and `_resolve_model`'s declaration selection; dedupes `llm.model_hint` warnings per (hint, backend). The predicates are duplicated from the executor on purpose (validation does not import `executor`); nothing shares them, so the validate-vs-`_preflight_model_hints` agreement test is what catches divergence. Name is a suggestion; line anchors throughout this issue drift — locate by symbol name.

### Call Path

- `ll-loop validate` (`cmd_validate` in `cli/loop/config_cmds.py`) → `load_and_validate(..., orchestration_request_path=, host_cli=, model_hints=)` → `validate_fsm` → `_validate_model_hint_resolution` → `resolve_model_hint` (per consumer path) → WARNING
- `host_cli` is `resolve_host().name` (env + probe, identical to run time — see Decisions), or `None` on `HostNotConfigured`. `model_hints` comes from `BRConfig(...).orchestration.model_hints`. Both are read at the same site that reads `.orchestration.request_path` today.
- `_cmd_fleet_review()` in `cli/logs.py` → `_validate_builtin_loop` (gains the same two kwargs) → `load_and_validate(..., host_cli=, model_hints=)`. In-process callers `cli/loop/scaffold_eval.py:278` and `scaffold_verify.py:340` stay unchanged and skip resolution warnings.
- Other `load_and_validate` callers (`cli/doctor.py:688`'s fleet-wide validate, `cli/loop/run.py:146`, `cli/loop/info.py:1472`, `cli/loop/edit_routes.py:51`, `fsm/loop_paths.py:104,128`, `fsm/executor.py:1163`) are **not** touched by this issue; they keep calling without `host_cli`/`model_hints`, so `host_cli=None`'s default skips resolution warnings there and behavior is unchanged. `cli/doctor.py` in particular validates every runnable built-in loop and is a plausible second surface for these warnings — deliberately deferred here, not an oversight; revisit as a fast-follow if fleet-wide hint-resolution coverage is wanted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- **Host source (decided — see Decisions).** `resolve_host()` reads only `LL_HOST_CLI`, `LL_HOOK_HOST` and the `_PROBE_ORDER` PATH probe; it does **not** read `orchestration.host_cli` today (BUG-3644, whose selected fix folds the config key into `resolve_host()`). The runtime preflight (`FSMExecutor._preflight_model_hints` → `_resolve_model`) uses `resolve_host()`, so validate calls it too and follows BUG-3644 automatically. Do not read `cfg.orchestration.host_cli` directly the way `doctor.py` (~815) does.
- **Reachable-path rules already exist at runtime and are side-effect free**: `FSMExecutor._configured_request_path`, `_compute_request_path` (static downgrade causes: `_SKILL_INVOKE_RE` match on the action, truthy `tools`; environmental causes: `anthropic` not importable, no credentials), `_model_consumer_paths` (returns `[]` for terminal, sub-loop and `human_approval` states; a `type: learning` state is treated as a slash-command prompt — CLI-only after BUG-3646; evaluator path only when `next` is unset and `llm.enabled`, for an implicit prompt-state verdict or explicit `llm_structured`; shell + `llm_structured` → evaluator only). `fsm/validation` deliberately mirrors executor predicates instead of importing executor (comments at `structural_rules.py` ~425/~440) but does import `_SKILL_INVOKE_RE` from `_base.py`. Validation can decide only the static causes; environmental downgrades are unknowable at validate time.
- **Existing ENH-3527 structural hint checks**: `_validate_model_hint_decl(state_name, state)` (called from `_validate_state_action`) emits ERRORs for vocabulary, `model`/`model_hint` exclusivity and inapplicable states via `_consumes_model_hint`; loop-level `llm.model_hint` checks are inline in `validate_fsm` (ERROR for vocabulary, WARNING when no state consumes a model). None has a `*_ok` suppression flag.
- **WARNING conventions**: rules are `_validate_*` functions returning `list[ValidationError]`, extended into `validate_fsm`; WARNINGs set `severity=ValidationSeverity.WARNING` explicitly (default is ERROR); paths are `states.<name>.<field>` or `llm.model_hint`; messages carry a `[state: <name>]` prefix and an issue-ID tag; `KNOWN_TOP_LEVEL_KEYS` in `_base.py` registers any `*_ok` flag. `resolve_model_hint` raises `ModelHintError` (a `ValueError`) for unknown hint, unknown backend, unsupported backend (`opencode`, `pi`), config-disabled (`False`) and missing mapping; `hint_backend_keys()` lists valid backends.
- **Severity asymmetry**: an unmapped hint on a reachable path is a run-ending ERROR at run start (`_preflight_model_hints`, `model_hint_error=True`) but only a WARNING at validate time here — intentional per the issue, since host and config vary by machine.
- **Config plumbing**: `BRConfig(...).orchestration.model_hints` is already validated at config load (`_validate_model_hints`) and typed `dict[str, dict[str, str | Literal[False]]]`; `initial_model_display` (`cli/loop/header.py`) is the existing non-raising consumer that catches `HostNotConfigured` and `ModelHintError` — evidence that host-not-configured is expected to degrade, not raise, outside the executor.
- **Decision Rules** (new gap kind: hint-resolution WARNING) — inputs: state, `fsm.llm`, `host_cli`, `model_hints`. A hint is checked per reachable consumer path: `sdk`/`batch` request path → `anthropic-api` backend plus the CLI host (fallback); `cli` → CLI host; evaluator (explicit `llm_structured` or implicit prompt verdict) → CLI host only, never `anthropic-api`; `/ll:` skill action or `tools:` → CLI only. No warning when `host_cli is None`. No escape hatch: ARCH-121 exemption decided (see Decisions). The host-source question above is also decided: `resolve_host()` (see Decisions, BUG-3644).

## Integration Map

- `scripts/little_loops/fsm/validation/{structural_rules,evaluator_rules}.py`.
- `validate_fsm` / `load_and_validate` plumbing and callers: `cli/loop/config_cmds.py`, `cli/logs.py`.
- Tests: `test_fsm_validation_structural.py`, `test_fsm_validation_evaluator_rules.py`, `test_wiring_reference_docs.py`, plus a `ll-loop validate` CLI-level test of the WARNING output.
- Docs are end-user docs (`docs/guides`, `docs/reference`): use consuming-project paths, no `scripts/tests/` citations (`test_docs_audience_gate.py`).

### Integration Research

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- **Missing `load_and_validate` callers** (not in the issue's Call Path; they stay on `host_cli=None`, so unchanged): `fsm/validation/structural_rules.py:297` (child-loop load) and `cli/artifact/policy_revision.py:95`. All other listed line anchors still hold (`run.py:146` is now `:147`).
- **Invariant the new kwargs must respect**: `test_ll_logs.py` (~6085-6108) calls `_validate_builtin_loop(name, orchestration_request_path=None)` and compares against a direct `load_and_validate(path, raise_on_error=False, orchestration_request_path=None)`. The new kwargs need defaults so these keep passing. `scripts/tests/spike/enh3342_scan_action_file_param/test_file_param.py` (`test_real_call_sites_have_no_file_path_available_for_validate_fsm`) asserts `validate_fsm`'s parameter set is exactly `{fsm, orchestration_request_path}` — it will fail on the signature change and its own message says to re-check the spike; it must be updated deliberately, not skipped.
- **Existing hint tests live in `scripts/tests/test_model_hints.py`** (`TestStructuralValidation`, `TestPreflight`, `TestEvaluatorDispatch`, helpers `_fsm`/`_errors`, `no_host` fixture), not in the two validation test files named above — those contain no hint coverage today. CLI-level warning tests follow `test_ll_loop_commands.py` (~111, ~326, ~369): non-JSON asserts through `caplog` (warnings are only `logger.warning`-ed when `raise_on_error=True`), `--json` asserts on `violations[].message`; both `cmd_validate` branches are conventionally covered.
- **Current Behavior claim "no docs describe hints" is partly stale.** Partial coverage exists in `docs/reference/CONFIGURATION.md` (~1370, `orchestration.model_hints` row), `docs/reference/CLI.md` (~936-968, model header/`unresolved` forms) and `docs/reference/EVENT-SCHEMA.md` (~229). None of `docs/guides/LOOPS_GUIDE.md` (~610-629 field table, no `model_hint` row), `docs/generalized-fsm-loop.md` (~404-409 `llm:` block), `docs/reference/API.md`, `docs/reference/HOST_COMPATIBILITY.md` (`## Orchestration CLI`) or `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (~113 `haiku-gen` row) mention hints. `API.md` documents `load_and_validate`'s `orchestration_request_path` as `Path | None`, contradicting the code's `str | None`.
- **Docs gates**: `test_wiring_reference_docs.py` is a tuple registry (`DOC_STRINGS_PRESENT` entries of doc path, needle, issue ID) with no hint needle today; `docs/generalized-fsm-loop.md` sits outside `test_docs_audience_gate.py`'s scope (`docs/guides`, `docs/reference`, `README.md`). Citing `scripts/little_loops/` in user docs is not flagged by that gate (only `scripts/tests` and the other listed markers are), but the audience rule still prefers dotted-module citations.
- **`haiku-gen` today** is `_validate_haiku_pinned_generator` (`evaluator_rules.py` ~520): keys only on `state.model` containing `haiku`, skips `_is_llm_judged` states, suppressed by `haiku_generator_ok`. It never reads `model_hint`, so a hint-only `burst` generator state is currently unflagged; `burst` aliases to `haiku` on the `anthropic-api` backend (`host_runner.py` `_HINT_ALIASES`).

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/structural_rules.py:2035` — `load_and_validate()` forwards `validate_fsm(fsm, orchestration_request_path)` positionally; add `host_cli`/`model_hints` keyword params and pass them by keyword in `load_and_validate()` [Agent 1 finding]
- `scripts/little_loops/fsm/validation/structural_rules.py:500` — `_validate_state_action()` is where `_validate_model_hint_decl()` runs per state; per-state resolution warnings need the two new values threaded here (or a sibling pass over `fsm.states` in `validate_fsm()`) [Agent 1 finding]
- `scripts/little_loops/fsm/validation/structural_rules.py:1320` — `llm.model_hint` inline checks in `validate_fsm()`; the loop-level hint is resolution-checked on the evaluator path (CLI host) and on `sdk`/`batch` states without a state-level declaration (`anthropic-api`), deduped per (hint, backend) — see Expected Behavior (corrected 2026-09-28: it is not evaluator-only) [Agent 1 finding]
- `scripts/little_loops/fsm/validation/evaluator_rules.py:520` — `_validate_haiku_pinned_generator()` keys only on `state.model`; extend for hint-only `burst` (`model_hint`), keeping `haiku_generator_ok` suppression, `_is_llm_judged` skip and exactly one WARNING for a `model:`-only state [Agent 1, 3 finding]
- `scripts/little_loops/cli/loop/config_cmds.py:25` — `cmd_validate()` reads `BRConfig(Path.cwd()).orchestration.request_path` before its `try:` and calls `load_and_validate` at `:33`; read `orchestration.model_hints` and derive `host_cli` at the same site and pass both [Agent 1, 2 finding]
- `scripts/little_loops/cli/logs.py:2326` — `_validate_builtin_loop()` has `orchestration_request_path` as a required keyword-only arg with no default; add `host_cli`/`model_hints` **with defaults** and forward to its `load_and_validate` call [Agent 1, 3 finding]
- `scripts/little_loops/cli/logs.py:2761` — `_cmd_fleet_review()` reads `BRConfig(Path.cwd()).orchestration.request_path` once and calls `_validate_builtin_loop` per loop at `:2764`; read the two new values at that site [Agent 1, 2 finding]
- `scripts/little_loops/fsm/validation/__init__.py:77` — module docstring (lines 27-38) documents the `validate_fsm`/`load_and_validate` signatures; refresh it, and add any new `_validate_*` helper to both the import block and `__all__` (`:246` region) per the existing convention [Agent 1, 2 finding]
- `scripts/little_loops/fsm/validation/_base.py:132` — `KNOWN_TOP_LEVEL_KEYS` (only if a `*_ok` suppression flag is added; also needs `FSMLoop` field + `to_dict`/`from_dict` in `fsm/schema.py:1494/1643/1768`). See Configuration note on ARCH-121 [Agent 1, 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:3745` — `_model_consumer_paths()` in `FSMExecutor` (with `_configured_request_path` at `:3560`, `_compute_request_path` at `:3568`, `_preflight_model_hints` at `:3721`) is the runtime predicate set validation must mirror; reference only, not modified [Agent 1, 2 finding]
- `scripts/little_loops/cli/loop/header.py:140` — `initial_model_display()` is the closest non-raising consumer (catches `HostNotConfigured` and `ModelHintError`); pattern for the host-not-configured degrade path, not modified [Agent 1, 3 finding]
- `scripts/little_loops/host_runner.py:2932` — `apply_host_cli_from_config()` (sole production caller `cli/doctor.py:1438`) copies `orchestration.host_cli` into `LL_HOST_CLI`; reference only — `cmd_validate` calls neither it nor `cfg.orchestration.host_cli`, only `resolve_host()` (see Decisions; BUG-3644 owns the config bridge) [Agent 2 finding]
- `scripts/little_loops/cli/artifact/policy_revision.py:95` — `load_and_validate` caller in the policy-validation flow; collects WARNING `v.message` into `ValidationOutcome.warnings`; stays on `host_cli=None`, so unchanged, but a host-independent hint-only `haiku-gen` WARNING would flow into it [Agent 2 finding]
- `scripts/little_loops/cli/loop/scaffold_eval.py:278` and `scaffold_verify.py:340` — `validate_fsm` callers that put every violation, warnings included, into `ScaffoldResult.errors` strings; scaffolded loops declare no hints, so a hint-only `haiku-gen` extension cannot fire there [Agent 2 finding]
- `scripts/little_loops/fleet_improve.py:657` — `gate()` compares `warning_count()` (`:408`) from `validate_loop()` (`:396`, runs `ll-loop validate <yaml> --json`) against a baseline and fails when warnings grow; a resolution WARNING firing after an edit but not before would veto it. No built-in loop declares `model_hint`, so no shipped loop is affected [Agent 2 finding]
- `scripts/little_loops/loops/workflow-generator.yaml` — `validate_artifact`, `record_baseline` and `shrink_probe_candidate` states parse `ll-loop validate --json` violations; the shrink probe compares a `(terminal, errors, warning count)` tuple for byte-identity, so a hint-resolution WARNING that appears or disappears when a state is excised changes the count [Agent 2 finding]
- `scripts/little_loops/fsm/validation/structural_rules.py:297` — `load_and_validate` child-loop load in `_validate_with_bindings()`; stays on `host_cli=None`, so unchanged [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:6684` — `validate_fsm` signature and `Parameters:` list in `validate_fsm`; `:6734-6738` `load_and_validate` documents `orchestration_request_path` as `Path | None`, contradicting the code's `str | None`; the "Checks performed" list (`:6689-6711`) has no hint-resolution or `haiku-gen` entry [Agent 2, 3 finding]
- `docs/reference/CLI.md:1104-1129` — `#### ll-loop validate` rule list, with the rule-to-suppression-flag paragraph at `:1122`; add the hint-resolution WARNING (and its escape hatch if one is added) [Agent 2 finding]
- `docs/ARCHITECTURE.md:259` — `validation/` tree line lists "MR-1..MR-6, MR-8/MR-10/MR-12/MR-13 + haiku-gen"; refresh only if a new rule family is added; lines 919-924 describe `resolve_host()`/`apply_host_cli_from_config()` [Agent 1, 2 finding]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:113` — `haiku-gen` row: add the hint-only `burst` case. `:455` lists MR rule severities. **Do not edit `:486`** (the `resolve_host()` precedence claim) — BUG-3644 makes it true and owns it (see Scope Boundaries) [Agent 2 finding]
- `skills/review-loop/reference.md:17` — `## First-Pass Checks (from ll-loop validate)` table has no `haiku-gen` or hint-resolution row (last row `MR-14`, `:53`). This is a skill mirror; if edited, regenerate host mirrors with `ll-adapt --host <gemini|kimi-code|qwen> --apply`. Skills execute inside the consuming project, so cite `little_loops.<module>` and no `scripts/` paths [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md:461` — `## Orchestration CLI` is the natural home for the support matrix, sitting between the parity-gated `## Adapter Host Capabilities` (`:389`) and `## Config probe path` (`:512`); the matrix must not add rows or `##` headings that alter those two sections (`test_verify_host_map.py` parses `## Adapter Host Capabilities`; `test_wiring_guides_and_meta.py` parses `## Host tiers` rows) [Agent 2, 3 finding]
- `docs/reference/CONFIGURATION.md:1368-1370` — `orchestration.host_cli` and `model_hints` rows; the `model_hints` row's "stops the run at start" wording should note the validate-time WARNING counterpart [Agent 2 finding]
- `scripts/little_loops/config-schema.json:1806` and `:1811` — `orchestration` and `host_cli` descriptions; **not edited here** — BUG-3644 owns them (see Scope Boundaries) [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md:229` — `model_requested` row mentions `model_hint`; already covered, no change expected [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/spike/enh3342_scan_action_file_param/test_file_param.py:40` — `test_real_call_sites_have_no_file_path_available_for_validate_fsm` in `TestNoRealPathAvailableAtCallSites` asserts `set(inspect.signature(validate_fsm).parameters) == {"fsm", "orchestration_request_path"}`; will fail on the signature change. Update the set to include `host_cli` and `model_hints` deliberately (the spike's premise, that no file path reaches `validate_fsm`, still holds); do not skip [Agent 3 finding]
- `scripts/tests/test_ll_logs.py:6093` — `test_validate_builtin_loop_matches_load_and_validate_directly` compares `_validate_builtin_loop` against a direct `load_and_validate`; pass the same `host_cli`/`model_hints` to both sides. `:6085` `test_validate_builtin_loop_unknown_name` and `:6106` `test_validate_builtin_loop_nested_oracle_resolves` break with `TypeError` if the new kwargs are required, so give them defaults [Agent 2, 3 finding]
- `scripts/tests/test_fsm_validation_evaluator_rules.py:42` — `TestHaikuPinnedGenerator`: add hint-only `model_hint="burst"` fires, `haiku_generator_ok` suppresses, `llm_structured` verdict state does not fire; keep `test_haiku_generator_ok_recognized_as_top_level_key` at exactly one WARNING for a `model:`-only state. Closest kwarg-gated-warning precedent is the MR-12 request-path class containing `test_config_request_path_sdk_via_validate_fsm_still_fires` (`:916`) [Agent 3 finding]
- `scripts/tests/test_model_hints.py:225` — `TestStructuralValidation`: add the resolution matrix (unmapped on `codex`, `claude-code` built-in silent, `False`-disabled, `opencode`/`pi` unsupported, `sdk`/`batch` → `anthropic-api`, evaluator-only CLI check, `/ll:`/`tools:` CLI-only, `host_cli=None` silent). `_errors()` calls `validate_fsm(fsm)` with no kwargs and callers pass `severity` positionally (`:272`, `:275`), so add a new helper or append new kwargs after `severity`. `TestPortabilityProof` (`:1039`, loop with `coding` and `burst` hints via `load_and_validate(path)`) must stay silent on the default and is a ready fixture [Agent 3 finding]
- `scripts/tests/test_ll_loop_commands.py:326` — `cmd_validate` CLI-level WARNING tests: non-JSON asserts via `caplog` (`:326-367`), `--json` asserts on `violations[].message` (`:369-405`); write `.ll/ll-config.json` with `orchestration.model_hints` and pin the host via `LL_HOST_CLI` monkeypatch or a `resolve_host` patch. The existing `test_validate_json_output_valid_loop` (`:201`) asserts `violations == []` and stays safe only while no-hint loops emit nothing new [Agent 3 finding]
- `scripts/tests/test_wiring_reference_docs.py:20` — `DOC_STRINGS_PRESENT` registry: add `(doc, needle, "ENH-3548")` tuples for the changed reference docs; `docs/guides/LOOPS_GUIDE.md` and `docs/reference/HOST_COMPATIBILITY.md` entries live in `test_wiring_guides_and_meta.py:97-117` [Agent 2, 3 finding]
- `scripts/tests/test_builtin_loops.py:16167` — `TestValidatorWarningBudget` ratchet maps warning message substrings to `CATEGORY_PATTERNS`; decided: no pattern for hint-resolution warnings (see Decisions). No change [Agent 2, 3 finding]
- `scripts/tests/test_verify_host_map.py:63` — `TestCheckDocParity::test_current_tree_has_no_mismatch` guards `HOST_COMPATIBILITY.md`'s Adapter Host Capabilities table; run after the docs pass [Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `.ll/decisions.yaml` ARCH-121 (`enforcement: advisory`) — "Every new `ll-loop validate` ERROR/WARNING rule must be paired with a named boolean suppression flag on the `FSMLoop` schema"; this issue currently adds none, so record the decision either way (add a `*_ok` flag with `_base.py`/`schema.py` plumbing, or record why hint-resolution warnings are exempt because they are host-dependent) [Agent 2 finding]
- `scripts/little_loops/config/orchestration.py:120` — `OrchestrationConfig.host_cli` (`:120`), `model_hints` (`:128`) and `_validate_model_hints` (`:62`); `cmd_validate` builds `BRConfig` before its `try:`, so a config `ValueError` from `_validate_model_hints` escapes uncaught there today [Agent 2 finding]

### Inferred, unconfirmed

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/`, `.qwen/`, `.kimi-code/` mirrors of `skills/review-loop/reference.md` — existence not verified; only relevant if that skill file is edited
- `site/reference/API/index.html` — generated mkdocs output showing `validate_fsm(fsm)`; git-tracked status not determined

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Write first (tdd_mode)**: the agreement test from the `cmd_validate` acceptance criterion. It is the only guard against drift between the validation mirror and the executor predicates, so it lands before `_validate_model_hint_resolution`. Setup, so it is deterministic on every machine:
  - pin the host via `LL_HOST_CLI`;
  - pin the environmental downgrades: monkeypatch `FSMExecutor._sdk_credentials_available` to True and make sure `anthropic` imports (or skip the sdk cases when it does not);
  - build the executor with an `OrchestrationConfig` carrying the same `request_path` and `model_hints` that validate receives, and no `run_model`.
  - Assertions (not literal equality — the preflight returns only the **first** error string, and validate deliberately checks more for `sdk`/`batch` states): (a) whenever `_preflight_model_hints` returns an error for state `S`, validate emits a hint-resolution WARNING for `S` (or at `llm.model_hint` when that is the failing declaration); (b) for fixtures whose states take only CLI/evaluator paths, preflight returns `None` ⇔ validate emits no resolution warning.
  - Matrix: `cli`/`sdk`/`evaluator` paths, `/ll:` skill and `tools:` downgrades, a literal-`model:` state with an evaluator path under `llm.model_hint`, and a `type: learning` state under `request_path: sdk` (both sides resolve it against the CLI host only).
- Update `scripts/little_loops/fsm/validation/structural_rules.py` `load_and_validate()` (`:2035`) — add `host_cli`/`model_hints` keyword params and forward them to `validate_fsm`
- Update `scripts/little_loops/cli/logs.py` `_validate_builtin_loop()` (`:2326`) and `_cmd_fleet_review()` (`:2761`) — new kwargs with defaults; read both values where `orchestration.request_path` is read
- Update `scripts/little_loops/cli/loop/config_cmds.py` `cmd_validate()` — read `model_hints`, derive `host_cli` via `resolve_host().name` (catch `HostNotConfigured` → `None`; see Decisions); move the `BRConfig` read inside error handling so an invalid `orchestration.model_hints` exits 1 with a validate error (see Decisions)
- Update `scripts/little_loops/fsm/validation/evaluator_rules.py` `_validate_haiku_pinned_generator()` (`:520`) — hint-only `burst` guidance
- Update `scripts/little_loops/fsm/validation/__init__.py` — docstring and any new helper in imports and `__all__`
- Update `scripts/tests/spike/enh3342_scan_action_file_param/test_file_param.py` — the pinned `validate_fsm` parameter set
- Update `scripts/tests/test_ll_logs.py` `test_validate_builtin_loop_matches_load_and_validate_directly` — pass matching new kwargs on both sides
- Add tests in `test_model_hints.py`, `test_fsm_validation_evaluator_rules.py`, `test_ll_loop_commands.py` and `DOC_STRINGS_PRESENT` entries in `test_wiring_reference_docs.py` / `test_wiring_guides_and_meta.py`
- Update `docs/reference/API.md` (fix `Path | None` → `str | None`), `docs/reference/CLI.md`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/CONFIGURATION.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (`haiku-gen` row only — not `:486`), `skills/review-loop/reference.md`. Leave `config-schema.json` host descriptions to BUG-3644
- ARCH-121: decided — exemption recorded, no `*_ok` flag (see Decisions); document the exemption in `docs/reference/CLI.md`'s rule-to-suppression-flag paragraph
- Run `ll-adapt --host <gemini|kimi-code|qwen> --apply` if `skills/review-loop/reference.md` is edited; run `test_verify_host_map.py` and `test_docs_audience_gate.py` after the docs pass

## Impact

- **Priority**: P3.
- **Effort**: Medium — ~8 code sites (warnings plus `validate_fsm`/`load_and_validate` plumbing), ~7 test files and a docs pass across ~8 files.
- **Risk**: Low.

## Acceptance Criteria

- [x] Warnings fire for an unmapped hint on a reachable request path and not when every path resolves; downgrade-only states produce no SDK warning.
- [x] An evaluator-only hint on a `request_path: sdk` state is checked against the CLI host only (no `anthropic-api` warning).
- [x] `llm.model_hint` is checked on the evaluator path (CLI host) and on `sdk`/`batch` states with no state-level declaration (`anthropic-api`), never on the CLI fallback; an unresolvable `llm.model_hint` produces exactly one WARNING per (hint, backend) at `path=llm.model_hint`.
- [x] `cmd_validate` derives `host_cli` from `resolve_host()` (not `orchestration.host_cli` directly); with no host found it emits no resolution warnings and does not error. A test pins the host via `LL_HOST_CLI` and asserts validate and `_preflight_model_hints` agree on the same loop.
- [x] `validate_fsm`/`load_and_validate` accept `host_cli`/`model_hints`; with `host_cli=None`, no resolution warnings fire and existing callers' output is unchanged.
- [x] An out-of-vocabulary hint produces only ENH-3527's vocabulary ERROR, no resolution WARNING.
- [x] A literal-`model:` state on the evaluator path does not warn about an unresolvable `llm.model_hint`; a `type: learning` state gets no evaluator-path check and is checked against the CLI host only, under any `request_path` (never `anthropic-api`). _(Correction 2026-09-28: the evaluator-path half holds. The CLI-only half does not: under `sdk`/`batch` the shipped mirror also checks `anthropic-api`, matching the unfixed executor. Delivered by BUG-3646.)_
- [x] `ll-loop validate` with an invalid `orchestration.model_hints` exits 1 with a validate error instead of an uncaught `ValueError`.
- [x] `haiku-gen` fires for a generator state with `model_hint: burst`, not for a `burst` verdict state (`_is_llm_judged`), is suppressed by `haiku_generator_ok`, and still emits exactly one WARNING for a `model:`-only haiku state.
- [x] `ll-loop validate` surfaces the resolution WARNING in both the plain (`caplog`) and `--json` (`violations[].message`) output branches.
- [x] Vocabulary semantics, support matrix, precedence, the Known limitations above and the skill/agent frontmatter hint scope (ENH-3533, done) are documented in `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/reference/{API,CLI,HOST_COMPATIBILITY,CONFIGURATION}.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` and `skills/review-loop/reference.md`.

## Status

**Done** | Created: 2026-09-24 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers validate-time WARNINGs, `haiku-gen` guidance, and documentation only. Resolver/config is ENH-3527 (done) and dispatch wiring is ENH-3547 (done). ENH-3527 dropped the `operation` parameter (2026-09-24). ENH-3547 proved the support matrix with tests that this issue's docs describe; both prerequisites have since landed, so this issue is no longer blocked.


## Resolution

**Completed** 2026-09-29.

- `structural_rules.py`: new `_is_prompt_action`, `_static_model_paths` and `_validate_model_hint_resolution` (mirrors `FSMExecutor._preflight_model_hints` per state/path, static downgrade causes only); `validate_fsm` and `load_and_validate` gained keyword-only `host_cli` / `model_hints` (`host_cli=None` skips resolution warnings, so other callers are unchanged).
- `evaluator_rules.py`: `haiku-gen` also flags a generator state with `model_hint: burst`.
- `cmd_validate` derives `host_cli` from `resolve_host()` (`HostNotConfigured` → `None`), reads `orchestration.model_hints`, and reports an invalid config as a validate error (exit 1). `_validate_builtin_loop` / `_cmd_fleet_review` in `cli/logs.py` forward the same values.
- Tests: resolution matrix and a validate-vs-preflight agreement test in `test_model_hints.py`; `haiku-gen` cases; `cmd_validate` CLI tests (plain and `--json`, no-host, invalid config); pinned-signature spike and `test_ll_logs.py` updated; doc-presence registry entries. Full suite: 27095 passed, 292 skipped.
- Docs: new `Loop model_hint support matrix` in `HOST_COMPATIBILITY.md`; `API.md`, `CLI.md`, `CONFIGURATION.md`, `LOOPS_GUIDE.md`, `generalized-fsm-loop.md`, `HARNESS_OPTIMIZATION_GUIDE.md`, `skills/review-loop/reference.md`. `API.md`'s `Path | None` corrected to `str | None`.
- Deviation from the plan: no separate plan file was written (the issue's Program Design served as the plan); `ll-adapt --apply` for gemini/kimi-code/qwen adapted 0 files.
- **Known gap (added 2026-09-28 by manual review):** landed before its `blocked_by` BUG-3646. `_static_model_paths`'s learning branch calls `action_paths(state.action)`; `state.action` is `None` for a learning state, so under `sdk`/`batch` it yields `[("sdk", False), ("cli", True)]`, which mirrors the unfixed executor rather than the CLI-only spec. `test_agreement` exempts `"learning"` from the strict check. BUG-3646 changes the branch to `[("cli", False)]` and removes the exemption. The stale `blocked_by` edge was dropped.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-28_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Concerns
- Line anchors are call-site/body lines, not definition lines, and still hold (`structural_rules.py:2035` is the `validate_fsm` forwarding call inside `load_and_validate`, defined at `:1944`; `config_cmds.py:25` is the `BRConfig` read inside `cmd_validate`, defined at `:14`); still locate by symbol name at implementation time.

### Outcome Risk Factors
- Broad enumeration across ~8 code sites, ~8 docs and ~7 test files, plus moderate per-site complexity in mirroring executor request-path predicates (`_model_consumer_paths`, `_compute_request_path`) inside validation.
- Wide dependent surface (~11 `load_and_validate` callers, `fleet_improve.gate()` and `workflow-generator.yaml` warning-count comparisons); new kwargs need defaults, and the pinned parameter set in `spike/enh3342_scan_action_file_param` must be updated deliberately.

## Verification Notes

_Added by `/ll:verify-issues` on 2026-09-28 (`--auto`)._

Verdict at time of check: **NEEDS_UPDATE** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- **Corrected**: the Confidence Check Notes concern claimed line anchors had drifted (`load_and_validate` `:2035`→`:1944`, `cmd_validate` `:25`→`:14`). Those figures are the definition lines; the issue's anchors point at body lines (`:2035` forwarding call, `:25` `BRConfig` read) that still hold. Concern rewritten in place.
- **Verified accurate**: `_model_consumer_paths` / `_resolve_model` / `_preflight_model_hints` behavior matches the per-path declaration-selection rules; `resolve_host()` ignores `orchestration.host_cli` (only `cli/doctor.py:815,1438` use it); all `load_and_validate` caller anchors (`doctor.py:688`, `run.py:147`, `info.py:1472`, `edit_routes.py:51`, `loop_paths.py:104,128`, `executor.py:1163`, `structural_rules.py:297`, `policy_revision.py:95`); `logs.py:2326/2761`; `evaluator_rules.py:520`; test anchors (`test_ll_logs.py:6085-6108`, `test_model_hints.py` classes, `TestHaikuPinnedGenerator`, spike test pinning `{"fsm", "orchestration_request_path"}`); docs anchors (`API.md:6684/6737` `Path | None` mismatch, `HOST_COMPATIBILITY.md` section order, `HARNESS_OPTIMIZATION_GUIDE.md:113/486`, `config-schema.json:1806/1811`, `review-loop/reference.md:53`); no hint docs in `LOOPS_GUIDE.md`, `generalized-fsm-loop.md`, `API.md`, `HOST_COMPATIBILITY.md`.
- **Dependencies**: ENH-3527, ENH-3547, ENH-3533 done; EPIC-3563, BUG-3644 open (references only). BUG-3646 added as a `blocked_by` edge on 2026-09-28 (manual review) so the learning-state mirror is written against the fixed executor. No broken refs.
- **Checks with no findings**: `ll-verify-evidence` clean; `ll-issues format-check` clean; no active required decision rules; ARCH-121 exemption entry `514b7ae3-…` present; Proposed-Solution consequence check (B6) found no exception-handler, fixture or AC-coverage gap. Graph-assisted checks not needed (no negative claims); provider `codegraph`, freshness `fresh`.

## Resolved Concerns

- [resolved 2026-09-28 by manual review] Host source for `cmd_validate` was undecided (`resolve_host()` ignores `orchestration.host_cli`) — decided: `resolve_host()` (env + probe), identical to run time; see Decisions and BUG-3644.
- [resolved 2026-09-28 by manual review] ARCH-121 requires a `*_ok` suppression flag for every new validate rule — decided: exemption for host-dependent hint-resolution warnings, recorded as decisions entry `514b7ae3-90e7-4894-af36-460b00bb1278`.

## Session Log
- `manual review` - 2026-09-28 - post-completion: dropped stale `blocked_by: [BUG-3646]`; recorded that the learning-state CLI-only mirror was not delivered (AC correction + Resolution known gap); BUG-3646 owns it
- `/ll:manage-issue` - 2026-09-29T00:04:57 - `9f6d1486-da8d-460c-9ae8-dad3ff47feac.jsonl`
- `manual review` - 2026-09-28 - added `blocked_by: [BUG-3646]`; learning states are now CLI-only in Expected Behavior, the agreement-test matrix and the ACs (no interim `anthropic-api` mirror)
- `/ll:ready-issue` - 2026-09-28T23:51:11 - `1e35f0ba-f9a3-4b2b-9bb2-0165c66c87c5.jsonl`
- `/ll:confidence-check` - 2026-09-28T22:54:42 - `30920171-b2d1-4a65-8976-6add0126d6fe.jsonl`
- `manual review` - 2026-09-28 - corrected evaluator-path `model` precedence and learning-state path rules (filed BUG-3646); added prompt-mode gate, out-of-vocab skip, contributed-action limitation, remediation text in messages; made agreement test deterministic; decided invalid-config and warning-budget handling; removed BUG-3644-owned doc/schema edits
- `/ll:confidence-check` - 2026-09-28T22:43:47 - `9b0a9144-bbd1-46a6-aca5-08f4cec9c484.jsonl`
- `/ll:verify-issues` - 2026-09-28T22:41:26 - `5fafe6c4-1e0c-4610-a069-76b4dd11d35b.jsonl`
- `/ll:confidence-check` - 2026-09-28T22:35:13 - `f9845aee-2566-463f-90fc-0809b301aae7.jsonl`
- `manual review` - 2026-09-28 - resolved host source (`resolve_host()`), corrected `llm.model_hint` path rules, added dedupe/limitations/ACs; filed BUG-3644; ARCH-121 exception recorded as decisions entry `514b7ae3-90e7-4894-af36-460b00bb1278`
- `/ll:confidence-check` - 2026-09-28T22:14:19 - `87ecf78a-2679-4eab-bd2f-bc0befce52dd.jsonl`
- `/ll:verify-issues` - 2026-09-28T22:12:49 - `a3a4c5a4-ab00-427b-b444-3be5a159c7cf.jsonl`
- `/ll:wire-issue` - 2026-09-28T22:10:45 - `d53bc120-f664-4e90-8dfa-617508184f55.jsonl`
- `/ll:refine-issue` - 2026-09-28T21:58:46 - `313f4024-8fcf-4417-9f15-70ffc98e80d7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:57 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
