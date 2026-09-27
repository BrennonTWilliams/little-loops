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
blocked_by:
- ENH-3547
relates_to:
- ENH-3548
---

# ENH-3638: Show hint-resolved model selection in ll-loop header and show

## Summary

Show the hint-resolved model selection in the `ll-loop` console header and in `ll-loop show`. ENH-3547 wires `model_hint` resolution into dispatch and adds `model_requested` / `model_resolved` / `model_backend` to event payloads. This issue makes that selection visible on every header render path. It was split out of ENH-3547 on 2026-09-27 because the display work carried most of that issue's remaining ambiguity (outcome confidence 46).

## Current Behavior

- `run.py:710`, `lifecycle.py:775-776` (`cmd_resume`) and `lifecycle.py:854-855` (`cmd_monitor`) pass `model=fsm.llm.model` to `run_foreground` / `StateFeedRenderer`. `LLMConfig.model` keeps its default (`DEFAULT_LLM_MODEL`) when `llm.model_hint` is set, so a hint-only loop shows the default model in the header.
- There are two independent header renderers: `header.py:_render_artifact_header_lines` (line 109; called from `feed.py:367` and `feed.py:787`) and the inline `model_line` at `runner.py:390-394` (`model if effort is None else f"{model} {_effort_code(effort)}"`).
- `StateFeedRenderer.handle_event` (`feed.py:843-849`) updates `self.model` / `self.effort` live from `action_complete` events, but only from `model` / `effort`. It does not read the ENH-3547 selection fields.
- `info.py:1528` (`cmd_show`) prints `llm: model=` only when the value is not `sonnet`, and never prints `model_hint`. A hint-only loop looks like the default.

## Expected Behavior

- **One display string, not three kwargs.** A shared helper, for example `format_model_selection(requested, resolved, backend) -> str`, builds the model-line text. Format: `<requested> → <resolved> (<backend>)` for a hint, for example `coding → sonnet (claude-code)`. A literal shows the bare value, which is today's display unchanged. The render sites take the string. They do not take `model_requested` / `model_resolved` / `model_backend` separately.
- **Effort composition.** The effort code goes after the whole display string: `coding → sonnet (claude-code) H`.
- **Initial value (before the first dispatch).** Run `--model` if set. Otherwise the `llm` declaration resolved against the CLI host (`resolve_host().name`, overrides from `orchestration.model_hints`).
- **Never raise.** A loop whose `llm.model_hint` nothing consumes (all-shell states, or `--no-llm`) passes the ENH-3547 preflight, but its hint may have no mapping on the CLI host. The helper catches `ModelHintError` and shows `<hint> (unresolved on <backend>)`. It must never raise from `run.py` / `lifecycle.py`.
- **Live update.** `StateFeedRenderer.handle_event`'s `action_complete` branch rebuilds the display string from the three event fields when they are present. When they are absent it keeps today's `model` behavior.
- **All entry points.** `run.py`, `lifecycle.py` (`cmd_resume`, `cmd_monitor`) and `runner.py:390` build the string through the shared helper. `feed.py:367` and `feed.py:787` pass it through to `_render_artifact_header_lines`.
- **Resume visibility.** Resuming a run that was started with `--llm-model X` (which cleared a YAML `llm.model_hint`) reactivates the hint. The resume header must show the hint selection, not `X`.
- **`ll-loop show`.** The `llm:` summary prints `model_hint=<hint>` when set.

## Motivation

After ENH-3547, a hint-only loop runs on the hint-resolved model while its header still shows `DEFAULT_LLM_MODEL`. An operator has no way to see from the console which model a hint selected, or whether a resume changed it. Events carry the selection, but nobody reads the raw events live.

## Proposed Solution

Add one pure, non-raising display helper, for example in `cli/loop/header.py`, that maps `(requested, resolved, backend)` to the model-line string. Compute the initial string at each entry point and pass the string wherever `model=` is passed today. Extend the `feed.py` `action_complete` hook to rebuild it from event fields.

## Program Design

### Types

- No new types. The helper takes plain strings, which come from ENH-3547's event fields or `ModelSelection`.

### Signatures

- `format_model_selection(requested: str | None, resolved: str | None, backend: str | None) -> str | None` — new pure helper in `cli/loop/header.py`; returns the bare `resolved` for a literal, `<requested> → <resolved> (<backend>)` for a hint, and `None` when there is nothing to show.
- `initial_model_display(fsm, run_model: str | None) -> str | None` — builds the pre-dispatch string for the run, resolving `llm.model_hint` against `resolve_host().name`; catches `ModelHintError` and returns `<hint> (unresolved on <backend>)`.

### Call Path

- `cmd_run` / `cmd_resume` / `cmd_monitor` → `initial_model_display` → `run_foreground` / `StateFeedRenderer` → `_render_artifact_header_lines`
- `StateFeedRenderer.handle_event` (`action_complete`) → `format_model_selection` → header redraw

## Integration Map

- `scripts/little_loops/cli/loop/{header,feed,runner,run,lifecycle,info}.py`
- Tests: `test_ll_loop_display.py`, `test_cli_loop_lifecycle.py` (`TestCmdResume`), `test_cli_loop_dispatch.py`, plus the existing header/`info` tests.

## Implementation Steps

1. Add the display helper with unit tests (hint, literal, unresolved, effort composition).
2. Wire the initial string through `run.py`, `lifecycle.py` (`cmd_resume`, `cmd_monitor`), `runner.py:390`, and both `feed.py` call sites.
3. Extend the `feed.py:843-849` live-update hook, and add `model_hint` to `info.py`.
4. Update the `docs/reference/CLI.md` header example, then run the display and lifecycle tests.

## Impact

- **Priority**: P3 - diagnostic visibility only; dispatch is already correct after ENH-3547.
- **Effort**: Small to medium - six display files, and no executor changes.
- **Risk**: Low - display-only; the no-hint header must stay byte-identical.
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: the header display helper, the four header entry points, the feed live update, `info.py`, and updating the "Model Header Display (ENH-1805)" example in `docs/reference/CLI.md`.
- **Out of scope**: event payload fields and dispatch resolution (ENH-3547); validate warnings and the remaining hint docs (ENH-3548). Also out of scope, as possible later work: extending the `evidence.py:269,460-489` `assemble_bundle` allowlist with the three selection fields.

## Acceptance Criteria

- [ ] A hint header shows `<hint> → <resolved> (<backend>)`. A literal or no-declaration header is byte-identical to today's.
- [ ] Effort composes after the display string on both `header.py` and `runner.py:390`.
- [ ] `cmd_run`, `cmd_resume` and `cmd_monitor` all show the resolved selection for a hint-only loop, not `DEFAULT_LLM_MODEL`.
- [ ] An unmapped, unconsumed `llm.model_hint` renders `<hint> (unresolved on <backend>)` and does not raise.
- [ ] The header updates live from an `action_complete` event carrying the three selection fields.
- [ ] A resume that drops an earlier `--llm-model` override shows the reactivated `llm.model_hint` selection.
- [ ] `ll-loop show` shows `model_hint=<hint>` for a hint-only `llm` block.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3
