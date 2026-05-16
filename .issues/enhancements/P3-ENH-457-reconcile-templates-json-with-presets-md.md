---
type: ENH
id: ENH-457
title: Reconcile templates/*.json with presets.md as single source of truth
priority: P3
status: open
created: 2026-02-22
---

# Reconcile templates/*.json with presets.md as single source of truth

## Summary

There are two sources of preset configuration data that have drifted apart:

1. **`templates/*.json`** (9 files): Rich JSON files with `_meta`, `project`, `scan`, `issues`, and `product` sections. These include `$schema` references, detect patterns, and tags.

2. **`presets.md`** (in `skills/init/`): Inline markdown code blocks covering only `project` and `scan` sections.

The init SKILL.md says "use the presets from presets.md" and never references the template JSON files. This means:
- Template JSON files have richer data (issues config, product config) that init ignores
- Changes to templates don't propagate to presets.md and vice versa
- The template JSON files include `_meta.detect` patterns that could replace the manual detection table in SKILL.md

## Current Behavior

There are two parallel sources of preset configuration data that have drifted apart:

1. **`templates/*.json`** (9 files): Rich JSON with `_meta`, `project`, `scan`, `issues`, `product` sections, `$schema` references, `_meta.detect` patterns, and tags.
2. **`skills/init/presets.md`**: Inline markdown code blocks with only `project` and `scan` sections — missing `issues` config, `product` config, and detect patterns.

`skills/init/SKILL.md` references `presets.md` for project type detection and presets, never using the richer `templates/*.json` files. Changes to templates don't propagate to presets.md and vice versa.

## Expected Behavior

`templates/*.json` is the single source of truth. The init skill reads the appropriate template file based on `_meta.detect` patterns for project type detection, eliminating the manual detection table in SKILL.md. `presets.md` is either removed or auto-generated from templates.

## Motivation

Two sources of truth for the same data guarantee drift. The JSON templates are already maintained with richer data (issues config, product config, detect patterns) that init ignores by using presets.md. Using templates directly would improve the quality of generated configs and eliminate the maintenance burden of keeping two files in sync.

## Proposed Solution

Make `templates/*.json` the single source of truth:

1. Update `skills/init/SKILL.md` Step 4 to reference template JSON files instead of presets.md
2. Have init read the appropriate `templates/<type>.json` file based on detection
3. Either remove `presets.md` or generate it from the templates
4. Use `_meta.detect` from templates for project type detection (replacing the manual table in SKILL.md Step 3)

## Scope Boundaries

- **In scope**: Updating SKILL.md Steps 3-4 to use template JSON files; removing or deprecating presets.md; using `_meta.detect` for project type detection
- **Out of scope**: Changes to template JSON file content, adding new project types, changing the wizard question flow

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Steps 3-4 (lines ~59-78): replace presets.md reference with templates/*.json; replace manual detection table with `_meta.detect` pattern matching
- `skills/init/presets.md` — Delete or replace with generated stub

### Dependent Files (Callers/Importers)
- `templates/*.json` (9 files) — consumed by init; no structural changes needed
- `skills/init/interactive.md` — Check for any references to presets.md

### Similar Patterns
- `_meta.detect` patterns already defined in all 9 template files

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Read all `templates/*.json` files and extract `_meta.detect` patterns
2. Replace the manual project type detection table in SKILL.md Step 3 with template-driven detection (iterate templates, check detect.indicators against discovered project files)
3. Update Step 4 to read the matched template JSON file and extract `project` and `scan` sections as presets
4. Apply `issues` and `product` sections from template JSON as additional config defaults
5. Either delete `presets.md` or add a deprecation notice pointing to `templates/*.json`
6. Verify that all 9 project types produce equivalent config output as current presets.md

## Impact

- **Priority**: P3 — Eliminates template drift; improves generated config quality for non-default project types
- **Effort**: Medium — Requires reading JSON files and restructuring detection logic in SKILL.md
- **Risk**: Low-Medium — Detection behavior could change if `_meta.detect` patterns differ from current logic; requires testing all 9 project types
- **Breaking Change**: No — output config format unchanged; only data source changes

## Labels

`enhancement`, `init`, `templates`, `single-source-of-truth`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`

## Blocked By

- BUG-449

## Blocks

- ENH-453
- ENH-458
- ENH-460

---

## Resolution

**Resolved**: 2026-02-23

### Changes Made
1. **SKILL.md Step 3**: Replaced manual 7-row detection table with template-driven detection using `_meta.detect` patterns from `templates/*.json` files. Now supports 9 project types including TypeScript (distinct from Node.js) and Java split into Maven/Gradle.
2. **SKILL.md Step 4**: Changed from referencing `presets.md` to reading the matched template JSON file directly, extracting `project`, `scan`, and `issues` sections.
3. **SKILL.md Additional Resources**: Updated reference from `presets.md` to `templates/*.json`.
4. **interactive.md**: Inlined the interactive mode alternative options (test/lint/format/build commands per language) directly into the file, with additions for TypeScript and Java Maven/Gradle variants.
5. **presets.md**: Deleted — all data migrated to template files and interactive.md.
6. **ARCHITECTURE.md**: Removed `presets.md` from directory tree listing.

### Verification
- All 2882 tests pass
- Linting passes
- No active files reference `presets.md`

---

## Status

**Resolved** | Created: 2026-02-22 | Resolved: 2026-02-23 | Priority: P3
