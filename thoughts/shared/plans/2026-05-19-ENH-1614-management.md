# ENH-1614: Improve `ll-loop list` output readability

## Approach

Six targeted changes to `cmd_list()` in `scripts/little_loops/cli/loop/info.py`, plus multiline ellipsis in `_load_loop_meta()`, plus test/documentation updates. Follows reference patterns already in the codebase: `_print_state_overview_table()` for column alignment, `_format_history_event()` for label badges, `list_cmd.py` for grouped separators.

## Files to Modify

1. `scripts/little_loops/cli/loop/info.py` — `cmd_list()` (lines 176-198), `_load_loop_meta()` (line 37)
2. `scripts/tests/test_ll_loop_commands.py` — add new tests
3. `docs/reference/CLI.md` — update `ll-loop list` section description

## Phase 1: Compute fixed-width name column

- Compute `max_name_len = max(len(lp["name"]) for lp in all_loops)` before the rendering loop
- Name column width = `max_name_len + 2` (padding)
- Use ANSI-aware padding: import `_strip_ansi` from `show.py` or inline a local helper → pad to width accounting for ANSI escapes
- Apply distinct colors: `"36"` (cyan, no bold) for built-in loops, `"36;1"` (bold cyan) for project loops

## Phase 2: Add multiline description ellipsis in `_load_loop_meta()`

- After `desc_raw.splitlines()[0]`, check if `len(splitlines) > 1` and append `…` if so

## Phase 3: Terminal-width-aware description truncation

- Get `tw = terminal_width()`
- Build suffix string first: labels + `[built-in]` tag
- Compute `avail = tw - 2 (indent) - name_col - len(suffix_with_spaces)`
- Use existing `_truncate(desc, max(avail, 20))`

## Phase 4: Add label badge rendering

- Build `labels_str = "  " + " ".join(colorize(f"[{l}]", "2") for l in lp["labels"])` if labels exist
- Combine with `[built-in]` tag in suffix, ordered: labels first, then `[built-in]`

## Phase 5: Add blank line between category groups

- Track `first_cat` boolean; print blank line before category header when not first

## Phase 6: Verify existing tests pass

```bash
python -m pytest scripts/tests/test_ll_loop_commands.py scripts/tests/test_builtin_loops.py scripts/tests/test_ll_loop_integration.py scripts/tests/test_cli_e2e.py scripts/tests/test_cli.py scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_ll_loop_parsing.py scripts/tests/test_cli_output.py -v
```

## Phase 7: Write new tests (TDD Red)

Tests for:
- Column alignment: descriptions start at same horizontal position
- Description truncation with `…` at 80/120 cols
- Multiline description `…` in `_load_loop_meta()`
- Label badge rendering `[experimental]`
- Different ANSI codes for built-in vs project names
- `[built-in]` tag on same line at 80 cols
- `_truncate()` unit test

## Phase 8: Update docs

- `docs/reference/CLI.md`: update `ll-loop list` section to describe new format
