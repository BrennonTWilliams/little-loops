---
id: ENH-569
priority: P3
status: active
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: null
outcome_confidence: null
---

# ENH-569: `ll-loop show` prompt action text over-truncated at 70 chars

## Summary

`cmd_show` truncates all action text to 70 characters regardless of action type. For `action_type: prompt` states, the full prompt *is* the spec — 70 chars conveys almost nothing useful. The output is misleading because it implies completeness.

## Current Behavior

For the `fix` state in `issue-refinement`:
```
  [fix]
    action: Run `ll-issues refine-status` to see the current refinement state of a...
    type: prompt
```

The prompt is ~1,500 chars long. The truncation hides all actionable content.

## Expected Behavior

Show a meaningful excerpt, differentiated by action type:

- **`shell`** actions: keep 70-char single-line truncation (these are commands, brevity works)
- **`prompt`** actions: show first 3 lines or ~200 chars, then `...` — enough to see the intent
- **`slash_command`** actions: show full command (usually short)

Additionally, add a `--verbose` / `-v` flag to `ll-loop show` that prints the full action text and full evaluate prompt for all states.

## Motivation

When debugging a loop or reviewing it before running, the prompt action text is what you most need to read. The current 70-char cap forces users to open the YAML file directly, defeating the purpose of `ll-loop show`.

## Implementation Steps

1. **`__init__.py:164-166` — Add `--verbose/-v` to `show` subparser**:
   ```python
   show_parser = subparsers.add_parser("show", help="Show loop details and structure")
   show_parser.add_argument("loop", help="Loop name or path")
   show_parser.add_argument("--verbose", "-v", action="store_true", help="Show full action text and evaluate prompt")
   ```

2. **`__init__.py:195-196` — Update dispatch to forward `args`** (following `cmd_history` pattern at `__init__.py:188`):
   ```python
   elif args.command == "show":
       return cmd_show(args.loop, args, loops_dir, logger)
   ```

3. **`info.py:503` — Update `cmd_show` signature** to accept `args: argparse.Namespace`:
   ```python
   def cmd_show(loop_name: str, args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int:
   ```

4. **`info.py:546-552` — Replace truncation block** with action-type-aware display:
   ```python
   if state.action:
       verbose = getattr(args, "verbose", False)
       if verbose:
           print(f"    action: |\n      {state.action.strip()}")
       elif state.action_type == "prompt":
           lines = state.action.strip().splitlines()
           preview = "\n      ".join(lines[:3])
           if len(lines) > 3 or len(state.action) > 200:
               preview += " ..."
           print(f"    action: |\n      {preview}")
       else:  # shell, slash_command, or None
           action_display = state.action[:70] + "..." if len(state.action) > 70 else state.action
           print(f"    action: {action_display}")
   if state.action_type:
       print(f"    type: {state.action_type}")
   if state.evaluate:
       print(f"    evaluate: {state.evaluate.type}")
       if verbose and state.evaluate.prompt:
           print(f"    evaluate_prompt: |\n      {state.evaluate.prompt.strip()}")
   ```

5. **`_helpers.py:110-114` — Apply same per-type fix to `print_execution_plan`** (for `ll-loop run --dry-run` consistency):
   Apply the same action_type-aware truncation; `print_execution_plan` receives `fsm: FSMLoop` — no `verbose` flag currently, so this step uses non-verbose truncation only (no `--verbose` in `--dry-run` path).

6. **`test_ll_loop_commands.py:TestCmdShow`** — Add tests:
   - `test_show_prompt_action_shows_3_lines`: verify long prompt action shows first 3 lines + `...` not the full text
   - `test_show_shell_action_truncated_at_70`: verify shell action still truncates at 70
   - `test_show_verbose_shows_full_action`: `["ll-loop", "show", "my-loop", "--verbose"]` — verify full action text present in output
   - `test_show_verbose_shows_evaluate_prompt`: verify `evaluate.prompt` appears in verbose output

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py:547` — `cmd_show` action display logic (unconditional `state.action[:70]`); also `info.py:551-552` for `evaluate.type`-only display to extend with `evaluate.prompt` in verbose mode; update `cmd_show` signature from `(loop_name, loops_dir, logger)` to `(loop_name, args, loops_dir, logger)` following `cmd_history` pattern
- `scripts/little_loops/cli/loop/__init__.py:164-166` — add `--verbose` / `-v` flag to `show` subparser; update dispatch at `__init__.py:195-196` from `cmd_show(args.loop, loops_dir, logger)` to `cmd_show(args.loop, args, loops_dir, logger)`
- `scripts/little_loops/cli/loop/_helpers.py:110-114` — `print_execution_plan` 70-char truncation (same hardcoded `[:70]`); apply per-type truncation here too for `ll-loop run --dry-run` consistency

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:195-196` — dispatches `cmd_show(args.loop, loops_dir, logger)`; must be updated when signature changes

### Similar Patterns
- `scripts/little_loops/cli/loop/__init__.py:127-131,188` — `history` subparser + `cmd_history(args.loop, args, loops_dir)` is the direct precedent for adding a flag to a `show`-like subparser and forwarding `args`
- `scripts/little_loops/cli/sprint/__init__.py:129-132` + `scripts/little_loops/cli/sprint/manage.py:26-33` — `--verbose/-v` on a subparser with `args.verbose` consumed directly in the handler
- `scripts/little_loops/cli/loop/_helpers.py:221-227` — live-run `action_start` display already branches on `is_prompt` with a 120-char limit (precedent for action_type-aware truncation)

### Tests
- `scripts/tests/test_ll_loop_commands.py:312-388` — `TestCmdShow` class (`test_show_displays_metadata`, `test_show_nonexistent_loop`); add tests for per-type truncation and `--verbose` flag using the same `patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"])` + `capsys` pattern
- `scripts/tests/test_ll_loop_display.py:359-389` — `test_long_action_truncated` covers the dry-run 70-char case; add companion test for prompt-type per-type truncation in `print_execution_plan`

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — documents `ll-loop show` usage; update to mention `--verbose` flag
- `docs/reference/CLI.md` — CLI reference with `loop show` entry; add `--verbose/-v` flag documentation

### Configuration
- N/A

## Scope Boundaries

- **In scope**: Display logic in `ll-loop show` — per-type action text truncation and `--verbose` flag
- **Out of scope**: YAML file editing or reformatting; changes to `ll-loop run` or other subcommands; interactive pager or viewer

## Success Metrics

- `shell` actions truncate at ≤70 chars (no change from current behavior)
- `prompt` actions show first 3 lines or ~200 chars followed by `...`
- `slash_command` actions display in full (typically short)
- `--verbose` flag shows 100% of action text and evaluate prompt with no truncation
- After the fix, a user reviewing `ll-loop show` output can understand the intent of prompt actions without opening the YAML file directly

## Impact

- **Priority**: P3 — minor UX friction; users must open YAML to read prompt actions, but functionality is unaffected
- **Effort**: Medium — arg parser change + display logic branch + verbose flag threading (~30–50 lines across 2 files)
- **Risk**: Low — display-only change; no state mutation, no FSM logic touched
- **Breaking Change**: No

## Labels

`enhancement`, `ll-loop`, `ux`, `cli`

---

**Completed** | Created: 2026-03-04 | Priority: P3

## Resolution

Implemented action-type-aware truncation in `ll-loop show` and `ll-loop run --dry-run`:

- `prompt` actions: show first 3 lines or ~200 chars followed by `...`
- `shell`/`slash_command` actions: unchanged 70-char truncation
- `--verbose/-v` flag: shows full action text and evaluate prompt

Files modified:
- `scripts/little_loops/cli/loop/__init__.py` — added `--verbose/-v` to show subparser; updated dispatch to pass `args`
- `scripts/little_loops/cli/loop/info.py` — updated `cmd_show` signature and display logic
- `scripts/little_loops/cli/loop/_helpers.py` — applied per-type truncation to `print_execution_plan`
- `scripts/tests/test_ll_loop_commands.py` — added 4 new tests in `TestCmdShow`
- `scripts/tests/test_ll_loop_display.py` — added companion dry-run prompt test

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d569869-6d78-45db-ae07-4c05f23b46fe.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4468f93a-677c-4cfe-9445-cc1a243211e3.jsonl`
- `/ll:refine-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e696e00-4453-4689-9b15-ff56c9d9b686.jsonl`
- `/ll:ready-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4bd39923-a65f-4d88-ab73-47f4169b654e.jsonl`
- `/ll:manage-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
