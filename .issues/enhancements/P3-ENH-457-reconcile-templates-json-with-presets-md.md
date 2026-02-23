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

## Proposed Change

Make `templates/*.json` the single source of truth:

1. Update `skills/init/SKILL.md` Step 4 to reference template JSON files instead of presets.md
2. Have init read the appropriate `templates/<type>.json` file based on detection
3. Either remove `presets.md` or generate it from the templates
4. Use `_meta.detect` from templates for project type detection (replacing the manual table in SKILL.md Step 3)

## Files

- `skills/init/SKILL.md` (Steps 3-4, lines ~59-78)
- `skills/init/presets.md` (entire file)
- `templates/*.json` (9 template files)
