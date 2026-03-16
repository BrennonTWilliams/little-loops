---
id: ENH-732
priority: P4
type: ENH
status: active
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 78
---

# ENH-732: Replace FSM State Box Badges with Unicode Compositions

## Summary

Replace the plain-text `[action_type]` badge labels rendered inside FSM box diagram state boxes with compact, visually distinctive multi-character unicode compositions.

## Current Behavior

State boxes in FSM box diagrams display plain-text bracket badges: `[prompt]`, `[slash_command]`, `[shell]`, and `[mcp]`. These badges are verbose and consume significant horizontal space inside fixed-width state boxes, causing state names to be truncated more frequently.

## Motivation

The current badges (`[prompt]`, `[slash_command]`, `[shell]`, `[mcp]`) are verbose and consume horizontal space inside fixed-width state boxes, causing more name truncation. Replacing them with compact unicode glyphs reduces badge width while improving visual clarity and making different action types immediately recognizable at a glance.

## Expected Behavior

Replace each action type badge with the following composition, positioned in the **top-right corner** of the state box (replacing the current inline badge that appears alongside the state name):

| Action Type     | Current Badge    | New Badge |
|----------------|-----------------|-----------|
| `prompt`        | `[prompt]`       | `✦`       |
| `slash_command` | `[slash_command]`| `/━►`     |
| `shell`         | `[shell]`        | `❯_`      |
| `mcp_tool`      | `[mcp_tool]`     | `⚡`       |

The badge must be right-aligned within the top border row of the box so it appears in the top-right corner, rather than inline next to the state name. The state name continues to occupy the remaining horizontal space on the name row.

The `mcp` action type is not yet implemented (tracked in FEAT-729), but the badge mapping should be added in anticipation of that feature.

## Scope Boundaries

- **In scope**: Replacing the badge strings for the four known action types (`prompt`, `slash_command`, `shell`, `mcp`) in the FSM box diagram renderer
- **Out of scope**: Implementing the `mcp` action type itself (tracked in FEAT-729)
- **Out of scope**: Changing state box sizes, padding, or layout algorithms
- **Out of scope**: Adding terminal auto-detection for environments that don't support unicode
- **Out of scope**: Updating other diagram renderers (e.g., ASCII fallback modes, if any)

## Implementation Steps

1. Add a `_ACTION_TYPE_BADGES` dict in `scripts/little_loops/cli/loop/layout.py` mapping action type strings to their unicode compositions (`"prompt"`, `"slash_command"`, `"shell"`, `"mcp_tool"`).
2. Replace all three badge-construction sites in `layout.py` — plus the hardcoded literal in `_helpers.py` — with lookups into `_ACTION_TYPE_BADGES`, falling back to `f"[{action_type}]"` for unknown types:
   - `layout.py:82–87` — badge construction in `_box_inner_lines` (also handles inline placement at lines 90–98)
   - `layout.py:463–467` — badge construction in `_compute_box_sizes` (width measurement only, not rendered)
   - `layout.py:1387–1391` — badge construction in pre-layout loop inside `_render_fsm_diagram` (width estimation only, not rendered)
   - `_helpers.py:334` — hardcoded `[prompt]` literal in the live execution event handler (`run_foreground`); this is a separate literal string, not a dynamic badge, so update it to `✦` directly
3. Move the badge from its current inline position (appended after the state name with two spaces, in `_box_inner_lines` at line 91) to the **top-right corner** of the state box: right-align the badge within the top border row so it occupies the rightmost characters of that row, and remove it from the state name row. The top border drawing logic is separate from `_box_inner_lines` — locate where the top border row (`┌─…─┐`) is assembled and embed the badge before the closing `┐`. (Quick discovery: `grep -n '┌' scripts/little_loops/cli/loop/layout.py` will surface the assembly site immediately.)
4. Verify width calculations remain correct — the new badges have different display widths than the old bracket strings (e.g., `[slash_command]` is 15 chars; `/━►` is 3 chars, but `━` (U+2501, BOX DRAWINGS HEAVY HORIZONTAL) and `►` (U+25BA, BLACK RIGHT-POINTING POINTER) are double-width in many terminals). All current width calculations use `len()` directly on strings; no `wcwidth` library is present. Validate visually after implementation.
5. Consider using `wcwidth` or a `_BADGE_DISPLAY_WIDTHS` override table for display-width calculation if terminal rendering is a concern.
6. No snapshot/golden-file tests assert on badge text — existing tests in `scripts/tests/test_ll_loop_display.py` check structural properties (box-drawing characters, state names) not exact badge strings. Run tests after changes to verify no regressions; no golden-file updates should be needed for the text change itself.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — primary badge rendering logic; 3 badge-construction sites:
  - `_box_inner_lines` (lines 82–87, placement at 90–98) — the only site that renders badges visually
  - `_compute_box_sizes` (lines 463–467, width used at 469) — width measurement only
  - `_render_fsm_diagram` pre-layout loop (lines 1387–1391, width used at 1397) — width estimation only
- `scripts/little_loops/cli/loop/_helpers.py` — hardcoded `[prompt]` literal at line 334 in `run_foreground` live execution event handler

### Dependent Files (Callers/Importers)
- Any module importing from `little_loops.cli.loop.layout` (grep for `from .layout import` or `from little_loops.cli.loop.layout import`)

### Similar Patterns
- `_helpers.py:334` uses a hardcoded `[prompt]` literal (not dynamic) — update as a direct string replacement
- No other `f"[{...}]"` badge-pattern sites exist in `layout.py` beyond the three listed

### Tests
- `scripts/tests/test_ll_loop_display.py` — tests check structural properties (box-drawing characters, state names) only; **no assertions on badge strings**, so no golden-file updates needed and new badges will not be automatically validated — consider adding a minimal assertion after implementing

### Documentation
- N/A — no docs reference these internal badge strings

### Configuration
- N/A — no config files affected

## Impact

- **Priority**: P4 - Low priority visual enhancement; purely cosmetic, no functional change
- **Effort**: Small - Three localized edits in `layout.py` plus test snapshot updates; reuses existing badge-construction pattern
- **Risk**: Low - Fallback to bracket notation for unknown types; no behavioral change; well-isolated to rendering layer
- **Breaking Change**: No — output format changes are cosmetic only (badge strings in terminal diagrams)

## Labels

`enhancement`, `ui`, `fsm`, `diagram`, `unicode`

## Related Issues

- FEAT-729: Dedicated `mcp_tool` action type (adds the `mcp` state this badge will serve)
- BUG-730: Transition lines occlude state boxes in FSM box diagram (sibling diagram visual issue)
- ENH-731: Rename FSM transition labels success/fail → yes/no (related diagram label cleanup)

---
## Verification Notes

- **Date**: 2026-03-14
- **Verdict**: NEEDS_UPDATE
- Feature not yet implemented; no `_ACTION_TYPE_BADGES` dict. Actual badge sites (verified 2026-03-15): `layout.py` lines 82–98, 463–469, and **1387–1397** (not 1367 as stated in prior notes). Fourth site: `_helpers.py:334` (hardcoded literal `[prompt]`). Action type for mcp is `mcp_tool` (per `schema.py:211`), not `mcp`.

## Status

Active — not yet started.

## Session Log
- `/ll:refine-issue` - 2026-03-16T02:01:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73de97cd-c70a-4e30-a624-ccf2502dd5ce.jsonl`
- `/ll:format-issue` - 2026-03-16T00:58:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8bc41a61-b249-4f82-b1e4-50bab87ac931.jsonl`
- `/ll:format-issue` - 2026-03-15T00:00:00Z - auto
- `/ll:verify-issues` - 2026-03-15T00:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:capture-issue` - 2026-03-13T22:51:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34ee1913-aa14-4e60-9d80-efda0df3efc0.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa4d2baf-3524-4c44-a9ad-16fe76a5f6b8.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/542b29e8-0de5-4f06-8439-bc467dc3bdab.jsonl`
