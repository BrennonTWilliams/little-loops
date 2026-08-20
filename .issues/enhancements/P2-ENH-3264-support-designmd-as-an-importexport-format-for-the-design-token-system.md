---
id: ENH-3264
type: ENH
title: Support DESIGN.md as an import/export format for the design-token system
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T20:04:28Z'
supersedes:
- ENH-3263
labels:
- enhancement
- design-tokens
- loops
- config
confidence_score: 90
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3264: Support DESIGN.md as an import/export format for the design-token system

## Summary

Teach the design-token subsystem to read and write [DESIGN.md](https://github.com/google-labs-code/design.md), the Google Labs draft spec (Apache 2.0, open-sourced 2026-04-21) for describing a visual identity to coding agents. DESIGN.md is a single root-level file with YAML frontmatter (`colors`, `typography`, `spacing`, `rounded`, `components`) plus a prose body (Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts).

The design decision this issue encodes: **DESIGN.md becomes a second *source format* feeding the existing resolver, not a replacement for it, and not a converter that writes profile JSON to disk.** Profiles stay the canonical internal model; DESIGN.md is an import/export edge.

## Current Behavior

Design tokens are only expressible as a multi-file profile under `.ll/design-tokens/profiles/<name>/`:
`primitives.json`, `semantic.json`, `typography.json`, `spacing.json`, and `themes/<theme>.json`.

- `load_design_tokens()` (`scripts/little_loops/design_tokens.py:160`) is the single entry point; it flattens those five files, layers them (semantic → typography → spacing → theme), and resolves `{dotted.path}` references into `DesignTokens.resolved`.
- `_resolve_token_root()` (`design_tokens.py:129`) knows exactly two layouts: the `profiles/<active>/` layout and the legacy flat one.
- There is no path by which a single human-authored markdown file can supply tokens, and no way to export a profile for another agent/tool to consume.

Consequences called out by the user: profiles are not very human-readable, are multi-file, and are awkward to author on the fly.

## Expected Behavior

1. A project with a root `DESIGN.md` and no materialized profile gets working token injection — `ll-loop run` (`cli/loop/run.py:249`) and `ll-artifact` (`cli/artifact.py:68`) behave as if a profile existed.
2. `ll-design export` (or an `ll-artifact` subcommand) round-trips any built-in profile out to a valid DESIGN.md for handoff to Cursor / Copilot / another little-loops project.
3. The DESIGN.md prose body is injected into generator prompts as design *intent*, alongside the token values.
4. Selection is explicit and predictable via config; degradation when DESIGN.md cannot express something (themes) is warned, not silent.

## Motivation

**Import side.** Lowers the authoring floor. A user can hand-write or paste one file instead of scaffolding four JSON files plus a themes dir, which is the stated pain.

**Export side.** Portability out. The spec is a plausible de-facto standard play (same bet OpenAPI made for REST); being able to emit one makes little-loops' three built-in profiles usable outside little-loops.

**The prose body is arguably the bigger win than the tokens.** `loops/html-website-generator.yaml:37-50` hand-rolls a design brief, and lines 46-48 / 74-76 hardcode an anti-slop "anti-patterns to avoid" list. A project's own DESIGN.md "Do's and Don'ts" section is exactly that content, authored per-project. Today there is no channel for it — `design_tokens_context` carries values only.

## Proposed Solution

### Why not the alternatives

- **Replace profiles with DESIGN.md (option A) — rejected.** It is a capability regression on three counts:
  - *Themes.* `render_as_css_vars_themed(light, dark)` (`design_tokens.py:330`), consumed by `cli/artifact.py:68-74`. This repo itself runs `active_theme: dark`. The DESIGN.md spec has no theme mechanism.
  - *The primitives→semantic split.* `render_as_prompt_context()` (`design_tokens.py:225`) groups by `surface`/`text`/`border`/`action` and deliberately suppresses raw primitives so the generator prompt gets roles, not a hex dump. DESIGN.md has one flat `colors:` map.
  - *The lint gate.* `ll-verify-design-tokens` (`cli/verify_design_tokens.py:42`) is defined entirely over "inverting theme × semantic color group". Both axes vanish under a flat DESIGN.md.

  Betting the whole styling path on an `alpha`-versioned spec four months old is also the wrong risk trade.

- **A Skill or a file-writing converter (the literal option C) — rejected.** Token injection happens at `cli/loop/run.py:249`, synchronous Python before any FSM state executes; a Skill cannot reach there. And a converter that materializes `profiles/<name>/*.json` from DESIGN.md creates a checked-in generated copy that drifts the instant either side is edited.

### The shape to build

Precedent: **ENH-1769** already absorbed a second input format (W3C DTCG `$value`) into `_flatten`/`_resolve_value` rather than converting it. Same seam, same move.

1. **`_load_design_md(path) -> tuple[dict, str]`** in `design_tokens.py` — returns `(flat_token_dict, prose_body)`. **Reuse the house frontmatter helpers, do not hand-roll a YAML reader:** `little_loops.frontmatter.parse_frontmatter(content, coerce_types=True)` (`frontmatter.py:255`) for the token block and `strip_frontmatter(content)` (`:416`) for the prose body. That is the entire body-extraction step — no separate parser needed, and no new dependency (this is why `learning_tests_required: [pyyaml]` was dropped from this issue's frontmatter). The spec's `{colors.primary}` alias syntax is the same `{dotted.path}` form as our `{color.paper.0}`, so the resolver needs little or no change. Map `colors`→`color`, keep `typography`/`spacing`, and decide handling for `rounded` and `components` (likely: fold `rounded` into the spacing/radius group; expose `components` verbatim in prompt context).
2. **`load_design_tokens()` gains a source branch**, still returning the same `DesignTokens` dataclass, so every downstream consumer (`run.py`, `artifact.py`, `hooks/session_start.py:303`) is untouched. **The branch must sit above the `if not base_path.exists(): return None` guard at `design_tokens.py:180`** — see "Branch placement" below.
3. **Config knob `design_tokens.source: auto | profile | design_md`** (schema: `scripts/little_loops/config-schema.json`). `auto` is defined in **filesystem** terms, not config terms — see "The `auto` rule" below.
4. **Theme degradation.** DESIGN.md source ⇒ single theme; `active_theme` is ignored with a stderr warning, matching the existing degradation style at `design_tokens.py:149`. Projects needing light/dark keep profiles. Do not invent a non-spec `themes:` key.
5. **Body injection.** Carry the markdown body into a new context var (e.g. `design_guidance_context`), injected next to `design_tokens_context` in `cli/loop/run.py`, and honor the existing per-loop `use_design_tokens` opt-out (ENH-3099) for both.
6. **`render_as_design_md(tokens: DesignTokens) -> str`** exporter + a CLI surface. Single-`DesignTokens` signature — see "Exporter is single-theme by construction" below. Round-trips `default`, `warm-paper`, `editorial-mono`.

### The `auto` rule — filesystem-based, not `active`-based

An earlier draft of this issue defined `auto` as "root `DESIGN.md` wins when `active` is unset." **That is unimplementable.** `DesignTokensConfig.active` defaults to `"default"` at `config/features.py:346` *and* `from_dict` re-applies `"default"` when the key is absent (`:356`), so the loader can never distinguish "user omitted `active`" from "user explicitly chose the `default` profile." (This repo's own `.ll/ll-config.json` sets `active: warm-paper`, so the ambiguity is live, not theoretical.)

Two ways out; **take the second**:

- Change `active`'s default to `None`. Rejected: it ripples into the two-guard `test_config_schema.py` gate, `core.py:888-897`'s echo dict, and `_resolve_token_root()`'s warning f-string, for no user-visible gain.
- **Define `auto` by what is materialized on disk** (chosen): a root `DESIGN.md` wins only when no profile is materialized — i.e. `<project_root>/<design_tokens.path>` does not exist, or `_resolve_token_root()` would return `None`. A materialized profile always wins. This needs zero config-dataclass churn and slots directly into the existing degradation ladder this issue already says to mirror.

`source: profile` and `source: design_md` remain explicit overrides that skip the probe entirely; `source: design_md` with no root `DESIGN.md` warns and returns `None`.

### Branch placement — above the `base_path.exists()` guard

`load_design_tokens()` returns `None` at `design_tokens.py:180` on `if not base_path.exists()`, **before `_resolve_token_root()` is ever called** (`:184`). A DESIGN.md-only project — precisely the target user in Expected Behavior #1 — has no `.ll/design-tokens/` directory at all, so putting the source branch inside or alongside `_resolve_token_root()` means the feature never fires and the primary use case silently returns `None`.

Correct placement: resolve the source **immediately after the `dt_cfg.enabled` check at `:177-178`**, before `base_path` is computed or tested. Only the profile branch proceeds into `base_path.exists()` / `_resolve_token_root()`.

### Exporter is single-theme by construction

This issue's rejection of option A rests on "the DESIGN.md spec has no theme mechanism." The exporter therefore has nowhere to put a second `DesignTokens`, so it takes one: `render_as_design_md(tokens: DesignTokens) -> str`.

Export from a themed profile is consequently **lossy**, and that must be explicit rather than silent: the CLI resolves the profile at `design_tokens.active_theme`, emits the corresponding single-theme DESIGN.md, and writes a stderr note naming which theme was exported and which were dropped. A `--theme` flag selects a different one.

### Prompt-context quality under a DESIGN.md source

`render_as_prompt_context()` gates its semantic-role output on `tokens.semantic["color"]` containing at least one of `surface`/`text`/`border`/`action` (`design_tokens.py:234-238`). A DESIGN.md flat `colors:` map mapped to `color.*` will **not** match, so it falls through to the flat sorted list at `:242-248` — losing both the role grouping *and* the contrast guardrail paragraph (`:292-295`), which are the two things this issue cites as the reason profiles beat a flat map.

So a DESIGN.md-sourced project gets a measurably worse generator prompt than a profile-sourced one unless this is handled. Pick one at implementation time and state it in the docs:

- **(a)** Map well-known spec color names (`background`/`surface`, `text`/`foreground`, `border`, `primary`/`accent`) onto the four semantic roles so the guardrail path engages, and leave unmapped names in a flat residual group.
- **(b)** Accept the flat fallback, but re-emit the contrast guardrail paragraph unconditionally so the anti-slop instruction survives regardless of source.

(b) is the smaller first cut and does not guess at the user's intent for a color named `primary`; (a) is the better end state. Either is acceptable — silently shipping the current fallback is not.

## Integration Map

### Files to Modify
- `scripts/little_loops/design_tokens.py` — `_load_design_md()` (new), `load_design_tokens()` source branch (`:160`), `DesignTokens` dataclass (`:27`), `render_as_design_md()` (new)
- `scripts/little_loops/config-schema.json` — `design_tokens.source` enum. The `design_tokens` object schema has `"additionalProperties": false` (`:1812`, confirmed) — any config with a `source` key is *rejected* until this lands, not merely undocumented.
- `scripts/little_loops/config/features.py:328-359` — `DesignTokensConfig` dataclass gains `source: str = "auto"`, defaulted in `from_dict()` (`:348-358`). *(An earlier draft pointed at `config/core.py` for the dataclass; that was wrong — `core.py` holds only the `to_dict()` echo, listed separately below.)*
- `scripts/little_loops/cli/loop/run.py:242-254` — inject `design_guidance_context` alongside `design_tokens_context`, respecting `use_design_tokens`
- `scripts/little_loops/loops/html-website-generator.yaml` — consume guidance in `plan` (`:37-50`) and `run_gen_eval.generate_prompt` (`:60-79`)
- `scripts/little_loops/cli/artifact.py` — new `design-md export` subcommand (resolved: no new `ll-design` console script, so `cli/__init__.py` and `scripts/pyproject.toml` are **not** touched)
- `scripts/little_loops/frontmatter.py` — read-only reuse of `parse_frontmatter` / `strip_frontmatter`; no change expected

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py:888-897` — `BRConfig`'s `to_dict()`-style config-echo builds a plain dict from `design_tokens` fields (`enabled, path, primitives_file, semantic_file, themes_dir, active_theme, active, profiles_dir`); needs a `"source": self._design_tokens.source` line. `scripts/tests/test_config_schema.py`'s two-guard consistency gate (Guard 1 ~`:444`, Guard 2 `_DATACLASS_SECTION_MAP` ~`:1284`) actively fails if `source` lands in the dataclass but not in both this dict and `config-schema.json` simultaneously.
- `scripts/little_loops/cli/loop/lifecycle.py:707-717` (`cmd_resume`) — independently injects `design_tokens_context` into `fsm.context`, duplicating `run.py:242-254`'s logic for the `ll-loop resume` path. This is a second primary injection site, not merely a caller that "keeps working unchanged" — it needs its own `design_guidance_context` injection added in lockstep with `run.py`, or `ll-loop resume` silently diverges from `ll-loop run`.

### Dependent Files (Callers/Importers)
All consume `load_design_tokens()` / the renderers and must keep working unchanged:
- `scripts/little_loops/cli/artifact.py:66-74` — `render_as_css_vars_themed(light, dark)`; the theme-degradation path must not crash here when the source is DESIGN.md
- `scripts/little_loops/cli/loop/run.py:229,249` — `render_as_prompt_context`
- `scripts/little_loops/hooks/session_start.py:303-325` — validates `design_tokens.path` / `active` at session start; needs a DESIGN.md-source branch or it will warn spuriously
- `scripts/little_loops/init/{core,writers,summary,tui,cli}.py` — profile picker; add the DESIGN.md option
- `scripts/little_loops/cli/doctor.py` — token health check
- `scripts/little_loops/cli/loop/lifecycle.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/session_start.py:303-325` — re-implements the degradation check against the raw config dict independently of `_resolve_token_root()`/`load_design_tokens()` (its own warning strings at `:311-314` and `:321-324`, not shared code); a DESIGN.md-source degradation warning needs a matching branch added here to stay stylistically consistent, since this runs before `load_design_tokens()` is ever called.
- `scripts/little_loops/cli/verify_design_tokens.py` (`_find_profiles_dir`, `lint_profiles_dir`) and `scripts/little_loops/cli/doctor.py:847-883` (`_full_design_tokens_data`) — operate directly on the filesystem (`profiles/<name>/semantic.json` + `themes/*.json`), independent of `DesignTokens`/`load_design_tokens()`. For a DESIGN.md-sourced project `_find_profiles_dir` returns `None`; confirm this surfaces as `doctor.py`'s existing `status: "unsupported", severity: "informational"` path rather than a false error.
- 14 other built-in loop YAMLs under `scripts/little_loops/loops/*.yaml` also consume `design_tokens_context` unchanged: `svg-textgrad`, `svg-image-generator`, `rlhf-svg-refine`, `rlhf-svg-generate`, `rlhf-animated-svg`, `pixi-generative-art`, `pixi-data-viz`, `interactive-component-generator`, `html-anything`, `hitl-md`, `hitl-compare`, `generative-art`, `flux-image-generator`, `canvas-sketch-generator`. Only `html-website-generator.yaml` is in scope to consume the new `design_guidance_context` per the Proposed Solution — the rest must keep receiving `design_tokens_context` unaffected; whether the prose-guidance win extends to them is open (see Open Questions).
- `scripts/tests/test_ll_loop_program_md.py:308` — the only other `DesignTokens(...)` construction call site besides `design_tokens.py:216`; uses keyword args, so new `guidance`/`source` fields with defaults won't break it, but confirm at implementation time.

### Similar Patterns
- **ENH-1769** (done) — the direct precedent: a second input format (W3C DTCG `$value`) absorbed into `_flatten`/`_resolve_value` rather than converted. Follow its shape.
- `_resolve_token_root()` (`design_tokens.py:129-157`) — the established pattern for "try layout A, fall back to layout B, warn and degrade to None". The `source: auto` resolution should mirror it.
- `design_tokens.py:149` — the stderr warning idiom to copy for theme degradation.
- `ENH-3099` — per-loop `use_design_tokens` opt-out; `design_guidance_context` must honor the same switch.

### Tests
- `scripts/tests/test_design_tokens.py` — add DESIGN.md parse cases (spec example, alias resolution, missing/malformed frontmatter), `source` precedence, theme-degradation warning, and a round-trip export test over `default` / `warm-paper` / `editorial-mono`. **Two cases specifically guard the defects corrected in this issue:** (i) a project with *no* `.ll/design-tokens/` directory still resolves tokens from a root `DESIGN.md` (catches a regression to the `base_path.exists()` short-circuit); (ii) `auto` with both sources materialized picks the profile *while `active` is at its `"default"` value* (catches a regression to the undecidable `active`-is-unset rule).
- `scripts/tests/test_verify_design_tokens.py` — assert the lint still skips cleanly (does not false-positive) when the project source is DESIGN.md
- `scripts/tests/test_builtin_loops.py` — `design_guidance_context` resolves (to `""` when absent) so `${context.design_guidance_context}` never hard-fails interpolation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_design_tokens.py:95-176` (`class TestLoadDesignTokensDtcgFormat`, the ENH-1769 precedent) — the shape to follow: exercise through the public `load_design_tokens()` entry point with a `_write_design_md()`-style fixture helper (mirroring existing `_write_tokens()`/`_make_config()` at `:23-51`), not isolated `_load_design_md()` unit tests — this file has no precedent for testing private functions directly.
- **Behavior parity for `config/features.py`** — the `source: str = "auto"` field added to `DesignTokensConfig` (`features.py:328-359`) is covered by `test_enh1768_profile_system.py::TestDesignTokensConfigProfileFields` (mirrored for `source`: default value, `from_dict` with the key present, and `from_dict` with the key absent falling back to `"auto"`), plus `test_config_schema.py`'s two-guard gate for the dataclass↔schema↔`to_dict()` round trip.
- `scripts/tests/test_enh1768_profile_system.py` (`TestDesignTokensConfigProfileFields` `:79`, `TestBRConfigDesignTokensProfileRoundTrip` `:107`, `TestConfigSchemaProfileFields` `:391`, `TestConfigureWiringForProfiles` `:422`) — the direct precedent for adding a `DesignTokensConfig` field (`active`/`profiles_dir` under ENH-1768); mirror all four classes 1:1 for `source`, including `TestConfigSchemaProfileFields`'s use of `importlib.resources.files("little_loops")` rather than a raw path read (wheel-install compatibility).
- `scripts/tests/test_config_schema.py` — the two-guard consistency gate (Guard 1 `test_design_tokens_in_schema` ~`:444` cross-checks `BRConfig.to_dict()` against `config-schema.json` defaults; Guard 2 `_DATACLASS_SECTION_MAP` ~`:1284` maps `DesignTokensConfig` → `design_tokens`) hard-fails unless `source` lands in the dataclass, `config-schema.json`, and `core.py:888-897`'s `to_dict()` dict together.
- `scripts/tests/test_cli_loop_lifecycle.py:921-948` (`test_design_tokens_context_injected_via_cmd_resume`) and `:1397-1480` (`TestUseDesignTokensOptOut`, ENH-3099) — add a `design_guidance_context` counterpart exercising the same `cmd_resume`/`cmd_run` injection paths and opt-out behavior.
- `scripts/tests/test_builtin_loops.py:8882` (`test_context_has_design_tokens_context` on `TestHtmlWebsiteGeneratorLoop`, class at `:8778`) — add `test_context_has_design_guidance_context` for the same loop.

### Documentation
- `docs/reference/CONFIGURATION.md` — `design_tokens.source`
- `docs/reference/CLI.md` — the export command
- `docs/reference/API.md` — `little_loops.design_tokens` public surface
- `docs/guides/GETTING_STARTED.md` — DESIGN.md as the low-friction authoring path

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:1007,1009` — names `DesignTokensConfig` and describes the pre-injection-into-FSM-context pattern; update for the new source/guidance model
- `docs/guides/LOOPS_REFERENCE.md` — ~14 per-loop tables document `design_tokens_context` as a runner-injected param; add `design_guidance_context` to the `html-website-generator` row at minimum
- `docs/generalized-fsm-loop.md:1099` — global runner-injected-context table entry for `design_tokens_context`, needs a `design_guidance_context` row with matching opt-out semantics (`use_design_tokens: false`)
- `skills/configure/areas.md:1107-1255` — full "Area: design_tokens" interactive `/ll:configure` section enumerating every `DesignTokensConfig` field individually; needs a `source` question/branch
- `skills/configure/show-output.md:186-198` — parallel `design_tokens --show` template listing the same fields

### Configuration
- `.ll/ll-config.json` → `design_tokens.source` (new, default `auto`)
- Root `DESIGN.md` becomes a recognized project file (discovery, not config)

## Program Design

### Types

- `DesignTokens` — at `design_tokens.py:26-34`; frozen dataclass, currently 5 required fields (`primitives`, `semantic`, `theme`, `resolved`, `source_path`), all positional/keyword, no defaults. The one production constructor call is at `design_tokens.py:216-222` inside `load_design_tokens()`. Adding `guidance: str = ""` and a source discriminator (e.g. `source: str = "profile"`) requires defaults — the dataclass is frozen and has 5+ construction call sites across `design_tokens.py` and `scripts/tests/test_design_tokens.py` / `scripts/tests/test_enh1768_profile_system.py` that would otherwise all need updating.
- `DesignTokensConfig` — at `scripts/little_loops/config/features.py:327-359`; plain dataclass, no existing field for source-format selection. Fields: `enabled: bool = True`, `path: str = ".ll/design-tokens"`, `primitives_file: str = "primitives.json"`, `semantic_file: str = "semantic.json"`, `themes_dir: str = "themes"`, `active_theme: str = "dark"`, `active: str = "default"`, `profiles_dir: str | None = None`, plus `from_dict(cls, data: dict[str, Any]) -> DesignTokensConfig`. `design_tokens.source` (ENH-3264's new config knob) is added here, defaulted via `from_dict`.
- `scripts/little_loops/cli/loop/lifecycle.py:891-896` separately builds a display/config-echo dict from `primitives_file`/`semantic_file`/`themes_dir`/`active_theme`/`profiles_dir` — outside the analyzer's confirmed-seed set, so unconfirmed whether it needs mirroring for a new `source` field; verify at implementation time.

### Signatures

- `load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None` — at `design_tokens.py:160-222`; unchanged signature per the issue's design, gains an internal source-format branch. Returns `None` when `dt_cfg.enabled` is `False`, `base_path` doesn't exist, or `_resolve_token_root()` degrades to `None`. Raises `ValueError` on circular/unknown references, propagated from `_resolve_references`/`_resolve_value`.
- `_flatten(obj: Any, prefix: str = "") -> dict[str, Any]` — at `design_tokens.py:44-64`; the ENH-1769 DTCG-absorption seam this issue's precedent points at. A dict node with a `"$value"` key is treated as a leaf (`:54-56`) and other `$`-prefixed sibling keys are skipped (`:58-59`), letting a differently-shaped input (W3C DTCG JSON) flatten through the *same* function as the legacy format — no separate DTCG loader exists. A DESIGN.md adapter needs to produce this same `dict[str, Any]` dotted-key shape, not a parallel pipeline.
- `_resolve_references(flat: dict[str, Any], primitives_flat: dict[str, Any], *, _resolving: frozenset[str] | None = None) -> dict[str, str]` — at `design_tokens.py:67-126`; pairs with `_resolve_value(key: str, raw: Any, flat: dict[str, Any], primitives_flat: dict[str, Any], resolving: frozenset[str]) -> str`, which handles `{token.reference}` syntax with a lookup order (primitives_flat → same-layer flat, recursively → DTCG `.$value`-suffixed fallback at `:95-125`). Whatever `_load_design_md()` produces must be `flat`-shaped before reaching this call — it is not itself extended for DESIGN.md.
- `_resolve_token_root(dt_cfg: Any, base_path: Path) -> Path | None` — at `design_tokens.py:129-157`; the fallback-chain pattern (prefer active profile dir → degrade-with-stderr-warning if profiles layout exists but `active` is missing → fall back to legacy flat `base_path`) whose *shape* a `source: auto` resolution should mirror. **It is not the host for the new branch** — it runs downstream of the `base_path.exists()` guard at `:180`, which a DESIGN.md-only project never gets past. See Decision Rules → Placement.
- `parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]` (`frontmatter.py:255`) and `strip_frontmatter(content: str) -> str` (`:416`) — the existing house helpers `_load_design_md()` is built on. `strip_frontmatter` yields the prose body for `DesignTokens.guidance` directly; no new YAML dependency and no bespoke parser.

### Call Path

`cmd_run` (`cli/loop/run.py:228-254`) / `cmd_resume` (`cli/loop/lifecycle.py:707-717`, structurally identical injection block) -> `load_design_tokens()` (`design_tokens.py:160`) -> **[source-format branch point, `:178-179`, immediately after the `dt_cfg.enabled` check and *before* `base_path` is computed]** -> _(design_md branch)_ `_load_design_md()` -> `_flatten()` -> `_resolve_references()` -> `DesignTokens(...)`; _(profile branch)_ `base_path.exists()` guard (`:180`) -> `_resolve_token_root()` (`:184`) -> `_load_json()` x5 -> `_flatten()` x5 (`:197-201`) -> merge in fixed layer order `semantic → typography → spacing → theme` (`:204-209`, primitives excluded from the merge, used only as the reference lookup table) -> `_resolve_references()` (`:210`) -> `DesignTokens(...)` construction (`:216-222`) -> `render_as_prompt_context()` / new `render_as_design_md()`.

Second call path, single call site with two invocations: `_themed_css_vars()` (`cli/artifact.py:59-74`) calls `load_design_tokens(config, theme="light")` and `load_design_tokens(config, theme="dark")` independently — the only two-theme consumer in the codebase. `_resolve_token_root()` does not vary by theme; only the `theme_file` lookup inside `load_design_tokens` (`:193-195`) does. Since DESIGN.md describes one `colors` block with no per-theme file, this is the concrete site where the "theme degradation ⇒ warn, not silent" requirement (Expected Behavior #4) must be implemented — either both calls resolve to the same `DesignTokens` object, or the function falls back to the existing neutral empty-block output already present at `:70-73`.

### Decision Rules

- **Source-format selection** (`design_tokens.source: auto | profile | design_md`): `auto` prefers a **materialized profile** and falls back to a root `DESIGN.md` — keyed on what exists on disk, *not* on whether `active` is set, which is undecidable because `active` defaults to `"default"` in both the dataclass (`config/features.py:346`) and `from_dict` (`:356`). See "The `auto` rule" under Proposed Solution.
  - **Placement:** this decision sits in `load_design_tokens()` at `:178-179`, *not* inside `_resolve_token_root()` (`:129-157`). `_resolve_token_root()` runs after the `if not base_path.exists(): return None` guard at `:180`, and a DESIGN.md-only project has no `.ll/design-tokens/` directory — branching there would short-circuit the primary use case to `None`. `_resolve_token_root()`'s 3-branch fallback shape (prefer A → degrade-with-warning → fall back to B) is still the *stylistic* model to copy; it is not the host function.
- **Theme degradation**: when the active source is DESIGN.md and a caller requests a specific `theme=` (as `_themed_css_vars` does for both `"light"` and `"dark"`), the resolver must not silently return divergent or empty output — it must emit the existing stderr-warning idiom (matching `design_tokens.py:149`'s degradation branch) and fall back to a single-theme result. Escape hatch: none — this only fires when the resolved source is DESIGN.md; profile-sourced projects are unaffected.

## Implementation Steps

1. Extend `DesignTokens` with a `guidance: str` field (default `""`) and a source discriminator.
2. Implement `_load_design_md()` on top of `frontmatter.parse_frontmatter` / `strip_frontmatter`, plus the frontmatter→flat-dict mapping; unit-test against the spec's own example.
3. Branch `load_design_tokens()` on `design_tokens.source` **at `:178-179`, above the `base_path.exists()` guard at `:180`**; implement the filesystem-based `auto` rule and the theme-degradation warning.
4. Add `design_tokens.source` to `config-schema.json` and to `/ll:configure` + `ll-init` surfaces.
5. Inject `design_guidance_context` in `cli/loop/run.py` next to the existing block (lines 242-254), respecting `use_design_tokens`.
6. Consume it in `loops/html-website-generator.yaml` — the `plan` state's brief, and the `generate_prompt` anti-slop clause.
7. Resolve the `render_as_prompt_context()` semantic-role gap — option (a) or (b) from "Prompt-context quality under a DESIGN.md source". Do not leave the bare flat-list fallback in place.
8. Implement `render_as_design_md(tokens)` + the `ll-artifact design-md export` subcommand; add a round-trip test over all three built-in profiles.
9. Docs: `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`, `docs/reference/API.md`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `source: str = "auto"` to `DesignTokensConfig` in `config/features.py:328-359` (not `config/core.py` — that file only holds the `to_dict()` echo)
- Update `config/core.py:888-897`'s `to_dict()` echo dict with a `source` key, in lockstep with the schema change — `test_config_schema.py`'s two-guard consistency gate fails otherwise
- Mirror `run.py:242-254`'s `design_guidance_context` injection into `cli/loop/lifecycle.py:707-717` (`cmd_resume`) so `ll-loop resume` doesn't diverge from `ll-loop run`
- Add a matching DESIGN.md-source degradation branch to `hooks/session_start.py:303-325`'s independently re-implemented warning logic
- Confirm `cli/verify_design_tokens.py` / `doctor.py:847-883` degrade to the existing informational "profiles directory not found" status for DESIGN.md-sourced projects rather than erroring
- Add `TestLoadDesignTokensDesignMdFormat`-style tests to `test_design_tokens.py` following the ENH-1769 `TestLoadDesignTokensDtcgFormat` pattern (`:95-176`), and mirror `test_enh1768_profile_system.py`'s four config-field test classes for `source`
- Add `design_guidance_context` counterparts to `test_cli_loop_lifecycle.py:921-948` and `test_builtin_loops.py:8882`

## Scope Boundaries

**In scope**

- DESIGN.md as a read source feeding the existing resolver, and as an export target.
- `design_tokens.source` config knob + its `/ll:configure`, `ll-init`, and schema surfaces.
- `design_guidance_context` injection on both `ll-loop run` and `ll-loop resume`, consumed by `html-website-generator.yaml` only.
- Resolving the semantic-role gap in `render_as_prompt_context()` for DESIGN.md sources.

**Out of scope**

- Replacing or deprecating the profile format. Profiles stay the canonical internal model; nothing about the existing five-file layout changes.
- Materializing `profiles/<name>/*.json` from a DESIGN.md, in either direction, on disk. The import is in-memory only — a checked-in generated copy would drift.
- Themes under DESIGN.md. No non-spec `themes:` key, no multi-theme export. Projects needing light/dark keep profiles.
- Extending `design_guidance_context` to the other 14 built-in loops. They keep receiving `design_tokens_context` unchanged; broader rollout is a follow-up once the prose channel proves out on one loop.
- Tracking `alpha`-spec churn. Pinning to the 2026-04-21 draft is acceptable for the first cut.
- Any change to `_resolve_references()` / `_resolve_value()`. The DESIGN.md adapter produces the flat dotted-key shape those already consume — if it needs them modified, the mapping is wrong.

## Acceptance Criteria

Each is individually testable.

1. A project whose only design artifact is a root `DESIGN.md` (no `.ll/design-tokens/` directory at all) gets a non-`None` `DesignTokens` from `load_design_tokens()`, and `ll-loop run` injects a non-empty `design_tokens_context`. *(Guards the `base_path.exists()` short-circuit at `design_tokens.py:180`.)*
2. A project with **both** a materialized profile and a root `DESIGN.md`, under `source: auto`, resolves to the profile — including when `active` is left at its `"default"` value.
3. `source: profile` ignores a root `DESIGN.md` entirely; `source: design_md` with no root `DESIGN.md` returns `None` and writes a stderr warning.
4. The spec's own example DESIGN.md parses, and its `{colors.primary}`-style aliases resolve through the existing `_resolve_references()` without modification to that function.
5. Malformed / absent frontmatter degrades to `None` with a stderr warning — no traceback.
6. `_themed_css_vars()` (`cli/artifact.py:59-74`) does not crash for a DESIGN.md-sourced project; both the `light` and `dark` calls return the same single-theme result, and exactly one degradation warning is emitted (not one per call).
7. `render_as_prompt_context()` output for a DESIGN.md source contains the contrast-guardrail paragraph. *(Fails today's flat-list fallback — this is the test for Implementation Step 7.)*
8. `render_as_design_md()` round-trips each of `default`, `warm-paper`, `editorial-mono` to a DESIGN.md that re-imports to equivalent resolved token values.
9. Exporting a themed profile writes a stderr note naming the exported theme and the dropped one(s).
10. `ll-verify-design-tokens` and `ll-doctor` report the existing informational "profiles directory not found" status for a DESIGN.md-sourced project — not an error, not a false positive.
11. `ll-loop resume` injects `design_guidance_context` identically to `ll-loop run`.
12. `use_design_tokens: false` on a loop suppresses **both** `design_tokens_context` and `design_guidance_context`.
13. All 14 other built-in loops still receive `design_tokens_context` unchanged.
14. `python -m pytest scripts/tests/` exits 0 — in particular `test_config_schema.py`'s two-guard gate, with `source` landing in the dataclass, `config-schema.json`, and `core.py:888-897`'s echo dict together.

## Impact

- **Scope**: `design_tokens.py`, `config-schema.json`, `cli/loop/run.py`, one or more `loops/*.yaml`, init/configure UX, docs. Estimated ~150 LOC for the reader, ~80 for the exporter, plus tests.
- **Compatibility**: additive. Default `source: auto` with no root `DESIGN.md` present preserves today's behavior exactly.
- **Risk**: the spec is `version: alpha` and may churn. Confining it to an import/export edge — rather than the internal model — is what keeps that churn cheap.

## API/Interface

- `little_loops.design_tokens._load_design_md(path: Path) -> tuple[dict[str, Any], str]` — new, private; returns `(flat_tokens, prose_body)`. Built on `little_loops.frontmatter.parse_frontmatter` / `strip_frontmatter`, not a new YAML reader.
- `little_loops.design_tokens.load_design_tokens(config, theme=None) -> DesignTokens | None` — signature unchanged; gains DESIGN.md source resolution at `:178-179`.
- `little_loops.design_tokens.render_as_design_md(tokens: DesignTokens) -> str` — new, public. **Single-`DesignTokens`**: the spec has no theme mechanism, so there is no second parameter to fill. Themed profiles export lossily with a stderr note naming the exported theme.
- `little_loops.design_tokens.render_body_as_prompt_context(body: str) -> str` — new, public (or fold into the DesignTokens dataclass as a `guidance: str` field).
- Config: `design_tokens.source` enum added to `config-schema.json`.
- CLI: `ll-artifact design-md export [--theme <name>] [-o <path>]` — a subcommand of the existing `ll-artifact`, **not** a new `ll-design` console script (see Resolved Questions).
- FSM context: `design_guidance_context` — new, runner-injected, `""` when absent.

## Open Questions

- Does `components:` map usefully into prompt context, or is it out of scope for the first cut?
- Should the exporter emit a *generated* prose body (from profile `_note` fields) or leave the body empty for a human to fill?
- Semantic-role mapping: option (a) or option (b) from "Prompt-context quality under a DESIGN.md source". Not blocking — (b) is a safe first cut — but one of them must ship.

### Resolved Questions

- ~~Where does `ll-design` live — a new entry point, or a subcommand of the existing `ll-artifact`?~~ **Resolved: `ll-artifact design-md export`.** No new console script, so `scripts/pyproject.toml` and `cli/__init__.py` drop out of the Integration Map. `ll-artifact` is already the two-theme `load_design_tokens()` consumer (`cli/artifact.py:59-74`), which is exactly where the lossy single-theme export decision has to be made anyway.
- ~~`auto` precedence keyed on whether `active` is set.~~ **Resolved: keyed on what is materialized on disk** — `active` defaults to `"default"` in both the dataclass and `from_dict`, so "unset" is not observable.
- ~~`render_as_design_md(light, dark)`.~~ **Resolved: `render_as_design_md(tokens)`** — the spec has no theme mechanism.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-20_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across ~9 modify sites (design_tokens.py, config-schema.json, config/features.py, config/core.py, cli/loop/run.py, cli/loop/lifecycle.py, cli/artifact.py, loops/html-website-generator.yaml, hooks/session_start.py) with cross-module consistency requirements — the two-guard `test_config_schema.py` gate, the duplicated `design_guidance_context` injection between `run.py`/`lifecycle.py`, and the independently re-implemented degradation check in `session_start.py` all need to move in lockstep or drift silently.
- Moderate depth from shared-state coordination rather than pure mechanical edits — the `load_design_tokens()` source branch and theme-degradation warning touch existing fallback logic, not isolated new code.
- Broad dependent surface (~6-10 call sites of `load_design_tokens()`/renderers — `artifact.py`, `doctor.py`, `verify_design_tokens.py`, `init/*.py`, `session_start.py`, `lifecycle.py`) that must keep working unchanged; verify each at implementation time rather than assuming pass-through safety.

## Session Log
- `/ll:confidence-check` - 2026-08-20T20:53:03 - `0ffa5e40-eabf-4e3f-9ddd-d1fd94489393.jsonl`
- `/ll:confidence-check` - 2026-08-20T20:33:22 - `1e7934c2-3f73-4b02-90d0-4a6aa50feef9.jsonl`
- `/ll:wire-issue` - 2026-08-20T20:24:02 - `7dde0c7a-2cdb-4340-890f-4e20e23fbdb7.jsonl`
- `/ll:refine-issue` - 2026-08-20T20:13:14 - `d3c778e1-6920-4445-bc39-5861315da162.jsonl`
- `/ll:capture-issue` - 2026-08-20T20:05:28 - `d2d69b09-ffdb-4870-8c2e-8b37aae045ea.jsonl`
- `/ll:capture-issue` - 2026-08-20T20:04:38 - `d2d69b09-ffdb-4870-8c2e-8b37aae045ea.jsonl`
