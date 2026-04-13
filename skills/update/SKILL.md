---
description: |
  Use when the user asks to update little-loops, update the plugin, or update the pip package.

  Trigger keywords: "update little-loops", "update plugin", "update package", "ll update"
argument-hint: "[flags]"
allowed-tools:
  - Bash(python3:*)
  - Bash(pip:*)
  - Bash(pip3:*)
  - Bash(claude:*)
arguments:
  - name: flags
    description: "Optional flags: --plugin, --package, --all, --dry-run"
    required: false
---

# Update little-loops

<!-- PLUGIN_VERSION: 1.66.1 -->

Update the little-loops Claude Code plugin and pip package to the latest version.

## Arguments

$ARGUMENTS

- **flags** (optional): Command flags
  - `--plugin` - Update only the little-loops Claude Code plugin (`claude plugin update ll@little-loops`)
  - `--package` - Update only the little-loops pip package (`pip install`)
  - `--all` - Update both components (same as providing no flag)
  - `--dry-run` - Show what would be updated without making any changes

**Default behavior**: If no component flag (`--plugin`, `--package`, `--all`) is given, both components are updated.

## Process

### 1. Parse Flags

```bash
FLAGS="${flags:-}"
DO_PLUGIN=false
DO_PACKAGE=false
DRY_RUN=false

if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
if [[ "$FLAGS" == *"--plugin"* ]]; then DO_PLUGIN=true; fi
if [[ "$FLAGS" == *"--package"* ]]; then DO_PACKAGE=true; fi
if [[ "$FLAGS" == *"--all"* ]]; then DO_PLUGIN=true; DO_PACKAGE=true; fi

# Default: update both if no component flag given
if [[ "$DO_PLUGIN" == false ]] && [[ "$DO_PACKAGE" == false ]]; then
    DO_PLUGIN=true
    DO_PACKAGE=true
fi
```

Track results for the summary report:
```
PLUGIN_RESULT="SKIP"
PACKAGE_RESULT="SKIP"
```

### 2. Read Current Versions

```bash
# Installed pip package version
PKG_VERSION=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null || echo "not installed")

# Installed plugin version
INSTALLED_PLUGIN_VERSION=$(claude plugin list 2>/dev/null | grep -A1 "ll@little-loops" | grep "Version:" | awk '{print $2}')
```

Print current state:
```
Current versions:
  Plugin (installed):   $INSTALLED_PLUGIN_VERSION
  Package (installed):  $PKG_VERSION
```

---

### 3. Update Plugin (Step A — --plugin)

**Skip this entire step if** `$DO_PLUGIN == false`. Set `PLUGIN_RESULT="SKIP"` and proceed to Step 4.

```bash
echo "========================================"
echo "PLUGIN UPDATE"
echo "========================================"
```

- If `$DRY_RUN == true`:
  - Print `[DRY-RUN] Would run: claude plugin update ll@little-loops`
  - Set `PLUGIN_RESULT="DRY-RUN"`
  - Proceed to Step 4

- If `$DRY_RUN == false`:
  - Run: `claude plugin update ll@little-loops`
  - On success (exit code 0):
    - Read updated version: `UPDATED_PLUGIN_VERSION=$(claude plugin list 2>/dev/null | grep -A1 "ll@little-loops" | grep "Version:" | awk '{print $2}')`
    - Print `[PASS] Plugin updated: $INSTALLED_PLUGIN_VERSION → $UPDATED_PLUGIN_VERSION`
    - Set `PLUGIN_RESULT="PASS ($INSTALLED_PLUGIN_VERSION → $UPDATED_PLUGIN_VERSION)"`
  - On failure:
    - Print `[FAIL] Plugin update failed — try reinstalling: claude plugin install ll@little-loops`
    - Set `PLUGIN_RESULT="FAIL"`

Continue to Step 4 regardless.

---

### 4. Update Package (Step B — --package)

**Skip this entire step if** `$DO_PACKAGE == false`. Set `PACKAGE_RESULT="SKIP"` and proceed to Step 5.

```bash
echo "========================================"
echo "PACKAGE UPDATE"
echo "========================================"
```

Detect install command based on whether little-loops is installed in editable mode:
```bash
EDITABLE_INSTALL=$(pip show little-loops 2>/dev/null | grep -E "^Editable project location:")
if [ -n "$EDITABLE_INSTALL" ]; then
    EDITABLE_PATH=$(echo "$EDITABLE_INSTALL" | sed 's/^Editable project location: //')
    INSTALL_CMD="pip install -e '$EDITABLE_PATH'"
else
    INSTALL_CMD="pip install --upgrade little-loops"
fi
```

Read version before update:
```bash
PKG_BEFORE=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null || echo "not installed")
```

- If `$DRY_RUN == true`:
  - Print `[DRY-RUN] Would run: $INSTALL_CMD`
  - Set `PACKAGE_RESULT="DRY-RUN"`
  - Proceed to Step 5

- If `$DRY_RUN == false`:
  - Run `$INSTALL_CMD`
  - On success:
    - Read new version: `PKG_AFTER=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null || echo "unknown")`
    - Print `[PASS] Package updated: $PKG_BEFORE → $PKG_AFTER`
    - Set `PACKAGE_RESULT="PASS ($PKG_BEFORE → $PKG_AFTER)"`
  - On failure:
    - Print `[FAIL] Package update failed — run manually: $INSTALL_CMD`
    - Set `PACKAGE_RESULT="FAIL"`

Continue to Step 5 regardless.

---

### 5. Summary Report

```
================================================================================
UPDATE COMPLETE
================================================================================

Dry-run: $DRY_RUN

Results:
  Plugin:   $PLUGIN_RESULT
  Package:  $PACKAGE_RESULT

Status key:
  PASS      — Updated successfully
  SKIP      — Step not selected
  FAIL      — Update failed (see errors above for manual steps)
  DRY-RUN   — Would have updated (re-run without --dry-run to apply)
  WARN      — Config has unknown keys (check ll-config.json)

================================================================================
```

---

### Step 6: Config Health Check

If either `$PLUGIN_RESULT` or `$PACKAGE_RESULT` starts with `"PASS"`:

```bash
if [[ "$PLUGIN_RESULT" == PASS* ]] || [[ "$PACKAGE_RESULT" == PASS* ]]; then
python3 -c "
import json, pathlib, sys

config_path = pathlib.Path('.ll/ll-config.json')
if not config_path.exists():
    sys.exit(0)

# Locate config-schema.json via plugin installation registry
plugins_file = pathlib.Path.home() / '.claude' / 'plugins' / 'installed_plugins.json'
if not plugins_file.exists():
    sys.exit(0)
plugins = json.loads(plugins_file.read_text()).get('plugins', {})
entry = plugins.get('ll@little-loops', [])
if not entry:
    sys.exit(0)
schema_path = pathlib.Path(entry[0]['installPath']) / 'config-schema.json'
if not schema_path.exists():
    sys.exit(0)

config = json.loads(config_path.read_text())
schema = json.loads(schema_path.read_text())
known = set(schema.get('properties', {}).keys())
unknown = sorted(set(config.keys()) - known)
if unknown:
    print('[WARN] Config issues detected: unknown keys: ' + ', '.join(unknown))
else:
    print('[PASS] ll-config.json is valid')
" 2>/dev/null || true
fi
```

Non-blocking — does not fail the update. Silent skip if `.ll/ll-config.json` or the schema is absent.

---

## Examples

```bash
# Update both plugin and package
/ll:update

# Update only the pip package
/ll:update --package

# Update only the Claude Code plugin
/ll:update --plugin

# Preview what would be updated
/ll:update --dry-run
```
