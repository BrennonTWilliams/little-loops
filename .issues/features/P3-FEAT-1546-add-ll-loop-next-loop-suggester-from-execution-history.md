---
captured_at: '2026-05-17T07:28:10Z'
completed_at: '2026-05-17T16:00:56Z'
discovered_date: '2026-05-17'
discovered_by: capture-issue
status: done
decision_needed: false
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1546: Add `ll-loop next-loop` sub-command to suggest next loop from execution history

## Summary

Add a new `ll-loop next-loop` sub-command (or top-level `ll-next-loop`) that inspects loop execution history under `.loops/.history/` and suggests the next FSM loop to run, along with the right input/context parameters. Enables "auto-continue" workflows where the system can pick up the next obvious task (e.g., spawn another `autodev` run against currently-active issues) without the human specifying which loop to execute.

## Motivation

When the human user steps away (sleep, lunch, meeting), the obvious next loop run is often inferable from recent history — e.g. `autodev` has been run 12 times in the past week against active issues, so the natural continuation is another `autodev` pass. Today, the human has to manually choose the loop and its inputs every time, which prevents fully unattended chaining and scheduling. `next-loop` closes that gap: it picks the loop and the parameters, so `/loop`, scheduled jobs, or on-completion hooks can dispatch follow-up work without a human in the loop.

## Current Behavior

- `ll-loop run <name>` requires the user to know both the loop name and its parameters.
- `.loops/.history/<timestamp>-<loop-name>/` records every past run but nothing reads it for prediction.
- `/ll:loop-suggester` exists, but suggests *new loops to author* from message history (FEAT-219, FEAT-716), not which *existing loop* to run next.
- Auto-chaining a follow-up loop requires the caller to hard-code the loop name and inputs.

## Expected Behavior

`ll-loop next-loop` (default count = 1):

1. Scans `.loops/.history/` for loop run frequency, recency, and outcome.
2. Picks the loop with the strongest historical signal (frequency × recency, weighted toward successful completions).
3. If the loop accepts parameters (input arg, `--context key=value`), derives sensible defaults from project state — e.g. for `autodev`, pass the current set of `status: open` issue IDs as input.
4. Prints a suggestion the caller can act on, with both a human-readable summary and a machine-readable form (JSON / shell-ready command line).
5. With `--count N`, returns the top N candidates instead of just one.

Should compose cleanly with `/loop`, `/ll:schedule`, and on-completion hooks so a finishing loop can dispatch the next one.

## Use Case

User runs `/ll:schedule "ll-loop next-loop --execute" --every 2h` before stepping away. Every two hours, the scheduler invokes `next-loop`, which inspects history, picks `autodev`, pulls the current `status: open` issue list as input, and either prints the command or (with `--execute`) directly runs it. The user wakes up to a stack of attempted issues instead of an idle queue.

## API / Interface

New surface area:

- `ll-loop next-loop [--count N] [--format text|json] [--execute] [--exclude <name>...]`
  - Default `--count 1`.
  - `--format json` emits a list of `{loop, input, context, score, rationale, command}` objects suitable for piping into other tools.
  - `--execute` runs the top suggestion immediately via the same code path as `ll-loop run`.
  - `--exclude` skips named loops (e.g. exclude the loop that just finished if calling from an on-completion hook to avoid trivial self-loops).

Parameter-suggestion contract:

- For loops that declare a parameter shape (input arg, context keys) in their YAML, `next-loop` should resolve those to concrete values from project state where there is an obvious mapping (e.g. `autodev` → active issue IDs; `refine-to-ready-issue` → most-recently-captured issue lacking `ready: true`).
- Where no mapping is known, fall back to the same default the loop's YAML declares, or omit the parameter and flag it in `rationale`.

## Implementation Steps

1. Add a `next-loop` sub-parser under `scripts/little_loops/cli/loop/__main__.py` (alongside `run`, `info`, `lifecycle`, etc.).
2. New module `scripts/little_loops/cli/loop/next_loop.py`:
   - Read `.loops/.history/` directory listing; group by loop name.
   - Compute score per loop: weighted blend of count, recency (days-since-last-run decay), and success rate (from run metadata, if recorded — otherwise treat all as equal).
   - For the top-scored loop(s), look up the loop YAML to learn its parameter shape.
3. Add a small parameter-resolver registry mapping loop name → callable that returns suggested input/context (e.g. `autodev` → active issues via the existing `ll-issues list` code path).
4. Wire `--execute` to call the existing run path used by `ll-loop run`.
5. Emit JSON and text output formats; ensure JSON is stable for downstream tooling.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — Sub-parser registration** (`scripts/little_loops/cli/loop/__init__.py`):
- `known_subcommands` is a `set` of strings near the top of `main_loop()`. Add `"next-loop"` to it or bare-name shorthand logic will try to treat it as a loop name to `run`.
- Each sub-parser follows the three-step pattern: `subparsers.add_parser("next-loop", aliases=[], help="...")`, `.set_defaults(command="next-loop")`, then `.add_argument(...)` calls.
- Add a dispatch branch in the `if/elif` chain near the end of `main_loop()`.
- Import `cmd_next_loop` from `scripts/little_loops/cli/loop/next_loop.py` at the top of that dispatch block.

**Step 2 — History reading** (`scripts/little_loops/fsm/persistence.py`):
- `HISTORY_DIR = ".history"` — relative to `loops_dir` (resolved as `loops_dir / HISTORY_DIR`).
- `_RUN_FOLDER = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{6})-(.+)$")` — parse `(run_id, loop_name)` from directory names.
- `list_run_history(loops_dir, loop_name)` returns `list[LoopState]` sorted newest-first; use this or the `iterdir()` pattern in `_list_archived_runs()` (`info.py`) to scan all loops.
- `LoopState` fields for scoring: `status` (`"completed"`, `"failed"`, `"interrupted"`, `"awaiting_continuation"`, `"timed_out"`), `started_at` (ISO string), `accumulated_ms` (int), `iteration` (int).
- Loop YAML parameter shape: `FSMLoop.context` (dict of runtime vars) from `scripts/little_loops/fsm/schema.py`; positional input lands at `FSMLoop.context[FSMLoop.input_key]` (default key `"input"`).

**Step 3 — Parameter resolver for `autodev`**:
- Call `_load_issues_with_status(config, include_open=True, include_done=False, include_deferred=False)` from `scripts/little_loops/cli/issues/search.py` to get `list[tuple[IssueInfo, str]]`.
- Extract `issue.issue_id` from each tuple to build the active issue list.
- Scoring/ranking reference: `build_sort_key()` and `_STRATEGY_SORT_KEYS` in `search.py` show the weighted multi-field tuple-sort pattern to follow.
- Nearest analog for "rank items, pick top" logic: `cmd_next_issue()` in `scripts/little_loops/cli/issues/next_issue.py`.

**Step 4 — `--execute` wiring**:
- `cmd_run()` in `scripts/little_loops/cli/loop/run.py` is importable and callable directly — signature: `cmd_run(loop_name: str, args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int`.
- Construct an `argparse.Namespace` with the suggested loop name and resolved input, then call `cmd_run()` directly. No subprocess spawn needed.
- `run_background()` in `_helpers.py` exists if background dispatch is ever needed, but foreground inline call is the simpler path.

**Step 5 — JSON/text output**:
- `print_json(data)` in `scripts/little_loops/cli/output.py` handles formatted JSON to stdout.
- Existing sub-commands use `-j`/`--json` flag (not `--format text|json`); the issue's API proposes `--format text|json` — either convention works, but `-j`/`--json` is more consistent with the rest of the codebase.
- Guard with `getattr(args, "json", False)` to tolerate `Namespace` objects that lack the flag.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/little_loops/cli/loop/__init__.py` epilog — add a `next-loop` usage example to the `argparse.ArgumentParser(epilog=...)` examples block inside `main_loop()` (e.g., `%(prog)s next-loop --count 3`)
7. Add `test_next_loop_subcommand_registered` to `TestCmdSimulate` in `scripts/tests/test_ll_loop_execution.py` — patch `sys.argv = ["ll-loop", "next-loop", "--help"]` and assert `SystemExit(0)`, following `test_fragments_subcommand_registered` at line ~1355
8. Update `docs/reference/CLI.md` — add `#### next-loop` subsection under `### ll-loop` with full flag table (`--count N`, `--format text|json`, `--execute`, `--exclude <name>...`) and usage examples
9. Update `docs/guides/LOOPS_GUIDE.md` — add `next-loop` row to the subcommand table in `## CLI Quick Reference → ### Subcommands`

## Acceptance Criteria

- `ll-loop next-loop` prints exactly one suggestion by default, including loop name and concrete parameter values.
- `ll-loop next-loop --count 3` prints three ranked suggestions.
- `ll-loop next-loop --format json` emits valid JSON with `loop`, `input`, `context`, `score`, `rationale`, and `command` keys.
- For `autodev`, the suggested input matches the current set of active issue IDs (verifiable against `ll-issues list --status open`).
- `--execute` runs the top suggestion through the same code path as `ll-loop run` (no duplicate runner logic).
- Empty history produces a clear "no history available" message and exit code 1, not a crash.
- Unit tests cover: ranking, parameter resolution for at least one parameterized loop, JSON output stability, and the empty-history case.

## Impact

- **Priority**: P3 - Convenience feature enabling unattended chaining; not blocking other work
- **Effort**: Medium - New sub-command with history-reading, scoring logic, and parameter-resolver registry
- **Risk**: Low - Purely additive; new module with no changes to existing run path
- **Breaking Change**: No

## Labels

`cli`, `loops`, `automation`, `enhancement`

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `"next-loop"` to `known_subcommands` set; register sub-parser; add dispatch branch; import `cmd_next_loop`
- `scripts/little_loops/cli/loop/next_loop.py` — **create new**: `cmd_next_loop(args, loops_dir, logger) -> int`; scoring logic; parameter-resolver registry

### Key Imports / Dependencies
- `scripts/little_loops/fsm/persistence.py` — `list_run_history()`, `HISTORY_DIR`, `_RUN_FOLDER`, `LoopState`
- `scripts/little_loops/fsm/schema.py` — `FSMLoop` (fields: `context`, `input_key`, `parameters`)
- `scripts/little_loops/fsm/validation.py` — `load_and_validate()` to read loop YAML for parameter shape
- `scripts/little_loops/cli/loop/_helpers.py` — `resolve_loop_path()`, `get_builtin_loops_dir()`, `EXIT_CODES`
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` (called directly for `--execute`)
- `scripts/little_loops/cli/issues/search.py` — `_load_issues_with_status()` (for `autodev` param resolver)
- `scripts/little_loops/cli/output.py` — `print_json()` (for JSON output format)
- `scripts/little_loops/config/core.py` — `BRConfig` (for issue dir resolution in param resolvers)

### Similar Patterns to Follow
- `scripts/little_loops/cli/loop/info.py` — `_list_archived_runs()` — iterdir + sort pattern for reading history dirs
- `scripts/little_loops/cli/issues/next_issue.py` — `cmd_next_issue()` — "scan all items, rank, return top N" pattern
- `scripts/little_loops/cli/issues/search.py` — `build_sort_key()`, `_STRATEGY_SORT_KEYS` — weighted multi-field tuple-sort
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status()` — `getattr(args, "json", False)` + `print_json()` pattern

### Tests
- `scripts/tests/test_ll_loop_commands.py` — add `TestCmdNextLoop` class here (follows `TestCmdList`, `TestCmdValidate` structure)
- `scripts/tests/test_cli_loop_lifecycle.py` — reference for `cmd_*` unit-test structure with `tmp_path` + `MagicMock()` logger
- `scripts/tests/test_fsm_persistence.py` — reference for history-reading test fixtures

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_execution.py` — existing tests to **update**: add `test_next_loop_subcommand_registered` to `TestCmdSimulate` class, following the `test_simulate_subcommand_registered` / `test_fragments_subcommand_registered` pattern (`sys.argv = ["ll-loop", "next-loop", "--help"]` → `SystemExit(0)`) [Agent 3 finding]

### Documentation
- `docs/ARCHITECTURE.md` — may need a note about `next-loop` in the loop runner section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — contains the authoritative per-subcommand reference for `ll-loop` with `####` subsection per subcommand and a full `Examples:` block; add `#### next-loop` subsection with flag table (`--count`, `--format`, `--execute`, `--exclude`) and usage examples [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — section `## CLI Quick Reference → ### Subcommands` has a markdown table listing all `ll-loop` subcommands; add `next-loop` row [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — re-exports `main_loop` as public API (the resolved entry point); no code changes needed, but confirms the call chain: `pyproject.toml` → `little_loops.cli:main_loop` → this module → `cli/loop/__init__.py` [Agent 1 finding]
- `scripts/little_loops/cli/loop/__main__.py` — executes `main_loop()` as the `__main__` entry point; no changes needed, confirms the dispatch chain [Agent 1 finding]

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Loop runner and history layout |
| `.claude/CLAUDE.md` | CLI tool conventions and `ll-*` entry-point pattern |

## Session Log
- `/ll:ready-issue` - 2026-05-17T15:53:02 - `5e731980-ce6f-43fb-ae38-e4b5aaeea8ef.jsonl`
- `/ll:confidence-check` - 2026-05-17T15:51:28Z - `4dd26516-8037-4dcd-9076-330b857b2aa5.jsonl`
- `/ll:wire-issue` - 2026-05-17T00:00:00 - `current.jsonl`
- `/ll:refine-issue` - 2026-05-17T15:44:27 - `572ddb22-a72f-4507-bb72-1e4d1be296c4.jsonl`
- `/ll:capture-issue` - 2026-05-17T07:28:10Z - `dce8ab13-a2bf-4753-b7b8-76c3a497a18f.jsonl`

---

## Resolution

Implemented `ll-loop next-loop` sub-command:
- New module `scripts/little_loops/cli/loop/next_loop.py` with scoring, parameter resolver registry, and output formatting
- Registered sub-parser and dispatch in `scripts/little_loops/cli/loop/__init__.py`
- `autodev` parameter resolver resolves active issue IDs from project state
- Scoring: 50% frequency (log-scale) + 30% recency (exponential decay, 7-day half-life) + 20% success rate
- All flags implemented: `--count`, `--json`, `--execute`, `--exclude`
- 7 new tests: ranking, JSON stability, empty-history, exclude, count, registration
- Docs updated in `docs/reference/CLI.md` and `docs/guides/LOOPS_GUIDE.md`

## Status

Done
