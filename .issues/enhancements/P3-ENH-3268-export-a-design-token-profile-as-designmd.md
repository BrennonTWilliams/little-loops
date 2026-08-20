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
4. Every lossy axis — the dropped theme(s) and every dropped token group — is named in a stderr note.

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
- `semantic.json` colors nest three levels deep (`color.surface.base`) and must collapse into the spec's flat one-level `colors:` map, so exported key names differ from the originals.
- Metadata keys (`_note` in `typography.json`/`spacing.json`, `_wcag_spot_check` in `semantic.json`) are export-only noise and are dropped.

The exporter therefore emits the **spec-expressible subset** under a documented, deterministic key mapping (e.g. `color.surface.base` → `surface-base`) and writes a stderr note listing every dropped group.

### `--profile` is required, not optional polish

`load_design_tokens()` only ever reads `config.project_root / dt_cfg.path`, so it **cannot reach a packaged built-in** under `templates/design-tokens/profiles/<name>/`. Without `--profile`, round-tripping the three built-ins is only expressible by copying each template into a temp project and re-pointing config.

Semantics: unset ⇒ export the project's active profile via today's `load_design_tokens()` path; set ⇒ resolve the named profile from the project's `profiles_dir` first, falling back to the packaged templates via `importlib.resources.files("little_loops")` (the wheel-safe accessor established by `test_enh1768_profile_system.py::TestConfigSchemaProfileFields`).

### CLI placement

A subcommand of the existing `ll-artifact`, **not** a new `ll-design` console script — so `scripts/pyproject.toml` and `cli/__init__.py` are untouched. `ll-artifact` is already the two-theme `load_design_tokens()` consumer (`cli/artifact.py:59-74`), which is exactly where the lossy single-theme decision has to be made anyway.

## Integration Map

### Files to Modify
- `scripts/little_loops/design_tokens.py` — `render_as_design_md()` (new, public)
- `scripts/little_loops/cli/artifact.py` — new `design-md export` subcommand alongside the existing `policy-builder` subparser (`:155`)

### Tests
- `scripts/tests/test_design_tokens.py` — round-trip export test over `default` / `warm-paper` / `editorial-mono`, asserting both value equality on the expressible subset and the dropped-groups note

### Documentation
- `docs/reference/CLI.md` — the export subcommand and its flags
- `docs/reference/API.md` — `render_as_design_md` in the `little_loops.design_tokens` public surface, including the documented key mapping and the dropped groups

## Implementation Steps

1. Implement `render_as_design_md(tokens)` with the documented key mapping.
2. Add the `ll-artifact design-md export [--profile] [--theme] [-o]` subcommand, including built-in profile resolution via `importlib.resources`.
3. Emit the stderr note: exported theme, dropped theme(s), and every dropped token group.
4. Add the subset round-trip test over all three built-in profiles.
5. Docs.

## Impact

- **Scope**: `design_tokens.py` (one new renderer), `cli/artifact.py` (one subcommand), tests, docs. Estimated ~80 LOC plus tests.
- **Compatibility**: purely additive — a new subcommand and a new public function. Nothing existing changes behavior.
- **Risk**: low. The lossiness is the design, not a defect; the risk is under-reporting it, which AC 2 and 3 pin down.

## Scope Boundaries

**In scope**
- `render_as_design_md`, the `ll-artifact design-md export` subcommand, and the documented lossy key mapping + dropped-groups note.

**Out of scope**
- Reading DESIGN.md. That is ENH-3264; this issue only writes.
- Multi-theme export. The spec has no theme mechanism; do not invent a non-spec `themes:` key.
- Materializing profile JSON on disk from a DESIGN.md, in either direction.
- Whether a little-loops-*generated* DESIGN.md re-imports back into semantic roles rather than a flat map — see Open Questions.

## Acceptance Criteria

1. `render_as_design_md()` round-trips the **spec-expressible subset** of each of `default`, `warm-paper`, `editorial-mono`: exporting then re-importing yields the same concrete values for every token that survives the documented key mapping. The test applies the forward mapping to the original keys and compares value-by-value against the re-imported keys.
2. Groups with no home in the spec frontmatter (`shadow.*`, `border.width.*`, and the `_note` / `_wcag_spot_check` metadata keys) are excluded from the round-trip comparison and asserted to appear in the exporter's dropped-groups note.
3. Exporting a themed profile writes a stderr note naming the exported theme, the dropped theme(s), **and** every dropped token group.
4. `--profile <name>` exports a packaged built-in profile without requiring it to be materialized in the project, resolved wheel-safely via `importlib.resources`.
5. `--theme <name>` selects a non-default theme for the flattened output.
6. No new console script — `scripts/pyproject.toml` and `cli/__init__.py` are unchanged.
7. `python -m pytest scripts/tests/` exits 0.

## API/Interface

- `little_loops.design_tokens.render_as_design_md(tokens: DesignTokens) -> str` — new, public. Single-`DesignTokens`: the spec has no theme mechanism, so there is no second parameter to fill.
- CLI: `ll-artifact design-md export [--profile <name>] [--theme <name>] [-o <path>]`

## Open Questions

- Should the exporter emit a *generated* prose body (from profile `_note` fields) or leave the body empty for a human to fill?
- Whether the export key mapping (`color.surface.base` → `surface-base`) should be reversible on import, i.e. whether a little-loops-generated DESIGN.md should re-import back into semantic roles rather than a flat map. Not blocking; affects how good the AC-1 round-trip can get.

## Notes

Split out of ENH-3264. Depends on ENH-3264 for the import side that AC 1's round-trip assertion needs.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P3
