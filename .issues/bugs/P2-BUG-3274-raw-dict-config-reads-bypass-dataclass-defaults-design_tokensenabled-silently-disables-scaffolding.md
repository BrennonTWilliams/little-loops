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
confidence_score: 100
outcome_confidence: 98
score_complexity: 23
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

### Sibling-section audit (partial — informs Proposed Solution step 1)
- `ProductConfig`, `AnalyticsConfig`, `ScratchPadConfig`, `DocumentsConfig`, and `PromptOptimizationConfig` dataclasses do not exist anywhere in `scripts/little_loops/config/` (confirmed via `class \w+Config` grep across the whole `config/` package and a targeted repo-wide grep for each name). Every raw-dict read of these sections (`product`, `analytics`, `scratch_pad`, `documents`, `prompt_optimization`) has no dataclass counterpart to diverge from — there is nothing for this bug's fix to change at those sites.
- `IssuesConfig` (`config/features.py:204`) has no `deploy_templates` field or attribute at all (confirmed by grep for `deploy_templates` in that file). The raw-dict reads at `init/cli.py:640,848` and `init/tui.py:875` (`config.get("issues", {}).get("deploy_templates")`) have no dataclass default to disagree with; the schema default (`config-schema.json:229-233`) is `false`, which already agrees with a bare `.get()` (absent → `None`, falsy). This sibling section is consistent and out of scope for a code change under the Proposed Solution's own table (dataclass default `False` → already agrees with bare-truthiness raw reads).
- This narrows Proposed Solution step 1's audit: of the sections named in this paragraph, only sections backed by an actual dataclass with a `True` default are candidates for the same disagreement `design_tokens` has. `LearningTestsConfig.enabled` defaults `False` (`config/features.py:501-528`), so it already agrees with its bare-truthiness raw read the same way `issues.deploy_templates` does — leaving `design_tokens` as the only confirmed-live instance of this bug among the sections this issue names. `commands.confidence_gate` and `history.session_digest` were not resolved to a dataclass during this pass and remain open for the audit in step 1.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Step 1's audit is now closed: `commands.confidence_gate` (dataclass default `False`, already consistent) and `history.session_digest` (dataclass-mediated, not raw-dict) are resolved — see the new Configuration subsection of the Integration Map. `design_tokens` remains the only live instance.
- Update `docs/reference/CONFIGURATION.md` (:172-179, :751-756, :862) — verify/update the Case B "(or was absent)" claim and disambiguate the two-tier rule from the unrelated `use_design_tokens` opt-out convention.
- Update `skills/configure/areas.md:1214` — verify Case B's enabled-transition logic stays consistent with the corrected two-tier rule.
- Update `scripts/little_loops/config-schema.json:1771-1774` — clarify the `enabled` description string to state section-omission resolves to off, not a flat `default: true`.
- Add tests per the Tests subsection: `test_init_core.py` (section-present-key-omitted + section-absent cases) and `test_hook_session_start.py::TestSessionStartFeatureValidation` (same two cases for the warning).

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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **BUG-2321 is not settled precedent to copy.** Its recorded decision (flip the runtime default to `True`, reject routing through `feature_enabled()`) diverges from what ships today: `hooks/user_prompt_submit.py:144-148` reads `prompt_opt.get("enabled", False)` — a `False` default. The divergence is not drift; a later issue, `.issues/enhancements/P3-ENH-3007-make-prompt-optimization-opt-in-by-default.md` (done), deliberately flipped `prompt_optimization`'s schema default from `true` to `false`, which is why the shipped code no longer matches BUG-2321's decision text. Only BUG-2321's reasoning pattern (prefer a literal `.get(key, default)` over `feature_enabled()` for a default that must be non-`False`) transfers; its specific default value does not.
- **Two raw-dict gate shapes coexist in this codebase, not one.** `init/cli.py:634,637,640,845,848` and `init/tui.py:868,871,878,888` use bare-truthiness `.get(section, {}).get("enabled")` with no key-level default. `hooks/session_start.py:294-337` adds an `isinstance(..., dict)` guard and reads with `is True`, but supplies no key-level default either — the same "no default" resolution as `init/cli.py`, just with an added type guard and stricter equality. A third shape, used only for seeding wizard/CLI choices from existing config (not for gating scaffolding), does supply an explicit default matching the dataclass — `config/core.py:903`, `init/cli.py:589-607`, `init/tui.py:444,471,480`, `init/summary.py:87` — but every instance found supplies a `False` default, so it does not demonstrate the shape adapting to a `True` dataclass default.
- **No existing helper expresses the two-tier "section absent → off, key omitted within a present section → dataclass default" rule.** `feature_enabled()` (`config/features.py:14-35`) collapses every absent case (missing section, missing key, non-dict) to a hard-coded `False` with no `default=` parameter — not reusable for a `True`-default section. `feature_enabled_for()` (`config/features.py:38-75`) takes a `default` but applies it uniformly to both "section missing" and "key omitted within a present section" — it does not distinguish the two tiers this bug's Proposed Solution table requires. The closest existing tiered-default shape, `McpTransportPolicyConfig.from_dict` (`config/features.py:573-583`), defaults nested keys independently (`http.get("allow_mutations", False)` vs `stdio.get("allow_mutations", True)`) but is a dataclass `from_dict`, not a raw-dict gate outside the dataclass — it doesn't express "outer-key presence is itself the signal."
- **Established regression-test convention for this defect class: one test per branch.** `test_hook_user_prompt_submit.py:340-429` (`TestPromptOptimizationRender`, BUG-2321's suite) pairs `test_absent_block_defaults_off` (:409, empty-`{}` config via a `_write_empty_config` helper) with `test_explicit_enabled_renders_template` (:421, explicit `True`). Existing `design_tokens` gate tests (`test_init_core.py:2108,2285,2508`) all set `enabled` explicitly and, like BUG-2321's suite, never cover the third branch — section-present-but-key-omitted — that this issue's AC 4 requires. `test_config.py:3395` (`test_design_tokens_defaults_when_absent`) pins only the dataclass side (`BRConfig(...).design_tokens.enabled is True` for a wholly-absent section); it does not assert anything about the raw-dict gates, consistent with why it doesn't catch this bug.

### Files to Modify
- `scripts/little_loops/init/cli.py:845` (`_run_apply`) — the on-disk raw-dict gate named in Proposed Solution step 2.
- `scripts/little_loops/hooks/session_start.py:306` (design-token validation) — the second on-disk raw-dict gate named in Proposed Solution step 2.
- `scripts/little_loops/init/cli.py:637` (`_run_yes`) and `scripts/little_loops/init/tui.py:871` (`_apply_config`) read a freshly-built config (not on-disk), matching the issue's own scoping — confirmed via `ll-code callers-of deploy_design_tokens`, no new information beyond what the issue's table already states.

### Dependent Files (Callers/Importers)
- Callers of `deploy_design_tokens()` (`init/writers.py:478`): `init/cli.py:638` (`_run_yes`), `init/cli.py:846` (`_run_apply`), and four unit tests in `scripts/tests/test_init_core.py` (`TestDeployDesignTokens::test_deploys_profiles:1136`, `::test_skips_if_already_exists:1144`, `::test_dry_run:1152`, `::test_skips_if_source_missing:1162`) — these test the deploy function directly, not the raw-dict gate above it.
- Callers of `load_existing_config()` (`init/writers.py:252`): `init/cli.py:453` (`_run_yes`), `init/cli.py:719` (`_run_plan`), `init/cli.py:833` (`_run_apply`), and three unit tests in `scripts/tests/test_init_core.py` (`TestMergeHelpers::test_load_existing_config_absent_returns_empty:3359`, `::test_load_existing_config_reads_ll_dir:3364`, `::test_load_existing_config_malformed_returns_empty:3369`).
- Importers of `init/writers.py` (the module defining both functions above): `scripts/tests/test_init_core.py:33`, `init/__init__.py:20`, `scripts/tests/test_deploy_issue_templates.py:9`, `cli/verify_cli_allowlist.py:23`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/design_tokens.py:370` (`load_design_tokens()`) — the dataclass-mediated consumer whose correct behavior (respecting `DesignTokensConfig.enabled`) is exactly what the two raw-dict gates fail to preserve today; must stay untouched by this fix, included here as the scope-boundary confirmation. [Agent 2 finding]
- `scripts/little_loops/cli/artifact.py:67,74,82` — calls `load_design_tokens(config, theme="light"/"dark")`. [Agent 1 finding]
- `scripts/little_loops/cli/loop/_helpers.py:1398-1426` — builds `context["design_tokens_context"]` via `load_design_tokens(config)` at `:1421`; the single chokepoint between the fix and every design-consuming built-in loop. Once the fix lands, this repo's 15 design-consuming loops (`html-website-generator.yaml`, `rlhf-animated-svg.yaml`, `rlhf-svg-refine.yaml`, `rlhf-svg-generate.yaml`, `pixi-data-viz.yaml`, `pixi-generative-art.yaml`, `svg-image-generator.yaml`, `svg-textgrad.yaml`, `canvas-sketch-generator.yaml`, `hitl-md.yaml`, `hitl-compare.yaml`, `flux-image-generator.yaml`, `generative-art.yaml`, `html-anything.yaml`, `interactive-component-generator.yaml`) start receiving a real `design_tokens_context` for the first time — no code change needed in them, informational only. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:862` (Case B, auto-scaffolding built-in profiles) — states enabling triggers "if flipped from false to true (**or was absent**)"; a fourth, independent code path (`/ll:configure`'s materialization flow) that already encodes an absence-implies-enabled assumption. Verify this parenthetical stays accurate once the two-tier rule (section absent → off) lands elsewhere. [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:172-179,751-756` — the canonical `design_tokens` example (`enabled: true` explicit, doesn't demonstrate the omitted-key case) sits next to the unrelated per-loop `use_design_tokens` opt-out convention (ENH-3099, "absent key treated as true") — a third defaulting convention in the same section a reader could conflate with this issue's rule. [Agent 2 finding]
- `docs/reference/API.md:157,216-218` — `DesignTokensConfig` table row and section header; no mention of the section-presence/key-default resolution rule. [Agent 2 finding]
- `docs/reference/CLI.md:121` — `/ll:configure design-tokens` area table row. [Agent 2 finding]
- `skills/configure/areas.md:1107-1272`, esp. `:1214` (Case B: `enabled` false→true transition gates `shutil.copytree` materialization) — a fourth, independent enabled-transition gate outside `init/cli.py:845`/`session_start.py:306`; check for consistency with the corrected two-tier rule. [Agent 2 finding]
- `skills/configure/show-output.md:186-202` — `--show` display template already annotates each field with "(default: true)"; consistent with the fix, confirm no change needed. [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:1771-1774` (`design_tokens.properties.enabled`) — description states a flat `"default": true` with no mention that section-omission resolves to off; candidate wording update alongside the fix (the schema structure itself does not need to change, `default` is documentation metadata only). [Agent 2 finding]
- `scripts/little_loops/config/automation.py:153-168` (`ConfidenceGateConfig`) — **resolves the issue's open sibling-audit item for `commands.confidence_gate`**: `enabled: bool = False`. The raw-dict reads at `init/tui.py:102`, `init/summary.py:64`, `fsm/schema.py:1081`, `cli/issues/check_readiness.py:87`, `cli/issues/next_action.py:39`, `cli/issues/set_flags.py:231`, and inline shell reads in `loops/refine-to-ready-issue.yaml:523,555,706` / `loops/recursive-refine.yaml:271,506` already agree with this `False` default (bare truthiness on an absent key already resolves off) — same already-consistent pattern as `issues.deploy_templates` and `learning_tests`. Not a live instance of this bug; no code change needed. [Agent 1 finding]
- `scripts/little_loops/config/features.py:1234-1417` (`SessionDigestConfig`) — **resolves the issue's open sibling-audit item for `history.session_digest`**: read via `config/core.py:934-938` through dataclass attribute access (`self._history.session_digest.enabled`), never a raw dict. No divergence risk; out of scope. [Agent 1 finding]

### Conventions in Force
- This codebase holds two disagreeing raw-dict `.get()` conventions in the same file (`init/cli.py`), not one — a fix must pick which one `design_tokens.enabled` should follow, not assume there is a single existing pattern to match. Bare-truthiness gates with no third-argument default (`config.get("product"/"design_tokens"/"learning_tests", {}).get("enabled")`) are applied uniformly at the scaffolding-gate call sites (`init/cli.py:634,637,643,649` and `:842,845,851,857`; `init/tui.py:868,871,878,888`). Explicit-default reads (`.get(section, {}).get(key, default)`, default matching each field's own dataclass default) are used when seeding wizard/CLI choices from `existing_config` (`init/cli.py:589-607`, `init/tui.py:444,471,480`, `init/summary.py:87`, `config/core.py:903`).
- `hooks/session_start.py:295-313` applies an `isinstance(section, dict)` guard before reading, but still reads `enabled` with strict `is True` (no key-level default) for all three sections it validates (`sync`, `documents`, `design_tokens`) — the same no-default shape as Pattern 1, evidence this is not a `design_tokens`-only omission.
- Among the three bare-truthiness-gated keys (`product`, `design_tokens`, `learning_tests`), `design_tokens` is the only one where the bug is live: `LearningTestsConfig.enabled` defaults to `False` (`config/features.py:501-528`, `from_dict` uses `data.get("enabled", False)`), which already agrees with a bare `.get("enabled")` read. `design_tokens` is the outlier because `DesignTokensConfig.enabled` defaults `True`.
- No existing helper in this codebase expresses "section absent → X, section present but key omitted → Y" as two distinct defaults. `feature_enabled()` (`config/features.py:14-35`) hard-defaults every absent case (missing section, missing key, non-dict) to `False`, no `default=` parameter. `feature_enabled_for()` (`config/features.py:38-75`) takes a `default` but applies that same single value to both "section missing" and "key omitted within a present section" — it does not distinguish the two tiers the Proposed Solution's table requires.
- A directly analogous prior bug, BUG-2321 (`.issues/bugs/P2-BUG-2321-...`), fixed the same defect class for `prompt_optimization.enabled` and recorded a decision explicitly declining to route the fix through `feature_enabled()`, for a hazard of the same shape as this issue's callout against routing through `BRConfig`/`from_dict`. However, the recorded decision ("Selected: Option A", raw read default `True`) and the code shipped today disagree: `hooks/user_prompt_submit.py:144-148` currently reads `prompt_opt.get("enabled", False)` with a comment stating the schema default is `false` — i.e. the schema/runtime-default side of the gap was closed instead of the raw-read side the issue's decision record describes. This is not settled precedent to copy; it is evidence that this class of fix has drifted from its own decision record before, which the regression test in AC 4 should guard against recurring.

### Tests
- Every existing test that exercises the `design_tokens` gate sets `enabled` explicitly (`True` or `False`) in the fixture config — none exercises the "section present, key omitted" case AC 4 requires: `scripts/tests/test_init_core.py` (`test_apply_deploys_design_tokens_when_enabled:2108-2124`, `test_yes_deploys_design_tokens_when_enabled:2285-2294`, `test_dry_run_shows_design_tokens_when_enabled:2508-2519`), `scripts/tests/test_hook_session_start.py` (fixtures at lines 189, 206, `test_warns_design_tokens_enabled_without_path:211-213`, JSON-based tests at 623-652).
- `scripts/tests/test_config.py:3395-3400` (`test_design_tokens_defaults_when_absent`) already pins the dataclass-mediated side of the disagreement: `BRConfig(...).design_tokens.enabled is True` when no `design_tokens` key exists at all on disk. This is the `BRConfig` path, not the raw-dict gates this issue is about — it does not conflict with AC 2b's requirement that a wholly-absent section not scaffold.

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed no existing test currently constructs a raw `design_tokens` dict with the section present and `enabled` omitted, at either fix site — searched `test_init_core.py`, `test_hook_session_start.py`, `test_init_tui.py`, `test_hooks_integration.py`, `test_design_tokens.py`, `test_wiring_init_and_configure.py`. The gap AC 4 requires is a true gap, not a vacuously-passing existing test. [Agent 3 finding]
- New: `scripts/tests/test_init_core.py` — alongside `test_apply_deploys_design_tokens_when_enabled:2108`, `test_yes_deploys_design_tokens_when_enabled:2285`, `test_dry_run_shows_design_tokens_when_enabled:2508` — a config with `design_tokens` section present and `enabled` omitted still deploys; plus a section-wholly-absent counterpart pinning AC 2b (no deploy). [Agent 3 finding]
- New: `scripts/tests/test_hook_session_start.py::TestSessionStartFeatureValidation:161` — alongside `test_warns_design_tokens_enabled_without_path:211` (reuse `_run_with` helper at `:162-166`) — section present, `enabled` omitted still fires the warning. [Agent 3 finding]
- Optional: `scripts/tests/test_config.py::TestBRConfigDesignTokensIntegration:3392` — a companion test asserting dataclass↔raw-dict agreement directly, adjacent to `test_design_tokens_override_from_config:3402`. [Agent 3 finding]
- Naming convention to follow: BUG-2321's `TestPromptOptimizationRender` (`scripts/tests/test_hook_user_prompt_submit.py:340-429`) pairs a `_write_<x>_config` fixture helper with one test method per tier (`_write_empty_config:404-407` → `test_absent_block_defaults_off:409-419`). No existing helper produces the "section present, key omitted" shape this issue needs — write a new one rather than reusing BUG-2321's helpers directly (that suite never needed a third tier, since `prompt_optimization` defaults `False`). [Agent 3 finding]

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


## Session Log
- `/ll:confidence-check` - 2026-08-21T04:47:42 - `06825300-0005-4b1f-8a38-697787be5d20.jsonl`
- `/ll:wire-issue` - 2026-08-21T04:45:06 - `ee8d0c92-9f75-42c4-9e2a-730c3d5d3cb0.jsonl`
- `/ll:refine-issue` - 2026-08-21T04:32:54 - `a85e8b1c-5475-4885-a40b-302d5e096fc6.jsonl`
