---
discovered_date: 2026-01-22
discovered_by: capture_issue
---

# ENH-107: Add sprints configuration to config schema

## Summary

The sprint feature stores files in `.sprints/` but this location is hardcoded. The `config-schema.json` has no `sprints` section to allow users to configure the sprints directory or default options.

## Context

Identified during audit of the `/ll:ll_create_sprint` slash command. Other features like `issues`, `automation`, and `parallel` have configurable settings in the schema, but sprints does not.

## Current Behavior

- `SprintManager` defaults to `.sprints/` (hardcoded in `sprint.py:162`)
- Command documentation says `.sprints/` (hardcoded in `ll_create_sprint.md:24`)
- No configuration options in `config-schema.json`

## Expected Behavior

Add a `sprints` section to `config-schema.json`:

```json
"sprints": {
  "type": "object",
  "description": "Sprint management settings",
  "properties": {
    "sprints_dir": {
      "type": "string",
      "description": "Directory for sprint definitions",
      "default": ".sprints"
    },
    "default_mode": {
      "type": "string",
      "enum": ["auto", "parallel"],
      "description": "Default execution mode for sprints",
      "default": "auto"
    },
    "default_timeout": {
      "type": "integer",
      "description": "Default timeout per issue in seconds",
      "default": 3600
    },
    "default_max_workers": {
      "type": "integer",
      "description": "Default workers for parallel mode",
      "default": 4
    }
  }
}
```

## Proposed Solution

1. Add `sprints` section to `config-schema.json`
2. Update `SprintManager.__init__` to read from config
3. Update `ll_create_sprint.md` to reference config values

## Impact

- **Priority**: P3 - Feature works but not configurable
- **Effort**: Low - Schema addition and minor code updates
- **Risk**: Low - Backward compatible with defaults

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Configuration system design |

## Labels

`enhancement`, `configuration`, `schema`

---

**Priority**: P3 | **Created**: 2026-01-22
