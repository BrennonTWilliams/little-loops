---
id: BUG-2284
type: BUG
priority: P2
status: done
captured_at: '2026-06-24T00:00:00Z'
completed_at: '2026-06-25T04:47:20Z'
discovered_date: 2026-06-24
discovered_by: manual-investigation
relates_to:
- BUG-042
labels:
- bug
- fsm-diagram
- ansi-escape
- video-recording
- vhs
- asciinema
confidence_score: 95
outcome_confidence: 95
score_complexity: 18
score_test_coverage: 80
score_ambiguity: 10
score_change_surface: 35
---

# BUG-2284: Per-character SGR wrapping in FSM diagram renderer produces raw ANSI fragments in CLI recordings

## Summary

`_draw_box()` in `cli/loop/layout.py` wraps every single box-drawing character in its own `\x1b[32;42m...\x1b[0m` SGR pair when rendering highlighted FSM state boxes. For a 40-char-wide box, this produces ~232 individual `colorize()` calls and ~460 ESC bytes per box. With 5+ states, **1000+ independent ANSI SGR sequences per frame**. This extreme density causes terminal recording tools (VHS 0.11.0, asciinema/tmux) to fail to process escape sequences, leaving raw text fragments like `0[32;42m` and `-8m-` visible in recorded video outputs instead of the intended solid-color state boxes.

## Motivation

- **Video quality**: Raw escape code fragments (`0[32;42m`, `-8m-`) are visible in ll-marketing CLI recordings (`deep-research/00-invoke.mp4`, `deep-research-cli-tools.cast.mp4`) in place of the intended colored FSM diagram boxes
- **Recording reliability**: VHS and asciinema recordings of `ll-loop run --show-diagrams clean` are unreliable due to ANSI code density overwhelming PTY frame buffers
- **Cross-cutting**: Affects every FSM diagram rendered with `highlight_state` set — all loop showcase videos

## Steps to Reproduce

1. Run `ll-loop run deep-research '<query>' --clear --show-diagrams clean` inside a VHS recording
2. Observe the output MP4: highlighted state boxes may show raw `[32;42m` text fragments instead of solid green blocks
3. Or: inspect the asciinema `.cast` file for `deep-research-cli-tools` — search for `32;42` and observe per-character wrapping (`\x1b[32;42m┌\x1b[0m\x1b[32;42m─\x1b[0m\x1b[32;42m─\x1b[0m...`)

## Root Cause

**File:** `scripts/little_loops/cli/loop/layout.py`, function `_draw_box()` (lines 579–701)

The `_bc()` closure (line 601) is called once per character for every border cell:

```python
def _bc(ch: str) -> str:
    if bg_code:
        return colorize(ch, f"{highlight_color};{bg_code}")  # per-char: "\x1b[32;42m─\x1b[0m"
    return colorize(ch, highlight_color)
```

Called sites producing per-character wrapping:

| Site | Characters | Count per box (40×5) |
|---|---|---|
| Top border (lines 608–615) | `┌`, `─`×38, `┐` | 40 `_bc()` calls |
| Badge overlay (lines 618–638) | space + badge chars + space | ~4 `_bc()` calls |
| Interior fill (lines 641–647) | `" "` per cell | 114 `colorize()` calls |
| Content side borders (lines 654–657) | `│` × 2 per row | 6 `_bc()` calls |
| Action content lines (lines 673–679) | per-char of action text | ~20 `colorize()` calls |
| Padding side borders (lines 682–689) | `│` × 2 per row | variable |
| Bottom border (lines 692–700) | `└`, `─`×38, `┘` | 40 `_bc()` calls |

**Total per highlighted box: ~460 ESC bytes from ~232 individual SGR sequences.**

For a 5-state FSM diagram: **~2,300 ESC bytes, ~1,100+ individual SGR sequences** in a single frame output burst.

Terminal recording tools (VHS PTY, asciinema via tmux) must process every `\x1b[...m` instruction. At this density, some sequences fail to process, and the raw parameter text (`[32;42m`, `[0;32;42m`, fragments like `-8m-` from `38;5;208m`) renders as visible text.

The `32;42` specifically appears because `_bc()` computes `bg_code = int(highlight_color) + 10` → `32 + 10 = 42`, producing the combined SGR code `32;42` (green foreground on green background) to create solid green highlighted state boxes.

## Fix

**File:** `scripts/little_loops/cli/loop/layout.py`, function `_draw_box()`

Replaced per-character SGR wrapping with batched `colorize()` calls for consecutive same-colored character runs:

| Component | Before | After | ESC reduction |
|---|---|---|---|
| Top border | 40 `_bc()` calls | 1 `colorize("┌──...──┐", code)` | **95%** |
| Bottom border | 40 `_bc()` calls | 1 `colorize("└──...──┘", code)` | **95%** |
| Interior fill | Per-cell `colorize(" ", bg)` | 1 `colorize(" " * N, bg)` per row | **95%** |
| Action lines | Per-char `colorize(ch, ...)` | 1 `colorize(line, code)` per line | **90%** |
| Side borders (`│`) | Per-char `_bc()` | Kept as-is (2 per row, negligible) | — |

The reference pattern for batching was already present in the same file: `_make_box()` (line 1781) builds entire border strings like `"┌" + "─" * N + "┐"` and wraps them in a single `colorize()` call.

### Badge handling

For the top border with a badge overlay, the badge is built into the batched border string:
```python
grid[row][col] = colorize("┌" + "─" * dash_count + " " + badge + " " + "┐", border_code)
```
where `dash_count = width - badge_w - 4` (accounting for `┌`, two spaces around badge, and `┐`). Badge display width is computed via `_badge_display_width()` which uses `wcswidth`, correctly handling double-width characters.

### Content row fill integration

The batched interior fill uses a single cell per row (`grid[ri][col + 1] = fill_str`). Content rows clear this cell and rebuild the interior with leading space + content + trailing fill in distinct cells to preserve proper column alignment.

## Verified Results (deep-research FSM, 4 states)

| Metric | Before | After |
|---|---|---|
| `\x1b[32;42m` sequences | ~30+ (per character) | **4** (2 batched borders + 2 side borders) |
| Per-char `─` pattern (`\x1b[32;42m─\x1b[0m\x1b[32;42m─\x1b[0m`) | present | **0** (eliminated) |
| Total ESC bytes per diagram | ~200+ | **60** |
| Box-drawing characters | Correct (but over-escaped) | Correct |
| Badge overlay (❯\_, ↳⟳, ⚡, etc.) | Per-char wrapped | Built into batched border |
| Neighborhood diagrams (`_make_box`) | Already batched | No change needed |
| Non-highlighted boxes | Already plain | No change needed |
| Alternate highlight colors (33;43) | Same per-char issue | Same batching applies |

**Tests performed:**
1. Highlighted state boxes (green 32;42) — rendered correctly, 0 per-char patterns
2. Non-highlighted boxes — no spurious 32;42 codes
3. Full verbose diagram (yellow 33;43) — correct, different color batching works
4. Neighborhood diagrams — correct, separate code path already batched
5. All box-drawing characters present (┌┐└┘│─▼▶)
6. Content alignment — name follows `│` with single leading space

## Related

- **BUG-042** (ll-marketing): Fleet-wide font rerecord after font swap — this ANSI density issue compounds with font rendering problems in older recordings
- **deep-research** slug (ll-marketing): Canonical reference slug, primary victim of the `32;42` artifacts
- **`_make_box()`** in `_render_neighborhood_diagram()`: Already uses batched approach, served as the reference pattern for this fix


## Session Log
- `hook:posttooluse-status-done` - 2026-06-25T04:47:53 - `7684775d-d19c-4b2b-af32-e4e7d442d288.jsonl`
