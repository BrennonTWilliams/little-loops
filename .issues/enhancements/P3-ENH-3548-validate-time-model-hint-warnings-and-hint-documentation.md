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
- `/ll:refine-issue` - 2026-09-28T21:58:46 - `313f4024-8fcf-4417-9f15-70ffc98e80d7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:57 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
