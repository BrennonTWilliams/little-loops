---
discovered_date: 2026-01-22
discovered_by: capture_issue
---

# ENH-107: Add sprints configuration to config schema

## Summary

The sprint feature stores files in `.sprints/` but this location is hardcoded. The `config-schema.json` has no `sprints` section to allow users to configure the sprints directory or default options.

## Context

Identified during audit of the `/ll:create-sprint` slash command. Other features like `issues`, `automation`, and `parallel` have configurable settings in the schema, but sprints does not.

## Current Behavior

- `SprintManager` defaults to `.sprints/` (hardcoded in `scripts/little_loops/sprint.py:162`)
- Command documentation says `.sprints/` (hardcoded in `.claude/commands/create_sprint.md:24`)
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
3. Update `create_sprint.md` to reference config values

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

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `config-schema.json`: Added `sprints` configuration section with `sprints_dir`, `default_mode`, `default_timeout`, `default_max_workers` properties
- `scripts/little_loops/config.py`: Added `SprintsConfig` dataclass with `from_dict()` classmethod, integrated into `BRConfig` class with property accessor and `to_dict()` serialization
- `scripts/little_loops/sprint.py`: Updated `SprintManager` to read `sprints_dir` from config, added `get_default_options()` helper method
- `scripts/tests/test_config.py`: Added `TestSprintsConfig` test class
- `scripts/tests/conftest.py`: Added `sprints` section to `sample_config` fixture
- `.claude/commands/create_sprint.md`: Updated documentation to reference configurable settings

### Verification Results
- Tests: PASS (47 config tests, 25 sprint tests)
- Lint: PASS
- Types: PASS
