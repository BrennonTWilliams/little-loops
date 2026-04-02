---
description: |
  Use when the user asks to update little-loops, update the plugin, push to marketplace, or update the pip package. Consolidates plugin, marketplace, and package updates.

  Trigger keywords: "update little-loops", "update plugin", "update marketplace", "update package", "ll update"
argument-hint: "[flags]"
allowed-tools:
  - Read
  - Edit
  - Bash(python3:*)
  - Bash(pip:*)
  - Bash(pip3:*)
  - Bash(claude:*)
  - Bash(git:*)
arguments:
  - name: flags
    description: "Optional flags: --marketplace, --plugin, --package, --all, --dry-run"
    required: false
---

# Update Components

<!-- PLUGIN_VERSION: 1.66.1 -->

You are tasked with updating one or more little-loops components: the plugin marketplace listing, the Claude Code plugin, and the pip package.

## Arguments

$ARGUMENTS

- **flags** (optional): Command flags
  - `--marketplace` - Update only the plugin marketplace listing (`.claude-plugin/marketplace.json`)
  - `--plugin` - Update only the little-loops Claude Code plugin (`claude plugin update ll@little-loops`)
  - `--package` - Update only the little-loops pip package (`pip install`)
  - `--all` - Update all components (same as providing no flag)
  - `--dry-run` - Show what would be updated without making any changes

**Default behavior**: If no component flag (`--marketplace`, `--plugin`, `--package`, `--all`) is given, all three components are updated.

## Process

### 1. Parse Flags

```bash
FLAGS="${flags:-}"
DO_MARKETPLACE=false
DO_PLUGIN=false
DO_PACKAGE=false
DRY_RUN=false

if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
if [[ "$FLAGS" == *"--marketplace"* ]]; then DO_MARKETPLACE=true; fi
if [[ "$FLAGS" == *"--plugin"* ]]; then DO_PLUGIN=true; fi
if [[ "$FLAGS" == *"--package"* ]]; then DO_PACKAGE=true; fi
if [[ "$FLAGS" == *"--all"* ]]; then DO_MARKETPLACE=true; DO_PLUGIN=true; DO_PACKAGE=true; fi

# Default: update all if no component flag given
if [[ "$DO_MARKETPLACE" == false ]] && [[ "$DO_PLUGIN" == false ]] && [[ "$DO_PACKAGE" == false ]]; then
    DO_MARKETPLACE=true
    DO_PLUGIN=true
    DO_PACKAGE=true
fi
```

Track results for the summary report:
```
MARKETPLACE_RESULT="SKIP"
PLUGIN_RESULT="SKIP"
PACKAGE_RESULT="SKIP"
```

### 2. Read Current Versions

```bash
# Installed pip package version (always relevant)
PKG_VERSION=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null || echo "not installed")

# Plugin/marketplace versions only exist in the little-loops repo itself
PLUGIN_VERSION="N/A"
MARKETPLACE_VERSION="N/A"
if [[ "$DO_MARKETPLACE" == true ]] || [[ "$DO_PLUGIN" == true ]]; then
    PLUGIN_VERSION=$(python3 -c "import json; d=json.load(open('.claude-plugin/plugin.json')); print(d['version'])")
    MARKETPLACE_VERSION=$(python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); print(d['version'])" 2>/dev/null || echo "N/A")
fi
```

Print current state:
```
Current versions:
  plugin.json:    $PLUGIN_VERSION
  marketplace:    $MARKETPLACE_VERSION
  pip package:    $PKG_VERSION
```

---

### 3. Update Marketplace Listing (Step A — --marketplace)

**Skip this entire step if** `$DO_MARKETPLACE == false`. Set `MARKETPLACE_RESULT="SKIP"` and proceed to Step 4.

```bash
echo "========================================"
echo "MARKETPLACE UPDATE"
echo "========================================"
```

Read the current marketplace version:
```bash
MARKETPLACE_CURRENT=$(python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); print(d['version'])")
MARKETPLACE_PLUGIN_ENTRY=$(python3 -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); print(d['plugins'][0]['version'])")
```

**If `$MARKETPLACE_CURRENT == $PLUGIN_VERSION` and `$MARKETPLACE_PLUGIN_ENTRY == $PLUGIN_VERSION`:**
- Print `[SKIP] Marketplace already at $PLUGIN_VERSION`
- Set `MARKETPLACE_RESULT="SKIP (already at $PLUGIN_VERSION)"`
- Proceed to Step 4

**Otherwise:**

- If `$DRY_RUN == true`:
  - Print `[DRY-RUN] Would update marketplace.json: $MARKETPLACE_CURRENT → $PLUGIN_VERSION`
  - Set `MARKETPLACE_RESULT="DRY-RUN ($MARKETPLACE_CURRENT → $PLUGIN_VERSION)"`
  - Proceed to Step 4

- If `$DRY_RUN == false`:
  - Use the Edit tool to update `.claude-plugin/marketplace.json`:
    - Replace the top-level `"version": "$MARKETPLACE_CURRENT"` with `"version": "$PLUGIN_VERSION"`
    - Replace `"version": "$MARKETPLACE_PLUGIN_ENTRY"` inside `plugins[0]` with `"version": "$PLUGIN_VERSION"`
  - Stage the change: run `git add .claude-plugin/marketplace.json`
  - On success:
    - Print `[PASS] Marketplace updated: $MARKETPLACE_CURRENT → $PLUGIN_VERSION`
    - Set `MARKETPLACE_RESULT="PASS ($MARKETPLACE_CURRENT → $PLUGIN_VERSION)"`
  - On failure:
    - Print `[FAIL] Marketplace update failed`
    - Set `MARKETPLACE_RESULT="FAIL"`

Continue to Step 4 regardless.

---

### 4. Update Plugin (Step B — --plugin)

**Skip this entire step if** `$DO_PLUGIN == false`. Set `PLUGIN_RESULT="SKIP"` and proceed to Step 5.

```bash
echo "========================================"
echo "PLUGIN UPDATE"
echo "========================================"
```

**Check installed plugin version first**:

```bash
INSTALLED_PLUGIN_VERSION=$(claude plugin list 2>/dev/null | grep -A1 "ll@little-loops" | grep "Version:" | awk '{print $2}')
```

**If `$INSTALLED_PLUGIN_VERSION == $PLUGIN_VERSION`** (and `INSTALLED_PLUGIN_VERSION` is non-empty):
- Print `[SKIP] Plugin already at $PLUGIN_VERSION`
- Set `PLUGIN_RESULT="SKIP (already at $PLUGIN_VERSION)"`
- Proceed to Step 5

If `claude plugin list` fails or returns empty, fall through to the update logic below (safe fallback).

- If `$DRY_RUN == true`:
  - Print `[DRY-RUN] Would run: claude plugin update ll@little-loops`
  - Set `PLUGIN_RESULT="DRY-RUN"`
  - Proceed to Step 5

- If `$DRY_RUN == false`:
  - Run: `claude plugin update ll@little-loops`
  - On success (exit code 0):
    - Print `[PASS] Plugin updated`
    - Set `PLUGIN_RESULT="PASS"`
  - On failure:
    - Print `[FAIL] Plugin update failed — try reinstalling: claude plugin install ll@little-loops`
    - Set `PLUGIN_RESULT="FAIL"`

Continue to Step 5 regardless.

---

### 5. Update Package (Step C — --package)

**Skip this entire step if** `$DO_PACKAGE == false`. Set `PACKAGE_RESULT="SKIP"` and proceed to Step 6.

```bash
echo "========================================"
echo "PACKAGE UPDATE"
echo "========================================"
```

Detect install command based on context:
```bash
[ -d "./scripts" ] && INSTALL_CMD="pip install -e './scripts'" || INSTALL_CMD="pip install --upgrade little-loops"
```

Read version before update:
```bash
PKG_BEFORE=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null || echo "not installed")
```

**Check source version for dev-repo installs** (skip comparison for non-dev `pip install --upgrade` installs where no local source exists):

```bash
SRC_VERSION=""
if [ -d "./scripts" ]; then
    SRC_VERSION=$(python3 -c "import tomllib; d=tomllib.load(open('scripts/pyproject.toml','rb')); print(d['project']['version'])" 2>/dev/null \
        || python3 -c "import re; m=re.search(r'version\s*=\s*\"([^\"]+)\"', open('scripts/pyproject.toml').read()); print(m.group(1) if m else '')" 2>/dev/null \
        || echo "")
fi
```

**If `$PKG_BEFORE == $SRC_VERSION`** (and `SRC_VERSION` is non-empty and `DRY_RUN == false`):
- Print `[SKIP] Package already at $PKG_BEFORE`
- Set `PACKAGE_RESULT="SKIP (already at $PKG_BEFORE)"`
- Proceed to Step 6

For non-dev installs (`INSTALL_CMD="pip install --upgrade little-loops"`), `SRC_VERSION` will be empty, so the skip is never triggered — always run.

- If `$DRY_RUN == true`:
  - Print `[DRY-RUN] Would run: $INSTALL_CMD`
  - Set `PACKAGE_RESULT="DRY-RUN"`
  - Proceed to Step 6

- If `$DRY_RUN == false`:
  - Run `$INSTALL_CMD`
  - On success:
    - Read new version: `PKG_AFTER=$(python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null || echo "unknown")`
    - Print `[PASS] Package updated: $PKG_BEFORE → $PKG_AFTER`
    - Set `PACKAGE_RESULT="PASS ($PKG_BEFORE → $PKG_AFTER)"`
  - On failure:
    - Print `[FAIL] Package update failed — run manually: $INSTALL_CMD`
    - Set `PACKAGE_RESULT="FAIL"`

Continue to Step 6 regardless.

---

### 6. Summary Report

```
================================================================================
UPDATE COMPLETE
================================================================================

Dry-run: $DRY_RUN

Results:
  Marketplace: $MARKETPLACE_RESULT
  Plugin:      $PLUGIN_RESULT
  Package:     $PACKAGE_RESULT

Status key:
  PASS      — Updated successfully
  SKIP      — Already up to date, or step not selected
  FAIL      — Update failed (see errors above for manual steps)
  DRY-RUN   — Would have updated (re-run without --dry-run to apply)

================================================================================
```

---

## Examples

```bash
# Update all components
/ll:update

# Sync marketplace.json with plugin.json version
/ll:update --marketplace

# Update only the pip package
/ll:update --package

# Preview what would be updated
/ll:update --dry-run

# Update plugin and package (skip marketplace)
/ll:update --plugin --package
```
