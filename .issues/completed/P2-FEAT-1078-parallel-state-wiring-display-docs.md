---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
testable: false
confidence_score: 78
outcome_confidence: 68
---

# FEAT-1078: Parallel State Wiring, Display, and Docs

## Summary

Wire `ParallelStateConfig` and `ParallelResult` into `fsm/__init__.py`, add display handling in `cli/loop/layout.py` and `cli/loop/info.py`, and update all documentation touchpoints identified in the wiring pass.

## Parent Issue

Decomposed from FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Current Behavior

`ParallelStateConfig` and `ParallelResult` do not yet exist — they will be added to `scripts/little_loops/fsm/schema.py` by FEAT-1074 (a hard dependency). Once FEAT-1074 is complete, these types must be exported from `scripts/little_loops/fsm/__init__.py` and a `parallel` field must be added to `StateConfig`. The CLI display functions in `cli/loop/layout.py` and `cli/loop/info.py` have no handling for the `parallel` state type. Additionally, the `loop:` state type is also unhandled in `info.py`'s overview table type column and verbose output (same gap, same fix site — both can be addressed together). Documentation (`ARCHITECTURE.md`, `API.md`, `LOOPS_GUIDE.md`, create-loop skill docs) does not mention the `parallel:` state type.

## Expected Behavior

- `from little_loops.fsm import ParallelStateConfig, ParallelResult` imports without error
- `ll-loop info <loop-with-parallel>` displays parallel states with a badge and `"parallel"` type column entry
- `ll-loop info --verbose <loop-with-parallel>` shows parallel state details (items source, loop name, max_workers, isolation, fail_mode)
- All documentation touchpoints (`ARCHITECTURE.md`, `API.md`, `LOOPS_GUIDE.md`, `loops/README.md`, `CONTRIBUTING.md`, create-loop skill docs) describe the `parallel:` state type and `ParallelStateConfig` / `ParallelResult`

## Use Case

**Who**: Developer building or inspecting a loop that uses the `parallel:` state type for concurrent sub-loop fan-out

**Context**: After FEAT-1074/1076 implement the parallel runner, developers need to reference `ParallelStateConfig` in their loop definitions and use `ll-loop info` to inspect parallel state execution details

**Goal**: Import parallel FSM types from the public `little_loops.fsm` API and inspect parallel state configuration via CLI

**Outcome**: `ParallelStateConfig` and `ParallelResult` are importable; `ll-loop info` displays parallel states with appropriate badge and verbose details; documentation allows discovery of the feature

## Motivation

This wiring and documentation pass completes the public surface of the `parallel:` state type added in FEAT-1074–1076. Without these changes:
- `ParallelStateConfig` and `ParallelResult` cannot be imported from the public `little_loops.fsm` API, breaking any code that references these types
- `ll-loop info` silently mishandles parallel states (no badge, wrong type display), degrading operator visibility
- Documentation gaps leave users unable to discover or understand the `parallel:` state type

## Proposed Solution

### __init__.py exports

`scripts/little_loops/fsm/__init__.py` — add `ParallelStateConfig` and `ParallelResult` to:
- `from little_loops.fsm.schema import (...)` block at lines 113–120 (extend the existing grouped schema import)
- `__all__` list at lines 136–184 (alphabetically sorted; `ParallelResult` between `"P..."` entries, `ParallelStateConfig` immediately after)
- Module docstring at lines 1–68 (add brief description of parallel state type)

### CLI display

**`scripts/little_loops/cli/loop/layout.py`** — `_get_state_badge()` at line 118 has no branch for `state.parallel is not None`:
- Add `_PARALLEL_BADGE = "\u2225"  # ∥ PARALLEL TO` constant after `_ROUTE_BADGE` at line 109 (follows same single-line constant pattern as `_SUB_LOOP_BADGE = "\u21b3\u27f3"` and `_ROUTE_BADGE = "\u2443"`)
- Add `if state.parallel is not None: return parallel_badge` branch before action_type checks; use `(badges or {}).get("parallel", _PARALLEL_BADGE)` for override-key consistency with the `"sub_loop"` pattern at line 128

**`scripts/little_loops/cli/loop/info.py`**:
- `_print_state_overview_table` type column at lines 555–563 — add `elif state.loop is not None: type_col = "loop"` AND `elif state.parallel is not None: type_col = "parallel"` branches (both confirmed absent; add together)
- Verbose state output (lines 739–835) — the verbose block currently renders: action (763–777), evaluate (778–797), capture (798), timeout (800), transitions (802–834); both `state.loop` and `state.parallel` are entirely absent from this block. Add `state.parallel` branch to show items source, loop name, max_workers, isolation, fail_mode (follow same structure as action block at lines 763–777)
- Note: `state.loop` verbose display is also entirely absent — add `state.loop` display alongside `state.parallel` to avoid a second incomplete state

### Documentation

**`docs/ARCHITECTURE.md`** — Document the `parallel:` state type in the FSM section.

**`docs/reference/API.md`** — Add `ParallelStateConfig` and `ParallelResult` to schema reference.

**`docs/guides/LOOPS_GUIDE.md:1653`** — "Composable Sub-Loops" section and comparison table (lines 1695–1700) describe only `loop:` and inline states; add `parallel:` row and YAML example.

**`scripts/little_loops/loops/README.md:148`** — "Composing Loops" section references `loop:` field only; add `parallel:` fan-out pattern.

**`CONTRIBUTING.md:231`** — `fsm/` directory tree listing; add `parallel_runner.py` entry.

### Skill/create-loop docs

**`skills/create-loop/reference.md:686`** — `loop:` field section documents sub-loop invocation; add `parallel:` field documentation alongside it.

**`skills/create-loop/loop-types.md:978`** — Sub-loop composition section describes `loop:` as the primary child mechanism; add `parallel:` as peer concurrent fan-out mechanism.

## Implementation Steps

1. Export `ParallelStateConfig` and `ParallelResult` from `fsm/__init__.py` (import block + `__all__` + module docstring)
2. Add `_PARALLEL_BADGE` constant and dispatch branch in `cli/loop/layout.py:_get_state_badge()`
3. Add `state.parallel` branches in `cli/loop/info.py` (type column + verbose output)
4. Update documentation touchpoints (`ARCHITECTURE.md`, `API.md`, `LOOPS_GUIDE.md`, `loops/README.md`, `CONTRIBUTING.md`)
5. Update create-loop skill docs (`reference.md`, `loop-types.md`)
6. Verify acceptance criteria: import, `ll-loop info`, and `ll-loop info --verbose` all work correctly

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/config/features.py:190` — add `parallel: str = _PARALLEL_BADGE` field to `LoopsGlyphsConfig` dataclass (dataclass is at lines 190–221, not 189); add `"parallel": self.parallel` entry to `to_dict()` at line 212; update `from_dict()` to read `"parallel"` key (follow same pattern as `sub_loop` and `route` fields)
8. Update `config-schema.json:658` — add `"parallel"` property to `loops.glyphs` object schema (block is at lines 658–670, not 661); mirrors `"sub_loop"` and `"route"` entries: `{"type": "string", "default": "\u2225", "description": "Badge for parallel states (default: \u2225)"}`; required before any `ll-config.json` glyph override can be validated
9. Update `scripts/tests/test_config.py:1448` — extend `test_to_dict_returns_all_keys` set assertion to include `"parallel"`; must be done in the same step as step 7 to avoid a failing test
10. Update `scripts/tests/test_ll_loop_display.py:15` — add `_PARALLEL_BADGE` to the import block; update `test_badge_constants_match_spec` at line 2225 (class `TestStateBadges`) to assert `_PARALLEL_BADGE == "\u2225"` alongside the existing `_SUB_LOOP_BADGE` assertion
11. Write `TestCmdShow` tests in `scripts/tests/test_ll_loop_commands.py` — parallel state type column (`"parallel"` in overview table) and verbose parallel details (items source, loop name, max_workers); follow `test_show_verbose_shows_full_action` at line 1370 as structural template

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/__init__.py` — Add `ParallelStateConfig`, `ParallelResult` exports
- `scripts/little_loops/cli/loop/layout.py` — Add `_PARALLEL_BADGE` and dispatch branch
- `scripts/little_loops/cli/loop/info.py` — Add `state.parallel` display branches
- `docs/ARCHITECTURE.md` — Document `parallel:` state type
- `docs/reference/API.md` — Add `ParallelStateConfig`, `ParallelResult` reference
- `docs/guides/LOOPS_GUIDE.md` — Add `parallel:` to composable sub-loops section + table
- `scripts/little_loops/loops/README.md` — Add `parallel:` to Composing Loops section
- `CONTRIBUTING.md` — Add `parallel_runner.py` to fsm/ tree listing
- `skills/create-loop/reference.md` — Add `parallel:` field docs
- `skills/create-loop/loop-types.md` — Add `parallel:` mechanism docs
- `config-schema.json` — Add `"parallel"` key to `loops.glyphs` block (required for user glyph override; `additionalProperties: false` at line 669 rejects unknown keys)
- `scripts/little_loops/config/features.py` — Add `parallel` field to `LoopsGlyphsConfig` dataclass and include `"parallel": self.parallel` in `to_dict()` at line 212; without this, the `(badges or {}).get("parallel", _PARALLEL_BADGE)` override lookup in `_get_state_badge` always falls back to the default regardless of user config

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/schema.py` — source of `ParallelStateConfig` and `ParallelResult` (read-only dependency; FEAT-1074 must be complete)
- Any external code importing from `little_loops.fsm` — benefits from new exports

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/features.py:189` — `LoopsGlyphsConfig.to_dict()` at line 212 enumerates badge keys passed to `_get_state_badge`; must add `"parallel": self.parallel` entry and `parallel: str` field (with `_PARALLEL_BADGE` default) for config-driven glyph overrides to work
- `scripts/little_loops/cli/loop/_helpers.py:155` — `print_execution_plan()` iterates state fields with no branch for `state.parallel`; assess whether in scope for FEAT-1078 or deferred to a follow-up
- `scripts/tests/test_config.py:1448` — `test_to_dict_returns_all_keys` asserts `set(d.keys()) == {"prompt", "slash_command", "shell", "mcp_tool", "sub_loop", "route"}` and **will break** if `to_dict()` gains `"parallel"`; must be updated in the same step as `config/features.py`

### Similar Patterns
- `from little_loops.fsm.schema import (...)` grouped import block in `fsm/__init__.py:113-120` — exact pattern to extend
- `_SUB_LOOP_BADGE` at `layout.py:108` and `_ROUTE_BADGE` at `layout.py:109` — naming convention for `_PARALLEL_BADGE`
- `_get_state_badge()` at `layout.py:118-133` — `state.loop` branch at line 125 is the exact structural pattern to copy for `state.parallel`
- `(badges or {}).get("sub_loop", _SUB_LOOP_BADGE)` at `layout.py:128` — override-key pattern to replicate for `"parallel"` key

### Tests
- `scripts/tests/test_ll_loop_display.py:TestGetStateBadge` — add parallel badge test cases here (test file already imports `_get_state_badge` at line 20)
- `scripts/tests/test_fsm_schema.py` — add import round-trip test for `ParallelStateConfig`/`ParallelResult` from `little_loops.fsm`
- Smoke test: `python -c "from little_loops.fsm import ParallelStateConfig, ParallelResult"` passes
- `ll-loop info` integration test for parallel state badge and type column

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_display.py:15` — update import block to add `_PARALLEL_BADGE` alongside `_SUB_LOOP_BADGE` and `_ROUTE_BADGE`; current import at lines 15–21 does not include it
- `scripts/tests/test_ll_loop_display.py:2228` (`test_badge_constants_match_spec`) — add `assert _PARALLEL_BADGE == "<unicode>"` assertion; this test enumerates every badge constant by unicode codepoint and will miss the new constant without an explicit line
- `scripts/tests/test_config.py:1448` (`test_to_dict_returns_all_keys`) — update hard-coded set assertion `{"prompt", "slash_command", "shell", "mcp_tool", "sub_loop", "route"}` to include `"parallel"`; this test **will break** when `LoopsGlyphsConfig.to_dict()` gains the `"parallel"` key
- `scripts/tests/test_ll_loop_commands.py:TestCmdShow` — write new tests: (1) overview table shows `"parallel"` in Type column for a loop with a parallel state; (2) `--verbose` shows parallel state details (items source, loop name, max_workers); follow `test_show_verbose_shows_full_action` at line 1370 as the structural template

### Documentation
- `docs/ARCHITECTURE.md`, `docs/reference/API.md`, `docs/guides/LOOPS_GUIDE.md`, `scripts/little_loops/loops/README.md`, `CONTRIBUTING.md`, `skills/create-loop/reference.md`, `skills/create-loop/loop-types.md`

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:658` — `loops.glyphs` object schema (block spans 658–670, `additionalProperties: false` is at the closing brace of this block); add `"parallel"` property with `"type": "string"` and description (mirrors the `"sub_loop"` and `"route"` entries already present); `"additionalProperties": false` will reject any `.ll/ll-config.json` with `"loops.glyphs.parallel"` until this is added

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **FEAT-1074 fully unimplemented**: `ParallelStateConfig`, `ParallelResult`, and `StateConfig.parallel` field do not exist anywhere in `scripts/`. All FEAT-1078 steps that touch these types must wait for FEAT-1074 to merge.
- **`_PARALLEL_BADGE` unicode**: `"\u2225"` (∥ PARALLEL TO). Consistent with `_SUB_LOOP_BADGE = "\u21b3\u27f3"` (↳⟳) and `_ROUTE_BADGE = "\u2443"` (⑃) at `layout.py:108–109`.
- **`state.loop` verbose gap confirmed**: `info.py` verbose block (lines 739–835) has no `state.loop` rendering either — only action, evaluate, capture, timeout, and transitions are shown. Both `state.loop` and `state.parallel` must be added together per implementation step 3.
- **`_helpers.py` scope decision**: `print_execution_plan()` at `_helpers.py:155–205` also has no `state.loop` branch (parallel to the `info.py` gap). Defer both `state.loop` and `state.parallel` handling in `print_execution_plan()` to a follow-up — keeping this FEAT additive-only avoids expanding scope.
- **Line number corrections** (from current codebase): `LoopsGlyphsConfig` dataclass starts at line 190 (not 189); `config-schema.json` glyphs block at line 658 (not 661); `TestStateBadges.test_badge_constants_match_spec` at line 2225 (not 2228).
- **`test_to_dict_returns_all_keys` exact assertion** (`test_config.py:1448`): `assert set(d.keys()) == {"prompt", "slash_command", "shell", "mcp_tool", "sub_loop", "route"}` — add `"parallel"` to this set and `assert d["parallel"] == "\u2225"` below it.

## Dependencies

- FEAT-1074 must be complete (needs `ParallelStateConfig`, `ParallelResult` to export)
- FEAT-1075 and FEAT-1076 should be complete for accurate display and docs

## Acceptance Criteria

- `from little_loops.fsm import ParallelStateConfig, ParallelResult` works without error
- `ll-loop info <loop-with-parallel>` displays parallel states with badge and type column entry
- `ll-loop info --verbose <loop-with-parallel>` shows parallel state details (items, loop, workers, isolation)
- `docs/ARCHITECTURE.md` and `docs/reference/API.md` document `parallel:` state type
- `LOOPS_GUIDE.md` comparison table includes `parallel:` row
- `create-loop` skill docs describe `parallel:` alongside `loop:`

## Impact

- **Priority**: P2 — Completes the public API surface of a shipped feature; without this, `ParallelStateConfig`/`ParallelResult` are unusable from `little_loops.fsm` and CLI display silently mishandles parallel states
- **Effort**: Small — Additive-only changes: export additions, display branches, and documentation updates; no logic changes
- **Risk**: Low — Purely additive; new exports, new display branches, new doc sections; no existing behavior modified
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `wiring`, `docs`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-12
- **Reason**: Issue too large for single session (score: 11/11 — Very Large)

### Decomposed Into

- FEAT-1080: Parallel State FSM API Exports and Config Wiring
- FEAT-1081: Parallel State CLI Display
- FEAT-1082: Parallel State Documentation

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-12_

**Readiness Score**: 78/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- FEAT-1074 is a hard block: `ParallelStateConfig` and `ParallelResult` do not exist in `schema.py` yet, nor does a `parallel` field on `StateConfig`. Every implementation step depends on these types being added first.
- FEAT-1075 and FEAT-1076 are still Open ("should be complete" per issue) — display logic and docs will be incomplete/inaccurate without the runner semantics settled.
- Only docs-only edits (`ARCHITECTURE.md`, `API.md`, `LOOPS_GUIDE.md`, `CONTRIBUTING.md`, skill docs) and `config-schema.json` can proceed now, but are premature to merge before the types exist.

---

## Session Log
- `/ll:issue-size-review` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/77a4f6c6-909a-4d66-84d7-1e952b12aed8.jsonl`
- `/ll:refine-issue` - 2026-04-12T22:55:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba5b41d1-15ee-4195-a924-8fb7f7d2b5a1.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c56625be-57cb-4f45-9a17-f6b854f56f00.jsonl`
- `/ll:wire-issue` - 2026-04-12T22:49:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6244078e-7945-4bbe-9309-ccd49fd2a566.jsonl`
- `/ll:refine-issue` - 2026-04-12T22:41:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15442a49-fc61-484a-8711-a06e1a651542.jsonl`
- `/ll:format-issue` - 2026-04-12T22:37:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/616a27fb-4ed2-44ea-b65f-884deb859e2f.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
