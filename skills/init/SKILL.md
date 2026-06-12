---
name: init
description: Use when asked to initialize little-loops, set up ll for a project, or bootstrap config.
disable-model-invocation: true
argument-hint: "[flags]"
allowed-tools:
  - Bash(ll-init:*)
arguments:
  - name: flags
    description: "Optional flags: --yes, --force, --dry-run, --hosts, --codex"
    required: false
metadata:
  short-description: Use when asked to initialize little-loops, set up ll for a project, or bootstrap
---

# Initialize Configuration

<!-- PLUGIN_VERSION: 1.106.0 -->

Guided init has moved to the CLI. This stub delegates to `ll-init`.

## Process

### 1. Parse Flags

```bash
FLAGS="${flags:-}"
FORCE_FLAG=""
DRY_RUN_FLAG=""
HOSTS_FLAG=""
CODEX_FLAG=""

if [[ "$FLAGS" == *"--force"* ]]; then FORCE_FLAG="--force"; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN_FLAG="--dry-run"; fi
if [[ "$FLAGS" == *"--hosts"* ]]; then
    HOSTS_VALUE=$(echo "$FLAGS" | grep -oP '(?<=--hosts\s)\S+' || true)
    if [[ -n "$HOSTS_VALUE" ]]; then HOSTS_FLAG="--hosts $HOSTS_VALUE"; fi
fi
if [[ "$FLAGS" == *"--codex"* ]]; then CODEX_FLAG="--codex"; fi
```

### 2. Run ll-init

```bash
echo "Guided init moved to CLI — running \`ll-init --yes\` with detected defaults…"
ll-init --yes $FORCE_FLAG $DRY_RUN_FLAG $HOSTS_FLAG $CODEX_FLAG
```

## Examples

```bash
/ll:init               # run ll-init --yes with auto-detected defaults
/ll:init --force       # overwrite existing config
/ll:init --dry-run     # preview without writing
/ll:init --hosts codex # also install Codex hook adapter
```
