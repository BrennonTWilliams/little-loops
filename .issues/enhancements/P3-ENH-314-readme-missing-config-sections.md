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

## Location

- **File**: `README.md`
- **Lines**: 119-186 (Full Configuration Example), 189-283 (Configuration Sections)

## Current State

The Full Configuration Example (line 119) includes: `project`, `issues`, `automation`, `parallel`, `commands`, `scan`, `context_monitor`.

Missing from both the example and section headers:
- `sync` - Only mentioned via `ll-sync` CLI tool documentation
- `sprints` - Not documented anywhere in README
- `documents` - Not documented anywhere in README

## Expected Content

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

Add Configuration Sections with tables for each.

## Impact

- **Severity**: Low (features work without docs, but discoverability suffers)
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P3
