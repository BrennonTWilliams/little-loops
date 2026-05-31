# Implementation Plan: BUG-1817

**Issue**: `ll-loop resume` fails to auto-select latest resumable instance
**Decision**: Option A — Auto-select latest resumable instance (matches `cmd_monitor()` pattern)
**Confidence**: 100/100

## Solution Summary

Move instance discovery before the `--background` branch in `cmd_resume()`, auto-select the latest resumable instance (following `cmd_monitor()` pattern), pass the resolved ID to `run_background()`, and unhide `--instance-id` from help.

## Phase 0: Write Tests (Red)

New tests to add before implementation:

1. **`TestCmdResumeBackground.test_background_auto_selects_latest_resumable`** — Verify that when multiple resumable instances exist and no `--instance-id` is passed in background mode, the latest (sorted `[-1]`) is auto-selected and passed to `run_background()`.
2. **`TestCmdResumeBackground.test_background_errors_on_zero_resumable`** — Verify background mode exits with error when no resumable instances exist.
3. **`TestCmdResumeBackground.test_background_explicit_instance_id_takes_priority`** — Verify that explicit `--instance-id` overrides auto-selection in background mode.

## Phase 1: Implementation

### Step 1: Move instance discovery before `--background` branch (`lifecycle.py:371`)

Move `_find_instances()` call + `RESUMABLE_STATUSES` filter (currently lines 382-386) to BEFORE the `--background` check at line 371. Also move `running_dir` creation (lines 379-380) before.

### Step 2: Implement auto-selection (`lifecycle.py`)

After filtering resumable instances, before the `--background` branch:
- If zero resumable: error and exit 1
- If `explicit_instance_id` given: filter to that (existing logic)
- If one resumable: use it (existing logic)  
- If multiple resumable AND no explicit ID: auto-select `resumable[-1]` (new behavior, following `cmd_monitor()` at line 556)

### Step 3: Add optional `instance_id` param to `run_background()` (`_helpers.py:941`)

```python
def run_background(
    loop_name: str, args: argparse.Namespace, loops_dir: Path, 
    subcommand: str = "run", instance_id: str | None = None
) -> int:
```

At line 984, when `instance_id` is provided, use it instead of calling `_make_instance_id()`.

### Step 4: Wire resolved instance to `run_background()` (`lifecycle.py:372`)

Change `run_background(loop_name, args, loops_dir, subcommand="resume")` to pass `instance_id=<resolved_id>`.

### Step 5: Unhide `--instance-id` (`__init__.py:289`)

Change `help=argparse.SUPPRESS` to `help="Instance ID to resume (auto-detected if omitted)"`.

## Phase 2: Update Existing Tests

- **`test_background_flag_calls_run_background`** (line 679): Add `instance_id=ANY` to assertion
- **`test_background_skips_foreground_execution`** (line 692): Verify passes when `_find_instances` returns `[]` (no running dir in tmp_path)
- **`TestRunBackgroundShowDiagramsForwarding`** (test_ll_loop_display.py:3677): Verify optional param doesn't break
- **`test_handoff_threshold_registered_on_real_resume_parser`** (test_ll_loop_parsing.py:334): Verify unhiding doesn't break parser
- **`test_resume_command`** (test_cli.py:2209): Verify no regressions

## Phase 3: Update Documentation

- **`docs/reference/CLI.md:503`**: Rewrite multi-instance error prose → auto-selection behavior
- **`docs/guides/LOOPS_GUIDE.md`**: Review all resume references for accuracy

## Verification

```bash
python -m pytest scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_cli_loop_background.py scripts/tests/test_ll_loop_display.py scripts/tests/test_ll_loop_parsing.py scripts/tests/test_cli.py -v
```
