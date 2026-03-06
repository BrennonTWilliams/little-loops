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

- [ ] `ll-loop list` shows paradigm type for each available loop (loaded from raw YAML spec)
- [ ] `ll-loop list` shows description when present in the loop spec
- [ ] `ll-loop list --running` shows `LoopState.status` and elapsed time derived from `accumulated_ms`
- [ ] `ll-loop list --status <value>` filters running loops by `LoopState.status`
- [ ] `ll-loop list --status interrupted` returns exit code 1 if no loops match

## Proposed Solution

In `cmd_list` (`info.py:22`): for available loops, use `yaml.safe_load` to read each YAML file and extract `paradigm` and `description` for display. For `--running`, extend the loop body to format `state.status` and compute elapsed from `state.accumulated_ms`. Add `--status` argument to `list_parser` in `__init__.py` and filter the `states` list before printing.

Elapsed time should be computed from `state.accumulated_ms` (in milliseconds) using the same minutes/seconds formatting already used in `_helpers.py:run_foreground`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py:22-63` — update `cmd_list` to load YAML spec for paradigm/description in available-loops block; add status/elapsed display and `--status` filter in `--running` block
- `scripts/little_loops/cli/loop/__init__.py:117-118` — add `--status` argument to `list_parser` (e.g., `list_parser.add_argument("--status", help="Filter by status")`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:192` — sole caller of `cmd_list`
- `scripts/little_loops/fsm/persistence.py:417` — `list_running_loops()` returns `list[LoopState]`; `LoopState.status` and `LoopState.accumulated_ms` are the fields consumed by the new display

### Similar Patterns
- `scripts/little_loops/cli/loop/_helpers.py:73-100` — `load_loop_with_spec` shows how to get both `FSMLoop` and raw spec dict from a YAML file
- `scripts/little_loops/cli/loop/_helpers.py:270-276` — elapsed seconds/minutes formatting pattern to reuse
- `scripts/little_loops/cli/loop/info.py:59-62` — existing `[built-in]` label shows the column alignment approach to extend

### Tests
- `scripts/tests/test_ll_loop_commands.py` — add tests for paradigm/description display, `--running` status/elapsed, and `--status` filtering

### Documentation
- N/A — CLI `--help` output is auto-generated from argparse

## Implementation Steps

1. In `__init__.py`, add `list_parser.add_argument("--status", help="Filter running loops by status (e.g., interrupted, awaiting_continuation)")`
2. In `info.py`, in the `--running` branch: after `states = list_running_loops(loops_dir)`, apply `if getattr(args, "status", None): states = [s for s in states if s.status == args.status]`; update the print line to include `state.status` and elapsed derived from `state.accumulated_ms // 1000`
3. In `info.py`, in the available-loops branch: for each `yaml_files` path, open and `yaml.safe_load` to read `paradigm` and `description`; format display as `name  [paradigm]  description_first_line`
4. Add tests for all three new behaviors

## Impact

- **Priority**: P4 - Nice-to-have UX improvement for loop management
- **Effort**: Small-Medium - Needs to load loop specs for paradigm/description
- **Risk**: Low - Display-only changes, additive CLI flags
- **Breaking Change**: No

## Labels

`feature`, `ll-loop`, `cli`, `ux`

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: `ll-loop list` displays only loop names; no paradigm/description/status shown; no `--status` filter
- `/ll:format-issue` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe94482e-9372-4143-bed0-d453aad43004.jsonl` — reformatted to v2.0 FEAT template; added Motivation, Scope Boundaries, Proposed Solution, Integration Map, Implementation Steps; confirmed `LoopState.status`, `accumulated_ms` available in `persistence.py`; confirmed `FSMLoop.paradigm` in `schema.py`; confirmed description field in `loops/*.yaml`
- `/ll:confidence-check` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe94482e-9372-4143-bed0-d453aad43004.jsonl` — readiness: 96/100 PROCEED, outcome: 88/100 HIGH CONFIDENCE

---

## Status

**Open** | Created: 2026-03-06 | Priority: P4
