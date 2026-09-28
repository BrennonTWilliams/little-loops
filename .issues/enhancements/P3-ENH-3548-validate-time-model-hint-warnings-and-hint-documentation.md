---
id: ENH-3548
type: ENH
title: Validate-time model hint warnings and hint documentation
priority: P3
status: open
parent: EPIC-3563
epic: EPIC-3563
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:15Z'
verify_verdict: VALID
labels:
- multi-host
- loops
---

# ENH-3548: Validate-time model hint warnings and hint documentation

## Summary

Add `ll-loop validate` warnings for model hints that will not resolve, and document the hint vocabulary, support matrix and precedence. This is piece 3 of ENH-3527's delivery split (its criteria 8 and 10); design details are in ENH-3527 → Config override.

## Current Behavior

- `ll-loop validate` checks `model_hint` vocabulary and exclusivity (ENH-3527) but does not check whether a hint resolves for the configured host.
- No docs describe the hint vocabulary, support matrix or precedence.

## Expected Behavior

- For each declared hint, `ll-loop validate` resolves it against the configured host (`orchestration.host_cli` / `LL_HOST_CLI`) and emits a WARNING, not an error, for any hint that cannot resolve on a reachable request path. For a prompt action, the reachable paths are the state's `request_path` if set, else `orchestration.request_path`, plus the CLI fallback for SDK/batch.
- An evaluator hint (explicit `evaluate:` or the implicit `llm_structured` verdict on a prompt state) is checked against the CLI host only. `fsm/evaluators.py` has no SDK path, so a shell action + `llm_structured` state with `request_path: sdk` must not warn about `anthropic-api`.
- States that always downgrade to CLI (a `/ll:` skill action per `_SKILL_INVOKE_RE`, or `tools:` per BUG-2831) are checked for CLI only.
- When no host or `model_hints` is supplied to validation (the in-process callers below), resolution warnings are skipped. Vocabulary and exclusivity errors from ENH-3527 still fire.
- `haiku-gen` guidance covers hint-only `burst` generation without rejecting valid `burst` verdict states.

## Scope Boundaries

- **In scope**: validate-time WARNINGs, `haiku-gen` guidance, documentation.
- **Out of scope**: runtime dispatch (ENH-3547); new vocabulary; `cli/doctor.py`'s fleet-wide `load_and_validate` sweep (deferred — see Call Path).

## Program Design

### Types

- No new types.

### Signatures

- `resolve_model_hint(hint, *, backend, overrides=None) -> str` — from ENH-3527; validation catches its error and emits a WARNING.
- `validate_fsm(fsm: FSMLoop, orchestration_request_path: str | None = None, *, host_cli: str | None = None, model_hints: dict[str, dict[str, str | Literal[False]]] | None = None) -> list[ValidationError]` — extends the existing signature (`structural_rules.py:1169`, drifts with the file — confirm at implementation time) with the two keyword args; `host_cli=None` skips resolution warnings.
- `load_and_validate(...)` — gains the same two keyword args and forwards them, mirroring how `orchestration_request_path` is threaded today.
- `cli/logs.py`'s `_validate_builtin_loop(...)` helper (`logs.py:2326`) — the fleet-review call site at `logs.py:2761` does not call `load_and_validate` directly; it goes through this wrapper. The wrapper's own signature must also gain `host_cli`/`model_hints` and forward them to its `load_and_validate` call, or the two new kwargs stop at the wrapper boundary.

### Call Path

- `ll-loop validate` (`cli/loop/config_cmds.py:25`) → `load_and_validate(..., orchestration_request_path=, host_cli=, model_hints=)` → `validate_fsm` → structural rules → `resolve_model_hint` (per reachable request path) → WARNING
- `host_cli` comes from the host `resolve_host()` would select (`LL_HOST_CLI` / `orchestration.host_cli` / probe order). `model_hints` comes from `BRConfig(...).orchestration.model_hints`. Both are read at the same site that reads `.orchestration.request_path` today.
- `cli/logs.py:2761` (fleet-review) → `_validate_builtin_loop` (`logs.py:2326`, gains the same two kwargs) → `load_and_validate(..., host_cli=, model_hints=)`. In-process callers `cli/loop/scaffold_eval.py:278` and `scaffold_verify.py:340` stay unchanged and skip resolution warnings.
- Other `load_and_validate` callers (`cli/doctor.py:688`'s fleet-wide validate, `cli/loop/run.py:146`, `cli/loop/info.py:1472`, `cli/loop/edit_routes.py:51`, `fsm/loop_paths.py:104,128`, `fsm/executor.py:1163`) are **not** touched by this issue; they keep calling without `host_cli`/`model_hints`, so `host_cli=None`'s default skips resolution warnings there and behavior is unchanged. `cli/doctor.py` in particular validates every runnable built-in loop and is a plausible second surface for these warnings — deliberately deferred here, not an oversight; revisit as a fast-follow if fleet-wide hint-resolution coverage is wanted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- **Host source ≠ what the issue's Call Path says.** `resolve_host()` reads only `LL_HOST_CLI`, `LL_HOOK_HOST` and the `_PROBE_ORDER` PATH probe; it does **not** read `orchestration.host_cli`. `apply_host_cli_from_config()` (which exports it into `LL_HOST_CLI`) is called only from `cli/doctor.py`, not from `cmd_validate`, `cli/logs.py`, `cli/loop/run.py` or `lifecycle.py`. The runtime preflight (`FSMExecutor._preflight_model_hints` → `_resolve_model`) therefore uses env+probe only, while `doctor.py` (~815) reads `cfg.orchestration.host_cli` directly. Contested convention: validate-time warnings must agree with what the run-time preflight will do, or `validate` and `run` disagree about the same loop. Which host source validate uses is a decision to make knowingly.
- **Reachable-path rules already exist at runtime and are side-effect free**: `FSMExecutor._configured_request_path`, `_compute_request_path` (static downgrade causes: `_SKILL_INVOKE_RE` match on the action, truthy `tools`; environmental causes: `anthropic` not importable, no credentials), `_model_consumer_paths` (returns `[]` for terminal, sub-loop and `human_approval` states; a `type: learning` state is treated as a slash-command prompt; evaluator path only when `next` is unset and `llm.enabled`, for an implicit prompt-state verdict or explicit `llm_structured`; shell + `llm_structured` → evaluator only). `fsm/validation` deliberately mirrors executor predicates instead of importing executor (comments at `structural_rules.py` ~425/~440) but does import `_SKILL_INVOKE_RE` from `_base.py`. Validation can decide only the static causes; environmental downgrades are unknowable at validate time.
- **Existing ENH-3527 structural hint checks**: `_validate_model_hint_decl(state_name, state)` (called from `_validate_state_action`) emits ERRORs for vocabulary, `model`/`model_hint` exclusivity and inapplicable states via `_consumes_model_hint`; loop-level `llm.model_hint` checks are inline in `validate_fsm` (ERROR for vocabulary, WARNING when no state consumes a model). None has a `*_ok` suppression flag.
- **WARNING conventions**: rules are `_validate_*` functions returning `list[ValidationError]`, extended into `validate_fsm`; WARNINGs set `severity=ValidationSeverity.WARNING` explicitly (default is ERROR); paths are `states.<name>.<field>` or `llm.model_hint`; messages carry a `[state: <name>]` prefix and an issue-ID tag; `KNOWN_TOP_LEVEL_KEYS` in `_base.py` registers any `*_ok` flag. `resolve_model_hint` raises `ModelHintError` (a `ValueError`) for unknown hint, unknown backend, unsupported backend (`opencode`, `pi`), config-disabled (`False`) and missing mapping; `hint_backend_keys()` lists valid backends.
- **Severity asymmetry**: an unmapped hint on a reachable path is a run-ending ERROR at run start (`_preflight_model_hints`, `model_hint_error=True`) but only a WARNING at validate time here — intentional per the issue, since host and config vary by machine.
- **Config plumbing**: `BRConfig(...).orchestration.model_hints` is already validated at config load (`_validate_model_hints`) and typed `dict[str, dict[str, str | Literal[False]]]`; `initial_model_display` (`cli/loop/header.py`) is the existing non-raising consumer that catches `HostNotConfigured` and `ModelHintError` — evidence that host-not-configured is expected to degrade, not raise, outside the executor.
- **Decision Rules** (new gap kind: hint-resolution WARNING) — inputs: state, `fsm.llm`, `host_cli`, `model_hints`. A hint is checked per reachable consumer path: `sdk`/`batch` request path → `anthropic-api` backend plus the CLI host (fallback); `cli` → CLI host; evaluator (explicit `llm_structured` or implicit prompt verdict) → CLI host only, never `anthropic-api`; `/ll:` skill action or `tools:` → CLI only. No warning when `host_cli is None`. No escape hatch exists in the issue; whether to add a `*_ok` flag is undecided (ENH-3527's hint rules have none).

## Integration Map

- `scripts/little_loops/fsm/validation/{structural_rules,evaluator_rules}.py`.
- `validate_fsm` / `load_and_validate` plumbing and callers: `cli/loop/config_cmds.py`, `cli/logs.py`.
- Tests: `test_fsm_validation_structural.py`, `test_fsm_validation_evaluator_rules.py`, `test_wiring_reference_docs.py`, plus a `ll-loop validate` CLI-level test of the WARNING output.
- Docs are end-user docs (`docs/guides`, `docs/reference`): use consuming-project paths, no `scripts/tests/` citations (`test_docs_audience_gate.py`).

### Codebase Research Findings

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
- `scripts/little_loops/fsm/validation/structural_rules.py:1320` — `llm.model_hint` inline checks in `validate_fsm()`; the loop-level hint gets the same evaluator-path (CLI-only) resolution warning [Agent 1 finding]
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
- `scripts/little_loops/host_runner.py:2932` — `apply_host_cli_from_config()` (sole production caller `cli/doctor.py:1438`) copies `orchestration.host_cli` into `LL_HOST_CLI`; the host-source decision for `cmd_validate` plugs in here or reads `cfg.orchestration.host_cli` directly as `cli/doctor.py:815` does [Agent 2 finding]
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
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:486` — claims `resolve_host()` selects via `LL_HOST_CLI / orchestration.host_cli / probe order`, which the code does not do (see Codebase Research Findings, host source); correct while documenting precedence. `:113` is the `haiku-gen` row and `:455` lists MR rule severities [Agent 2 finding]
- `skills/review-loop/reference.md:17` — `## First-Pass Checks (from ll-loop validate)` table has no `haiku-gen` or hint-resolution row (last row `MR-14`, `:53`). This is a skill mirror; if edited, regenerate host mirrors with `ll-adapt --host <gemini|kimi-code|qwen> --apply`. Skills execute inside the consuming project, so cite `little_loops.<module>` and no `scripts/` paths [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md:461` — `## Orchestration CLI` is the natural home for the support matrix, sitting between the parity-gated `## Adapter Host Capabilities` (`:389`) and `## Config probe path` (`:512`); the matrix must not add rows or `##` headings that alter those two sections (`test_verify_host_map.py` parses `## Adapter Host Capabilities`; `test_wiring_guides_and_meta.py` parses `## Host tiers` rows) [Agent 2, 3 finding]
- `docs/reference/CONFIGURATION.md:1368-1370` — `orchestration.host_cli` and `model_hints` rows; the `model_hints` row's "stops the run at start" wording should note the validate-time WARNING counterpart [Agent 2 finding]
- `scripts/little_loops/config-schema.json:1806` and `:1811` — `orchestration` and `host_cli` descriptions state "read by `apply_host_cli_from_config()` before `resolve_host()` runs" and "env var takes precedence"; align with whichever host source `cmd_validate` adopts [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md:229` — `model_requested` row mentions `model_hint`; already covered, no change expected [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/spike/enh3342_scan_action_file_param/test_file_param.py:40` — `test_real_call_sites_have_no_file_path_available_for_validate_fsm` in `TestNoRealPathAvailableAtCallSites` asserts `set(inspect.signature(validate_fsm).parameters) == {"fsm", "orchestration_request_path"}`; will fail on the signature change. Update the set to include `host_cli` and `model_hints` deliberately (the spike's premise, that no file path reaches `validate_fsm`, still holds); do not skip [Agent 3 finding]
- `scripts/tests/test_ll_logs.py:6093` — `test_validate_builtin_loop_matches_load_and_validate_directly` compares `_validate_builtin_loop` against a direct `load_and_validate`; pass the same `host_cli`/`model_hints` to both sides. `:6085` `test_validate_builtin_loop_unknown_name` and `:6106` `test_validate_builtin_loop_nested_oracle_resolves` break with `TypeError` if the new kwargs are required, so give them defaults [Agent 2, 3 finding]
- `scripts/tests/test_fsm_validation_evaluator_rules.py:42` — `TestHaikuPinnedGenerator`: add hint-only `model_hint="burst"` fires, `haiku_generator_ok` suppresses, `llm_structured` verdict state does not fire; keep `test_haiku_generator_ok_recognized_as_top_level_key` at exactly one WARNING for a `model:`-only state. Closest kwarg-gated-warning precedent is the MR-12 request-path class containing `test_config_request_path_sdk_via_validate_fsm_still_fires` (`:916`) [Agent 3 finding]
- `scripts/tests/test_model_hints.py:225` — `TestStructuralValidation`: add the resolution matrix (unmapped on `codex`, `claude-code` built-in silent, `False`-disabled, `opencode`/`pi` unsupported, `sdk`/`batch` → `anthropic-api`, evaluator-only CLI check, `/ll:`/`tools:` CLI-only, `host_cli=None` silent). `_errors()` calls `validate_fsm(fsm)` with no kwargs and callers pass `severity` positionally (`:272`, `:275`), so add a new helper or append new kwargs after `severity`. `TestPortabilityProof` (`:1039`, loop with `coding` and `burst` hints via `load_and_validate(path)`) must stay silent on the default and is a ready fixture [Agent 3 finding]
- `scripts/tests/test_ll_loop_commands.py:326` — `cmd_validate` CLI-level WARNING tests: non-JSON asserts via `caplog` (`:326-367`), `--json` asserts on `violations[].message` (`:369-405`); write `.ll/ll-config.json` with `orchestration.model_hints` and pin the host via `LL_HOST_CLI` monkeypatch or a `resolve_host` patch. The existing `test_validate_json_output_valid_loop` (`:201`) asserts `violations == []` and stays safe only while no-hint loops emit nothing new [Agent 3 finding]
- `scripts/tests/test_wiring_reference_docs.py:20` — `DOC_STRINGS_PRESENT` registry: add `(doc, needle, "ENH-3548")` tuples for the changed reference docs; `docs/guides/LOOPS_GUIDE.md` and `docs/reference/HOST_COMPATIBILITY.md` entries live in `test_wiring_guides_and_meta.py:97-117` [Agent 2, 3 finding]
- `scripts/tests/test_builtin_loops.py:16167` — `TestValidatorWarningBudget` ratchet maps warning message substrings to `CATEGORY_PATTERNS`; a new hint-warning message is ignored unless a pattern is added, so decide whether it should be ratcheted. No built-in loop declares `model_hint`, so it cannot fire today [Agent 2, 3 finding]
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

- Update `scripts/little_loops/fsm/validation/structural_rules.py` `load_and_validate()` (`:2035`) — add `host_cli`/`model_hints` keyword params and forward them to `validate_fsm`
- Update `scripts/little_loops/cli/logs.py` `_validate_builtin_loop()` (`:2326`) and `_cmd_fleet_review()` (`:2761`) — new kwargs with defaults; read both values where `orchestration.request_path` is read
- Update `scripts/little_loops/cli/loop/config_cmds.py` `cmd_validate()` (`:25`) — read `model_hints`, derive `host_cli` (decide env+probe vs `orchestration.host_cli` knowingly), guard the pre-`try:` config load
- Update `scripts/little_loops/fsm/validation/evaluator_rules.py` `_validate_haiku_pinned_generator()` (`:520`) — hint-only `burst` guidance
- Update `scripts/little_loops/fsm/validation/__init__.py` — docstring and any new helper in imports and `__all__`
- Update `scripts/tests/spike/enh3342_scan_action_file_param/test_file_param.py` — the pinned `validate_fsm` parameter set
- Update `scripts/tests/test_ll_logs.py` `test_validate_builtin_loop_matches_load_and_validate_directly` — pass matching new kwargs on both sides
- Add tests in `test_model_hints.py`, `test_fsm_validation_evaluator_rules.py`, `test_ll_loop_commands.py` and `DOC_STRINGS_PRESENT` entries in `test_wiring_reference_docs.py` / `test_wiring_guides_and_meta.py`
- Update `docs/reference/API.md` (fix `Path | None` → `str | None`), `docs/reference/CLI.md`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/CONFIGURATION.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `skills/review-loop/reference.md`
- Decide and record the ARCH-121 suppression-flag question before finalizing the rule (add `*_ok` in `_base.py`/`fsm/schema.py`, or document the exemption)
- Run `ll-adapt --host <gemini|kimi-code|qwen> --apply` if `skills/review-loop/reference.md` is edited; run `test_verify_host_map.py` and `test_docs_audience_gate.py` after the docs pass

## Impact

- **Priority**: P3.
- **Effort**: Small (warnings plus `validate_fsm`/`load_and_validate` plumbing) plus a docs pass across ~6 files.
- **Risk**: Low.

## Acceptance Criteria

- [ ] Warnings fire for an unmapped hint on a reachable request path and not when every path resolves; downgrade-only states produce no SDK warning.
- [ ] An evaluator-only hint on a `request_path: sdk` state is checked against the CLI host only (no `anthropic-api` warning).
- [ ] `validate_fsm`/`load_and_validate` accept `host_cli`/`model_hints`; with `host_cli=None`, no resolution warnings fire and existing callers' output is unchanged.
- [ ] Vocabulary semantics, support matrix, precedence and the deferred skill/agent scope (ENH-3533) are documented in `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/reference/{API,CLI,HOST_COMPATIBILITY,CONFIGURATION}.md` and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`.

## Status

**Open** | Created: 2026-09-24 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers validate-time WARNINGs, `haiku-gen` guidance, and documentation only. Resolver/config is ENH-3527 (done) and dispatch wiring is ENH-3547 (done). ENH-3527 dropped the `operation` parameter (2026-09-24). ENH-3547 proved the support matrix with tests that this issue's docs describe; both prerequisites have since landed, so this issue is no longer blocked.


## Session Log
- `/ll:verify-issues` - 2026-09-28T22:12:49 - `a3a4c5a4-ab00-427b-b444-3be5a159c7cf.jsonl`
- `/ll:wire-issue` - 2026-09-28T22:10:45 - `d53bc120-f664-4e90-8dfa-617508184f55.jsonl`
- `/ll:refine-issue` - 2026-09-28T21:58:46 - `313f4024-8fcf-4417-9f15-70ffc98e80d7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:57 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
