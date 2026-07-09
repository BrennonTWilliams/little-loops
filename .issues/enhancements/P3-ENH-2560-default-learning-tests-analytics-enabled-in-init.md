---
type: ENH
id: ENH-2560
title: Default learning_tests and analytics to enabled in generated config
priority: P3
status: done
created: 2026-07-08
completed_at: 2026-07-09T04:06:16Z
labels: [config, init, cli]
---

# Default learning_tests and analytics to enabled in generated config

## Summary

When `ll-init` generated a project's `.ll/ll-config.json`, the `learning_tests`
and `analytics` sections were written with `enabled: false`. The interactive TUI
already pre-checked both features (`_DEFAULT_FEATURES` in
`scripts/little_loops/init/tui.py:31-33`), so the guided flow treated them as
on-by-default while the headless path (`ll-init --yes`, and any bare
`build_config()` call) wrote them as `false`.

The fix makes the single source of truth — `config-schema.json`'s declared
`default` for each flag — agree with the intended on-by-default behavior.
`build_config()` reads these via `schema_default()`
(`scripts/little_loops/init/core.py:128-144`), so flipping the schema defaults
makes every non-interactive init emit `enabled: true`, matching the TUI.

## Changes

### Source of truth — `scripts/little_loops/config-schema.json`
- `learning_tests.enabled`: `false` → `true`
- `analytics.enabled`: `false` → `true` (also removed the stale "Default off;
  opt-in until the ctx-stats CLI ships" note from the description)

Result: a freshly-initialized project gets `learning_tests: {enabled: true}` and
`analytics: {enabled: true, capture: {...}}` by default across both the
interactive and headless init paths. Verified end-to-end via `build_config()`.

### Scope decision — runtime fallbacks left unchanged
Per an explicit product decision (new configs only), the runtime feature-read
fallbacks were intentionally left at `False`:
- `LearningTestsConfig.enabled` dataclass default (`config/features.py`)
- `feature_enabled(config, "analytics.enabled")` for a missing key

A newly init'd config always writes the keys explicitly, so it is unaffected.
Leaving the fallbacks at `False` means existing projects that never had these
sections are **not** silently switched on when they upgrade — only new /
`ll-init`-regenerated configs get the on-by-default value. This avoids silently
enabling analytics data capture on upgrade.

### Tests / docs updated to the new default
- `scripts/tests/test_config_schema.py` — two `default is False` → `is True`
  (learning_tests.enabled, analytics.enabled).
- `scripts/tests/test_init_core.py` — renamed/flipped
  `test_learning_tests_disabled_by_default` and `test_analytics_disabled_by_default`
  to `...enabled_by_default`; fixed `test_schema_default_returns_real_default`.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — analytics default note `false` → `true`.

Left untouched (correctly): the dataclass-fallback test
`test_learning_tests_enabled_defaults_false`, the TUI `selected_set=set()`
disabled-when-not-selected test, and vestigial `analytics` blocks in template
JSON (never read by `build_config()`, which only pulls `project`/`issues`/`scan`
from a template).

## Verification

```bash
python -m pytest scripts/tests/test_init_tui.py scripts/tests/test_init_core.py \
  scripts/tests/test_config_schema.py scripts/tests/test_config.py \
  scripts/tests/test_hook_post_tool_use.py scripts/tests/test_hook_user_prompt_submit.py -q
# 666 passed
```

Headless emit check:

```python
from little_loops.init.detect import detect_project_type
from little_loops.init.core import build_config
from pathlib import Path
cfg = build_config(detect_project_type(Path('.'), None))
# cfg['learning_tests'] == {'enabled': True}
# cfg['analytics'] == {'enabled': True, 'capture': {...}}
```

## Files Changed

- `scripts/little_loops/config-schema.json`
- `scripts/tests/test_config_schema.py`
- `scripts/tests/test_init_core.py`
- `docs/guides/BUILTIN_HOOKS_GUIDE.md`


## Session Log
- `hook:posttooluse-status-done` - 2026-07-09T04:07:24 - `430cd13b-4e4b-40ca-91dd-50081361bb8b.jsonl`
