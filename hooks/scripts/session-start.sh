#!/bin/bash
#
# session-start.sh
# SessionStart hook for little-loops plugin
#
# Cleans up state from previous session and loads/displays config
# Supports user-local overrides via .claude/ll.local.md
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

# Function to merge local overrides into config using Python
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
    config_text = config_file.read_text()

    # Warn if very large
    if len(config_text) > 5000:
        print(f"[little-loops] Warning: Large config ({len(config_text)} chars)", file=sys.stderr)

    print(config_text)  # Full output
else:
    print("[little-loops] Warning: No config found. Run /ll:init to create one.", file=sys.stderr)
PYTHON
}

# Validate enabled features have required sub-configuration
validate_enabled_features() {
    local config_file="$1"

    if ! command -v jq &> /dev/null; then
        return 0
    fi

    if [ ! -f "$config_file" ]; then
        return 0
    fi

    # sync.enabled requires sync.github configuration
    local sync_enabled
    sync_enabled=$(jq -r '.sync.enabled // false' "$config_file" 2>/dev/null)
    if [ "$sync_enabled" = "true" ]; then
        local github_keys
        github_keys=$(jq -r '.sync.github // {} | keys | length' "$config_file" 2>/dev/null)
        if [ "$github_keys" = "0" ]; then
            echo "[little-loops] Warning: sync.enabled is true but sync.github is not configured" >&2
        fi
    fi

    # documents.enabled requires documents.categories with entries
    local docs_enabled
    docs_enabled=$(jq -r '.documents.enabled // false' "$config_file" 2>/dev/null)
    if [ "$docs_enabled" = "true" ]; then
        local cat_keys
        cat_keys=$(jq -r '.documents.categories // {} | keys | length' "$config_file" 2>/dev/null)
        if [ "$cat_keys" = "0" ]; then
            echo "[little-loops] Warning: documents.enabled is true but no document categories configured" >&2
        fi
    fi

    # product.enabled requires goals file to exist
    local product_enabled
    product_enabled=$(jq -r '.product.enabled // false' "$config_file" 2>/dev/null)
    if [ "$product_enabled" = "true" ]; then
        local goals_file
        goals_file=$(jq -r '.product.goals_file // ".claude/ll-goals.md"' "$config_file" 2>/dev/null)
        if [ ! -f "$goals_file" ]; then
            echo "[little-loops] Warning: product.enabled is true but goals file not found: $goals_file" >&2
        fi
    fi
}

# Display config (with optional local overrides)
if [ -f "$CONFIG_FILE" ] || [ -f "$LOCAL_FILE" ]; then
    if [ -f "$LOCAL_FILE" ]; then
        # Use Python to merge configs
        merge_local_config
    else
        echo "[little-loops] Config loaded: $CONFIG_FILE" >&2
        cat "$CONFIG_FILE"
    fi
    # Validate enabled features have required sub-configuration
    validate_enabled_features "$CONFIG_FILE"
else
    echo "[little-loops] Warning: No config found. Run /ll:init to create one."
fi
