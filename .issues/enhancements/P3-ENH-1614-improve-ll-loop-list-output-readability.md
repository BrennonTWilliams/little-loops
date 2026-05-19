---
discovered_date: '2026-05-19'
discovered_by: capture-issue
captured_at: '2026-05-19T21:17:53Z'
status: done
completed_at: 2026-05-19T22:23:07Z
decision_needed: false
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1614: Improve `ll-loop list` output readability with column alignment, truncation, and label badges

## Summary

`ll-loop list` displays available FSM loops grouped by category, but the output has several readability issues that make it harder to scan — especially with 50+ built-in loops. This enhancement adds fixed-width column alignment, terminal-width-aware description truncation with ellipsis, label badge display, visual separators between categories, distinct coloring for built-in vs project loops, and tag position guarding to prevent `[built-in]` from wrapping.

## Current Behavior

```
apo (3):
  apo-contrastive  Contrastive prompt optimization (APO technique): generates multiple prompt variants  [built-in]
  apo-feedback-refinement  Feedback-driven prompt refinement (APO technique): reads the target prompt,  [built-in]
  apo-opro  OPRO-style prompt optimization (APO technique): maintains a running history of  [built-in]
```

Issues:
1. **Mid-sentence truncation**: `splitlines()[0]` cuts multiline descriptions at the first newline with no ellipsis — output ends with dangling commas/words ("reads the target prompt,").
2. **No terminal-width-aware truncation**: Single-line descriptions exceeding terminal width wrap messily rather than truncating with `…`.
3. **No column alignment**: Names are variable-width (9–30+ chars), so descriptions start at different horizontal positions.
4. **Label badges hidden**: Labels exist in the data and are filterable via `--label`, but never displayed.
5. **Category headers lack visual weight**: Just `category (N):` in bold with no separator between groups.
6. **Dense within groups**: No blank line between entries in large (11-item) categories.
7. **`[built-in]` tag can wrap**: Since the tag is appended at end-of-line with no width guard, long descriptions push it to a wrapped line.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Rendering code**: `cmd_list()` text display path at `info.py:176-198` — `colorize(lp["name"], "36;1")` for names, `colorize(lp['description'], '2')` for descriptions, `colorize('[built-in]', '2')` for tag. No terminal-width calculation, no column alignment, no label rendering.
- **Metadata truncation**: `_load_loop_meta()` at `info.py:29-42` — line 37: `desc = desc_raw.splitlines()[0]` discards all lines after the first with no ellipsis. Labels are loaded at line 39 (`spec.get("labels", [])`) but the rendering code at lines 189-197 never references `lp["labels"]`.
- **Terminal width unused**: `terminal_width` is imported at `info.py:23` but never called within `cmd_list()` text display. It IS used in `cmd_history()` (line 487), `cmd_show()` (line 681), and `_print_state_overview_table()` (line 572) in the same file.
- **Color handling**: `_USE_COLOR` boolean at `output.py:31` gates `colorize()` — when `NO_COLOR` is set or stdout is non-TTY, all ANSI escapes vanish and text is structurally identical.
- **JSON path unaffected**: JSON output at `info.py:161-174` takes a completely separate code path that builds a dict and calls `print_json()`. The text rendering changes do not intersect this path.

## Expected Behavior

Columns aligned, descriptions truncated with `…` at terminal width, labels displayed, categories visually separated, and `[built-in]` tag always on the same line:

```
apo (3):
  apo-contrastive             Contrastive prompt optimization (APO technique): generates multiple…  [experimental]  [built-in]
  apo-feedback-refinement     Feedback-driven prompt refinement (APO technique): reads the targ…  [experimental]  [built-in]
  apo-opro                    OPRO-style prompt optimization (APO technique): maintains a runni…  [experimental]  [built-in]
```

## Motivation

`ll-loop list` is the primary discovery command for the loop system. With 50+ built-in loops across 10+ categories, users need to quickly scan and identify relevant loops. Poor alignment and abrupt truncation force re-reading and slow down loop selection. This enhancement makes the output scannable at a glance — consistent with the visual quality standard set by `ll-issues list`.

## Proposed Solution

Modify `cmd_list()` in `scripts/little_loops/cli/loop/info.py` with six targeted changes:

**1. Fixed-width name column**
- Compute `max_name_len` across all displayed loops
- Pad names to consistent width so descriptions align vertically

**2. Description truncation with ellipsis**
- Compute available width: `terminal_width - indent - name_col - gaps - tag_width`
- Truncate description to fit, appending `…` when cut
- Also append `…` when a multiline description has content beyond the first line (signals "more available")

**3. Add label badges**
- Render labels as dimmed, bracketed tags between description and `[built-in]`
- E.g., `[experimental]` `[slow]` in dim style

**4. Visual separators between categories**
- Print a blank line before each category header (after the first)

**5. Distinct color for built-in names**
- Project loops: keep cyan bold (`36;1`)
- Built-in loops: use a slightly dimmer cyan (`36`) so project overrides stand out

**6. Guard `[built-in]` tag position**
- Reserve the last ~13 chars for the tag; truncate description before it
- Prevents the tag from wrapping to a new line

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Existing `_truncate()` reusable**: `info.py:204-210` already defines `_truncate(text, max_len)` that truncates with `…` ellipsis. Use this instead of inline slicing.
- **Existing ANSI-aware `_ljust()`**: `show.py:281-288` defines `_ljust(text, width)` that pads to a fixed width accounting for invisible ANSI escape codes via `_strip_ansi()`. This is needed for fixed-width name columns when names are colorized (the escape codes add invisible bytes).
- **Reference pattern for column alignment**: `_print_state_overview_table()` at `info.py:572-628` (same file) computes per-column max widths from data, splits remaining terminal width between dynamic columns, and truncates with `…`. Follow this pattern for the name column.
- **Reference pattern for grouped output**: `ll-issues list` in `list_cmd.py:134-156` groups by type, colorizes headers with `TYPE_COLOR.get(prefix, '0');1`, appends status tags conditionally, and adds blank lines between groups.
- **Label badge convention**: `_format_history_event()` at `info.py:264` uses `colorize(f"[{kind_label}]", "2")` for inline `[kind]` badges — follow this same dim-bracketed pattern for loop labels.
- **`terminal_width()` canonical source**: `output.py:16-18` — `shutil.get_terminal_size((default, 24)).columns`. Already imported in `info.py:23`. All width-aware CLIs in the codebase use this single function.
- **Test pattern for terminal width**: `test_cli_output.py:31-41` patches `shutil.get_terminal_size` to return a specific column count. Use this pattern to test truncation at various widths.

### Pseudocode
max_name_len = max(len(lp["name"]) for lp in all_loops)
name_col = max_name_len + 2  # padding
tag_width = 13  # "  [built-in]"
tw = terminal_width()

for cat in sorted_cats:
    group = buckets[cat]
    if not first_cat:
        print()  # blank between groups
    first_cat = False
    print(colorize(f"{cat} ({len(group)}):", "1"))

    for lp in group:
        name_padded = lp["name"].ljust(name_col)
        name_color = "36" if lp["builtin"] else "36;1"
        name_str = colorize(name_padded, name_color)

        # Build suffix (labels + builtin tag)
        suffix = ""
        if lp["labels"]:
            suffix += "  " + " ".join(colorize(f"[{l}]", "2") for l in lp["labels"])
        if lp["builtin"]:
            suffix += colorize("  [built-in]", "2")

        avail = tw - 2 - name_col - len(suffix) + 2
        desc = lp["description"]
        if desc and len(desc) > avail:
            desc = desc[:avail - 1] + "…"
        desc_str = f"  {colorize(desc, '2')}" if desc else ""

        print(f"  {name_str}{desc_str}{suffix}")
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_list()` at line 45 (text display path: lines 176-198), `_load_loop_meta()` at line 29

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — imports and calls `cmd_list()` at line 421; registers `--label` flag at line 204, `--category` at line 197

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/logs.py` — imports `_format_history_event` from `info.py` (line 13-15, with comment noting cross-module coupling). Unchanged by ENH-1614 (we don't modify `_format_history_event`), but noted as a consumer of `info.py` symbols.
- `skills/review-loop/SKILL.md` — Step 0 "Resolve Loop Name" (lines 43-47) runs `ll-loop list` with no `--json` and parses the human-readable text output to extract loop names and descriptions. Truncated descriptions (with `…`) and new label badges will be new tokens in the parse stream.

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py:134-156` — `cmd_list()` for issues, reference for grouped output with colorized headers and blank-line separators
- `scripts/little_loops/cli/loop/info.py:572-628` — `_print_state_overview_table()`, reference for dynamic column widths computed from data, truncation with `…`
- `scripts/little_loops/cli/issues/refine_status.py:151-165` — `_truncate()` and `_col()`/`_rcol()` for fixed-width columns with ellipsis
- `scripts/little_loops/cli/issues/show.py:281-288` — `_ljust()` and `_strip_ansi()` for ANSI-aware padding
- `scripts/little_loops/cli/loop/info.py:264` — `_format_history_event()` `[kind]` badge pattern: `colorize(f"[{kind_label}]", "2")`

### Reusable Code Already in `info.py`
- `_truncate(text, max_len)` at line 204 — truncates with `…` ellipsis, already handles `max_len < 1` edge case
- `terminal_width()` import at line 23 (from `output.py:16`) — canonical terminal width source, already available

### Tests
- `scripts/tests/test_ll_loop_commands.py:189-213` — `test_list_shows_description` — asserts description text appears in output
- `scripts/tests/test_builtin_loops.py:208-223` — `test_list_shows_builtin_tag` — asserts `[built-in]` in output
- `scripts/tests/test_builtin_loops.py:225-247` — `test_list_hides_overridden_builtin` — project loop overrides hide built-in tag
- `scripts/tests/test_ll_loop_commands.py:381-437` — category and label filter tests
- `scripts/tests/test_cli_output.py:31-41` — terminal-width-patching test pattern to follow for width-dependent assertions

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_integration.py:242-383` — `TestLoopIntegration` class: 5 tests exercise `cmd_list` via `main_loop()` entry point (empty dir, multiple loops, missing dir, `--running`, `--running` empty)
- `scripts/tests/test_cli_e2e.py:418-484` — `TestLoopExecutionWorkflow` class: 2 tests run `ll-loop list` end-to-end
- `scripts/tests/test_cli.py:718-745` — `TestMainLoopIntegration` class: 2 tests exercise list/list `--running` via `main_loop`
- `scripts/tests/test_cli_loop_lifecycle.py:1855-1898` — `TestCmdListMultiInstance` class: tests `--running` path deduplication
- `scripts/tests/test_ll_loop_parsing.py:407-424` — `TestLoopJsonShortForm.test_list_json_short_form`: patches `cmd_list`, tests `-j` flag parsing
- `scripts/tests/test_refine_status.py:837-860,1619-1643` — width-sensitive table tests: reference pattern for asserting truncation at specific terminal widths
- `scripts/tests/test_cli_output.py:269-302` — `TestIssueListNoColor`: reference pattern for NO_COLOR regression testing
- `scripts/tests/test_issues_cli.py:85-176` — `TestIssueList`: reference pattern for grouped output format assertions

_Test gaps identified by `/ll:wire-issue` (new tests to write):_
- Column alignment: assert descriptions start at same horizontal position across lines
- Description truncation at 80/120/200 cols: assert `…` presence/absence
- Multiline description ellipsis in `_load_loop_meta()`: assert `…` appended when second line exists
- Label badge rendering: assert `[experimental]` appears in output for labeled loops
- Blank lines between categories: assert blank line count between category headers
- Distinct built-in vs project name color: assert `\033[36m` (no bold) for built-in, `\033[36;1m` (bold) for project loops
- NO_COLOR regression for loop `cmd_list()`: assert no ANSI escapes when color suppressed
- `[built-in]` tag never wraps: at 80 cols with long description, tag stays on same line as name
- `_truncate()` unit test: directly test `_truncate("hello", 3)` → `"he…"`, `_truncate("hi", 5)` → `"hi"`, `_truncate("text", 0)` → `""`

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:405-415` — `#### ll-loop list` section: description says output is "grouped by category" — now also column-aligned, truncated with `…`, with label badges. Update to reflect new format.
- `docs/reference/OUTPUT_STYLING.md:236-248` — documents `_print_state_overview_table()` in `info.py` but has no section for loop list format. Opportunity to add documentation for the new format (follows same terminal-width-aware, ANSI-aware patterns already documented).

### Configuration
- N/A

## Implementation Steps

1. **Compute `max_name_len` for fixed-width name column** (`info.py` text display path, ~line 185)
   - Iterate `all_loops` to find `max(len(lp["name"]) for lp in all_loops)` before the rendering loop
   - Pad names with `name.ljust(name_col)` in the name string. For ANSI-aware padding when color is on, follow `show.py:281` `_ljust()` pattern (strip ANSI before computing pad width, then append spaces)

2. **Implement terminal-width-aware description truncation** (`info.py` text display path)
   - Call `terminal_width()` to get `tw`
   - Compute `avail = tw - indent(2) - name_col - 2 - len(suffix_str) + 2` (extra `+2` because the name has trailing spaces that act as gap)
   - Use existing `_truncate()` at `info.py:204` instead of inline slicing: `_truncate(desc, max(avail, 20))`
   - Also append `…` when `desc_raw` has content beyond `splitlines()[0]` (in `_load_loop_meta()`) — signals "more available" for multiline descriptions

3. **Add label badge rendering** (between description and `[built-in]` tag)
   - Follow the `_format_history_event()` pattern at `info.py:264`: `colorize(f"[{l}]", "2")` for each label
   - Build a suffix string: `labels_str = "  " + " ".join(colorize(f"[{l}]", "2") for l in lp["labels"])` if labels exist
   - Combine with the `[built-in]` tag in the suffix, ordered: labels first, then `[built-in]`

4. **Add blank line separator between category groups** (before each header after the first)
   - Track `first_cat` boolean; print blank line before `colorize(...)` when not first
   - Follow `list_cmd.py:144-155` pattern (blank line between groups, but `list_cmd.py` places it after each group in a single `"\n".join(lines)`)

5. **Apply distinct color to built-in vs project loop names**
   - Project loops: keep `"36;1"` (bold cyan) — they stand out as user-created
   - Built-in loops: use `"36"` (cyan, no bold) — slightly dimmer so project overrides have visual prominence
   - `if lp["builtin"]: colorize(name, "36") else: colorize(name, "36;1")`

6. **Guard `[built-in]` tag position** (reserve trailing chars during truncation)
   - The `avail` calculation in step 2 must account for `suffix_str` width (labels + `[built-in]` tag)
   - Suffix width includes: `len("  [built-in]")` + sum of label badge widths
   - When `_truncate()` respects `avail`, the suffix always fits on the same line as the description

7. **Run `ll-loop list` with various terminal widths, categories, and `--label` filters to verify**
   - Test at 80, 120, 200 columns by setting `COLUMNS` env var or using `stty columns`
   - Verify `ll-loop list --category apo --label experimental` works correctly

8. **Verify `NO_COLOR=1 ll-loop list` and `ll-loop list -j` still work correctly**
   - `NO_COLOR=1`: names still align correctly (ANSI-aware padding handles this), output is readable
   - `-j`: JSON output at `info.py:161-174` is a separate code path — unchanged by text rendering modifications

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Verify all existing tests still pass** — 29 tests across 8 files exercise `cmd_list()` or `ll-loop list`. All use substring-in-output assertions that tolerate whitespace/alignment changes. Run full loop test suite:
   ```bash
   python -m pytest scripts/tests/test_ll_loop_commands.py scripts/tests/test_builtin_loops.py scripts/tests/test_ll_loop_integration.py scripts/tests/test_cli_e2e.py scripts/tests/test_cli.py scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_ll_loop_parsing.py scripts/tests/test_cli_output.py -v
   ```

10. **Update `docs/reference/CLI.md` `ll-loop list` section** (lines 405-415) — description currently says output is "grouped by category." Add mention of column alignment, description truncation with `…`, label badges, distinct built-in vs project name colors, and `[built-in]` tag position guarding.

11. **Review `skills/review-loop/SKILL.md` Step 0** (lines 43-47) — this skill parses human-readable `ll-loop list` output to extract names/descriptions for `AskUserQuestion`. Truncated descriptions (with `…`) and label badges are new tokens. Add a note that descriptions may be truncated at narrow terminal widths, and that labels appear as `[label]` badges between the description and `[built-in]` tag.

12. **Write new tests for the test gaps** identified above (see `### Tests` section, at minimum: column alignment, terminal-width truncation at 80/120 cols, label badge rendering, `[built-in]` tag non-wrapping at 80 cols, and `_truncate()` unit test). Follow patterns from `test_refine_status.py` (width-sensitive formatting) and `test_ll_loop_commands.py` (direct `cmd_list()` invocation).

## Impact

- **Priority**: P3 — UX improvement, not functional
- **Effort**: Small — single function, additive changes within `cmd_list()`
- **Risk**: Low — display-only changes; existing `NO_COLOR` and non-TTY guards handle graceful degradation; JSON output path unchanged
- **Breaking Change**: No

## Scope Boundaries

- Do NOT change `ll-loop show`, `ll-loop history`, or diagram rendering
- Do NOT change the JSON output path (`-j` / `--json`)
- Do NOT add new CLI flags — this is purely about the default text output format
- Do NOT restructure the data loading pipeline — only the rendering in `cmd_list()`

## Success Metrics

- Column alignment verified by visual inspection at 80-, 120-, and 200-column terminal widths
- No `[built-in]` tag wraps to a second line at 80 columns
- Label badges appear when loops have labels
- Category groups are visually separated by blank lines
- All existing `ll-loop list` tests pass
- `ll-loop list -j` output unchanged (JSON regression)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `ux`, `ll-loop`

## Session Log
- `/ll:ready-issue` - 2026-05-19T22:01:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f6bc2bff-66a9-49f5-885d-d3b4f5d2a679.jsonl`
- `/ll:refine-issue` - 2026-05-19T21:39:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4c3ca7d-58d8-4cc6-9bb3-f91efba0dde0.jsonl`
- `/ll:format-issue` - 2026-05-19T21:22:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/451b846b-4c03-44f6-8253-e177eee3b4d9.jsonl`
- `/ll:capture-issue` - 2026-05-19T21:17:53Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f32992af-af95-42bd-866d-9b7e07b5918b.jsonl`
- `/ll:manage-issue` - 2026-05-19T22:23:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a9aa1840-11ba-419f-8a25-b5d4e74df8fd.jsonl`
- `/ll:wire-issue` - 2026-05-19T22:15:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9205bee-2e8b-48b5-b0d1-2ba2fe9559f9.jsonl`
- `/ll:confidence-check` - 2026-05-19T22:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11b10f14-390f-4b6c-83ed-16b4834b7b71.jsonl`

---

## Status

**Open** | Created: 2026-05-19 | Priority: P3
