---
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 64
---

# ENH-576: Align bug/enh section JSON files with format-issue templates.md v2.0 definitions

## Summary

Six gaps exist between the per-type section definition JSON files (`templates/bug-sections.json`, `templates/enh-sections.json`) and the authoritative v2.0 section definitions in `skills/format-issue/templates.md`, and between skills and `ll-config.json`. These sources of truth are out of sync, causing format-issue and related skills to operate on incomplete or undocumented section data, and giving users no way to configure template behavior per project.

## Current Behavior

1. `enh-sections.json` is missing `API/Interface` from `type_sections` — `templates.md` explicitly lists it as a FEAT/ENH section, but it only exists in `feat-sections.json`.
2. `bug-sections.json` is missing deprecated entries for `Proposed Fix` and `Reproduction Steps` — the v1→v2 rename table in `templates.md` documents both renames, but neither old name appears as a deprecated entry in the JSON, so format-issue has no machine-readable record to drive auto-rename for BUGs.
3. `bug-sections.json` has `Actual Behavior` as a required type_section, but `templates.md` doesn't mention it — it also semantically overlaps with `Current Behavior` (a common section present in all three JSON files).
4. `bug-sections.json` has `Location` as a type_section (with `creation_contexts: ["scan"]`), but `templates.md` never declares it as a v2.0 section — it's only implicitly referenced in the Integration Map inference rules.
5. There is no `issues.capture_template` setting in `ll-config.json` / `config-schema.json` — skills (`capture-issue`, `format-issue`, `ready-issue`) hardcode the `full` variant and do not respect `issues.templates_dir`; only `ll-sync pull` uses config-driven template selection via `sync.github.pull_template`. Users cannot globally control which creation variant or custom template directory skills use when assembling new issues.

## Expected Behavior

- `enh-sections.json` includes `API/Interface` in `type_sections`, matching `feat-sections.json`'s definition.
- `bug-sections.json` includes deprecated entries for `Proposed Fix` and `Reproduction Steps` so format-issue can auto-rename them.
- `Actual Behavior` is either removed from `bug-sections.json` (resolving the overlap with `Current Behavior`) or documented in `templates.md` with a clear distinction.
- `Location` is documented in `templates.md` as a BUG scan-only section, or annotated in the JSON as intentionally undocumented in the skill guide.
- Both sources of truth are in sync so any skill reading the JSON files has consistent section knowledge.
- `ll-config.json` supports an `issues.capture_template` key (enum: `full`/`minimal`/`legacy`, default: `"full"`) so users can globally configure which creation variant skills use when assembling new issues.
- Skills (`capture-issue`, `format-issue`, `ready-issue`) read `issues.templates_dir` and `issues.capture_template` from `ll-config.json`, giving users full control over template source and structure without code changes.

## Motivation

The JSON files are the machine-readable source of truth consumed by format-issue, capture-issue, ready-issue, and ll-sync pull. The `templates.md` is the human-readable definition document. When they diverge:

- format-issue misses valid rename opportunities for BUG issues (`Proposed Fix`, `Reproduction Steps`)
- ENH issues never get `API/Interface` suggested or validated by format-issue or ready-issue
- Undocumented sections (`Actual Behavior`, `Location`) create ambiguity about what v2.0 actually defines
- Users working with different project styles (e.g., lightweight issues, or custom section sets) have no way to change the default template structure — every skill defaults to `full` regardless of project preferences

## Proposed Solution

1. **Add `API/Interface` to `enh-sections.json` `type_sections`** — copy the definition from `feat-sections.json` (same level, description, quality_guidance).
2. **Add deprecated entries to `bug-sections.json`** for:
   - `Reproduction Steps` (deprecated, renamed to `Steps to Reproduce`)
   - `Proposed Fix` (deprecated, renamed to `Proposed Solution`)
3. **Resolve `Actual Behavior` vs `Current Behavior` overlap** — either:
   - Remove `Actual Behavior` from `bug-sections.json` (it duplicates `Current Behavior`), OR
   - Document it in `templates.md` as a distinct BUG-specific section with a clear semantic difference
4. **Document `Location`** in `templates.md` as a BUG-only scan-time section, or annotate it in `bug-sections.json` as intentionally excluded from the skill guide.
5. **Make Issue Template configurable via `ll-config.json`**:
   - Add `issues.capture_template` (enum: `full`/`minimal`/`legacy`, default: `"full"`) to `config-schema.json` and `IssuesConfig` in `config.py`
   - Update skills (`capture-issue`, `format-issue`, `ready-issue`) to read `issues.capture_template` and `issues.templates_dir` from ll-config and pass them through to `load_issue_sections` / `assemble_issue_markdown` — matching what `sync.py` already does

## API/Interface

N/A - No public API changes

## Integration Map

### Files to Modify
- `templates/enh-sections.json` — add `API/Interface` to `type_sections`
- `templates/bug-sections.json` — add `Proposed Fix` and `Reproduction Steps` deprecated entries; resolve `Actual Behavior`
- `skills/format-issue/templates.md` — document `Location` and `Actual Behavior`, or note their removal/scan-only scope
- `config-schema.json` — add `issues.capture_template` (enum: full/minimal/legacy, default: "full")
- `scripts/little_loops/config.py` — add `capture_template: str = "full"` to `IssuesConfig` and `from_dict()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_template.py` — reads section JSON files; no logic change needed (already accepts `templates_dir` param)
- `scripts/little_loops/sync.py` — already reads `issues.templates_dir` and `sync.github.pull_template`; reference pattern for skills to follow
- `scripts/little_loops/config.py:762-773` — `to_dict()` on `BRConfig` serializes the `issues` section; add `capture_template` here alongside `templates_dir` (not mentioned in original issue)
- `skills/capture-issue/SKILL.md:28-31,219-226` — already references `config.issues.capture_template`; verify conditional logic covers all branches
- `commands/ready-issue.md` — update to read `issues.capture_template` and `issues.templates_dir` from ll-config
- `skills/format-issue/SKILL.md` — update to read `issues.capture_template` and `issues.templates_dir` from ll-config
- `skills/configure/show-output.md:27-32` — already lists `capture_template`; no change needed once config.py is updated
- `skills/configure/areas.md:134-137` — already lists `capture_template`; no change needed

### Similar Patterns
- `sync.py:652-655` — existing pattern: reads `config.issues.templates_dir`, passes to `load_issue_sections()`
- `sync.py:679` — reads `sync_config.github.pull_template` to select creation variant

### Tests
- `scripts/tests/test_issue_template.py` — verify no regressions if `Actual Behavior` is removed
- `scripts/tests/test_config.py` — add test for `capture_template` field in `IssuesConfig`

### Documentation
- `skills/format-issue/templates.md` — primary doc to update
- `.claude/ll-config.json` example: add `"capture_template": "minimal"` under `issues` as a comment/example

### Configuration
- `config-schema.json` — `issues.capture_template` field addition

## Implementation Steps

1. Copy `API/Interface` entry from `feat-sections.json:164-176` into `enh-sections.json` `type_sections` (append after `Backwards Compatibility` at ~line 168)
2. Add deprecated entries for `Proposed Fix` (→ `Proposed Solution`) and `Reproduction Steps` (→ `Steps to Reproduce`) to `bug-sections.json` `type_sections` — use the same two-key pattern as `bug-sections.json:169-186`: `"deprecated": true` + `"deprecation_reason"`
3. Remove `Actual Behavior` from `bug-sections.json:144-150` (confirmed: overlaps with `Current Behavior` in common_sections)
4. Annotate `Location` at `bug-sections.json:187-196` as scan-only — add `"skill_guide_excluded": true` (or equivalent) with a `"skill_guide_note"` explaining it is generated by scan tools and intentionally absent from the skill guide
5. Add `capture_template` to `config-schema.json:63-121` under `issues.properties` — `"type": "string"`, `"enum": ["full", "minimal", "legacy"]`, `"default": "full"` — mirroring `sync.github.pull_template` at `config-schema.json:719-724`; note `"additionalProperties": false` at line 121 means the schema itself must list this new property
6. Add `capture_template: str = "full"` field to `IssuesConfig` in `config.py:97-133`; wire through `from_dict()` via `data.get("capture_template", "full")` (follow `GitHubSyncConfig.pull_template` at `config.py:350-374`); also add `capture_template` to `to_dict()` at `config.py:762-773`
7. `capture-issue/SKILL.md` already references `config.issues.capture_template` at lines 28-31 and 219-226 — verify the conditional logic is complete; update `format-issue/SKILL.md` and `commands/ready-issue.md` to reference `issues.capture_template` and `issues.templates_dir` (follow `sync.py:651-655` and `sync.py:679` as reference)
8. Add test for `capture_template` to `TestIssuesConfig` in `test_config.py:99-146` — follow the `deferred_dir` single-field pattern at line 136-140; also update `test_from_dict_with_all_fields` and `test_from_dict_with_defaults` to cover the new field
9. Run `python -m pytest scripts/tests/test_issue_template.py scripts/tests/test_config.py -v`

## Impact

- **Priority**: P3 - Moderate consistency issue; skills work but miss some rename/validation opportunities and offer no template configurability
- **Effort**: Small/Medium - JSON edits and markdown doc updates for gaps 1-4; small Python/schema changes and skill instruction updates for gap 5
- **Risk**: Low - Additive changes; deprecated entries and new config fields are backward compatible; skills default to current behavior (`full` variant) if config is absent
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/format-issue/templates.md` | Authoritative v2.0 section definitions (human-readable) |
| `templates/bug-sections.json` | BUG type section definitions (machine-readable) |
| `templates/enh-sections.json` | ENH type section definitions (machine-readable) |
| `templates/feat-sections.json` | FEAT type section definitions (reference for API/Interface) |
| `config-schema.json` | Config schema — add `issues.capture_template` |
| `scripts/little_loops/config.py` | `IssuesConfig` dataclass — add `capture_template` field |
| `scripts/little_loops/sync.py:652-655` | Reference pattern for reading `issues.templates_dir` from config |

## Success Metrics

- All sections listed in `templates.md` "New Sections in v2.0" exist in the corresponding JSON files
- All renames in `templates.md` v1→v2 rename table have corresponding deprecated entries in JSON
- No section exists in JSON without documentation in `templates.md` (or an explicit scan-only annotation)
- `config-schema.json` defines `issues.capture_template` with enum validation (full/minimal/legacy)
- `IssuesConfig` exposes `capture_template` and `test_config.py` covers the new field
- `capture-issue`, `format-issue`, and `ready-issue` skill instructions reference ll-config for variant and templates_dir

## Scope Boundaries

- **In scope**: JSON and `templates.md` alignment (gaps 1-4); `issues.capture_template` config field and skill instruction updates (gap 5); no logic changes to `issue_template.py`
- **Out of scope**: Changing section definitions (e.g., making `API/Interface` required for ENH); batch-reformatting existing issue files; per-type variant overrides (e.g., separate BUG vs ENH variant settings)

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Confirmed Gap Locations

| Gap | File | Lines | Finding |
|-----|------|-------|---------|
| `API/Interface` missing from ENH | `templates/enh-sections.json` | 135–168 | 4 type_sections; no API/Interface entry |
| `API/Interface` source to copy | `templates/feat-sections.json` | 164–176 | Full entry with `level`, `description`, `ai_usage`, `human_value`, `question`, `quality_guidance`, `creation_template` |
| `Proposed Fix` deprecated entry missing | `templates/bug-sections.json` | type_sections | No `Proposed Fix` entry anywhere in file |
| `Reproduction Steps` deprecated entry missing | `templates/bug-sections.json` | type_sections | No `Reproduction Steps` entry anywhere in file |
| `Actual Behavior` to remove | `templates/bug-sections.json` | 144–150 | `required` type_section, no `creation_template`, absent from templates.md |
| `Location` to annotate | `templates/bug-sections.json` | 187–196 | `conditional` with `creation_contexts: ["scan"]` only |
| `capture_template` absent from config.py | `scripts/little_loops/config.py` | 97–133 | `IssuesConfig` has 6 fields; `capture_template` not present |
| `capture_template` absent from schema | `config-schema.json` | 63–121 | 6 properties; `additionalProperties: false` at line 121 |

### Deprecated Entry Pattern (confirmed)

Existing deprecated entries in `bug-sections.json:169-186` use exactly:
```json
"<SectionName>": {
  "level": "...",
  "description": "...",
  "deprecated": true,
  "deprecation_reason": "..."
}
```

### Config Field Pattern (confirmed)

`GitHubSyncConfig` at `config.py:350-374` is the closest analog for an enum-defaulted string field:
```python
pull_template: str = "minimal"
# from_dict: data.get("pull_template", "minimal")
```

Schema analog at `config-schema.json:719-724`:
```json
"pull_template": {
  "type": "string",
  "enum": ["full", "minimal", "legacy"],
  "description": "Creation variant for issues pulled from GitHub",
  "default": "minimal"
}
```

### Key Discoveries

- **`capture_template` already in skills**: `capture-issue/SKILL.md:28-31,219-226` and `configure/show-output.md:27-32` and `configure/areas.md:134-137` all reference `config.issues.capture_template` — using this name avoids skill rewrites
- **`config-schema.json:121` has `additionalProperties: false`**: the new `capture_template` property must be added inside the `issues.properties` block or schema validation will reject the key
- **`config.py to_dict()` at lines 762-773** also serializes `issues` section and needs `capture_template` (was missing from original issue's Integration Map)
- **`load_issue_sections` at `issue_template.py:15-37`** already accepts `templates_dir: Path | None = None` — no changes needed to this function

## Resolution

Implemented 2026-03-04 via `/ll:manage-issue enhancements improve ENH-576`.

### Changes Made

1. **`templates/enh-sections.json`** — Added `API/Interface` to `type_sections`, copied from `feat-sections.json` (matching level, description, quality_guidance, creation_template).
2. **`templates/bug-sections.json`** — Removed `Actual Behavior` type_section (overlapped with `Current Behavior` in common_sections); annotated `Location` with `skill_guide_excluded: true` and `skill_guide_note`; added deprecated entries for `Reproduction Steps` (→ `Steps to Reproduce`) and `Proposed Fix` (→ `Proposed Solution`).
3. **`config-schema.json`** — Added `issues.capture_template` (enum: full/minimal/legacy, default: "full") to the `issues.properties` block (inside `additionalProperties: false`).
4. **`scripts/little_loops/config.py`** — Added `capture_template: str = "full"` to `IssuesConfig` dataclass; wired through `from_dict()` and `to_dict()`.
5. **`skills/format-issue/SKILL.md`** — Added `issues.templates_dir` and `issues.capture_template` to Configuration section.
6. **`commands/ready-issue.md`** — Added `issues.templates_dir` and `issues.capture_template` to Configuration section.
7. **`scripts/tests/test_config.py`** — Added `test_from_dict_with_capture_template` test; updated `test_from_dict_with_all_fields` and `test_from_dict_with_defaults` to cover the new field.

All 86 tests pass.

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71d22af5-24cb-487d-908f-cec125f5dea8.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c434fb1a-b818-4976-8960-216295369861.jsonl`
- `/ll:confidence-check` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6630aaf7-a055-4d37-8067-e37ae8a6463d.jsonl`
- `/ll:refine-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49000194-a591-48d4-83af-ce16b54ea23a.jsonl`
- `/ll:ready-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e3d410b6-368d-4444-9143-c758acc53fee.jsonl`
- `/ll:manage-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

## Labels

`enhancement`, `templates`, `format-issue`, `consistency`, `config`

## Status

**Completed** | Created: 2026-03-04 | Resolved: 2026-03-04 | Priority: P3
