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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- **Argparse placement constraint (verified)**: an optional positional (`nargs="?"`) declared after `target` binds correctly when it directly follows `target` (`add L X --priority P2`) on both Python 3.11.11 and 3.12.10, but the interleaved form `add L --priority P2 X` parses on 3.12.10 and fails with `unrecognized arguments: X` on 3.11.11. The project floor is Python 3.11 (`pip` here resolves to pyenv 3.11), so the documented and tested form must be the positional-immediately-after-target shape, and docs must not imply the interleaved form works.
- **Ambiguity check must compare against `args.input` after parsing**: because positional and `--input` land in different Namespace attributes (`loop_input` vs `input`), argparse itself cannot make them mutually exclusive; the exit-2 check has to live in `cmd_add` and return the code (matching the existing `return 2` contract), not raise `SystemExit`.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- **Second caller of `_classify_action`**: `scripts/little_loops/mcp_server/tools.py:_tool_queue_add` calls `_classify_action(..., input_value=str(input_value) if input_value is not None else None)` directly, with no `try/except ValueError`. Invariant: the positional-vs-runner restriction must not be added inside `_classify_action` (it would surface as an unhandled exception in the MCP tool, and would change `--input`'s deliberately permissive behaviour); it belongs in the argparse-facing `cmd_add`. `scripts/tests/test_enh_3444_mcp_skills_list.py` also calls `_classify_action` directly with the current keyword set, so its signature must stay as-is.
- **`--input` is accepted for every runner today**: `_classify_action` builds `args_dict["loop_input"]` before classification and passes it into every `ActionSpec` branch (override, LOOP, SKILL, CMD); `_format_args_summary` renders `input=...` for any runner. No existing test passes `input_value` with a non-loop runner, so the "`--input` unchanged" criterion has no current pin for the non-loop case.
- **Runner availability in `cmd_add`**: `spec.runner` is a `RunnerType` (`scripts/little_loops/runner_spec.py`) on the returned frozen `ActionSpec`. Without `--runner`, classification order is loop-file lookup (`resolve_loop_path`) → skill/command lookup → `CMD` fallback, so a bare loop name that has no `.loops/<name>.yaml` (or built-in) resolves to a non-`LOOP` runner and the positional would be rejected. `--runner` choices are `skill|cmd|mcp|prompt|loop` (`dsl` is not selectable).
- **Dest collision confirmed**: the `add` subparser already has `dest="input"` (from `--input`); `loop_input` is not a parser dest anywhere (it appears only as the `args` dict key), so it is free. `ll-loop run` declares its second positional as `input` (`scripts/little_loops/cli/loop/__init__.py`, `run_parser`) — there is no sibling `--input` there, which is why the naming differs.
- **Error-path contract in `cmd_add`**: the only existing error path is `except ValueError as exc: print(f"Error: {exc}", file=sys.stderr); return 2` — a returned code, not `SystemExit`. Tests assert it that way (`test_add_with_bad_arg_pair_exits_2` asserts `result == 2` and does not inspect stderr); argparse-level failures are the ones tested with `pytest.raises(SystemExit)`.
- **Test harness convention**: tests invoke `with patch("sys.argv", [...]): main_queue()` under an autouse `_isolate_cwd` fixture (chdir to `tmp_path`, so `.ll/queue.db` and `.loops/` are per-test). `scripts/tests/test_cli_queue_run.py` uses `ll-queue add <target> --runner cmd|loop --json` with a single bare token and is unaffected.
- **Docs anchors (verified current)**: `docs/reference/CLI.md` — subcommand table row `` `add TARGET` `` (line ~4583), `TARGET` flag-table row (~4595), `--input INPUT` row (~4599), Examples `--input` line (~4672). The subcommand-table and `TARGET` rows also describe the signature and need to reflect the optional second token. The `main_queue` epilog `Examples:` block has no `--input` example either.

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
- `/ll:refine-issue` - 2026-09-28T22:17:13 - `ddb9c068-0ba1-4e5f-bc15-cadeb7d03857.jsonl`
- `/ll:format-issue` - 2026-09-28T22:12:07 - `00e1806e-99df-47db-8e10-d56d6eca502a.jsonl`
- `/ll:capture-issue` - 2026-09-28T21:07:32 - `7f294095-d1d9-4ee9-9b43-311d4ce2c57c.jsonl`
