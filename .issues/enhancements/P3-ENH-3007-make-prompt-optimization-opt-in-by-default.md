---
id: ENH-3007
status: done
priority: P3
captured_at: '2026-08-03T00:05:35Z'
discovered_date: 2026-08-03
discovered_by: user
decision_needed: false
testable: true
completed_at: '2026-08-03T00:05:35Z'
---

# Make prompt_optimization opt-in (default off)

## Summary

`prompt_optimization` shipped as a default-on feature: with no
`prompt_optimization` block in `.ll/ll-config.json`, the `user_prompt_submit`
hook injected the optimize-prompt template into every qualifying user message.
It is now opt-in — the schema default is `false`, an absent config block reads
as disabled, and `ll-init` writes the section only when the user asks for it.

## Current Behavior

The default lived in three coupled places, all set to on:

1. `scripts/little_loops/config-schema.json` — `prompt_optimization.enabled`
   had `"default": true`.
2. `scripts/little_loops/hooks/user_prompt_submit.py:147` —
   `prompt_opt.get("enabled", True)`, so an absent block meant enabled. This
   was the live behavior gate; the schema default alone changes nothing at
   runtime.
3. `scripts/little_loops/init/core.py:191` — an *opt-out* emission policy:
   the section was written only when `prompt_optimization_enabled is False`.
   A fresh `ll-init` therefore left the key absent, which (2) read as on.

The TUI asked "Enable automatic prompt optimization?" with `default=True`, and
`ll-init --yes --disable prompt_optimization` was the documented way to turn it
off.

## Expected Behavior

Prompt optimization is off unless explicitly enabled. Concretely:

- Absent `prompt_optimization` block → hook returns without injecting
  (`bypass_reason="disabled"` still recorded).
- `ll-init` omits the section by default; `--enable prompt_optimization` (or
  answering Yes in the TUI) writes `{"enabled": true}`.
- Explicit `{"enabled": true}` renders the template exactly as before.

## Motivation

The user-prompt-submit hook rewrites what the user typed before the host sees
it. Silently enabling that for every new project — with no config key present
to hint that it is happening — is the wrong default for a behavior that
intercepts input. Opting in is cheap (`/ll:toggle-autoprompt enabled`);
discovering that an unseen hook is rewriting your prompts is not.

## Program Design

### Signatures

No signature changes — the inversion is entirely in default values and one
emission branch. The three functions whose *behavior* changes:

- `handle(event: LLHookEvent) -> LLHookResult`
  (`scripts/little_loops/hooks/user_prompt_submit.py`). Unchanged signature;
  the `enabled` lookup's fallback flips from `True` to `False`.
- `build_config(template: TemplateMatch, choices: dict[str, Any] | None = None) -> dict[str, Any]`
  (`scripts/little_loops/init/core.py`). Unchanged signature; the
  `prompt_optimization_enabled` key in `choices` now gates writing the section
  rather than gating writing `enabled: false`.
- `prompt_optimization_enabled: bool = False`
  (`scripts/little_loops/init/tui.py`, `_build_final_config` keyword
  parameter, was `bool = True`). The one signature-level edit. All call sites
  pass the value explicitly, so no caller changes.

### Emission policy inversion

`build_config()` previously followed the opt-out shape:

```python
# --- prompt_optimization (default-on; only write when opting out) ---
if prompt_optimization_enabled is False:
    config["prompt_optimization"] = {"enabled": False}
```

It now follows the opt-in shape already used by `decisions`, `scratch_pad`,
and `session_capture`:

```python
# --- prompt_optimization (default-off; only write when opting in) ---
if prompt_optimization_enabled is True:
    config["prompt_optimization"] = {"enabled": True}
```

The value still sources from `schema_default("prompt_optimization.enabled")`
(per ENH-2434), so flipping the schema flips the wizard default too; only the
*emission* branch is hand-inverted.

### Call Path

`.ll/ll-config.json` -> `handle()`
(`scripts/little_loops/hooks/user_prompt_submit.py`) -> `prompt_opt.get(
"enabled", False)` -> early return, or template render of
`scripts/little_loops/hooks/prompts/optimize-prompt-hook.md`. The bypass
guards (prefix / `/` / `#` / `?` / min-length) still fire before the enabled
check, unchanged.

Init path: `ll-init` -> `build_config()` (`init/core.py`) -> written config;
`run_tui()` / `_build_final_config()` (`init/tui.py`) and the `--upgrade`
re-read in `init/cli.py` supply the `prompt_optimization_enabled` choice.

## Integration Map

### Files to Modify

- `scripts/little_loops/config-schema.json` — `enabled` default `true` → `false`
- `scripts/little_loops/hooks/user_prompt_submit.py` — absent block reads as
  disabled
- `scripts/little_loops/init/core.py` — opt-out → opt-in emission + docstring
- `scripts/little_loops/init/tui.py` — wizard default, `_build_final_config`
  parameter default, summary row (`"on"` when opted in)
- `scripts/little_loops/init/cli.py` — `--upgrade` re-read default, help example

### Dependent Files (Callers/Importers)

- `hooks/scripts/user-prompt-check.sh`, `hooks/adapters/codex/prompt-submit.sh`,
  `hooks/adapters/kimi/user-prompt-submit.sh` — all delegate to
  `python -m little_loops.hooks user_prompt_submit`, so they inherit the new
  default with no edit.
- `commands/toggle-autoprompt.md` — unchanged mechanism; only the documented
  default moves.

### Tests

- `scripts/tests/test_hook_user_prompt_submit.py` — `test_absent_block_defaults_on`
  → `test_absent_block_defaults_off`; new `test_explicit_enabled_renders_template`
  keeps the enabled path covered (the old test was the only one exercising a
  successful render from an absent block).
- `scripts/tests/test_init_core.py` — the two `build_config` default tests and
  the headless-flag test inverted (`--disable` → `--enable`).
- `scripts/tests/test_init_tui.py` — the two TUI toggle tests inverted.

### Documentation

- `docs/reference/CONFIGURATION.md` — sample config, defaults table, new
  opt-in note
- `docs/reference/CLI.md` — `--disable` flag prose and the example line
- `docs/development/TROUBLESHOOTING.md` — new step 0 in "User prompt
  optimization not working": check that it is enabled at all
- `skills/configure/show-output.md` — `(default: false)`
- `commands/toggle-autoprompt.md` — `enabled` row notes default OFF

## Implementation Steps

1. `prompt_optimization.enabled` has `"default": false` in the schema —
   verified by reading `config-schema.json`.
2. The hook treats an absent block as disabled — verified by
   `test_absent_block_defaults_off`.
3. `build_config()` writes the section only when opting in — verified by
   `test_prompt_optimization_omitted_when_explicitly_disabled` and
   `test_prompt_optimization_enabled_writes_enabled_true`.
4. The TUI and `--upgrade` re-read carry the off default, and the summary
   reports "on" when opted in — verified by the two inverted TUI tests.
5. Docs state the opt-in default and point at `--enable
   prompt_optimization` / `/ll:toggle-autoprompt enabled`.

## Acceptance Criteria

- [x] `prompt_optimization.enabled` defaults to `false` in the schema.
- [x] A config with no `prompt_optimization` block produces no template
      injection from the `user_prompt_submit` hook.
- [x] An explicit `{"enabled": true}` still renders the template with the
      user's prompt interpolated.
- [x] `ll-init --yes` omits the `prompt_optimization` section; `ll-init --yes
      --enable prompt_optimization` writes `{"enabled": true}`.
- [x] No doc or skill still states `true` as the default for
      `prompt_optimization.enabled`.
- [x] `python -m pytest scripts/tests/` passes for every test touching
      prompt optimization, init, config, and hooks.

## Impact

- New projects no longer get prompt rewriting they did not ask for.
- Existing projects with an explicit `{"enabled": true}` are unaffected.
- Existing projects relying on the *implicit* default (no block present) lose
  prompt optimization on upgrade. This is the intended behavior change; the
  remedy is one `/ll:toggle-autoprompt enabled`.

## Scope Boundaries

- Does **not** change `mode`, `confirm`, `bypass_prefix`, or
  `clarity_threshold` defaults, or any optimization logic.
- Does **not** migrate existing configs — no upgrade shim writes
  `{"enabled": true}` to preserve the old implicit behavior. Silently
  re-enabling on upgrade would defeat the point of the change.
- Does **not** touch the `--disable prompt_optimization` flag itself; it
  remains valid (now a no-op against the default).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/CONFIGURATION.md` | `prompt_optimization` defaults table |
| `docs/reference/CLI.md` | `ll-init --enable/--disable` flag surface |
| `commands/toggle-autoprompt.md` | Runtime toggle for the feature |

## Session Log
- `hook:posttooluse-status-done` - 2026-08-03T00:06:28 - `df66edc5-ca4d-4f21-805d-e3a74b61ae34.jsonl`
- Direct session - 2026-08-03T00:05:35Z - investigate and fix

## Status

- **Status**: done

---

## Resolution

- **Action**: improve
- **Completed**: 2026-08-03
- **Status**: Completed

### Files Changed
- `scripts/little_loops/config-schema.json`
- `scripts/little_loops/hooks/user_prompt_submit.py`
- `scripts/little_loops/init/core.py`
- `scripts/little_loops/init/tui.py`
- `scripts/little_loops/init/cli.py`
- `scripts/tests/test_hook_user_prompt_submit.py`
- `scripts/tests/test_init_core.py`
- `scripts/tests/test_init_tui.py`
- `docs/reference/CONFIGURATION.md`
- `docs/reference/CLI.md`
- `docs/development/TROUBLESHOOTING.md`
- `commands/toggle-autoprompt.md`
- `skills/configure/show-output.md`

### Verification Results
- `python -m pytest scripts/tests/` — 18000 passed, 42 skipped, 1 failed.
  The single failure is `test_fsm_topology.py::TestAutodevSmoke::test_autodev_topology`
  (79 vs 77 states), caused by an unrelated uncommitted working-tree edit to
  `scripts/little_loops/loops/autodev.yaml`, not by this change.
- Targeted re-run of the affected files (hooks, init, config, wiring):
  979 passed, 1 skipped.
- `ruff check` clean on all touched files. `ruff format --check` flags
  `init/cli.py` and `test_init_core.py`, but the diffs are pre-existing
  formatting drift in unrelated Kimi-adapter code, left untouched.
