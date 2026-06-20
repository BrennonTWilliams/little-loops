---
id: ENH-2241
title: ll-init should surface decisions, scratch_pad, session_capture, and prompt_optimization toggles
type: enh
status: done
priority: P3
completed_at: 2026-06-20 05:01:15+00:00
labels:
- cli
- ll-init
- ux
relates_to:
- ENH-2240
---

# ENH-2241: ll-init should surface decisions, scratch_pad, session_capture, and prompt_optimization toggles

## Summary

Audited the `ll-init` wizard wiring against `config-schema.json` and `/ll:configure`
(the post-init config editor) to find opt-in feature toggles that the wizard never
exposed. Four genuine gaps were found and wired into both the interactive wizard and
the headless path:

| Toggle | Schema default | Why it was a gap |
|---|---|---|
| `decisions.enabled` | `false` | First-class opt-in feature with its own CLI (`ll-issues decisions`) + CLAUDE.md docs; exposed in `/ll:configure` but absent from init |
| `scratch_pad.enabled` | `false` | Automation observation-masking (ll-auto / ll-parallel); reachable only by hand-editing config |
| `session_capture.enabled` | `false` | Per-tool capture feeding PreCompact handoff snapshots |
| `prompt_optimization.enabled` | `true` | Default-on feature with no opt-out at init time |

Richer features that carry sub-config (`parallel`, `sync`, `documents`,
`design_tokens`, `confidence_gate`, `tdd`) remain interactive-only and were
intentionally excluded from the headless flags. Non-toggle / advanced areas
(`automation`, `sprints`, `continuation`, `events`, `orchestration`, `cli`,
`dependency_mapping`, etc.) remain `/ll:configure`-only by design.

## Changes

### Headless config builder — `scripts/little_loops/init/core.py`
`build_config()` now honors four new `choices` keys: `decisions_enabled`,
`scratch_pad_enabled`, `session_capture_enabled` (opt-in; section omitted when off)
and `prompt_optimization_enabled` (default-on; writes `{enabled: false}` only when
opted out). Docstring updated to list the new keys.

### Interactive wizard — `scripts/little_loops/init/tui.py`
- Added 3 opt-in checkbox entries to `_FEATURE_CHOICES` / `_FEATURE_LABELS`
  (Decisions & rules log, Scratch pad, Session event capture), left out of
  `_DEFAULT_FEATURES` so they default unchecked.
- Added a prompt-optimization opt-out confirm (default `True`) mirroring the existing
  `session_digest` confirm; threaded through `_build_final_config()` and routed into
  `build_config()` alongside the existing `*_enabled` choices.
- Summary panel surfaces each enabled new toggle (and prompt-optimization when off).

### Headless CLI flags — `scripts/little_loops/init/cli.py`
- Added repeatable `--enable FEATURE` / `--disable FEATURE` flags for the
  `--yes` / `--dry-run` / `--plan` paths, backed by a `_TOGGLEABLE_FEATURES`
  allowlist and a `_feature_choices_from_args()` translator.
- Validation: unknown feature names exit `2`; using the flags without a headless
  mode exits `2`. `--plan` output reflects the flags for parity.

### Gitignore — `scripts/little_loops/init/writers.py`
Added `.ll/ll-session-events.jsonl` (ephemeral, written by session_capture) to
`_GITIGNORE_ENTRIES`. `.ll/decisions.yaml` is intentionally NOT ignored — the
decisions log is meant to be committed.

### Docs — `docs/reference/CLI.md`
Documented the new `--enable`/`--disable` flags, the new wizard toggles in the
Features screen, and added usage examples.

## Files Modified

- `scripts/little_loops/init/core.py`
- `scripts/little_loops/init/tui.py`
- `scripts/little_loops/init/cli.py`
- `scripts/little_loops/init/writers.py`
- `scripts/tests/test_init_core.py` — `build_config` cases (on/off/default) for all four toggles + headless flag tests (`--enable`, `--disable`, unknown-name exit 2, mode-guard exit 2, `--plan` parity)
- `scripts/tests/test_init_tui.py` — `_wire_q` extended with `prompt_optimization`; wizard cases for the 3 opt-ins, omit-when-unselected, and prompt-optimization opt-out/default
- `docs/reference/CLI.md`

## Verification

- `python -m pytest scripts/tests/test_init_core.py scripts/tests/test_init_tui.py` — 210 passed (17 new).
- `scripts/tests/test_wiring_init_and_configure.py` — 88 passed, 1 skipped.
- `python -m mypy scripts/little_loops/init/` clean; `ruff check` / `ruff format` clean.
- End-to-end dry-run confirmed:
  - `ll-init --yes --dry-run --enable decisions --enable session_capture` → both sections written; no `prompt_optimization` key.
  - `ll-init --yes --dry-run --disable prompt_optimization` → `prompt_optimization.enabled: false`.
  - `ll-init --yes --dry-run --enable bogus` → exit `2` with "Unknown feature(s): bogus".

## Follow-ups

- **ENH-2240** (pre-populate wizard from existing config): when that lands, its
  checked-set logic should also pre-check these new toggles from existing config.

## Impact

- **Priority**: P3 — UX/discoverability improvement; opt-in features are now reachable at init time rather than only via `/ll:configure` or manual config edits.
- **Effort**: Small — wiring mirrored the existing `github_sync` / `session_digest` patterns; no schema changes.
- **Risk**: Low — additive; new toggles default off (or default-on opt-out), existing tests preserved.
- **Breaking Change**: No


## Session Log
- `hook:posttooluse-status-done` - 2026-06-20T05:02:12 - `eb21245b-b71b-4640-8819-0ebd78cd0c03.jsonl`
