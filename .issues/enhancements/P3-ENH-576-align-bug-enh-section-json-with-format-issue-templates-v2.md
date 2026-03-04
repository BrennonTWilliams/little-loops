---
discovered_date: 2026-03-04
discovered_by: capture-issue
---

# ENH-576: Align bug/enh section JSON files with format-issue templates.md v2.0 definitions

## Summary

Five gaps exist between the per-type section definition JSON files (`templates/bug-sections.json`, `templates/enh-sections.json`) and the authoritative v2.0 section definitions in `skills/format-issue/templates.md`. These two sources of truth are out of sync, causing format-issue and related skills to operate on incomplete or undocumented section data.

## Current Behavior

1. `enh-sections.json` is missing `API/Interface` from `type_sections` — `templates.md` explicitly lists it as a FEAT/ENH section, but it only exists in `feat-sections.json`.
2. `bug-sections.json` is missing deprecated entries for `Proposed Fix` and `Reproduction Steps` — the v1→v2 rename table in `templates.md` documents both renames, but neither old name appears as a deprecated entry in the JSON, so format-issue has no machine-readable record to drive auto-rename for BUGs.
3. `bug-sections.json` has `Actual Behavior` as a required type_section, but `templates.md` doesn't mention it — it also semantically overlaps with `Current Behavior` (a common section present in all three JSON files).
4. `bug-sections.json` has `Location` as a type_section (with `creation_contexts: ["scan"]`), but `templates.md` never declares it as a v2.0 section — it's only implicitly referenced in the Integration Map inference rules.

## Expected Behavior

- `enh-sections.json` includes `API/Interface` in `type_sections`, matching `feat-sections.json`'s definition.
- `bug-sections.json` includes deprecated entries for `Proposed Fix` and `Reproduction Steps` so format-issue can auto-rename them.
- `Actual Behavior` is either removed from `bug-sections.json` (resolving the overlap with `Current Behavior`) or documented in `templates.md` with a clear distinction.
- `Location` is documented in `templates.md` as a BUG scan-only section, or annotated in the JSON as intentionally undocumented in the skill guide.
- Both sources of truth are in sync so any skill reading the JSON files has consistent section knowledge.

## Motivation

The JSON files are the machine-readable source of truth consumed by format-issue, capture-issue, ready-issue, and ll-sync pull. The `templates.md` is the human-readable definition document. When they diverge:

- format-issue misses valid rename opportunities for BUG issues (`Proposed Fix`, `Reproduction Steps`)
- ENH issues never get `API/Interface` suggested or validated by format-issue or ready-issue
- Undocumented sections (`Actual Behavior`, `Location`) create ambiguity about what v2.0 actually defines

## Proposed Solution

1. **Add `API/Interface` to `enh-sections.json` `type_sections`** — copy the definition from `feat-sections.json` (same level, description, quality_guidance).
2. **Add deprecated entries to `bug-sections.json`** for:
   - `Reproduction Steps` (deprecated, renamed to `Steps to Reproduce`)
   - `Proposed Fix` (deprecated, renamed to `Proposed Solution`)
3. **Resolve `Actual Behavior` vs `Current Behavior` overlap** — either:
   - Remove `Actual Behavior` from `bug-sections.json` (it duplicates `Current Behavior`), OR
   - Document it in `templates.md` as a distinct BUG-specific section with a clear semantic difference
4. **Document `Location`** in `templates.md` as a BUG-only scan-time section, or annotate it in `bug-sections.json` as intentionally excluded from the skill guide.

## API/Interface

N/A - No public API changes

## Integration Map

### Files to Modify
- `templates/enh-sections.json` — add `API/Interface` to `type_sections`
- `templates/bug-sections.json` — add `Proposed Fix` and `Reproduction Steps` deprecated entries; resolve `Actual Behavior`
- `skills/format-issue/templates.md` — document `Location` and `Actual Behavior`, or note their removal/scan-only scope

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_template.py` — reads section JSON files; no logic change needed
- `skills/capture-issue/SKILL.md` — references templates for section assembly
- `skills/ready-issue/SKILL.md` — validates against section definitions
- `skills/format-issue/SKILL.md` — uses both templates.md and JSON for formatting

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_issue_template.py` — verify no regressions if `Actual Behavior` is removed

### Documentation
- `skills/format-issue/templates.md` — primary doc to update

### Configuration
- N/A

## Implementation Steps

1. Add `API/Interface` to `enh-sections.json` `type_sections` (copy from `feat-sections.json`)
2. Add deprecated entries for `Proposed Fix` and `Reproduction Steps` to `bug-sections.json`
3. Decide on `Actual Behavior`: remove from JSON or document in `templates.md`
4. Document `Location` in `templates.md` or annotate it as scan-only in the JSON
5. Run `python -m pytest scripts/tests/test_issue_template.py` to verify no regressions

## Impact

- **Priority**: P3 - Moderate consistency issue; skills work but miss some rename/validation opportunities
- **Effort**: Small - JSON edits and markdown doc updates, no logic changes
- **Risk**: Low - Additive changes; deprecated entries are backward compatible
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/format-issue/templates.md` | Authoritative v2.0 section definitions (human-readable) |
| `templates/bug-sections.json` | BUG type section definitions (machine-readable) |
| `templates/enh-sections.json` | ENH type section definitions (machine-readable) |
| `templates/feat-sections.json` | FEAT type section definitions (reference for API/Interface) |

## Success Metrics

- All sections listed in `templates.md` "New Sections in v2.0" exist in the corresponding JSON files
- All renames in `templates.md` v1→v2 rename table have corresponding deprecated entries in JSON
- No section exists in JSON without documentation in `templates.md` (or an explicit scan-only annotation)

## Scope Boundaries

- **In scope**: JSON and `templates.md` alignment; no logic changes to `issue_template.py`
- **Out of scope**: Changing section definitions (e.g., making `API/Interface` required for ENH); batch-reformatting existing issue files

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71d22af5-24cb-487d-908f-cec125f5dea8.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c434fb1a-b818-4976-8960-216295369861.jsonl`

## Labels

`enhancement`, `templates`, `format-issue`, `consistency`

## Status

**Open** | Created: 2026-03-04 | Priority: P3
