---
id: BUG-2042
title: "ll-init parity gaps \u2014 deploy_design_tokens, history.session_digest, and\
  \ explore-api permission not wired"
type: BUG
status: done
priority: P2
discovered_date: 2026-06-09
completed_at: 2026-06-09 15:50:23+00:00
discovered_by: manual-review
parent: EPIC-1978
blocks:
- ENH-1982
relates_to:
- FEAT-1979
- FEAT-1980
labels:
- init
- parity
- bug
confidence_score: 100
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# BUG-2042: ll-init parity gaps — deploy_design_tokens, history.session_digest, and explore-api permission not wired

## Summary

Three silent functional regressions in the Python `ll-init` implementation vs. the
`/ll:init` skill spec. All three exist in `scripts/little_loops/init/` and must be
fixed before ENH-1982 can safely delete the prose skill wizard.

## Current Behavior

Three silent omissions in the `scripts/little_loops/init/` package:

1. `deploy_design_tokens` is implemented in `writers.py` but never called from `cli.py:_run_yes` or `tui.py:_apply_config` — design-token profile files are never copied even when `design_tokens.enabled: true`.
2. `build_config` in `core.py` produces no `history` key — newly generated configs silently omit `history.session_digest` rather than explicitly recording it with the default `enabled: true`.
3. `merge_settings` in `writers.py` accepts `extra_permissions` but neither `_run_yes` nor `_apply_config` passes `["Skill(ll:explore-api)"]` when learning tests are enabled.

## Expected Behavior

- `ll-init --yes` with a template enabling design tokens copies profiles to `.ll/design-tokens/profiles/`.
- `ll-init --yes` produces a config with `history.session_digest.enabled: true`.
- `ll-init --yes` with learning tests enabled adds `"Skill(ll:explore-api)"` to `.claude/settings.local.json`.
- The interactive TUI (`_apply_config`) satisfies the same three criteria.

## Steps to Reproduce

1. Run `ll-init --yes` using a template that sets `design_tokens.enabled: true`.
2. Observe: `.ll/design-tokens/profiles/` is not created/populated.
3. Inspect the generated `.ll/ll-config.json` — no `history` key is present.
4. Run `ll-init --yes` with `learning_tests.enabled: true`; inspect `.claude/settings.local.json` — `"Skill(ll:explore-api)"` is absent from the allow list.

## Root Cause

Three separate call-site omissions in the `init` package:

- **File**: `scripts/little_loops/init/cli.py` — **Anchor**: `_run_yes` — `deploy_design_tokens(ll_dir, templates_dir)` is never called after `deploy_goals`.
- **File**: `scripts/little_loops/init/tui.py` — **Anchor**: `_apply_config` — same omission.
- **File**: `scripts/little_loops/init/core.py` — **Anchor**: `build_config` — the output dict never includes a `history` key.
- **File**: `scripts/little_loops/init/cli.py` and `tui.py` — **Anchor**: `merge_settings` call sites — `extra_permissions` argument is never passed when learning tests are enabled.

## Gaps

### 1. `deploy_design_tokens` never called (`cli.py`, `tui.py`)

`writers.py:deploy_design_tokens` (line 226) is implemented but never invoked.

- `_run_yes` (`cli.py:64`) doesn't call it — if the template or `--yes` flow
  sets `design_tokens.enabled: true`, the profile files are never copied.
- `_apply_config` (`tui.py:328`) also omits the call — even when the user
  selects "Design tokens" in Screen 2, the profiles are silently absent from
  `.ll/design-tokens/profiles/`.

**Fix**: add `deploy_design_tokens(ll_dir, templates_dir)` after `deploy_goals`
in both `_run_yes` and `_apply_config`, guarded by
`config.get("design_tokens", {}).get("enabled")`.

### 2. `history.session_digest` not written to generated config (`core.py`)

`build_config` (`core.py:21`) never writes a `history` section. The skill always
writes:
```json
"history": { "session_digest": { "enabled": true, "days": 7, "char_cap": 1200 } }
```
(Round 9.5 of the interactive wizard; the default is now `enabled: true`).
New configs produced by `ll-init` silently inherit whatever the plugin default is
rather than explicitly recording the user's intent.

**Fix**: add `history.session_digest` to `build_config` with the same defaults.
Consider a `session_digest_enabled` choice key (default `True`) to allow the TUI
to toggle it in a future screen.

### 3. `Skill(ll:explore-api)` permission not added for learning-tests configs

The skill (Step 10) inserts `"Skill(ll:explore-api)"` into
`.claude/settings.local.json` when `LEARNING_TESTS_ENABLED=true`. `merge_settings`
in `writers.py` already accepts `extra_permissions`, but neither `_run_yes` nor
`_apply_config` passes it.

**Fix**: in both call sites, pass
`extra_permissions=["Skill(ll:explore-api)"]` to `merge_settings` when
`config.get("learning_tests", {}).get("enabled")` is true.

## Files to Change

| File | Change |
|------|--------|
| `scripts/little_loops/init/cli.py` | Call `deploy_design_tokens` in `_run_yes`; pass `extra_permissions` to `merge_settings` |
| `scripts/little_loops/init/tui.py` | Call `deploy_design_tokens` in `_apply_config`; pass `extra_permissions` to `merge_settings` |
| `scripts/little_loops/init/core.py` | Add `history.session_digest` section to `build_config` output |

## Acceptance Criteria

- `ll-init --yes` with a template that enables design tokens deploys
  `templates/design-tokens/profiles/` to `.ll/design-tokens/profiles/`.
- `ll-init --yes` produces a config with `history.session_digest.enabled: true`.
- `ll-init --yes` with learning tests enabled writes `"Skill(ll:explore-api)"`
  into the settings allow list.
- TUI (interactive) path satisfies the same three criteria.
- Existing tests pass; new unit tests cover each branch.

## Impact

- **Priority**: P2 — blocks ENH-1982 (skill deprecation is unsafe until parity holds).
- **Effort**: Small (three localized call-site additions + one `build_config` line).
- **Risk**: Low — all writer functions already exist and are tested.

## Status

**Open** | Created: 2026-06-09 | Priority: P2


## Resolution

Fixed three call-site omissions in `scripts/little_loops/init/`:

1. **`core.py:build_config`**: Added `history.session_digest` section (enabled=True, days=7, char_cap=1200) with `session_digest_enabled` choice key.
2. **`cli.py:_run_yes`**: Added `deploy_design_tokens` call guarded by `design_tokens.enabled`; passes `extra_permissions=["Skill(ll:explore-api)"]` to `merge_settings` when `learning_tests.enabled`.
3. **`tui.py:_apply_config`**: Same two additions as cli.py.

New unit tests: `TestBuildConfig::test_history_session_digest_*` (3), `TestMainInit::test_yes_deploys_design_tokens_when_enabled`, `TestMainInit::test_yes_adds_explore_api_permission_when_learning_tests`, `TestHappyPath::test_design_tokens_selected_deploys_profiles`, `TestHappyPath::test_learning_tests_adds_explore_api_permission`.

## Session Log
- `/ll:ready-issue` - 2026-06-09T15:43:15 - `76321915-d9bd-42c3-b0f4-d22861417203.jsonl`
- `/ll:format-issue` - 2026-06-09T15:35:30 - `40fc9d4a-b459-4aa0-bbce-9d6e904df2fa.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00 - `b09a5a68-6cd2-4934-b07a-972c01dc416b.jsonl`
- `/ll:manage-issue` - 2026-06-09T15:50:23Z - implemented BUG-2042
