---
id: ENH-2869
status: open
captured_at: "2026-07-27T00:00:00Z"
discovered_date: 2026-07-27
discovered_by: capture-issue
---

# ENH-2869: Show effort level in `ll-loop run` header

## Summary

`ll-loop run`'s CLI header prints `loop:`/`input:` and `run_dir:`/`model:` rows via `_render_artifact_header_lines()` (`scripts/little_loops/cli/loop/_helpers.py:1294-1340`). Add a fourth field, immediately after `model:`, that shows the reasoning-effort level for the run — but only when an effort level is actually set. There is currently no effort concept anywhere in the FSM loop system (`fsm/schema.py`'s `FSMLoop`/`StateConfig` have `model` fields but no `effort` field; no `--effort` CLI flag on `ll-loop run`; `_resolve_action_model()` in `fsm/executor.py:2249` resolves only `state.model or self.run_model or self.fsm.llm.model`), so this issue needs to both introduce the concept and surface it in the header.

## Current Behavior

`_render_artifact_header_lines()` packs `input:` onto the `loop:` row and `model:` onto the `run_dir:` row (lines 1319-1327), falling back to a standalone `model:` line when no `run_dir` is present. There is no field for effort level, and no underlying data source for one — `model` is resolved via `_resolve_action_model()` (`fsm/executor.py:2249`) with no effort component, and `_helpers.py:1084-1086` refreshes `self.model` from the live SDK/action event's `model` key only.

## Expected Behavior

When a run has an effort level set (state-level override, run-level override, or loop default — mirroring the existing `state.model or self.run_model or self.fsm.llm.model` precedence pattern used for `_resolve_action_model()`), the header shows an `effort:` field directly after `model:`. When no effort level is set anywhere in that chain, the field is omitted entirely (no blank/`None` placeholder) — matching how `model:` itself is only shown when non-`None` (`_render_artifact_header_lines` line 1323/1326).

## Motivation

Loops can already invoke agents/subagents with a `low`/`medium`/`high`/`xhigh`/`max` reasoning-effort setting elsewhere in the harness (e.g. Task/Agent tool `effort` param, Workflow `agent()` `opts.effort`), but FSM loop states have no equivalent, and the run header gives no visibility into it. Once effort control is added to FSM states, users watching `ll-loop run` output need to see at a glance which effort tier a run is using, the same way they can already see which model it's using.

## Proposed Solution

1. Add an `effort` field to `StateConfig` and `FSMLoop.llm`/run-level config in `scripts/little_loops/fsm/schema.py` (near the existing `model` fields), accepting the same `low|medium|high|xhigh|max` vocabulary used elsewhere in the harness.
2. Add a `_resolve_action_effort(self, state)` in `fsm/executor.py` mirroring `_resolve_action_model()` (`fsm/executor.py:2249`): `state.effort or self.run_effort or self.fsm.llm.effort`.
3. Thread the resolved effort value into the header renderer the same way `model` is threaded today — via the constructor param at `_helpers.py:859` and the live-event refresh at `_helpers.py:1084-1086` (reading an `effort` key from the action event, if the host CLI/SDK reports one).
4. In `_render_artifact_header_lines()` (`_helpers.py:1294-1340`), add an `effort` parameter and append `effort: <value>` immediately after the `model:` text on whichever row currently carries `model:` — only when `effort is not None`, following the exact same present/absent pattern already used for `model`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `effort` field(s)
- `scripts/little_loops/fsm/executor.py` — add `_resolve_action_effort()`, call sites near `_resolve_action_model()` (line 2249)
- `scripts/little_loops/cli/loop/_helpers.py` — `_render_artifact_header_lines()` (1294-1340), its two call sites (601, 1028), constructor at 859, live-refresh at 1084-1086

### Dependent Files (Callers/Importers)
- Both call sites of `_render_artifact_header_lines(` in `_helpers.py` (lines 601, 1028) must pass the new `effort` argument.

### Similar Patterns
- `_resolve_action_model()` (`fsm/executor.py:2249`) is the precedence pattern to mirror for effort resolution.

### Tests
- `scripts/tests/` — add/extend header-rendering tests asserting `effort:` appears only when set, and its precedence order (state > run > loop default).

### Documentation
- N/A — internal CLI display and FSM schema; update `docs/reference/API.md` if `StateConfig`/`FSMLoop` schema docs enumerate fields explicitly.

### Configuration
- N/A

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
- `/ll:capture-issue` - 2026-07-27 - see current session

---
## Status
**Open** | Created: 2026-07-27 | Priority: P3
