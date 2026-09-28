---
id: ENH-3643
type: ENH
title: Add positional [input] shorthand to ll-queue add for LOOP targets
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T21:07:23Z'
---

# ENH-3643: Add positional [input] shorthand to ll-queue add for LOOP targets

## Summary

`ll-queue add` has no positional counterpart to `ll-loop run <loop> [input]`'s second
positional. Queuing a LOOP-runner target with input always requires `--input`, even
though the CLI help text for that flag already describes it as having "the same
semantics as `ll-loop run <loop> [input]`" (`scripts/little_loops/cli/queue.py:1218-1220`).

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

Users fanning out multiple issue IDs to a loop-runner queue entry (e.g. queuing
`refine-to-ready-issue` once per issue ID) currently must remember and type `--input`
for every entry. A second positional consistent with `ll-loop run` would shorten the
common case and reduce the cognitive gap between "run a loop directly" and "queue a
loop to run later" — the two commands should feel like the same verb with different
scheduling.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

- Add an optional second positional (e.g. `input`, `nargs="?"`) to the `add` subparser
  in `scripts/little_loops/cli/queue.py`.
- If both the positional and `--input` are given, error out (ambiguous) rather than
  silently picking one.
- Route the positional value through the same JSON-object-vs-plain-string handling
  `--input` already uses (JSON object unpacks into matching context keys, else stored
  under `fsm.input_key`).
- Restrict the positional to `--runner loop` (or auto-classified loop targets) —
  non-loop runners (skill/cmd/mcp/prompt) don't have this semantics and should keep
  erroring/ignoring it the way they do today for `--input`.
- Update `docs/reference/CLI.md`'s `ll-queue add` section and its examples.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Current Pain Point

`add_parser` defines only one positional argument:

```python
add_parser.add_argument(
    "target", help="Loop name, skill/command name, or raw CLI invocation"
)
```

(`scripts/little_loops/cli/queue.py:1190-1192`)

There is no second positional, so the shortest form of queuing a loop with an argument is:

```bash
ll-queue add refine-to-ready-issue --input "$id" --priority P2
```

instead of the more familiar

```bash
ll-queue add refine-to-ready-issue "$id" --priority P2
```

which mirrors how `ll-loop run <loop> [input]` already works.

## Acceptance Criteria

- `ll-queue add refine-to-ready-issue "BUG-3354"` queues an entry equivalent to
  `ll-queue add refine-to-ready-issue --input "BUG-3354"`.
- `ll-queue add refine-to-ready-issue "BUG-3354" --input "ENH-1"` errors (ambiguous
  input), rather than silently preferring one.
- Existing `--input`-only invocations continue to work unchanged (backward compatible).
- `docs/reference/CLI.md` documents the new positional and updates the example block.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-28 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-09-28T21:07:32 - `7f294095-d1d9-4ee9-9b43-311d4ce2c57c.jsonl`
