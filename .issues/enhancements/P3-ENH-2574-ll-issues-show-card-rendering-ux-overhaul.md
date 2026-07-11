---
id: ENH-2574
title: "ll-issues show: card rendering UX overhaul \u2014 summary reflow, visual hierarchy,\
  \ low-signal pruning"
status: done
priority: P3
labels:
- cli
- ux
- issues
captured_at: '2026-07-10T03:10:36Z'
completed_at: '2026-07-11T04:14:02Z'
discovered_date: '2026-07-10'
discovered_by: capture-issue
relates_to:
- ENH-2572
- ENH-2535
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2574: ll-issues show: card rendering UX overhaul — summary reflow, visual hierarchy, low-signal pruning

## Summary

`_render_card` in `scripts/little_loops/cli/issues/show.py` optimizes for
per-row completeness, but the actual job of the single-issue card is scanning:
read the title, orient on status, absorb the summary. Today the summary reflows
badly (a wrapping bug produces 1–2 word orphan lines), the card is too narrow on
wide terminals, every row carries equal ink weight, and several low-signal rows
(`Source: manual`, cryptic `Norm: ✓ │ Fmt: ✗`, redundant `Captured at` vs
`Discovered`) crowd out the content. This is a direct sibling of ENH-2572's
scanning-first rationale for `ll-loop list`, applied to `ll-issues show`.

## Motivation

The card is the primary surface for inspecting a single issue. Small rendering
defects compound: the summary-reflow bug alone turns ~7 clean lines into ~13
ragged ones, and the flat visual weight forces the reader to parse chrome
(borders, glyphs) with the same attention as content. Fixing reflow + hierarchy
is low-risk, self-contained (one renderer function), and materially improves
every `ll-issues show` invocation.

## Current Behavior

In `scripts/little_loops/cli/issues/show.py`:

- **Summary reflow bug** (`show.py:639`): `_render_card` wraps the summary per
  source line (`summary_text.splitlines()` → wrap each), so hard line breaks
  from the markdown file survive into the card. Each ~80-char source line wraps
  to a full line plus a 1–2 word orphan.
- **Width** (`show.py:650`): driven by the longest structural line (e.g. the
  Path line, ~68 cols) with a 60-col floor, capped at `terminal_width() - 4`.
  On a 200-col terminal the card stays narrow and the summary wraps to the
  metadata's width.
- **Flat hierarchy**: every row is equal weight; the only ink hierarchy is the
  horizontal rules. ID is colored, but title, labels, status, and Path all read
  at the same intensity.
- **Ambiguous separator**: the inline `  │  ` between fields (e.g.
  `Priority: P3  │  Status: Open`) reuses the card-border glyph, reading as
  accidental column lines.
- **Low-signal rows**: `Source: manual` (the default case), cryptic
  `Norm: ✓ │ Fmt: ✗`, and `Captured at: 2026-07-10T00:00:00Z` duplicating
  `Discovered: 2026-07-10` on the same day.

## Expected Behavior

The card scans cleanly: summary paragraphs wrap without orphan lines, the card
widens on wide terminals instead of staying pinned to metadata width, title
and status carry visual weight while borders/labels/Path recede, the intra-row
separator no longer doubles as the border glyph, low-signal rows (`Source:
manual`, cryptic `Norm/Fmt`, redundant `Captured at`) are hidden or collapsed,
and metadata keys align into a column once the detail block has 4+ rows.

## Proposed Solution

1. **Reflow paragraphs before wrapping.** Split the summary on blank lines,
   join each paragraph's words, then `textwrap.wrap(..., break_long_words=False)`
   to `wrap_width`, inserting a blank line between paragraphs:

   ```python
   paragraphs = re.split(r"\n\s*\n", summary_text)
   for para in paragraphs:
       summary_lines.extend(
           textwrap.wrap(" ".join(para.split()), width=wrap_width, break_long_words=False)
       )
       summary_lines.append("")  # blank between paragraphs
   ```

2. **Let the card breathe.** Target `min(terminal_width() - 4, ~100)` and wrap
   the summary to that width, rather than inheriting the metadata block's width.

3. **Add hierarchy with color/weight, not more borders.**
   - Bold the title (ID already colored).
   - Dim the borders (`\x1b[2m`) so content pops over chrome.
   - Dim field labels (`Priority:`, `Labels:`), leave values full intensity.
   - Color all statuses: In Progress yellow, Blocked red, Deferred/Cancelled
     dim, Open default (Completed already colored).
   - Dim the Path line (reference info, not content).

4. **Calmer intra-row separator.** Replace inline `  │  ` with `·` or plain
   triple-space: `Priority: P3   ·   Status: Open`.

5. **Cut / collapse low-signal rows.** Hide `Source: manual`; replace cryptic
   `Norm/Fmt` with a single actionable `Needs: formatting` line only when
   `fmt` is ✗; render dates as `2026-07-10` (drop `T00:00:00Z`) and collapse
   `Captured at` when it equals `Discovered`.

6. **Align the metadata block into columns.** Right-pad keys once the detail
   block has 4+ `Key: value` lines so the eye tracks one vertical edge.

## Integration Map

_Added by `/ll:refine-issue` — codebase-driven research findings:_

### Files to Modify
- `scripts/little_loops/cli/issues/show.py:520` (`_render_card`) — primary
  target; all 6 implementation steps land here
- `scripts/little_loops/cli/issues/show.py:636-643` — summary reflow loop
  (item 1, the `splitlines()` + per-line `textwrap.wrap` bug)
- `scripts/little_loops/cli/issues/show.py:645-650` — width computation:
  `wrap_width = max(len(longest structural line), 60)` followed by
  `width = min(width, terminal_width() - 4)` (item 2)
- `scripts/little_loops/cli/issues/show.py:666-668` — status colorization
  site (currently only `Completed` is colored green) (item 3)
- `scripts/little_loops/cli/issues/show.py:683-700` — line assembly where
  `_ljust` (colored) and `f"{line:<{width-1}}"` (uncolored) mix; per item 3
  + AC #7 every site must switch to `_ljust` (item 3 correctness)
- `scripts/little_loops/cli/issues/show.py:558, 566, 578, 593, 602, 674` —
  literal `"  │  "` separator sites (item 4)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/show.py:728` — `cmd_show` is the sole
  caller of `_render_card(fields)`. No other internal callers; no external
  import surface (`_render_card` is module-private).

### Similar Patterns
- `scripts/little_loops/cli/issues/show.py:466-470` (`_render_discovery_block`)
  — short-SHA truncation guard (`sha[:7] if len(sha) > 7 else sha`). Same
  shape as the proposed unbreakable-token guard in item 2; zero-dependency,
  in-file.
- `scripts/little_loops/cli/loop/info.py:567` — `_smart_truncate` (word-
  boundary + sentence-preferring). More capable than needed for AC #7 but
  available if shared.
- `scripts/little_loops/cli/loop/layout.py:219` — `_truncate_to_width_ansi`
  (wcwidth-aware, preserves SGR sequences, emits `\x1b[0m` reset before `…`).
  Canonical truncation helper; used by `info.py:539`. Cross-module dep if
  imported from `show.py`.
- `scripts/little_loops/cli/loop/info.py:124-131` — local `_STATUS_COLORS`
  for loop state (running/interrupted/stopped/etc.). Reference palette shape
  for item 3.
- `scripts/little_loops/cli/sprint/show.py:110` — `_STATUS_COLOR =
  {"OK": "32", "REVIEW": "33", "WARNING": "38;5;208", "BLOCKED": "31"}`.
  Reference palette shape; matches the proposal's "In Progress yellow,
  Blocked red" intent (RENH-style sprint status vs issue status mapping).
- `scripts/little_loops/cli/loop/info.py:316-322, 382, 1514, 1519` —
  `·` (U+00B7, middle dot) is the established separator throughout
  `ll-loop list` (item 4).
- `scripts/little_loops/cli/loop/info.py:497` — `colorize(name, "1")` for
  bold title (item 3).
- `scripts/little_loops/cli/loop/info.py:434, 531` — `colorize(tag, "2")`
  for dim chrome (item 3).
- `scripts/little_loops/cli/output.py:333-345` — `status_block(items)`
  right-pads keys via `max(len(k) for k in items)`. Models item 6's column-
  pad intent (plain-text only — must be replaced by an ANSI-aware variant
  once labels get dim-colored).

### Tests
- `scripts/tests/test_show.py:419-575` (`TestRenderCard`) — existing card-
  renderer tests; substring-style assertions under the `stable_snapshot_env`
  fixture.
  - **Gap to add**: summary reflow / no-orphan-lines (no current test
    asserts the AC #1 behavior).
  - **Gap to add**: status coloring for non-`Completed` statuses
    (`In Progress`, `Blocked`, `Deferred`, `Cancelled`) — only `Completed`
    is currently asserted.
  - **Gap to add**: width scaling on wide terminals — `stable_snapshot_env`
    (`scripts/tests/conftest.py:109-123`) pins `terminal_width = 80`, so
    the AC #2 wide-terminal behavior is untested.
  - **Conflict to resolve**: `test_long_unbreakable_word_extends_box`
    (`test_show.py:447`) asserts a 120-char token IS in the card
    (`assert long_word in card`). AC #7 flips this — the token must be
    **truncated** (and absent from the card). Replace this test in the
    same commit that lands the truncation guard.
  - **Pattern to copy**: `test_discovered_commit_shortened`
    (`test_show.py:528`) asserts both substring presence and absence
    (`"abc1234" in card` and `"abc1234567890def" not in card`). Direct
    shape for the AC #7 truncation test.
- `scripts/tests/test_show.py:387-411` (`TestLjust`) — already covers
  ANSI-coded input, plain text, exact-width, and over-width cases; extend
  with a card-level assertion once item 3 colors labels.

_Wiring pass added by `/ll:wire-issue`:_
- **Additional breaking tests within `TestRenderCard`** (beyond the reflow
  conflict above) — these assert literal label/date text that items 3 and
  5 change: `test_closure_block_present_for_done_status` (`"Closing note:
  ..." in card`), `test_discovery_block_renders_discovered_date`
  (`"Discovered: 2026-06-15"` and `"Captured at: 2026-07-01T00:00:00Z"` —
  both named directly in item 5's date-collapse target), plus
  `test_discovered_commit_shortened`, `test_decision_coupling_with_ref`,
  `test_decision_explicit_no_when_false`, `test_decision_ref_alone_renders_explicit`,
  `test_relationships_block_renders_blocked_by`,
  `test_blocked_status_includes_blocked_by_name` (all assert literal
  substrings adjacent to the `"  │  "` separator being swapped in item 4).
- `scripts/tests/test_issues_cli.py::TestIssuesCLIShow` (~line 1990+) —
  integration-level tests that invoke `ll-issues show` via
  `main_issues()`/`sys.argv` and assert on `capsys` output (e.g.
  `"Priority: P0" in captured.out`), separate from `test_show.py`'s direct
  `_render_card` unit tests. Lower risk (substrings don't pin exact
  separator text) but still depends on the `"Priority: {colorize(...)}"`
  format staying intact — spot-check after implementation.
- **Test patterns to model new tests after** (no existing test file covers
  color-on/reflow/width-scaling for `_render_card`):
  - `scripts/tests/test_loop_layout_alignment.py` —
    `_assert_boxes_rectangular()` (structural border-column invariant, not
    substring-based; model for the AC #1 no-orphan-lines check) and the
    `terminal_width` monkeypatch pattern (narrow-clamped /
    wide-unclamped pair) for AC #2's width-scaling gap.
  - `scripts/tests/test_cli_loop_layout.py::TestColorizeLabel._force_color`
    — `monkeypatch.setattr(..., "_USE_COLOR", True)` fixture; needed since
    `stable_snapshot_env` (which all current `TestRenderCard` tests use)
    forces color OFF, so none of today's tests can assert the new bold/dim
    hierarchy from item 3.
  - `scripts/tests/test_sprint.py::test_show_color_output` /
    `test_show_no_color_output` — closest existing analog (a "show"-style
    card renderer tested once with color forced on, once off); template
    for the AC #3 color-hierarchy test pair.

### Documentation
- `docs/reference/OUTPUT_STYLING.md:211-269` — dedicated "Issue Card:
  `scripts/little_loops/cli/issues/show.py`" section. Line 269 documents
  the current width formula ("max of all content line lengths plus 2
  padding, with a minimum of 60 characters. The summary section is
  wrapped with `textwrap.wrap()` to fit the structural width.") that
  ENH-2574 replaces. Requires an update pass once implementation lands.
- `docs/reference/OUTPUT_STYLING.md:283+` — "FSM Diagram:
  `scripts/little_loops/cli/loop/layout.py`" section documents the shared
  width/truncation helpers (`_display_width`, `_truncate_to_width`,
  `_truncate_to_width_ansi`, `_wrap_to_width`) — reference if item 2's
  truncation guard is implemented via the shared layout module.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:~1093-1108` (`#### ll-issues show <issue_id>`
  section) — enumerates the exact card fields in prose, including `source
  (discovered_by)`, `norm`/`fmt`, `captured_at` / `completed_at`
  timestamps. Item 5's row pruning (hide `Source: manual`, collapse
  `Norm/Fmt` → `Needs:`, drop `Captured at` when it equals `Discovered`)
  makes this prose stale — needs a matching edit in the same change.

### Coupling Reference (informational — no action expected)
_Wiring pass added by `/ll:wire-issue`:_ the following were traced and
ruled OUT as wiring targets — `_render_card` is the sole consumer of the
`output.py` primitives it uses (`colorize`, `strip_ansi`, `terminal_width`,
`status_block`), and none of their signatures change. Machine consumers of
`ll-issues show` (skills/loops) exclusively use `--json`, which is a
separate code path unaffected by `_render_card`. No action needed on
`plugin.json`, `.ll/ll-config.json`, `hooks/hooks.json`, or the 40+ other
files importing `output.py` helpers for unrelated renderers.

### Configuration
- None — this is a pure renderer change. No new CLI flags, no schema, no
  `ll-config.json` keys. Reuses existing `terminal_width()`, `colorize()`,
  `strip_ansi()`, `_ljust()` primitives.

## Implementation Steps

1. Fix the summary reflow in `_render_card` (`show.py:639`) — paragraph-first
   wrap.
2. Decouple card width from metadata width; compute `wrap_width` from
   `min(terminal_width() - 4, ~100)` (`show.py:650`).
3. Apply color/weight hierarchy (title bold, dim borders/labels/Path, full
   status coloring).
4. Swap the intra-row separator glyph.
5. Prune/collapse low-signal rows (Source, Norm/Fmt → Needs, date formatting).
6. Align metadata keys into a padded column when ≥4 detail lines.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

7. Update `docs/reference/CLI.md` (~line 1093-1108) — the `ll-issues show`
   section's field-list prose still names `Source`/`Norm`/`Fmt`/
   `Captured at` as always-rendered rows; revise to match item 5's
   pruning/collapse rules.
8. Update `scripts/tests/test_show.py::TestRenderCard` — the 8 tests
   listed under "Tests" that assert literal `Captured at:`/`Discovered:`
   text or content adjacent to the `"  │  "` separator.
9. Spot-check `scripts/tests/test_issues_cli.py::TestIssuesCLIShow` after
   implementation — integration-level assertions on card substrings.

## Correctness Notes

- Uncolored detail lines use `f"{dl:<{width-1}}"` while colored lines use
  `_ljust` (`show.py:406`). The moment labels/status get colorized, switch
  **everything** to `_ljust` or padding breaks (ANSI codes count toward
  `str` length).
- Width is capped at `terminal_width() - 4`, so an unbreakable token longer
  than the cap bleeds through the right border — add a truncation guard.

## Acceptance Criteria

- [x] Summary paragraphs reflow cleanly with no 1–2 word orphan lines; hard
      line breaks from the source markdown do not survive into the card.
- [x] Card width scales up on wide terminals (targets ~100 cols, not the
      metadata width) and never exceeds `terminal_width() - 4`.
- [x] Title is bold; borders, field labels, and Path are dimmed; all status
      values are colored per state.
- [x] Intra-row separator is no longer the border glyph.
- [x] `Source: manual` is hidden; `Norm/Fmt` collapses to an actionable
      `Needs:` line only when formatting is missing; dates render date-only and
      collapse when captured == discovered.
- [x] Metadata keys align into a padded column when the detail block has ≥4
      rows.
- [x] All colored/padded lines use `_ljust`; a token longer than the width cap
      is truncated rather than bleeding past the right border.
- [x] Tests cover the reflow fix and truncation guard.

## Scope Boundaries

- **In scope**: Rendering of `_render_card` only — summary reflow, card width,
  color/weight hierarchy, intra-row separator, low-signal row pruning/collapse,
  and metadata column alignment.
- **Out of scope**: New content or fields on the card (surfacing closure
  context, relationships, discovery, decision coupling) — that is ENH-2535.
- **Out of scope**: Changes to the issue data model, frontmatter schema, or the
  `ll-issues show` command surface (flags, arguments).
- **Out of scope**: Other CLI renderers — `ll-loop list` scanning-first work is
  tracked separately under ENH-2572.

## Impact

- **Priority**: P3 - Quality-of-life UX polish on a frequently-hit surface
  (`ll-issues show`); no functional blocker, so below feature/bug work.
- **Effort**: Small - Self-contained in a single renderer function
  (`_render_card`); reuses existing `_ljust`/`textwrap` primitives, no new
  dependencies or data plumbing.
- **Risk**: Low - Pure presentation change with no data-model impact; primary
  hazards (ANSI-aware padding, unbreakable-token overflow) are enumerated in
  Correctness Notes and covered by the acceptance criteria's test requirement.
- **Breaking Change**: No - Output formatting only; no API, flag, or schema
  changes.

## Related Issues

- **ENH-2572** — `ll-loop list` UX overhaul (the scanning-first sibling this
  mirrors).
- **ENH-2535** — `ll-issues show`: surface closure context, relationships,
  discovery, and decision coupling (content/fields; complementary, not
  overlapping — this issue is rendering-only).

## Related Key Documentation

_None identified._

## Status

- **Status**: open
- **Priority**: P3

## Session Log
- `/ll:manage-issue` - 2026-07-11T04:13:21 - `c4beaae3-c0b9-45a1-b688-8037d422a9c6.jsonl`
- `/ll:ready-issue` - 2026-07-11T03:48:09 - `56bccfb9-6c3d-48e1-8028-d234b7a312c1.jsonl`
- `/ll:ready-issue` - 2026-07-11T03:47:50 - `56bccfb9-6c3d-48e1-8028-d234b7a312c1.jsonl`
- `/ll:confidence-check` - 2026-07-10T00:00:00Z - `0ce66e18-b0c3-48ab-9ab5-6caf248dbeab.jsonl`
- `/ll:wire-issue` - 2026-07-11T03:43:28 - `c6b8268e-4922-4226-8bbd-7893754bf36e.jsonl`
- `/ll:refine-issue` - 2026-07-11T03:37:49 - `6dcfc439-b277-4037-965b-53b0e49c808a.jsonl`
- `/ll:format-issue` - 2026-07-10T20:13:04 - `2b14d541-25a4-44a2-b564-12e3bfaf1c45.jsonl`
- `/ll:capture-issue` - 2026-07-10T03:10:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/35fe1048-04fc-45c5-b8aa-3c931ebbd1d9.jsonl`
