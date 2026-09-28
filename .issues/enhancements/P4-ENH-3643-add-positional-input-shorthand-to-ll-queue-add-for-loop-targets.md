---
id: ENH-3643
type: ENH
title: Add positional [input] shorthand to ll-queue add for LOOP targets
priority: P4
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T21:07:23Z'
completed_at: '2026-09-28T23:36:53Z'
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3643: Add positional [input] shorthand to ll-queue add for LOOP targets

## Summary

`ll-queue add` has no positional counterpart to `ll-loop run <loop> [input]`'s second
positional. Queuing a LOOP-runner target with input always requires `--input`, even
though the CLI help text for that flag already describes it as having "the same
semantics as `ll-loop run <loop> [input]`" (`scripts/little_loops/cli/queue.py:1219-1222`).

## Current Behavior

`add_parser` defines only one positional argument:

```python
add_parser.add_argument(
    "target", help="Loop name, skill/command name, or raw CLI invocation"
)
```

(`scripts/little_loops/cli/queue.py:1191-1193`)

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
   (`args.loop_input is not None and args.input is not None`) with this message on
   stderr and return 2, matching the existing `ValueError` exit path:

   ```
   Error: input given both positionally and via --input; use one
   ```

3. Pass `args.loop_input if args.loop_input is not None else args.input` as
   `input_value` — no change to `_classify_action`, which already stores it verbatim
   under `args["loop_input"]` (JSON coercion stays at dequeue time).
4. After classification, if the positional was used and `spec.runner` is not
   `RunnerType.LOOP`, print this message on stderr and return 2 (nothing is enqueued):

   ```
   Error: positional input is only valid for loop targets ('<target>' classified as <runner>); use --input, or quote the full command
   ```

   `<runner>` is `spec.runner.value`. Naming the runner is required: a loop name that
   does not resolve (a typo, or no `.loops/<name>.yaml` in the current directory) falls
   through classification to `cmd`, and without the runner in the message the user
   cannot tell why their loop target was rejected. The "quote the full command" hint
   covers the unquoted raw-command case (`ll-queue add pytest tests/`), which today fails
   in argparse with `unrecognized arguments` and after this change reaches `cmd_add`
   instead. This restriction applies to the positional only; `--input` keeps its current
   permissive behaviour so existing invocations are unaffected.

**Rationale vs. the FEAT-2906 design note.** FEAT-2906 says "Do not add a bare second
positional to `ll-queue add`: it would collide with `target`, which under `--runner cmd`
is already a full command line." That concern is about a raw command's words being
split across `target` and a second positional. Step 4 removes it: the positional is
accepted only when the target classifies as (or is forced to) `LOOP`, where `target` is
a single loop name. For every non-loop runner a second token is still an error, as it is
today; only the message changes from argparse's to the one above.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

- **Argparse placement constraint (verified)**: an optional positional (`nargs="?"`) declared after `target` binds correctly when it directly follows `target` (`add L X --priority P2`) on both Python 3.11.11 and 3.12.10, but the interleaved form `add L --priority P2 X` parses on 3.12.10 and fails with `unrecognized arguments: X` on 3.11.11. The project floor is Python 3.11 (`pip` here resolves to pyenv 3.11), so the documented and tested form must be the positional-immediately-after-target shape, and docs must not imply the interleaved form works. Re-verified 2026-09-28: the flags-before-target form `add --priority P2 L X` binds correctly on both 3.11.11 and 3.12.10, so docs may show it as well.
- **Test-authoring trap (Python version skew)**: the local `python` is 3.12 but CI unit tests run on 3.11 (`.github/workflows/ci.yml` `python-version: '3.11'`). A test that uses the interleaved form `add L --priority P2 X` passes locally and fails in CI. Tests must use only `add L X [flags]` (or `add [flags] L X`). Do not add a test for the interleaved form; if one is wanted, it must skip below Python 3.12.
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

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:5126` — `add TARGET` bullet in `### main_queue` lists `--priority`, `--runner`, `--arg`, `--timeout`, `--json` but no `--input` at all (already stale since FEAT-2906); add `[input]` positional and `--input` [Agent 2 finding]
- `docs/reference/API.md:5123` — **Returns** line in `### main_queue` says "2 on a malformed `--arg`"; extend for the new ambiguity / non-loop-runner exit-2 paths [Agent 2 finding]
- `scripts/little_loops/cli/queue.py:1170` — `main_queue` epilog `Examples:` block has no `--input` example; optionally add `ll-queue add <loop> "<id>"` [Agent 1 finding]
- `docs/reference/CLI.md:4583` and `:4595` — `` `add TARGET` `` subcommand-table row and the `TARGET` flag row in `### ll-queue`; reflect the optional second token (also `:4613` prose mentioning `loop_input`) [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/queue.py` `main_queue` dispatches to `cmd_add`; no other importers of `cmd_add`
- Any loop/skill/script that shells out to `ll-queue add ... --input` is unaffected (backward compatible)

_Wiring pass added by `/ll:wire-issue`:_
- `.issues/features/P2-FEAT-2906-ll-queue-run-loop-dispatch-via-persistentexecutor.md:172` — design note in the `--input` section of FEAT-2906: "Do not add a bare second positional to `ll-queue add`: it would collide with `target`, which under `--runner cmd` is already a full command line." ENH-3643 does not address it. The mitigation is already in the plan (positional rejected with exit 2 unless the target classifies as `LOOP`), but a raw-command target followed by a stray word now gets a `cmd_add` error instead of an argparse "unrecognized arguments" error; the AC and a test must cover it [Agent 2 finding]
- `scripts/little_loops/cli/queue.py:476` — `_dispatch_loop_entry` appends `action.args.get("loop_input")` as the bare positional of `ll-loop run <loop> <input>`; a positional-sourced value is stored identically, so no change [Agent 1 finding]
- `scripts/little_loops/cli/queue.py:96` — `_format_args_summary` renders `input=...` from `args["loop_input"]` for any runner; no change [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py` — re-exports `main_queue` only (`cmd_add` is not re-exported); no change [Agent 1 finding]
- No loop YAML, skill, command, hook or `.sh` script shells out to `ll-queue add`; `.loops/probes/enh-3507-served-page-probes.mjs` `ll(cmd)` uses only `cancel`/`requeue` [Agent 1 finding]
- Argparse `cmd_add` reads no Namespace generically (`vars(args)` unused); `args.loop_input` is read nowhere today [Agent 2 finding]

### Similar Patterns
- `ll-loop run <loop> [input]` — the positional being mirrored (`scripts/little_loops/cli/loop/`)
- `--input` handling in `_classify_action` (FEAT-2906)

### Tests
- `scripts/tests/test_cli_queue.py` — add cases beside `test_add_with_input_persists_onto_entry_args` (~line 156): positional persists to `args["loop_input"]`; positional + `--input` exits 2; positional with a non-loop runner exits 2; `--input`-only unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_queue.py:122` — new cases go in `TestCmdAdd` after `test_add_with_input_persists_onto_entry_args` (:156). No existing `TestCmdAdd` test resolves a loop from a file through `main_queue`; create `.loops/<name>.yaml` in `tmp_path` (as `TestClassifyAction.test_classifies_loop_name` does at :46, under the autouse `_isolate_cwd`) or pass `--runner loop`. Use argv shape `add <target> <input> [flags]` [Agent 3 finding]
- All new `TestCmdAdd` argv lists must place the input immediately after the target (`["ll-queue", "add", L, X, "--priority", "P2"]`) — the interleaved form fails on the 3.11 CI runner (see Codebase Research Findings)
- `scripts/tests/test_cli_queue.py:176` — `test_add_with_bad_arg_pair_exits_2` asserts only `result == 2`; the new ambiguity/non-loop tests should also assert the exact message substrings from Proposed Solution steps 2 and 4 (`"given both positionally and via --input"`; `"only valid for loop targets"` plus `"classified as cmd"`) in stderr via `capsys` (template: `test_cli_learning_tests.py:69`) and that `list_entries()` is empty [Agent 3 finding]
- `scripts/tests/test_cli_queue.py:88` — `test_input_value_stored_verbatim_under_loop_input` covers `_classify_action` with `runner_override="loop"`; no test pins `--input` with a non-loop runner, so add `add x --runner cmd --input Y` → 0 to pin "`--input` unchanged" [Agent 3 finding]
- `scripts/tests/test_cli_queue.py` — extra cases: `add L X` entry equals `add L --input X` (args, runner, timeout — the Success Metric); `add L X --priority P2` binds on 3.11; bare unresolved name + positional → 2; raw-command target (`add "pytest tests/" extra --runner cmd`) → 2 (FEAT-2906 collision case); empty-string positional counts as given (`is not None`) [Agent 3 finding]
- `scripts/tests/test_cli_queue_run.py:40` — helpers `_add_target`/`_add_and_get_id` and `TestCmdRunLoopDispatch._add_loop` (:316) use a single bare token; unaffected [Agent 3 finding]
- `scripts/tests/test_cli_surface.py:144` — `test_build_cli_surface_index_against_real_metavar_tools` scrapes `ll-queue --help` for subcommand names and long flags only (`_LONG_FLAG_RE` in `issues/cli_surface.py`); a positional line is invisible to it, but the `--input INPUT` line must stay [Agent 2 finding]
- `scripts/tests/test_enh_3444_mcp_skills_list.py:243` and `scripts/tests/test_feat_queue_mcp_tools.py` — call `_classify_action` / MCP `queue_add` with the current keyword set; break only if `_classify_action`'s signature or error behaviour changes (it must not) [Agent 3 finding]
- No test pins `ll-queue add --help`/usage text or compares `CLI.md` to the parser; the docs edit is not test-enforced [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — document the positional, update the example block

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:4583` — `` `add TARGET` `` row in the `### ll-queue` Subcommands table; show the optional `[input]` [Agent 1 finding]
- `docs/reference/API.md:5126` — `add TARGET` bullet in `### main_queue`; add `[input]` and `--input` (see Files to Modify) [Agent 2 finding]
- Docs must show only the positional-immediately-after-target shape (`add L X --priority P2`) or the flags-first shape (`add --priority P2 L X`); the interleaved form `add L --priority P2 X` fails on Python 3.11 [Agent 2 finding]
- `docs/reference/CLI.md` is end-user audience — no `scripts/tests/` paths (`test_docs_audience_gate.py`) [Agent 2 finding]

### Configuration
- N/A — `config-schema.json` `queue` covers only the DB path [Agent 1 finding]

### Integration Research Findings

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/API.md` `### main_queue` — `add TARGET` bullet (add `[input]` and `--input`) and the **Returns** line (new exit-2 paths)
- Update `docs/reference/CLI.md` — `add TARGET` subcommand row, `TARGET` flag row and Examples block; show only the `add L X --priority P2` ordering
- Optionally add an `--input`/positional example to `main_queue`'s epilog `Examples:` block in `queue.py`
- Keep the runner-kind check in `cmd_add`, never `_classify_action` (`_tool_queue_add` has no `try/except ValueError`; `test_enh_3444_mcp_skills_list.py` pins the signature)
- Add the `capsys`-asserting exit-2 tests, the `--input`-with-non-loop-runner pin and the raw-command-plus-stray-word test in `TestCmdAdd` (`test_cli_queue.py`)
- Acknowledge the FEAT-2906 "no bare second positional" design note in the Proposed Solution rationale (guarded by the `LOOP`-only restriction)

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
- `ll-queue add refine-to-ready-issue "BUG-3354" --input "ENH-1"` exits 2 with
  `Error: input given both positionally and via --input; use one` on stderr, rather than
  silently preferring one, and enqueues nothing.
- A positional input with a non-loop target/runner (e.g. `--runner cmd`, or a loop name
  that does not resolve) exits 2 with
  `Error: positional input is only valid for loop targets ('<target>' classified as <runner>); use --input, or quote the full command`
  on stderr, and enqueues nothing.
- The Proposed Solution states why the loop-only restriction resolves the FEAT-2906
  "no bare second positional" design note.
- All new tests use the positional-immediately-after-target argv shape and pass on the
  Python 3.11 CI runner.
- Existing `--input`-only invocations continue to work unchanged (backward compatible).
- `docs/reference/CLI.md` documents the new positional and updates the example block.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-28 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-09-28T23:36:53 - `83ac1e49-6b2b-4760-949f-e5772941f97a.jsonl`
- `/ll:ready-issue` - 2026-09-28T23:29:03 - `6b3e8a79-8bfd-4e04-88fb-db485036db20.jsonl`
- `/ll:confidence-check` - 2026-09-28T22:41:59 - `567c9044-53d9-466d-a31f-6021ef77a649.jsonl`
- `/ll:wire-issue` - 2026-09-28T22:36:29 - `29b6f7a1-cbe3-4641-a1f5-b4e98b2d2120.jsonl`
- `/ll:refine-issue` - 2026-09-28T22:17:13 - `ddb9c068-0ba1-4e5f-bc15-cadeb7d03857.jsonl`
- `/ll:format-issue` - 2026-09-28T22:12:07 - `00e1806e-99df-47db-8e10-d56d6eca502a.jsonl`
- `/ll:capture-issue` - 2026-09-28T21:07:32 - `7f294095-d1d9-4ee9-9b43-311d4ce2c57c.jsonl`

## Resolution

**Implemented** 2026-09-28. Added an optional second positional (`dest="loop_input"`, `metavar="input"`) to `ll-queue add`. `cmd_add` rejects positional + `--input` (exit 2) and rejects the positional for non-`loop` runners (exit 2, naming the classified runner); `_classify_action` is unchanged. Tests added in `TestCmdAdd`; `docs/reference/CLI.md` and `API.md` updated.
