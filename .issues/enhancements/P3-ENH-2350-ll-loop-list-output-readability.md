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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` rendering
  (lines ~243-313) and `_truncate` (line ~319).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/output.py` — `colorize`, `terminal_width`,
  `strip_ansi`, box-drawing constants (reuse; no change required).

### Tests
- Search `scripts/tests/` for existing `cmd_list` / `ll-loop list` coverage;
  add cases for column-cap behavior, built-in marker inversion, label capping,
  and summary header. Keep `--json` output unchanged (parsed downstream).

### Documentation
- TBD — check `docs/` references to `ll-loop list` output shape.

### Configuration
- N/A — respects existing `NO_COLOR`/`FORCE_COLOR` via `output.py`.

## Impact

- **Scope**: single command's human-readable branch; `--json` path untouched.
- **Risk**: low. Pure presentation; no behavior/data changes.
- **Benefit**: every row of the most-used discovery surface becomes legible.

## Session Log
- `/ll:format-issue` - 2026-06-27T21:48:53 - `4db93a84-28af-46ec-8824-975ef1360e97.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:43:31Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a29a508-1851-4c25-8ce4-a3c3e4cf6b9b.jsonl`

---

## Status

open
