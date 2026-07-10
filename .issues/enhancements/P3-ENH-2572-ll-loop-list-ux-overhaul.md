---
id: ENH-2572
title: ll-loop list UX overhaul — scanning-first layout
type: ENH
priority: P3
status: open
captured_at: "2026-07-10T00:00:00Z"
discovered_date: 2026-07-10
discovered_by: manual
labels: [cli, ux, loops]
---

# ENH-2572: `ll-loop list` UX overhaul — scanning-first layout

## Summary

`ll-loop list` currently optimizes for per-row completeness when the actual
job of the listing is *scanning and picking*: 81 rows × full-width truncated
descriptions is ~110 lines where the informative part of most rows is cut
off mid-clause. This issue captures a coherent set of layout/formatting
changes (from a UX review of the current output) to make the listing
scannable at a glance. All changes are in
`scripts/little_loops/cli/loop/info.py` (`cmd_list` and helpers) unless
noted.

## Problems and changes

### 1. Invert the kind column (high impact)

`built-in` is printed 77 times and carries zero information — the summary
header already says `77 BUILT-IN`. Drop the kind column entirely and badge
only the exceptions (`project`, `internal`, `example`), e.g. a colored
`◆ project` marker or cyan name color for project loops. Frees ~12 columns
for descriptions and removes the largest visual-noise source.

### 2. Surface project loops first (high impact)

The user's own project loops (currently 4) are the most likely run targets
but are scattered across categories (`distill-decisions` is buried under
KNOWLEDGE MANAGEMENT between built-ins). Pin a `▸ YOUR PROJECT (N)` section
at the top; loops may still also appear in their category, or move there
exclusively.

### 3. Collapse singleton/tiny categories (high impact)

21 categories for 81 loops is over-fragmented — seven categories have a
single member, so a third of the headers "manage" one row each. Fold
categories below a member threshold (<2 or <3) into a trailing
`▸ OTHER (N)` group with the original category shown as a dim inline tag,
e.g. `inkscape-task  (generated)  …`. Cuts header overhead by ~1/3 and lets
real clusters (HARNESS 19, ISSUE MANAGEMENT 12) stand out.

### 4. Smarter description truncation (high impact)

- Cut at the last word boundary, not mid-word (`(installed-package …`
  reads broken).
- Prefer ending at the first sentence when it fits — the first sentence is
  usually the whole value.
- Strip or dim repeated leading boilerplate within a category: HARNESS has
  9 rows starting "Generator-evaluator harness for…", so the truncated
  visible text is nearly identical across rows; eliding the shared prefix
  makes the *distinguishing* words visible.

### 5. Compact default, detail on demand (medium impact)

For discovery, a two/three-column grid of names grouped by category (like
`ls`) fits 81 loops on one screen; `ll-loop list -l` gives the current
description layout. Alternatively keep descriptions but pipe to `$PAGER`
when output exceeds terminal height (git-style).

### 6. Order categories by relevance, not alphabet (medium impact)

Alphabetical puts API ADOPTION first and buries ISSUE MANAGEMENT/HARNESS.
Sort by member count descending (project-containing categories first),
keeping `uncategorized` last. Alphabetical-within-category stays.

### 8. Header separator consistency (polish)

`81 LOOPS · 21 CATEGORIES · 4 PROJECT, 77 BUILT-IN` mixes `,` with `·` —
use `·` throughout: `81 LOOPS · 21 CATEGORIES · 4 PROJECT · 77 BUILT-IN`.

### 9. Footer next-action affordances (polish)

Alongside the existing hidden-tier hint, add:
`ll-loop show <name> for details · --category <cat> to filter`. Discovery
of the next action is the point of a list.

### 10. Loosen subgroup subhead thresholds (polish)

`· apo-* (5)` subheads are useful, but the current rule in
`_detect_subgroups` (≥3 members AND ≥50% of the category) blocks e.g.
`rl-*`-style clusters inside mixed categories. The ≥3-members rule alone is
likely sufficient; drop or relax the dominance requirement.

*(Item 7 from the original review — label column jitter — was intentionally
excluded from this issue.)*

## Acceptance criteria

- [ ] Kind column removed; non-built-in rows carry a distinguishing badge/color
- [ ] Project loops surfaced in a pinned top section
- [ ] Categories under the member threshold folded into `OTHER` with inline tags
- [ ] Description truncation is word-boundary aware; shared category prefixes de-emphasized
- [ ] Compact grid default (or pager) with `-l` for the detailed layout
- [ ] Categories ordered by size/relevance, `uncategorized` last
- [ ] Header uses `·` separators throughout
- [ ] Footer includes show/filter hints
- [ ] Subgroup detection relaxed to the ≥3-members rule
- [ ] `--json` output unchanged; existing tests in `scripts/tests/test_ll_loop_commands.py` updated
