---
id: ENH-3264
type: ENH
title: Support DESIGN.md as an import/export format for the design-token system
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T20:04:28Z'
supersedes: [ENH-3263]
labels:
- enhancement
- design-tokens
- loops
- config
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

1. **`_load_design_md(path) -> dict`** in `design_tokens.py` — parse YAML frontmatter into the same flat dict `_resolve_references()` already consumes. The spec's `{colors.primary}` alias syntax is the same `{dotted.path}` form as our `{color.paper.0}`, so the resolver needs little or no change. Map `colors`→`color`, keep `typography`/`spacing`, and decide handling for `rounded` and `components` (likely: fold `rounded` into the spacing/radius group; expose `components` verbatim in prompt context).
2. **`load_design_tokens()` gains a source branch**, still returning the same `DesignTokens` dataclass, so every downstream consumer (`run.py`, `artifact.py`, `hooks/session_start.py:303`) is untouched.
3. **Config knob `design_tokens.source: auto | profile | design_md`** (schema: `scripts/little_loops/config-schema.json`). `auto` = root `DESIGN.md` wins when `active` is unset; an explicit `active` profile wins otherwise.
4. **Theme degradation.** DESIGN.md source ⇒ single theme; `active_theme` is ignored with a stderr warning, matching the existing degradation style at `design_tokens.py:149`. Projects needing light/dark keep profiles. Do not invent a non-spec `themes:` key.
5. **Body injection.** Carry the markdown body into a new context var (e.g. `design_guidance_context`), injected next to `design_tokens_context` in `cli/loop/run.py`, and honor the existing per-loop `use_design_tokens` opt-out (ENH-3099) for both.
6. **`render_as_design_md(light, dark) -> str`** exporter + a CLI surface. Round-trips `default`, `warm-paper`, `editorial-mono`.

## Integration Map

### Files to Modify
- `scripts/little_loops/design_tokens.py` — `_load_design_md()` (new), `load_design_tokens()` source branch (`:160`), `DesignTokens` dataclass (`:27`), `render_as_design_md()` (new)
- `scripts/little_loops/config-schema.json` — `design_tokens.source` enum
- `scripts/little_loops/config/core.py` — `design_tokens` config dataclass gains `source`
- `scripts/little_loops/cli/loop/run.py:242-254` — inject `design_guidance_context` alongside `design_tokens_context`, respecting `use_design_tokens`
- `scripts/little_loops/loops/html-website-generator.yaml` — consume guidance in `plan` (`:37-50`) and `run_gen_eval.generate_prompt` (`:60-79`)
- `scripts/little_loops/cli/__init__.py` — register the export entry point
- `scripts/pyproject.toml` — `ll-design` console script (if a new entry point rather than an `ll-artifact` subcommand)

### Dependent Files (Callers/Importers)
All consume `load_design_tokens()` / the renderers and must keep working unchanged:
- `scripts/little_loops/cli/artifact.py:66-74` — `render_as_css_vars_themed(light, dark)`; the theme-degradation path must not crash here when the source is DESIGN.md
- `scripts/little_loops/cli/loop/run.py:229,249` — `render_as_prompt_context`
- `scripts/little_loops/hooks/session_start.py:303-325` — validates `design_tokens.path` / `active` at session start; needs a DESIGN.md-source branch or it will warn spuriously
- `scripts/little_loops/init/{core,writers,summary,tui,cli}.py` — profile picker; add the DESIGN.md option
- `scripts/little_loops/cli/doctor.py` — token health check
- `scripts/little_loops/cli/loop/lifecycle.py`

### Similar Patterns
- **ENH-1769** (done) — the direct precedent: a second input format (W3C DTCG `$value`) absorbed into `_flatten`/`_resolve_value` rather than converted. Follow its shape.
- `_resolve_token_root()` (`design_tokens.py:129-157`) — the established pattern for "try layout A, fall back to layout B, warn and degrade to None". The `source: auto` resolution should mirror it.
- `design_tokens.py:149` — the stderr warning idiom to copy for theme degradation.
- `ENH-3099` — per-loop `use_design_tokens` opt-out; `design_guidance_context` must honor the same switch.

### Tests
- `scripts/tests/test_design_tokens.py` — add DESIGN.md parse cases (spec example, alias resolution, missing/malformed frontmatter), `source` precedence, theme-degradation warning, and a round-trip export test over `default` / `warm-paper` / `editorial-mono`
- `scripts/tests/test_verify_design_tokens.py` — assert the lint still skips cleanly (does not false-positive) when the project source is DESIGN.md
- `scripts/tests/test_builtin_loops.py` — `design_guidance_context` resolves (to `""` when absent) so `${context.design_guidance_context}` never hard-fails interpolation

### Documentation
- `docs/reference/CONFIGURATION.md` — `design_tokens.source`
- `docs/reference/CLI.md` — the export command
- `docs/reference/API.md` — `little_loops.design_tokens` public surface
- `docs/guides/GETTING_STARTED.md` — DESIGN.md as the low-friction authoring path

### Configuration
- `.ll/ll-config.json` → `design_tokens.source` (new, default `auto`)
- Root `DESIGN.md` becomes a recognized project file (discovery, not config)

## Implementation Steps

1. Extend `DesignTokens` with a `guidance: str` field (default `""`) and a source discriminator.
2. Implement `_load_design_md()` + frontmatter→flat-dict mapping; unit-test against the spec's own example.
3. Branch `load_design_tokens()` on `design_tokens.source`; add the `auto` precedence rule and the theme-degradation warning.
4. Add `design_tokens.source` to `config-schema.json` and to `/ll:configure` + `ll-init` surfaces.
5. Inject `design_guidance_context` in `cli/loop/run.py` next to the existing block (lines 242-254), respecting `use_design_tokens`.
6. Consume it in `loops/html-website-generator.yaml` — the `plan` state's brief, and the `generate_prompt` anti-slop clause.
7. Implement `render_as_design_md()` + CLI entry point; add a round-trip test over all three built-in profiles.
8. Docs: `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`, `docs/reference/API.md`.

## Impact

- **Scope**: `design_tokens.py`, `config-schema.json`, `cli/loop/run.py`, one or more `loops/*.yaml`, init/configure UX, docs. Estimated ~150 LOC for the reader, ~80 for the exporter, plus tests.
- **Compatibility**: additive. Default `source: auto` with no root `DESIGN.md` present preserves today's behavior exactly.
- **Risk**: the spec is `version: alpha` and may churn. Confining it to an import/export edge — rather than the internal model — is what keeps that churn cheap.

## API/Interface

- `little_loops.design_tokens._load_design_md(path: Path) -> dict[str, Any]` — new, private.
- `little_loops.design_tokens.load_design_tokens(config, theme=None) -> DesignTokens | None` — signature unchanged; gains DESIGN.md source resolution.
- `little_loops.design_tokens.render_as_design_md(light: DesignTokens, dark: DesignTokens | None = None) -> str` — new, public.
- `little_loops.design_tokens.render_body_as_prompt_context(body: str) -> str` — new, public (or fold into the DesignTokens dataclass as a `guidance: str` field).
- Config: `design_tokens.source` enum added to `config-schema.json`.
- FSM context: `design_guidance_context` — new, runner-injected, `""` when absent.

## Open Questions

- Does `components:` map usefully into prompt context, or is it out of scope for the first cut?
- Should the exporter emit a *generated* prose body (from profile `_note` fields) or leave the body empty for a human to fill?
- Where does `ll-design` live — a new entry point, or a subcommand of the existing `ll-artifact`?

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-20T20:05:28 - `d2d69b09-ffdb-4870-8c2e-8b37aae045ea.jsonl`
- `/ll:capture-issue` - 2026-08-20T20:04:38 - `d2d69b09-ffdb-4870-8c2e-8b37aae045ea.jsonl`
