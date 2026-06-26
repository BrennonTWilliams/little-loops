---
id: BUG-2321
title: "Autoprompt enabled-default mismatch silently disables feature on standard installs"
type: bug
priority: P2
status: open
captured_at: "2026-06-26T22:30:26Z"
discovered_date: "2026-06-26"
discovered_by: capture-issue
labels: [hooks, prompt-optimization, config, init, default-resolution]
---

# BUG-2321: Autoprompt enabled-default mismatch silently disables feature on standard installs

## Summary

The auto-prompt-optimization feature (`UserPromptSubmit` hook) is documented as
**default-on**, but the runtime handler treats an absent `prompt_optimization`
block as **disabled**. Because `ll-init` only writes the block when the user
*opts out*, a standard install (and this very repo) ends up with no block at
all — so autoprompt silently does nothing despite the schema/docs claiming it
is enabled by default. The full hook machinery is wired and functional; it is
gated off by a default-resolution disagreement across three sources.

## Steps to Reproduce

1. Run `ll-init` and keep prompt optimization enabled (the default) — observe
   that no `prompt_optimization` block is written to `.ll/ll-config.json`
   (see `scripts/little_loops/init/core.py:105-107`).
2. Submit a vague prompt (≥10 chars, not a slash command) so the
   `UserPromptSubmit` hook fires.
3. Observe that **no** optimization context is injected — the prompt passes
   through untouched.

Empirical confirmation in this repo (config has no `prompt_optimization` block):

```bash
$ echo '{"prompt":"fix the authentication bug somewhere in the code"}' \
    | python -m little_loops.hooks user_prompt_submit
# (empty stdout — nothing injected, exit 0)
```

Force-enabling the block makes it work (emits the full ~3161-char rendered
`optimize-prompt-hook.md` template), proving the plumbing itself is sound.

## Current Behavior

Three sources disagree on the default:

| Source | Behavior when block is absent |
|---|---|
| `config-schema.json:585-589` | documents `enabled` default = **`true`** |
| `scripts/little_loops/init/core.py:105-107` (*"default-on; only write when opting out"*) | writes **no block** |
| `scripts/little_loops/hooks/user_prompt_submit.py:102` — `prompt_opt.get("enabled", False)` | reads absence as **disabled** |

Net effect: on any install where the user did not explicitly opt out, the
config has no `prompt_optimization` key, and the runtime defaults it off. The
feature is dormant for all standard installs.

## Expected Behavior

The effective default must be consistent across schema, `ll-init`, and the
runtime handler. Either:

- **(A)** The handler honors the documented default-on: treat an absent block
  (and absent `enabled` key) as `enabled = true`, matching
  `config-schema.json` and the `init/core.py` "only write when opting out"
  convention; **or**
- **(B)** `ll-init` always writes an explicit `prompt_optimization.enabled`
  value so the runtime never has to infer a default, and the schema default is
  updated to match whatever shipped behavior is intended.

Whichever is chosen, a vague prompt on a fresh default install should produce
the behavior the docs promise (inject the optimization template / show the
diff with `confirm: true`).

## Root Cause

`scripts/little_loops/hooks/user_prompt_submit.py:102`:

```python
if not prompt_opt.get("enabled", False):
    return LLHookResult(exit_code=0)
```

`_load_config` (`user_prompt_submit.py:50-58`) does a raw `json.loads` of the
config file and applies **no** schema defaults, so when the
`prompt_optimization` block is absent, `prompt_opt` is `{}` and
`.get("enabled", False)` resolves to `False`. This contradicts both the schema
default (`true`) and the `init/core.py` comment that explicitly assumes
"default-on; only write when opting out" — that comment is only correct if a
*consumer* supplies the `true` default, which the handler does not.

## Proposed Fix

Prefer **(A)** for least surprise and to match the existing schema/init intent:

1. Change `user_prompt_submit.py:102` to default-on, e.g.
   `if not prompt_opt.get("enabled", True):` — or route the check through the
   shared `feature_enabled(...)` helper (used elsewhere in the same file for
   `analytics.enabled`) so default resolution is centralized and consistent
   with how other feature flags are evaluated.
2. Decide the bypass-guard ordering relative to the enabled check is preserved
   (slash/`*`/`#`/`?`/short-prompt guards still short-circuit first).
3. If **(B)** is preferred instead, update `init/core.py:105-107` to always
   write `prompt_optimization.enabled` and reconcile the schema default.

## Integration Map

- `scripts/little_loops/hooks/user_prompt_submit.py:99-103` — enabled gate (the bug site)
- `scripts/little_loops/init/core.py:105-107` — init write-on-opt-out logic
- `config-schema.json:585-589` — schema `enabled` default
- `hooks/hooks.json:17-28` → `hooks/scripts/user-prompt-check.sh` → `python -m little_loops.hooks user_prompt_submit` (delivery path; confirmed working)
- `scripts/little_loops/hooks/prompts/optimize-prompt-hook.md` — injected template (rendered correctly when enabled)

## Implementation Steps

1. Pick resolution strategy (A) or (B); (A) recommended to honor documented default-on.
2. Apply the one-line default change (or centralize via `feature_enabled`).
3. Add a unit test in `scripts/tests/test_hook_user_prompt_submit.py` asserting:
   - absent `prompt_optimization` block → template **is** injected for a vague prompt;
   - `enabled: false` → no injection;
   - bypass guards still short-circuit regardless of enabled state.
   (Note: that test file currently only covers the analytics/correction write
   path — the optimization gate is untested, which is why this regressed
   unnoticed.)
4. Reconcile schema/init so all three sources agree on the effective default.

## Impact

- **Severity**: A documented default-on feature is silently inert for every
  standard install, including the source repo. Users believe autoprompt is
  active; it is not, with no error or signal.
- **Blast radius**: All installs without an explicit `prompt_optimization`
  block. No data loss; purely a missing-feature/silent-no-op condition.
- **Detection difficulty**: High — fails open with exit 0 and empty stdout, so
  nothing distinguishes "disabled by design" from "disabled by this bug."

## Related Key Documentation

| Document | Relevance |
|---|---|
| `config-schema.json` | Declares the `enabled` default (`true`) that the runtime contradicts |
| `.claude/CLAUDE.md` (CLI Tools / hooks) | Describes hook intents and `toggle-autoprompt` |
| BUG-181, BUG-868, BUG-361 (all `done`) | Prior autoprompt breakage history; this is a distinct default-resolution defect |

## Labels

hooks, prompt-optimization, config, init, default-resolution

## Session Log
- `/ll:capture-issue` - 2026-06-26T22:30:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67adb916-4f2d-4717-9406-52734035f867.jsonl`

## Status
open
