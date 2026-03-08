---
discovered_commit: 7ad4673a831718284ad0c0cf10178fe1194cc751
discovered_branch: main
discovered_date: 2026-03-08T00:52:40Z
discovered_by: capture-issue
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

- [ ] `--show-diagrams` flag added to `ll-loop run` (and `ll-loop resume` if applicable)
- [ ] FSM box diagram with active state highlight is shown each step **only** when `--show-diagrams` is passed
- [ ] `--verbose` no longer triggers FSM box diagram output
- [ ] `--verbose` and `--show-diagrams` can be combined without conflict
- [ ] Help text for `--show-diagrams` clearly describes its purpose
- [ ] Existing `--verbose` tests continue to pass without diagram assertions

## API / Interface Changes

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

## Related

- FEAT-637: FSM Box Diagram with Active State Highlight (the feature this refactors)

## Session Log

- `/ll:capture-issue` - 2026-03-08T00:52:40Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
