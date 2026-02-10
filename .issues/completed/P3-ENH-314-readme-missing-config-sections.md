---
discovered_commit: 56c0d40
discovered_branch: main
discovered_date: 2026-02-10T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# ENH-314: README missing `sync`, `sprints`, and `documents` config sections

## Summary

Documentation issue found by `/ll:audit_docs`. The README's "Full Configuration Example" and "Configuration Sections" are missing documentation for three config sections that exist in the schema and are actively used:

1. **`sync`** - GitHub Issues sync configuration (used by `ll-sync` and `/ll:sync_issues`)
2. **`sprints`** - Sprint management configuration (used by `ll-sprint` and `/ll:create_sprint`)
3. **`documents`** - Document tracking configuration (used by `/ll:align_issues`)

## Current Pain Point

Users cannot discover the `sync`, `sprints`, or `documents` configuration options from the README. These sections exist in `config-schema.json` and are actively used by CLI tools and commands, but the README's configuration documentation omits them entirely, reducing discoverability and forcing users to read the schema directly.

## Location

- **File**: `README.md`
- **Lines**: 119-186 (Full Configuration Example), 189-285 (Configuration Sections)
- **Anchor**: `### Full Configuration Example` and `### Configuration Sections`

## Current Behavior

The Full Configuration Example (line 119) includes: `project`, `issues`, `automation`, `parallel`, `commands`, `scan`, `context_monitor`.

Missing from both the example and section headers:
- `sync` - Only mentioned via `ll-sync` CLI tool documentation
- `sprints` - Not documented anywhere in README
- `documents` - Not documented anywhere in README

## Expected Behavior

The Full Configuration Example should include `sync`, `sprints`, and `documents` sections with their default values. The Configuration Sections area should include description tables for each, matching the format of existing sections.

## Proposed Solution

Add to Full Configuration Example:

```json
"sync": {
  "enabled": false,
  "github": {
    "label_mapping": {
      "BUG": "bug",
      "FEAT": "enhancement",
      "ENH": "enhancement"
    },
    "priority_labels": true,
    "sync_completed": false
  }
},

"sprints": {
  "sprints_dir": ".sprints",
  "default_mode": "auto",
  "default_timeout": 3600,
  "default_max_workers": 4
},

"documents": {
  "enabled": false,
  "categories": {}
}
```

Add Configuration Sections with tables for each, following the existing `| Key | Default | Description |` format.

## Scope Boundaries

- Only `sync`, `sprints`, and `documents` sections are in scope
- Other undocumented sections (e.g., `workflow`, `prompt_optimization`, `continuation`) are out of scope for this issue
- No changes to the config schema itself — documentation only

## Impact

- **Severity**: Low (features work without docs, but discoverability suffers)
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-02-10 | Completed: 2026-02-10 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `README.md`: Added `sync`, `sprints`, and `documents` sections to Full Configuration Example JSON block
- `README.md`: Added three new Configuration Section tables with descriptions, defaults, and usage examples

### Verification Results
- Tests: PASS (2660 passed)
- Lint: PASS (pre-existing issues only, none introduced)
- Types: N/A (documentation-only change)
