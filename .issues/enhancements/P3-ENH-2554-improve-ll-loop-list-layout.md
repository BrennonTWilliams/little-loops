---
status: done
completed_at: 2026-07-08T00:00:00Z
---
# P3-ENH-2554: Improve `ll-loop list` layout — 5 high-impact fixes

## Summary

The `ll-loop list` command rendered 81 loops in ~21 categories with several
redundancies and inconsistencies. A direct review of the output identified
11 candidate fixes; this issue implements the 5 high-impact ones, scoped to
keep the diff small and tests stable. Three follow-up items (singleton
collapse, uncategorized de-emphasis, type-column polish) are explicitly
deferred.

## Changes Implemented

### 1. Display-width-aware truncation (cmd_list)
**Problem**: Local `_truncate` (`info.py:400`) counted characters, not
display columns. Wide glyphs and the ellipsis were sized inconsistently.
**Fix**: Reuse `layout._truncate_to_width` (already in the codebase) via a
thin `_truncate` adapter. `_truncate_to_width` uses `wcwidth` for column
counts and keeps wide glyphs whole.

### 2. Strip redundant path prefixes from loop names
**Problem**: Loop names like `tmp/harness-plan-research-imple…` and
`generated/inkscape-task` exposed filesystem structure that duplicated the
category header. The `tmp/` prefix also stole 4 chars of name column.
**Fix**: New `_display_name(name)` helper strips `tmp/`, `generated/`,
`examples/`, `lib/` prefixes via regex. **`oracles/` is intentionally
preserved** — nested oracles round-trip through `ll-loop run` by relative
path (`test_nested_loop_appears_with_relative_path`).
**Result**: `tmp/harness-plan-research-imple…` →
`harness-plan-research-implement…` (more name visible, no `tmp/` clutter).
`generated/inkscape-task` → `inkscape-task`. JSON output unchanged — the
raw `lp["name"]` is still used for serialization.

### 3. Deduplicate category header rollup
**Problem**: `▸ APO  (6)  6 built-in` — the `(6)` and `6 built-in` said the
same thing; the breakdown was redundant for homogeneous categories.
**Fix**: Rewrote `_category_rollup` to return:
- `""` for homogeneous groups (the `(N)` already carries the count)
- Minority kinds only when there's a clear dominant kind (the dominant
  count duplicates `(N)`)
- The full mix when kinds are tied at the top (so `(N)` still
  disambiguates the breakdown)

### 4. Standardize subgroup indent
**Problem**: Categories with subgroups (APO, PLANNING, RL) mixed three
indent levels within one category: 2-space flat, 4-space subhead,
6-space leaves. Visually cluttered.
**Fix**: Consistent 2/4 hierarchy:
- Categories without subgroups: 2-space leaves (unchanged)
- Categories with subgroups: 2-space subhead, 4-space leaves for ALL
  members (subgroup + flat tail unified). No 6-space level, no mixed
  2/6 within a category.

### 5. Drop redundant TOTAL footer
**Problem**: The closing `TOTAL: 81 LOOPS · …` line repeated the header
summary.
**Fix**: Removed the TOTAL line entirely. The hidden-tier hint (`N hidden
(X internal, Y example) — pass --all to show`) is the only footer
emitted, and only when there ARE hidden loops.

## Deferred (separate follow-up)

These came up in review but are explicitly out of scope for this pass:
- **Singleton-category collapse** — fold 6 single-loop categories
  (`KNOWLEDGE MANAGEMENT`, `OPTIMIZATION`, `QUALITY`, `ROUTING`,
  `TELEMETRY`, `GENERATED`) into a single line.
- **Uncategorized de-emphasis** — render `uncategorized` dimmed unless
  `--all` is passed.
- **Type-column polish** — replace `"built-in"` / `"project"` text with
  short colored badges.

## Acceptance Criteria

- [x] Category headers no longer echo `(N)` AND the count of the dominant kind
- [x] Mixed categories emit only minority-kind counts (e.g. `HARNESS (19)  1 project`)
- [x] No `tmp/`, `generated/`, `examples/`, `lib/` prefix on display names
- [x] `oracles/` prefix preserved (round-trip through `ll-loop run`)
- [x] Subgroup indent is 2/4 (subhead 2, leaves 4) — no 6-space level
- [x] Truncation is display-width-aware (CJK/wide glyphs stay whole)
- [x] No `TOTAL:` line at bottom of `ll-loop list`
- [x] Hidden-tier hint still appears when public filter hides loops
- [x] JSON output unchanged (path-relative `name` field preserved)
- [x] All existing tests pass; tests pinning the removed redundant
      behavior were updated to reflect the new (correct) behavior

## Files Changed

- `scripts/little_loops/cli/loop/info.py` — all 5 fixes (cmd_list,
  _truncate, _category_rollup, new _display_name helper)
- `scripts/tests/test_ll_loop_commands.py` — 5 tests updated to reflect
  new dedup/no-footer behavior (test_rollup_badge_in_header,
  test_closing_total_summary, test_row_columns_aligned_at_tw_80,
  test_summary_header_bold_and_uppercase, and the oracles/ preservation
  verified by test_nested_loop_appears_with_relative_path)
- `scripts/tests/test_cli_loop_layout.py` — 2 _category_rollup unit
  tests updated (test_all_built_in_public, test_internal_hidden_count_included)

## Verification

### Automated
- Full pytest suite: **14,356 passed, 36 skipped, 0 failed** (in 58s)
- `scripts/tests/test_ll_loop_commands.py`: **189 passed**
- `scripts/tests/test_cli_loop_layout.py`: **77 passed**

### Manual smoke
- `ll-loop list` — clean output, no redundant counts, no TOTAL footer,
  consistent indent
- `ll-loop list -c harness` — mixed case shows `HARNESS  (19)  1 project`
- `ll-loop list --json` — contract unchanged; `name` field still has
  path-relative keys (`generated/inkscape-task`)
- `ll-loop list --visibility public` — hidden-tier hint still emits:
  `19 hidden (15 internal, 4 example) — pass --all to show`

## Plan Reference

`.claude/plans/no-worktree-or-seperate-lazy-sutherland.md` — the plan
filed before implementation.

## Labels

ui, layout, cli, ux, polish

## Priority

P3 — UX improvement to a user-facing command; not critical, but the
existing output was redundant enough to warrant direct review.

## Resolution

- **Action**: improve
- **Completed**: 2026-07-08
- **Status**: Completed
- **Implementation**: Direct edits to `scripts/little_loops/cli/loop/info.py`
  plus matching test updates in `test_ll_loop_commands.py` and
  `test_cli_loop_layout.py`. No worktree, no separate branch (per user
  instruction).

### Verification Results

- 14,356 tests pass, 0 fail
- Manual smoke confirms all 5 layout improvements render as specified
- JSON contract preserved (verified via `ll-loop list --json | jq`)

### Commits

- See git log for details

## Session Log
- `hook:posttooluse-status-done` - 2026-07-09T01:09:01 - `3aa28e19-94d0-4c9e-b047-f21db8e0ecf5.jsonl`

> **Historical duplicate ID (normalize-issues 2026-07-10):** number `2554` is a cross-type duplicate shared with **BUG-2554** (`ll-loop-list-rows-overflow-terminal-width-with-wide-labels`). Both issues are `done` and embedded in shipped code/CHANGELOG/git history, so neither was renumbered — the type prefix disambiguates them. (The four resolvable collisions 2519/2520/2521, 2575/2576/2577, and 2530 were renumbered to 2580–2586 the same day.)
