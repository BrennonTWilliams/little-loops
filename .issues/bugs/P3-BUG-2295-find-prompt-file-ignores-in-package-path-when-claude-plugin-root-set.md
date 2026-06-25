---
id: BUG-2295
type: BUG
priority: P3
status: done
captured_at: '2026-06-25T17:00:00Z'
completed_at: '2026-06-25T17:11:50Z'
discovered_date: 2026-06-25
discovered_by: run-tests
relates_to:
- BUG-2275
- FEAT-2274
labels:
- bug
- hooks
- path-resolution
- prompt-optimization
---

# BUG-2295: `_find_prompt_file` resolves wrong path when `CLAUDE_PLUGIN_ROOT` is set

## Summary

After FEAT-2274 moved `optimize-prompt-hook.md` into the package at
`scripts/little_loops/hooks/prompts/`, the `CLAUDE_PLUGIN_ROOT` env-var branch
in `_find_prompt_file()` (`user_prompt_submit.py`) was never updated. When
`CLAUDE_PLUGIN_ROOT` is set, the resolver returned
`$CLAUDE_PLUGIN_ROOT/hooks/prompts/optimize-prompt-hook.md` — the old pre-move
location — which no longer exists. The in-package fallback was never reached,
so prompt optimization silently produced no output whenever the plugin root env
var was present.

Discovered as `1 xfailed` in the test suite: `TestUserPromptCheck::test_optimization_template_injected_when_claude_plugin_root_set` was marked `strict=True` xfail for exactly this gap (BUG-2275 partial fix).

## Root Cause

`_find_prompt_file()` had an env-var-first branch that predated the in-package
move and was not updated when FEAT-2274 ran `git mv`. The in-package path
`Path(__file__).parent / "prompts" / "optimize-prompt-hook.md"` was correct
post-move but unreachable when `CLAUDE_PLUGIN_ROOT` was set.

## Fix

Removed the `CLAUDE_PLUGIN_ROOT` branch entirely. The in-package path is now
the sole resolver. Also removed the now-unused `import os`.

**Commit**: `dbe8e3a4 fix(BUG-2275): drop CLAUDE_PLUGIN_ROOT branch in _find_prompt_file`

## Files Changed

- `scripts/little_loops/hooks/user_prompt_submit.py` — simplified `_find_prompt_file()`, removed `import os`
- `scripts/tests/test_hooks_integration.py` — removed `@pytest.mark.xfail` from regression test

## Verification

`pytest scripts/tests/test_hooks_integration.py::TestUserPromptCheck::test_optimization_template_injected_when_claude_plugin_root_set` — **PASSED** (was XFAIL).

Full suite: **12,453 passed, 15 skipped, 0 xfailed** after the fix.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-25T17:12:33 - `192e7ffc-8aee-4a1a-9b96-fea3b948c278.jsonl`
