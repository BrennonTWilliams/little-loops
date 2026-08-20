---
id: ENH-3264
type: ENH
title: Support DESIGN.md as an import source for the design-token system
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T20:04:28Z'
supersedes:
- ENH-3263
relates_to:
- BUG-3266
- ENH-3267
- ENH-3268
labels:
- enhancement
- design-tokens
- loops
- config
confidence_score: 100
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3264: Support DESIGN.md as an import source for the design-token system

## Summary

Teach the design-token subsystem to **read** [DESIGN.md](https://github.com/google-labs-code/design.md), the Google Labs draft spec (Apache 2.0, open-sourced 2026-04-21) for describing a visual identity to coding agents. DESIGN.md is a single root-level file with YAML frontmatter (`colors`, `typography`, `spacing`, `rounded`, `components`) plus a prose body (Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts).

The design decision this issue encodes: **DESIGN.md becomes a second *source format* feeding the existing resolver, not a replacement for it, and not a converter that writes profile JSON to disk.** Profiles stay the canonical internal model; DESIGN.md is an import edge.

> **Split note.** This issue originally covered import, export, and the prose channel together. It was split into four siblings so each owns exactly one cross-module lockstep cluster; ENH-3264 retains the import core (and, with it, the `config/features.py` + `config-schema.json` + `core.py` two-guard cluster). See:
> - **BUG-3266** — `ll-loop resume` ignores `use_design_tokens`; extracts the shared injection helper. Independent of DESIGN.md, ships first.
> - **ENH-3267** — the `design_guidance_context` prose channel + `html-website-generator.yaml`. Depends on this issue for the parsed body.
> - **ENH-3268** — `render_as_design_md` + `ll-artifact design-md export`. Depends on this issue for the round-trip assertion.

## Current Behavior

Design tokens are only expressible as a multi-file profile under `.ll/design-tokens/profiles/<name>/`:
`primitives.json`, `semantic.json`, `typography.json`, `spacing.json`, and `themes/<theme>.json`.

- `load_design_tokens()` (`scripts/little_loops/design_tokens.py:160`) is the single entry point; it flattens those five files, layers them (semantic → typography → spacing → theme), and resolves `{dotted.path}` references into `DesignTokens.resolved`.
- `_resolve_token_root()` (`design_tokens.py:129`) knows exactly two layouts: the `profiles/<active>/` layout and the legacy flat one.
- There is no path by which a single human-authored markdown file can supply tokens, and no way to export a profile for another agent/tool to consume.

Consequences called out by the user: profiles are not very human-readable, are multi-file, and are awkward to author on the fly.

## Expected Behavior

1. A project with a root `DESIGN.md` and no materialized profile gets working token injection — `ll-loop run` (`cli/loop/run.py:249`) and `ll-artifact` (`cli/artifact.py:68`) behave as if a profile existed.
2. Selection is explicit and predictable via config; degradation when DESIGN.md cannot express something (themes) is warned, not silent.
3. The parsed prose body is available on `DesignTokens` for ENH-3267 to inject — this issue populates it, ENH-3267 wires it into prompts.

## Motivation

Lowers the authoring floor. A user can hand-write or paste one file instead of scaffolding four JSON files plus a themes dir, which is the stated pain.

This is also the enabling issue for the other two siblings: ENH-3267's prose channel (which the original Motivation called "arguably the bigger win than the tokens") and ENH-3268's exporter round-trip both need a working reader first.

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

1. **`_load_design_md(path) -> tuple[dict, str]`** in `design_tokens.py` — returns `(flat_token_dict, prose_body)`. **Reuse the house frontmatter helpers, do not hand-roll a YAML reader:** `little_loops.frontmatter.parse_frontmatter(content)` (`frontmatter.py:255`) for the token block and `strip_frontmatter(content)` (`:416`) for the prose body. That is the entire body-extraction step — no separate parser needed, and no new dependency (this is why `learning_tests_required: [pyyaml]` was dropped from this issue's frontmatter). The spec's `{colors.primary}` alias syntax is the same `{dotted.path}` form as our `{color.paper.0}`, so the resolver itself needs no change — but the *namespace rename* does, see "The rename is not just `colors`→`color`" and "Alias rewriting" below. Map `colors`→`color`, `typography`→`font`, `spacing`→`space`, `rounded`→`radius` via a single mapping table, normalize list values, and build the nested `semantic` dict; `components` is expected verbatim in prompt context (see Open Questions).

   **`components` is excluded from the token dict in this cut.** An earlier draft said it is "expected verbatim in prompt context" while Open Questions simultaneously asked whether it maps usefully at all — those contradicted, and the answer is neither. `components:` is structural guidance, not tokens: routing it through the flatten path would flood the generator prompt with `components.button.radius`-style leaves *and* emit them as `--components-button-radius` custom properties from `render_as_css_vars()`. It belongs to the prose channel ENH-3267 already owns. Drop the key before mapping; the residual bucket (below) is therefore *not* a `components` dumping ground.

   **Do not pass `coerce_types=True`.** `parse_frontmatter` loads with `yaml.BaseLoader`, so every scalar arrives as a `str` regardless; `coerce_types` would only turn a bare `4` into an `int` while `"4px"` stays a string, introducing a type split for no gain. Resolved token values are stringified downstream (`_resolve_value` returns `str`) anyway.
2. **`load_design_tokens()` gains a source branch**, still returning the same `DesignTokens` dataclass, so every downstream consumer (`run.py`, `artifact.py`, `hooks/session_start.py:303`) is untouched. **The branch must sit above the `if not base_path.exists(): return None` guard at `design_tokens.py:180`** — see "Branch placement" below.
3. **Config knob `design_tokens.source: auto | profile | design_md`** (schema: `scripts/little_loops/config-schema.json`). `auto` is defined in **filesystem** terms, not config terms — see "The `auto` rule" below.
4. **Theme degradation.** DESIGN.md source ⇒ single theme; `active_theme` is ignored with a stderr warning, matching the existing degradation style at `design_tokens.py:149`. Projects needing light/dark keep profiles. Do not invent a non-spec `themes:` key.

   **The warning fires only when a caller passes an explicit `theme=`.** `cmd_run` (`cli/loop/run.py:249`) calls `load_design_tokens(config)` with `theme=None`, so the single-theme nature of DESIGN.md is not a degradation from its point of view and it must stay silent — otherwise every `ll-loop run` in a DESIGN.md project prints a warning it can do nothing about. `_themed_css_vars()` (`cli/artifact.py:66-67`) is the only caller that passes an explicit theme and therefore the only site that warns. Read "DESIGN.md ⇒ single theme, warned" with that qualifier throughout this issue.
5. **Prose body capture.** `strip_frontmatter()` yields the markdown body; store it on `DesignTokens.guidance`. **Injection into prompts is ENH-3267**, not this issue — but the field is populated here, since it falls out of the same parse.

### Discovery: exactly one filename, exactly one location, not configurable

The issue text says "root `DESIGN.md`" throughout but never pinned what that resolves to. Specify it once, as a module-level constant in `design_tokens.py`:

```python
DESIGN_MD_FILENAME = "DESIGN.md"   # spec-mandated; project root only
```

- **Exact case.** The spec names the file `DESIGN.md`. Do **not** fall back to `design.md` / `Design.md`: macOS and the default Windows filesystem are case-insensitive while Linux and containers are not, so a case-tolerant probe passes on the author's machine and fails in CI or a devcontainer — the worst failure shape for a feature whose whole value is "it just works from one file."
- **Project root only.** `config.project_root / DESIGN_MD_FILENAME`. No recursive search.
- **No config knob.** Deliberately: `design_tokens.source` selects *whether* DESIGN.md is used; a second `design_md_path` setting would reintroduce the configuration burden this feature exists to remove. If a project needs the file elsewhere, it wants a profile.

### The rename is not just `colors`→`color` — every namespace must be renamed

An earlier draft said "map `colors`→`color`, **keep `typography`/`spacing`**." Keeping them is wrong, and it fails for exactly the same reason the `colors` rename is required. Confirmed against `templates/design-tokens/profiles/warm-paper/`:

| DESIGN.md frontmatter key | profile namespace | why |
|---|---|---|
| `colors` | `color.*` | `_SEMANTIC_ROLE_PREFIXES` / `_PRIMITIVE_COLOR_PREFIXES` (`design_tokens.py:258-272`) |
| `typography` | `font.*` | `typography.json` top-level key is `font` (`font.family`, `font.size`, `font.weight`, `font.line-height`, `font.letter-spacing`); the prompt-context bucket tests `name.startswith("font.")` (`:285`) |
| `spacing` | `space.*` | `spacing.json` top-level keys are `space`/`radius`/`shadow`/`border`; the layout bucket tests `space.`/`radius.`/`shadow.`/`border.width.` (`:287`) |
| `rounded` | `radius.*` | same bucket |

**The failure mode is silent deletion, not a wrong label.** The bucket loop at `design_tokens.py:274-290` assigns each resolved key to exactly one bucket and *drops anything that matches none* — there is no default case. A key named `typography.body` or `spacing.md` matches no prefix, hits none of the `elif`s, and simply never appears in the generator prompt. So under the current code a DESIGN.md-sourced project would ship a prompt containing colors and nothing else, with no warning.

### A residual bucket has to be added — it does not exist today

Option (a) says "leave unmapped names in a flat residual group." There is no such group: `_emit_group` is called exactly six times (`:310-315`) against six fixed buckets. Implementing (a) requires adding a seventh bucket that catches anything unmatched (minus the `_`-prefixed metadata and the deliberately-suppressed raw primitives) plus its `_emit_group("Other", residual)` call. This is a change to `render_as_prompt_context()` for **all** sources, not just DESIGN.md — under profiles it is a pure improvement (nothing is currently dropped from the three built-ins, but nothing guarantees that for a user-authored profile either). Covered by AC 7b.

### `DesignTokens.semantic` must be populated as a *nested* dict, not just `resolved`

`render_as_prompt_context()` gates the entire semantic/guardrail path on `tokens.semantic["color"]` being a **dict containing one of `surface`/`text`/`border`/`action`** (`design_tokens.py:234-239`) — it inspects the nested `semantic` field, not the flat `resolved` map. But `_load_design_md(path) -> tuple[dict, str]` as specified returns a *flat* token dict and prose only. With that signature the design_md branch has nothing to put in `semantic`, the gate returns `False`, and AC 7 fails no matter how well the flat keys are named.

**Resolution:** the adapter builds the nested structure too. Either widen the return to `tuple[dict[str, Any], dict[str, Any], str]` — `(flat_tokens, nested_semantic, prose)` — or have it return the nested dict and let the branch call the existing `_flatten()` on it (preferred: it reuses the ENH-1769 seam and keeps one source of truth for the mapping). The design_md branch then constructs `DesignTokens(primitives={}, semantic=<nested>, theme={}, resolved=<resolved>, source_path=<the DESIGN.md file>)`. Update the API/Interface entry accordingly.

### List-valued frontmatter must be normalized before `_flatten()`

`_flatten()` treats any non-dict as a leaf (`design_tokens.py:62-63`), so a list value is stored verbatim; `_resolve_value()` then does `str(raw)` (`:94`), emitting the Python repr — `['Inter', 'sans-serif']` — straight into the generator prompt and into `--font-family-body:` in the CSS. Profile JSON never hits this because font stacks are authored as a single comma-joined string. Hand-authored DESIGN.md plausibly will (font stacks, a spacing scale, `components` entries).

The adapter must normalize sequence values (join with `", "` for font stacks; index as `<key>.0`, `<key>.1` … for ordinal scales) before anything reaches `_flatten()`. Add a test with a list-valued `typography` entry.

### Alias rewriting — the renames must rewrite reference *strings* too

An earlier draft of this issue asserted both "map `colors`→`color`" (Proposed Solution #1) and "`{colors.primary}`-style aliases resolve through the existing `_resolve_references()` without modification" (Acceptance Criterion 4). **Those are mutually exclusive as written.**

`_resolve_value()` (`design_tokens.py:88-126`) matches the alias string *literally*: it takes `value[1:-1]` and looks that exact dotted key up in `primitives_flat`, then `flat`, then the `.$value` fallback. If `_load_design_md()` flattens the spec's `colors:` block into keys named `color.primary`, then a value of `"{colors.primary}"` finds no matching key on any of the three lookups and falls through to `raise ValueError(f"Unknown token reference '{ref_name}' in '{key}'")` at `:126`. Every DESIGN.md using the spec's own alias syntax would raise.

**Resolution: rewrite the alias strings as part of the same mapping step that renames the keys.** When `_load_design_md()` maps the `colors:` block to the `color.*` namespace, it must also rewrite values matching `{colors.<rest>}` to `{color.<rest>}`, so keys and references stay in the same namespace before anything reaches `_resolve_references()`. **This applies to every rename in the table above, not just `colors`** — `{typography.*}`→`{font.*}`, `{spacing.*}`→`{space.*}`, `{rounded.*}`→`{radius.*}`. Drive the rewrite off the same single namespace-mapping table that renames the keys, so the two can never disagree. `_resolve_references()`/`_resolve_value()` themselves remain untouched — the Scope Boundaries exclusion still holds; the rewrite lives entirely inside the adapter.

The alternative — keep the `colors.*` namespace verbatim and skip the rename — is **rejected**: `render_as_prompt_context()`'s role prefixes (`color.surface.`, …) and `_PRIMITIVE_COLOR_PREFIXES` (`design_tokens.py:256-271`) are all written against `color.*`, so none of them would ever fire. This is a second, independent reason to prefer option **(a)** over option (b) in "Prompt-context quality under a DESIGN.md source".

Note also that `_resolve_value()` only resolves a value that is *entirely* `{ref}` (`:95-96`). Interpolated forms the spec permits in prose-adjacent fields — `"1px solid {colors.border}"`, `"0 1px 2px {colors.shadow}"` — pass through **unresolved and silently wrong**. Document this limitation; do not extend `_resolve_value()` to fix it in this issue.

### Unresolvable references degrade, they do not raise

`load_design_tokens()` deliberately lets `ValueError` propagate (docstring, `design_tokens.py:164`) and `cmd_run` does not catch it (`cli/loop/run.py:249`). That is the correct contract for profile JSON, which is repo-controlled and reviewed. **It is the wrong contract for DESIGN.md**, whose entire motivation is "a user can hand-write or paste one file" — a single typo'd alias would abort `ll-loop run` with a traceback.

When the resolved source is DESIGN.md, `_resolve_references()` must be called inside a `try`/`except ValueError` that emits the stderr-warning idiom (`design_tokens.py:149`) naming the offending reference and returns `None`. Profile-sourced projects keep the existing raising behavior unchanged.

### The `auto` rule — filesystem-based, not `active`-based

An earlier draft of this issue defined `auto` as "root `DESIGN.md` wins when `active` is unset." **That is unimplementable.** `DesignTokensConfig.active` defaults to `"default"` at `config/features.py:346` *and* `from_dict` re-applies `"default"` when the key is absent (`:356`), so the loader can never distinguish "user omitted `active`" from "user explicitly chose the `default` profile." (This repo's own `.ll/ll-config.json` sets `active: warm-paper`, so the ambiguity is live, not theoretical.)

Two ways out; **take the second**:

- Change `active`'s default to `None`. Rejected: it ripples into the two-guard `test_config_schema.py` gate, `core.py:888-897`'s echo dict, and `_resolve_token_root()`'s warning f-string, for no user-visible gain.
- **Define `auto` by what is materialized on disk** (chosen): a root `DESIGN.md` wins only when no profile is materialized. A materialized profile always wins. This needs zero config-dataclass churn and slots directly into the existing degradation ladder this issue already says to mirror.

`source: profile` and `source: design_md` remain explicit overrides that skip the probe entirely; `source: design_md` with no root `DESIGN.md` warns and returns `None`.

#### "Materialized" must mean *token files exist*, not *the root resolves*

An earlier phrasing of the chosen rule defined it as "`<project_root>/<design_tokens.path>` does not exist, or `_resolve_token_root()` would return `None`." **That test is too weak and silently defeats the feature.**

`_resolve_token_root()` returns `base_path` **unconditionally** whenever `profiles/` is not a directory (`design_tokens.py:155-157` — the legacy-flat fallback). It never inspects whether any token file is actually present. So an **empty or partially-populated `.ll/design-tokens/` directory** satisfies both halves of the weak test: it counts as a materialized profile, wins over a root `DESIGN.md`, all five `_load_json()` calls return `{}` (`_load_json` returns `{}` for a missing path, `:37-39`), and the project gets a `DesignTokens` whose `resolved` is empty — so `ll-loop run` injects an **empty `design_tokens_context`** with no warning and the DESIGN.md is ignored.

This is not hypothetical. Both of these produce it: a leftover directory after a profile is deleted, and `ll-init` scaffolding `.ll/design-tokens/` before the user has selected a profile.

**Correct test — the profile branch wins only if it would yield tokens.** After resolving the token root, require that at least one of the four token files exists under it:

```
dt_cfg.primitives_file, dt_cfg.semantic_file, "typography.json", "spacing.json"
```

(Themes alone do not count: a `themes/` dir with no base layer resolves to a theme-override-only token set, which is not a usable profile.) If none exist, the profile is not materialized and `auto` falls through to DESIGN.md. Covered by AC 2b.

Note this probe is *only* for the `auto` decision — it does not change `source: profile`, which keeps today's exact behavior including the empty-but-present case, so no existing project's resolution changes.

### Branch placement — above the `base_path.exists()` guard

`load_design_tokens()` returns `None` at `design_tokens.py:180` on `if not base_path.exists()`, **before `_resolve_token_root()` is ever called** (`:184`). A DESIGN.md-only project — precisely the target user in Expected Behavior #1 — has no `.ll/design-tokens/` directory at all, so putting the source branch inside or alongside `_resolve_token_root()` means the feature never fires and the primary use case silently returns `None`.

Correct placement: resolve the source **immediately after the `dt_cfg.enabled` check at `:177-178`**, before `base_path` is computed or tested. Only the profile branch proceeds into `base_path.exists()` / `_resolve_token_root()`.

### Export moved to ENH-3268

The exporter analysis — single-`DesignTokens` signature, the lossy theme axis, the non-expressible token groups (`shadow.*`, `border.width.*`, `_note`/`_wcag_spot_check`), the documented key mapping, and the `--profile` flag needed to reach packaged built-ins — now lives in **ENH-3268**, which depends on this issue for the import side its round-trip assertion needs.

What stays here: the *reason* the spec cannot be the internal model (no theme mechanism, flat one-level `colors:`), which is what "Why not the alternatives" above rests on.

### Prompt-context quality under a DESIGN.md source

`render_as_prompt_context()` gates its semantic-role output on `tokens.semantic["color"]` containing at least one of `surface`/`text`/`border`/`action` (`design_tokens.py:234-238`). A DESIGN.md flat `colors:` map mapped to `color.*` will **not** match, so it falls through to the flat sorted list at `:242-248` — losing both the role grouping *and* the contrast guardrail paragraph (`:292-295`), which are the two things this issue cites as the reason profiles beat a flat map.

So a DESIGN.md-sourced project gets a measurably worse generator prompt than a profile-sourced one unless this is handled. Pick one at implementation time and state it in the docs:

- **(a)** Map well-known spec color names (`background`/`surface`, `text`/`foreground`, `border`, `primary`/`accent`) onto the four semantic roles so the guardrail path engages, and leave unmapped names in a flat residual group.
- **(b)** Accept the flat fallback, but re-emit the contrast guardrail paragraph unconditionally so the anti-slop instruction survives regardless of source.

(b) is the smaller first cut and does not guess at the user's intent for a color named `primary`; (a) is the better end state. Either is acceptable — silently shipping the current fallback is not.

## Integration Map

### Files to Modify
- `scripts/little_loops/design_tokens.py` — `_load_design_md()` (new), `load_design_tokens()` source branch (`:160`), `DesignTokens` dataclass (`:27`, gaining `guidance` + a source discriminator), and `render_as_prompt_context()` (`:225`) for the residual bucket — note this last one changes behavior for **profile** sources too (previously-dropped unmatched keys now appear); assert the three built-ins' output is unchanged, since none of them currently have unmatched keys.
- `scripts/little_loops/config-schema.json` — `design_tokens.source` enum. The `design_tokens` object schema has `"additionalProperties": false` (`:1812`, confirmed) — any config with a `source` key is *rejected* until this lands, not merely undocumented.
- `scripts/little_loops/config/features.py:328-359` — `DesignTokensConfig` dataclass gains `source: str = "auto"`, defaulted in `from_dict()` (`:348-358`). *(An earlier draft pointed at `config/core.py` for the dataclass; that was wrong — `core.py` holds only the `to_dict()` echo, listed separately below.)*
- `scripts/little_loops/cli/artifact.py:59-74` — `_themed_css_vars()` enters `load_design_tokens()` once for a DESIGN.md source and reuses the result for both theme blocks (the "warn once" mechanism; see Decision Rules). *Not* the export subcommand — that is ENH-3268.
- `scripts/little_loops/frontmatter.py` — read-only reuse of `parse_frontmatter` / `strip_frontmatter`; no change expected

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py:888-897` — `BRConfig`'s `to_dict()`-style config-echo builds a plain dict from `design_tokens` fields (`enabled, path, primitives_file, semantic_file, themes_dir, active_theme, active, profiles_dir`); needs a `"source": self._design_tokens.source` line. `scripts/tests/test_config_schema.py`'s two-guard consistency gate (Guard 1 ~`:444`, Guard 2 `_DATACLASS_SECTION_MAP` ~`:1284`) actively fails if `source` lands in the dataclass but not in both this dict and `config-schema.json` simultaneously.
- `scripts/little_loops/cli/loop/lifecycle.py:707-717` (`cmd_resume`) — independently injects `design_tokens_context`, duplicating `run.py:242-254`. Both sites keep working unchanged under this issue (the `DesignTokens` dataclass and `load_design_tokens()` signature are stable), so **no edit is required here for the import core**.

  The duplication itself, and the pre-existing ENH-3099 defect it hides (`lifecycle.py:715` has no `_use_tokens` gate, so the per-loop opt-out is silently ignored on `ll-loop resume` today), are **BUG-3266** — split out because they are a live defect on `main` with no dependency on DESIGN.md. ENH-3267 then consumes the shared helper BUG-3266 extracts.

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
- 14 other built-in loop YAMLs under `scripts/little_loops/loops/*.yaml` also consume `design_tokens_context` unchanged: `svg-textgrad`, `svg-image-generator`, `rlhf-svg-refine`, `rlhf-svg-generate`, `rlhf-animated-svg`, `pixi-generative-art`, `pixi-data-viz`, `interactive-component-generator`, `html-anything`, `hitl-md`, `hitl-compare`, `generative-art`, `flux-image-generator`, `canvas-sketch-generator`. All 14 — plus `html-website-generator` itself — must keep receiving `design_tokens_context` unaffected under a DESIGN.md source. Wiring any of them to the prose channel is ENH-3267 (which scopes it to `html-website-generator` only).
- `scripts/tests/test_ll_loop_program_md.py:308` — the only other `DesignTokens(...)` construction call site besides `design_tokens.py:216`; uses keyword args, so new `guidance`/`source` fields with defaults won't break it, but confirm at implementation time.

### Similar Patterns
- **ENH-1769** (done) — the direct precedent: a second input format (W3C DTCG `$value`) absorbed into `_flatten`/`_resolve_value` rather than converted. Follow its shape.
- `_resolve_token_root()` (`design_tokens.py:129-157`) — the established pattern for "try layout A, fall back to layout B, warn and degrade to None". The `source: auto` resolution should mirror it.
- `design_tokens.py:149` — the stderr warning idiom to copy for theme degradation.
- `ENH-3099` — per-loop `use_design_tokens` opt-out. Not touched by this issue; see BUG-3266 for its `cmd_resume` gap.

### Tests
- `scripts/tests/test_design_tokens.py` — add DESIGN.md parse cases (spec example, alias resolution, namespace renames, list-value normalization, missing/malformed frontmatter), `source` precedence, and the theme-degradation warning. *(The round-trip export test over the three built-in profiles moves to ENH-3268.)* **Two cases specifically guard the defects corrected in this issue:** (i) a project with *no* `.ll/design-tokens/` directory still resolves tokens from a root `DESIGN.md` (catches a regression to the `base_path.exists()` short-circuit); (ii) `auto` with both sources materialized picks the profile *while `active` is at its `"default"` value* (catches a regression to the undecidable `active`-is-unset rule).
  Two further cases guard the defects corrected in this review pass: (iii) an **empty** `.ll/design-tokens/` directory plus a root `DESIGN.md` under `auto` resolves to DESIGN.md, not to a hollow profile with empty `resolved` (AC 2b — catches a regression to the `_resolve_token_root() is not None` materialization test); (iv) `load_design_tokens(config)` with `theme=None` under a DESIGN.md source writes nothing to stderr, while `theme="dark"` warns (AC 6b).
- `scripts/tests/test_verify_design_tokens.py` — assert the lint still skips cleanly (does not false-positive) when the project source is DESIGN.md
- `scripts/tests/` (session-start hook coverage) — a DESIGN.md-only project produces an empty `warnings_out` from `hooks/session_start.py`'s design-token validation (AC 9b)
- `scripts/tests/test_builtin_loops.py` — all 15 built-in loops still receive `design_tokens_context` unchanged under a DESIGN.md source *(the `design_guidance_context` coverage moves to ENH-3267)*

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_design_tokens.py:95-176` (`class TestLoadDesignTokensDtcgFormat`, the ENH-1769 precedent) — the shape to follow: exercise through the public `load_design_tokens()` entry point with a `_write_design_md()`-style fixture helper (mirroring existing `_write_tokens()`/`_make_config()` at `:23-51`), not isolated `_load_design_md()` unit tests — this file has no precedent for testing private functions directly.
- **Behavior parity for `config/features.py`** — the `source: str = "auto"` field added to `DesignTokensConfig` (`features.py:328-359`) is covered by `test_enh1768_profile_system.py::TestDesignTokensConfigProfileFields` (mirrored for `source`: default value, `from_dict` with the key present, and `from_dict` with the key absent falling back to `"auto"`), plus `test_config_schema.py`'s two-guard gate for the dataclass↔schema↔`to_dict()` round trip.
- `scripts/tests/test_enh1768_profile_system.py` (`TestDesignTokensConfigProfileFields` `:79`, `TestBRConfigDesignTokensProfileRoundTrip` `:107`, `TestConfigSchemaProfileFields` `:391`, `TestConfigureWiringForProfiles` `:422`) — the direct precedent for adding a `DesignTokensConfig` field (`active`/`profiles_dir` under ENH-1768); mirror all four classes 1:1 for `source`, including `TestConfigSchemaProfileFields`'s use of `importlib.resources.files("little_loops")` rather than a raw path read (wheel-install compatibility).
- `scripts/tests/test_config_schema.py` — the two-guard consistency gate (Guard 1 `test_design_tokens_in_schema` ~`:444` cross-checks `BRConfig.to_dict()` against `config-schema.json` defaults; Guard 2 `_DATACLASS_SECTION_MAP` ~`:1284` maps `DesignTokensConfig` → `design_tokens`) hard-fails unless `source` lands in the dataclass, `config-schema.json`, and `core.py:888-897`'s `to_dict()` dict together.
- `scripts/tests/test_cli_loop_lifecycle.py:921-948` (`test_design_tokens_context_injected_via_cmd_resume`) — must keep passing unchanged; this issue alters neither injection site. *(BUG-3266 owns the opt-out counterpart, ENH-3267 the guidance counterpart.)*

### Documentation
- `docs/reference/CONFIGURATION.md` — `design_tokens.source`
- `docs/reference/API.md` — `little_loops.design_tokens` public surface
- `docs/guides/GETTING_STARTED.md` — DESIGN.md as the low-friction authoring path

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:1007,1009` — names `DesignTokensConfig` and describes the pre-injection-into-FSM-context pattern; update for the new source/guidance model
- *(`docs/guides/LOOPS_REFERENCE.md` and `docs/generalized-fsm-loop.md:1099` document the runner-injected context vars; they need edits for `design_guidance_context` under ENH-3267, not here.)*
- `skills/configure/areas.md:1107-1255` — full "Area: design_tokens" interactive `/ll:configure` section enumerating every `DesignTokensConfig` field individually; needs a `source` question/branch
- `skills/configure/show-output.md:186-198` — parallel `design_tokens --show` template listing the same fields

### Configuration
- `.ll/ll-config.json` → `design_tokens.source` (new, default `auto`)
- Root `DESIGN.md` becomes a recognized project file (discovery, not config)

## Program Design

### Types

- `DesignTokens` — at `design_tokens.py:26-34`; frozen dataclass, currently 5 required fields (`primitives`, `semantic`, `theme`, `resolved`, `source_path`), all positional/keyword, no defaults. **`source_path` changes meaning under a DESIGN.md source**: today it is always a *directory* (the resolved token root, `design_tokens.py:221`); for DESIGN.md it becomes a *file* path. Only two call sites read it, both tests (`test_design_tokens.py:92`, `test_enh1768_profile_system.py:178`), so this is safe — but update the field's docstring to say "token root directory, or the DESIGN.md file when the source is `design_md`", since the widening is invisible to the type annotation (`Path` either way). The one production constructor call is at `design_tokens.py:216-222` inside `load_design_tokens()`. Adding `guidance: str = ""` and a source discriminator (e.g. `source: str = "profile"`) requires defaults — the dataclass is frozen and has 5+ construction call sites across `design_tokens.py` and `scripts/tests/test_design_tokens.py` / `scripts/tests/test_enh1768_profile_system.py` that would otherwise all need updating.
- `DesignTokensConfig` — at `scripts/little_loops/config/features.py:327-359`; plain dataclass, no existing field for source-format selection. Fields: `enabled: bool = True`, `path: str = ".ll/design-tokens"`, `primitives_file: str = "primitives.json"`, `semantic_file: str = "semantic.json"`, `themes_dir: str = "themes"`, `active_theme: str = "dark"`, `active: str = "default"`, `profiles_dir: str | None = None`, plus `from_dict(cls, data: dict[str, Any]) -> DesignTokensConfig`. `design_tokens.source` (ENH-3264's new config knob) is added here, defaulted via `from_dict`.
- `scripts/little_loops/cli/loop/lifecycle.py:891-896` separately builds a display/config-echo dict from `primitives_file`/`semantic_file`/`themes_dir`/`active_theme`/`profiles_dir` — outside the analyzer's confirmed-seed set, so unconfirmed whether it needs mirroring for a new `source` field; verify at implementation time.

### Signatures

- `load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None` — at `design_tokens.py:160-222`; unchanged signature per the issue's design, gains an internal source-format branch. Returns `None` when `dt_cfg.enabled` is `False`, `base_path` doesn't exist, or `_resolve_token_root()` degrades to `None`. Raises `ValueError` on circular/unknown references, propagated from `_resolve_references`/`_resolve_value`.
- `_flatten(obj: Any, prefix: str = "") -> dict[str, Any]` — at `design_tokens.py:44-64`; the ENH-1769 DTCG-absorption seam this issue's precedent points at. A dict node with a `"$value"` key is treated as a leaf (`:54-56`) and other `$`-prefixed sibling keys are skipped (`:58-59`), letting a differently-shaped input (W3C DTCG JSON) flatten through the *same* function as the legacy format — no separate DTCG loader exists. A DESIGN.md adapter needs to produce this same `dict[str, Any]` dotted-key shape, not a parallel pipeline.
- `_resolve_references(flat: dict[str, Any], primitives_flat: dict[str, Any], *, _resolving: frozenset[str] | None = None) -> dict[str, str]` — at `design_tokens.py:67-126`; pairs with `_resolve_value(key: str, raw: Any, flat: dict[str, Any], primitives_flat: dict[str, Any], resolving: frozenset[str]) -> str`, which handles `{token.reference}` syntax with a lookup order (primitives_flat → same-layer flat, recursively → DTCG `.$value`-suffixed fallback at `:95-125`). Whatever `_load_design_md()` produces must be `flat`-shaped before reaching this call — it is not itself extended for DESIGN.md.
- `_resolve_token_root(dt_cfg: Any, base_path: Path) -> Path | None` — at `design_tokens.py:129-157`; the fallback-chain pattern (prefer active profile dir → degrade-with-stderr-warning if profiles layout exists but `active` is missing → fall back to legacy flat `base_path`) whose *shape* a `source: auto` resolution should mirror. **It is not the host for the new branch** — it runs downstream of the `base_path.exists()` guard at `:180`, which a DESIGN.md-only project never gets past. See Decision Rules → Placement.
- `parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]` (`frontmatter.py:255`) and `strip_frontmatter(content: str) -> str` (`:416`) — the existing house helpers `_load_design_md()` is built on. `strip_frontmatter` yields the prose body for `DesignTokens.guidance` directly; no new YAML dependency and no bespoke parser. Two caveats confirmed by reading the implementations:
  - **They disagree about multiple blocks.** `parse_frontmatter` scans for *several* `---` blocks and merges them (`_iter_frontmatter_blocks`, `frontmatter.py:161-191`, BUG-2955), bounded to the header region up to the first `^## ` heading and skipping fenced code; `strip_frontmatter` cuts at the *first* closing fence (`:432-436`). A DESIGN.md that opens with an `# Title` h1 followed by a `---` thematic break before its first `## ` heading could have that rule absorbed as a second token block (it must parse as a YAML mapping to be accepted, so the risk is low) while its text simultaneously remains in the prose body. Add one test pinning the behavior for an h1-then-rule document.
  - **Everything arrives as `str`.** `parse_frontmatter` loads with `yaml.BaseLoader`, which resolves all scalars to strings. Harmless here, and the reason `coerce_types` should be left off (see Proposed Solution #1).

### Call Path

`cmd_run` (`cli/loop/run.py:228-254`) / `cmd_resume` (`cli/loop/lifecycle.py:707-717`, structurally identical injection block) -> `load_design_tokens()` (`design_tokens.py:160`) -> **[source-format branch point, `:178-179`, immediately after the `dt_cfg.enabled` check and *before* `base_path` is computed]** -> _(design_md branch)_ `_load_design_md()` -> `_flatten()` -> `_resolve_references()` -> `DesignTokens(...)`; _(profile branch)_ `base_path.exists()` guard (`:180`) -> `_resolve_token_root()` (`:184`) -> `_load_json()` x5 -> `_flatten()` x5 (`:197-201`) -> merge in fixed layer order `semantic → typography → spacing → theme` (`:204-209`, primitives excluded from the merge, used only as the reference lookup table) -> `_resolve_references()` (`:210`) -> `DesignTokens(...)` construction (`:216-222`) -> `render_as_prompt_context()`.

Second call path, single call site with two invocations: `_themed_css_vars()` (`cli/artifact.py:59-74`) calls `load_design_tokens(config, theme="light")` and `load_design_tokens(config, theme="dark")` independently — the only two-theme consumer in the codebase. `_resolve_token_root()` does not vary by theme; only the `theme_file` lookup inside `load_design_tokens` (`:193-195`) does. Since DESIGN.md describes one `colors` block with no per-theme file, this is the concrete site where the "theme degradation ⇒ warn, not silent" requirement (Expected Behavior #4) must be implemented — either both calls resolve to the same `DesignTokens` object, or the function falls back to the existing neutral empty-block output already present at `:70-73`.

### Decision Rules

- **Source-format selection** (`design_tokens.source: auto | profile | design_md`): `auto` prefers a **materialized profile** and falls back to a root `DESIGN.md` — keyed on what exists on disk, *not* on whether `active` is set, which is undecidable because `active` defaults to `"default"` in both the dataclass (`config/features.py:346`) and `from_dict` (`:356`). See "The `auto` rule" under Proposed Solution.
  - **Placement:** this decision sits in `load_design_tokens()` at `:178-179`, *not* inside `_resolve_token_root()` (`:129-157`). `_resolve_token_root()` runs after the `if not base_path.exists(): return None` guard at `:180`, and a DESIGN.md-only project has no `.ll/design-tokens/` directory — branching there would short-circuit the primary use case to `None`. `_resolve_token_root()`'s 3-branch fallback shape (prefer A → degrade-with-warning → fall back to B) is still the *stylistic* model to copy; it is not the host function.
- **Theme degradation**: when the active source is DESIGN.md and a caller requests a specific `theme=` (as `_themed_css_vars` does for both `"light"` and `"dark"`), the resolver must not silently return divergent or empty output — it must emit the existing stderr-warning idiom (matching `design_tokens.py:149`'s degradation branch) and fall back to a single-theme result. Escape hatch: none — this only fires when the resolved source is DESIGN.md; profile-sourced projects are unaffected.
  - **Where the "warn once" lives.** `_themed_css_vars()` (`cli/artifact.py:66-67`) makes two *fully independent* `load_design_tokens()` calls sharing no state. "Exactly one warning across both calls" therefore has no mechanism inside the loader short of module-level `_warned` state — which leaks across calls in a long-lived process and makes any test of it order-dependent. **Chosen: dedupe at the call site.** `load_design_tokens()` warns at most once *per call*; `_themed_css_vars()` calls the loader once for a DESIGN.md source and reuses the single `DesignTokens` for both the `:root` and `[data-theme=dark]` blocks — so exactly one warning is emitted because the loader is only entered once. Do not add module-level warning state.
  - **How the call site detects the source — it must call first.** "Enter the loader once *for a DESIGN.md source*" is circular as stated: `_themed_css_vars()` cannot know the source before it calls, and re-probing the filesystem there would duplicate the `auto` rule in a second place where it can drift. **Mechanism:** call `load_design_tokens(config, theme="light")` once, then branch on the returned object's `source` discriminator — reuse it for both blocks when it is `"design_md"`, and only make the second `theme="dark"` call when it is `"profile"`. The `None` guard at `artifact.py:70-73` is checked before the branch, unchanged.

    This makes the `source` field on `DesignTokens` **load-bearing rather than informational** — it is the only supported way a consumer learns which branch produced its tokens, so it must be set on both branches (`"profile"` / `"design_md"`), not just defaulted. AC 6 asserts it.

- **Unresolvable-reference handling is source-dependent**: profile sources raise `ValueError` (unchanged); DESIGN.md sources warn and return `None`. See "Unresolvable references degrade, they do not raise".

## Implementation Steps

1. Extend `DesignTokens` with a `guidance: str` field (default `""`) and a `source: str` discriminator (default `"profile"`), **set explicitly on both branches** — `cli/artifact.py` reads it (see Decision Rules).
2. Vendor the spec's example DESIGN.md as a checked-in test fixture (no network in the suite), recording the spec revision.
3. Implement `_load_design_md()` on top of `frontmatter.parse_frontmatter` (no `coerce_types`) / `strip_frontmatter`, keyed off the `DESIGN_MD_FILENAME` constant. One namespace-mapping table drives all four renames (`colors`→`color`, `typography`→`font`, `spacing`→`space`, `rounded`→`radius`) **and** the matching `{ref}` alias rewrite. Drop `components` before mapping. Normalize list values before flattening. Return the *nested* mapped dict so the branch can both `_flatten()` it and hand it to `DesignTokens.semantic`. Test against the vendored fixture.
4. Branch `load_design_tokens()` on `design_tokens.source` **at `:178-179`, above the `base_path.exists()` guard at `:180`**; implement the filesystem-based `auto` rule — using the *token-files-exist* materialization test, not `_resolve_token_root() is not None` — the theme-degradation warning (explicit-`theme=` callers only), and the DESIGN.md-only `try`/`except ValueError` → warn-and-return-`None` path.
5. Add `design_tokens.source` to `config-schema.json` and to the `/ll:configure` (`skills/configure/areas.md:1107-1255`, `show-output.md:186-198`) + `ll-init` (`init/{core,writers,summary,tui,cli}.py` profile picker) surfaces.
5b. Add a DESIGN.md branch to `hooks/session_start.py:303-325` so a DESIGN.md-only project stops emitting the spurious *"design_tokens.enabled is true but path … does not exist"* warning on **every session start** (`session_start.py:309-313`). This runs before `load_design_tokens()` is ever called and re-implements the check against the raw config dict, so it needs its own copy of the discovery + materialization logic — keep the two consistent.
6. Resolve the `render_as_prompt_context()` semantic-role gap — option **(a)** from "Prompt-context quality under a DESIGN.md source". Two parts: (i) map well-known spec color names onto `surface`/`text`/`border`/`action` in the *nested* dict so the gate at `:234-239` fires; (ii) add the residual bucket + its `_emit_group` call at `:310-315` so unmapped names stop being silently dropped. Do not leave the bare flat-list fallback in place.
7. Update `_themed_css_vars()` (`cli/artifact.py:59-74`) to enter `load_design_tokens()` once for a DESIGN.md source and reuse the result for both theme blocks.
8. Docs: `docs/reference/CONFIGURATION.md`, `docs/reference/API.md` — including the namespace mapping table and the "only whole-value `{ref}` aliases resolve" limitation.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `source: str = "auto"` to `DesignTokensConfig` in `config/features.py:328-359` (not `config/core.py` — that file only holds the `to_dict()` echo)
- Update `config/core.py:888-897`'s `to_dict()` echo dict with a `source` key, in lockstep with the schema change — `test_config_schema.py`'s two-guard consistency gate fails otherwise
- Confirm `cli/loop/run.py:242-254` and `cli/loop/lifecycle.py:707-717` keep working untouched — this issue changes neither the `DesignTokens` construction signature nor `load_design_tokens()`'s, so both injection sites are pass-through. *(BUG-3266 owns the shared-helper extraction.)*
- Add a matching DESIGN.md-source degradation branch to `hooks/session_start.py:303-325`'s independently re-implemented warning logic
- Confirm `cli/verify_design_tokens.py` / `doctor.py:847-883` degrade to the existing informational "profiles directory not found" status for DESIGN.md-sourced projects rather than erroring
- Add `TestLoadDesignTokensDesignMdFormat`-style tests to `test_design_tokens.py` following the ENH-1769 `TestLoadDesignTokensDtcgFormat` pattern (`:95-176`), and mirror `test_enh1768_profile_system.py`'s four config-field test classes for `source`

## Scope Boundaries

**In scope**

- DESIGN.md as a read source feeding the existing resolver.
- `design_tokens.source` config knob + its `/ll:configure`, `ll-init`, and schema surfaces.
- Resolving the semantic-role gap and the silently-dropped-key gap in `render_as_prompt_context()`.
- Populating `DesignTokens.guidance` from the parsed prose body (consumed by ENH-3267).
- **Vendoring the spec's example DESIGN.md as a test fixture.** Acceptance Criterion 4 tests against it and the suite has no network access, so the file must be checked in (under `scripts/tests/fixtures/`, or inline in the test module following whatever `test_design_tokens.py` already does for JSON fixtures). Record the spec revision it was copied from — the spec is `alpha` and will churn.

**Out of scope**

- Replacing or deprecating the profile format. Profiles stay the canonical internal model; nothing about the existing five-file layout changes.
- Materializing `profiles/<name>/*.json` from a DESIGN.md, in either direction, on disk. The import is in-memory only — a checked-in generated copy would drift.
- Themes under DESIGN.md. No non-spec `themes:` key. Projects needing light/dark keep profiles.
- **The exporter** — `render_as_design_md`, the `ll-artifact design-md export` subcommand, the lossy key mapping and dropped-groups note. All ENH-3268.
- **Injecting the prose body into prompts** — `design_guidance_context` and the `html-website-generator.yaml` consumption. ENH-3267. This issue only populates the field.
- **The `cmd_resume` opt-out gap and the shared-helper extraction.** BUG-3266.
- Tracking `alpha`-spec churn. Pinning to the 2026-04-21 draft is acceptable for the first cut.
- Any change to `_resolve_references()` / `_resolve_value()`. The DESIGN.md adapter produces the flat dotted-key shape those already consume — if it needs them modified, the mapping is wrong.
- **`components:` as tokens.** Dropped before mapping; it reaches the model via ENH-3267's prose channel. See Resolved Questions.
- **A configurable DESIGN.md location.** Case-exact `DESIGN.md` at the project root, no knob. See "Discovery".

**Optional de-risking (implementer's call)**

The residual-bucket half of AC 7b — adding a seventh bucket + `_emit_group("Other", …)` to `render_as_prompt_context()` — is the one change here that alters output for **profile** sources too, and it is independent of everything DESIGN.md. Landing it as its own small commit *ahead* of the import work is a legitimate sequencing choice: it lets the "three built-in profiles' output is unchanged" assertion be verified in isolation, and shrinks this issue's blast radius to the import edge. Not a split — same issue, just a suggested commit boundary.

## Acceptance Criteria

Each is individually testable.

1. A project whose only design artifact is a root `DESIGN.md` (no `.ll/design-tokens/` directory at all) gets a non-`None` `DesignTokens` from `load_design_tokens()`, and `ll-loop run` injects a non-empty `design_tokens_context`. *(Guards the `base_path.exists()` short-circuit at `design_tokens.py:180`.)*
2. A project with **both** a materialized profile and a root `DESIGN.md`, under `source: auto`, resolves to the profile — including when `active` is left at its `"default"` value.
2b. A project with an **empty (or token-file-less) `.ll/design-tokens/` directory** and a root `DESIGN.md`, under `source: auto`, resolves to **DESIGN.md** — not to a hollow profile yielding an empty `design_tokens_context`. *(Guards the weak `_resolve_token_root() is not None` materialization test; see "'Materialized' must mean token files exist".)* Same project under `source: profile` keeps today's behavior exactly.
3. `source: profile` ignores a root `DESIGN.md` entirely; `source: design_md` with no root `DESIGN.md` returns `None` and writes a stderr warning. A lowercase `design.md` is **not** discovered under any source setting (case-exact match on `DESIGN_MD_FILENAME`).
4. The spec's own example DESIGN.md (vendored as a test fixture — see below) parses, and its `{colors.primary}`-style aliases resolve to concrete values. `_resolve_references()` / `_resolve_value()` are **not** modified; the `{colors.*}`→`{color.*}` rewrite happens inside `_load_design_md()` alongside the key rename. *(Guards the namespace contradiction described in "Alias rewriting".)*
5. Malformed / absent frontmatter degrades to `None` with a stderr warning — no traceback.
5b. A **well-formed** DESIGN.md containing an unresolvable `{ref}` degrades to `None` with a stderr warning naming the offending reference — no traceback out of `ll-loop run`. Profile-sourced projects still raise `ValueError` for the same defect (behavior unchanged).
6. `_themed_css_vars()` (`cli/artifact.py:59-74`) does not crash for a DESIGN.md-sourced project; the `:root` and `[data-theme=dark]` blocks are generated from a single `DesignTokens`, and exactly one degradation warning is emitted — achieved by entering `load_design_tokens()` once at that call site, not by module-level warning state. The one-call path is driven by branching on the returned `DesignTokens.source`, so this AC also pins that `source` is set to `"design_md"` / `"profile"` on the respective branches rather than left at its default.
6b. `ll-loop run` in a DESIGN.md-sourced project emits **no** theme-degradation warning (it calls `load_design_tokens()` with `theme=None`); only the explicit-`theme=` caller warns.
7. `render_as_prompt_context()` output for a DESIGN.md source contains the contrast-guardrail paragraph, which requires the design_md branch to populate the **nested** `DesignTokens.semantic` dict — the gate at `design_tokens.py:234-239` reads `tokens.semantic["color"]`, not `tokens.resolved`. *(Fails today's flat-list fallback — this is the test for Implementation Step 8.)*
7b. Non-color tokens survive into the prompt: a DESIGN.md with `typography`, `spacing`, and `rounded` blocks produces a `render_as_prompt_context()` output whose Typography and Layout groups are non-empty (guards the `font.`/`space.`/`radius.` renames), and a token in no known namespace appears in the new residual group rather than being silently dropped by the bucket loop at `:274-290`. A `components:` block contributes **nothing** to `resolved` — it appears in neither the residual group nor `render_as_css_vars()` output.
7c. A list-valued frontmatter entry (e.g. a font stack) renders as a joined string — no `['Inter', 'sans-serif']` Python repr in either `render_as_prompt_context()` or `render_as_css_vars()` output.
8. `DesignTokens.guidance` holds the DESIGN.md prose body (frontmatter stripped) for a DESIGN.md source, and `""` for a profile source. *(ENH-3267 asserts what happens to it downstream; this issue only asserts it is populated.)*
9. `ll-verify-design-tokens` and `ll-doctor` report the existing informational "profiles directory not found" status for a DESIGN.md-sourced project — not an error, not a false positive.
9b. `hooks/session_start.py`'s config validation emits **no** warning for a DESIGN.md-only project (no `.ll/design-tokens/` directory, `design_tokens.enabled` at its `True` default). *(Today this unconditionally appends "design_tokens.enabled is true but path '.ll/design-tokens' does not exist" at `session_start.py:309-313` — it would fire on every session start for exactly the user in Expected Behavior #1.)*
9c. `design_tokens.source` is reachable from both configuration surfaces: `/ll:configure design_tokens` offers it as a question and `--show` renders its current value, and `ll-init`'s profile picker offers DESIGN.md alongside the built-in profiles. Covered by the `TestConfigureWiringForProfiles` mirror named in the Tests section.
10. All 15 built-in loops still receive `design_tokens_context` unchanged under a DESIGN.md source.
11. `python -m pytest scripts/tests/` exits 0 — in particular `test_config_schema.py`'s two-guard gate, with `source` landing in the dataclass, `config-schema.json`, and `core.py:888-897`'s echo dict together.

## Impact

- **Scope**: `design_tokens.py`, `config-schema.json`, `config/features.py`, `config/core.py`, `cli/artifact.py` (`_themed_css_vars` only), `hooks/session_start.py`, init/configure UX, docs. Estimated ~150 LOC for the reader plus tests. *(Down from ~9 modify sites to ~7 after the split; the exporter's ~80 LOC and the two loop-runner sites left with ENH-3268 / BUG-3266.)*
- **Compatibility**: additive. Default `source: auto` with no root `DESIGN.md` present preserves today's behavior exactly.
- **Risk**: the spec is `version: alpha` and may churn. Confining it to an import edge — rather than the internal model — is what keeps that churn cheap.

## API/Interface

- `little_loops.design_tokens._load_design_md(path: Path) -> tuple[dict[str, Any], str]` — new, private; returns `(nested_mapped_tokens, prose_body)`. **Nested, not flat** (revised — see "`DesignTokens.semantic` must be populated as a *nested* dict"): the caller runs the existing `_flatten()` over it for `resolved` and passes the same object as `DesignTokens.semantic`, which is what `render_as_prompt_context()`'s guardrail gate inspects. Built on `little_loops.frontmatter.parse_frontmatter` / `strip_frontmatter`, not a new YAML reader.
- `little_loops.design_tokens.load_design_tokens(config, theme=None) -> DesignTokens | None` — signature unchanged; gains DESIGN.md source resolution at `:178-179`.
- `little_loops.design_tokens.DesignTokens.guidance: str = ""` — new field, populated from the prose body. Consumed by ENH-3267.
- `little_loops.design_tokens.DesignTokens.source: str = "profile"` — new field; `"profile" | "design_md"`, set explicitly on both branches. **Public, not informational**: `cli/artifact.py:_themed_css_vars()` branches on it to decide whether to make the second themed load (see Decision Rules → "How the call site detects the source").
- `little_loops.design_tokens.DESIGN_MD_FILENAME: str = "DESIGN.md"` — new module constant; case-exact, project-root only, not configurable.
- Config: `design_tokens.source` enum added to `config-schema.json`.
- No CLI surface in this issue. `ll-artifact design-md export` is ENH-3268; `design_guidance_context` is ENH-3267.

## Open Questions

- *(None open. The two exporter questions — generated prose body, reversible key mapping — moved to ENH-3268.)*

### Resolved Questions

- ~~Does `components:` map usefully into prompt context, or is it out of scope for the first cut?~~ **Resolved: excluded from the token dict in this cut.** It is structural guidance, not tokens; flattening it would both flood the generator prompt with `components.button.radius`-style leaves *and* emit them as `--components-button-radius` custom properties. It reaches the model through ENH-3267's prose channel instead. See Proposed Solution #1 and AC 7b.

- ~~Where does `ll-design` live — a new entry point, or a subcommand of the existing `ll-artifact`?~~ **Resolved: `ll-artifact design-md export`** — carried forward to ENH-3268. No new console script, so `scripts/pyproject.toml` and `cli/__init__.py` drop out of the Integration Map for both issues.
- ~~`auto` precedence keyed on whether `active` is set.~~ **Resolved: keyed on what is materialized on disk** — `active` defaults to `"default"` in both the dataclass and `from_dict`, so "unset" is not observable.
- ~~`render_as_design_md(light, dark)`.~~ **Resolved: `render_as_design_md(tokens)`** — the spec has no theme mechanism. Carried forward to ENH-3268.
- ~~Semantic-role mapping: option (a) or option (b).~~ **Resolved: option (a).** The `colors`→`color` key rename is required anyway (otherwise no `color.*` role prefix in `render_as_prompt_context` ever matches), and it forces the `{colors.*}`→`{color.*}` alias rewrite. Once both are in place, mapping well-known spec names onto the four semantic roles is the natural completion; option (b)'s "just re-emit the guardrail paragraph" would leave the role grouping permanently dead for DESIGN.md sources.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-20_

Re-run post four-way split (ENH-3264/BUG-3266/ENH-3267/ENH-3268). All `format-check`
gap signals (`missing_behavior_parity`, `stale_symbol_ref`/`stale_cli_flag`,
`unapplied_decision`, `template_placeholders`/`boilerplate`) are empty, the Program
Design gate passes, and there is no unresolved `blocked_by` entry — readiness scores
max on all five criteria. Outcome confidence is unchanged from the pre-split score:
the split reduced actively-*modified* sites (~9 → ~6) but not the breadth bracket
(6-15) or the dependent-surface bracket (6-10 callers that must keep working
unchanged), so the arithmetic nets to the same total.

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across ~6 actively-modified sites (design_tokens.py, config-schema.json, config/features.py, config/core.py, cli/artifact.py, hooks/session_start.py) with cross-module consistency requirements — the two-guard `test_config_schema.py` gate must see `source` land in the dataclass, schema, and `core.py`'s `to_dict()` echo simultaneously or it hard-fails.
- Moderate depth from shared-state coordination rather than pure mechanical edits — the `load_design_tokens()` source branch, the namespace-rename + alias-rewrite table, the nested-`semantic` construction for the prompt-context gate, and the residual-bucket addition to `render_as_prompt_context()` (which changes output for **profile** sources too) all touch existing logic rather than adding isolated new code.
- Broad dependent surface (~6-10 call sites/consumers of `load_design_tokens()`/renderers — `artifact.py`, `doctor.py`, `verify_design_tokens.py`, `init/*.py`, `session_start.py`, plus 15 built-in loop YAMLs that must keep receiving `design_tokens_context` unaffected) that must keep working unchanged; verify each at implementation time rather than assuming pass-through safety.

## Session Log
- `/ll:confidence-check` - 2026-08-20T21:33:49 - `ff90fea6-905c-4a3b-9ca3-a82cdf5d6ffd.jsonl`
- `/ll:confidence-check` - 2026-08-20T21:20:10 - `258d49d0-ba4c-49f3-a1e8-6f2e12d7799a.jsonl`
- `/ll:confidence-check` - 2026-08-20T21:01:05 - `0d64dd59-9207-4726-a40b-813a377a1fec.jsonl`
- `/ll:confidence-check` - 2026-08-20T20:53:03 - `0ffa5e40-eabf-4e3f-9ddd-d1fd94489393.jsonl`
- `/ll:confidence-check` - 2026-08-20T20:33:22 - `1e7934c2-3f73-4b02-90d0-4a6aa50feef9.jsonl`
- `/ll:wire-issue` - 2026-08-20T20:24:02 - `7dde0c7a-2cdb-4340-890f-4e20e23fbdb7.jsonl`
- `/ll:refine-issue` - 2026-08-20T20:13:14 - `d3c778e1-6920-4445-bc39-5861315da162.jsonl`
- `/ll:capture-issue` - 2026-08-20T20:05:28 - `d2d69b09-ffdb-4870-8c2e-8b37aae045ea.jsonl`
- `/ll:capture-issue` - 2026-08-20T20:04:38 - `d2d69b09-ffdb-4870-8c2e-8b37aae045ea.jsonl`
