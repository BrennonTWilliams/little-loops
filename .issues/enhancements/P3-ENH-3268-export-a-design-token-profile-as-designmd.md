---
id: ENH-3268
type: ENH
title: Export a design-token profile as DESIGN.md
priority: P3
status: open
depends_on:
- ENH-3264
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T21:10:34Z'
labels:
- enhancement
- design-tokens
- cli
confidence_score: 90
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3268: Export a design-token profile as DESIGN.md

## Summary

Export a little-loops design-token profile out to a valid [DESIGN.md](https://github.com/google-labs-code/design.md), for handoff to Cursor / Copilot / another little-loops project. Adds `render_as_design_md(tokens)` plus an `ll-artifact design-md export` subcommand.

The export is **lossy by construction** — the spec has no theme mechanism and no home for several token groups the built-in profiles carry — so the design constraint is that every dropped axis is reported on stderr, never silently omitted.

## Current Behavior

Design tokens are only expressible as a multi-file profile under `.ll/design-tokens/profiles/<name>/` (`primitives.json`, `semantic.json`, `typography.json`, `spacing.json`, `themes/<theme>.json`). There is no way to emit a profile in any portable format for another agent or tool to consume.

## Expected Behavior

1. `ll-artifact design-md export` writes a valid DESIGN.md for the project's active profile.
2. `--profile <name>` exports a named profile, including the packaged built-ins.
3. `--theme <name>` selects which theme is flattened into the single-theme output.
4. Every lossy axis — the dropped theme(s), every dropped token group, and the typography axes lost to the axis→role synthesis — is named in a stderr note.
5. The output carries a `name:` key and, for a DESIGN.md source, the original prose body.

## Motivation

Portability out. The spec is a plausible de-facto standard play (the bet OpenAPI made for REST); being able to emit one makes little-loops' three built-in profiles usable outside little-loops.

## Proposed Solution

### The exporter is single-theme by construction

The DESIGN.md spec has no theme mechanism, so `render_as_design_md` has nowhere to put a second `DesignTokens` and takes one:

```python
render_as_design_md(tokens: DesignTokens) -> str
```

The CLI resolves the profile at `design_tokens.active_theme` (or `--theme`), emits the corresponding single-theme DESIGN.md, and writes a stderr note naming which theme was exported and which were dropped.

### Themes are not the only lossy axis

Confirmed against `templates/design-tokens/profiles/warm-paper/`:

- `spacing.json` top-level keys are `space`, `radius`, `shadow`, `border`. The spec frontmatter (`colors`, `typography`, `spacing`, `rounded`, `components`) has no home for `shadow.*` or `border.width.*`; `themes/dark.json` adds a second `shadow` block.
- `semantic.json` colors nest three levels deep (`color.surface.primary`) and must collapse into the spec's flat one-level `colors:` map, so exported key names differ from the originals.
- Metadata keys (`_note` in `typography.json`/`spacing.json`, `_wcag_spot_check` in `semantic.json`) are export-only noise and are dropped **silently**, per the `if name.startswith("_"): continue` convention every existing renderer already follows (`:571`, `:603`, `:674`). They are not a lost *token group* and naming them in the dropped-groups note only dilutes it.
- **`components:` is lost on the DESIGN.md → DESIGN.md path and must be reported.** `_map_design_md_namespaces` drops the `components` block on *import* (`design_tokens.py:280-281`), and no profile has anything to emit there, so an import→export round trip of a real DESIGN.md silently loses the spec's richest block — the one Cursor/Copilot actually consume. This is out of scope to preserve (nothing in `DesignTokens` carries it), but it **is** in scope to report: when `tokens.source == "design_md"`, the dropped-groups note says so.

The exporter therefore emits the **spec-expressible subset** under a documented, deterministic key mapping and writes a stderr note listing every dropped group.

### Scalar typing: the round trip cannot see quoting bugs

`parse_frontmatter` reads frontmatter with `yaml.load(..., Loader=yaml.BaseLoader)` (`frontmatter.py:153,206`), which keeps **every scalar and key a string**. AC 1's round trip therefore passes whether or not the exporter quotes anything — it is structurally blind to type drift. An external consumer using a normal `yaml.safe_load` sees something different: `radius.none: 0`, `space.0: 0`, and font weights `400` parse as **ints**, and `spacing:`'s numeric keys (`0`, `1`, `2`, …) become **int keys**.

Since portability-out is the whole motivation, the exporter must emit quoted scalars *and* quoted keys, and a test must assert this through `yaml.safe_load` (not through the house parser) — see AC 12.

### The key mapping must be classifier-aware, and the round trip is not key-identical

**This is the decision AC 1 hangs on.** Import is not the inverse of a naive `role`+`name` join. `_map_design_md_namespaces` (`design_tokens.py:284-296`) runs every flat `colors:` name through `_classify_design_md_color_role` (`:63-73`), which *re-derives* a role from the name and nests under it. That classifier only recognizes Material-style names (`on-*`, `surface*`, `outline*`, `primary|secondary|tertiary|accent|error`) — it was written for the upstream fixture, not for little-loops' own output. Tracing warm-paper through the naive mapping:

| profile key | naive export | `_classify…` role | re-imported key |
|---|---|---|---|
| `color.surface.primary` | `surface-primary` | `surface` | `color.surface.surface-primary` ✗ doubled |
| `color.text.primary` | `text-primary` | **None** | `color.text-primary` ✗ role lost |
| `color.border.subtle` | `border-subtle` | **None** | `color.border-subtle` ✗ role lost |
| `color.action.primary` | `action-primary` | **None** | `color.action-primary` ✗ role lost |

Three of the four roles land in the residual bucket. The exporter must therefore emit **classifier-recognized names** so a re-import recovers the role.

**The mapping is a generic per-role rule, not a per-leaf allowlist.** An enumerated table covering only the built-ins' twelve semantic leaves silently regresses on any user profile with a different leaf name, and it also misses a leaf the built-ins *do* carry: `action.destructive` → `destructive` → `_classify_design_md_color_role` returns **None** → residual bucket → AC 2 fails on all three built-ins. Every name produced by the rule below was run through the live classifier and lands in its intended role:

| profile key | export name | re-classified role |
|---|---|---|
| `color.surface.<n>` | `surface` when `n == "primary"`, else `surface-<n>` | `surface` ✓ |
| `color.text.<n>` | `on-surface` when `n == "primary"`; `inverse-on-surface` when `n == "inverse"`; else `on-surface-<n>` | `text` ✓ |
| `color.border.<n>` | `outline` when `n == "primary"`, else `outline-<n>` | `border` ✓ |
| `color.action.<n>` | `primary` when `n == "primary"`, else `accent-<n>` | `action` ✓ |

Note `action.destructive` → `accent-destructive` (or `error`), **not** `destructive`. `accent-*` does not collide with `editorial-mono`'s `color.accent.*` primitives, because primitives are excluded from the export entirely (see Decision Rules).

Even under this rule the *leaf* name changes (`color.border.subtle` → `outline-subtle` → `color.border.outline-subtle`), so **keys never round-trip identically — only roles and values do**. AC 1 is stated in terms of the composed forward∘import mapping, not the forward mapping alone.

Nesting the colors block instead does **not** rescue this: `_normalize_design_md_leaf` (`:228-230`) returns dicts untouched, so a nested `colors: {surface: {primary: …}}` flattens to `color.surface.surface.primary`. The importer assumes a one-level-flat `colors:` map; the exporter must produce one.

### Typography is a structural transform, and spec shape wins

little-loops typography is **axis-organized** (`font.family.*`, `font.weight.*`, `font.size.*`, `font.line-height.*`, `font.letter-spacing.*`). DESIGN.md typography is **role-organized** — the vendored fixture has `display`, `headline-lg`, `body-md`, `label-sm`, each a composite of `fontFamily`/`fontSize`/`fontWeight`/`lineHeight`/`letterSpacing`. Nothing in a profile says "display = Fraunces @ 2.75rem/1.2"; that composition does not exist in our model.

Two options, in direct tension:

- **Emit the axis scales flat under `typography:`** — round-trips *exactly* through our own importer (`_rename_design_md_leaves` is recursive, so `typography.size.xs` → `font.size.xs`), but produces a document Cursor/Copilot will not read as a type ramp. Maximizes AC 1, defeats the Motivation.
- **Synthesize a role ramp** — portable and spec-shaped, but lossy and not round-trip-verifiable.

**Decision: spec shape wins.** Portability-out is the stated motivation, and an AC that rewards emitting a non-portable document is the wrong gate. The exporter synthesizes a role ramp; typography is excluded from AC 1's value-equality comparison and is instead covered by a shape assertion (every emitted role carries `fontFamily` + `fontSize`) plus a stderr note naming the axes that did not survive.

**The role table is pinned here, not left to the implementer.** There is no "corresponding" step to pair with: the profiles carry 8–9 `font.size.*` steps but only 3 `font.line-height.*` and 4 `font.weight.*` steps, and the built-ins' scales are not even the same shape (`editorial-mono` has a `5xl` the others lack). Left unspecified, two implementations produce two different documents. Role names below match the vendored fixture's; all three built-ins carry `font.family.body` and `font.family.heading`, so every role resolves:

| role | `font.size` | `font.family` | `font.line-height` | `font.weight` |
|---|---|---|---|---|
| `display` | `4xl` | `heading` | `tight` | `bold` |
| `headline-lg` | `3xl` | `heading` | `tight` | `bold` |
| `headline-md` | `2xl` | `heading` | `tight` | `semibold` |
| `title-lg` | `xl` | `heading` | `tight` | `semibold` |
| `body-lg` | `lg` | `body` | `relaxed` | `normal` |
| `body-md` | `base` | `body` | `normal` | `normal` |
| `label-md` | `sm` | `body` | `normal` | `medium` |
| `label-sm` | `xs` | `body` | `normal` | `medium` |

A role whose `font.size` step is absent from the profile is skipped and named in the stderr note. Every axis value not consumed by the table — unused size steps (`editorial-mono`'s `5xl`), the entire `font.letter-spacing.*` axis, the unpicked families (`sans`/`serif`/`mono`/`display`/`code`) and weights — is likewise named in the note. `letterSpacing` is a spec-supported per-role key but the profiles express it as a free-standing axis with no role association, so it is dropped rather than guessed.

### `--profile` is required, not optional polish

`load_design_tokens()` only ever reads `config.project_root / dt_cfg.path`, so it **cannot reach a packaged built-in** under `templates/design-tokens/profiles/<name>/`. Without `--profile`, round-tripping the three built-ins is only expressible by copying each template into a temp project and re-pointing config.

Semantics: unset ⇒ export the project's active profile via today's `load_design_tokens()` path; set ⇒ resolve the named profile from the project's `profiles_dir` first, falling back to the packaged templates via `importlib.resources.files("little_loops")` (the wheel-safe accessor established by `test_enh1768_profile_system.py::TestConfigSchemaProfileFields`).

### CLI placement

A subcommand of the existing `ll-artifact`, **not** a new `ll-design` console script — so `scripts/pyproject.toml` is untouched. `ll-artifact` is already the two-theme `load_design_tokens()` consumer (`cli/artifact.py:59-74`), which is exactly where the lossy single-theme decision has to be made anyway.

**`design-md export` is two subparser levels; today's parser has one.** `main_artifact()` builds a single `add_subparsers(dest="command")` and dispatches on `args.command` (`cli/artifact.py:164-186`), so `cmd_design_md_export` cannot be wired the way `cmd_policy_builder` is without a second level. Decision: nest a `add_subparsers(dest="subcommand", required=True)` under a `design-md` parser and dispatch on `(args.command, args.subcommand)`, keeping the `ll-artifact design-md export` surface stated in API/Interface. The alternative (flattening to `ll-artifact design-md-export`) is rejected: `design-md` is a namespace that will grow an `import`/`check` sibling.

## Program Design

### Types
- `DesignTokens` (frozen dataclass, `scripts/little_loops/design_tokens.py:27-43`) — `primitives: dict[str, Any]`, `semantic: dict[str, Any]`, `theme: dict[str, Any]`, `resolved: dict[str, str]` (the flat dotted-key → value map every existing renderer iterates), `source_path: Path`, `guidance: str = ""`, `source: str = "profile"` (`"profile"` or `"design_md"`). `render_as_design_md` takes this type and only this type — no new dataclass is introduced.

### Signatures
- `render_as_design_md(tokens: DesignTokens) -> str` — new, public; matches the existing renderer shape exactly: `render_as_prompt_context(tokens: DesignTokens) -> str` (`:545`), `render_as_css_vars(tokens: DesignTokens) -> str` (`:651`), `render_as_css_vars_themed(light: DesignTokens, dark: DesignTokens) -> str` (`:661`) — all take only `DesignTokens`, no config object, no I/O.
- `load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None` (`:354-357`) — existing loader the CLI path must still route through for the project's active profile; `--profile`/packaged-built-in resolution is new logic layered in front of it, not a change to this signature.
- `cmd_design_md_export(args: argparse.Namespace, logger: Logger) -> int` — new, following the one existing `cli/artifact.py` subcommand handler's shape, `cmd_policy_builder(args, logger)` (`:88-140`): whole body in `try/except Exception as exc: logger.error(str(exc)); return 1`, `logger.success(...)` on the success path, return 0/1.

### Call Path
`main_artifact()` subparser dispatch (`cli/artifact.py:164-186`) → new `cmd_design_md_export(args, logger)` → profile-root resolution (`_resolve_token_root`, `design_tokens.py:168-200` — note it reads `dt_cfg.active` off the config at `:184` and takes **no** profile-name override, so `--profile` needs either a new keyword param or a shim config object; it is not reusable unchanged — plus a new packaged-built-in fallback) → the loader's `_load_profile`-equivalent read → `render_as_design_md(tokens)` (new) → iterates `tokens.resolved` **minus every key in `_flatten(tokens.primitives)`** (see Decision Rules) → `sys.stderr.write` per dropped theme/group (existing `[little-loops] Warning: ...` convention, `design_tokens.py:192` et al.) → rendered string written to stdout or the `-o` target.

### Decision Rules
- **Primitives are excluded structurally, not by name allowlist.** `_load_profile` deliberately merges every primitive leaf into `resolved` (`design_tokens.py:395-398`, comment: *"Also include primitive leaf values in resolved"*), so a renderer that iterates `tokens.resolved` unfiltered emits warm-paper's full `color.paper.0…950` + `color.terracotta.*` palette into `colors:` — ~60 raw swatches burying the semantic signal that makes a DESIGN.md useful. Do **not** copy `render_as_prompt_context`'s `_PRIMITIVE_COLOR_PREFIXES` (`:592-599`): that hardcoded allowlist (`neutral/brand/accent/success/warning/danger`) does not cover `paper` or `terracotta`, so warm-paper's primitives already leak into its residual bucket today. The rule here is: skip any key present in `_flatten(tokens.primitives)`.
- **Emit `name:`.** The spec fixture opens with `name: Paws & Paths` (`scripts/tests/fixtures/design_md/paws_and_paths_DESIGN.md:2`). The export emits the profile name as the frontmatter `name:` key.
- **Prose body: emit `tokens.guidance`.** ENH-3267 landed `DesignTokens.guidance` (`:37-39`), populated even on degraded loads. For a `source == "design_md"` input the body round-trips for free; for a `source == "profile"` input `guidance` is `""` and the exporter emits a minimal section skeleton. No new parameter needed — the single-`DesignTokens` signature already carries it.
- `--profile <name>` resolution order: (1) resolve `name` under the project's configured `profiles_dir` via the existing `_resolve_token_root` path (`design_tokens.py:168-200`); if that path does not exist on disk, (2) fall back to the packaged built-in via `importlib.resources.files("little_loops").joinpath("templates/design-tokens/profiles", name)` — the single-file wheel-safe accessor pattern already used by `init/core.py:35` and confirmed by `test_enh1768_profile_system.py:451-462`, not the multi-candidate `Path` search in `cli/verify_design_tokens.py:_find_profiles_dir` (`:181-194`). Escape hatch: if neither location resolves, `cmd_design_md_export` returns 1 via `logger.error(...)` — never a silent empty export.
- **Emit quoted YAML scalars and quoted keys.** The house parser's `BaseLoader` makes every value a string on re-import, so nothing in the round trip forces this; a plain `safe_load` consumer is the one that breaks (`radius.none: 0` → int, `spacing:`'s `0`/`1`/`2` → int keys, `fontWeight: 400` → int). Emit with explicit quoting (e.g. `yaml.dump(..., default_style='"')` or a hand-rolled writer) so an external tool reads back exactly what a little-loops consumer does.
- **What the dropped-groups note covers, and what it does not.** In the note: the dropped theme(s), `shadow.*`, `border.width.*`, the typography axes/roles lost to the role synthesis, and — when `tokens.source == "design_md"` — the `components:` block dropped at import. Not in the note: `_`-prefixed metadata (`_note`, `_wcag_spot_check`), dropped silently per the existing renderer convention. Metadata is not a lost token group and listing it dilutes the signal.
- Dropped-groups/theme reporting: one `sys.stderr.write(f"[little-loops] Warning: ...\n")` call per AC 6, reusing the exact prefix/format every `load_design_tokens` warning already uses (`design_tokens.py:192-195`, `:439-442`, etc.) rather than `Logger.error`/`Logger.warning` — this codebase has two disagreeing stderr channels (raw `sys.stderr.write` at the `design_tokens.py` loader layer vs. `Logger`-mediated at the `cli/artifact.py` handler layer) and no prior convention for an *export* dropping fields specifically, so this rule pins which channel applies here.

## Integration Map

### Files to Modify
- `scripts/little_loops/design_tokens.py` — `render_as_design_md()` (new, public)
- `scripts/little_loops/cli/artifact.py` — new `design-md export` subcommand alongside the existing `policy-builder` subparser (`:155`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/package_data.py` — `PACKAGE_DATA_ASSETS` (`:28-49`) has no `("templates", "design-tokens", "profiles", ...)` entries; once `--profile`'s packaged-built-in fallback reads profile JSON via `importlib.resources`, register one tuple per file actually read. **Review-pass correction: this is manifest hygiene, not a shipping fix** — hatchling already ships these files (`pyproject.toml:192` `packages = ["little_loops"]`), so `--profile` works without it; the registration exists so the completeness check isn't false-green (`primitives.json`, `semantic.json`, `typography.json`, `spacing.json`, `themes/<theme>.json`) for each of `default`/`warm-paper`/`editorial-mono`, following the existing single-file-entry convention [Agent 2 finding]
- `scripts/little_loops/cli/__init__.py:6` — the `ll-artifact` docstring line reads "Generate self-contained human-facing HTML artifacts (policy-builder: file://-safe policy-router/rubric loop builder)"; `design-md export` emits Markdown, not HTML, so this line becomes inaccurate once the subcommand ships and needs broadening plus a `design-md export` mention (this line also drives `/ll:help`/`ll-help` output, which derives its listing from it) [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `cli/artifact.py:74,82` — `_themed_css_vars` calls `load_design_tokens(config, theme=...)` twice; unaffected by this change but establishes the existing `load_design_tokens` call convention the new export path should follow
- `cli/loop/_helpers.py:1422` — `inject_design_context` calls `load_design_tokens`; unaffected, listed for completeness of `load_design_tokens`'s caller set
- `scripts/tests/test_design_tokens.py`, `scripts/tests/test_enh1768_profile_system.py` — extensive existing `load_design_tokens` test coverage that must keep passing unmodified by this change

### Tests
- `scripts/tests/test_design_tokens.py` — over `default` / `warm-paper` / `editorial-mono`: (a) composed-mapping value round-trip for semantic colors + `space`/`radius` (AC 1), (b) role preservation — nothing lands in the importer's residual bucket (AC 2), (c) typography shape assertion (AC 3), (d) no key from `_flatten(tokens.primitives)` appears in the output (AC 4), (e) the dropped-groups note (AC 5), (f) `yaml.safe_load` scalar-typing assertion (AC 12)
- **Round-trip entry point** (otherwise ambiguous — there is no public parse function, and `load_design_tokens` only reaches a DESIGN.md via `source: design_md` + a case-exact root file through `_find_design_md`): AC 1/2/12 assert against `_load_design_md(path)` + `_flatten` called directly on the written file — cheap, no `BRConfig` construction — plus **one** end-to-end case that writes the export to a tmp project root as `DESIGN.md` and loads it through `load_design_tokens(config)` with `design_tokens.source: design_md`, proving the real path works. The existing `scripts/tests/fixtures/design_md/paws_and_paths_DESIGN.md` fixture also gives a free import→export→import prose/value round-trip for a `source == "design_md"` input (AC 7)

_Wiring pass added by `/ll:wire-issue`:_
- New test file/class for `cmd_design_md_export` and the `design-md` subparser dispatch — no existing coverage for this subcommand exists (it's new); model on `scripts/tests/test_policy_builder_emit.py`'s direct-handler-invocation pattern (`_emit_html`-style helper building an `argparse.Namespace` and calling the handler directly, never the console script) and its `TestArtifactCLIDispatch` class (mocks the handler, asserts argv routes `--profile`/`--theme`/`-o` into the parsed `Namespace`) [Agent 3 finding]
- `scripts/tests/test_package_data_manifest.py` — if profile JSON files are registered in `PACKAGE_DATA_ASSETS` per the Files to Modify entry above, this parametrized completeness test will need the new entries to pass through unmodified (no logic change, just exercises the new tuples) [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — the export subcommand and its flags
- `docs/reference/API.md` — `render_as_design_md` in the `little_loops.design_tokens` public surface, including the documented key mapping and the dropped groups

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- Every existing `render_as_*` renderer (`render_as_prompt_context:545`, `render_as_css_vars:651`, `render_as_css_vars_themed:661`) takes only `DesignTokens`, iterates `tokens.resolved` sorted, and skips `_`-prefixed metadata keys via `if name.startswith("_"): continue` (`:571`, `:603`, `:674`) — evidence for the convention `render_as_design_md` should reuse to drop `_note`/`_wcag_spot_check`.
- Degraded-load/dropped-data warnings in this codebase go through a raw `sys.stderr.write(f"[little-loops] Warning: ...\n")` call, never `logger.warning` (`design_tokens.py:192-195,439-442,445-449,463-466,498-501,523-526,534-537`) — evidence for how the export's dropped-groups note should be emitted.
- `cli/artifact.py`'s one existing subcommand (`cmd_policy_builder`, `:88-140`) wraps its body in `try/except Exception as exc: logger.error(str(exc)); return 1` and calls `logger.success(...)` on the success path (`:136,139`) — evidence for the new `cmd_design_md_export` handler's error/success shape.
- `-o`/`--output` is used two disagreeing ways in this codebase: `policy-builder` (`cli/artifact.py:170-176`) and `session.py`'s `schemas` command (`:41-47`) treat it as an **output directory**; `session.py`'s `export` command (`:268-274, 817-837`) treats it as an **output file** with a stdout fallback when unset. `design-md export` writes a single rendered document (not a directory of files), making the `export`-command file+stdout-fallback shape the closer precedent.
- `importlib.resources.files("little_loops")` is the established wheel-safe accessor for a *single packaged file* (`init/core.py:35`, `mcp_server/server.py:67`, `session_store/schema.py:1449`, `test_enh1768_profile_system.py:451-462`), but no existing code resolves a packaged *directory* this way — `cli/verify_design_tokens.py:_find_profiles_dir` (`:181-194`) resolves the `profiles/` directory instead via a multi-candidate `Path` search across source-repo/editable-install/user-project layouts. `--profile <name>`'s packaged-built-in fallback combines "resolve via importlib.resources" with "it's a directory of several files," which is new territory rather than a straight copy of either existing pattern.
- `PACKAGE_DATA_ASSETS` (`package_data.py:28-49`), the manifest gating package-data completeness checks, does not currently list `templates/design-tokens/profiles/**` — its non-membership reflects that nothing reads profile JSON via `importlib.resources` yet, not an intentional exclusion.

_Added by review pass — 2026-08-21:_

- **The `--profile` packaged-built-in fallback is manifest hygiene, not a shipping fix.** `scripts/pyproject.toml:192` is `packages = ["little_loops"]`, and hatchling ships non-Python files inside the package directory by default, so `templates/design-tokens/profiles/**` is *already* in the wheel. Registering the tuples in `PACKAGE_DATA_ASSETS` is still correct (that manifest is the completeness gate, and omitting an entry gives a false-green result per its own header comment) but `--profile` will function without it.
- `_classify_design_md_color_role` (`:63-73`) recognizes only Material-style names; little-loops' own role names (`text`, `border`, `action`) are **not** among them, so a naive `role-name` export key falls into the residual bucket on re-import. See "The key mapping must be classifier-aware" above for the full trace.
- `_normalize_design_md_leaf` (`:228-230`) returns `dict` values untouched, so the `colors:` branch of `_map_design_md_namespaces` mangles nested input into `color.<role>.<role>.<name>`. The importer requires a one-level-flat `colors:` map.
- `_resolve_token_root` (`:168-200`) reads `dt_cfg.active` directly (`:184`) and exposes no profile-name override, so `--profile` cannot reuse it unchanged.
- **`action.destructive` is the counterexample that kills a per-leaf mapping table.** Verified against the live classifier: `destructive` → `None` (residual), `accent-destructive` → `action`, `error` → `action`. All three built-ins carry `color.action.destructive`, so an export table covering only `primary`/`accent-*` fails AC 2 everywhere. The generic per-role rule (above) was verified leaf-by-leaf against `_classify_design_md_color_role`.
- **The house frontmatter parser cannot detect quoting bugs.** `parse_frontmatter` → `yaml.load(..., Loader=yaml.BaseLoader)` (`frontmatter.py:153,206`) with `coerce_types=False` by default, so every scalar and key re-imports as `str` regardless of how the exporter wrote it. Type-correctness for external consumers needs a separate `yaml.safe_load` assertion (AC 12).
- **No public parse entry point for the import side.** `load_design_tokens` reaches a DESIGN.md only via `source: design_md` plus a case-exact root file (`_find_design_md`); `_load_design_md(path)` is the private function tests should call directly for the mapping assertions.
- **`ll-artifact` has exactly one subparser level today** (`add_subparsers(dest="command", required=True)`, dispatch `if args.command == "policy-builder"`, `cli/artifact.py:164-186`), so `design-md export` is the first two-level surface in this CLI.
- All three built-in profiles carry `font.family.body` and `font.family.heading`, so the pinned typography role table resolves on every one; the size scales differ (`editorial-mono` alone has `5xl`), which is why the table needs a documented skip-and-report rule rather than an index-based pairing.
- The vendored spec fixture's `typography:` block is role-organized composites (`display`, `headline-lg`, `body-md`, `label-sm` → `fontFamily`/`fontSize`/`fontWeight`/`lineHeight`/`letterSpacing`), while every built-in profile's `typography.json` is axis-organized (`font.family/weight/size/line-height/letter-spacing`). The two shapes are not related by a key rename.

## Implementation Steps

1. Implement the classifier-aware color key mapping as the generic per-role rule tabulated above, writing the round-trip test *first* over **every** semantic leaf of all three built-ins — it is the cheapest way to catch a name the classifier rejects (`action.destructive` is the known one).
2. Implement `render_as_design_md(tokens)`: `name:` + flat `colors:` under that mapping, role-organized `typography:` per the pinned role table, `spacing:`/`rounded:`, primitives excluded via `_flatten(tokens.primitives)`, `_`-prefixed metadata skipped, body from `tokens.guidance`, all scalars and keys emitted quoted.
3. Add the `ll-artifact design-md export [--profile] [--theme] [-o]` subcommand — a nested `design-md` → `export` subparser pair plus `(command, subcommand)` dispatch, built-in profile resolution via `importlib.resources`, and the `_resolve_token_root` profile-name override.
4. Emit the stderr note: exported theme, dropped theme(s), dropped token groups (`shadow.*`, `border.width.*`), the typography axes/roles lost to the role synthesis, and `components:` for a `design_md` source. Metadata keys are not listed.
5. Complete the test set over all three built-in profiles (round-trip, role preservation, typography shape, no-primitives).
6. Docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Register the packaged profile JSON files read via `importlib.resources` in `scripts/little_loops/package_data.py`'s `PACKAGE_DATA_ASSETS` — one tuple per file, for all three built-ins
- Update `scripts/little_loops/cli/__init__.py:6`'s `ll-artifact` docstring line to drop the "HTML artifacts" framing and mention `design-md export`
- Add a new CLI-dispatch test for `cmd_design_md_export` / the `design-md` subparser, modeled on `scripts/tests/test_policy_builder_emit.py`

## Impact

- **Scope**: `design_tokens.py` (one new renderer), `cli/artifact.py` (one nested subcommand pair), tests, docs. Estimated ~110 LOC plus tests.
- **Compatibility**: purely additive — a new subcommand and a new public function. Nothing existing changes behavior.
- **Risk**: low-to-moderate. The lossiness is the design, not a defect; the risk is under-reporting it (AC 5 and 6) and the non-obvious asymmetry between export and import (AC 1 and 2), which is where the implementation is most likely to go wrong.

## Scope Boundaries

**In scope**
- `render_as_design_md`, the `ll-artifact design-md export` subcommand, and the documented lossy key mapping + dropped-groups note.

**Out of scope**
- Reading DESIGN.md. That is ENH-3264; this issue only writes.
- Multi-theme export. The spec has no theme mechanism; do not invent a non-spec `themes:` key.
- Materializing profile JSON on disk from a DESIGN.md, in either direction.
- Preserving the spec's `components:` block. `DesignTokens` never carries it (the importer drops it at `design_tokens.py:280-281`), so there is nothing to emit. Reporting the loss *is* in scope (AC 6); round-tripping it is a change to the import side, i.e. a separate issue.
- Emitting `letterSpacing` on synthesized typography roles. The profiles express letter-spacing as a free-standing axis with no role association; guessing the pairing is worse than dropping and reporting it.
- Whether a little-loops-*generated* DESIGN.md re-imports back into semantic roles rather than a flat map — see Open Questions.

## Acceptance Criteria

1. **Semantic colors and `space`/`radius` round-trip by value under the composed mapping.** For each of `default`, `warm-paper`, `editorial-mono`: exporting then re-importing yields the same concrete value for every semantic color token and every `space.*`/`radius.*` token. The test composes the exporter's forward mapping with the importer's own re-derivation (`_classify_design_md_color_role` → `color.<role>.<name>`) to compute the expected re-imported key — **keys are not identical across the round trip, only roles and values are** (`color.border.subtle` → `outline-subtle` → `color.border.outline-subtle`). Asserting forward-mapped keys alone will fail; see "The key mapping must be classifier-aware".
2. **Every exported semantic color re-imports into its original role.** For each built-in profile, a re-import of the exported document classifies each color into the same one of `surface`/`text`/`border`/`action` it started in — i.e. nothing lands in the residual bucket. This is the AC that forces classifier-recognized export names, and it is asserted over **every** semantic leaf, not a sampled subset: `action.destructive` is the leaf a naive `role-name` mapping drops into the residual bucket on all three built-ins.
3. **Typography is shape-asserted, not value-round-tripped.** The exported `typography:` block is role-organized per the spec and matches the pinned role table (`display`, `headline-lg`, `headline-md`, `title-lg`, `body-lg`, `body-md`, `label-md`, `label-sm`); every emitted role carries at least `fontFamily` and `fontSize`. The axes and roles that do not survive the axis→role synthesis are named in the stderr note.
4. **Raw primitives do not appear in the export.** No key present in `_flatten(tokens.primitives)` is emitted — asserted on `warm-paper`, whose `color.paper.*` / `color.terracotta.*` primitives are the case the existing `_PRIMITIVE_COLOR_PREFIXES` allowlist misses.
5. Groups with no home in the spec frontmatter (`shadow.*`, `border.width.*`) are excluded from the round-trip comparison and asserted to appear in the exporter's dropped-groups note. `_`-prefixed metadata (`_note`, `_wcag_spot_check`) is excluded from the export **and** asserted *absent* from the note — it is dropped silently, per the existing renderer convention.
6. Exporting a themed profile writes a stderr note naming the exported theme, the dropped theme(s), **and** every dropped token group. For a `source == "design_md"` input, the note additionally names the `components:` block dropped at import — the spec's richest block is lost on the DESIGN.md → DESIGN.md path and must not be lost silently.
7. The export emits a frontmatter `name:` key carrying the profile name, and a prose body equal to `tokens.guidance` when the source is a DESIGN.md (a `source == "design_md"` input therefore round-trips its prose).
8. `--profile <name>` exports a packaged built-in profile without requiring it to be materialized in the project, resolved wheel-safely via `importlib.resources`.
9. `--theme <name>` selects a non-default theme for the flattened output.
10. No new console script — `scripts/pyproject.toml` is unchanged. (`cli/__init__.py:6`'s docstring line *is* updated, per the wiring phase.)
11. `python -m pytest scripts/tests/` exits 0.
12. **The export is correctly typed for a non-little-loops consumer.** Parsing the exported frontmatter with `yaml.safe_load` (not the house `BaseLoader` parser, which cannot see this) yields string values and string keys throughout — `radius.none`, `spacing`'s numeric keys, and `fontWeight` do not come back as ints.

## API/Interface

- `little_loops.design_tokens.render_as_design_md(tokens: DesignTokens) -> str` — new, public. Single-`DesignTokens`: the spec has no theme mechanism, so there is no second parameter to fill.
- CLI: `ll-artifact design-md export [--profile <name>] [--theme <name>] [-o <path>]`

## Open Questions

- ~~Should the exporter emit a *generated* prose body (from profile `_note` fields) or leave the body empty for a human to fill?~~ **Closed by review pass:** ENH-3267 landed `DesignTokens.guidance`, so the body is `tokens.guidance` when present and a minimal skeleton otherwise. See Decision Rules.
- ~~Whether the export key mapping should be reversible on import, i.e. whether a little-loops-generated DESIGN.md should re-import back into semantic roles rather than a flat map.~~ **Closed by review pass — it is blocking, and resolved:** it must re-import into semantic roles, which is why export names have to be classifier-recognized. Promoted to AC 2.

## Notes

Split out of ENH-3264. ENH-3264 (the import side AC 1's round-trip assertion needs) is done as of 2026-08-21.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-21T15:51:49 - `4b6e7fc8-bea5-4102-8c7c-774c0b28d5e6.jsonl`
- `/ll:confidence-check` - 2026-08-21T15:28:19 - `2eadf414-6592-4c46-8e33-1e7a8dad58d9.jsonl`
- `/ll:wire-issue` - 2026-08-21T15:12:15 - `67bfc067-2789-446b-ab7b-cdcf09aecfb3.jsonl`
- `/ll:refine-issue` - 2026-08-21T15:01:21 - `398581da-0218-4423-81c6-1d0e088cc1c1.jsonl`
