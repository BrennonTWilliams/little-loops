---
description: |
  Publish little-loops: bump version in plugin.json, marketplace.json, pyproject.toml, and __init__.py.
  Source-repo-only command for little-loops maintainers.

  Trigger keywords: "publish little-loops", "bump version", "sync marketplace", "update plugin.json version"
argument-hint: "<version|patch|minor|major> [--dry-run]"
allowed-tools:
  - Read
  - Edit
  - Bash(python3:*)
  - Bash(git:*)
arguments:
  - name: version
    description: "New version string (e.g., 1.67.0) or bump level (patch|minor|major)"
    required: true
  - name: flags
    description: "Optional flags: --dry-run"
    required: false
---

# Publish little-loops

Bump the version in all source files and sync `marketplace.json` with the new version.

**This command is for little-loops source repo maintainers only.**

## Arguments

$ARGUMENTS

- **version** (required): New version string (e.g., `1.67.0`) or bump level (`patch`, `minor`, `major`)
- **flags** (optional): `--dry-run` — Preview changes without applying

## Process

### 1. Verify Source Repo

```bash
if [ ! -f ".claude-plugin/plugin.json" ]; then
    echo "Error: Not in little-loops source repo (.claude-plugin/plugin.json not found)"
    exit 1
fi
```

### 2. Parse Arguments and Compute New Version

```bash
VERSION="${version}"
FLAGS="${flags:-}"
DRY_RUN=false

if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
```

Read current version from `plugin.json`:
```bash
CURRENT_VERSION=$(python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])")
```

If `$VERSION` is a bump level (`patch`, `minor`, or `major`), compute the new version:
```bash
NEW_VERSION=$(python3 -c "
v = '$CURRENT_VERSION'.split('.')
major, minor, patch = int(v[0]), int(v[1]), int(v[2])
level = '$VERSION'
if level == 'major': major += 1; minor = 0; patch = 0
elif level == 'minor': minor += 1; patch = 0
elif level == 'patch': patch += 1
else: raise SystemExit(f'Invalid version/level: {level}')
print(f'{major}.{minor}.{patch}')
")
```

If `$VERSION` is an explicit version string (e.g., `1.67.0`), set `NEW_VERSION="$VERSION"`.

### 3. Read All Current Versions

```bash
CURRENT_MARKETPLACE=$(python3 -c "import json; print(json.load(open('.claude-plugin/marketplace.json'))['version'])")
CURRENT_PKG=$(python3 -c "
import tomllib
d = tomllib.load(open('scripts/pyproject.toml', 'rb'))
print(d['project']['version'])
" 2>/dev/null || python3 -c "
import re
m = re.search(r'version\s*=\s*\"([^\"]+)\"', open('scripts/pyproject.toml').read())
print(m.group(1))
")
CURRENT_INIT=$(python3 -c "
import re
m = re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('scripts/little_loops/__init__.py').read())
print(m.group(1))
")
```

Print planned changes:
```
Publish little-loops $CURRENT_VERSION → $NEW_VERSION

Files to update:
  .claude-plugin/plugin.json           $CURRENT_VERSION → $NEW_VERSION
  .claude-plugin/marketplace.json      $CURRENT_MARKETPLACE → $NEW_VERSION (top-level + plugins[0])
  scripts/pyproject.toml               $CURRENT_PKG → $NEW_VERSION
  scripts/little_loops/__init__.py     $CURRENT_INIT → $NEW_VERSION
```

If `$DRY_RUN == true`: print `[DRY-RUN] No changes applied.` and stop here.

### 4. Bump Versions

Use the Edit tool to update each file:

**`.claude-plugin/plugin.json`** — replace version field:
- Replace `"version": "$CURRENT_VERSION"` with `"version": "$NEW_VERSION"`

**`.claude-plugin/marketplace.json`** — update both version fields:
- Replace top-level `"version": "$CURRENT_MARKETPLACE"` with `"version": "$NEW_VERSION"`
- Replace `"version": "$CURRENT_MARKETPLACE"` in `plugins[0]` with `"version": "$NEW_VERSION"`

  > **Note**: Both occurrences share the same value (`$CURRENT_MARKETPLACE`). Use `replace_all: true` or two targeted Edit operations to update both fields.

**`scripts/pyproject.toml`** — replace version field:
- Replace `version = "$CURRENT_PKG"` with `version = "$NEW_VERSION"`

**`scripts/little_loops/__init__.py`** — replace `__version__`:
- Replace `__version__ = "$CURRENT_INIT"` with `__version__ = "$NEW_VERSION"`

### 5. Commit Changes

Stage and commit all version files:

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json scripts/pyproject.toml scripts/little_loops/__init__.py
git commit -m "chore(release): bump version to $NEW_VERSION"
```

Print on success:
```
[PASS] Version bumped: $CURRENT_VERSION → $NEW_VERSION
Committed: chore(release): bump version to $NEW_VERSION

Next steps:
  Tag:        git tag -a v$NEW_VERSION -m "Release v$NEW_VERSION"
  Push:       git push origin main && git push origin v$NEW_VERSION
  Or use:     /ll:manage-release release $NEW_VERSION --push
```

---

## Examples

```bash
# Bump patch version (e.g., 1.66.1 → 1.66.2)
/ll:publish patch

# Bump minor version (e.g., 1.66.1 → 1.67.0)
/ll:publish minor

# Set explicit version
/ll:publish 1.70.0

# Preview changes without applying
/ll:publish patch --dry-run
```
