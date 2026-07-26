---
id: BUG-2831
type: BUG
title: "request_path sdk/batch silently no-ops agentic skill states \u2014 autodev\
  \ skips every issue as refine_failed"
priority: P1
status: open
captured_at: '2026-07-26T17:03:09Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
relates_to:
- BUG-2830
- BUG-2828
- BUG-2818
- BUG-2807
- ENH-2738
- ENH-2737
- FEAT-2710
labels:
- fsm
- orchestration
- request-path
- autodev
confidence_score: 96
outcome_confidence: 88
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 20
deferred_by: automation
deferred_date: '2026-07-26T17:57:56Z'
deferred_reason: gate_blocked
---

# BUG-2831: request_path sdk/batch silently no-ops agentic skill states — autodev skips every issue as refine_failed

## Summary

With `orchestration.request_path: "sdk"` set project-wide in `.ll/ll-config.json`,
every prompt-mode FSM state — including agentic skill states like
`/ll:refine-issue`, `/ll:format-issue`, `/ll:wire-issue`, `/ll:confidence-check` —
is dispatched as a **single-shot, tool-less** `messages.create()` call via
`host_runner.dispatch_anthropic_request(action=..., system_prompt=None, tools=None)`
(`fsm/executor.py:1652` → `_dispatch_live` → `executor.py:2238`). The model
receives only the bare action string (~45–49 input tokens per `usage.jsonl`),
cannot execute tools or edit files, emits its intended tool calls as plain text
(e.g. a literal `**Tool: bash**` block in the output tail), and the state exits 0
having changed nothing.

Downstream, `refine-to-ready-issue` correctly diagnoses the no-op as a quality
failure (`refine-terminal-class: quality`, `failing_state: diagnose`,
`failing_exit_code: 0`), autodev routes through `skip_inflight`, appends
`<ID>  refine_failed` to `autodev-skipped.txt`, and the run terminates `done` —
so the loop *reports success* while every issue it touched remains `open`.

Observed on `ll-loop run autodev ENH-2825` and `ll-loop run autodev ENH-2829`
(runs `.loops/runs/autodev-20260726T115354/` and `autodev-20260726T115416/`),
each completing in ~40–55s with 5 tiny SDK invocations under `refine_current`.

## Current Behavior

With `orchestration.request_path: "sdk"` configured, every agentic skill state
(`/ll:refine-issue`, `/ll:format-issue`, `/ll:wire-issue`, `/ll:confidence-check`,
etc.) is dispatched as a bare, tool-less `messages.create()` call. The model
cannot execute tools or edit files, so it emits its intended actions as plain
text and the state exits 0 having changed nothing. Downstream, `autodev`
diagnoses this no-op as a `refine_failed` quality failure and skips the issue,
while the loop run still terminates with a `done` status.

## Impact

Every issue processed by `autodev`/`ll-auto` under an `sdk`/`batch`
`orchestration.request_path` default is silently skipped rather than refined —
the loop reports success (`done`) while no issue file is actually modified.
This masks real backlog progress and wastes the ~40–55s per run spent on
useless single-shot API calls. Mitigated today only by the interim workaround
of removing `orchestration.request_path: "sdk"` from `.ll/ll-config.json`
(applied in commit 9510a10f), which is not a durable fix — any future opt-in
to the sdk/batch path will silently reintroduce this bug for agentic states.

## Status

Open — interim mitigation applied (removed `orchestration.request_path: "sdk"`
project-wide default), but the underlying dispatch defect in
`_resolve_request_path()`/`_dispatch_live()` is unfixed. Deferred by automation
(`gate_blocked`) pending the code change described in Proposed Fix.

## Root Cause

The sdk/batch request path was designed for lightweight evaluator/verdict
prompts (MR-12's pruning exemption already treats it as such), but
`_resolve_request_path()` (`fsm/executor.py:2122`) applies the config-level
default to **all** prompt states with no distinction between evaluator prompts
and agentic skill invocations. The path was never exercised end-to-end until
BUG-2828 (model-alias 404s) and BUG-2830 (subscription OAuth rejection) were
fixed — those fixes unmasked this defect rather than causing it. Prior runs
failed fast at the API layer; now the calls succeed and return useless text.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`_resolve_request_path()`** (`scripts/little_loops/fsm/executor.py:2122-2162`) resolves in order: `state.request_path` (per-state override) → `self.orchestration_config.request_path` (project config default) → `"cli"` fallback. When resolved to `"sdk"`/`"batch"`, it only probes SDK importability and credential availability (`_sdk_credentials_available()`, lines 2164-2192) — it never inspects `state.action` content, so it has no way to know the action is a tool-requiring skill invocation.
- **Dispatch branch** (`executor.py:1652-1653`): `elif action_mode == "prompt" and self._resolve_request_path(state) in ("sdk", "batch"): result = self._dispatch_live(state, action, ctx)`. This entirely bypasses the CLI branch (`executor.py:1654-1686`) that normally passes `tools=state.tools`, `agent=state.agent`, `is_slash_command=True` to `self.action_runner.run(...)`.
- **`_dispatch_live()`** (`executor.py:2216-2288`) hardcodes `system_prompt=None, tools=None` at both call sites: line ~2237-2244 for `host_runner.dispatch_anthropic_request(...)` (sdk) and line ~2262-2269 for `host_runner.dispatch_batch_request(...)` (batch) — `state.tools` is never read on this path.
- `host_runner.dispatch_anthropic_request` / `dispatch_batch_request` (`scripts/little_loops/host_runner.py:1587-1644` and `:1647-1683`) both already accept a `tools: list[ToolDefinition] | None` parameter and plumb it through to the request builders — the pass-through plumbing exists, it's simply never invoked with non-`None` tools from the executor side.
- **Existing downgrade mechanism** — `_warn_request_path_downgrade()` (`executor.py:2194-2201`) emits the `request_path_downgrade` event + a stderr warning, but only for two conditions today: `anthropic` not importable, or no resolvable credential. It fires once per run (`self._request_path_downgrade_warned`, a single bool set at `executor.py:223` — not per-reason), so a new "skill invocation on sdk/batch" reason reuses the same helper but should be checked for whether one-shot-per-run masking is acceptable for the new reason.
- **Reusable skill-invocation predicate** — `_SKILL_INVOKE_RE = re.compile(r"/ll:([a-zA-Z0-9_-]+)")` (`scripts/little_loops/fsm/validation.py:2143`) is the only existing mechanism that identifies "this action invokes a `/ll:` skill." There is no `skill:` field on `StateConfig` (`scripts/little_loops/fsm/schema.py`) — detection is inline regex-matching against `state.action`, gated by `state.action.lstrip().startswith("/")` (used in `_validate_pruning_profile`, `validation.py:2153-2254`, e.g. line ~2192-2194). A runtime fix in `executor.py` would need to import this regex from `fsm.validation` (not currently imported by `executor.py`) or duplicate it.
- **MR-12 Check 3 already special-cases this exact condition — in the opposite direction.** `validation.py:2233-2236` (`ENH-2805`) explicitly *exempts* `request_path: sdk`/`batch` states from the "no resolvable pruning_profile" warning, reasoning (docstring at `validation.py:2168-2183`) that sdk/batch states "bypass `action_runner` entirely ... and send a bare single-turn API call with no catalog/CLAUDE.md/hooks to prune." That reasoning assumed sdk/batch states genuinely don't need tool/catalog context — BUG-2831 shows a skill-invoking action *does* need it, so this exemption's premise needs revisiting alongside the executor fix (it currently treats the broken condition as intentionally out-of-scope rather than a defect).
- **Regression test home**: `scripts/tests/test_fsm_executor.py`, class `TestRequestPathDispatchWiring` (starts at line 9814) already covers `_resolve_request_path`/`_dispatch_live` behavior — e.g. `test_request_path_sdk_falls_back_to_cli_when_no_credentials` (~line 10096) shows the pattern: build a single-state prompt FSM, patch `host_runner.dispatch_anthropic_request`, assert `not mock_dispatch.called` and `mock_runner.calls == [...]` when a downgrade should occur. A new test for skill-invocation downgrade (`action="/ll:refine-issue ..."`, `OrchestrationConfig(request_path="sdk")`) fits directly into this class following the same shape.

## Steps to Reproduce

1. Set `orchestration.request_path: "sdk"` in `.ll/ll-config.json`.
2. `ll-loop run autodev <any open issue ID>`.
3. Observe: run completes `done` in under a minute; `usage.jsonl` shows ~45-token
   inputs under `refine_current`; `autodev-skipped.txt` records
   `<ID>  refine_failed`; the issue is still `status: open`.

## Expected Behavior

Agentic skill states must run through the host CLI (agentic loop with tools)
regardless of the sdk/batch config default. The sdk/batch path should apply only
to states it can actually serve (pure text-in/text-out evaluator prompts).

## Proposed Fix

In `_resolve_request_path()` (or at the dispatch site, `executor.py:1652`),
downgrade `sdk`/`batch` to `cli` for any prompt state whose action invokes a
`/ll:` skill/slash command or that declares `tools:`, emitting the existing
`request_path_downgrade` event + stderr warning (mechanism already present at
`executor.py:2194`) so the downgrade is observable. A state-level explicit
`request_path: sdk` override could either be honored (author opted in) or
warned — decide during implementation; the silent-no-op default must go.

Optionally add an MR-class validation warning for loops whose skill-invoking
states resolve to sdk/batch (extends the existing MR-12 exemption logic in
`fsm/validation.py`, which already computes exactly this resolution).

Interim mitigation: remove `"request_path": "sdk"` from `.ll/ll-config.json`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files to modify:**
- `scripts/little_loops/fsm/executor.py` — `_resolve_request_path()` (lines 2122-2162) needs a skill-invocation/`tools:`-declared check (reusing or importing `_SKILL_INVOKE_RE` from `fsm/validation.py:2143`) that forces a downgrade to `"cli"` via the existing `_warn_request_path_downgrade()` (lines 2194-2201) before returning `"sdk"`/`"batch"`.
- `scripts/little_loops/fsm/validation.py` — MR-12 Check 3's sdk/batch exemption (lines 2233-2236) currently treats skill-invoking sdk/batch states as out-of-scope; once the executor forces a downgrade, this exemption no longer matches reality for skill-invoking states specifically (non-skill sdk/batch states are still legitimately exempt) and may need narrowing.

**Tests:**
- `scripts/tests/test_fsm_executor.py`, class `TestRequestPathDispatchWiring` (starts line 9814) — add a new test alongside `test_request_path_sdk_falls_back_to_cli_when_no_credentials` (~line 10096) using an `action="/ll:refine-issue ..."` state and `OrchestrationConfig(request_path="sdk")`, asserting `dispatch_anthropic_request` is not called and the CLI `action_runner` runs instead.

**Similar patterns to follow:**
- The two existing downgrade reasons in `_resolve_request_path()` ("anthropic package not importable", "no ... credential resolvable") are the template for a third reason string — same `_warn_request_path_downgrade(resolved, reason)` call, same event shape (`request_path_downgrade` with `requested`/`reason` keys).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:1584-1585` — `FSMExecutor._run_action()` is the sole caller of both `_resolve_request_path()` and `_dispatch_live()`; `_resolve_request_path()` is also called a second time from inside `_dispatch_live()` itself (line 2235) — confirm both call sites see the same downgraded value (no divergent resolution between the two calls in one dispatch).
- No other executor-side caller or importer of `_resolve_request_path`/`_dispatch_live`/`_warn_request_path_downgrade` exists (confirmed via `ll-code callers-of`, cross-checked with grep) — the fix is contained to a single call path.

### Tests (MR-12 exemption narrowing — new, not previously in this issue)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation.py:4760-4898` — the MR-12 Check 3 sdk/batch-exemption test block (`test_does_not_fire_for_sdk_request_path_state` L4760, `test_does_not_fire_for_batch_request_path_state` L4776, `test_does_not_fire_when_orchestration_request_path_sdk` L4794, `test_config_exemption_via_validate_fsm` L4863, plus 3 siblings) currently assert Check 3 is unconditionally silent for *any* sdk/batch state. Once `validation.py`'s exemption is narrowed to exclude skill-invoking states (to match the executor's forced runtime downgrade), these tests need review — non-skill-invoking sdk/batch states should still be exempt, but a skill-invoking sdk/batch state should now warn. Existing assertions may need splitting into skill-invoking vs. non-skill-invoking cases.
- `scripts/tests/test_fsm_executor.py`, `TestRequestPathDispatchWiring` — confirmed via codebase-pattern-finder that **no existing test in this 15-method class uses a `/ll:`-prefixed action**; all 15 fixtures use `action="Say hi"`. The new test is a genuine gap, not a duplicate — follow `test_request_path_sdk_falls_back_to_cli_when_no_credentials` (L10096-10129) exactly, but keep credentials valid (so the assertion isolates the new skill-invocation downgrade reason from the existing credential-downgrade reason).

### Documentation & Schema (exhaustive two-cause downgrade description, now three)

_Wiring pass added by `/ll:wire-issue`:_ Several places describe the `sdk`/`batch` → `cli` downgrade as gated on exactly two causes ("`anthropic` not importable" or "no credential resolvable"); adding a third cause (skill-invocation forced downgrade) means each of these needs a wording update:
- `scripts/little_loops/observability/schema.py:193-201` — `RequestPathDowngradeVariant` docstring: *"Fired once per run when a configured `request_path: sdk`/`batch` is downgraded because the `anthropic` package is unimportable or no credential is resolvable (ENH-2737)."*
- `scripts/little_loops/config-schema.json:1574-1578` — `orchestration.request_path` property description carries the MR-12 Check 3 exemption clause verbatim ("a skill-invoking state with no explicit state-level request_path is exempt from the no-resolvable-pruning_profile warning when this config default is 'sdk'/'batch'") — must be reconciled with the narrowed exemption once implemented.
- `docs/reference/CONFIGURATION.md:1178-1184` (downgrade prose) and `:1538-1546` (`deferred_tools` "only consulted when sdk/batch" scope note, whose practical scope narrows once skill-invoking states no longer reach this code path).
- `docs/ARCHITECTURE.md:883-906` — § "SDK/Batches Dispatch Path (`orchestration.request_path`)" describes the same two-cause downgrade.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:107` — MR-12 table row rationale: *"`request_path: sdk`/`batch` states are exempt since pruning is a no-op there (`executor.py`'s `_dispatch_live` bypasses `action_runner` and its static prefix entirely)"* — this is the source-of-truth prose `.claude/CLAUDE.md`'s MR-12 row summarizes verbatim, so both need synchronized updates (CLAUDE.md's own MR-12 row update was already noted in the Root Cause section above).

No exhaustive test currently enumerates the `request_path_downgrade` reason-string set, so adding a third reason carries no test-break risk on that front (confirmed gap, not a regression).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Narrow `validation.py`'s MR-12 Check 3 sdk/batch exemption to exclude skill-invoking states, then update/split `test_fsm_validation.py:4760-4898` accordingly (non-skill sdk/batch states stay exempt; skill-invoking ones now warn).
2. Add a skill-invocation downgrade test to `test_fsm_executor.py::TestRequestPathDispatchWiring` (no existing test in the class covers this).
3. Update the two-cause downgrade description to three causes in: `observability/schema.py:193-201` (`RequestPathDowngradeVariant` docstring), `config-schema.json:1574-1578`, `docs/reference/CONFIGURATION.md:1178-1184` + `:1538-1546`, `docs/ARCHITECTURE.md:883-906`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:107`, and `.claude/CLAUDE.md`'s MR-12 row.

## Acceptance Criteria

- [ ] A prompt state invoking a `/ll:` skill under `orchestration.request_path: "sdk"` (config default, no state override) executes via the host CLI, with a `request_path_downgrade` event emitted.
- [ ] Pure evaluator prompt states (no skill invocation, no `tools:`) still honor `request_path: sdk`/`batch` unchanged.
- [ ] `ll-loop run autodev <issue>` with sdk config default performs real refinement (issue file modified) instead of skipping the issue as `refine_failed`.
- [ ] Regression test in `scripts/tests/` covering the downgrade decision in `_resolve_request_path()`/dispatch for skill-invoking vs. evaluator states.

## Session Log
- `/ll:ready-issue` - 2026-07-26T18:11:31 - `f7d7bf20-f34a-4fc9-be2a-96035eba2254.jsonl`
- `/ll:wire-issue` - 2026-07-26T17:50:33 - `6c9e3799-ee10-42c6-be43-83fa4abe251b.jsonl`
- `/ll:refine-issue` - 2026-07-26T17:43:20 - `ca1fe139-8e4a-45a9-8e81-4359c1b633d7.jsonl`
- `/ll:capture-issue` - 2026-07-26T17:03:09Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b6b3c38-43c1-4595-a323-7b5c44517c87.jsonl`
