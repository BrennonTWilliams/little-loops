---
id: ENH-2572
title: ll-loop list UX overhaul — scanning-first layout
type: ENH
priority: P3
status: closed
closed_date: 2026-07-10
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
at the top. Project loops move there **exclusively** — they do not also
appear under their category (duplication would inflate row counts and make
category totals disagree with the header). Each row in the pinned section
shows its home category as a dim inline tag, e.g.
`distill-decisions  (knowledge management)  …`, so category context isn't
lost.

### 3. Collapse singleton/tiny categories (high impact)

21 categories for 81 loops is over-fragmented — seven categories have a
single member, so a third of the headers "manage" one row each. Fold
categories with **fewer than 3 members** (i.e., 1–2 loops) into a trailing
`▸ OTHER (N)` group with the original category shown as a dim inline tag,
e.g. `inkscape-task  (generated)  …`. Cuts header overhead by ~1/3 and lets
real clusters (HARNESS 19, ISSUE MANAGEMENT 12) stand out. The <3
threshold (rather than <2) is deliberate: two-member categories are as
marginal as singletons for scanning purposes, and folding both keeps the
rule from needing revisiting as the catalog grows.

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

**Decision: compact grid default, `-l` for detail.** The default output
becomes a multi-column grid of names grouped by category (like `ls`),
sized to terminal width (fall back to one column when stdout is not a
TTY), fitting all loops on roughly one screen. `ll-loop list -l` (long)
gives the current one-row-per-loop description layout, with items 1–4
applied to it. The `$PAGER` alternative was rejected: paging keeps the
per-row noise and merely hides it behind scrolling, which contradicts the
scanning-first goal, and paged output surprises scripts and CI logs.

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

- [x] Kind column removed; non-built-in rows carry a distinguishing badge/color
- [x] Project loops surfaced in a pinned top section exclusively (not duplicated in categories), with dim home-category tag
- [x] Categories with <3 members folded into `OTHER` with inline tags
- [x] Description truncation is word-boundary aware; shared category prefixes de-emphasized
- [x] Compact grid is the default (one column when not a TTY); `-l` gives the detailed layout
- [x] Categories ordered by size/relevance, `uncategorized` last
- [x] Header uses `·` separators throughout
- [x] Footer includes show/filter hints
- [x] Subgroup detection relaxed to the ≥3-members rule
- [x] `--json` output unchanged; existing tests in `scripts/tests/test_ll_loop_commands.py` updated
