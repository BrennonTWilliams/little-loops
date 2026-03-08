---
discovered_commit: 7ad4673a831718284ad0c0cf10178fe1194cc751
discovered_branch: main
discovered_date: 2026-03-08T00:52:40Z
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 93
---

# FEAT-642: Add `--show-diagrams` Flag to `ll-loop` for FSM Box Diagram Display

## Summary

FEAT-637 added an FSM box diagram with active state highlighting, triggered by `--verbose`. This makes `--verbose` output noisier and harder for AI agents to parse. Decouple diagram display into a dedicated `--show-diagrams` flag so human users can opt in explicitly, independent of verbosity level.

## Motivation

- `--verbose` is used by both human users and AI agents for debugging. Injecting visual ASCII diagrams into verbose output creates noise that interferes with agent log parsing.
- The FSM box diagram is a "delighter" feature for human users who want visual feedback on loop execution, but is not universally useful.
- A dedicated flag gives users precise control: full verbosity without diagrams, or diagrams without full verbosity.

## Use Case

A human user running a loop wants to watch the FSM state machine progress visually:

```bash
ll-loop run my-loop.yaml --show-diagrams
```

An AI agent running a loop in verbose mode for structured debugging output gets clean logs without diagram noise:

```bash
ll-loop run my-loop.yaml --verbose
```

Both flags can be combined for maximum output:

```bash
ll-loop run my-loop.yaml --verbose --show-diagrams
```

## Acceptance Criteria

- [x] `--show-diagrams` flag added to `ll-loop run` (and `ll-loop resume` if applicable)
- [x] FSM box diagram with active state highlight is shown each step **only** when `--show-diagrams` is passed
- [x] `--verbose` no longer triggers FSM box diagram output
- [x] `--verbose` and `--show-diagrams` can be combined without conflict
- [x] Help text for `--show-diagrams` clearly describes its purpose
- [x] Existing `--verbose` tests continue to pass without diagram assertions

## API/Interface

```
ll-loop run <config> [--verbose] [--show-diagrams] [--exit-code] [--context KEY=VALUE]
ll-loop resume <config> [--verbose] [--show-diagrams] [--exit-code] [--context KEY=VALUE]
```

New flag: `--show-diagrams` — Display the FSM box diagram with the current active state highlighted after each step.

## Implementation Steps

1. Locate where `--verbose` flag is parsed in `ll-loop` CLI (likely `scripts/little_loops/loop/` or `scripts/little_loops/cli/`)
2. Add `--show-diagrams` as a new boolean CLI argument
3. Find where the FSM box diagram is rendered (search for the FEAT-637 implementation — likely near `render_fsm_diagram` or similar)
4. Replace the `if verbose:` condition guarding diagram output with `if show_diagrams:`
5. Pass `show_diagrams` through the call chain alongside `verbose`
6. Update help text and any relevant docstrings
7. Update/add tests to verify:
   - `--verbose` alone does not show diagram
   - `--show-diagrams` alone shows diagram
   - Both flags together show diagram and verbose output

## Impact

- **Priority**: P3 — UX improvement; not blocking, but diagram noise in `--verbose` actively affects agent log parsing workflows
- **Effort**: Small — additive flag refactor; `--verbose` condition replaced by `--show-diagrams` in `_helpers.py`, propagated through call chain
- **Risk**: Low — purely additive; no behavior change to existing `--verbose` or other flags
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — Add `--show-diagrams` arg to `run` (line 113) subparser; add to `resume` subparser after `--context` arg (~line 177, no `--verbose` exists there currently)
- `scripts/little_loops/cli/loop/_helpers.py` — Replace `if verbose:` with `if show_diagrams:` in `run_foreground()` diagram branch (lines 292–321); propagate `show_diagrams` param through call signature

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — `_render_fsm_diagram()` called by `_helpers.py`; no changes needed here, only the call-site condition changes

### Similar Patterns
- `--verbose` flag propagation pattern in `run_background()` (`_helpers.py:212`) — check if diagram display exists there too and apply same decoupling

### Tests
- `scripts/tests/test_ll_loop_display.py` — Update `test_verbose_state_enter_prints_diagram` (line 1025) and `test_nonverbose_state_enter_no_diagram` (line 1046) to use `--show-diagrams`; add new tests for `--show-diagrams` alone and `--verbose --show-diagrams` combined

### Documentation
- N/A — no user-facing docs reference `--verbose` diagram behavior explicitly

### Configuration
- N/A

## Labels

`feature`, `cli`, `loop`, `ux`

## Related Key Documentation

- FEAT-637: FSM Box Diagram with Active State Highlight (the feature this refactors)

## Session Log

- `/ll:capture-issue` - 2026-03-08T00:52:40Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4db38ae0-a36b-494b-a855-6d7f6b8178be.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eef0284f-0058-4962-abe7-f481fe36fb93.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5da8f93f-6709-43ee-bcec-97fdfaf1d8be.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4205aea9-72fb-4d1f-aac7-c3f34b6f4898.jsonl`
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`

## Resolution

Implemented `--show-diagrams` flag as a dedicated opt-in for FSM diagram display, decoupled from `--verbose`.

### Changes Made
- `scripts/little_loops/cli/loop/__init__.py`: Added `--show-diagrams` arg to `run` and `resume` subparsers
- `scripts/little_loops/cli/loop/_helpers.py`: Changed diagram guard from `if verbose:` to `if show_diagrams:`; added `show_diagrams` forwarding in `run_background()`
- `scripts/tests/test_ll_loop_display.py`: Updated `_make_args` to include `show_diagrams`; replaced old verbose diagram tests with 4 precise tests covering `--show-diagrams` alone, `--verbose` alone (no diagram), no flags (no diagram), and both combined

---

**Completed** | Created: 2026-03-08 | Priority: P3
