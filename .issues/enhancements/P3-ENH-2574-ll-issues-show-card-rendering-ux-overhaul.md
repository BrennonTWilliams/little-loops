---
id: ENH-2574
title: 'll-issues show: card rendering UX overhaul — summary reflow, visual hierarchy, low-signal pruning'
status: open
priority: P3
labels: [cli, ux, issues]
captured_at: "2026-07-10T03:10:36Z"
discovered_date: "2026-07-10"
discovered_by: capture-issue
relates_to: [ENH-2572, ENH-2535]
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

## Correctness Notes

- Uncolored detail lines use `f"{dl:<{width-1}}"` while colored lines use
  `_ljust` (`show.py:406`). The moment labels/status get colorized, switch
  **everything** to `_ljust` or padding breaks (ANSI codes count toward
  `str` length).
- Width is capped at `terminal_width() - 4`, so an unbreakable token longer
  than the cap bleeds through the right border — add a truncation guard.

## Acceptance Criteria

- [ ] Summary paragraphs reflow cleanly with no 1–2 word orphan lines; hard
      line breaks from the source markdown do not survive into the card.
- [ ] Card width scales up on wide terminals (targets ~100 cols, not the
      metadata width) and never exceeds `terminal_width() - 4`.
- [ ] Title is bold; borders, field labels, and Path are dimmed; all status
      values are colored per state.
- [ ] Intra-row separator is no longer the border glyph.
- [ ] `Source: manual` is hidden; `Norm/Fmt` collapses to an actionable
      `Needs:` line only when formatting is missing; dates render date-only and
      collapse when captured == discovered.
- [ ] Metadata keys align into a padded column when the detail block has ≥4
      rows.
- [ ] All colored/padded lines use `_ljust`; a token longer than the width cap
      is truncated rather than bleeding past the right border.
- [ ] Tests cover the reflow fix and truncation guard.

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
- `/ll:format-issue` - 2026-07-10T20:13:04 - `2b14d541-25a4-44a2-b564-12e3bfaf1c45.jsonl`
- `/ll:capture-issue` - 2026-07-10T03:10:36Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/35fe1048-04fc-45c5-b8aa-3c931ebbd1d9.jsonl`
