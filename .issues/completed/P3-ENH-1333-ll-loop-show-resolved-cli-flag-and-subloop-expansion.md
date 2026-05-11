---
id: ENH-1333
type: ENH
priority: P3

confidence_score: 100
outcome_confidence: 85
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-02T21:48:36Z
parent: ENH-1326
---

# ENH-1333: `ll-loop show --resolved`: CLI Flag and Sub-loop Expansion with Tests

## Summary

Add a `--resolved` flag to `ll-loop show` that expands `loop:` sub-loop references inline under a `_subloop` key on the parent state dict. Includes full test coverage and documentation updates for the CLI flag.

## Parent Issue

Decomposed from ENH-1326: `/ll:analyze-loop` Should Resolve `from:`, Fragments, and Sub-loops Before Judging

## Background

`from:` inheritance and `fragment:` references are already fully resolved in `ll-loop show --json` output. The only remaining gap is `loop:` sub-loop resolution — `StateConfig.to_dict()` emits only the bare sub-loop name string; the child loop's state map is never expanded. This child issue adds the CLI flag that exposes sub-loop internals so downstream skills can classify them.

## Current Behavior

`ll-loop show <name> --json` resolves `from:` inheritance and `fragment:` references inline, but states with a `loop:` field emit only the bare sub-loop name string. Downstream consumers (e.g., `/ll:analyze-loop`, `/ll:assess-loop`) cannot inspect sub-loop states without a separate `ll-loop show` call on the child loop.

## Expected Behavior

`ll-loop show <name> --resolved --json` returns the FSM config with each state that has a `loop:` field augmented by a `_subloop` key containing the child loop's full state map (one level deep). Existing `ll-loop show <name> --json` output (without `--resolved`) is unchanged.

## Scope Boundaries

- Sub-loop expansion is **one level deep only** — recursive expansion of nested sub-loops is out of scope.
- `--resolved` does not alter `from:` or `fragment:` resolution behaviour (already handled without the flag).
- Human-readable output (without `--json`) is unaffected by `--resolved`.
- `skills/analyze-loop/SKILL.md` and `skills/assess-loop/SKILL.md` wiring is deferred to the parent ENH-1326 scope.

## Impact

- **Priority**: P3 — Quality-of-life improvement enabling downstream skill analysis of sub-loop states
- **Effort**: Small — Additive flag; 7 well-specified touchpoints across CLI, tests, and docs
- **Risk**: Low — Purely additive; no existing output modified
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `ll-loop`, `testing`

## Status

**Open** | Created: 2026-05-02 | Priority: P3

## Implementation Steps

1. **Add `--resolved` flag to `ll-loop show` subparser** — `scripts/little_loops/cli/loop/__init__.py:main_loop()` around line 357, after the existing `--json` arg:
   ```python
   show_parser.add_argument("--resolved", action="store_true",
       help="Expand sub-loop states inline under _subloop key")
   ```
   Follow the existing `store_true` + `getattr(args, "resolved", False)` convention used by `--verbose` and `--json`.

2. **Implement sub-loop expansion in `cmd_show()`** — `scripts/little_loops/cli/loop/info.py:cmd_show()`: when `--resolved` is set, iterate the `fsm.to_dict()["states"]` dict; for any state with a `"loop"` key, call `resolve_loop_path(state["loop"], loops_dir)` then `load_and_validate(child_path)` and attach `child_fsm.to_dict()["states"]` as `_subloop` on the parent state dict before printing. Mirror the runtime loading pattern in `scripts/little_loops/fsm/executor.py:_execute_sub_loop()`. **Important**: `load_and_validate` is NOT currently imported in `info.py` — add `from little_loops.fsm.validation import load_and_validate`.

3. **Update existing `Namespace` calls** — `scripts/tests/test_ll_loop_commands.py:TestCmdShowJson` (lines 2450, 2471, 2501): add `resolved=False` to all 3 `argparse.Namespace(json=True, verbose=False)` constructor calls to prevent `AttributeError` if `args.resolved` is accessed directly.

4. **Create fixture** — `scripts/tests/fixtures/fsm/inner-eval.yaml`: minimal terminal child loop as a companion to `assess-subloop-laundering.yaml`, so that fixture is fully exercisable in `TestCmdShowResolved`.

5. **Add `TestCmdShowResolved` test class** — `scripts/tests/test_ll_loop_commands.py`: follow the `TestCmdShowJson` pattern using direct-import + `argparse.Namespace(json=True, verbose=False, resolved=True)`. Write a parent loop YAML with `loop: inner-eval` state and a `inner-eval.yaml` in `tmp_path/.loops/`; assert the JSON output has `_subloop` on the parent state dict.

6. **Update `docs/guides/LOOPS_GUIDE.md`** — subcommands table (around line 1917): add `--resolved` to the `(--json for raw FSM config)` parenthetical.

7. **Update `docs/reference/CLI.md`** — document `--resolved` flag for `ll-loop show`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `README.md` — add `--resolved` to the `ll-loop show` examples block (lines 325–326) alongside the existing `--json` example, parallel to the CLI.md update in step 7.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `--resolved` flag to `show_parser`
- `scripts/little_loops/cli/loop/info.py` — add `load_and_validate` import; handle `--resolved` in `cmd_show()`
- `scripts/tests/test_ll_loop_commands.py` — update 3 existing `Namespace` calls; add `TestCmdShowResolved`

### Files to Create
- `scripts/tests/fixtures/fsm/inner-eval.yaml` — minimal terminal child loop fixture (use `assess-subloop-laundering.yaml` as the parent fixture; `inner-eval.yaml` should be a 3-state terminal loop):
  ```yaml
  name: inner-eval
  description: "Minimal evaluation child loop for testing"
  initial: evaluate
  states:
    evaluate:
      action_type: prompt
      action: "Evaluate the current state."
      on_yes: done
      on_no: done
    done:
      terminal: true
  ```

### Similar Patterns
- `scripts/little_loops/fsm/executor.py:_execute_sub_loop()` — exact loading pattern to mirror
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — existing parent fixture for the laundering scenario

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add `--resolved` to subcommands table
- `docs/reference/CLI.md` — document the new flag

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — lines 325–326 document `ll-loop show <loop-name> --json`; add `--resolved` entry as parallel flag (same pattern as CLI.md update) [Agent 2 finding]

### Downstream Consumers (informational — parent ENH-1326 scope)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/analyze-loop/SKILL.md` — Step 2 uses `ll-loop show <loop_name> --json`; after this issue lands, the skill can optionally pass `--resolved` to get `_subloop` expansion. No change required here; this is the follow-on wiring in ENH-1326. [Agent 2 finding]
- `skills/assess-loop/SKILL.md` — Step 2 uses `ll-loop show <loop_name> --json`; same downstream consumer pattern as `analyze-loop`. No change required in this issue. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `resolve_loop_path` is **already imported** at `info.py:14` (`from little_loops.cli.loop._helpers import ..., resolve_loop_path`) — do NOT add a second import; only add `load_and_validate`
- `load_and_validate` returns `(FSMLoop, list[ValidationError])` — unpack as `child_fsm, _ = load_and_validate(child_path)` then call `child_fsm.to_dict()["states"]`
- `cmd_show()` is at `info.py:626`; use `getattr(args, "resolved", False)` consistent with `getattr(args, "json", False)` at line 643 and `getattr(args, "verbose", False)` at line 723
- `StateConfig.to_dict()` emits `"loop": str` when the field is set (`schema.py:358-359`) — iterate `fsm.to_dict()["states"].values()` and check for `"loop"` key presence
- `TestCmdShowJson` class starts at `test_ll_loop_commands.py:2421`; `TestCmdShowResolved` should use the same "Style B" fully-inline pattern (no monkeypatch, no sys.argv patching)

## Acceptance Criteria

- [x] `ll-loop show <name> --resolved --json` returns states with `_subloop` key for any state with `loop:`.
- [x] `_subloop` contains the resolved state map of the child loop (one level deep).
- [x] `ll-loop show <name> --json` (without `--resolved`) is unchanged.
- [x] `TestCmdShowResolved` tests pass covering the `_subloop` expansion.
- [x] All 3 existing `TestCmdShowJson` tests still pass (no `AttributeError` from missing `resolved` attribute).
- [x] `apo-textgrad` loop (uses `from:` and `fragment:`) returns unchanged output with `--resolved` (inheritance already resolved).

## Resolution

Implemented all 7 touchpoints as specified:

1. Added `--resolved` flag to `show_parser` in `scripts/little_loops/cli/loop/__init__.py`
2. Added `load_and_validate` import and sub-loop expansion logic in `scripts/little_loops/cli/loop/info.py:cmd_show()` — when `--resolved` is set, iterates `fsm.to_dict()["states"]` and injects `_subloop` for any state with a `"loop"` key
3. Updated 3 existing `argparse.Namespace` calls in `TestCmdShowJson` to include `resolved=False`; added `TestCmdShowResolved` with 2 tests (expansion present with `--resolved`, absent without)
4. Created `scripts/tests/fixtures/fsm/inner-eval.yaml` — minimal 2-state terminal child loop
5. Updated `docs/guides/LOOPS_GUIDE.md` subcommands table (line 1917) to mention `--resolved`
6. Updated `docs/reference/CLI.md` flag table and examples block for `ll-loop show`
7. Updated `README.md` lines 325-326 with `--json --resolved` example

All 5 new/updated tests pass; full suite passes (pre-existing marketplace version mismatch unrelated).

## Session Log
- `/ll:ready-issue` - 2026-05-02T21:42:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4022dd56-dbec-4f0e-9f39-bc62efc12c5b.jsonl`
- `/ll:confidence-check` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d0f0a1e-fe3f-4de8-8df5-7352ca00ba12.jsonl`
- `/ll:wire-issue` - 2026-05-02T21:37:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/618354dc-0253-4ebe-894a-92b0731f4a6f.jsonl`
- `/ll:refine-issue` - 2026-05-02T21:32:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0bf8418-8c88-439e-a4be-eb189fcfd156.jsonl`
- `/ll:issue-size-review` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3504f81c-8403-4c3e-84f2-f27905b579d2.jsonl`
- `/ll:manage-issue` - 2026-05-02T21:48:36Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4022dd56-dbec-4f0e-9f39-bc62efc12c5b.jsonl`
