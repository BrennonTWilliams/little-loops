---
id: ENH-2810
type: ENH
priority: P3
status: done
captured_at: '2026-07-25T15:15:00Z'
completed_at: '2026-07-25T22:57:12Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 90
score_complexity: 21
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 22
---

# ENH-2810: MR-12 Check 3 should honor config-level request_path sdk exemption

## Summary

`_validate_pruning_profile` Check 3 (ENH-2805) warns when a skill-invoking state has no resolvable `pruning_profile`, exempting states with `request_path: sdk`/`batch`. But the exemption only inspects the **state-level** `StateConfig.request_path` — it never sees the project's `orchestration.request_path` config default, which `FSMExecutor._resolve_request_path()` falls back to at execution time. A project with `orchestration.request_path: "sdk"` in `.ll/ll-config.json` gets MR-12 Check 3 warnings for states that will in fact dispatch via `_dispatch_live` (the SDK path), where pruning is a no-op and the warning's "pays the full static prefix" claim is false.

## Current Behavior

`ll-loop validate autodev` in a project configured with `orchestration.request_path: "sdk"` emitted five MR-12 Check 3 warnings (deposit_options, run_decide, run_spike, run_size_review, reconcile_current) even though every one of those prompt-mode states resolves to the SDK request path at runtime. `_validate_pruning_profile(fsm)` takes only the `FSMLoop`; the exemption at the Check 3 site (`fsm/validation.py`, the `state.request_path in ("sdk", "batch")` guard) cannot consult `BRConfig`.

## Expected Behavior

Validation-time exemption mirrors the executor's two-level resolution (`state.request_path` → `orchestration.request_path` config default → `"cli"`), so projects running the SDK path by config default don't get false-positive Check 3 warnings. States that explicitly set `request_path: cli` still warn regardless of config.

## Motivation

False-positive WARNs erode trust in the MR gate output and push users toward `pruning_profile_ok: true`, a blunt suppression that also silences the ERROR-tier Check 1 (tools-allowlist exclusion). Making Check 3's exemption match runtime resolution keeps the warning meaningful for CLI-path installs while staying silent where it's genuinely a no-op.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — `_validate_pruning_profile(fsm: FSMLoop) -> list[ValidationError]` (lines 2079-2171); Check 3 exemption site is `if state.request_path in ("sdk", "batch"): continue` at lines 2152-2153. `validate_fsm()` calls it at line 1300 (`errors.extend(_validate_pruning_profile(fsm))`). `load_and_validate(path, raise_on_error=True)` (lines 3054-3158) calls `validate_fsm(fsm)` at line 3136 — both signatures need the new optional parameter threaded through.
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` (lines 12-52) calls `load_and_validate(path)` (non-JSON path, line 43) and `load_and_validate(path, raise_on_error=False)` (`--json` path, line 29). Currently imports neither `BRConfig` nor any config module — needs `from little_loops.config import BRConfig` plus `BRConfig(Path.cwd())` construction to pass `orchestration.request_path` through.
  - **Wiring pass correction (`/ll:wire-issue`):** both call sites (line 29 `--json` branch AND line 43 non-JSON branch) need the same threading — load `BRConfig` once at the top of `cmd_validate()` and pass `orchestration.request_path` to both `load_and_validate()` calls. Without this, `ll-loop validate --json` would still report Check 3 warnings that the non-JSON output suppressed, an inconsistency between the two output modes of the same command.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:2102-2142` — `FSMExecutor._resolve_request_path(self, state: StateConfig) -> str` is the runtime resolver to mirror: `state.request_path` → `self.orchestration_config.request_path` (an `OrchestrationConfig | None`) → literal `"cli"`. Lines 2128-2172 also handle a runtime-only sdk→cli downgrade (`_warn_request_path_downgrade`, lines 2174-2181) when the `anthropic` package/credentials are unavailable — validation-time code has no way to observe this, so the config-level exemption stays optimistic (matches the issue's stated caveat).
- `scripts/little_loops/cli/loop/lifecycle.py:570,586` and `scripts/little_loops/cli/loop/run.py:231,579-580` — both construct `config = BRConfig(Path.cwd())` and thread `orchestration_config=config.orchestration` into the executor constructor. This is the exact load→thread pattern to replicate in `config_cmds.py`.
- `scripts/little_loops/config/orchestration.py:63-103` — `OrchestrationConfig` dataclass, `request_path: str = "cli"` field at line 91, `from_dict()` at lines 95-103.
- `scripts/little_loops/config/core.py:174` — `BRConfig` class; `.orchestration` property at line 366 returns the `OrchestrationConfig`. A lighter single-key alternative exists at `scripts/little_loops/cli/config.py:63` (`BRConfig(Path.cwd()).resolve_variable(args.key)`), but the full `orchestration.request_path` field is more directly reached via `.orchestration`.

### Similar Patterns
- `scripts/little_loops/fsm/validation.py:2072-2076` — `_effective_pruning_profile(fsm, state)` already implements the "state override, else outer default" resolution idiom this issue needs to add for `request_path` (state → orchestration config). No existing `_validate_*` MR check in this file currently accepts an optional config-derived parameter — this would be the first.

### Tests
- `scripts/tests/test_fsm_validation.py:4574-4723` — class `TestPruningProfileCoverageValidation`. Fixture builder `_simple_fsm()` (line 4581) and warning filter `_mr12_coverage_warnings()` (line 4592) to reuse. Existing state-level exemption tests: `test_does_not_fire_for_sdk_request_path_state` (line 4672), `test_does_not_fire_for_batch_request_path_state` (line 4688), both using `make_state(request_path=...)` with no config object involved. `test_fires_end_to_end_via_validate_fsm` (line 4706) exercises the `validate_fsm(fsm)` wiring. **No existing test constructs an `OrchestrationConfig`/`BRConfig` and passes it through** — confirmed via grep, zero matches for `BRConfig`/`ll-config.json`/`resolve_config`/`load_config` in `validation.py` or `config_cmds.py`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_commands.py` (lines 111, 145, 169, 199, 224, 251, 291) — existing `cmd_validate()`-level tests (`test_validate_with_unreachable_state_prints_warning`, `test_validate_json_output_valid_loop`, etc.) call `cmd_validate(loop_name, args, loops_dir, logger)` directly with no config object; none construct `BRConfig`/`OrchestrationConfig`. Once Step 3 wires `cmd_validate` to load `BRConfig(Path.cwd())`, add a new case here exercising `orchestration.request_path: sdk` from an on-disk `.ll/ll-config.json` fixture and asserting the Check 3 warning is suppressed — this is the CLI-level test the issue's existing Test section didn't call out (it only names the `fsm/validation.py`-level unit tests).
- Construction patterns to follow for the new tests: `scripts/tests/test_fsm_executor.py` (`OrchestrationConfig(request_path="sdk")` passed directly, e.g. `test_request_path_sdk_calls_dispatch_not_cli` line 9529) for lightweight in-memory unit tests of `_validate_pruning_profile`/`validate_fsm`; `scripts/tests/test_config.py::TestBRConfigOrchestration` (line 3217, writes `.ll/ll-config.json` then constructs `BRConfig(temp_project_dir)`) for the CLI-level `cmd_validate` test that needs the full config-loading path.
- Breakage check confirmed clean: all 40+ `validate_fsm(fsm)`/`load_and_validate(path, raise_on_error=...)` call sites across 39 test files use positional-fsm/path plus keyword-only trailing args — an appended optional parameter with a default is additive and won't require touching any of them.

### Documentation
- `.claude/CLAUDE.md` (MR-12 row, ~line 160) and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (~line 107) both need the config-level exemption noted per Implementation Step 4.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### validate_fsm` signature block (`def validate_fsm(fsm: FSMLoop) -> list[ValidationError]`, ~line 5590) goes stale once `validate_fsm` gains the new optional parameter; update the signature shown.
- `docs/guides/LOOPS_GUIDE.md` (~line 633) — third prose description of the Check 3 exemption ("`request_path: sdk`/`batch` states are exempt since pruning is a no-op there"), currently state-level-only phrasing; needs the config-level fallback noted alongside CLAUDE.md and HARNESS_OPTIMIZATION_GUIDE.md.

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` — `orchestration.request_path` description (~line 1574) enumerates existing consumers ("cache_control"/"deferred tool-loading" sibling properties follow this pattern) but doesn't mention MR-12 validation as a consumer; not required for schema correctness, but matches the established cross-reference pattern in this file. Optional/nice-to-have.

## Proposed Solution

Thread the orchestration config into validation, mirroring `_resolve_request_path`:

- Add an optional `orchestration_request_path: str | None = None` (or an `OrchestrationConfig`) parameter to `_validate_pruning_profile` / the top-level `validate()` entry, defaulting to `None` (current behavior — no exemption widening for callers that don't pass config).
- At the Check 3 exemption site, exempt when `state.request_path or orchestration_request_path` is in `("sdk", "batch")`.
- In the `ll-loop validate` CLI path, load the resolved `BRConfig` and pass `orchestration.request_path` through.
- Alternative (lighter touch): keep the warning but downgrade its message when the config default is sdk (e.g. "note: config request_path=sdk makes this a no-op at runtime"). Full exemption is preferred — a no-op warning is still noise.

Caveat: the executor downgrades sdk→cli at runtime when the `anthropic` package is unavailable (`_warn_request_path_downgrade`), so a config-level exemption is optimistic. That mirrors the existing state-level exemption's semantics, so no new inconsistency is introduced.

## Implementation Steps

1. Extend `_validate_pruning_profile` (and its caller in `validate()`) with an optional orchestration request-path input; keep default behavior unchanged when absent.
2. Apply the widened exemption only to Check 3 (Checks 1 and 2 are about allowlist/catalog consistency, not prefix cost — leave them as-is).
3. Wire `ll-loop validate` to resolve the project config and pass the value.
4. Update the MR-12 row in `.claude/CLAUDE.md` and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` to note the config-level exemption.
5. Tests: Check 3 silent with config-level sdk; still warns with config cli/unset; state-level `request_path: cli` override still warns under config sdk (or document chosen precedence); Checks 1–2 unaffected.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. In `config_cmds.py::cmd_validate()`, thread `orchestration.request_path` into **both** `load_and_validate()` call sites (line 29 `--json` branch and line 43 non-JSON branch), not just one — confirmed via side-effect trace that the `--json` branch is a separate call in the same function.
7. Update `docs/guides/LOOPS_GUIDE.md` (~line 633) and `docs/reference/API.md` (`#### validate_fsm` signature block, ~line 5590) alongside CLAUDE.md/HARNESS_OPTIMIZATION_GUIDE.md — two additional docs independently describe Check 3's exemption or `validate_fsm`'s signature and would otherwise go stale/inconsistent.
8. Add a CLI-level regression test in `scripts/tests/test_ll_loop_commands.py` (alongside the existing `cmd_validate()` tests at lines 111/145/169/199/224/251/291) that builds a real `.ll/ll-config.json` with `orchestration.request_path: sdk` via `BRConfig(temp_project_dir)` (pattern: `test_config.py::TestBRConfigOrchestration`, line 3217) and asserts Check 3 is suppressed through the full CLI path — the fsm/validation.py-level unit tests alone don't cover the config-loading wiring in `cmd_validate` itself.
9. Optional: note the new MR-12 validation-time consumer in `scripts/little_loops/config-schema.json`'s `orchestration.request_path` description (~line 1574), matching the existing pattern where sibling properties cross-reference their consumers.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact edit sites for Step 1**: `_validate_pruning_profile` signature at `scripts/little_loops/fsm/validation.py:2079`; exemption check at lines 2152-2153 (`if state.request_path in ("sdk", "batch"): continue`); caller in `validate_fsm()` at line 1300; `load_and_validate()` signature/call at lines 3054 and 3136.
- **Exact edit site for Step 3**: `cmd_validate()` in `scripts/little_loops/cli/loop/config_cmds.py:12-52`, calling `load_and_validate()` at lines 29 (`--json` path) and 43 (non-JSON path). Reuse the `BRConfig(Path.cwd())` → `config.orchestration` load-and-thread pattern already used at `scripts/little_loops/cli/loop/lifecycle.py:570,586` and `scripts/little_loops/cli/loop/run.py:231,579-580`.
- **Test model for Step 5**: extend `TestPruningProfileCoverageValidation` in `scripts/tests/test_fsm_validation.py:4574-4723`, alongside `test_does_not_fire_for_sdk_request_path_state` (line 4672) and `test_does_not_fire_for_batch_request_path_state` (line 4688). New cases: state has no `request_path` + `orchestration_request_path="sdk"` passed → exempt; `orchestration_request_path="cli"`/unset → still warns; state `request_path="cli"` explicit override + `orchestration_request_path="sdk"` → still warns (confirms the precedence Expected Behavior already specifies). Reuse `_simple_fsm()` (line 4581) and `_mr12_coverage_warnings()` (line 4592) helpers.

## Impact

- **Effort**: Small (single validation function + CLI wiring + tests)
- **Risk**: Low — exemption widening only; no new warnings introduced
- **Files**: `scripts/little_loops/fsm/validation.py`, `ll-loop` validate CLI entry, `scripts/tests/` validation tests, CLAUDE.md / HARNESS_OPTIMIZATION_GUIDE.md docs

## Context

Found while investigating five MR-12 Check 3 warnings on `autodev.yaml` in a project with `orchestration.request_path: "sdk"`; the immediate warnings were resolved by adding `pruning_profile` blocks to the five states (harmless on sdk, beneficial on cli), but the validator gap remains for any sdk-configured project.

## Resolution

Threaded an optional `orchestration_request_path` parameter through
`_validate_pruning_profile` → `validate_fsm` → `load_and_validate`, mirroring
`FSMExecutor._resolve_request_path`'s state → config → `"cli"` fallback at the
Check 3 exemption site (`effective_request_path = state.request_path or
orchestration_request_path`). `ll-loop validate`'s `cmd_validate` now loads
`BRConfig(Path.cwd()).orchestration.request_path` once and threads it into both
the `--json` and non-JSON `load_and_validate()` call sites. Added unit tests in
`test_fsm_validation.py::TestPruningProfileCoverageValidation` covering the
config-sdk exemption, config-cli/unset no-op, and state-level `cli` override
precedence, plus CLI-level regression tests in `test_ll_loop_commands.py`
exercising a real on-disk `.ll/ll-config.json`. Updated CLAUDE.md,
HARNESS_OPTIMIZATION_GUIDE.md, LOOPS_GUIDE.md, API.md, and config-schema.json.

## Session Log
- `/ll:manage-issue` - 2026-07-25T22:56:36Z - `0e9d5cfe-a08f-405d-9496-907be762d917.jsonl`
- `/ll:wire-issue` - 2026-07-25T22:46:08 - `9ff0f6ba-b8a3-4233-8059-9e050b15f762.jsonl`
- `/ll:refine-issue` - 2026-07-25T22:40:52 - `df55e5c2-4dd5-41e5-8009-e1aaaee3ee1f.jsonl`
- `/ll:capture-issue` - 2026-07-25T15:15:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe35d20e-b1d7-4e57-9b51-73d0a86b9144.jsonl`
