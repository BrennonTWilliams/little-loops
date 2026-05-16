---
id: ENH-732
priority: P4
type: ENH
status: completed
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 86
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
| sub-loop        | `[loop]`         | `↳⟳`     |

The badge must be right-aligned within the top border row of the box so it appears in the top-right corner, rather than inline next to the state name. The state name continues to occupy the remaining horizontal space on the name row.

The `mcp` action type is not yet implemented (tracked in FEAT-729), but the badge mapping should be added in anticipation of that feature.

Sub-loop states (introduced in FEAT-659) have `state.loop is not None` but no `action_type`. The badge renderer must check for the sub-loop condition **before** the `_ACTION_TYPE_BADGES` lookup, since `action_type` will be `None` for these states. These states currently render no badge at all — the current badge placeholder (shown as `[loop]` above) is what they would display without this enhancement.

## Scope Boundaries

- **In scope**: Replacing the badge strings for the four known action types (`prompt`, `slash_command`, `shell`, `mcp_tool`) in the FSM box diagram renderer, plus adding a badge for sub-loop states (`loop:` field set, introduced in FEAT-659)
- **Out of scope**: Implementing the `mcp` action type itself (tracked in FEAT-729)
- **Out of scope**: Changing state box sizes, padding, or layout algorithms
- **Out of scope**: Adding terminal auto-detection for environments that don't support unicode
- **Out of scope**: Updating other diagram renderers (e.g., ASCII fallback modes, if any)

## Implementation Steps

1. Add a `_ACTION_TYPE_BADGES` dict in `scripts/little_loops/cli/loop/layout.py` mapping action type strings to their unicode compositions (`"prompt"`, `"slash_command"`, `"shell"`, `"mcp_tool"`), and a separate `_SUB_LOOP_BADGE = "↳⟳"` constant for sub-loop states.
2. Replace all three badge-construction sites in `layout.py` — plus the hardcoded literal in `_helpers.py` — with a helper that checks `state.loop is not None` first (returning `_SUB_LOOP_BADGE`), then falls back to `_ACTION_TYPE_BADGES.get(action_type, f"[{action_type}]")`:
   - `layout.py:82–87` — badge construction in `_box_inner_lines` (also handles inline placement at lines 90–98)
   - `layout.py:463–467` — badge construction in `_compute_box_sizes` (width measurement only, not rendered)
   - `layout.py:1387–1391` — badge construction in pre-layout loop inside `_render_fsm_diagram` (width estimation only, not rendered)
   - `_helpers.py:334` — hardcoded `[prompt]` literal in the live execution event handler (`run_foreground`); this is a separate literal string, not a dynamic badge, so update it to `✦` directly
3. Move the badge from its current inline position (appended after the state name with two spaces, in `_box_inner_lines` at line 91) to the **top-right corner** of the state box. The top border is assembled cell-by-cell in `_draw_box:510–517` (`layout.py`): `grid[row][col]` = `┌`, `grid[row][col+j]` = `─` for j=1..width-2, `grid[row][col+width-1]` = `┐`. The cleanest approach:
   - Add a `badge: str = ""` keyword parameter to `_draw_box` (signature at line 494)
   - After drawing the `─` fill, overwrite cells at `col + width - 1 - display_width(badge)` through `col + width - 2` with badge characters, preserving `┐` at `col + width - 1`
   - Remove the badge from `_box_inner_lines` (lines 90–98) so it no longer appears on the name row
   - Compute a `box_badge: dict[str, str]` alongside `box_inner`/`box_width` in `_compute_box_sizes` and pass it through to both `_draw_box` call sites (line 898 in FSM diagram loop, line 1475 in linear path renderer)
4. Add a `_badge_display_width(badge: str) -> int` helper using `wcwidth` (or `wcswidth` from the `wcwidth` package) to compute the true terminal display width of each badge. Several badge characters are double-wide in most terminals (e.g., `━` U+2501, `►` U+25BA in `/━►`; `⟳` U+27F3 in `↳⟳`). All badge width calculations — in `_compute_box_sizes` (line 469), the pre-layout loop in `_render_fsm_diagram` (line 1397), and the `_draw_box` corner-placement offset — **must use `_badge_display_width` instead of `len()`**. Add `wcwidth` to the package dependencies in `scripts/pyproject.toml` if not already present.
5. After implementing, verify visually in a terminal that top-right badge placement is pixel-correct for all five badge strings.
6. No snapshot/golden-file tests assert on badge text — existing tests in `scripts/tests/test_ll_loop_display.py` check structural properties (box-drawing characters, state names) not exact badge strings. Run tests after changes to verify no regressions; no golden-file updates should be needed for the text change itself.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — primary badge rendering logic; 3 badge-construction sites:
  - `_box_inner_lines` (lines 82–87, placement at 90–98) — the only site that renders badges visually
  - `_compute_box_sizes` (lines 463–467, width used at 469) — width measurement only
  - `_render_fsm_diagram` pre-layout loop (lines 1387–1391, width used at 1397) — width estimation only
- `scripts/little_loops/cli/loop/_helpers.py` — hardcoded `[prompt]` literal at **line 337** (inside `f" -> {colorize('[prompt]', '2')} ..."`) in `run_foreground` live execution event handler; line 334 is `lines = action.strip().splitlines()` — the colorize call with the string is at 337

### Dependent Files (Callers/Importers)
- Any module importing from `little_loops.cli.loop.layout` (grep for `from .layout import` or `from little_loops.cli.loop.layout import`)

### Schema Reference
- `scripts/little_loops/fsm/schema.py:180` — `StateConfig` dataclass
  - `action_type: Literal["prompt", "slash_command", "shell", "mcp_tool"] | None = None` (line 214)
  - `loop: str | None = None` (line 230) — sub-loop states; confirmed `state.loop is not None` is the right check

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
- FEAT-659: Hierarchical FSM Loops — introduced sub-loop states (`loop:` field); these require the new `↳⟳` badge and a pre-check before `_ACTION_TYPE_BADGES` lookup since `action_type` is `None` for sub-loop states
- BUG-730: Transition lines occlude state boxes in FSM box diagram (sibling diagram visual issue)
- ENH-731: Rename FSM transition labels success/fail → yes/no (related diagram label cleanup)

---
## Verification Notes

- **Date**: 2026-03-14
- **Verdict**: NEEDS_UPDATE
- Feature not yet implemented; no `_ACTION_TYPE_BADGES` dict. Actual badge sites (verified 2026-03-15): `layout.py` lines 82–98, 463–469, and **1387–1397** (not 1367 as stated in prior notes). Fourth site: `_helpers.py:334` (hardcoded literal `[prompt]`). Action type for mcp is `mcp_tool` (per `schema.py:211`), not `mcp`.

## Resolution

Implemented 2026-03-18.

- Added `_ACTION_TYPE_BADGES` dict and `_SUB_LOOP_BADGE` constant to `layout.py`
- Added `_badge_display_width` (wcwidth), `_get_state_badge` helpers
- Updated `_draw_box` to place badge in top-right corner of top border
- Updated `_compute_box_sizes` to return `box_badge` dict and use `_badge_display_width` for width calculations
- Updated both `_draw_box` call sites to pass `badge=box_badge[sname]`
- Updated pre-layout width estimation to use `_get_state_badge` / `_badge_display_width`
- Removed badge from `_box_inner_lines` name row (badge now lives in border)
- Updated `_helpers.py` hardcoded `[prompt]` → `✦`
- Added `wcwidth>=0.2` to `pyproject.toml` dependencies
- Added `TestStateBadges` test class with 8 assertions; all 99 tests pass

## Status

Completed.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-03-18_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
_Resolved 2026-03-18: sub-loop badge standardized to `↳⟳`; `wcwidth` required for all badge width calculations._

### Outcome Risk Factors
- `_draw_box` plumbing: threading `box_badge` dict through `_compute_box_sizes` to two call sites adds mechanical change surface
- No test validation of new badges: existing tests won't catch regressions in badge string values; consider adding a minimal assertion

## Session Log
- `/ll:ready-issue` - 2026-03-18T21:08:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3fec43af-cec2-467f-a768-5983e0362e95.jsonl`
- `/ll:ready-issue` - 2026-03-18T21:07:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3fec43af-cec2-467f-a768-5983e0362e95.jsonl`
- `/ll:confidence-check` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99fb3108-5258-4dd7-a41c-e5235bf3351d.jsonl`
- `/ll:confidence-check` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/deac850f-4f1f-4d78-b685-fb9e12887a16.jsonl`
- `/ll:refine-issue` - 2026-03-18T20:22:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/deac850f-4f1f-4d78-b685-fb9e12887a16.jsonl`
- `/ll:refine-issue` - 2026-03-16T02:01:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73de97cd-c70a-4e30-a624-ccf2502dd5ce.jsonl`
- `/ll:format-issue` - 2026-03-16T00:58:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8bc41a61-b249-4f82-b1e4-50bab87ac931.jsonl`
- `/ll:format-issue` - 2026-03-15T00:00:00Z - auto
- `/ll:verify-issues` - 2026-03-15T00:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:capture-issue` - 2026-03-13T22:51:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34ee1913-aa14-4e60-9d80-efda0df3efc0.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa4d2baf-3524-4c44-a9ad-16fe76a5f6b8.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/542b29e8-0de5-4f06-8439-bc467dc3bdab.jsonl`
- `/ll:ready-issue` - 2026-03-18T21:08:35Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
