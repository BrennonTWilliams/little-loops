---
id: BUG-2042
title: ll-init parity gaps — deploy_design_tokens, history.session_digest, and explore-api permission not wired
type: BUG
status: open
priority: P2
discovered_date: 2026-06-09
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
---

# BUG-2042: ll-init parity gaps — deploy_design_tokens, history.session_digest, and explore-api permission not wired

## Summary

Three silent functional regressions in the Python `ll-init` implementation vs. the
`/ll:init` skill spec. All three exist in `scripts/little_loops/init/` and must be
fixed before ENH-1982 can safely delete the prose skill wizard.

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
