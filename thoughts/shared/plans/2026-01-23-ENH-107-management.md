# ENH-107: Add sprints configuration to config schema - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-107-add-sprints-configuration-to-config-schema.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The sprint feature currently works but has hardcoded defaults:

### Key Discoveries
- `sprint.py:162` - SprintManager defaults to `Path(".sprints")` hardcoded
- `sprint.py:25-28` - SprintOptions defaults hardcoded (mode="auto", timeout=3600, max_workers=4)
- `create_sprint.md:24` - Documentation hardcodes `.sprints/` directory
- `config.py:318-328` - _parse_config() shows pattern for adding new config sections
- `config-schema.json:119-153` - Example of config section schema (automation)

### Patterns to Follow
- Config sections defined in `config-schema.json` with type, description, properties, defaults
- Python dataclass in `config.py` with `from_dict()` classmethod
- Integration in `BRConfig._parse_config()` and property accessor
- Serialization in `BRConfig.to_dict()`
- Export in `__all__`
- Tests in `test_config.py` following `TestXxxConfig` pattern

## Desired End State

A `sprints` section in `config-schema.json` that allows users to configure:
- Sprint definitions directory (default: `.sprints`)
- Default execution mode (default: `auto`)
- Default timeout per issue (default: 3600 seconds)
- Default max workers for parallel mode (default: 4)

`SprintManager` reads these defaults from config when available.

### How to Verify
- Unit tests pass for `SprintsConfig` dataclass
- `BRConfig.sprints` property returns configured values
- `SprintManager` uses config values when provided
- `to_dict()` includes sprints section

## What We're NOT Doing

- Not modifying CLI argument parsing for sprint commands
- Not adding sprint execution settings to `ll-auto` or `ll-parallel` configs (they have their own)
- Not changing the Sprint YAML file format (options remain per-sprint)
- Not making sprints_dir configurable via CLI flags (config only)

## Problem Analysis

The sprint feature was implemented with reasonable hardcoded defaults, but unlike other features (issues, automation, parallel), it doesn't integrate with the project configuration system. This inconsistency makes it harder for users to customize sprint behavior project-wide.

## Solution Approach

1. Add `sprints` section to JSON schema
2. Add `SprintsConfig` dataclass following existing patterns
3. Integrate into `BRConfig` class
4. Update `SprintManager` to read from config
5. Update documentation
6. Add tests

## Implementation Phases

### Phase 1: Add Config Schema Section

#### Overview
Add the `sprints` configuration section to `config-schema.json`.

#### Changes Required

**File**: `config-schema.json`
**Changes**: Add `sprints` object after `product` section (line 526)

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
      "description": "Default execution mode for sprints (auto=sequential, parallel=concurrent)",
      "default": "auto"
    },
    "default_timeout": {
      "type": "integer",
      "description": "Default timeout per issue in seconds",
      "default": 3600,
      "minimum": 60
    },
    "default_max_workers": {
      "type": "integer",
      "description": "Default worker count for parallel mode",
      "default": 4,
      "minimum": 1,
      "maximum": 8
    }
  },
  "additionalProperties": false
}
```

#### Success Criteria

**Automated Verification**:
- [ ] JSON schema is valid (can be parsed)
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 2: Add SprintsConfig Dataclass

#### Overview
Add the `SprintsConfig` dataclass to `config.py` following existing patterns.

#### Changes Required

**File**: `scripts/little_loops/config.py`
**Changes**:
1. Add `SprintsConfig` to `__all__` (line 17-29)
2. Add `SprintsConfig` dataclass after `ScanConfig` (around line 282)
3. Add `_sprints` initialization in `_parse_config()` (line 328)
4. Add `sprints` property accessor (after `scan` property, line 358)
5. Add `sprints` section to `to_dict()` (line 555)

```python
# Add to __all__ list:
"SprintsConfig",

# New dataclass:
@dataclass
class SprintsConfig:
    """Sprint management configuration."""

    sprints_dir: str = ".sprints"
    default_mode: str = "auto"
    default_timeout: int = 3600
    default_max_workers: int = 4

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SprintsConfig:
        """Create SprintsConfig from dictionary."""
        return cls(
            sprints_dir=data.get("sprints_dir", ".sprints"),
            default_mode=data.get("default_mode", "auto"),
            default_timeout=data.get("default_timeout", 3600),
            default_max_workers=data.get("default_max_workers", 4),
        )

# In _parse_config():
self._sprints = SprintsConfig.from_dict(self._raw_config.get("sprints", {}))

# Property:
@property
def sprints(self) -> SprintsConfig:
    """Get sprints configuration."""
    return self._sprints

# In to_dict():
"sprints": {
    "sprints_dir": self._sprints.sprints_dir,
    "default_mode": self._sprints.default_mode,
    "default_timeout": self._sprints.default_timeout,
    "default_max_workers": self._sprints.default_max_workers,
},
```

#### Success Criteria

**Automated Verification**:
- [ ] Type checking passes: `mypy scripts/little_loops/config.py`
- [ ] Lint passes: `ruff check scripts/little_loops/config.py`

---

### Phase 3: Update SprintManager to Use Config

#### Overview
Modify `SprintManager` to read default values from `BRConfig.sprints` when available.

#### Changes Required

**File**: `scripts/little_loops/sprint.py`
**Changes**: Update `__init__` to derive sprints_dir from config

```python
def __init__(self, sprints_dir: Path | None = None, config: "BRConfig | None" = None) -> None:
    """Initialize SprintManager.

    Args:
        sprints_dir: Directory for sprint definitions (overrides config)
        config: Project configuration for settings and issue validation
    """
    self.config = config
    # Derive sprints_dir: explicit arg > config > default
    if sprints_dir is not None:
        self.sprints_dir = sprints_dir
    elif config is not None:
        self.sprints_dir = Path(config.sprints.sprints_dir)
    else:
        self.sprints_dir = Path(".sprints")
    self.sprints_dir.mkdir(parents=True, exist_ok=True)
```

Also add helper method for getting default options:

```python
def get_default_options(self) -> SprintOptions:
    """Get default SprintOptions from config or hardcoded defaults.

    Returns:
        SprintOptions with values from config if available, else defaults
    """
    if self.config is not None:
        return SprintOptions(
            mode=self.config.sprints.default_mode,
            timeout=self.config.sprints.default_timeout,
            max_workers=self.config.sprints.default_max_workers,
        )
    return SprintOptions()
```

#### Success Criteria

**Automated Verification**:
- [ ] Type checking passes: `mypy scripts/little_loops/sprint.py`
- [ ] Lint passes: `ruff check scripts/little_loops/sprint.py`
- [ ] Existing sprint tests pass: `pytest scripts/tests/test_sprint.py -v`

---

### Phase 4: Add Tests

#### Overview
Add tests for `SprintsConfig` dataclass and integration.

#### Changes Required

**File**: `scripts/tests/test_config.py`
**Changes**: Add `TestSprintsConfig` class and update `to_dict` test

```python
# Add import:
from little_loops.config import SprintsConfig

# New test class:
class TestSprintsConfig:
    """Tests for SprintsConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating SprintsConfig with all fields."""
        data = {
            "sprints_dir": "custom-sprints/",
            "default_mode": "parallel",
            "default_timeout": 7200,
            "default_max_workers": 8,
        }
        config = SprintsConfig.from_dict(data)

        assert config.sprints_dir == "custom-sprints/"
        assert config.default_mode == "parallel"
        assert config.default_timeout == 7200
        assert config.default_max_workers == 8

    def test_from_dict_with_defaults(self) -> None:
        """Test creating SprintsConfig with default values."""
        config = SprintsConfig.from_dict({})

        assert config.sprints_dir == ".sprints"
        assert config.default_mode == "auto"
        assert config.default_timeout == 3600
        assert config.default_max_workers == 4
```

**File**: `scripts/tests/conftest.py`
**Changes**: Add `sprints` section to `sample_config` fixture

```python
"sprints": {
    "sprints_dir": ".sprints",
    "default_mode": "auto",
    "default_timeout": 3600,
    "default_max_workers": 4,
},
```

#### Success Criteria

**Automated Verification**:
- [ ] All config tests pass: `pytest scripts/tests/test_config.py -v`
- [ ] All tests pass: `pytest scripts/tests/ -v`

---

### Phase 5: Update Documentation

#### Overview
Update command documentation to reference config values.

#### Changes Required

**File**: `.claude/commands/create_sprint.md`
**Changes**: Update Configuration section (lines 19-24) to reference config

From:
```markdown
- **Sprints directory**: `.sprints/`
```

To:
```markdown
- **Sprints directory**: `{{config.sprints.sprints_dir}}` (default: `.sprints`)
- **Default mode**: `{{config.sprints.default_mode}}` (auto or parallel)
- **Default timeout**: `{{config.sprints.default_timeout}}` seconds
- **Default max workers**: `{{config.sprints.default_max_workers}}`
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes on changed files

**Manual Verification**:
- [ ] Documentation is clear and accurate

---

## Testing Strategy

### Unit Tests
- `SprintsConfig.from_dict()` with all fields
- `SprintsConfig.from_dict({})` for defaults
- `BRConfig.sprints` property returns `SprintsConfig`
- `BRConfig.to_dict()` includes sprints section

### Integration Tests
- `SprintManager` uses config values when config provided
- `SprintManager` falls back to defaults when no config

## References

- Original issue: `.issues/enhancements/P3-ENH-107-add-sprints-configuration-to-config-schema.md`
- Config pattern: `scripts/little_loops/config.py:169-191` (AutomationConfig)
- Schema pattern: `config-schema.json:119-153` (automation section)
- Test pattern: `scripts/tests/test_config.py:130-158` (TestAutomationConfig)
