---
discovered_date: 2026-03-04T00:00:00Z
discovered_by: capture-issue
---

# ENH-575: Improve `ll-loop show --verbose` Output Quality, Clarity, and Structure

## Summary

`ll-loop show --verbose` has 10 distinct quality issues across its diagram rendering, metadata display, state/transition formatting, and commands section. These range from an outright rendering bug (label clipping) to UX noise (YAML artifacts, redundant fields, verbose transition labels). Fixing them as a group will make the verbose output significantly cleaner and more useful.

## Current Behavior

Running `ll-loop show <loop> --verbose` produces output with the following problems (all in `scripts/little_loops/cli/loop/info.py`):

1. **Label clipping bug in diagram** (line 432) — `dstart = down_col - len(dlabel) - 1` can go negative when the anchor column is small, silently clipping the leading characters of labels (e.g., `"partial"` renders as `"artial"`).

2. **Redundant "Loop: name" line** (line 523) — The separator header already shows the loop name (`── issue-refinement ────`); printing `Loop: issue-refinement` immediately after is pure noise.

3. **YAML `|` block-scalar artifact** (line 581) — Verbose action display shows `action: |\n  content`, exposing the YAML multi-line indicator to the user. Should show `action:\n  content` or just `action: <cmd>` for single-line shell actions.

4. **Raw `evaluate:` enum string** (line 595) — `evaluate: llm_structured` shows the internal enum value. Should be humanized to e.g. `evaluate: LLM (structured)`.

5. **Same-target transitions not grouped** (lines 617–638) — When `on_failure`, `on_error`, and `on_partial` all target the same state, they each appear on separate lines. Should collapse to `failure/error/partial ──→ fix`.

6. **`on_` prefix noise on transition labels** (lines 618–628) — `on_success`, `on_failure`, `on_error`, `on_partial` should display as `success`, `failure`, `error`, `partial` — the `on_` is a YAML implementation detail.

7. **No summary stats line** (lines 520–548) — No at-a-glance count of states/transitions. A line like `3 states · 5 transitions · fsm paradigm` after the header would help.

8. **INITIAL/TERMINAL not marked in diagram** (lines 87–175) — These markers only appear in the States section text. The diagram itself has no visual indicator for the entry point or terminal state.

9. **Deep indentation for verbose prompt content** (lines 598–606) — Prompt content inside an evaluate block is indented 8 spaces, making long prompts hard to read. A `│` vertical-gutter at 4 spaces would improve legibility.

10. **`ll-loop stop` missing from Commands section** (lines 641–651) — The commands table at the bottom omits `ll-loop stop <name>`, which is a commonly needed command.

## Expected Behavior

After fixing:

1. Diagram labels render completely (no clipping).
2. The `Loop: <name>` line is removed (name is already in the separator).
3. Action blocks show `action:` without the `|` YAML artifact.
4. Evaluate type is humanized (`LLM (structured)` etc.).
5. Transitions that share the same target are grouped on one line.
6. Transition labels drop the `on_` prefix.
7. A summary stats line appears between the header and description.
8. The diagram visually marks the initial and terminal states.
9. Prompt content uses a `│` gutter at 4-space indent.
10. `ll-loop stop <name>` appears in the Commands section.

## Motivation

The verbose output is the primary way users inspect loop structure before running or debugging. Rendering bugs reduce trust in the tool. YAML artifacts make it feel like a debug dump rather than a polished CLI. Grouping improvements reduce visual noise and speed up comprehension. Collectively these are high-leverage, low-risk polish items.

## Proposed Solution

All changes are localized to `scripts/little_loops/cli/loop/info.py` in two functions:
- `cmd_show()` — handles items 2, 3, 4, 5, 6, 7, 9, 10
- `_render_2d_diagram()` and `_render_fsm_diagram()` — handles items 1, 8

**Item 1 fix**: In `_render_2d_diagram()`, clamp `dstart` to prevent negative values:
```python
dstart = max(0, down_col - len(dlabel) - 1)
```

**Items 5+6**: Add a helper function in `cmd_show()` that groups transitions by target state and strips the `on_` prefix before rendering.

**Item 8**: In `_render_2d_diagram()`, prefix the initial state box label with `→ ` (adding 2 chars to box width calculation), and append a `◉` or double-line annotation for terminal states.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — all changes

### Dependent Files (Callers/Importers)
- `scripts/tests/test_ll_loop_display.py` — primary display test file; has 54 assertions against verbose/transition output (confirmed)
- `scripts/tests/test_ll_loop_commands.py` — 35 assertions matching verbose/on_failure/Loop: patterns (confirmed)

### Similar Patterns
- `scripts/little_loops/cli/sprint/show.py` — similar show command, check for consistency

### Tests
- `scripts/tests/test_ll_loop_display.py` — update output assertions for all 10 items
- `scripts/tests/test_ll_loop_commands.py` — update transition label assertions

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Fix the `dstart` label-clipping bug (item 1) — isolated, low risk
2. Strip `on_` prefix from all transition label strings (item 6)
3. Group same-target transitions into single line (item 5)
4. Remove the redundant `Loop: <name>` metadata line (item 2)
5. Remove `|` from verbose action display (item 3)
6. Humanize evaluate type strings (item 4)
7. Add summary stats line to header block (item 7)
8. Annotate INITIAL/TERMINAL in diagram (item 8)
9. Improve verbose prompt indentation with `│` gutter (item 9)
10. Add `ll-loop stop` to Commands table (item 10)
11. Run tests and update any output snapshots

## Scope Boundaries

Out of scope:
- Loop execution, FSM logic, config parsing, or any non-display behavior
- Other CLI commands (`ll-loop run`, `ll-loop status`, etc.)
- Structured output format changes (e.g., `--json` flag)
- Changes to the non-verbose `ll-loop show` default output
- Any test infrastructure changes beyond updating existing output assertions

## Success Metrics

- All 10 enumerated display issues are resolved (each item in Current Behavior has a matching fix)
- Existing test suite passes with updated output snapshots — no new test failures introduced
- No regressions in `ll-loop show` (non-verbose) behavior

## Impact

- **Priority**: P3 — Polish; no blocking issues
- **Effort**: Small — all changes in one file, no architectural work
- **Risk**: Low — purely display logic, no state mutations
- **Breaking Change**: No (output format change only; no structured consumers)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `ux`, `captured`

## Status

**Open** | Created: 2026-03-04 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45f5e92b-9ceb-436a-99d3-42f60acd8906.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/476e3b5a-af7b-4364-a392-08cb347c2f45.jsonl`
