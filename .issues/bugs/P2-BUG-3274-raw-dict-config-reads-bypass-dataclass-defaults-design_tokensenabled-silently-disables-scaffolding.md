---
id: BUG-3274
type: BUG
title: "Raw-dict config reads bypass dataclass defaults \u2014 design_tokens.enabled\
  \ silently disables scaffolding"
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T23:31:07Z'
relates_to:
- ENH-3275
- ENH-3264
labels:
- bug
- config
- design-tokens
- init
---

# BUG-3274: Raw-dict config reads bypass dataclass defaults — design_tokens.enabled silently disables scaffolding

## Summary

Every consumer that reads a config *section* off the raw `.ll/ll-config.json` dict
(`config.get("design_tokens", {}).get("enabled")`) disagrees with the dataclass that
models the same section (`DesignTokensConfig.enabled: bool = True`,
`from_dict` → `data.get("enabled", True)`).

For a config block that **omits** `enabled`, the dataclass reports `True` while every
raw-dict reader evaluates falsy and silently skips its work. The two views of the same
file return opposite answers, and nothing warns.

This is not hypothetical: **the little-loops source repo is in exactly this state today.**

## Current Behavior

`.ll/ll-config.json` in this repo contains:

```json
"design_tokens": { "active": "warm-paper", "active_theme": "dark" }
```

No `enabled` key. Confirmed at runtime:

```
BRConfig(...).design_tokens  ->  enabled=True  active='warm-paper'  path='.ll/design-tokens'
load_design_tokens(config)   ->  None
```

The dataclass says the feature is on. `.ll/design-tokens/` was never created, so the
loader returns `None`, and every `ll-loop run` in this repo injects an **empty**
`design_tokens_context`. All 15 design-consuming built-in loops run unstyled, silently.

### Root cause chain

1. Commit `a5d15112` (ENH-1836, 2026-05-31) hand-wrote the `design_tokens` block that
   `/ll:configure` had selected but never persisted — omitting `enabled`.
2. `deploy_design_tokens()` (`init/writers.py:478`), which mirrors
   `templates/design-tokens/profiles/` into `.ll/design-tokens/profiles/`, is gated at
   every call site on the **raw dict**. The gate is falsy, so it has never run here.

### Confirmed raw-dict readers

| Site | Reads | Config provenance |
|---|---|---|
| `init/cli.py:845` (`_run_apply`) | `config.get("design_tokens", {}).get("enabled")` | **on-disk** — `merge_with_existing(plan, load_existing_config(project_root), force)` at `:833` |
| `hooks/session_start.py:306` | `design_tokens.get("enabled") is True` | **on-disk** raw config dict |
| `init/cli.py:637` (`_run_yes`) | same | freshly built by `build_config`, but merged with existing on `--upgrade` |
| `init/tui.py:871` (`_apply_config`) | same | freshly built (`tui.py:746` writes `enabled: True`) |

The first two are unambiguously wrong — they read a user's on-disk config where the
dataclass default genuinely differs.

**`ll-init apply` cannot self-heal the project.** Because `_run_apply` merges the plan
with the existing config and then gates on the raw merged dict, re-running
`ll-init apply` on a project in this state skips `deploy_design_tokens` again. There is
no supported command that repairs it; the user must hand-edit the JSON.

Note also the two readers disagree with *each other*: `session_start.py` uses strict
`is True`, init uses truthiness. An `enabled: 1` or `enabled: "true"` config splits them.

## Expected Behavior

One source of truth. Config sections are read through their dataclass
(`BRConfig.design_tokens.enabled`), so a key omitted from the JSON resolves to the
documented default everywhere — or, if raw-dict reads must stay for a structural reason,
they resolve defaults identically (`.get("enabled", True)`) and are covered by a test
that pins dataclass↔raw-dict agreement.

A project whose config says a feature is enabled must not have that feature silently
skipped by the scaffolder.

## Motivation

The failure is silent in both directions and has already produced two independent
defects:

1. This repo's own design tokens never deployed (above).
2. **ENH-3264's AC 9b was written against the wrong premise** — it assumed
   `session_start.py` would warn for a project at the dataclass's `True` default. It
   does not; the key must be literally `true` in the JSON. The acceptance test would
   have passed vacuously. Corrected in ENH-3264's fourth review pass, but the trap
   is still live for the next author.

Any config section modeled by a dataclass *and* read raw elsewhere carries this bug.
`product`, `learning_tests`, `issues.deploy_templates`, `history.session_digest`, and
`commands.confidence_gate` are read the same way (`init/cli.py:634-857`,
`init/tui.py:100-102`, `init/summary.py:64`) and should be audited alongside — several
have `False` dataclass defaults, where the bug inverts (harmless) rather than silently
disabling.

## Proposed Solution

> **The naive fix is wrong — do not "just read through the dataclass."** Verified:
> `DesignTokensConfig.from_dict({}).enabled` is `True`. A section that is **absent
> entirely** resolves to enabled, so routing the init gate through the dataclass would
> make `ll-init apply` deploy `.ll/design-tokens/profiles/` for **every project**,
> including ones that never opted into design tokens at all. That is a far larger
> behavior change than this bug warrants, and it would land silently on every existing
> install.

**Correct rule: section presence is the opt-in; key-level defaults apply within it.**

| Config state | Resolve to | Rationale |
|---|---|---|
| `design_tokens` section **absent** | off — no scaffold, no warning | Preserves today's behavior for projects that never opted in |
| section present, `enabled` **omitted** | `True` (the dataclass default) | Fixes the observed bug — this repo's exact shape |
| section present, `enabled: false` | off | Explicit opt-out, unchanged |

This repairs the real defect with zero expansion: the only projects whose behavior changes
are those that already have a `design_tokens` block, i.e. ones that demonstrably asked for
the feature.

1. **Audit** every `config.get("<section>", {}).get(...)` in `init/` and `hooks/` against
   its dataclass default. Produce the disagreement list; sections whose dataclass
   default is `False` are already consistent and need no change.
2. **Fix the two on-disk readers** — `init/cli.py:845` and `hooks/session_start.py:306`
   — to apply the table above: test section presence first, then resolve the key with its
   dataclass default (`.get("enabled", True)`) rather than bare truthiness. Do **not**
   substitute a `BRConfig`-mediated read, for the reason in the callout.
3. **Add a regression test** asserting dataclass↔raw-dict agreement for `design_tokens`:
   a config dict omitting `enabled` yields `enabled=True` from `DesignTokensConfig`
   *and* satisfies every gate that reads it raw.
4. **Decide the repair path for already-broken projects.** Fixing the gate makes
   `ll-init apply` deploy profiles for every project whose config omits `enabled` — which
   is the correct outcome, but it is a behavior change on existing installs that will
   newly write `.ll/design-tokens/profiles/`. Confirm that is intended before shipping;
   `deploy_design_tokens` is skip-if-exists, so it will not clobber.

## Steps to Reproduce

1. Write a `.ll/ll-config.json` whose `design_tokens` block omits `enabled`:
   `"design_tokens": {"active": "warm-paper", "active_theme": "dark"}`
2. Confirm the dataclass reports the feature on:
   ```python
   from little_loops.config.core import BRConfig
   BRConfig(project_root=Path(".")).design_tokens.enabled   # -> True
   ```
3. Run `ll-init apply` against that project.
4. Observe `.ll/design-tokens/` is **not** created — `_run_apply`'s gate
   (`init/cli.py:845`) read the raw dict, got `None`, and skipped
   `deploy_design_tokens()`.
5. Confirm the runtime consequence: `load_design_tokens(config)` returns `None`, so
   `ll-loop run` injects an empty `design_tokens_context`.

The little-loops source repo reproduces this as-is; no fixture setup needed.

## Program Design

### Types
- `DesignTokensConfig` — `scripts/little_loops/config/features.py:328-359`. `enabled: bool = True`;
  `from_dict` resolves `data.get("enabled", True)` (`:348`). This is the authoritative default.

### Signatures
- `load_existing_config(project_root: Path) -> dict[str, Any]` — `init/writers.py`; returns the
  parsed on-disk config **as a raw dict**, with no dataclass defaults applied. The source of the
  divergent view consumed at `init/cli.py:845`.
- `deploy_design_tokens(ll_dir, templates_dir, active_profile="default", dry_run=False, force=False) -> bool`
  — `init/writers.py:478`; skip-if-exists, so re-running after a fix is safe and non-clobbering.

### Call Path
`ll-init apply` -> `_run_apply()` (`init/cli.py:779`) -> `merge_with_existing(plan, load_existing_config(project_root), force)` (`:833`)
-> **[raw-dict gate, `:845`: `config.get("design_tokens", {}).get("enabled")`]** -> `deploy_design_tokens()` *(skipped when the key is absent)*.

Independently: `SessionStart` hook -> `hooks/session_start.py:306` -> **[raw-dict gate, `is True`]** -> warning *(suppressed when the key is absent)*.

### Decision Rules
- **Section presence is the opt-in; key defaults apply within it.** See the table in Proposed
  Solution. An absent section stays off — routing through `BRConfig`/`from_dict` instead would
  resolve an absent section to `enabled=True` and scaffold every project on earth.
- **Raw-dict reads resolve the same key-level defaults as the dataclass.** The init flow builds a
  dict before any `BRConfig` exists, so raw reads are structurally required there; they must
  supply `.get("enabled", True)` rather than bare truthiness, covered by the agreement test in AC 4.
- **Sections whose dataclass default is `False` are already consistent** and are out of scope for
  a code change — record them in the audit as intentional rather than editing them.

## Impact

- **Priority**: P2 - Silently disables a feature the user's config says is enabled, and
  `ll-init apply` cannot repair it. Not P1: the blast radius is styling quality, not
  correctness or data loss, and a hand-edit works around it.
- **Effort**: Small - Two one-line default fixes plus an audit and a regression test. The
  audit across sibling sections is the bulk of the work.
- **Risk**: Medium - Fixing the gate is a behavior change on existing installs: projects
  whose config omits `enabled` will newly get `.ll/design-tokens/profiles/` written on the
  next `ll-init apply`. `deploy_design_tokens` is skip-if-exists so nothing is clobbered,
  but the new files are a visible side effect (AC 2 requires confirming this is intended).
- **Breaking Change**: No

## Scope Boundaries

**In scope**
- The dataclass↔raw-dict disagreement for `design_tokens`, and the audit of sibling
  sections read the same way.
- A regression test pinning agreement.

**Out of scope**
- Remediating *this repo's* `.ll/` state — that is its own decision (mirror the profiles
  in as tracked files vs. set `enabled: false` to make the no-token state explicit).
  Filed separately.
- Changing any dataclass default value.
- ENH-3264's DESIGN.md work. That issue consumes the corrected understanding of
  `session_start.py:306`; it does not depend on this fix landing.

## Acceptance Criteria

1. A config with a **present** `design_tokens` section that omits `enabled` produces the
   same answer from `DesignTokensConfig.from_dict()` and from every gate that reads the
   section raw.
2. `ll-init apply` on a project whose config has a `design_tokens` section omitting
   `enabled` deploys the token profiles.
2b. **No expansion to non-opted-in projects.** `ll-init apply` on a project whose config
   has **no `design_tokens` section at all** does **not** deploy token profiles — today's
   behavior, preserved. *(Guards the naive "read through the dataclass" fix:
   `DesignTokensConfig.from_dict({}).enabled` is `True`, so a `BRConfig`-mediated gate
   would scaffold every project. See the callout in Proposed Solution.)*
3. `hooks/session_start.py`'s design-token validation fires for a config whose
   `design_tokens` section is present but omits `enabled`, matching the dataclass default
   — not only for a literal `true`. It stays silent when the section is absent.
4. A test pins dataclass↔raw-dict agreement for the section-present case and fails against
   today's code; a sibling test pins the section-absent case against the over-broad fix.
5. The audit of sibling sections is recorded, with each disagreement either fixed or
   documented as intentional.
6. `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-20 | Priority: P2
