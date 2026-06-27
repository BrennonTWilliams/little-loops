---
id: ENH-2335
title: 'll-issues clusters: add legend + filter/summary header, adopt shared palette, unify edge notation'
type: ENH
priority: P3
status: open
captured_at: '2026-06-26T23:55:00Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- ENH-2336
- FEAT-2337
labels:
- captured
- cli
- ll-issues
- clusters
- output-styling
---

# ENH-2335: `ll-issues clusters` — legend, filter/summary header, shared palette, unified edge notation

## Summary

The `clusters` command (`scripts/little_loops/cli/issues/clusters.py`) color-codes
six relationship types but prints **no legend**, never **echoes the active filters**,
gives only a thin **footer summary**, **bypasses the shared configurable palette**,
uses **two different notations** for the same relationship, and carries a **dead
color mapping**. These are contained, low-risk output fixes (no layout change) that
make the command's existing output self-explanatory and consistent with sibling
`ll-issues` subcommands. The larger layout rework is tracked separately in
FEAT-2337; scoping flags / richer per-cluster headers in ENH-2336.

## Current Behavior

Audited live against the current backlog (9 clusters, 52 issues, 373 lines of output).

- **No legend (B1).** `EDGE_COLOR` (`clusters.py:16-23`) maps six relationship types
  to ANSI colors, but nothing tells the reader which color means what. Sibling
  commands already establish the convention: `refine_status.py:529 _print_key()` and
  `cli/sprint/show.py` both print a `Key:` block.
- **Active filters not echoed (B2).** `--edges`, `--status`, and `--min-connections`
  change what is shown, but the output never states the active scope, so the reader
  can't tell `active` from `all`, or `hard` edges from everything.
- **Thin summary (B3).** Footer is `9 clusters, 52 issues total` (`clusters.py:392-395`)
  — no edge count, no cycle count, no relationship-type breakdown, and no overview
  printed *before* the ~370-line detail dump.
- **Ignores the shared, configurable palette (C1).** Clusters hardcodes `EDGE_COLOR`
  and never uses `PRIORITY_COLOR` / `TYPE_COLOR` (`cli/output.py:111-131`), which are
  theme-configurable. `[P3]` priorities and issue IDs render uncolored, so the user's
  theme is bypassed.
- **Two notations for one concept (C2).** Inline edges render a colored ` depends_on`
  label + ▲/▼ arrowhead (`clusters.py:254-267`); the skip-edge list renders
  `SRC → DST  (rel)` (`clusters.py:280-289`). Same relationship, two visual languages.
- **Cycle warning bypasses the helper (C3).** `print("⚠ cycle detected — using
  fallback layout")` (`clusters.py:386`) hardcodes the ⚠ icon instead of calling
  `output.warning()` (`cli/output.py:195`), so the icon shows even under `NO_COLOR`,
  unlike the rest of the CLI.
- **Dead color mapping (C4).** `"sibling": "36"` (`clusters.py:20`) is never collected
  in `_build_neighbour_map` / `_cluster_edges` and there is no `sibling` field on
  `IssueInfo` (confirmed: no `sibling` usage in `issue_parser.py`). Stale entry.

## Expected Behavior

Running `ll-issues clusters` produces self-explanatory output consistent with sibling subcommands:
- Prints a `Key:` legend listing only the edge types present in the rendered output, with color swatches (suppressed under `NO_COLOR`)
- Echoes active filters and an aggregate overview before the per-cluster detail dump (e.g., `edges=all · status=active · min-connections=0` and `9 clusters · 52 issues · N edges · 1 cycle`)
- Colorizes `[P{n}]` priority tags via `PRIORITY_COLOR` and issue IDs via `TYPE_COLOR` (from `cli/output.py`), honoring the user's theme and `config.color`/`NO_COLOR`
- Uses one consistent notation for all edge representations (inline and skip-edge list)
- Routes cycle warnings through `output.warning()` so the ⚠ icon is suppressed under `NO_COLOR`
- No longer contains the unused `"sibling"` entry in `EDGE_COLOR`
- `--json` output is unchanged

## Motivation

This enhancement makes `ll-issues clusters` output self-explanatory and consistent with sibling subcommands:
- **Usability**: The six ANSI colors currently have no legend — users cannot decode what each color means without reading source code
- **Consistency**: Sibling commands (`refine_status`, `sprint show`) already print `Key:` blocks and echo active filters; clusters is the outlier
- **Theme respect**: Bypassing `PRIORITY_COLOR`/`TYPE_COLOR` means user-configured themes have no effect on cluster output — breaking the expected UX contract
- **Low risk**: All six fixes are isolated to text rendering; no algorithm or layout changes; `--json` is untouched

## Proposed Solution

1. **Legend.** Add a `Key:` block (modeled on `refine_status.py:_print_key`) mapping
   each *active* edge type to its color/meaning. Only list edge types actually present
   in the rendered output. Respect `NO_COLOR` (legend still prints, sans color).
2. **Filter echo + overview header.** Before the per-cluster detail, print the active
   scope and an aggregate overview, e.g.:
   `edges=all · status=active · min-connections=0` and
   `9 clusters · 52 issues · N edges · 1 cycle`.
3. **Adopt the shared palette.** Colorize `[P{n}]` via `PRIORITY_COLOR` and the issue
   ID via `TYPE_COLOR` (`cli/output.py`), so cluster output honors the user's theme.
   Keep `EDGE_COLOR` for relationship labels (no shared edge palette exists).
4. **Unify edge notation.** Make the skip-edge list use the same colored-label
   notation as inline arrows (or vice-versa) so both read as one visual language.
5. **Route the cycle warning through `output.warning()`** so the icon obeys `NO_COLOR`.
6. **Delete the dead `sibling` entry** from `EDGE_COLOR`.

## Acceptance Criteria

- Running `ll-issues clusters` prints a legend covering every edge color present in
  the output, and an active-filter line + aggregate overview before the detail.
- Priority tags and issue IDs are colorized via the shared `PRIORITY_COLOR` /
  `TYPE_COLOR` palettes and respect `config.color` / `NO_COLOR`.
- Inline edges and skip-edges use one consistent notation.
- The cycle warning is emitted via `output.warning()` (icon suppressed under `NO_COLOR`).
- `EDGE_COLOR` no longer contains the unused `sibling` key.
- `--json` output is unchanged (this issue is text-render only).
- Tests cover: legend lists only active edge types, filter/overview line content, and
  `NO_COLOR` suppression of color + cycle icon.

## Scope Boundaries

- Layout / graph-shape rework (FEAT-2337).
- `--cluster N` / `--limit` / compact mode and richer per-cluster headers (ENH-2336).

## Implementation Steps

1. **Delete dead `sibling` entry** from `EDGE_COLOR` in `clusters.py` (one-line removal)
2. **Add legend** — implement `_print_key()` listing only edge types present in rendered output; model after `refine_status.py:_print_key`; respect `NO_COLOR`
3. **Add filter echo + overview header** — before per-cluster detail, print active `--edges`/`--status`/`--min-connections` values and aggregate counts (clusters, issues, edges, cycles)
4. **Adopt shared palette** — replace hardcoded priority/type color strings with `PRIORITY_COLOR`/`TYPE_COLOR` from `cli/output.py`; colorize `[P{n}]` tags and issue IDs
5. **Unify edge notation** — align skip-edge list (`_render_skip_edges`, `clusters.py:280-289`) to the same colored-label + arrowhead format as inline edges (`clusters.py:254-267`)
6. **Route cycle warning** — replace bare `print("⚠ cycle detected …")` with `output.warning()` call
7. **Add tests** — cover legend (active types only), filter/overview line content, `NO_COLOR` suppression of colors and cycle icon

## Integration Map

- `scripts/little_loops/cli/issues/clusters.py` — `cmd_clusters` (header/footer/legend),
  `_render_cluster_diagram` (palette + unified notation), `EDGE_COLOR` (drop `sibling`).
- `scripts/little_loops/cli/output.py` — reuse `PRIORITY_COLOR`, `TYPE_COLOR`,
  `colorize`, `warning`.
- New/updated tests under `scripts/tests/` (no dedicated clusters render test exists yet).

## Impact

- **Priority**: P3 — Output polish/consistency on an internal command; not blocking,
  but the missing legend makes the existing colors undecodable.
- **Effort**: Small — contained additions to one render function plus reuse of existing
  output helpers; no layout/algorithm change.
- **Risk**: Low — text rendering only; `--json` untouched.
- **Breaking Change**: No.

---
**Open** | Created: 2026-06-26 | Priority: P3


## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Step 5 (unify skip-edge notation, aligning `_render_skip_edges` to match the inline arrow format) is provisional. FEAT-2337 plans to eliminate the skip-edge renderer entirely by promoting all edges into the primary graph-aware layout — when FEAT-2337 ships, the renderer step 5 polishes ceases to exist in its current form. Implement step 5 to improve the current box-stack output, but the implementation need not be forward-compatible with FEAT-2337's new renderer. Related issue: FEAT-2337.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-27T22:09:57 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:format-issue` - 2026-06-27T01:46:36 - `b75f8bb7-5276-4075-a005-0b4de6a3121b.jsonl`
