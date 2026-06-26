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
decision_needed: false
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

## Proposed Solution

Prefer **(A)** for least surprise and to match the existing schema/init intent:

> **Selected:** Option A — flip the runtime default to `True` (`prompt_opt.get("enabled", True)` at `user_prompt_submit.py:102`), staying with the literal `.get()` and **not** routing through `feature_enabled` (which hard-defaults absent keys to `False`). One line aligns the runtime with the schema default, the init "write-on-opt-out" convention, and both init read-back sites — fixing existing installs (incl. this repo) and new installs at once.

1. Change `user_prompt_submit.py:102` to default-on, e.g.
   `if not prompt_opt.get("enabled", True):` — or route the check through the
   shared `feature_enabled(...)` helper (used elsewhere in the same file for
   `analytics.enabled`) so default resolution is centralized and consistent
   with how other feature flags are evaluated.
2. Decide the bypass-guard ordering relative to the enabled check is preserved
   (slash/`*`/`#`/`?`/short-prompt guards still short-circuit first).
3. If **(B)** is preferred instead, update `init/core.py:105-107` to always
   write `prompt_optimization.enabled` and reconcile the schema default.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- ⚠ **HAZARD — the `feature_enabled(...)` "centralize" suggestion in step 1 does
  NOT fix this bug.** `feature_enabled` (`scripts/little_loops/config/features.py:14-35`)
  hard-defaults **absent keys to `False`**: it mirrors jq's `// false` semantics
  (docstring, lines 19–20) and returns `False` on the first missing path part
  (`if not isinstance(value, dict) or part not in value: return False`, lines 32–33).
  So `feature_enabled(config, "prompt_optimization.enabled")` returns `False` for
  an install with no `prompt_optimization` block — **preserving the exact bug**.
  `feature_enabled` has no `default=` parameter (unlike its sibling
  `feature_enabled_for`, lines 38–75, which defaults to `True`). Therefore the
  only resolution-(A) fix that actually flips the default-on is the literal
  `prompt_opt.get("enabled", True)` at `user_prompt_submit.py:102`. Centralizing
  through `feature_enabled` would require either adding a `default` param to that
  helper or wrapping the call — strictly more work than the one-line flip, and it
  would silently no-op if done naïvely.
- The analytics gate at `user_prompt_submit.py:78` (`feature_enabled(config, "analytics.enabled")`)
  is the precedent cited as "how other feature flags are evaluated" — but analytics
  is **opt-in** (default-off is correct there), whereas prompt_optimization is
  **default-on**. They are not symmetric, which is precisely why borrowing the
  `feature_enabled` pattern here is the trap above.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-26.

**Selected**: Option A — flip the runtime handler default to `True` at `user_prompt_submit.py:102` (literal `.get("enabled", True)`, not via `feature_enabled`).

**Reasoning**: Option A is the only change that fixes the *reported* symptom — every existing install with no `prompt_optimization` block, including this source repo, is inert today. The one-line `.get("enabled", True)` flip matches three existing read-back sites (`init/cli.py:296`, `init/tui.py:421`, `init/tui.py:778`), the schema default (`config-schema.json:588`), and the `init/core.py` "write-on-opt-out" comment, so it resolves the three-way default-resolution disagreement at the consumer. Option B (always-write from `ll-init`) only repairs *new* installs and still needs the same runtime change to fix existing ones, while also requiring inversion of three unit tests, a CLI integration assertion, and a docstring contract — strictly more work for an incomplete fix.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — flip runtime default to `True` | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| B — `ll-init` always writes explicit block | 2/3 | 2/3 | 2/3 | 1/3 | 7/12 |

**Key evidence**:
- Option A: `.get("enabled", True)` already used at `init/cli.py:296-298`, `init/tui.py:421`, and the `init/tui.py:778` display guard; `config-schema.json:588` declares `default: true`; `init/core.py:105-107` comment asserts "default-on; only write when opting out". Single-line change fixes existing + new installs; one new absent-block test needed in `TestPromptOptimizationRender` (`test_hook_user_prompt_submit.py:312`).
- Option B: aligns with the `learning_tests`/`analytics`/`history`/`loops` always-write group, but `context_monitor`/`product` (also default-on) use the omit-if-disabled shape, so it is not the dominant convention; fixes only new installs, leaves existing configs (incl. this repo) inert without an additional runtime change; forces inversion of `test_prompt_optimization_omitted_by_default`, `test_prompt_optimization_omitted_when_explicitly_enabled`, the `assert "prompt_optimization" not in data` integration check, and the `build_config` docstring.

## Integration Map

- `scripts/little_loops/hooks/user_prompt_submit.py:99-103` — enabled gate (the bug site)
- `scripts/little_loops/init/core.py:105-107` — init write-on-opt-out logic
- `config-schema.json:585-589` — schema `enabled` default
- `hooks/hooks.json:17-28` → `hooks/scripts/user-prompt-check.sh` → `python -m little_loops.hooks user_prompt_submit` (delivery path; confirmed working)
- `scripts/little_loops/hooks/prompts/optimize-prompt-hook.md` — injected template (rendered correctly when enabled)

### Codebase Research Findings

_Added by `/ll:refine-issue` — additional integration points discovered:_

- `scripts/little_loops/config/features.py:14-35` — `feature_enabled()` helper
  referenced by the Proposed Solution. Absent-key default is **`False`** (see the
  Proposed Solution hazard note); read this before considering the "centralize"
  route.
- `scripts/tests/test_hook_user_prompt_submit.py:312` — `TestPromptOptimizationRender`
  (BUG-2275) is the existing test class for the optimization render path; new gate
  tests should extend it (see Implementation Steps note below).

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_hook_user_prompt_submit.py:312` — `TestPromptOptimizationRender`;
  reuse the `_write_opt_config` helper (lines 315–326, which always writes
  `enabled: True`) as the template for the new absent-block / `enabled: false`
  fixtures. This is the only class that exercises the `prompt_optimization` branch
  of the handler. [Agent 3 finding]
- `scripts/tests/test_hook_intents.py:315` — `test_dispatch_user_prompt_submit_happy_path`
  is an e2e subprocess dispatch (`python -m little_loops.hooks user_prompt_submit`)
  with **no config file**; it asserts `"No config found"` on stdout. The no-config
  path short-circuits at `user_prompt_submit.py:96-97` (`_NO_CONFIG_MSG`) **before**
  the enabled gate at line 102, so absent *file* ≠ absent *block* — this test is
  unaffected by Option A and serves as a regression guard that the no-config path
  is preserved. [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py:1302` — `TestUserPromptCheck` exercises the
  Bash hook `hooks/scripts/user-prompt-check.sh` via subprocess. The `test_config`
  fixture (line 1313) writes `{"prompt_optimization": {"enabled": False}}` and the
  `enabled_config` fixture (line 1374) writes `{"enabled": True, ...}` — both explicit,
  so unaffected by the runtime default flip. Optionally add a shell-level absent-block
  case here to mirror the new unit test end-to-end. [Agent 3 finding]
- **Option-B canary tests — MUST stay green under Option A (do NOT touch):** these
  assert init's write-on-opt-out contract, which Option A leaves unchanged. If any
  go red, the fix accidentally altered `init/core.py`/`init/tui.py` instead of just
  the runtime handler:
  - `scripts/tests/test_init_core.py:586` `test_prompt_optimization_omitted_by_default`
  - `scripts/tests/test_init_core.py:594` `test_prompt_optimization_omitted_when_explicitly_enabled`
  - `scripts/tests/test_init_core.py:602` `test_prompt_optimization_disabled_writes_enabled_false`
  - `scripts/tests/test_init_core.py:1284` `test_yes_enable_feature_flags_write_sections` (`assert "prompt_optimization" not in data`)
  - `scripts/tests/test_init_tui.py:785` `test_prompt_optimization_default_on_omits_key`
  [Agent 2 + Agent 3 finding]

### Dependent Display Sites (absent-block ambiguity)

_Wiring pass added by `/ll:wire-issue`:_

These read `prompt_optimization.enabled` purely for **display** and share the exact
absent-block ambiguity this bug fixes. After the runtime default flips to `True`,
the runtime treats an absent block as ON — but these display surfaces still resolve
an absent block to empty/`None`, so status output can disagree with actual behavior.
Advisory: align them (resolve absent → ON / "default: true") or explicitly scope out.

- `commands/toggle-autoprompt.md:43` — `status` subcommand renders `enabled: [ON|OFF]`;
  with no `prompt_optimization` block there is no explicit key to display. The
  `enabled` toggle subcommand (line 52) writes an explicit value on first use, which
  masks the gap thereafter. [Agent 2 finding]
- `skills/configure/areas.md:624` — renders `{{config.prompt_optimization.enabled}}`,
  which yields empty/`None` for an absent block. [Agent 2 finding]
- `skills/configure/show-output.md:143` — renders the same value but annotates it
  `(default: true)`, so it is already aligned with the default-on intent. [Agent 2 finding]

### Documentation (already aligned — no change required)

_Wiring pass added by `/ll:wire-issue`:_

The fix aligns the runtime to what the docs already say; **no doc edits are needed**.
Listed so the implementer does not hunt for stale references:

- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — already documents `prompt_optimization.enabled`
  default **true** in 4 places (lifecycle table, UserPromptSubmit section, "Turning
  Hooks Off", Configuration Reference). [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `prompt_optimization` table states `enabled | true`. [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-init --disable` description calls it "the default-on
  prompt optimizer". [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md:1004` — "User prompt optimization not working"
  documents bypass/template causes; the absent-block cause becomes N/A after the fix,
  so the section stays accurate as-is. [Agent 2 finding]

### Codex Delivery Path (fix covers both hosts)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/hooks/adapters/codex/hooks.json:28-33` → `prompt-submit.sh` —
  Codex registers `UserPromptSubmit` against the **same** Python handler
  (`python -m little_loops.hooks user_prompt_submit`). The one-line runtime flip
  therefore repairs Claude Code **and** Codex installs simultaneously; no host-specific
  change is required. Confirms the blast radius (all installs without an explicit
  block) spans both hosts. [Agent 1 finding]

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — refines the step-3 test note:_

- The step-3 parenthetical ("that test file currently only covers the
  analytics/correction write path — the optimization gate is untested") is now
  **partially stale**: `scripts/tests/test_hook_user_prompt_submit.py:312`
  (`TestPromptOptimizationRender`, BUG-2275) already covers the render path
  (`test_renders_from_package_without_env_var`,
  `test_env_var_override_uses_custom_template`) and the short-prompt bypass
  (`test_silent_noop_when_prompt_too_short`). **However, every one of those tests
  writes an explicit `prompt_optimization: {enabled: True}` config** (see
  `_write_opt_config`, lines 315–326). The genuinely-untested condition — the
  actual bug — is the **absent `prompt_optimization` block** and the explicit
  `enabled: false` case. Add the three assertions from step 3 to that existing
  class rather than a new file; the absent-block test is the one that would have
  caught this regression.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation. Decision is Option A (one-line runtime flip at
`user_prompt_submit.py:102`):_

1. Add the gate tests to the **existing** `TestPromptOptimizationRender` class
   (`scripts/tests/test_hook_user_prompt_submit.py:312`), reusing `_write_opt_config`
   (lines 315–326) as the fixture template:
   - absent `prompt_optimization` block → template **is** injected for a vague prompt
     (this is the regression that would have caught the bug);
   - `{"prompt_optimization": {"enabled": false}}` → no injection (explicit opt-out preserved);
   - bypass guards (slash / `*` / `#` / `?` / short-prompt) still short-circuit
     regardless of the enabled default.
2. Run the **Option-B canary tests** and confirm they stay green — they prove the
   change was confined to the runtime handler and did not touch init:
   `test_init_core.py:586,594,602,1284` and `test_init_tui.py:785`.
3. Implementation Step 4 ("reconcile schema/init") requires **no schema or init edit**
   under Option A: `config-schema.json:588` already declares `default: true`,
   `init/core.py:105-107` already writes on opt-out only, and the three init read-back
   sites (`init/cli.py:296`, `init/tui.py:421`, `init/tui.py:778`) already default-on.
   The one-line runtime flip makes all sources agree — Step 4 is a verify-agreement
   check, not a modification.
4. (Optional, advisory) Decide whether to align the display-default sites
   (`commands/toggle-autoprompt.md:43` status output, `skills/configure/areas.md:624`)
   so an absent block reads as ON, matching the new runtime default — or explicitly
   scope them out as a follow-on. `skills/configure/show-output.md:143` is already
   annotated `(default: true)` and needs nothing.

## Impact

- **Priority**: P2 - A documented default-on feature is inert on every standard
  install, but there is no data loss or crash and prompts still pass through
  unmodified, so it sits below P0/P1 corruption-class bugs.
- **Effort**: Small - Resolution (A) is a one-line default flip at
  `user_prompt_submit.py:102` (or routing through the existing `feature_enabled`
  helper) plus a focused unit test; no new patterns or schema migration.
- **Risk**: Low - Restores the documented default; bypass-guard and
  enabled-check ordering are unchanged. The only behavioral surprise is for
  installs that silently relied on the inert state, mitigated by
  `/ll:toggle-autoprompt`.
- **Breaking Change**: No - Aligns runtime resolution with the schema/docs
  default rather than introducing new behavior.

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
- `/ll:wire-issue` - 2026-06-26T23:19:50 - `9638d775-3967-4517-9cef-a97510938e46.jsonl`
- `/ll:decide-issue` - 2026-06-26T23:04:06 - `53786629-d9b8-4f2a-8643-10c3f08458a2.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:46:36 - `ae61a1f8-a8d1-4f8e-949b-9e03bb674838.jsonl`
- `/ll:format-issue` - 2026-06-26T22:39:03 - `4f12d4d4-d57d-4bb8-8efc-70d6214a6307.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:30:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67adb916-4f2d-4717-9406-52734035f867.jsonl`

## Status
**Open** | Created: 2026-06-26 | Priority: P2
