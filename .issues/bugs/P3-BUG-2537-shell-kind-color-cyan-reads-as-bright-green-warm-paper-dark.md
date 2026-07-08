---
id: BUG-2537
title: shell kind-color cyan renders as bright green on warm-paper dark palette — recede
  via bright-black
type: BUG
priority: P3
status: done
captured_at: '2026-07-08T00:29:16Z'
completed_at: 2026-07-08 00:29:16+00:00
discovered_date: 2026-07-08
discovered_by: manual-investigation
testable: true
decision_needed: false
confidence_score: 100
outcome_confidence: 90
score_complexity: 8
score_test_coverage: 10
score_ambiguity: 5
score_change_surface: 6
---

# BUG-2537: shell kind-color cyan reads as bright green on warm-paper dark palette

## Summary

Follow-up to **BUG-2536**. After the per-kind color system landed, FSM box
outlines for `action_type: shell` (and bare `action:` which defaults to shell
hue) render in SGR cyan (`36`). On the project's active `warm-paper` design
token set to `dark` theme (per `.ll/ll-config.json`), cyan reads visually as
**bright green** to the user — distracting for the most common state kind in
shell-heavy loops like `rn-implement` / `autodev`.

## Current Behavior

`ll-loop run <shell-heavy-loop> --show-diagrams clean` shows every `shell:`
state box bordered and named in a color that the user perceives as bright
green rather than cyan. The user reported it as "the green for prompt/Skill
fsm states is distracting" before realizing cyan was the actual SGR code.

## Expected Behavior

`shell:` boxes render in a hue that:
1. Recedes visually against the dark-theme background palette.
2. Stays distinct from the other three kind hues (`34` blue, `35` magenta,
   `33` yellow) so the kind-color signal is preserved.
3. Does not render greenish on the project's warm-paper dark palette.

## Steps to Reproduce

1. Confirm the active palette (per `.ll/ll-config.json`):
   `design_tokens.active = "warm-paper"`, `design_tokens.active_theme = "dark"`.
2. Identify any loop with multiple `action_type: shell` states — e.g.
   `rn-implement` / `autodev` / `rn-remediate`.
3. Render the diagram in the active palette:
   ```bash
   ll-loop run rn-implement --show-diagrams clean --dry-run
   ```
4. Observe: each `shell:` state box border and name-row text appears in a
   **bright-green-tinted hue** rather than the intended cyan.
5. Capture the raw SGR stream to confirm:
   ```bash
   FORCE_COLOR=1 ll-loop run rn-implement --show-diagrams clean --dry-run \
     | cat -v | grep -aoE $'\033\[3[0-9]m' | sort -u
   ```
   Observe: `\033[36m` (cyan) is the only 4-bit hue emitted for shell boxes
   — the user's terminal palette is responsible for the green-cast read.

## Root Cause

`_ACTION_TYPE_KIND_COLORS["shell"] = "36"` at `layout.py:128` was inherited
from BUG-2536's kind-color table. Standard 4-bit SGR `36` is cyan, but
`warm-paper dark` terminal palettes commonly remap cyan toward mint/green.
No code-level error; an aesthetic palette clash.

## Resolution Applied

Single-value substitution: `"36"` → `"90"` (bright black, reads as gray on
most palettes including warm-paper dark). The kind-color signal is
preserved (still distinct from blue/magenta/yellow) and the hue no longer
collides with the active-state highlight green (`highlight_color` default
`"32"`).

| State kind | Before | After |
|---|---|---|
| `action_type: shell` (or bare `action:`) | `\033[36m` (cyan → green-cast) | `\033[90m` (bright black / gray) |
| `action_type: slash_command` | `\033[34m` (blue) | unchanged |
| `action_type: prompt` | `\033[35m` (magenta) | unchanged |
| `action_type: mcp_tool` | `\033[33m` (yellow) | unchanged |
| `loop:` sub-FSM | `\033[35m` (magenta) | unchanged |
| Terminal | `\033[2m` (dim) | unchanged |

## Location

- **File**: `scripts/little_loops/cli/loop/layout.py:128` — `_ACTION_TYPE_KIND_COLORS["shell"]`
- **Files**: `scripts/tests/test_cli_loop_layout.py` — three test assertions updated to match the new SGR code:
  - `TestBoxKindColor::test_shell_explicit_maps_to_bright_black` (renamed from `..._to_cyan`)
  - `TestBoxKindColor::test_bare_action_defaults_to_shell` (assertion updated)
  - `TestDiagramKindColors::test_kind_colors_appear_without_highlight` (renders `\033[90` instead of `\033[36` for shell box borders)

## Acceptance Criteria

- [x] `_ACTION_TYPE_KIND_COLORS["shell"]` is `"90"`, not `"36"`.
- [x] `test_shell_explicit_maps_to_bright_black` asserts `"90"`.
- [x] `test_bare_action_defaults_to_shell` asserts `"90"`.
- [x] `test_kind_colors_appear_without_highlight` asserts `\033[90` in the
      rendered diagram (no remaining `\033[36`).
- [x] Other kind colors unchanged: `slash_command=34`, `prompt=35`, `mcp_tool=33`.
- [x] `test_cli_loop_layout.py` + `test_ll_loop_display.py` → all 333 tests pass.

## Verification

```bash
python -m pytest scripts/tests/test_cli_loop_layout.py::TestBoxKindColor -v
# 10 passed

python -m pytest scripts/tests/test_cli_loop_layout.py scripts/tests/test_ll_loop_display.py -q
# 333 passed in 1.62s
```

## Impact

- **Priority**: P3 — cosmetic. The diagram still renders color-correctly; only
  one hue clashes with the active palette. Users on other palettes (light,
  default macOS Terminal, alacritty default) may not notice the change.
- **Effort**: Trivial — one data-table substitution + three test assertion
  edits. No runtime or threading changes.
- **Risk**: Negligible. The change is local to the shell kind. If a contributor
  prefers cyan, they can change one value in `_ACTION_TYPE_KIND_COLORS`.

## Related Issues

- **BUG-2536** — introduced `_ACTION_TYPE_KIND_COLORS`. This issue is its
  palette-tuning follow-up; the kind-color mechanism itself is unchanged.
- **Future ENH (suggested, not captured)**: implement the `clean` /
  `slim` preset's "single dim gray" gate that BUG-2536's commit message
  claimed via `TestMinimalPresetDimming` but never wired. That gate would
  pass `kind_color=None` whenever `facets.state_detail == "title"`, making
  the `clean` preset genuinely quiet across all palettes — a broader fix
  for palette-specific color clashes in general.

## Status

done

## Resolution

`_ACTION_TYPE_KIND_COLORS["shell"]` (`scripts/little_loops/cli/loop/layout.py:128`)
changed from `"36"` (cyan) to `"90"` (bright black / gray). Three tests in
`scripts/tests/test_cli_loop_layout.py` updated to assert the new value.
333 tests in the affected suites pass.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-08T00:29:41 - `f3262ea7-2180-4465-8c25-488246e710df.jsonl`

- `/ll:capture-issue` 2026-07-08T00:29Z — capture BUG-2537 after the
  one-line palette fix (`shell: 36 → 90`) and three test updates landed on
  `f5-backlog`. Commit: not yet authored.
