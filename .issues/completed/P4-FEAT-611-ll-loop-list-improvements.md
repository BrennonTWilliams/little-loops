---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 96
outcome_confidence: 88
---

# FEAT-611: `ll-loop list` improvements: status filter, paradigm type, description

## Summary

`ll-loop list` currently shows only loop file stems (names) with no metadata. The `--running` flag calls `list_running_loops()` but shows only `loop_name`, `current_state`, and `iteration` — omitting `status`, elapsed time, and `updated_at` which are available on `LoopState`. There is also no way to filter by status (e.g., show only `interrupted` or `awaiting_continuation` loops).

## Current Behavior

Available loops display:
```
Available loops:
  my-loop
  quality-gate
  invariants  [built-in]
```

Running loops display:
```
Running loops:
  my-loop: check_types (iteration 3)
```

No paradigm type, description, status, or elapsed time shown. No `--status` filter exists in `list_parser`.

## Expected Behavior

Available loops show paradigm and optional description:
```
Available loops:
  my-loop         [goal]     Ensure tests pass
  quality-gate    [invariants]
  invariants      [invariants]  [built-in]
```

Running loops show status and elapsed time:
```
Running loops:
  my-loop: check_types (iteration 3) [running] 2m 15s
```

A `--status <value>` flag filters running loops by `LoopState.status`.

## Motivation

`cmd_list` at `info.py:22` omits fields that are already loaded for free: `LoopState.status` and `LoopState.accumulated_ms` are persisted and returned by `list_running_loops()`. For available loops, `FSMLoop.paradigm` is set during compilation and the raw YAML `description` field is present in built-in loops (e.g., `loops/issue-refinement.yaml`). The display gap means users have no way to triage a list of loops without running `ll-loop status <name>` individually for each one.

## Use Case

A developer managing multiple loops wants to quickly see which are `interrupted` (needing manual resume) vs `awaiting_continuation` (paused handoff). They run `ll-loop list --status interrupted` to find loops that need attention without inspecting each loop individually.

## Scope Boundaries

**In Scope**:
- Add paradigm type and description to `cmd_list` available-loops output (loaded from raw YAML spec)
- Add `status` and elapsed time fields to `--running` output (from `LoopState.status` and `LoopState.accumulated_ms`)
- Add `--status <value>` argument to `list_parser` for filtering `list_running_loops()` results

**Out of Scope**:
- Changing `list_running_loops()` in `persistence.py`
- Adding color/formatting beyond what `colorize()` already provides
- New subcommands or changes to `status`, `show`, or `history`

## Acceptance Criteria

- [x] `ll-loop list` shows paradigm type for each available loop (loaded from raw YAML spec)
- [x] `ll-loop list` shows description when present in the loop spec
- [x] `ll-loop list --running` shows `LoopState.status` and elapsed time derived from `accumulated_ms`
- [x] `ll-loop list --status <value>` filters running loops by `LoopState.status`
- [x] `ll-loop list --status interrupted` returns exit code 1 if no loops match

## Proposed Solution

In `cmd_list` (`info.py:22`): for available loops, use `yaml.safe_load` to read each YAML file and extract `paradigm` and `description` for display. For `--running`, extend the loop body to format `state.status` and compute elapsed from `state.accumulated_ms`. Add `--status` argument to `list_parser` in `__init__.py` and filter the `states` list before printing.

Elapsed time should be computed from `state.accumulated_ms` (in milliseconds) using the same minutes/seconds formatting already used in `_helpers.py:run_foreground`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py:22-63` — update `cmd_list` to load YAML spec for paradigm/description in available-loops block; add status/elapsed display and `--status` filter in `--running` block
- `scripts/little_loops/cli/loop/__init__.py:133-135` — add `--status` argument to `list_parser` (e.g., `list_parser.add_argument("--status", help="Filter by status")`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:231` — sole caller of `cmd_list`
- `scripts/little_loops/fsm/persistence.py:424` — `list_running_loops()` returns `list[LoopState]`; `LoopState.status` and `LoopState.accumulated_ms` are the fields consumed by the new display

### Similar Patterns
- `scripts/little_loops/cli/loop/_helpers.py:135-162` — `load_loop_with_spec` shows how to get both `FSMLoop` and raw spec dict from a YAML file
- `scripts/little_loops/cli/loop/_helpers.py:301-307` — elapsed seconds/minutes formatting pattern to reuse
- `scripts/little_loops/cli/loop/info.py:59-62` — existing `[built-in]` label shows the column alignment approach to extend

### Tests
- `scripts/tests/test_ll_loop_commands.py` — add tests for paradigm/description display, `--running` status/elapsed, and `--status` filtering

### Documentation
- N/A — CLI `--help` output is auto-generated from argparse

## Implementation Steps

1. In `__init__.py` (`list_parser` block at line 133), add:
   ```python
   list_parser.add_argument("--status", help="Filter running loops by status (e.g., interrupted, awaiting_continuation)")
   ```

2. In `info.py`, change the branch condition at line 27 from:
   ```python
   if getattr(args, "running", False):
   ```
   to:
   ```python
   if getattr(args, "running", False) or getattr(args, "status", None):
   ```
   This ensures `ll-loop list --status interrupted` works without requiring `--running`.

3. In `info.py`, after `states = list_running_loops(loops_dir)` (line 30), apply status filter and update exit code:
   ```python
   if getattr(args, "status", None):
       states = [s for s in states if s.status == args.status]
   if not states:
       if getattr(args, "status", None):
           print(f"No loops with status: {args.status}")
           return 1
       print("No running loops")
       return 0
   ```
   Then update the print line (line 36) to include `state.status` and elapsed derived from `accumulated_ms`:
   ```python
   elapsed_s = state.accumulated_ms // 1000
   elapsed_str = f"{elapsed_s}s" if elapsed_s < 60 else f"{elapsed_s // 60}m {elapsed_s % 60}s"
   print(f"  {state.loop_name}: {state.current_state} (iteration {state.iteration}) [{state.status}] {elapsed_str}")
   ```

4. In `info.py`, in the available-loops display loop (lines 59-62), open each YAML file with `yaml.safe_load` to read `paradigm` and `description`. Add `import yaml` at the top of the branch (inside the function is fine — `yaml` is not currently in `info.py`'s file-level imports). Note: all current built-in loops have `paradigm: fsm`; user-created loops compiled from a paradigm will show the paradigm name (e.g., `goal`):
   ```python
   for path in sorted(yaml_files):
       import yaml
       with open(path) as f:
           spec = yaml.safe_load(f)
       paradigm = spec.get("paradigm", "")
       desc = (spec.get("description", "") or "").splitlines()
       desc_str = f"  {desc[0]}" if desc else ""
       tag = f"  [{paradigm}]" if paradigm else ""
       print(f"  {path.stem}{tag}{desc_str}")
   for path in builtin_files:
       import yaml
       with open(path) as f:
           spec = yaml.safe_load(f)
       paradigm = spec.get("paradigm", "")
       desc = (spec.get("description", "") or "").splitlines()
       desc_str = f"  {desc[0]}" if desc else ""
       tag = f"  [{paradigm}]" if paradigm else ""
       print(f"  {path.stem}{tag}{desc_str}  [built-in]")
   ```

5. Add tests in `TestCmdList` in `test_ll_loop_commands.py` for:
   - Paradigm and description shown for available loops (use a fixture YAML with `paradigm: goal` and `description: "My description"`)
   - `--running` output includes `state.status` and elapsed string
   - `--status interrupted` filters correctly; exit code 1 when no loops match

## Impact

- **Priority**: P4 - Nice-to-have UX improvement for loop management
- **Effort**: Small-Medium - Needs to load loop specs for paradigm/description
- **Risk**: Low - Display-only changes, additive CLI flags
- **Breaking Change**: No

## Labels

`feature`, `ll-loop`, `cli`, `ux`

## Session Log
- `/ll:refine-issue` - 2026-03-06T16:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ede83e8-b180-4a37-9f33-509b62da4be9.jsonl` — verified all line refs accurate; identified `--status` without `--running` gap in Implementation Steps (condition must be `args.running OR args.status`); noted `yaml` not in `info.py` imports; noted built-in loops use `paradigm: fsm`; expanded steps with concrete code
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: `ll-loop list` displays only loop names; no paradigm/description/status shown; no `--status` filter
- `/ll:format-issue` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe94482e-9372-4143-bed0-d453aad43004.jsonl` — reformatted to v2.0 FEAT template; added Motivation, Scope Boundaries, Proposed Solution, Integration Map, Implementation Steps; confirmed `LoopState.status`, `accumulated_ms` available in `persistence.py`; confirmed `FSMLoop.paradigm` in `schema.py`; confirmed description field in `loops/*.yaml`
- `/ll:confidence-check` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe94482e-9372-4143-bed0-d453aad43004.jsonl` — readiness: 96/100 PROCEED, outcome: 88/100 HIGH CONFIDENCE
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: minimal display, no status filter
- `/ll:ready-issue` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2089b015-11be-4a21-8755-bb4e28055f84.jsonl` — CORRECTED: fixed 5 drifted line references in Integration Map
- `/ll:ready-issue` - 2026-03-06T15:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a1160365-3807-494c-a819-6ebdac72cd6f.jsonl` — READY: all line references verified accurate; no corrections needed

---

## Resolution

Implemented in `info.py` and `__init__.py`:
- Added `_load_loop_meta()` helper to extract paradigm and description from loop YAML specs
- Updated `cmd_list` available-loops block to show `[paradigm]` tag and description for each loop
- Extended `--running` output to include `[status]` and elapsed time (derived from `accumulated_ms`)
- Added `--status` argument to `list_parser`; filter applied before display with exit code 1 on no match
- `--status` alone (without `--running`) triggers the running-loops branch
- Added 4 new tests covering all acceptance criteria

## Status

**Completed** | Created: 2026-03-06 | Priority: P4
