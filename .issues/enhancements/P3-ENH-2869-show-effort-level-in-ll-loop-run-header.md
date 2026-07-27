---
id: ENH-2869
status: open
captured_at: '2026-07-27T00:00:00Z'
discovered_date: 2026-07-27
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 73
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 16
score_change_surface: 17
---

# ENH-2869: Show effort level in `ll-loop run` header

## Summary

`ll-loop run`'s CLI header prints `loop:`/`input:` and `run_dir:`/`model:` rows via `_render_artifact_header_lines()` (`scripts/little_loops/cli/loop/_helpers.py:1294-1340`). Add a fourth field, immediately after `model:`, that shows the reasoning-effort level for the run — but only when an effort level is actually set. There is currently no effort concept anywhere in the FSM loop system (`fsm/schema.py`'s `FSMLoop`/`StateConfig` have `model` fields but no `effort` field; no `--effort` CLI flag on `ll-loop run`; `_resolve_action_model()` in `fsm/executor.py:2249` resolves only `state.model or self.run_model or self.fsm.llm.model`), so this issue needs to both introduce the concept and surface it in the header.

## Current Behavior

`_render_artifact_header_lines()` packs `input:` onto the `loop:` row and `model:` onto the `run_dir:` row (lines 1319-1327), falling back to a standalone `model:` line when no `run_dir` is present. There is no field for effort level, and no underlying data source for one — `model` is resolved via `_resolve_action_model()` (`fsm/executor.py:2249`) with no effort component, and `_helpers.py:1084-1086` refreshes `self.model` from the live SDK/action event's `model` key only.

## Expected Behavior

When a run has an effort level set (state-level override, run-level override, or loop default — mirroring the existing `state.model or self.run_model or self.fsm.llm.model` precedence pattern used for `_resolve_action_model()`), the header shows the effort level appended directly to the `model:` value — not as its own labeled field. Unlike the other header fields, effort gets no `effort:` label: it's shown one space after the model name, in brackets and upper-cased, e.g. `Model: claude-sonnet-5 [LOW]`. When no effort level is set anywhere in that chain, nothing is appended — the `model:` value is shown bare, matching current behavior.

## Motivation

Loops can already invoke agents/subagents with a `low`/`medium`/`high`/`xhigh`/`max` reasoning-effort setting elsewhere in the harness (e.g. Task/Agent tool `effort` param, Workflow `agent()` `opts.effort`), but FSM loop states have no equivalent, and the run header gives no visibility into it. Once effort control is added to FSM states, users watching `ll-loop run` output need to see at a glance which effort tier a run is using, the same way they can already see which model it's using.

## Proposed Solution

1. Add an `effort` field to `StateConfig` and `FSMLoop.llm`/run-level config in `scripts/little_loops/fsm/schema.py` (near the existing `model` fields), accepting the same `low|medium|high|xhigh|max` vocabulary used elsewhere in the harness.
2. Add a `_resolve_action_effort(self, state)` in `fsm/executor.py` mirroring `_resolve_action_model()` (`fsm/executor.py:2249`): `state.effort or self.run_effort or self.fsm.llm.effort`.
3. Thread the resolved effort value into the header renderer the same way `model` is threaded today — via the constructor param at `_helpers.py:859` and the live-event refresh at `_helpers.py:1084-1086` (reading an `effort` key from the action event, if the host CLI/SDK reports one).
4. In `_render_artifact_header_lines()` (`_helpers.py:1294-1340`), add an `effort` parameter and, when `effort is not None`, append it to the existing `model:` value — no separate label, one space after the model name, upper-cased and bracketed: `model: <model_value> [<EFFORT>]` (e.g. `model: claude-sonnet-5 [LOW]`). When `effort is None`, the `model:` value is unchanged from current output.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Add `--effort` argparse registration in `cli/loop/__init__.py` (184-186) and `cmd_run()` in `run.py` (159-160, 183-189), thread `run_effort=getattr(args, "run_effort", None)` into `PersistentExecutor` at `run.py:577`, and pass `effort=` alongside `model=fsm.llm.model` into `run_foreground()` at `run.py:600`.
6. Thread `effort=` through `run_foreground()` (1675-1745) → `StateFeedRenderer` → `_redraw_pinned()` (884-905) → `_render_pinned_pane()`/`_build_pinned_pane()` (600-604, 625) → `_render_artifact_header_lines()`, and through `lifecycle.py:cmd_resume()`'s `run_foreground()` call (~617) for resumed runs.
7. Add `--effort` forwarding in the detached/handoff subprocess re-exec block at `_helpers.py:1593-1595` (currently only forwards `--model`).
8. Add a parallel `effort` property to `StateConfig.model`/`LLMConfig.model` blocks in `fsm/fsm-loop-schema.json` (571-574, 902-906).
9. Update `docs/reference/CLI.md` (flag table 562-563, header example 606-614, per-state field note 675), `docs/guides/LOOPS_GUIDE.md` (587-601, 738), and `docs/reference/API.md` (`StateConfig`/`LLMConfig`/`PersistentExecutor` field listings) to document the new field/flag.
10. Update all 9 call sites in `test_state_feed_renderer.py::TestRenderArtifactHeaderLines` for the new `effort` param, sync `test_ll_loop_parsing.py::_create_run_parser`'s fixture parser with the real `--effort` registration, and add the new schema round-trip / precedence / CLI-flag tests listed in Integration Map → Tests.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `effort` field(s)
- `scripts/little_loops/fsm/executor.py` — add `_resolve_action_effort()`, call sites near `_resolve_action_model()` (line 2249); must be called on **both** the SDK/Batches dispatch branch (`_dispatch_live()` at `executor.py:2279`) and the host-CLI-binary dispatch path (`executor.py:1702`, currently an inline `state.model or self.run_model` two-tier expression with no `_resolve_action_model()` call) — `ll-loop run` typically dispatches via the host-CLI path, so mirroring only the SDK branch leaves the header blank for the common case
- `scripts/little_loops/cli/loop/_helpers.py` — `_render_artifact_header_lines()` (1294-1340), its two call sites (601, 1028), constructor at 859, live-refresh at 1084-1086, plus `_redraw_pinned()`/`_render_pinned_pane()`/`_build_pinned_pane()` chain (884-905, 600-604, 625) and `run_foreground()` (1675-1745, model param at 1686/1734/1744-1745)
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()`: `--model`/`--llm-model` argparse block (~159-160, 183-189) needs a parallel `--effort` flag; `run_model=getattr(args, "run_model", None)` threading at line 577 needs a parallel `run_effort=` line; `model=fsm.llm.model` passed to `run_foreground()` at line 600 needs a parallel `effort=` argument
- `scripts/little_loops/cli/loop/__init__.py` — `--model` argparse registration (184-186) needs a parallel `--effort` registration
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` calls `run_foreground()` with `model=fsm.llm.model` (line ~617); needs a parallel `effort=` argument for resumed runs to also show the header suffix
- `scripts/little_loops/fsm/fsm-loop-schema.json` — hand-maintained JSON Schema mirror of the dataclasses (distinct from any auto-generated `LLEvent` schemas); `StateConfig.model` property block (571-574) and `LLMConfig.model` property block (902-906) each need a parallel `effort` property definition — no confirmed auto-regeneration tool covers this file, treat as a manual parallel edit

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- Both call sites of `_render_artifact_header_lines(` in `_helpers.py` (lines 601, 1028) must pass the new `effort` argument.
- `_helpers.py:1593-1595` — subprocess re-forwarding for handoff/detached runs currently only forwards `--model` (`if run_model: cmd.extend(["--model", run_model])`); needs a parallel `--effort` forward or a detached/handoff run silently drops the effort setting.
- `scripts/little_loops/fsm/validation.py:693-704` — existing lint rule warns when `state.model` is set on an `action_type` that can't use it (shell/mcp_tool/contract states); if `effort` inherits the same action-type applicability, this rule's pattern should be mirrored for `state.effort` (or the asymmetry — silent no-op instead of a warning — should be a deliberate scope decision, not an oversight).

### Similar Patterns
- `_resolve_action_model()` (`fsm/executor.py:2249`) is the precedence pattern to mirror for effort resolution.
- `StateConfig.session_mode` / `FSMLoop.session_mode` (`fsm/schema.py:667-672`, `1260-1266`) is the closer schema-field precedent than `model` itself — `test_fsm_schema.py:4009-4078`'s `session_mode` block is an explicit 5-test skeleton (state round-trip, state-omit-when-None, state-default, FSMLoop round-trip, FSMLoop-omit-default) that documents itself as mirroring `model`'s pattern and is the template to clone for `effort`.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_state_feed_renderer.py::TestRenderArtifactHeaderLines` — **must be updated, not just extended**: all 9 existing positional call sites to `_render_artifact_header_lines(fsm, loop_path, model, input, width)` (lines 559, 570, 584, 595, 605, 621, 640, 669, 691) will need the new `effort` argument threaded in once the signature changes (add as an optional keyword-only trailing param to avoid breaking all 9 at once).
- `scripts/tests/test_fsm_schema.py` — new tests mirroring the `session_mode` 5-test skeleton at lines 4009-4078: `test_state_effort_round_trips`, `test_state_effort_none_omitted_from_dict`, `test_state_effort_defaults_none`, `test_fsmloop_effort_round_trips` (or `test_llmconfig_effort_round_trips`), `test_fsmloop_default_omits_effort_key`.
- `scripts/tests/test_ll_loop_execution.py` — new tests mirroring `test_run_model_used_as_fallback_for_host_action` and `test_state_model_overrides_run_model` (~977-1037) for `_resolve_action_effort()` precedence; and mirroring `test_run_model_flag_accepted_with_dry_run`/`test_run_model_propagates_to_fsm_executor` (895-975) for the new `--effort` CLI flag's end-to-end propagation into `FSMExecutor.__init__` kwargs.
- `scripts/tests/test_ll_loop_parsing.py` — `_create_run_parser()` fixture (lines 26-51) mirrors the real argparse setup in `cli/loop/__init__.py:184-186` but has no `--effort`; must gain a matching `parser.add_argument("--effort", ...)` line, plus new tests mirroring `test_run_model_flag_parsed_correctly`, `test_run_model_default_is_none`, `test_run_model_independent_of_llm_model` (205-223).
- **Verify before implementing** (not confirmed to need changes, but reference `action_complete`): `scripts/tests/test_generate_schemas.py` and `scripts/tests/test_otel_attributes.py` may enumerate/validate the full known-key set of the `action_complete` event payload (`executor.py:1710-1739`) — check both before adding a new `effort` key to that payload, since no test currently hard-asserts on its exact key set but these two are the most likely to.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `--model`/`--llm-model` flag table (lines 562-563) needs a parallel `--effort` row; prose + literal example block documenting the header's model line (lines 606-614, e.g. `model: claude-sonnet-4-6`) needs a companion effort example; note at line 675 (`agent:`, `tools:`, `model:` are per-state YAML fields, not CLI flags) needs `effort:` added if it becomes a per-state YAML field.
- `docs/guides/LOOPS_GUIDE.md` — `model:` per-state field doc + haiku-pinning guidance table (lines 587-601) needs a parallel `effort:` entry if documented as a state-level override; line 738 (diagram header packs "the model (packed onto the `run_dir:` row)") needs updating to describe where `effort` is packed.
- `docs/reference/API.md` — `StateConfig` dataclass field listing (~line 5095, `model: str | None = None`) needs a parallel `effort` field line; `LLMConfig` dataclass field listing (~line 5297) needs the same if `LLMConfig.effort` is added; `PersistentExecutor` constructor signature (~line 5516, `model: str | None = None`) needs a parallel `effort`/`run_effort` param line.
- `scripts/tests/test_wiring_reference_docs.py` — maintains a pinned-string registry `(doc_file, expected_substring, issue_id)` asserting specific issue-introduced text stays present in `docs/reference/API.md`; may need a new `("docs/reference/API.md", "<effort-related substring>", "ENH-2869")` row once API.md is updated, following the existing convention (e.g. rows for ENH-1433, ENH-1734, ENH-1866).

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json` — see Files to Modify above; `StateConfig.model` (571-574) and `LLMConfig.model` (902-906) property blocks each need a parallel `effort` property definition with equivalent override-precedence/action-type-exemption description language.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No existing effort vocabulary in this repo**: a repo-wide grep for `effort` outside issue-tracking (`impact_effort.py`, issue `effort:` estimates) finds no `Literal["low", "medium", "high", "xhigh", "max"]` type anywhere in `scripts/little_loops/`. The `low`/`medium`/`high`/`xhigh`/`max` vocabulary cited in the issue is external (host Agent/Task tool schema, `Workflow.agent()` `opts.effort`) — there is nothing to import; the new field should be a plain `str | None` like `model`/`session_mode`, not a `Literal`.
- **Closest existing convention for the new field**: `StateConfig.session_mode` (`fsm/schema.py:667-672`) and `FSMLoop.session_mode` (`fsm/schema.py:1260-1266`) are the precedent for adding a second, independently-optional, state-override-with-loop-default string field next to `model` — plain `str | None = None`, vocabulary documented only in an adjacent comment, with the standard conditional `to_dict()` emit (`if self.x is not None: result["x"] = self.x`) and `from_dict()` parse (`data.get("x")`). `StateConfig.model` itself follows the same shape at `fsm/schema.py:659` (`to_dict` 742-743, `from_dict` 856).
- **`LLMConfig.model` (`fsm/schema.py:913-954`, field at line 927) is the loop-default tier** `_resolve_action_model()` falls back to via `self.fsm.llm.model`; it has a `DEFAULT_LLM_MODEL` constant at `schema.py:22`. There is no analogous default-effort constant today — an `LLMConfig.effort` field can default to `None` (no forced default needed, since the header only appends a suffix when set).
- **`run_effort` doesn't exist yet and needs new CLI plumbing**: unlike `run_model` (constructor param on `PersistentExecutor` set at `executor.py:186,230`, threaded from the CLI via `getattr(args, "run_model", None)` at `run.py:577`), there is no `--effort` flag or `run_effort` concept anywhere today. Step 2 of the Proposed Solution (`_resolve_action_effort`) requires this new flag + constructor param, not just the resolver method.
- **Gap in the Proposed Solution's dispatch coverage**: `_resolve_action_model()` (`executor.py:2249-2260`) is only called from the SDK/Batches dispatch branch (`_dispatch_live()` at `executor.py:2279`, gated by `FEAT-2716`'s `request_path`). The host-CLI-binary dispatch path (`executor.py:1702`) uses a separate inline two-tier expression (`state.model or self.run_model`, no `fsm.llm.model` fallback, since the host binary applies its own default) and does not call `_resolve_action_model()` at all. Since `ll-loop run` typically dispatches via the host CLI (not SDK/Batches), `_resolve_action_effort()` needs to be called on **both** paths for the header to show effort on ordinary runs — mirroring only the SDK branch (as written) would leave the header blank for the common case.
- **Event payload has no `effort` key today**: the `action_complete` payload built at `executor.py:1710-1739` carries `model` sourced from `result.usage_events[-1].model` (`executor.py:1726,1731`) but has no equivalent `effort` source — host-CLI/SDK usage events don't report a reasoning-effort value. The live-refresh step (Proposed Solution step 3, `_helpers.py:1084-1086`) can only read `event.get("effort")` if the executor is first changed to emit that key (likely the *resolved* value from `_resolve_action_effort()`, not a host-reported "actual" value, since no host surface reports one back).
- **Additional threading point not listed in the Integration Map**: `_redraw_pinned()` (`_helpers.py:884-905`) forwards `model=self.model` into `_render_pinned_pane()` at `_helpers.py:903`, which in turn calls the non-class call site of `_render_artifact_header_lines()` at `_helpers.py:600-604` (`_render_pinned_pane`'s own `model` parameter, not `self.model` directly). An `effort` value needs threading through this call chain too, in addition to the two call sites already listed.
- **Existing header tests to extend**: `scripts/tests/test_state_feed_renderer.py:551-694`, class `TestRenderArtifactHeaderLines` (docstring cites ENH-2596), already has the exact template to follow — e.g. `test_model_packed_onto_run_dir_line` and `test_model_standalone_line_when_no_run_dir` construct an `FSMLoop`/`StateConfig` fixture, call `_render_artifact_header_lines(fsm, loop_path, model, input_value, cols)` positionally, and assert on substring presence/absence. New tests should mirror this shape, asserting the bracketed `[LOW]` suffix appears only when `effort is not None` and is absent (bare `model:`) otherwise.

## Impact

- **Priority**: P3 - Cosmetic/observability enhancement, not blocking any workflow.
- **Effort**: Medium - Requires adding a new schema field, executor resolution function, and threading it through the header renderer and its two call sites, plus tests for the conditional-visibility behavior.
- **Risk**: Low - Purely additive; omitted when unset, so no behavior change for existing loops without an effort field.
- **Breaking Change**: No

## Scope Boundaries

- Does not implement effort-based model routing/host-CLI invocation behavior — only schema plumbing needed to resolve a value for display, plus whatever minimal wiring is needed to pass a real effort setting through to the host CLI invocation if one doesn't already exist as a side effect of adding the field.
- Does not add effort level to any output other than the `ll-loop run` CLI header (e.g. not added to `ll-loop diagram`, JSON summaries, or other reporting surfaces).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:confidence-check` - 2026-07-27T22:09:58 - `dc7b97b2-5fb5-4663-a58c-b2d0b4ed36e1.jsonl`
- `/ll:wire-issue` - 2026-07-27T22:08:35 - `4df334c0-8486-4924-989f-828d3f4812d1.jsonl`
- `/ll:refine-issue` - 2026-07-27T22:02:02 - `18aefba9-f220-445e-aa33-430e2cbf1440.jsonl`
- `/ll:capture-issue` - 2026-07-27 - see current session

---
## Status
**Open** | Created: 2026-07-27 | Priority: P3
