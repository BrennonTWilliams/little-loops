---
id: ENH-3275
type: ENH
title: "Decide little-loops' own design-token state \u2014 repo resolves to no tokens\
  \ despite active: warm-paper"
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T23:31:14Z'
relates_to:
- BUG-3274
- ENH-3264
labels:
- enhancement
- design-tokens
- config
- source-repo
---

# ENH-3275: Decide little-loops' own design-token state — repo resolves to no tokens despite active: warm-paper

## Summary

The little-loops source repo resolves to **no design tokens at all**, despite its config
naming an active profile. Decide which of two coherent end states it should be in, then
put it there. This is a source-repo-only housekeeping decision, not a product change.

## Current Behavior

`.ll/ll-config.json`:

```json
"design_tokens": { "active": "warm-paper", "active_theme": "dark" }
```

Confirmed at runtime:

```
BRConfig(...).design_tokens  ->  enabled=True  active='warm-paper'
load_design_tokens(config)   ->  None
```

`.ll/design-tokens/` does not exist and never has (`git log --all -- .ll/design-tokens`
is empty; it is not gitignored — `!/.ll/` un-ignores the tree). Consequence: every
`ll-loop run` in this repo injects an **empty** `design_tokens_context`, and all 15
design-consuming built-in loops (`svg-textgrad`, `generative-art`,
`html-website-generator`, `pixi-data-viz`, …) run unstyled, silently.

Root cause is BUG-3274 — the scaffolder's gate reads `enabled` off the raw config
dict where the dataclass's `True` default does not apply, so `deploy_design_tokens()`
never ran. That bug is filed separately; **this issue is the repo-state decision, which
stands regardless of whether the gate is fixed.**

## Expected Behavior

The repo is in one deliberate state, and its config tells the truth about it.

## Motivation

Two concrete costs to leaving it as-is:

1. Design-oriented loop output produced in this repo is unstyled, and the reason is
   invisible — the config looks correct.
2. **ENH-3264 makes it actively misleading.** Under that issue's `source: auto` rule,
   little-loops is an unmaterialized-profile project, so it would resolve to a root
   `DESIGN.md` the moment ENH-3267/3268 land one — while `active: warm-paper` remains in
   config, silently inert. The repo becomes its own live fixture for ENH-3264's AC 2c
   (the "explicitly-requested profile is missing → warn accurately" sub-case). Better to
   settle the repo's state before that lands rather than debug the interaction.

## Proposed Solution

Two coherent options. Pick one — do not leave the current third state, where the config
claims `warm-paper` and the runtime has nothing.

### Option A — materialize the profiles

Run the mirror (`deploy_design_tokens`, or copy
`scripts/little_loops/templates/design-tokens/profiles/` → `.ll/design-tokens/profiles/`)
and add `"enabled": true` to the config block.

- **For:** `warm-paper` actually applies; the repo dogfoods its own design-token path;
  the 15 design loops produce styled output here.
- **Against:** because `!/.ll/` un-ignores the tree, this adds ~3 profiles × 5 JSON files
  as **tracked** files that duplicate `templates/design-tokens/profiles/` byte-for-byte.
  A second copy in-repo can drift from the packaged source with no gate catching it.
  If chosen, consider whether a drift test (`templates/` vs `.ll/`) is warranted, or
  whether `.ll/design-tokens/` should be added to `.gitignore` so the mirror stays local.

### Option B — make the no-token state explicit

Set `"enabled": false` and drop `active`/`active_theme`, or remove the `design_tokens`
block entirely.

- **For:** zero duplication; the config stops lying; nothing to keep in sync.
- **Against:** the repo no longer exercises its own design-token path, so a regression in
  `load_design_tokens()` would not surface during ordinary local loop runs here.

**Recommendation: Option A with `.ll/design-tokens/` gitignored** — dogfooding is the
point of this repo, and gitignoring the mirror gets it without the tracked duplicate or
the drift surface. Confirm the gitignore addition does not conflict with the `!/.ll/`
un-ignore at `.gitignore:150-151`.

## Program Design

### Types
- No new types. The change is to `.ll/ll-config.json`'s `design_tokens` block, which is
  modeled by `DesignTokensConfig` (`config/features.py:328-359`) — unmodified here.

### Signatures
- `deploy_design_tokens(ll_dir, templates_dir, active_profile="default", dry_run=False, force=False) -> bool`
  — `init/writers.py:478`. Option A's mechanism: mirrors
  `templates/design-tokens/profiles/` → `.ll/design-tokens/profiles/`. Skip-if-exists
  without `force`; returns `False` when the destination already exists or the source is
  missing. Callable directly, so Option A does not require re-running `ll-init`.
- `load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None`
  — `design_tokens.py:160`. The verification oracle for AC 2.

### Call Path
Option A: `deploy_design_tokens()` -> `.ll/design-tokens/profiles/<3 profiles>` ->
`load_design_tokens()` clears its `base_path.exists()` guard (`design_tokens.py:180`) ->
`_resolve_token_root()` resolves `profiles/warm-paper/` -> populated `DesignTokens` ->
`inject_design_context()` (`cli/loop/_helpers.py:1397`) injects a non-empty
`design_tokens_context`.

Option B: config `enabled: false` -> `load_design_tokens()` returns `None` at its first
guard (`:177-178`) -> `inject_design_context()` sets `design_tokens_context` to `""`
explicitly, which is what already happens today — only the config now says so honestly.

### Decision Rules
- **The config must not claim a state the runtime does not have.** Either option satisfies
  this; the current third state does not.
- **If Option A, the mirror is either tracked deliberately or gitignored deliberately** —
  an untracked tree under a `!/.ll/`-un-ignored path is the failure mode AC 3 exists to
  prevent.
- **No loader or template changes.** If a fix appears to require one, it belongs in
  BUG-3274 or ENH-3264, not here.

## Impact

- **Priority**: P3 - Housekeeping on the source repo's own state. Real cost (unstyled
  loop output, a misleading config) but no consumer-facing defect; consuming projects
  are unaffected.
- **Effort**: Small - A config edit plus either a directory mirror or a gitignore line.
  The decision is the work, not the change.
- **Risk**: Low - Source-repo-only and fully reversible. Option A's only real risk is
  committing a duplicate profile tree that later drifts from `templates/`, which the
  recommended gitignore variant avoids.
- **Breaking Change**: No

## Scope Boundaries

**In scope**
- This repo's `.ll/ll-config.json` `design_tokens` block and `.ll/design-tokens/` state.
- A `.gitignore` entry if Option A is chosen with the mirror untracked.

**Out of scope**
- The raw-dict `enabled` gate defect itself — separate bug.
- Any change to `templates/design-tokens/profiles/` or to the loader.
- Consuming projects' state. This is source-repo-only.

## Acceptance Criteria

1. An option is chosen and the rationale recorded in the issue.
2. `load_design_tokens(BRConfig(project_root=<repo>))` returns a populated `DesignTokens`
   (Option A) or `None` with `enabled: false` explicitly set (Option B) — not the current
   "config says on, runtime says None" mismatch.
3. If Option A: `git status` is clean afterward — either the profiles are intentionally
   tracked, or `.ll/design-tokens/` is gitignored. No accidental untracked tree.
4. `python -m pytest scripts/tests/` exits 0.

## Resolution

**Option A chosen (user decision, 2026-08-20), with `.ll/design-tokens/` gitignored.**

Applied:
1. `.gitignore:152-158` — added `.ll/design-tokens/` with a comment recording *why* it is
   untracked (byte-for-byte duplicate of the packaged profiles, no drift gate) and the
   one-liner to recreate it. Placed after the `!/.ll/` un-ignore so it wins.
2. Ran `deploy_design_tokens(Path('.ll'), Path('scripts/little_loops/templates'))` —
   mirrored all three profiles (`default`, `editorial-mono`, `warm-paper`).
3. `.ll/ll-config.json` — added `"enabled": true` to the `design_tokens` block, first key.

Verified:
- `load_design_tokens()` now returns a populated `DesignTokens` — **99 resolved tokens**,
  `source_path` = `.ll/design-tokens/profiles/warm-paper`, semantic role grouping and the
  contrast-guardrail paragraph both present in `render_as_prompt_context()`. Was `None`.
- `git check-ignore` confirms the mirror is ignored; `git status` shows only `.gitignore`
  and `.ll/ll-config.json` as modified — no untracked tree (AC 3).
- `python -m pytest scripts/tests/` → **19312 passed, 15 skipped, exit 0** (AC 4).

Note the `enabled: true` line is what makes this stick *today*: the scaffolding gates read
the raw dict, where the dataclass default does not apply (BUG-3274). Once BUG-3274 lands,
the key becomes redundant-but-harmless — a present section with the key omitted will
resolve to `True` on its own.

## Status

**Done** | Created: 2026-08-20 | Priority: P3
