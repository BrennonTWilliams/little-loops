---
id: ENH-2542
title: 'Swap loop-name column color from cyan to 256-steel-blue'
type: ENH
priority: P4
status: done
discovered_date: 2026-07-08
captured_at: '2026-07-08T05:01:30+00:00'
discovered_by: user
decision_needed: false
completed_at: '2026-07-08T05:01:30+00:00'
labels:
  - enhancement
  - cli-output
  - ux
  - follow-up-to-ENH-2541
confidence_score: 90
outcome_confidence: 85
score_complexity: 5
score_test_coverage: 10
score_ambiguity: 8
score_change_surface: 6
---

# ENH-2542: De-emphasize chromatic text in `ll-loop list`

## Summary

Follow-up to ENH-2541. Two pieces of text in `ll-loop list` rendered with ANSI 36 (cyan) that reads as greenish on dark terminals with teal-leaning palettes (Solarized Dark, certain Dracula variants) and competes visually with the bold category headers above each group:

1. **Loop-name column** (`info.py:335`) — switched from `"36"` (cyan) to `"1"` (bold). Weight-based emphasis that reads identically on every palette and never collides with a category color.
2. **Rollup badge** inside each category header (`info.py:309`, e.g. `"18 built-in, 1 project"`) — switched from `"36"` (cyan) to `"90"` (bright black / "gray"). A neutral de-emphasis that doesn't compete with the bold category header color.

Both changes replace chromatic emphasis with neutral emphasis (weight / grayscale), so they cannot conflict with any `CATEGORY_COLOR` entry or kind-label color, and they read the same way on every terminal palette.

## Current Behavior

Before ENH-2542, both surfaces used ANSI 36 (cyan):

```python
# info.py:335 — loop-name column
name_str = colorize(_truncate(lp["name"], _MAX_NAME_COL).ljust(name_col), "36")

# info.py:309 — rollup badge inside category header
header_label += f"  {colorize(rollup, '36')}"
```

ANSI 36 is cyan. On most terminals it's recognizably blue, but on dark themes with teal-leaning palettes it shifts perceptually toward green. Once perceived as green, it competes visually with the FEAT green (`"32"`) and makes the loop-name column look like a category label rather than a row identifier.

## Expected Behavior

After ENH-2542, both surfaces use neutral ANSI codes:

```python
# info.py:335 — loop-name column: bold, no chromatic information
name_str = colorize(_truncate(lp["name"], _MAX_NAME_COL).ljust(name_col), "1")

# info.py:309 — rollup badge: ANSI 90 ("bright black" / gray)
header_label += f"  {colorize(rollup, '90')}"
```

`"1"` (bold) and `"90"` (bright black) are both **palette-neutral**:
- `"1"` re-renders the default foreground at bold weight — no chromatic baggage, no palette dependency.
- `"90"` is the standard "bright black" ANSI code, which reads as gray on both light and dark terminals (not as black-on-black).

Both choices are conventional for "primary identifier" / "secondary metadata" cells in CLI tables (`ls`, `git status`, `kubectl get`).

## Iteration history

Three iterations considered before settling on bold + gray:

1. **256-steel-blue (`"38;5;67"`)** for loop-name — implemented first; rejected on user review as "too distracting." A chromatic emphasis competes with the kind-label colors and draws the eye away from category organization.
2. **Bold white (`"1"`)** for loop-name — chosen final. Weight-based emphasis has no chromatic baggage.
3. **Gray (`"90"`)** for rollup badge — chosen after the user flagged the rollup cyan as "ugly green." Gray reads as a neutral de-emphasis alongside the bold category header without competing for chromatic attention.

## Resolution

Two single-line swaps + two tests that lock in the new styles and guard against regressions.

**Files modified:**

- `scripts/little_loops/cli/loop/info.py`:
  - Line 309 (rollup badge): `"36"` → `"90"`, with a 4-line comment documenting why.
  - Line 335 (loop-name column): `"36"` → `"1"`, with a 4-line comment documenting why.
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdListENH2539Polished`:
  - `test_loop_name_bold_white` — asserts the loop-name row contains `\033[1m` immediately before the loop name (last ANSI opener in the cell starts with `1m`). Guards against future chromatic openers re-asserting inside the loop-name cell.
  - `test_rollup_badge_uses_gray` — asserts the rollup badge text is wrapped in `\033[90m…\033[0m` and that the badge no longer carries the legacy `\033[36m…\033[0m` wrap. Allows `\033[36;1m` (project kind label) to remain elsewhere in the output.

The tests assert specific openers **inside the targeted cell/segment** (loop-name row / rollup badge substring) rather than blanket-asserting that cyan is absent from the output. Compound codes like `\033[36;1m` are allowed outside the targeted cells.

## Out of scope (preserved)

- `kind_color_map["project"] = "36;1"` (cyan+bold): unchanged. It's the kind column, distinct from the loop-name column, and the bold weight keeps it readable.
- `LABEL_COLOR["hitl"] = "36"` (cyan): unchanged. Used for the `[hitl]` label badge — different surface, intentional accent color.
- Category headers, subheads, summary lines: all retain their `CATEGORY_COLOR` codes. No category color changed.
- The hidden-tier hint (`info.py:380-385`): still dim (`"2"`) — correctly de-emphasized.

## Verification

- **Targeted tests:** 14/14 passed (`TestCmdListENH2539Polished`), including the two new tests `test_loop_name_bold_white` and `test_rollup_badge_uses_gray`.
- **Broader suites:** 264/264 passed (`test_ll_loop_commands.py` + `test_cli_output.py`).
- **Full suite:** 14,251 passed, 35 skipped, 0 failed.
- **Visual smoke test:** `FORCE_COLOR=1 ll-loop list` — loop-name column is bold (no chromatic noise); category headers retain their colors; `[hitl]` labels still cyan; project kind label still cyan+bold; rollup badge is now gray instead of greenish-cyan.
- **No regression:** only two call sites changed; no other surfaces use these specific ANSI codes for these specific text fields.

Refines ENH-2541.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-08T04:08:44 - `34d6d9a8-606d-4fb8-a12d-2f6cd682dc4a.jsonl`
