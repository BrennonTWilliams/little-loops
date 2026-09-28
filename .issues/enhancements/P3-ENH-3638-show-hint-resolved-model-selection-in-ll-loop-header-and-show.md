---
id: ENH-3638
type: ENH
title: Show hint-resolved model selection in ll-loop header and show
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T21:28:20Z'
parent: EPIC-3563
labels:
- multi-host
- loops
epic: EPIC-3563
relates_to:
- ENH-3547
- ENH-3548
---

# ENH-3638: Show hint-resolved model selection in ll-loop header and show

## Summary

Show the hint-resolved model selection in the `ll-loop` console header and in `ll-loop show`. ENH-3547 (done) wires `model_hint` resolution into dispatch and adds `model_requested` / `model_resolved` / `model_backend` to event payloads. This issue makes that selection visible on every header render path. It was split out of ENH-3547 on 2026-09-27 because the display work carried most of that issue's remaining ambiguity (outcome confidence 46).

## Current Behavior

- `run.py:710`, `lifecycle.py:775` (`cmd_resume`) and `lifecycle.py:854` (`cmd_monitor`) pass `model=fsm.llm.model` to `run_foreground` / `StateFeedRenderer`. `LLMConfig.model` keeps its default (`DEFAULT_LLM_MODEL`, `"sonnet"`) when `llm.model_hint` is set, so a hint-only loop shows the default model in the header.
- `run.py:710` passes `fsm.llm.model` even when `--model` (`run_model`) is set, although `--model` is what CLI actions actually dispatch with.
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
- **Never raise.** A loop whose `llm.model_hint` nothing consumes (all-shell states, or `--no-llm`) passes the ENH-3547 preflight, but its hint may have no mapping on the CLI host. `initial_model_display` must never raise from `run.py` or `lifecycle.py`:
  - On `ModelHintError` it renders `<hint> (unresolved on <backend>)`.
  - On `HostNotConfigured` from `resolve_host()` it renders `<hint> (unresolved: no host CLI)`.
- **Live update.** `StateFeedRenderer.handle_event`'s `action_complete` branch works as follows:
  - **Selection fields present:** rebuild with `format_model_selection(model_requested, <observed model or model_resolved>, model_backend)`. The observed `model` wins over `model_resolved` in the resolved slot, which matches ENH-2885's observed-over-config precedence for effort.
  - **Selection fields absent:** keep today's behavior, a bare observed `model`. For a hint-only loop on a CLI host, the header changes from the pre-dispatch hint label to the host-default model after the first CLI action. That is correct: the action did run on the host default.
- **All entry points.** `cmd_run`, `cmd_resume` and `cmd_monitor` build the initial string through `initial_model_display`. `run_foreground` passes the string to both its inline header (`runner.py:393`) and `StateFeedRenderer`. `feed.py:367` and `feed.py:787` pass it through to `_render_artifact_header_lines`.
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

Compute the initial string at each entry point and pass it wherever `model=` is passed today. Replace the duplicated composition at `runner.py:393` and `header.py:136` with `compose_model_line`. Extend the `feed.py` `action_complete` hook to rebuild the string from the event fields.

## Program Design

### Types

- No new types. The helpers take plain strings, which come from ENH-3547's event fields or the `ModelSelection` fields.

### Signatures

- `format_model_selection(requested: str | None, resolved: str | None, backend: str | None) -> str | None` — new pure helper in `cli/loop/header.py`; treats the selection as a hint iff `requested in MODEL_HINTS`; returns `<requested> → <resolved> (<backend>)` for a hint (without the backend suffix when `backend` is `None`), the bare `resolved` (else `requested`) for a literal, and `None` when both are `None`.
- `compose_model_line(display: str | None, effort: str | None) -> str | None` — new pure helper in `cli/loop/header.py`; appends `_effort_code(effort)` after the whole display string; replaces the inline composition in `header.py` and `runner.py`.
- `initial_model_display(fsm: FSMLoop, run_model: str | None, overrides: dict[str, dict[str, str | Literal[False]]] | None) -> str | None` — new helper in `cli/loop/header.py`; applies the pre-dispatch precedence (`run_model`, then `llm.model_hint` resolved against `resolve_host().name`, then `fsm.llm.model`); catches `ModelHintError` and `HostNotConfigured`, never raises.

### Call Path

- `cmd_run` / `cmd_resume` / `cmd_monitor` → `initial_model_display` → `run_foreground` / `StateFeedRenderer` → `compose_model_line` → header render
- `StateFeedRenderer.handle_event` (`action_complete`) → `format_model_selection` → `compose_model_line` → header redraw

## Integration Map

- `scripts/little_loops/cli/loop/header.py`: the three helpers, and `_render_artifact_header_lines` switched to `compose_model_line`.
- `scripts/little_loops/cli/loop/runner.py`: `run_foreground` switched to `compose_model_line`.
- `scripts/little_loops/cli/loop/feed.py`: the live-update hook.
- `scripts/little_loops/cli/loop/run.py`: `cmd_run` passes `run_model` and `_config.orchestration.model_hints`.
- `scripts/little_loops/cli/loop/lifecycle.py`: `cmd_resume` passes `run_model=None` and `config.orchestration.model_hints`; `cmd_monitor` passes `run_model=None` and `_config.orchestration.model_hints`.
- `scripts/little_loops/cli/loop/info.py`: `model_hint=`, and the `DEFAULT_LLM_MODEL` comparison.
- `docs/reference/CLI.md` § "Model Header Display (ENH-1805)".
- Tests: `test_ll_loop_display.py`, `test_cli_loop_lifecycle.py` (`TestCmdResume`), `test_cli_loop_dispatch.py`, plus the existing header and `info` tests.

## Implementation Steps

1. Add `format_model_selection`, `compose_model_line` and `initial_model_display` with unit tests:
   - hint, literal, SDK-literal alias (`sonnet`/`claude-sonnet-5` renders as a literal), and `backend=None`;
   - unresolved hint, and no host CLI;
   - effort composition;
   - the `--model` precedence.
2. Switch `header.py:136` and `runner.py:393` to `compose_model_line`.
3. Wire `initial_model_display` through `cmd_run`, `cmd_resume` and `cmd_monitor`, then pass the string through `run_foreground` and both `feed.py` call sites.
4. Extend the `feed.py:843-849` live-update hook with the two branches: selection fields present (observed model wins over `model_resolved`), and selection fields absent (today's behavior).
5. Add `model_hint=` to `info.py` and replace the hardcoded `"sonnet"` with `DEFAULT_LLM_MODEL`.
6. Update the `docs/reference/CLI.md` header example: add a hint example, show the `L`/`H` effort codes instead of the stale `[LOW]`, and use a current model ID instead of `claude-sonnet-4-6`. Then run the display and lifecycle tests.

## Impact

- **Priority**: P3 - diagnostic visibility only; dispatch is already correct after ENH-3547.
- **Effort**: Small to medium - six display files, and no executor changes.
- **Risk**: Low - display-only. The no-hint, no-`--model` header must stay byte-identical.
- **Breaking Change**: No

## Scope Boundaries

- **In scope**:
  - the three header helpers;
  - the three entry points (`cmd_run`, `cmd_resume`, `cmd_monitor`) and `run_foreground`;
  - the feed live update;
  - `info.py`;
  - updating the "Model Header Display (ENH-1805)" example in `docs/reference/CLI.md`.
- **Out of scope**:
  - Event payload fields and dispatch resolution (ENH-3547).
  - Validate warnings and the remaining hint docs (ENH-3548).
  - Displaying the evaluator's selection. `evaluate` events also carry the three selection fields (`executor.py:3249,3301`), and for a CLI-host loop that is where `llm.model_hint` actually shows up. It is possible later work, for example as a separate `eval:` header segment.
  - `cmd_resume` dropping the run's `--model`. This is a pre-existing gap: resume constructs `PersistentExecutor` without `run_model`.
  - Monitor replay of run-start overrides.
  - Extending the `evidence.py:269,460-489` `assemble_bundle` allowlist with the three selection fields. Also possible later work.

## Acceptance Criteria

- [ ] Before the first dispatch, a hint-only loop's header shows `<hint> → <resolved> (<backend>)`. A no-declaration or literal header without `--model` is byte-identical to today's.
- [ ] With `--model X`, the `cmd_run` header shows `X` before the first dispatch. This is an intentional change from `fsm.llm.model`.
- [ ] Hint detection uses `MODEL_HINTS` membership. An SDK-path literal (`requested=sonnet`, `resolved=claude-sonnet-5`) renders bare, not as a hint.
- [ ] Effort composes after the display string through `compose_model_line` on both `header.py` and `runner.py`. No duplicated composition remains.
- [ ] `cmd_run`, `cmd_resume` and `cmd_monitor` all show the resolved hint selection for a hint-only loop before the first dispatch, not `DEFAULT_LLM_MODEL`.
- [ ] An unmapped, unconsumed `llm.model_hint` renders `<hint> (unresolved on <backend>)`. No host CLI renders `<hint> (unresolved: no host CLI)`. Neither raises.
- [ ] An `action_complete` event carrying the three selection fields updates the header to `<requested> → <observed model or model_resolved> (<backend>)`.
- [ ] An `action_complete` event without selection fields shows the bare observed `model` (today's behavior). This includes the change from the pre-dispatch hint label to the host default for a hint-only CLI loop.
- [ ] A resume of a run started with `--llm-model X` shows the reactivated `llm.model_hint` selection, not `X`.
- [ ] `ll-loop show` shows `model_hint=<hint>` for a hint-only `llm` block, and compares `model=` against `DEFAULT_LLM_MODEL`.
- [ ] The `docs/reference/CLI.md` header example includes a hint example and matches the rendered effort-code format.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3
