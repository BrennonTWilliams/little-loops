---
id: BUG-1817
captured_at: "2026-05-30T22:06:48Z"
discovered_date: 2026-05-30
discovered_by: capture-issue
status: open
---

# BUG-1817: `ll-loop resume` fails to auto-select latest resumable instance

## Summary

Running `ll-loop resume <loop-name> --background` (with no explicit instance ID) allocates a *new* instance timestamp, then errors because that brand-new ID is not among the resumable instances. The user must somehow learn the existing instance ID and pass it explicitly — but `ll-loop resume --help` does not show an instance positional, so it isn't obvious how.

## Current Behavior

`ll-loop resume <loop-name> --background` allocates a new instance timestamp unconditionally, then fails because the newly-created ID doesn't exist in the set of resumable instances. The error message identifies the resumable instances but doesn't tell the user how to select one. Since `ll-loop resume --help` doesn't expose an instance positional or flag, the user can't discover the correct invocation from the CLI alone.

## Steps to Reproduce

1. Start a loop: `ll-loop run pixi-generative-art --background ...`. Wait for it to begin iterating.
2. Stop it before terminal: `ll-loop stop pixi-generative-art`. The instance is now `interrupted`.
3. Try to resume: `ll-loop resume pixi-generative-art --background`.

Observed (reproduced this session):

```
Loop pixi-generative-art started in background (PID: 66619)
  Log: .loops/.running/pixi-generative-art-20260530T163647.log
```

…and the log contains:

```
Instance 'pixi-generative-art-20260530T163647' not found among resumable instances of 'pixi-generative-art'.
Resumable instances:
  pixi-generative-art-20260530T162645
```

The resume allocated a NEW timestamp `T163647` (the time `resume` was called), then immediately failed because the only resumable instance was the original `T162645`. The user has to: (a) discover the instance ID is needed, (b) figure out where to pass it (`--help` doesn't expose a positional), and (c) try again.

## Expected Behavior

Either:
- `ll-loop resume <loop-name>` with no instance ID **auto-selects the most recently interrupted instance** of that loop, OR
- Errors *before* allocating a new instance ID, printing the resumable instances and the exact command to use, e.g.:
  ```
  ❌ ll-loop resume requires an instance ID. Available:
    pixi-generative-art-20260530T162645  (interrupted, 26m ago)
  Try: ll-loop resume --instance pixi-generative-art-20260530T162645
  ```

Currently it silently does the wrong thing (allocates a new ID), then fails opaquely after the fact.

## Motivation

This bug makes loop resume unusable without prior knowledge of the instance ID. Users who interrupt a long-running loop and want to continue it later hit a silent failure with no discoverable recovery path from `--help`. Fixing this removes friction from the loop development workflow and aligns `resume` behavior with user expectations (resume should find the thing to resume).

## Root Cause

`scripts/little_loops/cli/loop/run.py` (or `lifecycle.py`) likely instantiates a new instance ID early in the `resume` codepath without checking whether resume mode means "use existing." Need to trace the path from `ll-loop resume <loop> --background` through to where the instance ID gets set.

## Proposed Solution

In the `resume` subcommand entry point:

1. Before allocating any new instance ID, scan `.loops/runs/` for instances of this loop with state != terminal.
2. If exactly one is found and no `--instance` was passed, use it.
3. If multiple are found and no `--instance` was passed, error with a helpful list (see Expected Behavior above).
4. If zero are found, error: "No resumable instances of <loop>."

Update `ll-loop resume --help` to document the instance argument (or `--instance` flag) so users know how to disambiguate.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py` — resume subcommand entry point
- `scripts/little_loops/cli/loop/lifecycle.py` — instance lifecycle management

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "ll-loop resume" scripts/`

### Similar Patterns
- TBD — check how `ll-loop stop` discovers running instances for similar selection logic

### Tests
- TBD — identify test files for loop CLI resume behavior

### Documentation
- TBD — update `ll-loop resume --help` output

### Configuration
- N/A

## Implementation Steps

1. Trace the `resume` codepath from CLI entry through to instance ID allocation
2. Add pre-allocation scan of `.loops/runs/` for non-terminal instances of the target loop
3. Implement auto-select (single match), helpful error (multiple matches), or not-found error
4. Expose `--instance` flag in `ll-loop resume --help` for manual disambiguation
5. Add tests for auto-select, multiple-match error, and zero-match error paths

## Impact

- **Priority**: P3 — Moderate. Resume is a convenience path; users can work around by manually passing instance IDs when discovered.
- **Effort**: Medium — Requires changes to CLI argument parsing and instance lifecycle logic in at least two files.
- **Risk**: Low — Changes are additive; existing run and stop codepaths are unaffected.
- **Breaking Change**: No

## Workaround

None obvious from `--help`. Users have to discover the syntax by trial and error or by reading `ll-loop history <loop>` output.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-30T22:36:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/51e4b8c3-1dc3-44cf-a08b-e4ed121b9e14.jsonl`
- `/ll:capture-issue` - 2026-05-30T22:06:48Z - this session

**Open** | Created: 2026-05-30 | Priority: P3
