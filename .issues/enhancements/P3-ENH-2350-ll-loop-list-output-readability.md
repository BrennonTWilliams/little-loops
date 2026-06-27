---
id: ENH-2350
title: Improve ll-loop list output readability and formatting
type: ENH
status: open
priority: P3
captured_at: "2026-06-27T21:43:31Z"
discovered_date: 2026-06-27
discovered_by: capture-issue
labels: [cli, dx, output-formatting]
---

# ENH-2350: Improve ll-loop list output readability and formatting

## Summary

The human-readable output of `ll-loop list` is hard to scan: nearly every
loop description is truncated to a ~20-char stub (a wall of ellipses), the
`[built-in]` tag is stamped on ~80 of 81 rows as pure noise, and a single
outlier loop name dictates the column width for the whole table. With 81
loops across 21 categories, the list fails at its core job — letting a user
tell loops apart by their descriptions.

## Current Behavior

Rendered by `cmd_list` in `scripts/little_loops/cli/loop/info.py:243-313`.

Example rows (80-col terminal):

```
api-adoption (2):
  learning-tests-audit                          Scans the Learning …  [built-in]
  migrate-sdk-version                           Re-proves stale lea…  [built-in]
```

Concrete defects:

1. **One outlier name crushes every description.** The name column is padded
   to the global longest name (`info.py:257`):
   ```python
   max_name_len = max((len(lp["name"]) for lp in all_loops), default=0)
   name_col = max_name_len + 2
   ```
   In the default listing the longest name is
   `tmp/harness-plan-research-implement-report` (42 chars — an *example* loop
   in `tmp/`). The next-longest real loop is `interactive-component-generator`
   at 31. That outlier inflates `name_col` to 44, collapsing the description
   budget at 80 cols to:
   `80 − 2(indent) − 44(name) − 2(gap) − 12("  [built-in]") = 20 chars`.
   Result: almost every description truncates to a useless stub.

2. **`[built-in]` repeated on ~80/81 rows is noise** (`info.py:278`). Nearly
   every loop is built-in, so the tag stamps almost every row and steals 12
   columns each. The signal is inverted — the *rare* project/local override is
   what deserves a marker.

3. **Label overflow on `hitl-*` rows.** `hitl-compare`/`hitl-md` render
   `[hitl] [comparison] [html] [interactive] [built-in]` (five tags,
   `info.py:275-277`), blowing past the line and pushing the description off
   entirely.

4. **Low-contrast category headers** (`info.py:267`): lowercase kebab-case,
   only a blank line between 21 groups — nothing to anchor the eye while
   scrolling.

5. **No summary header.** A reader hits 81 rows before learning there are 81;
   only the footer orients (`info.py:307`).

6. **Inconsistent ellipsis spacing** from `_truncate` (`info.py:319`):
   `"Scans the Learning …"` (space) vs `"Generator-evaluator…"` (glued).

## Expected Behavior

Descriptions get a real budget (~50 cols at 80-wide), built-in noise is gone,
categories are scannable, and a count orients the reader up front. Proposed
80-col mock:

```
  81 loops · 21 categories · 1 project, 80 built-in

  ▸ apo  (6)
      apo-beam            Beam search prompt optimizer over a population of …
      apo-contrastive     Contrastive prompt optimization from win/lose pairs
      rn-plan-apo         Plan-quality gradient descent via APO scoring

  ▸ harness  (19)
      hitl-compare    ●   Human-in-the-loop comparison of N variants  [+3 labels]

  ● = project loop (overrides built-in)
  Hidden: 15 internal (--internal), 4 example (--examples) · all with --all
  Not sure which loop? ll-loop run loop-router --input goal="<what you want>"
```

## Motivation

`ll-loop list` is the primary discovery surface for 81 built-in loops. When
every description is an ellipsis stub, users can't distinguish loops and fall
back to reading YAML or guessing — defeating the list. The P0 fix is ~3 lines
and improves every row at once, with near-zero risk.

## Proposed Solution

Prioritized; land P0+P1 first (substantive readability), P2/P3 as polish.

- **P0 — cap the name column.** Replace the global-max padding with a sane cap,
  e.g. `name_col = min(max_name_len, 32) + 2`, and truncate the rare over-long
  name. Roughly doubles the description budget for all rows.
- **P1 — drop per-row `[built-in]`.** Color already distinguishes them
  (project `36;1` bold-cyan vs built-in `36` dim-cyan). Mark only the rare
  project loop (e.g. `●` / `[local]`) and explain the convention once in the
  footer.
- **P1 — cap displayed labels** (e.g. first 2 + `+N`), or move labels below the
  description / behind `--label`/verbose, to stop `hitl-*` overflow.
- **P2 — style category headers** (uppercase/title-case + `▸`/rule). The
  `BOX_H` box-drawing constants in `scripts/little_loops/cli/output.py` exist
  for a lightweight underline.
- **P2 — add a summary header**: `N loops · M categories` (+ active filters).
- **P3 — normalize ellipsis**: strip trailing whitespace before appending `…`
  in `_truncate`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**P0 — name column cap** (`info.py:257-258`):
```python
# Current (inflates to 44 for a tmp/ outlier):
max_name_len = max((len(lp["name"]) for lp in all_loops), default=0)
name_col = max_name_len + 2

# Fix — follow the bounded-column idiom used in impact_effort.py:_render_grid()
# and output.py:table():
name_col = min(max_name_len, 32) + 2
```
`cmd_fragments()` in `info.py` is the closest analog: it uses
`name_col_w = max(max_name_len, 8)` (no cap, but bounded below), with
`desc_col_w = max(20, tw - name_col_w - 6)` driving the description budget.
The established capped idiom throughout the codebase is
`max(floor, min(cap, expr))`.

**P1 — built-in marker inversion** (`info.py:274-286`):
```python
# Current: appends colorize("[built-in]", "2") for every lp["builtin"] == True
# Fix: swap — mark only project loops
if not lp["builtin"]:
    suffix_parts.append(colorize("●", "36;1"))   # or "[local]"
```
Color already distinguishes them: `"36;1"` (bold cyan) for project loops,
`"36"` (dim cyan) for built-ins. Explain convention once in the footer.

**P1 — label capping** (`info.py:274-277`):
```python
# Current: all labels rendered individually, no overflow handling
# Fix: cap at first 2, then +N more — pattern from
# impact_effort.py:_render_quadrant_lines():
#   lines.append(f"  … +{extra} more".ljust(col_width))
MAX_LABELS = 2
visible_labels = lp["labels"][:MAX_LABELS]
hidden = len(lp["labels"]) - MAX_LABELS
for lb in visible_labels:
    suffix_parts.append(colorize(f"[{lb}]", "2"))
if hidden > 0:
    suffix_parts.append(colorize(f"[+{hidden}]", "2"))
```

**P2 — category header styling** (`info.py:267`):
```python
# Current: colorize(f"{cat} ({len(group)}):", "1")
# Reference: list_cmd.py:cmd_list() uses type-keyed color + bold:
#   colorize(f"{label} ({len(group)})", f"{TYPE_COLOR.get(prefix, '0')};1")
# Proposed: title-case + ▸ prefix + bold cyan
print(colorize(f"  ▸ {cat.replace('-', ' ').title()}  ({len(group)})", "36;1"))
```

**P2 — summary header** (`info.py` — new, before category loop):
The `·` separator pattern is established in `cmd_show()` (`info.py`):
```python
" · ".join(stats_parts)   # rendered as ·
```
For the new header:
```python
n_project = sum(1 for lp in displayed_loops if not lp["builtin"])
n_builtin  = len(displayed_loops) - n_project
header = f"  {len(displayed_loops)} loops · {len(buckets)} categories"
if n_project:
    header += f" · {n_project} project, {n_builtin} built-in"
print(colorize(header, "2"))
print()
```

**P3 — ellipsis whitespace** (`info.py:_truncate` at lines 319-325):
`_truncate` itself is correct — it slices then appends `"…"` with no
space. The inconsistency originates upstream: `_load_loop_meta()` (lines 32-63)
reads `description` as the first YAML line; if that line ends with a space, the
space survives into `desc_text` before `_truncate` is called. Fix: add
`.rstrip()` in `_load_loop_meta()` when setting description, or in `_truncate`
before checking length.

## Implementation Steps

1. **P0**: In `cmd_list()` at `info.py:257`, change
   `name_col = max_name_len + 2` → `name_col = min(max_name_len, 32) + 2`.
   Truncate names that exceed the cap before `.ljust()` using the existing
   `_truncate()` helper.
2. **P1a**: In the suffix-assembly block (`info.py:274-286`), remove the
   unconditional `[built-in]` append. Replace with a marker only for
   `not lp["builtin"]` (project loops).
3. **P1b**: In the same block, cap labels at `MAX_LABELS = 2` and append
   a `[+N]` overflow badge when `len(lp["labels"]) > 2`.
4. **P2a**: Replace the category header `print` at `info.py:267` with a
   styled header (`▸ Title  (N)` in bold cyan).
5. **P2b**: Before the category loop (after `tw = terminal_width()` at
   `line 259`), compute and print the summary header using the `·` separator
   pattern from `cmd_show()`.
6. **P3**: In `_load_loop_meta()` (`info.py:32-63`), apply `.rstrip()` to the
   first-line description before storing.
7. **Tests**: Update `test_builtin_tag_on_same_line()` and
   `test_label_badge_rendering()` in `TestLoopListFormatting`
   (`test_ll_loop_commands.py:1110`). Add new test methods for column-cap
   clamping, project-loop `●` marker, label `+N` overflow, and summary header.
8. **Verify**: `python -m pytest scripts/tests/test_ll_loop_commands.py::TestLoopListFormatting -v`
   and `python -m pytest scripts/tests/test_ll_loop_display.py -v`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` rendering
  (lines ~243-313) and `_truncate` (line ~319).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/output.py` — `colorize`, `terminal_width`,
  `strip_ansi`, box-drawing constants (reuse; no change required).
- `scripts/little_loops/cli/loop/__init__.py` — registers the `list`
  subcommand in the argument parser (line 296) and dispatches to `cmd_list()`
  (line 821); defines list flags (`--running`, `--status`, `--json`, etc.).

### Tests
- `scripts/tests/test_ll_loop_commands.py` — `TestLoopListFormatting` class
  (line 1110) is the primary test target:
  - `test_truncate_unit()` (line 1113) — unit tests for `_truncate()`
  - `test_column_alignment_names_padded()` (line 1126) — name column padding
  - `test_description_truncation_at_narrow_width()` (line 1171) — truncation
    at narrow width (patches `terminal_width` to 60)
  - `test_description_not_truncated_at_wide_width()` (line 1198) — wide-width
    no-truncation
  - `test_builtin_tag_on_same_line()` — must be updated: P1 removes
    `[built-in]` from ~80 rows; this test currently asserts its presence
  - `test_label_badge_rendering()` — must be updated for P1 label capping
- `scripts/tests/test_ll_loop_display.py` — `test_terminal_width_no_overflow()`
  (line 1489); multiple tests patching `terminal_width()` (lines 1496, 1711+)
- `scripts/tests/test_ll_loop_integration.py` — `test_list_multiple_loops()`
  (line 208)
- Patch pattern: `patch("little_loops.cli.loop.info.terminal_width", return_value=60)`
  for width-sensitive tests; `patch("little_loops.cli.output._USE_COLOR", True)`
  for color-sensitive tests. ANSI stripping before position arithmetic uses
  `re.compile(r"\033\[[0-9;]*m")`.
- Add new cases under `TestLoopListFormatting` for: column-cap behavior,
  built-in marker inversion (project `●` present, `[built-in]` absent),
  label capping (`+N more` on overflow), and summary header text.
- Keep `--json` path untouched (parsed downstream by other tools).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_json_output_contracts.py` — `TestLoopListJsonContract`
  imports `cmd_list` and asserts JSON field names (`built_in`, `name`,
  `category`, `labels`, `visibility`, `description`) and types. The `--json`
  path is not changed by this issue, but spot-check that P0–P3 edits don't
  accidentally touch the JSON branch [Agent 1+2 finding]
- `scripts/tests/test_cli_loop_dispatch.py` — `TestMainLoopListFlagForwarding`
  (line 788) tests that `ll-loop list` flag arguments (`--running`, `--status`,
  `--json`, `-j`) are correctly forwarded; verify no regressions after format
  changes [Agent 1 finding]
- **Additional tests that will break with P2a (title-case headers) — update
  required beyond what step 7 already lists:**
  - `test_blank_line_between_categories` (line 1371, `TestLoopListFormatting`)
    — asserts `"beta" in line` on the category header; breaks when header
    becomes `▸ Beta  (1)` (lowercase match fails); update to check `"Beta"`
    or `"▸"` in the header line
  - `test_list_without_json_unchanged` (line 480, `TestCmdList`) — asserts
    `"uncategorized" in out`; breaks when header title-cases to `Uncategorized`
  - `test_grouped_display_by_category` (line 661, `TestLoopListCategoryFilter`)
    — asserts `"uncategorized" in out`; same title-case break (`"apo"` and
    `"meta"` survive via loop names, but `"uncategorized"` does not)
  - `test_list_empty_loops_dir` (line 184, `TestMainLoopIntegration` in
    `test_ll_loop_integration.py`) — `if "[built-in]" in captured.out:` guard
    becomes a permanently dead branch after P1; update to assert the post-P1
    expected state directly

### Documentation
- `docs/reference/COMMANDS.md` — documents `ll-loop list` command syntax and
  options; update if column-cap or built-in-tag changes alter listed behavior.
- `docs/reference/OUTPUT_STYLING.md` — covers color constants and ANSI styling
  conventions used by `colorize()` and `strip_ansi()`.
- `docs/guides/LOOPS_GUIDE.md` — user guide referencing `ll-loop list` for
  discovery; may need updated screenshot/mock if format changes materially.
- `docs/guides/LOOPS_REFERENCE.md` — loop command reference.
- `docs/reference/json-output-contracts.md` — JSON output contract for
  `ll-loop list --json`; must remain unchanged (human-readable branch only).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — section `ll-loop list / ll-loop l` (~line 645)
  contains detailed prose of the list output structure (column layout,
  `[built-in]` tag placement, category header format); update if the visible
  format changes materially (P1 removes per-row tag; P2 changes header style)
  [Agent 1+2 finding]

### Configuration
- N/A — respects existing `NO_COLOR`/`FORCE_COLOR` via `output.py`.


### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `test_blank_line_between_categories` (line 1371, `test_ll_loop_commands.py`)
   — change category-header match from `"beta" in line` to `"Beta" in line` or
   `"▸" in line` to survive P2a title-casing
10. Update `test_list_without_json_unchanged` (line 480) and
    `test_grouped_display_by_category` (line 661) — change `"uncategorized" in out`
    to `"Uncategorized" in out` (or case-insensitive) for P2a
11. Update `test_list_empty_loops_dir` (line 184, `test_ll_loop_integration.py`)
    — remove dead `if "[built-in]" in captured.out:` branch; assert post-P1
    expected state directly
12. Spot-check `test_json_output_contracts.py::TestLoopListJsonContract` passes
    unchanged — confirm P0–P3 edits don't touch the JSON serialization branch
13. Update `docs/reference/CLI.md` §`ll-loop list / ll-loop l` — reflect new
    column-cap behavior, absence of per-row `[built-in]`, and new category
    header style
## Impact

- **Scope**: single command's human-readable branch; `--json` path untouched.
- **Risk**: low. Pure presentation; no behavior/data changes.
- **Benefit**: every row of the most-used discovery surface becomes legible.

## Session Log
- `/ll:wire-issue` - 2026-06-27T22:12:45 - `e61208ac-a505-4f00-9646-b676ce7f4f5f.jsonl`
- `/ll:refine-issue` - 2026-06-27T21:59:58 - `8c2cb2c3-a9c6-420a-9fce-18dc166b500b.jsonl`
- `/ll:format-issue` - 2026-06-27T21:48:53 - `4db93a84-28af-46ec-8824-975ef1360e97.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:43:31Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a29a508-1851-4c25-8ce4-a3c3e4cf6b9b.jsonl`

---

## Status

open
