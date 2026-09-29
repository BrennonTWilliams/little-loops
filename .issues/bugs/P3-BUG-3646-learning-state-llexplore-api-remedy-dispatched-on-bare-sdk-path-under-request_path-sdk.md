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
verify_verdict: VALID
labels:
- loops
- multi-host
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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
- `ll-loop validate`'s mirror (`structural_rules.py:_static_model_paths`) reports only `("cli", False)` for a learning state, so validate and preflight agree exactly.

## Motivation

A learning state exists to prove unproven targets before work continues. On the SDK path the remedy never runs, so every unproven target burns its retries and blocks — the same failure the earlier `action_type="slash_command"` fix (the `# BUG:` comment at the call site) removed on the CLI path. It is silent apart from outcomes, and it gets likelier as `request_path: sdk` sees more use.

## Proposed Solution

Build the remedy copy in one place so the dispatch site and the preflight cannot drift apart again (the preflight's copy was meant to mirror the dispatch and is how this bug went unnoticed). Add a small helper on `FSMExecutor`:

```python
@staticmethod
def _learning_remedy_state(state: StateConfig, target: str = "") -> StateConfig:
    """The prompt-mode state copy a learning state's remedy dispatches on."""
    action = f"/ll:explore-api {target}".rstrip()
    return _dc_replace(state, action_type="slash_command", action=action)
```

Use it at the dispatch site (`self._run_action(remedy.action, remedy, ctx)` with `remedy = self._learning_remedy_state(state, target)`) and in `_model_consumer_paths`'s learning branch (`self._learning_remedy_state(state)`). With `action` set, `_SKILL_INVOKE_RE` matches in both places. `StateConfig` has no `__post_init__`, so setting `action=` on the copy is safe. Nothing else reads `state.action` from the copy (see Side Effects to Expect).

Update the validate-time mirror to match: in `structural_rules.py:_static_model_paths`, the learning branch (`return action_paths(state.action)`, ~`:497-498`) becomes `return [("cli", False)]`. Today it passes `state.action` (`None` for a learning state), so under sdk/batch it yields `[("sdk", False), ("cli", True)]`, which reproduces this bug at validate time.

**Optional (message clarity):** under the helper approach, a learning state's downgrade reason reads "state action invokes a /ll: skill…", though the author wrote no `action:`. An alternative is a dedicated `state.type == "learning"` check in `_compute_request_path`, before the `_SKILL_INVOKE_RE` check, with its own reason (e.g. "type: learning state's /ll:explore-api remedy requires the host CLI's agentic tool loop"). That makes the validate mirror a literal one-line match. The shared helper is worth keeping either way, because it removes the duplicated `_dc_replace` copy.

## Program Design

### Types

- No new types.

### Signatures

- `_learning_remedy_state(state: StateConfig, target: str = "") -> StateConfig` — new `FSMExecutor` staticmethod; returns `_dc_replace(state, action_type="slash_command", action="/ll:explore-api <target>")`. The single source of the remedy copy for both call sites.
- `_model_consumer_paths(self, state: StateConfig) -> list[Literal["cli", "sdk", "evaluator"]]` — unchanged signature; the learning branch uses `_learning_remedy_state(state)` so `_compute_request_path` downgrades it to `cli`.
- `_run_action(self, action_template: str, state: StateConfig, ctx: InterpolationContext, on_usage: UsageCallback | None = None) -> ActionResult` — unchanged signature; the learning remedy caller passes `_learning_remedy_state(state, target)`, whose `action` is the remedy text.

### Call Path

- `FSMExecutor.run` → `FSMExecutor._preflight_model_hints` → `FSMExecutor._model_consumer_paths` → `FSMExecutor._compute_request_path`
- `FSMExecutor.run` → learning-target loop → `FSMExecutor._run_action` → `FSMExecutor._resolve_request_path` → `FSMExecutor._compute_request_path`

## Integration Map

- `scripts/little_loops/fsm/executor.py` — learning remedy dispatch, `_model_consumer_paths`, `_compute_request_path`
- `scripts/little_loops/fsm/validation/structural_rules.py` — **required**: `_static_model_paths`'s learning branch becomes `return [("cli", False)]`. ENH-3548 (done, commit 416b8e230) shipped this mirror copying the buggy executor behavior: `action_paths(state.action)` with `state.action is None` yields an `anthropic-api` path plus a CLI fallback under sdk/batch.
- `scripts/tests/test_model_hints.py::TestValidateAgreesWithPreflight::test_agreement` — **required**: remove `"learning"` from the exemption `elif case not in ("sdk", "learning"):` (~`:1356`) so validate and preflight must agree exactly for learning states. This must land together with the `structural_rules.py` change: with only the executor fixed, the `{"anthropic-api": {"coding": False}}` override case gets a validate warning with no matching preflight failure.
- Tests: learning-state tests in `scripts/tests/` (remedy under `request_path: sdk` with credentials patched available → dispatched via CLI; preflight hint resolved against the CLI host)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- Dependents of the changed computation: `_compute_request_path` has three call sites — `_resolve_request_path` (`executor.py:3555`, run-time, emits the one-shot `request_path_downgrade`), and `_model_consumer_paths` (`:3758` learning branch, `:3764` generic branch). `_model_consumer_paths` has one caller, `_preflight_model_hints` (`:3739`). `_resolve_request_path` is called only from `_run_action` (`:2577`, prompt-mode actions only).
- Invariants to preserve: `action_start` payload and fragment-store key derive from `action_template`, not `state.action`; the `# BUG:` fix's contract (remedy runs as a prompt-mode slash command, `is_slash_command=True` to the runner) must keep holding; the downgrade check applies even under an explicit per-state `request_path` override.
- ENH-3548's validate-time mirror **is in code** (landed in commit 416b8e230; ENH-3548 is `done`): `_validate_model_hint_resolution` and `_static_model_paths` in `structural_rules.py`, with `host_cli=`/`model_hints=` kwargs on `validate_fsm`/`load_and_validate`. Its learning branch mirrors the *current, buggy* executor: `action_paths(state.action)` gets `None`, so no `_SKILL_INVOKE_RE` match, and under sdk/batch it returns `[("sdk", False), ("cli", True)]`. ENH-3548's learning-state AC ("checked against the CLI host only… never `anthropic-api`") is ticked but does not hold in code. This issue delivers it. The agreement test hides the gap by exempting `"learning"` from the strict validate-⇔-preflight check (`test_model_hints.py:~1356`) — [corrected by manual review 2026-09-28].
- Tests — existing coverage and gaps: `test_learning_state.py::TestLearningStateExploreApiDispatchMode` (regression for the earlier `action_type` fix; asserts `is_slash_command == [True]`) must keep passing; no learning test in `test_learning_state.py` or `test_model_hints.py` constructs an `OrchestrationConfig` or sets `request_path`. `test_model_hints.py::TestLearningState` (`test_unmapped_hint_fails_preflight`, `test_resolved_hint_reaches_remedy`) covers the preflight/dispatch hint path for learning states and must keep passing. No test anywhere calls `_compute_request_path`, `_model_consumer_paths` or `_dispatch_live` directly.
- Conventions in Force (test side): "dispatched to the CLI" is asserted as `not mock_dispatch.called` (patching `little_loops.host_runner.dispatch_anthropic_request`) plus `mock_runner.calls == [...]`, with `OrchestrationConfig(request_path="sdk")` — `test_fsm_executor.py::TestRequestPathDispatchWiring` (`test_request_path_sdk_downgrades_for_skill_invoking_action`, BUG-2831) and `test_model_hints.py::TestCliActionDispatch`. The downgrade event is asserted via `_of(events, "request_path_downgrade")`. Preflight behavior is tested end to end through `executor.run()`, not by calling `_model_consumer_paths`. Credentials are usually made available by `monkeypatch.setenv("ANTHROPIC_API_KEY", ...)` (the preferred convention for new tests). Direct patches of `FSMExecutor._sdk_credentials_available` exist in both forms: `False` at `test_model_hints.py:415` and `True` at `test_model_hints.py:1347` (`TestValidateAgreesWithPreflight::test_agreement`).
- Batch dispatch does not go through `dispatch_anthropic_request`: `_dispatch_live`'s batch branch calls `host_runner.dispatch_batch_request` / `poll_batch_result`, and returns an error `ActionResult` early when `run_dir` is absent from context. A batch-parametrized test that patches only `dispatch_anthropic_request` and asserts `not mock_dispatch.called` passes even before the fix. See `test_fsm_executor.py::TestRequestPathDispatchWiring::test_request_path_batch_submits_polls_and_clears_tracker` for the batch patch targets.
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
- The one-shot downgrade latch is consumed by the learning remedy: `_request_path_downgrade_warned` is per executor, so once a learning remedy emits `request_path_downgrade`, any later downgrade in the same run is silent, including a distinct environmental one (e.g. "no Anthropic credential resolvable") for an ordinary sdk state. This is the latch's existing design, not a regression, but a loop-wide `orchestration.request_path: sdk` with an early learning state now reliably spends the warning on the learning remedy [review 2026-09-28]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `orchestration.request_path` section lists the downgrade triggers (`/ll:` skill action, `tools:`); optionally note that a `type: learning` state's implicit `/ll:explore-api` remedy always runs on the host CLI [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` — `### request_path_downgrade` (fires at most once per run) and `### learning_explore_invoked` sections; optional cross-note that a learning remedy under sdk/batch triggers the downgrade [Agent 1/2 finding]
- `docs/reference/API.md` — `FSMExecutor._resolve_request_path()` bullet lists only importability/credential probes and omits the BUG-2831 skill check; update alongside this fix [Agent 2 finding]
- `.issues/enhancements/P3-ENH-3548-validate-time-model-hint-warnings-and-hint-documentation.md` — `done` (416b8e230); its `blocked_by: [BUG-3646]` edge was dropped 2026-09-28 (frontmatter carries none); its learning-state AC is ticked but the shipped mirror doesn't satisfy it. Optionally add a note there that BUG-3646 delivers it.
- `.issues/enhancements/P2-ENH-3547-wire-model-hint-resolution-through-loop-dispatch-and-lifecycle.md` — records the learning-remedy path decision now being reversed [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_learning_state.py` — add `TestLearningStateRequestPathSdk` (skeleton: `TestLearningStateExploreApiDispatchMode::test_explore_api_dispatched_as_slash_command`, `_MockRunner`, `_learning_fsm`): `monkeypatch.setenv("ANTHROPIC_API_KEY", ...)`, patch `little_loops.host_runner.dispatch_anthropic_request` **and** `little_loops.host_runner.dispatch_batch_request`; assert neither is called, `runner.calls == ["/ll:explore-api <target>"]`, one `request_path_downgrade` event across multiple targets/retries [Agent 3 finding]
  - Parametrize over `request_path` `"sdk"` and `"batch"` — `_compute_request_path` treats them identically, and both must downgrade [review 2026-09-28]
  - For `batch`, the `runner.calls` assertion is the one that fails before the fix. The batch branch never calls `dispatch_anthropic_request`, so asserting only that mock isn't called passes trivially. Patch `dispatch_batch_request` too (it may never be reached without `run_dir`), so the test can't make a network call if a context supplies one [review 2026-09-28]
  - Parametrize over where the path is declared: `OrchestrationConfig(request_path=...)` (loop-wide) and `request_path:` on the learning state itself (per-state override, which `_resolve_request_path`'s docstring says the skill downgrade still overrides) [review 2026-09-28]
- `scripts/tests/test_model_hints.py::TestLearningState` — add sdk variants using `_fsm(hint)`/`_execute`/`_of`: (a) `LL_HOST_CLI=claude-code`, hint resolves to `haiku` with `model_backend == "claude-code"`; (b) `LL_HOST_CLI=codex` + unmapped hint → `model_hint_error` at preflight, `runner.calls == []`, no downgrade event at preflight; (c) `fake` host modelled on `TestCliActionDispatch::test_downgrade_re_resolves_for_cli_host` [Agent 3 finding]
- `scripts/tests/test_model_hints.py::TestValidateAgreesWithPreflight::test_agreement` — remove `"learning"` from `elif case not in ("sdk", "learning"):` so validate and preflight must agree exactly for learning states; fails until `_static_model_paths` is fixed [review 2026-09-28]
- `scripts/tests/test_fsm_executor.py::TestRequestPathDispatchWiring` — optional learning-state sibling of `test_request_path_sdk_downgrades_for_skill_invoking_action` [Agent 3 finding]
- Regression set to re-run (no updates expected): `test_learning_state.py` (incl. `TestLearningStateExploreApiDispatchMode`), `test_model_hints.py` (`TestLearningState`, `TestPreflight::test_preflight_emits_no_downgrade_event`, `TestCliActionDispatch`), `TestRequestPathDispatchWiring::test_request_path_sdk_unchanged_for_pure_evaluator_action` [Agent 3 finding]
- Note: prefer the `ANTHROPIC_API_KEY` env convention for new tests; `_sdk_credentials_available` is patched to `True` only in the agreement test (`test_model_hints.py:1347`) [corrected 2026-09-28]

## Implementation Steps

1. Write failing tests first (credentials via `monkeypatch.setenv("ANTHROPIC_API_KEY", ...)`; `dispatch_anthropic_request` and `dispatch_batch_request` patched):
   - `test_learning_state.py::TestLearningStateRequestPathSdk` — parametrized over `sdk`/`batch` and loop-wide vs per-state declaration: the remedy goes through the action runner (neither dispatcher called, `runner.calls == ["/ll:explore-api <target>"]`) and exactly one `request_path_downgrade` event fires across several targets/retries.
   - `test_model_hints.py::TestLearningState` sdk variants — the preflight half, tested end to end through `executor.run()` (no test calls `_model_consumer_paths` directly): the hint resolves against the CLI host (`model_backend` is the host name), and an unmapped hint on a non-Claude host fails at preflight with no runner calls.
   - `test_model_hints.py::TestValidateAgreesWithPreflight::test_agreement` — drop `"learning"` from the exemption.
2. Add `_learning_remedy_state()` and use it at the dispatch site and in `_model_consumer_paths`'s learning branch.
3. Change `structural_rules.py:_static_model_paths`'s learning branch to `return [("cli", False)]` and update its docstring (learning remedy is always CLI).
4. Update docs (API.md, CONFIGURATION.md; EVENT-SCHEMA.md optional).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `TestLearningStateRequestPathSdk` to `scripts/tests/test_learning_state.py` and sdk-config cases to `scripts/tests/test_model_hints.py::TestLearningState` (env-key credentials, not a `_sdk_credentials_available` patch)
- Update `docs/reference/API.md` (`FSMExecutor._resolve_request_path()` bullet) and `docs/reference/CONFIGURATION.md` (`orchestration.request_path` downgrade triggers) to cover the learning remedy
- Fix `structural_rules.py:_static_model_paths`'s learning branch to CLI-only and drop the `"learning"` exemption from `test_agreement` (ENH-3548 shipped the mirror against the buggy executor)
- Optionally add a one-line note to ENH-3548 and ENH-3547 (both done) that BUG-3646 delivers/reverses their learning-remedy path handling

## Impact

- **Priority**: P3 - only affects learning states under a non-default `request_path`
- **Effort**: Small - one helper replacing two `_dc_replace` call sites, a one-line validate-mirror change, plus tests
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
- Both `_dc_replace(state, action_type="slash_command")` sites (`executor.py:1569`, `executor.py:3757`) override `action_type` only; `action` stays `None`. These are the only `StateConfig` copies synthesized in `fsm/`. A copy preserves `state.type == "learning"` and `state.tools`, so both remain visible to `_compute_request_path`.
- With `action` unreachable, `_compute_request_path` falls through checks 2-4 (`state.tools`, `import anthropic`, `_sdk_credentials_available()`); with `anthropic` importable and a credential present it returns `("sdk", None)`, so no `request_path_downgrade` warning is emitted and `_run_action` takes its `_dispatch_live` branch (tool-less, single-turn).
- `_model_consumer_paths` uses the side-effect-free `_compute_request_path`, so the preflight never emits the downgrade warning; only the run-time `_resolve_request_path` → `_warn_request_path_downgrade` does (one-shot per executor via `_request_path_downgrade_warned`).

## Acceptance Criteria

- [ ] With `request_path: sdk` or `batch` (loop-wide or on the learning state) and credentials available, a learning state's remedy is dispatched through the host CLI, not `_dispatch_live`.
- [ ] Under sdk/batch, exactly one `request_path_downgrade` event (and stderr warning) is emitted for a learning state, across all its targets and retries; under `cli`, none is.
- [ ] `_model_consumer_paths` returns `["cli"]` for a learning state under any request path, so the preflight resolves its hint against the CLI host (verified end to end through `executor.run()`).
- [ ] The dispatch site and the preflight build the remedy copy through one shared helper.
- [ ] `structural_rules.py:_static_model_paths` returns only `("cli", False)` for a learning state under any request path, and `test_agreement` passes with `"learning"` removed from its exemption (validate and preflight agree exactly).
- [ ] Existing `TestLearningStateExploreApiDispatchMode` and `test_model_hints.py::TestLearningState` tests still pass.

## Related

- ENH-3548 — done (416b8e230). It shipped the validate-time mirror against the buggy executor, and its learning-state AC (CLI host only, never `anthropic-api`) is delivered here rather than by ENH-3548.
- ENH-3547 — introduced `_compute_request_path` / `_model_consumer_paths`.
- Follow-up candidate (not in scope): MR-12 (`_validate_pruning_profile`) skips learning states because it reads `state.action`. Once the remedy always runs on the CLI through `action_runner`, learning states arguably deserve the same pruning-profile guidance as other `/ll:` states.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **CLAIMS_OUTDATED** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

Full-sweep pass (2026-09-29, `--auto`). Graph: provider=`codegraph` freshness=`fresh` (not needed to decide any verdict).

- Codebase Research Findings cited the learning-remedy `_dc_replace` site as `executor.py:1567`; it is `:1569` (the `:3757` site was correct). Rewritten in place.
- Documentation cited ENH-3548 as `done` "despite its `blocked_by: [BUG-3646]` edge"; that edge was dropped 2026-09-28 (ENH-3548's frontmatter carries no `blocked_by`). Reworded in place.
- Confirmed accurate: root cause (`_compute_request_path` `_SKILL_INVOKE_RE.search(state.action)` at `:3579` sees `None` on the remedy copy, so sdk/batch is not downgraded); `_model_consumer_paths` learning branch (`:3757-3758`); `_resolve_request_path` `:3555`/`:2577`; `_preflight_model_hints` `:3739`; `_SKILL_INVOKE_RE` at `_base.py:192`; `structural_rules._static_model_paths` learning branch returns `action_paths(state.action)` (`:497-498`) and yields `[("sdk", False), ("cli", True)]` under sdk/batch; `test_agreement` exemption `elif case not in ("sdk", "learning")` at `test_model_hints.py:1356`, with `_sdk_credentials_available` patched at `:415` (False) and `:1347` (True); all cited test names exist; MR-12 (`_validate_pruning_profile`) reads `state.action`.
- Decisions rules: no active required rules. `ll-verify-evidence`: clean.
- Proposal-vs-code check (B6): no exception-handler, fixture, or AC-coverage gaps found.

## Status

**Open** | Created: 2026-09-28 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-29T00:37:37 - `5b5d1874-2832-4b4f-9528-f02ed025e782.jsonl`
- `manual review` - 2026-09-28 - ENH-3548 found already landed (416b8e230) with a learning mirror copying the bug: made the `_static_model_paths` fix and `test_agreement` exemption removal required, added AC; dropped stale `blocks: [ENH-3548]`; batch tests must also patch `dispatch_batch_request`; corrected `_sdk_credentials_available` patch claim; noted optional learning-specific downgrade reason
- `manual review` - 2026-09-28 - reconciled Step 1 with the env-key test convention; added downgrade-event AC, sdk/batch and per-state parametrization, shared `_learning_remedy_state` helper, latch side effect; set `blocks: [ENH-3548]` and updated ENH-3548 to CLI-only learning states; noted MR-12 follow-up
- `/ll:confidence-check` - 2026-09-28T23:38:36 - `11482c9b-ffe7-4717-8544-400c53005e5c.jsonl`
- `/ll:verify-issues` - 2026-09-28T23:37:23 - `32aeb86c-0b9a-4909-acf8-c825531b5ad2.jsonl`
- `/ll:wire-issue` - 2026-09-28T23:35:40 - `be64666f-45f5-4318-9b0c-ddfe25860145.jsonl`
- `/ll:refine-issue` - 2026-09-28T23:30:47 - `83ac1e49-6b2b-4760-949f-e5772941f97a.jsonl`
