---
id: ENH-3017
title: CLI.md describes the ll-init wizard as 6 screens; code has 7 (missing Plugin
  Install screen)
type: ENH
status: done
priority: P3
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
completed_at: '2026-08-03T16:49:00Z'
parent: EPIC-3008
depends_on:
- ENH-3016
program_design_not_applicable: true
testable: false
labels:
- docs
- ll-init
milestone: epic-3008
confidence_score: 95
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3017: `CLI.md` describes the `ll-init` wizard as 6 screens; code has 7 (missing "Plugin Install" screen)

## Summary

`docs/reference/CLI.md:65-76` documents the interactive `ll-init` wizard as 6
screens ("1/6 Project Basics" through "6/6 CLAUDE.md update"). The actual code
(`scripts/little_loops/init/tui.py`) has 7 screens, with screen 1 — "Plugin
Install" — undocumented entirely. This is the first thing a new user sees when
running `ll-init` interactively, so the gap is user-visible from the very
start of the flow.

## Current Behavior

`tui.py` screen sequence (line numbers per the audit):
1. `"1 / 7 Plugin Install"` (`tui.py:207`) — install/upgrade/adapter-staleness
   detection + `questionary.confirm("Proceed with wizard?")`
2. `"2 / 7 Project Basics"` (`tui.py:267`)
3. `"3 / 7 Scan"` (`tui.py:318`)
4. `"4 / 7 Features"` (`tui.py:347`)
5. `"5 / 7 Hosts"` (`tui.py:485`)
6. `"6 / 7 Settings"` (`tui.py:499`)
7. `"7 / 7 CLAUDE.md"` (`tui.py:523`)

`CLI.md:65-76` numbers these as 1/6 through 6/6 and never mentions the Plugin
Install screen.

## Scope Boundaries

In scope: `docs/reference/CLI.md:65-76`'s wizard-screen walkthrough **and the
lead-in sentence immediately above it** (see below). Out of scope: changing the
actual TUI screen order/content in `init/tui.py`.

**File-conflict note:** ENH-3016 edits the same `## ll-init` section of
`docs/reference/CLI.md` (host lists at `:37,49`). This issue declares
`depends_on: [ENH-3016]` so the two are serialized — land ENH-3016 first. Do
not run them as concurrent epic branches.

## Two corrections to this issue's own earlier description

1. **`CLI.md:65-76` is a markdown table, not a numbered list.** It has
   `| Screen | Prompt | Notes |` columns with rows `1 / 6` … `6 / 6`. The fix is
   inserting a table *row* and renumbering the `Screen` column — an earlier draft
   of this issue said "update the numbered list," which would mislead an
   implementer expecting `1.`/`2.` markdown list syntax.

2. **The lead-in sentence above the table is also now wrong.** `CLI.md` currently
   reads: *"The detected project type is shown as a banner line (not a
   questionary prompt) before Screen 1 starts."* With Plugin Install becoming
   Screen 1, this sentence must be re-verified against `init/tui.py` — the banner
   almost certainly precedes **Project Basics** (the new Screen 2), not the new
   Screen 1. Check where the banner is actually emitted relative to
   `tui.py:207` (`1 / 7 Plugin Install`) and `tui.py:267` (`2 / 7 Project
   Basics`), and correct the sentence accordingly.

## Expected Behavior

`CLI.md`'s wizard-screen walkthrough should match the actual 7-screen
sequence, including a short description of the Plugin Install screen (what it
checks: install/upgrade status, adapter staleness; what it asks: confirm to
proceed).

## Suggested Fix Direction

Insert a `| 1 / 7 | Plugin Install | ... |` row at the top of the table in
`CLI.md:65-76` and renumber the existing rows `2 / 7` through `7 / 7`. Keep the
new row's Notes cell brief and consistent with the existing entries — what it
checks (install/upgrade status, adapter staleness) and what it asks
(`questionary.confirm("Proceed with wizard?")`, `tui.py:207`). Then fix the
lead-in banner sentence per correction #2 above.

## Acceptance Criteria

- [x] The `CLI.md` table has 7 rows numbered `1 / 7` … `7 / 7`, matching the
      `console.rule` labels at `tui.py:207,267,318,347,485,499,523` exactly.
- [x] The Plugin Install row is first and describes both what it checks and what
      it prompts.
- [x] The lead-in banner sentence names the correct screen it precedes, verified
      against `init/tui.py`.
- [x] No change to `init/tui.py`.

## Resolution

Inserted a `1 / 7 | Plugin Install` row at the top of the `CLI.md` wizard-screen
table and renumbered the remaining rows `2 / 7` … `7 / 7` to match
`tui.py:207,267,318,347,485,499,523`. The new row notes it's conditional (only
shown when install/upgrade is needed) and documents the
`questionary.confirm("Proceed with wizard? ...")` prompt. Corrected the lead-in
sentence: the project-type banner (`tui.py:260-262`) prints after the
conditional Plugin Install block and immediately before the `2 / 7 Project
Basics` rule, so it now reads "before Screen 2 starts" instead of "before
Screen 1 starts." No changes to `init/tui.py`.

## Status

**Done** | Created: 2026-08-02 | Priority: P3

## Impact

- **Priority**: P3 — user-facing doc inaccuracy affecting the very first
  screen a new user encounters.
- **Effort**: Small.
- **Risk**: None.
- **Breaking Change**: No.


## Session Log
- `/ll:manage-issue` - 2026-08-03T16:48:39 - `ebb78be3-195c-4134-ad17-a99b7493e411.jsonl`
- `/ll:confidence-check` - 2026-08-03T15:07:46 - `7932f7a9-44bc-4afe-a0b6-100d091d368a.jsonl`
