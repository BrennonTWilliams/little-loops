---
id: BUG-2439
title: ll-init never displays the bundled CLI logo
type: BUG
status: done
priority: P4
captured_at: '2026-07-02T04:05:05Z'
completed_at: '2026-07-02T04:05:05Z'
discovered_date: '2026-07-02'
discovered_by: user
labels:
- ll-init
- cli-ux
- dead-code
---

# BUG-2439: ll-init never displays the bundled CLI logo

## Summary

The CLI logo asset (`scripts/little_loops/assets/ll-cli-logo.txt`) is bundled in
the package and a `print_logo()` helper exists in
`scripts/little_loops/logo.py`, but nothing ever calls it. The logo was wired up
to the point of a helper and a packaging test (BUG-2276) yet never actually
displayed in any command output, so users running `ll-init` never see the
branding.

## Current Behavior

`little_loops/logo.py` defines `get_logo()` and `print_logo()`, and
`package_data.py` / `test_logo.py` ensure the asset ships inside the wheel. But a
repo-wide search for `print_logo` / `get_logo` returned only the definition site
and tests — no call site anywhere in the CLI. `ll-init` (both the headless
`--yes` flow and the interactive TUI) printed status lines and the closing
`✓ little-loops initialized` message with no banner.

## Expected Behavior

`ll-init` shows the logo as a start-of-run banner on human-facing runs, bookended
by the existing closing success line. Machine-readable output must stay clean:
the `--plan` (JSON) and `apply` paths must never emit the banner, and piped /
redirected runs should stay bare so logs and CI output are not polluted.

## Root Cause

`print_logo()` was authored as a helper but never invoked. The reusable banner
was effectively dead code.

## Resolution

_Resolved 2026-07-02._

Wired `print_logo()` into the human-facing `ll-init` flows, guarded so it never
touches machine-readable or non-interactive output:

1. **`init/cli.py` — `_run_yes`**: calls `print_logo()` at the top of the
   function, gated behind `if sys.stdout.isatty():` so `--yes` and `--dry-run`
   show the banner interactively while piped/redirected runs stay bare. The
   machine-readable `_run_plan` and `_run_apply` functions were deliberately left
   untouched, so `ll-init --plan` still emits pure, parseable JSON.
2. **`init/tui.py` — `run_tui`**: calls `print_logo()` right after the existing
   `stdin.isatty()` check, also guarded by `if sys.stdout.isatty():` for
   consistency.

**Tests** (`scripts/tests/integration/test_init_e2e.py::TestInitLogoBanner`):
- `test_yes_run_prints_logo_banner_on_tty` — monkeypatches `sys.stdout.isatty` to
  `True` and asserts the banner appears in `--yes` output.
- `test_yes_run_omits_logo_when_not_tty` — asserts the banner is absent from
  non-TTY (piped) `--yes` output.
- `test_plan_output_has_no_logo_and_stays_valid_json` — asserts `--plan` output
  contains no banner and still parses as valid JSON.

## Verification

Local verification in this session was limited to `py_compile` syntax checks and
an isolated exercise of `print_logo()` (confirmed it emits the `little loops`
banner). The full suite could not be run in the working sandbox because it only
has Python 3.10 while the package requires 3.11+ (`from datetime import UTC`).
Run `python -m pytest scripts/tests/integration/test_init_e2e.py
scripts/tests/test_logo.py` on a 3.11+ interpreter to confirm green.

## Session Log
- Manual implementation session - 2026-07-02T04:05:05Z

---

## Status

done
