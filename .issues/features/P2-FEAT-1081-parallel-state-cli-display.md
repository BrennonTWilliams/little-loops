> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1078
testable: false
confidence_score: 80
outcome_confidence: 93
---

# FEAT-1081: Parallel State CLI Display

## Summary

Add `_PARALLEL_BADGE` constant and dispatch branch in `cli/loop/layout.py`, and add `state.parallel` (and the missing `state.loop`) display branches to `cli/loop/info.py`'s type column and verbose output block.

## Parent Issue

Decomposed from FEAT-1078: Parallel State Wiring, Display, and Docs

## Current Behavior

- `_get_state_badge()` in `layout.py:118` has no branch for `state.parallel is not None` — parallel states get no badge
- `_print_state_overview_table` type column in `info.py:555–563` has no `elif state.parallel is not None` branch — parallel states show the wrong type string
- The verbose output block in `info.py:739–835` has no `state.loop` or `state.parallel` rendering — both state types are entirely invisible in `ll-loop info --verbose`
- `test_ll_loop_display.py:15` import block does not include `_PARALLEL_BADGE`
- `TestStateBadges.test_badge_constants_match_spec` at line 2225 does not assert the `_PARALLEL_BADGE` unicode value

## Expected Behavior

- `ll-loop info <loop-with-parallel>` shows a `∥` badge and `"parallel"` in the Type column for parallel states
- `ll-loop info --verbose <loop-with-parallel>` shows parallel state details: items source, loop name, max_workers, isolation, fail_mode
- `state.loop` verbose display is also added (currently absent) alongside `state.parallel`
- Test assertions for the new badge constant and display branches pass

## Use Case

**Who**: Developer managing FSM loops with parallel state configurations

**Context**: When running `ll-loop info <loop-name>` or `ll-loop info --verbose <loop-name>` on a loop that contains one or more `state.parallel` entries

**Goal**: See parallel states clearly identified with a `∥` badge and `"parallel"` type column in the overview table; inspect full parallel state details (items source, loop name, max_workers, isolation, fail_mode) in verbose output

**Outcome**: Parallel states are visually distinguishable from other state types and fully inspectable from the CLI, enabling effective debugging and monitoring of parallel FSM loops

## Motivation

Without parallel state display support:
- `ll-loop info` shows no badge and incorrect type for parallel states — visually indistinguishable from standard states
- `ll-loop info --verbose` omits parallel state details entirely — users cannot inspect `items`, `loop`, `max_workers`, `isolation`, or `fail_mode` from the CLI
- Blocks effective debugging and monitoring of parallel FSM loops introduced in FEAT-1074

## Proposed Solution

### `cli/loop/layout.py`

- Add `_PARALLEL_BADGE = "\u2225"  # ∥ PARALLEL TO` constant after `_ROUTE_BADGE` at line 109 (follows single-line constant pattern of `_SUB_LOOP_BADGE` and `_ROUTE_BADGE`)
- Add `if state.parallel is not None: return (badges or {}).get("parallel", _PARALLEL_BADGE)` branch in `_get_state_badge()` before action_type checks; use override-key pattern consistent with `(badges or {}).get("sub_loop", _SUB_LOOP_BADGE)` at line 128

### `cli/loop/info.py`

**Type column** (`_print_state_overview_table`, lines 555–563):
- Add `elif state.loop is not None: type_col = "loop"` branch (currently absent)
- Add `elif state.parallel is not None: type_col = "parallel"` branch (currently absent)

**Verbose output block** (lines 739–835):
- Add `state.loop` verbose display (currently absent from block that renders action, evaluate, capture, timeout, transitions)
  - Display `loop: <loop_name>` (from `state.loop: str`)
  - Display `context_passthrough: true` only when `state.context_passthrough is True` (omit when False — follows omit-if-default convention used by `evaluate`, `timeout` blocks)
  - Example output:
    ```
    loop: child-loop.yaml
    context_passthrough: true
    ```
- Add `state.parallel` branch showing fields from `ParallelStateConfig` (field names confirmed from FEAT-1074 spec):
  - **Always display**: `items: <state.parallel.items>`, `loop: <state.parallel.loop>`
  - **Omit if default** (matches `ParallelStateConfig.to_dict()` omit-if-default convention): `max_workers` (default `4`), `isolation` (default `"thread"`), `fail_mode` (default `"collect"`), `context_passthrough` (default `False`)
  - Confirmed field types: `items: str`, `loop: str`, `max_workers: int = 4`, `isolation: str = "thread"`, `fail_mode: str = "collect"`, `context_passthrough: bool = False`
  - Rationale: omitting `"thread"` (the fast default) means the verbose display always surfaces the *explicit opt-in* value `"worktree"`. Omitting `"worktree"` would hide the safer-but-slower choice from authors, which is backwards — `"thread"` is what a casual reader already assumes.
- Insert `state.loop` and `state.parallel` blocks immediately after `if state.timeout:` (line 801), before the transition collection block (line 803)
- Follow structure of action block at lines 763–777 as template

### Tests

**`scripts/tests/test_ll_loop_display.py`**:
- Update import block at line 15 to include `_PARALLEL_BADGE` alongside `_SUB_LOOP_BADGE` and `_ROUTE_BADGE`
- Update `test_badge_constants_match_spec` at line 2225 to assert `_PARALLEL_BADGE == "\u2225"`
- Add `TestGetStateBadge` test cases for parallel state badge dispatch

**`scripts/tests/test_ll_loop_commands.py` (`TestCmdShow`)**:
- Test 1: overview table shows `"parallel"` in Type column for a loop with a parallel state
- Test 2: `--verbose` shows parallel state details (items source, loop name, max_workers)
- Follow `test_show_verbose_shows_full_action` at line 1370 as structural template

## Implementation Steps

1. Add `_PARALLEL_BADGE` constant to `layout.py` after `_ROUTE_BADGE`
2. Add `state.parallel` dispatch branch in `_get_state_badge()` in `layout.py`
3. Add `state.loop` and `state.parallel` branches to type column in `info.py`
4. Add `state.loop` and `state.parallel` verbose output blocks in `info.py`
5. Update `test_ll_loop_display.py` import and `test_badge_constants_match_spec` assertion
6. Add `TestGetStateBadge` parallel test cases in `test_ll_loop_display.py`
7. Add `TestCmdShow` parallel type column and verbose tests in `test_ll_loop_commands.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/reference/OUTPUT_STYLING.md:213-224` — add `"loop"` and `"parallel"` rows to the Type column example table for `_print_state_overview_table`

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/layout.py` — `_PARALLEL_BADGE` constant + `_get_state_badge()` branch
- `scripts/little_loops/cli/loop/info.py` — type column + verbose block for `state.parallel` (and `state.loop`)
- `scripts/tests/test_ll_loop_display.py` — import update, badge constant assertion, parallel badge tests
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdShow` parallel type column and verbose tests

### Read-only Dependencies

- `scripts/little_loops/fsm/schema.py` — `StateConfig.parallel` field (FEAT-1074 must be complete)
- `scripts/little_loops/config/features.py` — `LoopsGlyphsConfig.parallel` for glyph override (FEAT-1080 must be complete for config-driven overrides, but `_PARALLEL_BADGE` default works without it)
- `scripts/little_loops/cli/loop/_helpers.py` — already references `state.parallel` and `state.loop`; imports from `layout.py`. Verify no conflicting parallel display logic before adding branches in `info.py`
- `scripts/little_loops/cli/loop/__init__.py:388` — dispatches `cmd_show` (which calls `_print_state_overview_table`); read-only, no changes needed here [wiring pass]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Confirmed current state of target files:**
- `layout.py:108-109` — `_SUB_LOOP_BADGE = "\u21b3\u27f3"` and `_ROUTE_BADGE = "\u2443"` exist; no `_PARALLEL_BADGE`
- `layout.py:125-126` — `_get_state_badge()` already has `state.loop` branch; missing `state.parallel` branch
- `info.py:555-563` — type column has no `state.loop` or `state.parallel` branches; both fall through to `"—"` else clause
- `info.py:763-834` — verbose block renders: `action`, `evaluate`, `capture`, `timeout`, transitions, `route`; no `state.loop` or `state.parallel` blocks
- `schema.py:230` — `StateConfig.loop: str | None = None` exists; `StateConfig.parallel` does NOT exist (FEAT-1074 blocker)
- `config/features.py:193-198` — `LoopsGlyphsConfig` has `prompt`, `slash_command`, `shell`, `mcp_tool`, `sub_loop`, `route` fields; no `parallel` field (FEAT-1080 blocker)

**`state.loop` fields available for verbose display** (`schema.py:230-231`):
- `state.loop: str` — the sub-loop name/path
- `state.context_passthrough: bool` — whether context is passed to the sub-loop

**Test import block** (`test_ll_loop_display.py:14-21`) currently imports `_ROUTE_BADGE` and `_SUB_LOOP_BADGE` but not `_PARALLEL_BADGE`.

**Badge test placement pattern:**
- `_SUB_LOOP_BADGE` assertion is in `test_badge_constants_match_spec` (line 2234) — add `_PARALLEL_BADGE` assertion here (not as a standalone test)
- `_ROUTE_BADGE` has a separate standalone test `test_route_badge_constant` (line 2319) — either pattern is valid, but `_SUB_LOOP_BADGE` pattern is preferred for consistency
- Import block at `test_ll_loop_display.py:15-19` imports `_ROUTE_BADGE` and `_SUB_LOOP_BADGE` from `layout.py` — add `_PARALLEL_BADGE` to the same block

**`_get_state_badge()` exact insertion point** (`layout.py:118-133`):
- Add `parallel_badge = (badges or {}).get("parallel", _PARALLEL_BADGE)` after the existing `route_badge = ...` line (line 124)
- Add `if state.parallel is not None: return parallel_badge` branch immediately after `if state.loop is not None: return sub_loop_badge` (line 125), before `if state.action_type:` (line 127)

**`ParallelStateConfig` field spec confirmed** (from FEAT-1074 issue `P2-FEAT-1074-parallel-state-schema-and-validation.md:54-70`):
- `items: str` — interpolated expression resolving to newline-delimited list (always display)
- `loop: str` — sub-loop name to run per item (always display)
- `max_workers: int = 4` — omit if 4
- `isolation: str = "thread"` — values: `"worktree"` | `"thread"`; omit if `"thread"`
- `fail_mode: str = "collect"` — values: `"collect"` | `"fail_fast"`; omit if `"collect"`
- `context_passthrough: bool = False` — omit if `False`

**`test_show_verbose_shows_full_action` test structure** (`test_ll_loop_commands.py:1370-1402`):
- Fixtures: `tmp_path`, `monkeypatch`, `capsys`
- YAML written as string literal to `(loops_dir / "my-loop.yaml").write_text(...)`
- CLI invoked via `patch.object(sys, "argv", [...])` + `main_loop()` inside same `with` block
- Assert order: `result == 0` → `capsys.readouterr().out` → content assertions

### Similar Patterns

- `_SUB_LOOP_BADGE` at `layout.py:108`, `_ROUTE_BADGE` at `layout.py:109` — constant naming
- `_get_state_badge()` `state.loop` branch at line 125 — exact structural pattern for `state.parallel`
- `(badges or {}).get("sub_loop", _SUB_LOOP_BADGE)` at `layout.py:128` — override-key pattern
- Action block at `info.py:763–777` — verbose display template

### Tests

- `scripts/tests/test_ll_loop_display.py` — update import, badge constant assertion, add parallel badge tests
- `scripts/tests/test_ll_loop_commands.py` — add `TestCmdShow` parallel type column and verbose tests

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/OUTPUT_STYLING.md:213-224` — documents `_print_state_overview_table` by name and shows a Type column example with only `prompt`/`shell` values; `"loop"` and `"parallel"` are absent — update the example table to include both new type strings [Agent 2 finding]

### Configuration

- N/A — no config files affected; `LoopsGlyphsConfig.parallel` (from FEAT-1080) is a read-only dependency for override support, not modified here

## Dependencies

- FEAT-1074 must be complete (`StateConfig.parallel` field must exist)
- FEAT-1080 recommended (provides `LoopsGlyphsConfig.parallel` for config-driven badge overrides)

## Acceptance Criteria

- `ll-loop info <loop-with-parallel>` displays parallel states with `∥` badge and `"parallel"` type column entry
- `ll-loop info --verbose <loop-with-parallel>` shows parallel state details (items, loop, workers, isolation, fail_mode)
- `_PARALLEL_BADGE == "\u2225"` test assertion passes
- All existing and new `TestGetStateBadge` and `TestCmdShow` tests pass
- **Per-worker label in live run display (v1 observability minimum)**: during a parallel state's execution, each worker's state transitions include an item-identifying label — format `[<state_name>#<item_index>:<item_truncated_to_24_chars>]` prepended to the worker's state log lines. Example: `[fan_out#2:issue-42-refine...] entering state resolve`. This is the v1 floor for making a log tail of a parallel run debuggable; full per-worker event-tagging is tracked in **P2-ENH-1177** (worker-tagged observability)
- A test in `test_ll_loop_display.py` (`test_parallel_worker_label_in_live_display`) asserts the label format is present on each worker's emitted state-enter line when a parallel state runs

## Impact

- **Priority**: P2
- **Effort**: Small — Additive display branches and test cases; no logic changes
- **Risk**: Low — Additive-only; no existing display branches modified
- **Breaking Change**: No

## API/Interface

N/A — No public API changes. Additive display-only changes to `ll-loop info` CLI output format (`_PARALLEL_BADGE` constant is internal to `cli/loop/layout.py`).

## Labels

`fsm`, `parallel`, `cli`, `display`

---

## Session Log
- `/ll:refine-issue` - 2026-04-12T23:38:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf2f981e-ade4-4780-ad4a-df80e6d7758b.jsonl`
- `/ll:wire-issue` - 2026-04-12T23:32:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/95d1ff17-2cf5-44eb-9ddf-ca62cea8eb23.jsonl`
- `/ll:refine-issue` - 2026-04-12T23:26:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cc9f3810-fa02-48ac-953a-596f1e67f193.jsonl`
- `/ll:format-issue` - 2026-04-12T23:21:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/817edd26-3090-46ed-b2e9-d8d618d579d7.jsonl`
- `/ll:issue-size-review` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/77a4f6c6-909a-4d66-84d7-1e952b12aed8.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
