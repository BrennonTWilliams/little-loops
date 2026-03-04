---
discovered_commit: 45967476d8f33ab60834266502dbdba439822661
discovered_branch: main
discovered_date: 2026-03-04T20:10:46Z
discovered_by: capture-issue
---

# ENH-573: Improve `ll-loop show --verbose` Output Quality and Layout

## Summary

`ll-loop show <loop> --verbose` has two rendering bugs (action/description indentation) and several UX problems: the FSM diagram is buried at the end, states have no visual separation, the action `type` appears after the action block rather than inline with the state header, and the run command section shows only a single command. Together these make the output harder to read and navigate than it should be.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 503–631
- **Anchor**: `in function cmd_show()`

## Current Behavior

Running `ll-loop show issue-refinement --verbose` produces:

1. **Bug — action indentation**: Only the first line of a multi-line action gets the 6-space indent. Continuation lines start at column 0:
   ```
       action: |
         Run `ll-issues refine-status` to see the current refinement state of all
   active issues. Thresholds: readiness=85, outcome=70.
   ```
   Root cause: `print(f"    action: |\n      {state.action.strip()}")` — the `"      "` prefix applies only to the first line.

2. **Bug — description indentation**: Multi-line descriptions wrap with continuation lines at column 0 instead of indented under the description value.
   Root cause: `print(f"Description: {description}")` dumps a raw multiline string.

3. **Layout — diagram at end**: The FSM diagram appears after all state detail blocks. Users must scroll to the bottom to get a structural overview before reading state details.

4. **Layout — no separation between states**: State blocks run together with no blank lines, making it hard to visually scan where one state ends and the next begins.

5. **Layout — `type:` after action block**: The action type (`type: shell` / `type: prompt`) is printed after the action content, so you don't know what kind of action you're reading until after you've read it.

6. **Layout — evaluate transitions visually ambiguous**: The `on_success/on_failure/on_error/on_partial` arrows appear at the same indentation as the evaluate sub-block, making it unclear whether transitions are inside or outside the evaluate config.

7. **UX — thin Run command section**: Only `ll-loop run <name>` is shown. Other useful commands (`test`, `status`, `history`) are not surfaced.

8. **UX — no metadata section header**: The output starts directly with field values (`Loop: ...`) with no visual frame or section separator.

## Expected Behavior

```
── issue-refinement ──────────────────────────────────────
Loop:          issue-refinement
Paradigm:      fsm
Max iter:      100
On handoff:    spawn
Source:        .loops/issue-refinement.yaml

Description:
  Progressively refine all active issues to ensure complete coverage.
  For each incomplete issue (starting from highest ID), runs all missing
  refinement commands, scores with confidence-check, and iterates with
  refine-issue until both confidence scores meet configured thresholds.
  Repeats until all active issues are fully refined.

Diagram:
  ┌──────────┐             ┌──────┐
  │ evaluate │───success──▶│ done │
  └──────────┘             └──────┘
       │ ▲
  fail │ │ next
       ▼ │
     ┌─────┐
     │ fix │
     └─────┘

States:

  [evaluate] [INITIAL] (shell)
    action: |
      ll-issues refine-status
    evaluate: llm_structured
      prompt: |
        Examine this ll-issues refine-status table output.
        ...
    Transitions:
      on_success ──→ done
      on_failure ──→ fix
      on_error   ──→ fix
      on_partial ──→ fix

  [fix] (prompt)
    action: |
      Run `ll-issues refine-status` to see the current refinement state of all
      active issues. Thresholds: readiness=85, outcome=70.
      ...
    Transitions:
      next ──→ evaluate

  [done] [TERMINAL]

Commands:
  ll-loop run issue-refinement          # run
  ll-loop test issue-refinement         # single test iteration
  ll-loop status issue-refinement       # check if running
  ll-loop history issue-refinement      # execution history
```

## Motivation

`ll-loop show --verbose` is the primary way to inspect a loop config before running it. The indentation bugs make action content unreadable for multi-line actions (i.e., all prompt-type states). Moving the diagram up gives immediate structural context. The other layout changes reduce visual noise and make state blocks scannable. This matters most for complex loops where states have long prompt actions.

## Success Metrics

- All 8 items in `## Current Behavior` resolved (verifiable against the expected output mock-up in `## Expected Behavior`)
- Multi-line action content: all continuation lines indented correctly (not at column 0)
- Multi-line description content: all continuation lines indented under the description value
- FSM diagram appears before the `States:` block in `--verbose` output
- State header line includes action type badge (e.g., `[evaluate] [INITIAL] (shell)`)
- `Commands:` section lists `run`, `test`, `status`, and `history` sub-commands

## Proposed Solution

Fix in `cmd_show()` in `info.py`:

1. **Fix action indent**: Replace single-line format with joined multiline:
   ```python
   indented = "\n      ".join(state.action.strip().splitlines())
   print(f"    action: |\n      {indented}")
   ```

2. **Fix description indent**: Wrap continuation lines:
   ```python
   desc_lines = description.splitlines()
   print(f"Description:")
   for line in desc_lines:
       print(f"  {line}")
   ```

3. **Move diagram before states**: Print the `Diagram:` section between the metadata block and the `States:` section.

4. **Blank line between states**: Add `print()` at the top of the state-rendering loop (after the first state).

5. **Type badge on state header**: Include action type in the header line:
   ```python
   type_badge = f" ({state.action_type})" if state.action_type else ""
   print(f"  [{name}]{initial_marker}{terminal_marker}{type_badge}")
   ```
   Then suppress the standalone `type:` line.

6. **Transitions sub-header**: Group all transition arrows under a `    Transitions:` label, each at 6-space indent.

7. **Enriched Commands section**: Replace single run command with a block covering `run`, `test`, `status`, `history`.

8. **Metadata header separator** (optional): Print a thin `── {loop_name} ` separator before the metadata fields.

## Scope Boundaries

- Only `cmd_show()` and its output rendering; no changes to FSM schema, executor, or other commands
- Does not affect non-verbose output (same truncation behavior without `--verbose`)
- Does not change `--dry-run` (`print_execution_plan()` in `_helpers.py`) — separate function

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_show()`

### Dependent Files
- `scripts/little_loops/cli/loop/__init__.py` — routes `show` subcommand; no changes needed

### Similar Patterns
- N/A — `cmd_show()` is the only verbose multi-section output renderer in the loop CLI; other commands (`cmd_list()`, `cmd_status()`) use single-line tabular output

### Tests
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdShow` class (if it exists) or new test:
  - Verify multiline action indentation (all lines indented, not just first)
  - Verify diagram appears before states section in output
  - Verify type badge appears on state header line

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Fix action multiline indentation (bug fix — `"\n      ".join(...)`)
2. Fix description multiline indentation (bug fix)
3. Move `Diagram:` section before `States:` section
4. Add blank line between state blocks
5. Inline action type as badge on state header; remove standalone `type:` line
6. Add `Transitions:` sub-header grouping for transition arrows
7. Expand `Run command:` → `Commands:` with test/status/history
8. (Optional) Add metadata section separator header

## Impact

- **Priority**: P3 — UX quality; bugs affect readability of all multi-line prompt states
- **Effort**: Small — All changes are in a single function; no schema or data changes
- **Risk**: Low — Output-only change; no behavioral impact on loop execution
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | CLI architecture and command structure |
| `docs/reference/API.md` | FSMLoop schema fields referenced in output |

## Labels

`enhancement`, `ll-loop`, `ux`, `cli`, `output-formatting`

## Session Log

- `/ll:capture-issue` — 2026-03-04T20:10:46Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffa88660-2b5b-4a83-a475-9f7a9def1102.jsonl`
- `/ll:format-issue` — 2026-03-04T20:33:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fac97403-79d6-481f-b8da-20f7f34b52d4.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P3
