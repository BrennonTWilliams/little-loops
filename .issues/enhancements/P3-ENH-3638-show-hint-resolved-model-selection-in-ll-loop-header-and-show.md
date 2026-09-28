---
id: ENH-3638
type: ENH
title: Show hint-resolved model selection in ll-loop header and show
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T21:28:20Z'
completed_at: '2026-09-28T21:54:26Z'
parent: EPIC-3563
labels:
- multi-host
- loops
epic: EPIC-3563
relates_to:
- ENH-3547
- ENH-3548
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# ENH-3638: Show hint-resolved model selection in ll-loop header and show

## Summary

Show the hint-resolved model selection in the `ll-loop` console header and in `ll-loop show`. ENH-3547 (done) wires `model_hint` resolution into dispatch and adds `model_requested` / `model_resolved` / `model_backend` to event payloads. This issue makes that selection visible on every header render path. It was split out of ENH-3547 on 2026-09-27 because the display work carried most of that issue's remaining ambiguity (outcome confidence 46).

## Current Behavior

- `run.py:710`, `lifecycle.py:775` (`cmd_resume`) and `lifecycle.py:854` (`cmd_monitor`) pass `model=fsm.llm.model` to `run_foreground` / `StateFeedRenderer`. `LLMConfig.model` keeps its default (`DEFAULT_LLM_MODEL`, `"sonnet"`) when `llm.model_hint` is set, so a hint-only loop shows the default model in the header.
- `run.py:710` passes `fsm.llm.model` even when `--model` (`run_model`) is set, although `--model` is what CLI actions actually dispatch with.
- `run.py:711` likewise passes `effort=fsm.llm.effort` even when `--effort` (`run_effort`) is set, so a `--effort high` run shows no effort code before the first dispatch. `docs/reference/CLI.md:947` already claims the header reflects the "`--effort` run override".
- Header composition is duplicated. `header.py:136` (`_render_artifact_header_lines`, called from `feed.py:367` and `feed.py:787`) and the inline `model_line` at `runner.py:393` (inside `run_foreground`, not a separate entry point) both build `model if effort is None else f"{model} {_effort_code(effort)}"`.
- `StateFeedRenderer.handle_event` (`feed.py:843-849`) updates `self.model` / `self.effort` live from `action_complete` events, but only from `model` (the observed model from usage events) and `effort`. It does not read the ENH-3547 selection fields.
- `info.py:1528` (`cmd_show`) prints `llm: model=` only when the value is not the hardcoded `"sonnet"`, and never prints `model_hint`. A hint-only loop looks like the default.

### What `llm.model_hint` actually controls (ENH-3547)

`FSMExecutor._resolve_model` gives the `"cli"` path this precedence: state `model` → state `model_hint` → run `--model` → **none** (host default). An `llm` declaration is never a CLI-action default. `llm.model_hint` drives only the `"evaluator"` path (`llm_structured` evaluators) and the `"sdk"` path (SDK/batch prompt actions, resolved against `anthropic-api`).

So for a hint-only loop on a CLI host, CLI prompt actions run on the host default, and their `action_complete` events carry **no** selection fields (`executor.py:2749-2752`). Only the observed `model` is present. The pre-ENH-3547 header had the same gap: it showed `llm.model` before the first action, then switched to the observed model.

## Expected Behavior

The `model:` line shows **the model the loop's actions run on**. Before the first dispatch, when no action model is known, the `llm` declaration is the fallback label.

- **Two shared helpers in `header.py`, not three kwargs.**
  - `format_model_selection(requested, resolved, backend)` builds the display string. The render sites take that string. They do not take `model_requested` / `model_resolved` / `model_backend` separately.
  - `compose_model_line(display, effort)` appends the effort code. Both `header.py:136` and `runner.py:393` use it, which removes the duplicated composition.
- **Hint detection.** A selection is a hint iff `requested in MODEL_HINTS`. Do not infer it from `requested != resolved`. On the SDK path a literal `sonnet` resolves to `claude-sonnet-5`, and events carry no `is_hint`.
- **Format.**
  - A hint renders `<requested> → <resolved> (<backend>)`, for example `coding → sonnet (claude-code)`. If `backend` is `None`, it renders `<requested> → <resolved>`.
  - A literal renders the bare resolved value, which is today's display unchanged.
- **Effort composition.** The effort code goes after the whole display string: `coding → sonnet (claude-code) H`.
- **Initial value (before the first dispatch)**, in precedence order:
  1. If `--model` (`run_model`) is set, show it bare. This is an intentional change from today, which shows `fsm.llm.model`; `--model` is what CLI actions dispatch with.
  2. Else, if `llm.model_hint` is set, resolve it against `resolve_host().name` with the `orchestration.model_hints` overrides and render it as a hint.
  3. Else show `fsm.llm.model` bare. This is byte-identical to today.
- **Initial effort (before the first dispatch).** `cmd_run` passes `run_effort or fsm.llm.effort`, which mirrors the `--model` precedence. Without `--effort` this is byte-identical to today. `cmd_resume` and `cmd_monitor` keep `fsm.llm.effort`, because neither has the run's `--effort`.
- **`--model` versus a state-level declaration (accepted).** If the initial state declares its own `model` or `model_hint`, that declaration wins over `run_model` in `FSMExecutor._resolve_model`. The pre-dispatch header then shows `X` and switches on the first action. This is the same trade-off as the two limitations below: the first `action_complete` corrects the header.
- **Pre-dispatch backend limitation (accepted).** Step 2 always resolves `llm.model_hint` against the CLI host (`resolve_host().name`). The CLI host is right for `llm_structured` evaluators. It is wrong for a loop whose hint consumers are SDK/batch prompt actions, which resolve against `anthropic-api`. For such a loop the pre-dispatch header can show `coding → sonnet (claude-code)` and then change to `coding → claude-sonnet-5 (anthropic-api)` after the first action. On a host where the hint is disabled (`False` mapping), it can also show `(unresolved on <host>)` for a run that succeeds. This is accepted, not fixed here, for the same reason as the monitor limitation: the first `action_complete` corrects the header. Resolving per the initial state's request path would need `FSMExecutor._compute_request_path`, which `cmd_monitor` does not have.
- **Never raise.** A loop whose `llm.model_hint` nothing consumes (all-shell states, or `--no-llm`) passes the ENH-3547 preflight, but its hint may have no mapping on the CLI host. `initial_model_display` must never raise from `run.py` or `lifecycle.py`:
  - On `ModelHintError` it renders `<hint> (unresolved on <backend>)`. This also covers opencode and pi. On those hosts `resolve_host()` succeeds and `resolve_model_hint` raises because the backend is not supported, so the header renders `(unresolved on opencode)`.
  - On `HostNotConfigured` from `resolve_host()` it renders `<hint> (unresolved: no host CLI)`.
- **Live update.** `StateFeedRenderer.handle_event`'s `action_complete` branch works as follows:
  - **Selection fields present:** rebuild with `format_model_selection(model_requested, <observed model or model_resolved>, model_backend)`. The observed `model` wins over `model_resolved` in the resolved slot, which matches ENH-2885's observed-over-config precedence for effort.
  - **Selection fields absent:** keep today's behavior, a bare observed `model`. For a hint-only loop on a CLI host, the header changes from the pre-dispatch hint label to the host-default model after the first CLI action. That is correct: the action did run on the host default.
  - **Expected changes, not regressions.** Tests must not assert that the header text stays the same across these changes:
    - The resolved slot changes from the pre-dispatch alias to the full observed ID. For example, `coding → sonnet (claude-code)` becomes `coding → claude-sonnet-5 (claude-code)`.
    - The header always reflects the most recent `action_complete`. In a mixed loop (some states hinted, some undeclared), it changes on each action between a hint display and a bare host default.
- **Parameter rename: `model` → `model_display`.** After this change, the value passed through the render chain is a display string (`coding → sonnet (claude-code)`), not a model ID. Rename the `model` parameter to `model_display` on `run_foreground`, `StateFeedRenderer.__init__` (and its `self.model` attribute), `_render_pinned_pane`, `_build_pinned_pane` and `_render_artifact_header_lines`. The rename stops later code from using the value as a model ID for pricing or dispatch. The churn is small: `tests/test_state_feed_renderer.py:165,322` (`model=` kwarg), `tests/test_state_feed_renderer.py:166,176` (`renderer.model` attribute assertions) and `tests/test_ll_loop_display.py:2804`.
  - **Local-name collision.** `_render_artifact_header_lines` already has a local named `model_display` (`header.py:136`). After the rename, give the composed value a different local name, for example `model_line = compose_model_line(model_display, effort)`, so the local does not shadow the parameter.
- **All entry points.** `cmd_run`, `cmd_resume` and `cmd_monitor` build the initial string through `initial_model_display`. `run_foreground` passes the string to both its inline header (`runner.py:393`) and `StateFeedRenderer`. Inside `feed.py` the string reaches `_render_artifact_header_lines` on two paths:
  - `StateFeedRenderer._redraw_pinned` → `feed.py:667` (`model=self.model` into `_render_pinned_pane`, `feed.py:391`) → `feed.py:446` (`model=model` into `_build_pinned_pane`) → `feed.py:367`;
  - `StateFeedRenderer` → `feed.py:787` directly.
- **Resume.** `cmd_resume` never re-applies `--llm-model` or `--model`: its `PersistentExecutor` (`lifecycle.py:737`) takes no `run_model`, and it reloads the YAML. A resumed run that was started with `--llm-model X` (which cleared a YAML `llm.model_hint`) therefore reactivates the hint. The header must show the hint selection, not `X`. This falls out of computing from the reloaded `fsm` with `run_model=None`, so no extra plumbing is needed.
- **Monitor limitation.** `cmd_monitor` loads the YAML fresh and seeks to the end of the events file (no replay). Its initial header cannot reflect any `--model` or `--llm-model` the monitored run was started with. The header corrects itself on the next `action_complete`. This is accepted, not fixed here.
- **`ll-loop show`.** The `llm:` summary prints `model_hint=<hint>` when it is set. The `model=` comparison uses `DEFAULT_LLM_MODEL` instead of the hardcoded `"sonnet"`.

## Motivation

After ENH-3547, `llm.model_hint` selects the model for evaluators and SDK/batch prompt actions, and a state-level `model_hint` selects the model for CLI actions. The header still shows `DEFAULT_LLM_MODEL` before dispatch and ignores the selection fields afterward. An operator cannot see from the console which model a hint selected, or whether a resume changed it. Events carry the selection, but nobody reads the raw events live.

## Proposed Solution

Add three pure helpers to `cli/loop/header.py`:

- `format_model_selection`, which maps `(requested, resolved, backend)` to the display string.
- `compose_model_line`, which appends effort.
- `initial_model_display`, which applies the pre-dispatch precedence and never raises.

Compute the initial string at each entry point and pass it wherever `model=` is passed today, renamed to `model_display=`. Replace the duplicated composition at `runner.py:393` and `header.py:136` with `compose_model_line`. Extend the `feed.py` `action_complete` hook to rebuild the string from the event fields.

## Program Design

### Types

- No new types. The helpers take plain strings, which come from ENH-3547's event fields or the `ModelSelection` fields.

### Signatures

- `format_model_selection(requested: str | None, resolved: str | None, backend: str | None) -> str | None` — new pure helper in `cli/loop/header.py`; treats the selection as a hint iff `requested in MODEL_HINTS`; returns `<requested> → <resolved> (<backend>)` for a hint (without the backend suffix when `backend` is `None`), the bare `resolved` (else `requested`) for a literal, and `None` when both are `None`.
- `compose_model_line(display: str | None, effort: str | None) -> str | None` — new pure helper in `cli/loop/header.py`; appends `_effort_code(effort)` after the whole display string; replaces the inline composition in `header.py` and `runner.py`.
- `initial_model_display(fsm: FSMLoop, run_model: str | None, overrides: dict[str, dict[str, str | Literal[False]]] | None) -> str | None` — new helper in `cli/loop/header.py`; applies the pre-dispatch precedence (`run_model`, then `llm.model_hint` resolved against `resolve_host().name`, then `fsm.llm.model`); catches `ModelHintError` and `HostNotConfigured`, never raises.
- `run_foreground(..., model_display: str | None = None, ...)`, `StateFeedRenderer.__init__(..., model_display: str | None = None, ...)`, `_render_pinned_pane(..., model_display: str | None = None, ...)`, `_build_pinned_pane(..., model_display: str | None = None, ...)` and `_render_artifact_header_lines(fsm, loop_path, model_display, ...)` — existing functions whose `model` parameter is renamed; behavior is unchanged except that the value is a display string.

### Call Path

- `cmd_run` / `cmd_resume` / `cmd_monitor` → `initial_model_display` → `run_foreground` / `StateFeedRenderer` → `compose_model_line` → header render
- `StateFeedRenderer._redraw_pinned` → `_render_pinned_pane` (`feed.py:667`) → `_build_pinned_pane` (`feed.py:446`) → `_render_artifact_header_lines` (`feed.py:367`) → `compose_model_line`
- `StateFeedRenderer.handle_event` (`action_complete`) → `format_model_selection` → `compose_model_line` → header redraw

## Integration Map

- `scripts/little_loops/cli/loop/header.py`: the three helpers, and `_render_artifact_header_lines` switched to `compose_model_line` (parameter renamed to `model_display`).
- `scripts/little_loops/cli/loop/runner.py`: `run_foreground` switched to `compose_model_line` (parameter renamed to `model_display`).
- `scripts/little_loops/cli/loop/feed.py`: the live-update hook; the `StateFeedRenderer` `model` → `model_display` rename (parameter and `self.model` attribute); the `_render_pinned_pane` and `_build_pinned_pane` parameter renames; and the pass-through sites `feed.py:667` (into `_render_pinned_pane`), `feed.py:446` (into `_build_pinned_pane`), `feed.py:367` and `feed.py:787`.
- `scripts/little_loops/cli/loop/run.py`: `cmd_run` passes `run_model` and `_config.orchestration.model_hints`, and passes `effort=run_effort or fsm.llm.effort`.
- `scripts/little_loops/cli/loop/lifecycle.py`: `cmd_resume` passes `run_model=None` and `config.orchestration.model_hints`; `cmd_monitor` passes `run_model=None` and `_config.orchestration.model_hints`.
- `scripts/little_loops/cli/loop/info.py`: `model_hint=`, and the `DEFAULT_LLM_MODEL` comparison.
- `docs/reference/CLI.md` § "Model Header Display (ENH-1805)": a rewrite of the section, not just its example (see step 7).
- Tests: `test_ll_loop_display.py`, `test_state_feed_renderer.py` (the `model` → `model_display` rename), `test_cli_loop_lifecycle.py` (`TestCmdResume`), `test_cli_loop_dispatch.py`, plus the existing header and `info` tests.

## Implementation Steps

0. **Golden tests first (TDD).** Before any refactor, add golden tests that pin today's rendered header for a no-hint loop without `--model`:
   - the `_render_artifact_header_lines` output, both with and without effort;
   - the inline `run_foreground` `model:` line, both with and without effort.

   They must pass on the unchanged code. They make the byte-identical AC something a test can check through the `compose_model_line` refactor.
1. Add `format_model_selection`, `compose_model_line` and `initial_model_display` with unit tests:
   - hint, literal, SDK-literal alias (`sonnet`/`claude-sonnet-5` renders as a literal), and `backend=None`;
   - unresolved hint (a `False` mapping, and an unsupported backend such as opencode), and no host CLI;
   - effort composition;
   - the `--model` precedence.
2. Switch `header.py:136` and `runner.py:393` to `compose_model_line`. In `header.py`, name the composed local `model_line` (not `model_display`) so step 3's parameter rename does not collide with it.
3. Rename the `model` parameter to `model_display` on `run_foreground`, `StateFeedRenderer` (parameter and `self.model` attribute), `_render_pinned_pane`, `_build_pinned_pane` and `_render_artifact_header_lines`, and update the affected tests (`test_state_feed_renderer.py:165,166,176,322`, `test_ll_loop_display.py:2804`).
4. Wire `initial_model_display` through `cmd_run`, `cmd_resume` and `cmd_monitor`. Then pass the string through `run_foreground` and the `feed.py` sites (`667` → `446` → `367`, and `787`). In `cmd_run`, also pass `effort=run_effort or fsm.llm.effort`.
5. Extend the `feed.py:843-849` live-update hook with the two branches: selection fields present (observed model wins over `model_resolved`), and selection fields absent (today's behavior).
6. Add `model_hint=` to `info.py` and replace the hardcoded `"sonnet"` with `DEFAULT_LLM_MODEL`.
7. Rewrite `docs/reference/CLI.md` § "Model Header Display (ENH-1805)". The current section has several wrong claims:
   - **Wrong model source.** It says the model is "detected from the Claude CLI `stream-json` init event". The pre-dispatch value actually comes from the loop declaration and run flags, and later values come from the observed model on `action_complete`. Replace the claim.
   - **Nonexistent fallback.** It says that when detection fails "the field shows `unknown`". No such fallback exists. Remove the sentence.
   - **Incomplete precedence.** It says "`--llm-model` reflects the override". Replace this with the full pre-dispatch precedence: `--model` → `llm.model_hint` (as `<hint> → <resolved> (<backend>)`) → `llm.model` (which `--llm-model` sets).
   - **Missing notes.** Add two:
     - `ll-loop resume` reactivates a YAML `llm.model_hint` that `--llm-model` cleared at run start.
     - After the first dispatch, the header shows the observed model of the most recent action.
   - **Effort sources.** Keep the claim that `--effort` shows in the header, which becomes true once `cmd_run` passes `run_effort`. Note that `ll-loop resume` and `ll-loop monitor` show only `llm.effort` until the first action.
   - **Examples.** Add a hint example, show the `L`/`H` effort codes instead of the stale `[LOW]`, and use a current model ID instead of `claude-sonnet-4-6`.

   Then run the display, feed-renderer and lifecycle tests.

## Impact

- **Priority**: P3 - diagnostic visibility only; dispatch is already correct after ENH-3547.
- **Effort**: Small to medium - six display files, and no executor changes.
- **Risk**: Low - display-only. The no-hint, no-`--model` header must stay byte-identical.
- **Breaking Change**: No

## Scope Boundaries

- **In scope**:
  - the three header helpers;
  - the three entry points (`cmd_run`, `cmd_resume`, `cmd_monitor`) and `run_foreground`;
  - the `cmd_run` initial effort from `--effort` (`run_effort`);
  - the feed live update;
  - `info.py`;
  - the `model` → `model_display` parameter rename along the render chain;
  - rewriting the "Model Header Display (ENH-1805)" section in `docs/reference/CLI.md`.
- **Out of scope**:
  - Event payload fields and dispatch resolution (ENH-3547).
  - Validate warnings and the remaining hint docs (ENH-3548).
  - Displaying the evaluator's selection. `evaluate` events also carry the three selection fields (`executor.py:3249,3301`), and for a CLI-host loop that is where `llm.model_hint` actually shows up. It is possible later work, for example as a separate `eval:` header segment.
  - `cmd_resume` dropping the run's `--model`. This is a pre-existing gap: resume constructs `PersistentExecutor` without `run_model`.
  - Monitor replay of run-start overrides.
  - Resolving the pre-dispatch hint against the initial state's request path (`anthropic-api` for SDK/batch consumers). This is an accepted limitation; see Expected Behavior.
  - Extending the `evidence.py:269,460-489` `assemble_bundle` allowlist with the three selection fields. Also possible later work.

## Acceptance Criteria

- [ ] Golden tests that pin today's no-hint header, with and without effort, on both `_render_artifact_header_lines` and the `run_foreground` inline line, are added before the refactor and pass both before and after it.
- [ ] Before the first dispatch, a hint-only loop's header shows `<hint> → <resolved> (<backend>)`. A no-declaration or literal header without `--model` is byte-identical to today's.
- [ ] The render-chain parameter is named `model_display` on `run_foreground`, `StateFeedRenderer` (including its attribute), `_render_pinned_pane`, `_build_pinned_pane` and `_render_artifact_header_lines`. No `model=` kwarg that carries the display string remains.
- [ ] With `--effort E`, the `cmd_run` header shows the effort code for `E` before the first dispatch. Without `--effort` the header is byte-identical to today's.
- [ ] No test asserts that the header text stays the same across the alias → observed-ID change (`coding → sonnet` → `coding → claude-sonnet-5`) or across actions in a mixed hinted/undeclared loop.
- [ ] With `--model X`, the `cmd_run` header shows `X` before the first dispatch. This is an intentional change from `fsm.llm.model`.
- [ ] Hint detection uses `MODEL_HINTS` membership. An SDK-path literal (`requested=sonnet`, `resolved=claude-sonnet-5`) renders bare, not as a hint.
- [ ] Effort composes after the display string through `compose_model_line` on both `header.py` and `runner.py`. No duplicated composition remains.
- [ ] `cmd_run`, `cmd_resume` and `cmd_monitor` all show the resolved hint selection for a hint-only loop before the first dispatch, not `DEFAULT_LLM_MODEL`.
- [ ] An unmapped, unconsumed `llm.model_hint` renders `<hint> (unresolved on <backend>)`, including on an unsupported backend such as opencode. No host CLI renders `<hint> (unresolved: no host CLI)`. Neither raises.
- [ ] An `action_complete` event carrying the three selection fields updates the header to `<requested> → <observed model or model_resolved> (<backend>)`.
- [ ] An `action_complete` event without selection fields shows the bare observed `model` (today's behavior). This includes the change from the pre-dispatch hint label to the host default for a hint-only CLI loop.
- [ ] A resume of a run started with `--llm-model X` shows the reactivated `llm.model_hint` selection, not `X`.
- [ ] `ll-loop show` shows `model_hint=<hint>` for a hint-only `llm` block, and compares `model=` against `DEFAULT_LLM_MODEL`.
- [ ] The `docs/reference/CLI.md` "Model Header Display" section:
  - no longer claims `stream-json` init-event detection or an `unknown` fallback;
  - documents the `--model` → `llm.model_hint` → `llm.model` pre-dispatch precedence;
  - documents resume reactivating the hint and the switch to the observed model after dispatch;
  - includes a hint example;
  - matches the rendered effort-code format.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Resolution

- **Status**: Completed
- **Completed**: 2026-09-28T21:54:26Z
- **Action**: improve
- Added `format_model_selection`, `compose_model_line`, `initial_model_display` to `cli/loop/header.py`; both header render paths now use `compose_model_line`.
- Renamed `model` → `model_display` along the render chain (`run_foreground`, `StateFeedRenderer`, `_render_pinned_pane`, `_build_pinned_pane`, `_render_artifact_header_lines`).
- `cmd_run` / `cmd_resume` / `cmd_monitor` pass `initial_model_display(...)`; `cmd_run` passes `run_effort or fsm.llm.effort`.
- `StateFeedRenderer` `action_complete` rebuilds the display from `model_requested`/`model_resolved`/`model_backend` (observed model wins).
- `ll-loop show` prints `model_hint=` and compares against `DEFAULT_LLM_MODEL`.
- Rewrote `docs/reference/CLI.md` § Model Header Display.
- Tests: golden header tests, `test_loop_model_display.py`, resume wiring, `show` model_hint.

## Status

**Completed** | Created: 2026-09-27 | Completed: 2026-09-28T21:54:26Z | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-09-28T21:54:26 - `58b447bf-2fdf-4de7-a511-a87e3ccf565b.jsonl`
- `/ll:ready-issue` - 2026-09-28T21:45:03 - `c36a34a2-b7a4-4553-812b-bece1a7c96ac.jsonl`
- `/ll:confidence-check` - 2026-09-28T20:24:41 - `c4c78c52-d947-4bd2-b3a6-6c632bd38fd7.jsonl`
- `/ll:confidence-check` - 2026-09-28T19:39:10 - `af11844b-bc48-4035-9869-d5e630b26c85.jsonl`
