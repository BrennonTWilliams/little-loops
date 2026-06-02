---
id: BUG-1817
captured_at: '2026-05-30T22:06:48Z'
completed_at: '2026-05-31T00:07:20Z'
discovered_date: 2026-05-30
discovered_by: capture-issue
status: done
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `run_background()` at line 984 — `instance_id = _make_instance_id(loop_name)`
- **Cause**: When `cmd_resume()` in `lifecycle.py:371` detects `--background`, it short-circuits to `run_background()` before any instance discovery. `run_background()` unconditionally generates a brand-new timestamp-based instance ID via `_make_instance_id()` (line 984) and injects it as `--instance-id` into the child process command (line 1000). The child process then enters `cmd_resume()` with this explicit (but nonexistent) instance ID, discovers the *actual* resumable instances via `_find_instances()` (`persistence.py:812`), and fails at `lifecycle.py:388-401` because the brand-new ID doesn't match any existing resumable instance.

### Full Call Trace

1. `main_loop()` in `__init__.py:616` dispatches `resume` → `cmd_resume()`
2. `cmd_resume()` in `lifecycle.py:371` detects `args.background` → calls `run_background(loop_name, args, loops_dir, subcommand="resume")`
3. `run_background()` in `_helpers.py:984` unconditionally calls `_make_instance_id(loop_name)` — generates e.g. `pixi-generative-art-20260530T163647`
4. `run_background()` at `_helpers.py:1000` injects `--instance-id <NEW-ID>` into the child command
5. Child process re-enters `cmd_resume()` with `explicit_instance_id` set (`lifecycle.py:388`)
6. Child discovers actual resumable instances via `_find_instances()` (`persistence.py:812`) — e.g. `pixi-generative-art-20260530T162645`
7. Filter at `lifecycle.py:389` finds no match → error printed at `lifecycle.py:394` → exit 1

### Contributing Factor

The `--instance-id` flag on the resume subparser (`__init__.py:289`) uses `help=argparse.SUPPRESS`, hiding it from `--help` output. Even if the user realizes an instance ID is needed, they cannot discover the flag name from the CLI.

## Proposed Solution

In the `resume` subcommand entry point (`cmd_resume()` at `lifecycle.py:371`):

1. Before allocating any new instance ID, call `_find_instances(loop_name, running_dir)` and filter by `RESUMABLE_STATUSES` (following the pattern in `cmd_stop()` at `lifecycle.py:295-301`).
2. If exactly one is found and no `--instance-id` was passed, use it — this already works in the foreground path (`lifecycle.py:415`).
3. **Design choice for multiple instances**: Two approaches exist:

   **Option A — Auto-select latest** (follows `cmd_monitor()` pattern at `lifecycle.py:556`):
   > **Selected:** Option A — best codebase fit and simplest fix for the reported bug
   - Auto-select `resumable[-1]` (the most recent by timestamp-sorted filename) when no `--instance-id` is passed.
   - Print a notice: `Auto-selected latest instance: <instance-id>`
   - This is the most user-friendly path; matches user expectation that "resume" should find the thing to resume.
   
   **Option B — Error with helpful list** (current multi-instance behavior in foreground path at `lifecycle.py:404-409`):
   - Print all resumable instances with their timestamps and ask the user to specify `--instance-id`.
   - Safer when the user needs explicit control, but requires knowing `--instance-id` exists (currently hidden from `--help`).

4. If zero are found, error: `No resumable instances of <loop>.`

In either case, the resolved `instance_id` must be passed to `run_background()` so it skips `_make_instance_id()` — either by accepting an optional `instance_id` parameter or by performing discovery before the `run_background()` call.

Update `ll-loop resume --help` to document the `--instance-id` flag (currently hidden via `help=argparse.SUPPRESS` at `__init__.py:289`) so users know how to disambiguate.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `cmd_monitor()` at `lifecycle.py:556` is the only existing auto-select implementation: uses `instances[-1]` to pick the latest instance by sorted filename. This is the pattern to model after for Option A.
- `_find_instances()` at `persistence.py:812` returns results pre-sorted by filename, and the timestamp format `YYYYMMDDTHHMMSS` sorts lexicographically — so `[-1]` reliably picks the most recent instance.
- `RESUMABLE_STATUSES` at `persistence.py:45` = `{"running", "awaiting_continuation", "interrupted"}` — these are the states to filter for.
- The `--instance-id` flag on the resume subparser at `__init__.py:289` uses `help=argparse.SUPPRESS`, making it invisible to users. Unhiding it (or changing to `help="Instance ID to resume (auto-detected if omitted)"`) would make the fallback path discoverable.
- `run_background()` at `_helpers.py:941` already accepts `subcommand` parameter; it could also accept an optional `instance_id` parameter to skip allocation.
- The fix is minimal: move the `_find_instances()` + `RESUMABLE_STATUSES` filter block (currently at `lifecycle.py:383-386`) BEFORE the `--background` branch at `lifecycle.py:371`, resolve the instance ID, then pass it to `run_background()`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-30.

**Selected**: Option A — Auto-select latest resumable instance

**Reasoning**: Option A follows the existing `cmd_monitor()` auto-selection pattern at `lifecycle.py:556` exactly — the codebase already sorts instances and picks `[-1]`. It's the simplest fix (move discovery before the `--background` branch, pick the last result, pass it through) and directly addresses the user expectation that "resume should find the thing to resume." Option B preserves the current friction where users must discover a hidden `--instance-id` flag and re-run, which is the behavior this bug exists to fix.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Auto-select latest | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| Option B — Error with helpful list | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- **Option A**: `cmd_monitor()` at `lifecycle.py:556` already implements `instances[-1]` auto-selection — this is the established pattern. `_find_instances()` returns results pre-sorted by timestamp-formatted filename, so `[-1]` reliably picks the most recent. Adding an optional `instance_id` param to `run_background()` is a 3-line change. Minimal new code, no new abstractions.
- **Option B**: The foreground path at `lifecycle.py:404-409` errors on multiple instances, but that's the behavior we're fixing — it forces users to discover a hidden `--instance-id` flag and re-run. Requires similar code changes to Option A (move discovery before `--background`) but leaves the UX friction in place. Conflicts with the established `cmd_monitor()` auto-selection pattern.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/lifecycle.py:371` — `cmd_resume()`: move instance discovery BEFORE the `run_background()` call so resumable instances are identified before any new ID allocation
- `scripts/little_loops/cli/loop/_helpers.py:984` — `run_background()`: accept an optional `instance_id` parameter to skip `_make_instance_id()` when the caller already resolved one; or add pre-discovery logic before the `--background` branch in `cmd_resume()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py:45` — `RESUMABLE_STATUSES` constant definition (read-only, no change needed)
- `scripts/little_loops/fsm/persistence.py:812` — `_find_instances()` used by `cmd_resume()` for instance discovery (no change needed, already correct)
- `scripts/little_loops/cli/loop/__init__.py:289` — `--instance-id` flag on resume subparser (consider unhiding from help for discoverability)
- `scripts/little_loops/cli/loop/run.py:242` — `cmd_run()` also calls `run_background()` (with `subcommand="run"`). Unaffected by optional `instance_id` param, but worth noting as the only other `run_background()` callsite. [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/cli/loop/lifecycle.py:556` — `cmd_monitor()`: uses `instances[-1]` to auto-select the latest instance by sorted filename — the exact pattern to follow for auto-selection
- `scripts/little_loops/cli/loop/lifecycle.py:286` — `cmd_stop()`: discovers instances first via `_find_instances()`, then filters by `status == "running"`, then acts on each — the correct ordering that `cmd_resume` should emulate

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py:332` — `TestCmdResume` (foreground resume tests)
- `scripts/tests/test_cli_loop_lifecycle.py:666` — `TestCmdResumeBackground` (background resume tests)
- `scripts/tests/test_cli_loop_lifecycle.py:1931` — `TestCmdResumeMultiInstance` (multi-instance error and single-instance success tests — directly relevant)
- `scripts/tests/test_cli_loop_lifecycle.py:1989` — `TestCmdResumeInterrupted` (interrupted instance resumability)
- `scripts/tests/test_cli_loop_lifecycle.py:1710` — `TestFindInstances` (_find_instances unit tests)
- `scripts/tests/test_cli_loop_background.py:269` — `test_resume_subcommand_spawns_resume` (verifies background resume spawns correct subcommand)
- `scripts/tests/test_cli_loop_background.py:1107` — `TestMakeInstanceId` (instance ID format tests)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_cli_loop_lifecycle.py:679` — `test_background_flag_calls_run_background`: asserts `mock_rb.assert_called_once_with("test-loop", args, tmp_path, subcommand="resume")`. Will break when `instance_id=...` kwarg is added — update to `assert_called_once_with("test-loop", args, tmp_path, subcommand="resume", instance_id=ANY)`. [Agent 2 finding]
- `scripts/tests/test_cli_loop_lifecycle.py:692` — `test_background_skips_foreground_execution`: may need `_find_instances` patched when discovery moves before the `--background` branch (if `running_dir` doesn't exist in tmp_path, returns `[]` and should pass as-is; verify). [Agent 2 finding]
- `scripts/tests/test_ll_loop_display.py:3677` — `TestRunBackgroundShowDiagramsForwarding`: tests `run_background()` Popen command-line construction. Verify works with new optional `instance_id` param. [Agent 3 finding]
- `scripts/tests/test_ll_loop_parsing.py:334` — `test_handoff_threshold_registered_on_real_resume_parser`: exercises resume subparser with `cmd_resume` patched. Verify `--instance-id` unhiding doesn't break parser registration. [Agent 3 finding]
- `scripts/tests/test_cli.py:2209` — patches `_find_instances`; contains `test_resume_command` exercising `cmd_resume`. Verify no regressions. [Agent 1 finding]

### Documentation
- `docs/reference/CLI.md:501-508` — documents `ll-loop resume` subcommand flags (needs update if `--instance-id` is unhidden)
- `docs/guides/LOOPS_GUIDE.md:1843-1851` — documents resume behavior (needs update for auto-selection)

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CLI.md:503` — prose: "Exits with an error listing instance IDs when two or more resumable instances exist" directly contradicts proposed auto-selection behavior; must be updated. [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:354,598,638,1653,1679,1730,2599,2719,3249` — additional resume references beyond the already-listed 1843-1851; review for behavioral accuracy post-fix. [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. **Move instance discovery before the `--background` branch** in `cmd_resume()` at `lifecycle.py:371`: call `_find_instances()` and filter by `RESUMABLE_STATUSES` before the `if getattr(args, "background", False):` check. This ensures the resumable instance set is known regardless of execution mode.
2. **Implement auto-selection or early error** (depending on resolution of design choice in Proposed Solution):
   - If Option A: auto-select `resumable[-1]` (following `cmd_monitor()` pattern at `lifecycle.py:556`), print notice.
   - If Option B: error with list when multiple instances exist and no `--instance-id` passed (existing logic at `lifecycle.py:404-409`).
3. **Pass resolved instance ID to `run_background()`**: add optional `instance_id` parameter to `run_background()` at `_helpers.py:941`. When provided, skip the `_make_instance_id()` call at `_helpers.py:984` and use the provided ID. Wire it through `cmd_resume()` at `lifecycle.py:372`: `return run_background(loop_name, args, loops_dir, subcommand="resume", instance_id=resolved_id)`.
4. **Unhide `--instance-id` from `--help`**: change `help=argparse.SUPPRESS` to a descriptive help string at `__init__.py:289` (e.g., `"Instance ID to resume (auto-detected if omitted)"`).
5. **Add tests** following patterns in `test_cli_loop_lifecycle.py`:
   - Extend `TestCmdResumeMultiInstance` (line 1931) to cover auto-selection of latest instance when multiple are resumable (if Option A chosen).
   - Extend `TestCmdResumeBackground` (line 666) to verify background resume uses the correct existing instance ID instead of allocating a new one.
   - Add test for zero-resumable-instances path in background mode.
6. **Update docs**: `docs/reference/CLI.md:501-508` if `--instance-id` is unhidden; `docs/guides/LOOPS_GUIDE.md:1843-1851` for updated resume behavior.
7. **Verify**: Run `python -m pytest scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_cli_loop_background.py -v` to confirm no regressions.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Update `test_background_flag_calls_run_background`** at `test_cli_loop_lifecycle.py:679`: change `assert_called_once_with("test-loop", args, tmp_path, subcommand="resume")` to accept the new `instance_id=...` kwarg (e.g., `instance_id=ANY`).
9. **Verify `test_background_skips_foreground_execution`** at `test_cli_loop_lifecycle.py:692`: confirm it still passes after instance discovery moves before the `--background` branch. If `running_dir` doesn't exist in tmp_path, `_find_instances()` returns `[]` and the test should pass as-is.
10. **Verify `TestRunBackgroundShowDiagramsForwarding`** at `test_ll_loop_display.py:3677`: confirm `run_background()` Popen command-line tests still pass with new optional `instance_id` param.
11. **Verify resume subparser tests** at `test_ll_loop_parsing.py:334`: confirm `--instance-id` unhiding doesn't break parser registration.
12. **Verify `test_resume_command`** at `test_cli.py:2209`: confirm cmd_resume exercise still passes.
13. **Update `docs/reference/CLI.md:503`**: rewrite the multi-instance error prose to reflect auto-selection behavior.
14. **Review `docs/guides/LOOPS_GUIDE.md`**: check all resume references (lines 354, 598, 638, 1653, 1679, 1730, 1843-1851, 2599, 2719, 3249) for accuracy post-fix.
15. **Run full test suite**: `python -m pytest scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_cli_loop_background.py scripts/tests/test_ll_loop_display.py scripts/tests/test_ll_loop_parsing.py scripts/tests/test_cli.py -v` to confirm no regressions across all affected test files.

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
- `/ll:ready-issue` - 2026-05-30T23:57:28 - `4467f377-9c28-4ac2-8355-523b121dd444.jsonl`
- `/ll:decide-issue` - 2026-05-30T23:52:45 - `036f576f-3522-43ca-985f-04f3a17d8140.jsonl`
- `/ll:wire-issue` - 2026-05-30T23:47:43 - `9fb81c50-c1ea-4f01-9e99-100cd2d449e0.jsonl`
- `/ll:confidence-check` - 2026-05-30T23:50:00 - `e9d6ca49-3428-421c-b16e-4d42ea05873a.jsonl`
- `/ll:refine-issue` - 2026-05-30T23:42:15 - `f68438cb-0bf5-4403-b436-89c264cf23d0.jsonl`
- `/ll:format-issue` - 2026-05-30T22:36:56 - `51e4b8c3-1dc3-44cf-a08b-e4ed121b9e14.jsonl`
- `/ll:capture-issue` - 2026-05-30T22:06:48Z - this session
- `/ll:confidence-check` - 2026-05-30T23:55:00Z - `521d38a9-e54b-4340-a6ec-f4e9418460d9.jsonl`

**Open** | Created: 2026-05-30 | Priority: P3
