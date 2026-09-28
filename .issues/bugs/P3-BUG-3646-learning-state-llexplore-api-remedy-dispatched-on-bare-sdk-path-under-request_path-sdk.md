---
id: BUG-3646
type: BUG
title: Learning-state /ll:explore-api remedy dispatched on bare SDK path under request_path
  sdk
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T22:51:25Z'
labels:
- loops
- multi-host
---

# BUG-3646: Learning-state /ll:explore-api remedy dispatched on bare SDK path under request_path sdk

## Summary

Under `request_path: sdk`/`batch` (state-level or `orchestration.request_path`) with the `anthropic` package importable and a resolvable credential, a `type: learning` state's `/ll:explore-api <target>` remedy is dispatched on the bare SDK path instead of the host CLI. The SDK path sends a tool-less single-turn request, so the skill never runs and the remedy silently no-ops.

## Current Behavior

- A `type: learning` state has no `action:` of its own. `FSMExecutor` runs the remedy as `self._run_action(f"/ll:explore-api {target}", _dc_replace(state, action_type="slash_command"), ctx)` (the learning-target loop, `# BUG:` comment above the call).
- `_run_action` resolves `request_path = self._resolve_request_path(state)` from that copied state. `_compute_request_path` downgrades sdk/batch to `cli` for a `/ll:` skill only when `_SKILL_INVOKE_RE.search(state.action)` matches — but the copy's `action` is `None`, so the downgrade never fires and the remedy goes to `_dispatch_live`.
- `_model_consumer_paths` (run-start preflight) makes the same computation for learning states, so `_preflight_model_hints` also resolves a learning state's hint against `anthropic-api` rather than the CLI host.

## Steps to Reproduce

1. Write a loop with a `type: learning` state (with `learning:` targets, at least one unproven) and `request_path: sdk` on the state or in `orchestration.request_path`.
2. Make sure the `anthropic` package is installed and a credential resolves (e.g. `ANTHROPIC_API_KEY` set).
3. Run the loop with `ll-loop run`.
4. Observe: no `request_path_downgrade` warning; the `/ll:explore-api` remedy goes out as a single-turn SDK request, no learning record is written, and the target blocks after its retries.

## Expected Behavior

- The `/ll:explore-api` remedy always runs on the host CLI (it needs the agentic tool loop), regardless of the configured request path, and emits the usual one-shot `request_path_downgrade` warning when sdk/batch was configured.
- `_model_consumer_paths` reports `["cli"]` for a learning state, so the preflight resolves its hint against the CLI host.

## Motivation

A learning state exists to prove unproven targets before work continues. On the SDK path the remedy never runs, so every unproven target burns its retries and blocks — the same failure the earlier `action_type="slash_command"` fix (the `# BUG:` comment at the call site) removed on the CLI path. It is silent apart from outcomes, and it gets likelier as `request_path: sdk` sees more use.

## Proposed Solution

Set the remedy text on the copy: `_dc_replace(state, action_type="slash_command", action=f"/ll:explore-api {target}")` at the dispatch site, and use an equivalent copy (e.g. `action="/ll:explore-api"`) in `_model_consumer_paths`'s learning branch, so `_SKILL_INVOKE_RE` matches in both places. Check that nothing else reads `state.action` from the copy in a way that changes (e.g. `action_start` payloads, interpolation).

## Program Design

### Types

- No new types.

### Signatures

- `_model_consumer_paths(self, state: StateConfig) -> list[Literal["cli", "sdk", "evaluator"]]` — unchanged signature; the learning branch builds its `slash_command` copy with `action="/ll:explore-api"` so `_compute_request_path` downgrades it to `cli`.
- `_run_action(self, action_template: str, state: StateConfig, ctx: InterpolationContext, on_usage: UsageCallback | None = None) -> ActionResult` — unchanged signature; the learning remedy caller passes a copy whose `action` is the remedy text.

### Call Path

- `FSMExecutor.run` → `FSMExecutor._preflight_model_hints` → `FSMExecutor._model_consumer_paths` → `FSMExecutor._compute_request_path`
- `FSMExecutor.run` → learning-target loop → `FSMExecutor._run_action` → `FSMExecutor._resolve_request_path` → `FSMExecutor._compute_request_path`

## Integration Map

- `scripts/little_loops/fsm/executor.py` — learning remedy dispatch, `_model_consumer_paths`, `_compute_request_path`
- `scripts/little_loops/fsm/validation/structural_rules.py` — ENH-3548's validate-time mirror for learning states must be updated to CLI-only when this lands
- Tests: learning-state tests in `scripts/tests/` (remedy under `request_path: sdk` with credentials patched available → dispatched via CLI; preflight hint resolved against the CLI host)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- Dependents of the changed computation: `_compute_request_path` has three call sites — `_resolve_request_path` (`executor.py:3555`, run-time, emits the one-shot `request_path_downgrade`), and `_model_consumer_paths` (`:3758` learning branch, `:3764` generic branch). `_model_consumer_paths` has one caller, `_preflight_model_hints` (`:3739`). `_resolve_request_path` is called only from `_run_action` (`:2577`, prompt-mode actions only).
- Invariants to preserve: `action_start` payload and fragment-store key derive from `action_template`, not `state.action`; the `# BUG:` fix's contract (remedy runs as a prompt-mode slash command, `is_slash_command=True` to the runner) must keep holding; the downgrade check applies even under an explicit per-state `request_path` override.
- ENH-3548's validate-time mirror is **not yet in code** (`_validate_model_hint_resolution` and a `host_cli=` kwarg on `validate_fsm` exist nowhere in `scripts/`; ENH-3548 is `open`). `structural_rules.py` today has no request-path logic for learning states (`_consumes_model_hint` has no learning branch; the learning rule at ~`:616-645` checks only targets/`max_retries`/routes). The mirror update is therefore conditional on ENH-3548 landing first, and ENH-3548 currently specs a learning state as "resolved on the configured path… until BUG-3646 lands".
- Tests — existing coverage and gaps: `test_learning_state.py::TestLearningStateExploreApiDispatchMode` (regression for the earlier `action_type` fix; asserts `is_slash_command == [True]`) must keep passing; no learning test in `test_learning_state.py` or `test_model_hints.py` constructs an `OrchestrationConfig` or sets `request_path`. `test_model_hints.py::TestLearningState` (`test_unmapped_hint_fails_preflight`, `test_resolved_hint_reaches_remedy`) covers the preflight/dispatch hint path for learning states and must keep passing. No test anywhere calls `_compute_request_path`, `_model_consumer_paths` or `_dispatch_live` directly.
- Conventions in Force (test side): "dispatched to the CLI" is asserted as `not mock_dispatch.called` (patching `little_loops.host_runner.dispatch_anthropic_request`) plus `mock_runner.calls == [...]`, with `OrchestrationConfig(request_path="sdk")` — `test_fsm_executor.py::TestRequestPathDispatchWiring` (`test_request_path_sdk_downgrades_for_skill_invoking_action`, BUG-2831) and `test_model_hints.py::TestCliActionDispatch`. The downgrade event is asserted via `_of(events, "request_path_downgrade")`. Preflight behavior is tested end to end through `executor.run()`, not by calling `_model_consumer_paths`. Credentials are made available by `monkeypatch.setenv("ANTHROPIC_API_KEY", ...)`; the only direct patch of `FSMExecutor._sdk_credentials_available` in tests is the `False` form (`test_model_hints.py:415`) — no test patches it to `True`.
- Conventions in Force (validate/runtime): validate-time rules deliberately duplicate executor predicates with a "Mirrors …" docstring rather than importing `executor` (`structural_rules.py:_is_shell_state`, `_consumes_model_hint`); only `_SKILL_INVOKE_RE` is shared. Divergence is caught by an agreement test (specified in ENH-3548, unwritten).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/evaluator_rules.py` — `_validate_pruning_profile` (MR-12) is the validate-time duplicate of the `_SKILL_INVOKE_RE` downgrade predicate; it reads `state.action` from the original learning state (`None`), so it skips learning states before and after the change — no edit needed [Agent 1/2 finding]
- `scripts/little_loops/observability/schema.py` — `RequestPathDowngradeVariant` (`request_path_downgrade` event) now fires for learning remedies; payload shape unchanged, no edit needed [Agent 1 finding]
- `scripts/little_loops/fsm/executor.py:_execute_learning_state` — enclosing function of the dispatch-site `_dc_replace`; `_request_path_downgrade_warned` is a single per-executor latch, so once the remedy takes the downgrade no later state in the same executor emits its own `request_path_downgrade` [Agent 2 finding]

### Side Effects to Expect

_Wiring pass added by `/ll:wire-issue`:_
- `action_complete` payload for the remedy changes: `_resolve_model(state, "cli")` replaces `_resolve_model(state, "sdk")`, so `model_backend` becomes the host CLI name (not `anthropic-api`) and `model_resolved` becomes the host mapping; `model_requested` is unchanged [Agent 2 finding]
- Preflight can newly fail: `_preflight_model_hints` resolves a learning state's hint against `host_runner.resolve_host().name`, so an unmapped hint on a non-Claude host raises `ModelHintError` at run start where the `anthropic-api` resolution previously could not [Agent 2 finding]
- `state.action` on the copy is read only by `_compute_request_path`; `action_start` payload, `fragment_key`, `_action_mode`, and `action_runner.run(..., is_slash_command=True)` are unaffected [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `orchestration.request_path` section lists the downgrade triggers (`/ll:` skill action, `tools:`); optionally note that a `type: learning` state's implicit `/ll:explore-api` remedy always runs on the host CLI [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` — `### request_path_downgrade` (fires at most once per run) and `### learning_explore_invoked` sections; optional cross-note that a learning remedy under sdk/batch triggers the downgrade [Agent 1/2 finding]
- `docs/reference/API.md` — `FSMExecutor._resolve_request_path()` bullet lists only importability/credential probes and omits the BUG-2831 skill check; update alongside this fix (note `API.md` has uncommitted edits in the working tree) [Agent 2 finding]
- `.issues/enhancements/P3-ENH-3548-validate-time-model-hint-warnings-and-hint-documentation.md` — acceptance text says a learning state under sdk is "checked against `anthropic-api` (matching the preflight until BUG-3646 lands)" and plans an agreement-test `type: learning` matrix row; stale once this lands [Agent 2 finding]
- `.issues/enhancements/P2-ENH-3547-wire-model-hint-resolution-through-loop-dispatch-and-lifecycle.md` — records the learning-remedy path decision now being reversed [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_learning_state.py` — add `TestLearningStateRequestPathSdk` (skeleton: `TestLearningStateExploreApiDispatchMode::test_explore_api_dispatched_as_slash_command`, `_MockRunner`, `_learning_fsm`): `OrchestrationConfig(request_path="sdk")` + `monkeypatch.setenv("ANTHROPIC_API_KEY", ...)`, patch `little_loops.host_runner.dispatch_anthropic_request`; assert `not mock_dispatch.called`, `runner.calls == ["/ll:explore-api <target>"]`, one `request_path_downgrade` event across multiple targets/retries [Agent 3 finding]
- `scripts/tests/test_model_hints.py::TestLearningState` — add sdk variants using `_fsm(hint)`/`_execute`/`_of`: (a) `LL_HOST_CLI=claude-code`, hint resolves to `haiku` with `model_backend == "claude-code"`; (b) `LL_HOST_CLI=codex` + unmapped hint → `model_hint_error` at preflight, `runner.calls == []`, no downgrade event at preflight; (c) `fake` host modelled on `TestCliActionDispatch::test_downgrade_re_resolves_for_cli_host` [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py::TestRequestPathDispatchWiring` — optional learning-state sibling of `test_request_path_sdk_downgrades_for_skill_invoking_action` [Agent 3 finding]
- Regression set to re-run (no updates expected): `test_learning_state.py` (incl. `TestLearningStateExploreApiDispatchMode`), `test_model_hints.py` (`TestLearningState`, `TestPreflight::test_preflight_emits_no_downgrade_event`, `TestCliActionDispatch`), `TestRequestPathDispatchWiring::test_request_path_sdk_unchanged_for_pure_evaluator_action` [Agent 3 finding]
- Note: no test patches `_sdk_credentials_available` to `True` — use the `ANTHROPIC_API_KEY` env convention instead of the `True` patch named in step 1 [Agent 3 finding]

## Implementation Steps

1. Write failing tests first: a learning state under `request_path: sdk` with `_sdk_credentials_available` patched True dispatches the remedy through the action runner (not `_dispatch_live`), and `_model_consumer_paths` returns `["cli"]`.
2. Put the remedy text on the state copy at the dispatch site and in `_model_consumer_paths`'s learning branch.
3. If ENH-3548 has landed, switch its learning-state mirror to CLI-only and re-run its agreement test.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `TestLearningStateRequestPathSdk` to `scripts/tests/test_learning_state.py` and sdk-config cases to `scripts/tests/test_model_hints.py::TestLearningState` (env-key credentials, not a `_sdk_credentials_available` patch)
- Update `docs/reference/API.md` (`FSMExecutor._resolve_request_path()` bullet) and `docs/reference/CONFIGURATION.md` (`orchestration.request_path` downgrade triggers) to cover the learning remedy
- Update ENH-3548's learning-state acceptance text and agreement-test matrix row (and ENH-3547's path note) so they no longer describe the learning remedy as resolved on the configured path

## Impact

- **Priority**: P3 - only affects learning states under a non-default `request_path`
- **Effort**: Small - two `_dc_replace` call sites plus tests
- **Risk**: Low - changes only the request path for the learning remedy
- **Breaking Change**: No

## Root Cause

- **Anchor**: `in method FSMExecutor._compute_request_path()` / the learning remedy call in the learning-target loop
- **Cause**: the skill-downgrade check inspects `state.action`, but the remedy's action text is passed separately to `_run_action` and never written onto the state copy.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- The remedy's action text reaches `_run_action` only as `action_template` (used for `interpolate()`, `fragment_key()`, and everything downstream incl. the `action_start` payload); `state.action` is never read inside `_run_action` itself. The only `state.action` read reachable from the copy is `_compute_request_path`'s `_SKILL_INVOKE_RE.search(state.action)` check (`executor.py:3579`) — the sole reason the downgrade misses.
- `_SKILL_INVOKE_RE` is `re.compile(r"/ll:([a-zA-Z0-9_-]+)")` (`fsm/validation/_base.py:192`), an unanchored `.search`, so any `/ll:<name>` text on the copy's `action` matches.
- Because the copy already pins `action_type="slash_command"`, `_action_mode()` returns `"prompt"` before it reaches its `state.action.startswith("/")` heuristic; the mode is independent of `action`.
- Both `_dc_replace(state, action_type="slash_command")` sites (`executor.py:1567`, `executor.py:3757`) override `action_type` only; `action` stays `None`. These are the only `StateConfig` copies synthesized in `fsm/`. A copy preserves `state.type == "learning"` and `state.tools`, so both remain visible to `_compute_request_path`.
- With `action` unreachable, `_compute_request_path` falls through checks 2-4 (`state.tools`, `import anthropic`, `_sdk_credentials_available()`); with `anthropic` importable and a credential present it returns `("sdk", None)`, so no `request_path_downgrade` warning is emitted and `_run_action` takes its `_dispatch_live` branch (tool-less, single-turn).
- `_model_consumer_paths` uses the side-effect-free `_compute_request_path`, so the preflight never emits the downgrade warning; only the run-time `_resolve_request_path` → `_warn_request_path_downgrade` does (one-shot per executor via `_request_path_downgrade_warned`).

## Acceptance Criteria

- [ ] With `request_path: sdk` and credentials available, a learning state's remedy is dispatched through the host CLI, not `_dispatch_live`.
- [ ] `_model_consumer_paths` returns `["cli"]` for a learning state under any request path.
- [ ] ENH-3548's validate-time mirror (if landed) treats learning states as CLI-only, and its validate-vs-preflight agreement test still passes.

## Related

- ENH-3548 — its validate-time mirror currently has to copy this behavior (learning states resolved on the configured path) to agree with the preflight.
- ENH-3547 — introduced `_compute_request_path` / `_model_consumer_paths`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-28 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-28T23:35:40 - `be64666f-45f5-4318-9b0c-ddfe25860145.jsonl`
- `/ll:refine-issue` - 2026-09-28T23:30:47 - `83ac1e49-6b2b-4760-949f-e5772941f97a.jsonl`
