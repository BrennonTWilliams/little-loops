---
id: ENH-2541
title: 'Further polish `ll-loop list` output: all-caps section markers, no dim body text, palette fix'
type: ENH
priority: P3
status: done
discovered_date: 2026-07-08
captured_at: '2026-07-08T03:56:35+00:00'
discovered_by: user
decision_needed: false
completed_at: '2026-07-08T03:56:35+00:00'
labels:
  - enhancement
  - cli-output
  - ux
  - follow-up-to-ENH-2539
confidence_score: 95
outcome_confidence: 88
score_complexity: 12
score_test_coverage: 18
score_ambiguity: 14
score_change_surface: 16
---

# ENH-2541: Further polish `ll-loop list` output

## Summary

Follow-up to ENH-2539 (commit `cd745299`). After ENH-2539 brought `ll-loop list` to rough parity with `ll-issues list --group-by epic`, six styling gaps remained that make the output look timid next to the reference:

1. Section markers (category headers, subgroup subheads, summary lines) are title-cased (`Harness`, `HITL`) rather than ALL-CAPS — looks timid next to the issues list.
2. Terminal width defaults to 80, so the description column is floored at 20 chars and most descriptions get truncated to `…`.
3. Subgroup subheads use dim (`0;2`) which is hard to read.
4. Two loop categories (`code-quality`, `quality`) both reuse the FEAT green (`"32"`), clashing with the issues list palette.
5. The render block uses ANSI dim (`"2"`) for 5 different text fields (summary, rollup, kind="built-in", description, subhead). Dim is a "transparency" layer that hurts readability.
6. The closing `Total:` line is plain text — no color, no styling.

## Current Behavior

`ll-loop list` output (after ENH-2539, but before this polish):

```
  81 loops · 21 categories · 4 project, 77 built-in     [colorize("2") = DIM]

  ▸ Code Quality  (4)  4 built-in                       [code-quality: green "32"]
  dead-code-cleanup                 built-in    Find dead code, remove high-…
  …

  ▸ Harness  (19)  18 built-in, 1 project
  tmp/harness-plan-research-imple…  project     EXAMPLE: Specialist…
  …

Total: 81 loops · 21 categories · 4 project, 77 built-in   [PLAIN]
       18 hidden (14 internal, 4 example) — pass --all to show   [DIM]
```

Specific gaps:
- `▸ Code Quality` — title-cased, not all-caps; green clashes with FEAT green.
- Top summary `"  81 loops · 21 categories"` — dim (`"2"`).
- Rollup badge `"  4 built-in"` — dim (`"2"`).
- `built-in` kind column — dim (`"2"`).
- Description text — dim (`"2"`).
- `    APO (5)` subgroup subhead — dim (`"0;2"`).
- `Total: 81 loops …` — plain, no styling.

## Expected Behavior

`ll-loop list` output (after this polish, commit `9b03609a`):

```
  81 LOOPS · 21 CATEGORIES · 4 PROJECT, 77 BUILT-IN     [bold "1"]

  ▸ CODE QUALITY  (4)  4 built-in                       [38;5;75 256-blue]
  dead-code-cleanup                 built-in    Find dead code, remove high-…
  …

  ▸ HARNESS  (19)  18 built-in, 1 project
  tmp/harness-plan-research-imple…  project     EXAMPLE: Specialist…
  …

TOTAL: 81 LOOPS · 21 CATEGORIES · 4 PROJECT, 77 BUILT-IN    [bold "1"]
       18 hidden (14 internal, 4 example) — pass --all to show   [DIM, kept]
```

Six concrete polish points:

1. **All-caps section markers** via a new `_all_caps()` helper in `output.py`. Differs from `_smart_title` in that non-acronyms are also uppercased (`"harness"` → `"HARNESS"`, not `"Harness"`). Applied to category headers, subgroup subheads, top summary, and closing Total line. Body content (name, kind, labels, description) stays mixed case.

2. **Full terminal width** — `cmd_list` uses `terminal_width(default=120)` (matches `list_cmd.py:172`). Effect: `desc_col` grows from 20 (floored at TW=80) to 52 chars at TW=120.

3. **Layout uniform** — subgroup subheads now render in bold + the parent's category color (instead of dim `0;2`). The 4-space subhead indent is subordinate to the 2-space category header and 6-space leaf rows.

4. **Replace green text** — `CATEGORY_COLOR` palette fix:
   - `code-quality`: `"32"` (FEAT green) → `"38;5;75"` (256-blue)
   - `quality`: `"32"` (FEAT green) → `"38;5;178"` (256-gold)
   - `meta`: `"38;5;208"` (BUG orange) → `"38;5;220"` (256-yellow)
   - All other entries retain their colors. Remaining intentional duplicates (apo/orchestration, gate/rl, harness/routing, issue-management/research, integration/planning, optimization/api-adoption) are documented as semantic groupings in the CATEGORY_COLOR docstring.

5. **Remove transparency from text** — 5 sites in `info.py` swap `colorize(..., "2")` for non-dim styles:
   - Top summary: `"2"` → `"1"` (bold)
   - Rollup badge: `"2"` → `"36"` (cyan)
   - `kind="built-in"`: `"2"` → `"0"` (default)
   - `kind="example"`: `"33;2"` → `"33"` (yellow non-dim)
   - Description text: removed `colorize` entirely (plain text — biggest readability win)
   - Subgroup subhead: `"0;2"` → `f"{cat_color};1"` (bold + category color)
   - Hidden-tier hint: kept `"2"` (correctly de-emphasized)

6. **Add color/styling to counts/summary** — both the top summary and the closing `TOTAL:` line are bold + uppercase. The closing line uses `colorize("TOTAL: " + " · ".join(total_parts), "1")`.

## Resolution

Commit `9b03609a` — `feat(loop): further polish ll-loop list output (all-caps, no dim, palette fix)`. 6 files changed, +226 / -63 lines.

**Files modified:**

- `scripts/little_loops/cli/output.py`
  - Added `_all_caps(slug)` helper (after `_smart_title` at line 127).
  - Updated `CATEGORY_COLOR` map: `code-quality`, `quality`, `meta` codes per item #4 above. Updated docstring to document intentional semantic-duplicate color groupings.

- `scripts/little_loops/cli/loop/info.py` — `cmd_list` render block changes (8 sites):
  1. Import `_all_caps` (drop unused `_smart_title`).
  2. `tw = terminal_width(default=120)`.
  3. Top summary: uppercase labels + `colorize(summary, "1")`.
  4. Category header: `cat_title = _all_caps(cat)`.
  5. Rollup badge: `colorize(rollup, "36")`.
  6. `kind_color_map`: `built-in` default, `example` non-dim.
  7. Description text: `f"  {desc_text}"` (no `colorize`).
  8. Subgroup subhead: `colorize(f"    {sub_label} ({len(members)})", f"{cat_color};1")`.
  9. Total line: uppercase labels + `colorize("TOTAL: " + …, "1")`.
  10. Hidden-tier hint: kept dim (`"2"`).

- `scripts/tests/test_ll_loop_commands.py` — `TestCmdListENH2539Polished`:
  - 7 existing tests updated for all-caps (e.g., `"Evaluation"` → `"EVALUATION"`, `"Total:"` → `"TOTAL:"`, `"Beta"` → `"BETA"`).
  - 3 new tests added:
    - `test_summary_header_bold_and_uppercase` — top summary + Total line both bold + uppercase.
    - `test_description_text_not_dim` — description substring is not wrapped in `\033[2m`.
    - `test_default_terminal_width_120` — 45-char description fits at TW=120 (would be truncated at TW=80).

- `scripts/tests/test_cli_output.py` — 2 new tests:
  - `test_all_caps_uppercases_all_words` — covers `_all_caps` + distinguishes from `_smart_title`.
  - `test_category_color_no_green_for_quality_or_code_quality` — no loop category reuses the FEAT green (`"32"`).

- `docs/reference/CLI.md` — `ll-loop list` section updated to mention `_all_caps`, `terminal_width(default=120)`, the palette fix, and "no body text is rendered with dim/faint ANSI; only the hidden-tier hint keeps dim."

- `docs/reference/OUTPUT_STYLING.md` — `_all_caps` helper documented; `CATEGORY_COLOR` table reflects v2 palette.

## Out of scope (preserved)

- Running-loops branch (`--running` / `--status`) — separate code path, unchanged.
- JSON output path — byte-identical to ENH-2539.
- `--group-by category|kind|visibility|label` flag (deferred from ENH-2539).
- `config-schema.json` `cli.colors.categories` block (deferred from ENH-2539, still not merged by `configure_output`).
- Visibility filter, no-loops early-return, filter-mismatch early-return — all untouched.

## Verification

- **Targeted tests:** 339/339 passed (`test_ll_loop_commands.py`, `test_cli_output.py`, `test_cli_loop_layout.py`).
- **Full suite:** 14,249 passed, 35 skipped, 0 failed (baseline 14,244 + 5 new tests).
- **Lint/format/mypy:** all clean on modified files.
- **Visual smoke test:** `FORCE_COLOR=1 ll-loop list` renders `HARNESS`, `APO`, `HITL`, `CODE QUALITY` headers in ALL-CAPS; description column visibly wider; no dim text in body content; closing `TOTAL:` line bold.

Refines ENH-2539.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-08T03:57:06 - `64503939-c5c4-438d-be45-6e2d43934834.jsonl`
