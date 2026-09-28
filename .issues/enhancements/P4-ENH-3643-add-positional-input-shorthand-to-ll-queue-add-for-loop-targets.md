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

A second bare token (`ll-queue add refine-to-ready-issue "$id"`) is rejected by argparse
as an unrecognized argument. `--input` is stored verbatim under `args["loop_input"]` by
`_classify_action` and is currently accepted for any runner kind, not just `loop`.

## Expected Behavior

`ll-queue add <loop> [input]` accepts an optional second positional that behaves exactly
like `--input`:

```bash
ll-queue add refine-to-ready-issue "$id" --priority P2
```

The positional and `--input` are mutually exclusive (both given → exit 2 with an
ambiguity error), and the positional is only valid when the target resolves to the
`loop` runner. Existing `--input`-only invocations are unchanged.

## Motivation

Users fanning out multiple issue IDs to a loop-runner queue entry (e.g. queuing
`refine-to-ready-issue` once per issue ID) currently must remember and type `--input`
for every entry. A second positional consistent with `ll-loop run` would shorten the
common case and reduce the cognitive gap between "run a loop directly" and "queue a
loop to run later" — the two commands should feel like the same verb with different
scheduling.

## Proposed Solution

In `scripts/little_loops/cli/queue.py`:

1. Add an optional second positional to the `add` subparser. Argparse derives `dest`
   from the first argument, so a positional literally named `input` would collide with
   `--input` (both `dest="input"`). Use a distinct dest with a display metavar:

   ```python
   add_parser.add_argument(
       "loop_input",
       nargs="?",
       default=None,
       metavar="input",
       help="Input for a LOOP-runner target (shorthand for --input)",
   )
   ```

2. In `cmd_add`, before calling `_classify_action`, reject the ambiguous case
   (`args.loop_input is not None and args.input is not None`) with an `Error:` message on
   stderr and return 2, matching the existing `ValueError` exit path.
3. Pass `args.loop_input if args.loop_input is not None else args.input` as
   `input_value` — no change to `_classify_action`, which already stores it verbatim
   under `args["loop_input"]` (JSON coercion stays at dequeue time).
4. After classification, if the positional was used and `spec.runner` is not
   `RunnerType.LOOP`, error out (exit 2). This restriction applies to the positional
   only; `--input` keeps its current permissive behaviour so existing invocations are
   unaffected.

## Program Design

### Types

- `loop_input: str | None` — new `argparse.Namespace` field set by the optional second positional

### Signatures

- `cmd_add(args: argparse.Namespace) -> int` — extended with the ambiguity and runner-kind checks
- `_classify_action(target: str, *, runner_override: str | None, timeout: int | None, arg_pairs: list[str] | None, input_value: str | None = None) -> Any` — unchanged

### Call Path

`main_queue` -> `cmd_add` -> `_classify_action` -> `add_entry`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/queue.py` — `add` subparser definition (~line 1190) and `cmd_add` (~line 229)
- `docs/reference/CLI.md` — `ll-queue add` flag table (~line 4599) and Examples block (~line 4672)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/queue.py` `main_queue` dispatches to `cmd_add`; no other importers of `cmd_add`
- Any loop/skill/script that shells out to `ll-queue add ... --input` is unaffected (backward compatible)

### Similar Patterns
- `ll-loop run <loop> [input]` — the positional being mirrored (`scripts/little_loops/cli/loop/`)
- `--input` handling in `_classify_action` (FEAT-2906)

### Tests
- `scripts/tests/test_cli_queue.py` — add cases beside `test_add_with_input_persists_onto_entry_args` (~line 156): positional persists to `args["loop_input"]`; positional + `--input` exits 2; positional with a non-loop runner exits 2; `--input`-only unchanged

### Documentation
- `docs/reference/CLI.md` — document the positional, update the example block

### Configuration
- N/A

## Implementation Steps

1. Add the optional second positional (`dest="loop_input"`, `metavar="input"`, `nargs="?"`) to the `add` subparser in `scripts/little_loops/cli/queue.py`.
2. In `cmd_add`, error out (exit 2) if both the positional and `--input` are given, rather than silently picking one.
3. Route the positional value through `_classify_action`'s existing `input_value` parameter (stored verbatim; JSON-object-vs-plain-string handling remains at dequeue time).
4. Error (exit 2) if the positional is used with a non-`loop` runner (skill/cmd/mcp/prompt); leave `--input` behaviour unchanged.
5. Add tests in `scripts/tests/test_cli_queue.py` and update `docs/reference/CLI.md`'s `ll-queue add` flags and examples.

## Success Metrics

- `ll-queue add <loop> "<id>"` produces a queue entry identical to `ll-queue add <loop> --input "<id>"` (same `args["loop_input"]`, runner, timeout)
- Zero regressions in `scripts/tests/test_cli_queue.py` existing `--input` tests

## Scope Boundaries

- **In scope**: optional second positional on `ll-queue add`; ambiguity error vs `--input`; loop-runner restriction for the positional; CLI reference docs and tests
- **Out of scope**: changing `--input` semantics or restricting it to loop runners (backward compatibility); JSON-parsing the input at enqueue time (`ll-queue add` never loads the FSM); adding positional input to other `ll-queue` subcommands; MCP queue tool changes

## Impact

- **Priority**: P4 - Ergonomic shorthand only; `--input` already covers the functionality
- **Effort**: Small - One argparse argument, a two-branch check in `cmd_add`, reuses `_classify_action` unchanged
- **Risk**: Low - Additive; existing `--input` invocations and the single-positional form are untouched
- **Breaking Change**: No

## Acceptance Criteria

- `ll-queue add refine-to-ready-issue "BUG-3354"` queues an entry equivalent to
  `ll-queue add refine-to-ready-issue --input "BUG-3354"`.
- `ll-queue add refine-to-ready-issue "BUG-3354" --input "ENH-1"` errors (ambiguous
  input), rather than silently preferring one.
- A positional input with a non-loop target/runner (e.g. `--runner cmd`) exits 2.
- Existing `--input`-only invocations continue to work unchanged (backward compatible).
- `docs/reference/CLI.md` documents the new positional and updates the example block.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-28 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-09-28T22:12:07 - `00e1806e-99df-47db-8e10-d56d6eca502a.jsonl`
- `/ll:capture-issue` - 2026-09-28T21:07:32 - `7f294095-d1d9-4ee9-9b43-311d4ce2c57c.jsonl`
