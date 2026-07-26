# CLI color palette policy

Why the CLI mixes basic-16 and indexed-256 ANSI codes on purpose, and when to
reach for each. Originated as a portability investigation into FSM box diagrams
rendering differently in Terminal.app vs. Ghostty+tmux; the investigation's
analysis held up, its headline recommendation did not. Both are recorded below.

Unless noted, references are to `scripts/little_loops/cli/loop/layout.py`.

## How the two code classes differ

| Class | Example | Resolves against |
|---|---|---|
| Basic 16-color | `31`, `32`, `33`, `34`, `35`, `36`, `90` | The emulator's theme palette |
| Indexed 256-color | `38;5;208`, `38;5;245` | Fixed xterm slots 16–255 |

Basic codes are not colors — they are aliases into the terminal's own palette.
`32` means "slot 2 of whatever palette this terminal is configured with," not any
particular green. So an identical byte stream resolves to different hues per
host:

- **Ghostty** — a `theme = light:…,dark:…` config makes `32` Gruvbox green,
  `33` Gruvbox yellow, and so on. With `window-theme = auto` the palette *also*
  flips with macOS light/dark mode, so output changes color within Ghostty alone.
- **Terminal.app** — resolves the same codes against its profile palette
  (Basic/Pro/etc.), nowhere near Gruvbox.

Indexed slots 16–255 are fixed by the xterm spec and are not theme-remappable,
which is why the orange/red escalation labels look the same in both terminals
while everything else tracks the theme.

### tmux is not the cause

With `default-terminal "tmux-256color"` plus `RGB` terminal features, tmux only
degrades *truecolor* (`38;2;r;g;b`) when RGB is unavailable; indexed and basic
codes pass through untouched. The drift reproduces in bare Ghostty vs. bare
Terminal.app.

The one genuine cross-emulator inconsistency is **SGR `2` (faint/dim)**, which is
optional in the spec and is rendered, ignored, or synthesized differently across
emulators and through tmux.

## Decision: theme-relativity is the design intent, not a defect

The original investigation recommended migrating every basic `31`–`36` code to
pinned indexed-256 equivalents for cross-terminal determinism. **That was
declined.**

Basic codes resolving against the user's theme is what ANSI is *for*. Pinning
buys cross-terminal agreement at the cost of per-user legibility — a
Solarized-light or high-contrast user would get Gruvbox-toned output regardless
of their configuration — and it defeats Ghostty's light/dark auto-flip, which the
investigation itself cited as a symptom. Byte-identical output across terminals
was never the goal; *legible, semantically consistent* output on each user's own
terminal is.

### The rule

- **Basic 16-color** for anything whose meaning maps onto a color the user
  already has an opinion about: success green, warning yellow, error red. These
  *should* look like the user's green/yellow/red.
- **Pinned indexed-256** only where basic-16 cannot express the distinction:
  1. **Graded ramps.** Basic-16 carries one red and one yellow, so a
     three-rung severity ramp is impossible. The exhaustion family is pinned:
     `rate_limit_exhausted` `38;5;214` (amber) → `retry_exhausted` `38;5;202`
     (deep orange) → `throttle_hard` `38;5;196` (vivid red).
  2. **Guaranteed non-collision.** Two grays that must stay distinguishable
     cannot both rely on where a theme happens to map bright-black. Shell boxes
     (`38;5;240`) and terminal-state boxes (`38;5;245`) are both pinned for this
     reason.
- **Never bare SGR `2`.** Use gray `90` for de-emphasis. Dim's rendering is
  optional, so de-emphasized text would sometimes not recede at all. `2` used as
  a *modifier* on a real color (`"33;2"`, `"0;2"` in `CATEGORY_COLOR`) is a
  different case and is fine.

Pure red `38;5;196` is reserved for `throttle_hard` alone, so it never competes
with theme red `31` to mean "the error color."

## What changed

**Background-fill bug (fixed).** `_draw_box` derived the highlight background by
integer arithmetic on the foreground code:

```python
bg_code: str | None = str(int(highlight_color) + 10)   # 32 -> 42
```

This only works for basic codes. `highlight_color` flows from the
user-configurable `config.cli.colors.fsm_active_state`, so anyone who had set a
256-color value there hit the `ValueError` path and **silently lost the
active-state background fill** — a live bug, independent of any migration.
Replaced by an explicit `_bg_of()` helper handling all three foreground forms.

Note this arithmetic appeared at **two** call sites, not one: `_draw_box` and
`nd_bg_code` in the neighborhood renderer. `_bg_of` returns `None` for basics
outside 30–37 / 90–97 (e.g. `"0"`, or a compound `"32;1"`), which callers already
treat as "no fill" — a deliberate tightening, since `int("0") + 10` previously
produced the invalid background `"10"`.

**SGR `2` eliminated.** All bare `"2"` codes across `cli/` replaced with `90`,
except `_TERMINAL_KIND_COLOR`, which took `38;5;245` — `90` was already claimed
by `shell`, and terminal and shell boxes must stay distinct.

**Shell pinned.** `shell` moved `90` → `38;5;240` so the shell/terminal gray gap
does not depend on where a theme maps bright-black.

**`retry_exhausted` de-collided.** Was `38;5;208`, identical to `no` — which
flattened a terminal failure into a routine negative branch. Now `38;5;202`, the
middle rung of the exhaustion ramp.

Config defaults live in **three** places and must be changed together:
`cli/output.py` (or `layout.py`), `config/cli.py` (both the dataclass field
default *and* the `from_dict()` fallback), and `config-schema.json`.
`configure_output()` overwrites the module-level dicts from config, so editing
the module alone is inert.

## Verification

Render a loop with `FORCE_COLOR=1` and dump the distinct escape sequences:

```sh
FORCE_COLOR=1 ll-loop show <loop> \
  | python3 -c "import re,sys;print(' '.join(sorted(set(re.findall(r'\x1b\[([0-9;]*)m', sys.stdin.read())))))"
```

The set must contain no bare `2`. It *should* still contain basic `31`–`36` and
`90` — those are intentional.

Current output for `docs-sync`:

```
0 1 31 32 35 35;1 38;5;208 38;5;240 38;5;240;1 38;5;245 38;5;245;1 90
```

## Corrections to the original investigation

- The background-fill arithmetic occurs at **two** sites, not one; the
  investigation flagged only `_draw_box`.
- The verification snippet cited `ll-loop info <loop>` — **no such subcommand**.
  It is `ll-loop show <loop>`.
- `cli/output.py`'s `CATEGORY_COLOR` was listed as needing the same treatment. It
  does not: it already carries hand-tuned 256 codes with comments recording which
  duplications are deliberate semantic groupings and which were actively
  rejected. It is the model the other maps now follow.

If the pinned-palette migration is ever revived, `_bg_of` has already removed the
blocker — it becomes a constant swap plus test updates.
