---
discovered_date: 2026-03-05
discovered_by: manual-audit
confidence_score: 95
outcome_confidence: 95
---

# ENH-591: Fix Output Styling Consistency in `ll-issues` CLI

## Summary

Three consistency gaps in the `ll-issues` CLI were identified and fixed: missing `configure_output()` initialization (silently ignoring user color config), a direct `shutil.get_terminal_size()` call bypassing the canonical `terminal_width()` abstraction, and plain-text issue ID/priority output in `sequence` that was inconsistent with the colorized `list` subcommand.

## Current Behavior

1. **`ll-issues` never called `configure_output()`** — User color overrides in `ll-config.json` (via `cli:` config key) were silently ignored for all `ll-issues` subcommands, including `list` which imports `PRIORITY_COLOR`/`TYPE_COLOR`.
2. **`refine_status.py` called `shutil.get_terminal_size().columns` directly** — Bypassed the `terminal_width()` abstraction in `output.py`, which is the single source of truth for terminal width (used by all other width-aware CLI modules).
3. **`sequence.py` printed issue IDs and priorities as plain text** — Inconsistent with `list_cmd.py`, which colorizes them by type and priority using `colorize()` + `PRIORITY_COLOR`/`TYPE_COLOR`.

## Resolution

### 1. `cli/issues/__init__.py` — Bug fix

Added `configure_output(config.cli)` call immediately after `BRConfig` is loaded, before any subcommand dispatch. This mirrors the pattern used in `cli/auto.py`, `cli/parallel.py`, and `cli/loop/__init__.py`.

### 2. `cli/issues/refine_status.py` — Code quality

Replaced `import shutil` and `shutil.get_terminal_size().columns` with `from little_loops.cli.output import terminal_width` and `terminal_width()`. `shutil` import removed entirely.

### 3. `cli/issues/sequence.py` — Enhancement

Added `from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize`. In the per-issue print loop, derived the type prefix from `issue.issue_id.split("-", 1)[0]` (same pattern as `list_cmd.py`) and colorized both the issue ID and priority label before printing.

## Files Changed

- `scripts/little_loops/cli/issues/__init__.py` — added `configure_output(config.cli)` after config load
- `scripts/little_loops/cli/issues/refine_status.py` — replaced `shutil.get_terminal_size()` with `terminal_width()`
- `scripts/little_loops/cli/issues/sequence.py` — added colorization of issue IDs and priority labels

## Verification

- `ruff check` passed (one import-sort fix auto-applied to `refine_status.py`)
- 280 relevant tests passed (`pytest -k "issues or sequence or refine"`)

## Impact

- **Priority**: P4 — Minor consistency/polish; no functional regression
- **Effort**: Minimal — three small, targeted edits
- **Risk**: None — purely additive; `NO_COLOR=1` suppresses all new color output via existing `colorize()` logic
