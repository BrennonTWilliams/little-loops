# FEAT-080: User-local settings override via ll.local.md - Implementation Plan

## Issue Reference
- **File**: .issues/features/P3-FEAT-080-user-local-settings-override.md
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The configuration loading occurs in two places:

1. **Shell Hook** (`hooks/scripts/session-start.sh:14-23`): Loads and displays `ll-config.json` to Claude Code's context via stdout
2. **Python CLI** (`scripts/little_loops/config.py:329-348`): `BRConfig` class loads config for CLI tools

Currently there's no support for user-local overrides. The codebase already has:
- `.claude/settings.local.json` pattern (gitignored at line 48)
- YAML frontmatter parsing in `goals_parser.py:111-140` using `yaml.safe_load()`
- Deep merge pattern in `config.py:100-123` for categories

## Desired End State

Users can create `.claude/ll.local.md` with YAML frontmatter to override settings from `ll-config.json`:

```markdown
---
project:
  test_cmd: "python -m pytest scripts/tests/ -v --tb=short"
scan:
  focus_dirs: ["scripts/", "my-experimental-dir/"]
---

# Local Settings Notes

Personal development preferences.
```

### How to Verify
- Create `ll.local.md` with override settings
- Start new session, see "[little-loops] Local overrides applied" message
- Verify overridden values are shown in config output

## What We're NOT Doing

- Not modifying Python `BRConfig` class - the shell hook provides config to Claude Code context
- Not adding schema validation for `ll.local.md` - keep it simple
- Not supporting complex merge strategies beyond deep merge - arrays replace, nulls remove

## Solution Approach

Modify `session-start.sh` to:
1. Check if `ll.local.md` exists
2. Parse YAML frontmatter using `yq` (commonly available) or Python one-liner
3. Deep merge local overrides onto base config
4. Output merged config to Claude Code context

## Implementation Phases

### Phase 1: Update .gitignore

#### Overview
Add `.claude/ll.local.md` to gitignore alongside `settings.local.json`.

#### Changes Required

**File**: `.gitignore`
**Changes**: Add entry for ll.local.md after settings.local.json

```gitignore
# Claude Code
.claude/settings.local.json
.claude/ll.local.md
.mcp.json
```

#### Success Criteria

**Automated Verification**:
- [ ] `.gitignore` contains `.claude/ll.local.md` entry: `grep -q "ll.local.md" .gitignore`

---

### Phase 2: Implement Local Override Loading

#### Overview
Modify `session-start.sh` to load and merge `ll.local.md` settings.

#### Changes Required

**File**: `hooks/scripts/session-start.sh`
**Changes**: Add YAML frontmatter parsing and JSON deep merge

The script will:
1. Check for `.claude/ll.local.md`
2. Extract YAML frontmatter (content between `---` markers)
3. Use Python to parse YAML and deep merge with JSON config
4. Output merged config or base config if no local file

```bash
#!/bin/bash
#
# session-start.sh
# SessionStart hook for little-loops plugin
#
# Cleans up state from previous session and loads/displays config
#

set -euo pipefail

# Clean up state from previous session
rm -f .claude/ll-context-state.json 2>/dev/null || true

# Find config file
CONFIG_FILE=".claude/ll-config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="ll-config.json"
fi

LOCAL_FILE=".claude/ll.local.md"

# Function to merge local overrides into config
merge_local_config() {
    python3 << 'PYTHON'
import json
import sys
from pathlib import Path

def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base. Arrays replace, null removes keys."""
    result = dict(base)
    for key, value in override.items():
        if value is None:
            # Explicit null removes the key
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            # Deep merge nested dicts
            result[key] = deep_merge(result[key], value)
        else:
            # Replace value (including arrays)
            result[key] = value
    return result

def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from markdown content."""
    if not content or not content.startswith("---"):
        return {}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}

    frontmatter_text = parts[1].strip()
    if not frontmatter_text:
        return {}

    try:
        import yaml
        return yaml.safe_load(frontmatter_text) or {}
    except Exception:
        return {}

# Load base config
config_file = Path(".claude/ll-config.json")
if not config_file.exists():
    config_file = Path("ll-config.json")

if config_file.exists():
    base_config = json.loads(config_file.read_text())
else:
    base_config = {}

# Check for local overrides
local_file = Path(".claude/ll.local.md")
if local_file.exists():
    local_overrides = parse_frontmatter(local_file.read_text())
    if local_overrides:
        merged = deep_merge(base_config, local_overrides)
        print("[little-loops] Config loaded:", str(config_file), file=sys.stderr)
        print("[little-loops] Local overrides applied from:", str(local_file), file=sys.stderr)
        print(json.dumps(merged, indent=2))
        sys.exit(0)

# No local overrides, output base config
if config_file.exists():
    print("[little-loops] Config loaded:", str(config_file), file=sys.stderr)
    print(config_file.read_text()[:4000])  # Limit output size
else:
    print("[little-loops] Warning: No config found. Run /ll:init to create one.", file=sys.stderr)
PYTHON
}

# Display config (with optional local overrides)
if [ -f "$CONFIG_FILE" ]; then
    if [ -f "$LOCAL_FILE" ]; then
        # Use Python to merge configs
        merge_local_config
    else
        echo "[little-loops] Config loaded: $CONFIG_FILE"
        head -50 "$CONFIG_FILE"
    fi
else
    echo "[little-loops] Warning: No config found. Run /ll:init to create one."
fi
```

#### Success Criteria

**Automated Verification**:
- [ ] Script syntax is valid: `bash -n hooks/scripts/session-start.sh`
- [ ] Script runs without error when no local file exists
- [ ] Script handles missing config file gracefully

**Manual Verification**:
- [ ] Create `.claude/ll.local.md` with test overrides
- [ ] Start new session and verify "[little-loops] Local overrides applied" message appears
- [ ] Verify merged config shows overridden values

---

### Phase 3: Update Documentation

#### Overview
Add documentation about `ll.local.md` to CLAUDE.md.

#### Changes Required

**File**: `.claude/CLAUDE.md`
**Changes**: Add "Local Settings" section under "Project Configuration"

```markdown
## Project Configuration

- **Plugin manifest**: `plugin.json`
- **Config schema**: `config-schema.json`
- **Project config**: `.claude/ll-config.json` (read this for project-specific settings)
- **Local overrides**: `.claude/ll.local.md` (user-specific, gitignored)
- **Hooks**: `hooks/hooks.json`

### Local Settings Override

Create `.claude/ll.local.md` to override settings for your local environment:

```markdown
---
project:
  test_cmd: "python -m pytest scripts/tests/ -v --tb=short"
scan:
  focus_dirs: ["scripts/", "my-experimental-dir/"]
---

# Local Settings Notes

Personal development preferences.
```

**Merge behavior**:
- Nested objects are deep merged
- Arrays replace (not append)
- Explicit `null` removes a setting
```

#### Success Criteria

**Automated Verification**:
- [ ] CLAUDE.md contains `ll.local.md` reference: `grep -q "ll.local.md" .claude/CLAUDE.md`
- [ ] Markdown lints cleanly

---

## Testing Strategy

### Manual Testing
1. Start fresh session without `ll.local.md` - should work as before
2. Create `ll.local.md` with project.test_cmd override
3. Start new session - verify override message and merged config
4. Test null value removes setting
5. Test array replacement (not append)

### Edge Cases
- Empty frontmatter (`---\n---`)
- Invalid YAML in frontmatter
- Missing base config file
- Deeply nested overrides

## References

- Original issue: `.issues/features/P3-FEAT-080-user-local-settings-override.md`
- YAML parsing pattern: `scripts/little_loops/goals_parser.py:111-140`
- Existing local pattern: `.gitignore:48` (settings.local.json)
- Config merge pattern: `scripts/little_loops/config.py:100-123`
