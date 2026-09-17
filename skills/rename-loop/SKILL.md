---
name: rename-loop
description: Rename a loop and update all references in YAMLs, tests, and docs.
disable-model-invocation: true

argument-hint: "<old-name> <new-name> [--dry-run] [--yes]"
model: sonnet
allowed-tools:
  - Bash(git:*, mv:*, test:*)
  - Read
  - Edit
  - Glob
  - Grep
  - AskUserQuestion

arguments:
  - name: old_name
    description: Current loop name (bare identifier, no .yaml extension)
    required: true
  - name: new_name
    description: New loop name (bare identifier, no .yaml extension)
    required: true
  - name: flags
    description: "--dry-run to preview all changes without applying; --yes to skip confirmation prompt"
    required: false
metadata:
  short-description: Rename a loop and update all references in YAMLs, tests, and docs.
---

# Rename Loop

Rename a loop YAML file and update every reference to it so the loop system remains
fully functional after the rename.

---

## Step 1: Parse and Validate Arguments

Extract `old_name`, `new_name`, and flags from the arguments:

- Strip any `.yaml` extension from `old_name` or `new_name` if present; note that you
  stripped it.
- Validate `new_name` is a valid kebab-case identifier (lowercase letters, numbers,
  hyphens, optional path prefix for sub-directory loops like `oracles/name`).
- Set `DRY_RUN=true` if `--dry-run` is present in flags.
- Set `YES=true` if `--yes` is present in flags.

---

## Step 2: Locate the Loop and Determine Scope

Check for the loop file in this priority order:

1. **Project-level**: `.loops/<old_name>.yaml` → scope = `project`
2. **Built-in**: `<builtin-dir>/<old_name>.yaml` → scope = `builtin`, where
   `<builtin-dir>` is the loops directory shipped inside the installed
   `little_loops` package:
   `$(python -c "import little_loops.loops as m, pathlib; print(pathlib.Path(m.__file__).parent)")`

Built-in loops are read-only package data — they are not part of your project's
source tree. A `builtin` rename therefore *copies* the loop into `.loops/` under
the new name (the project copy shadows the built-in by name); the packaged
original is left untouched.

If neither file exists, abort:
```
Error: Loop '<old_name>' not found.
  Checked: .loops/<old_name>.yaml
           <builtin-dir>/<old_name>.yaml
```

---

## Step 3: Guard — Check for Naming Conflict

Check whether the destination file already exists in the same directory as the source.
If `<dir>/<new_name>.yaml` already exists, abort:
```
Error: A loop named '<new_name>' already exists at <path>.
  Remove or rename it first.
```

---

## Step 4: Guard — Check If Loop Is Running

Check for active PID files (any instance):
```bash
ls .loops/.running/<old_name>-*.pid 2>/dev/null | head -1
```

If the output is non-empty (at least one PID file found), abort:
```
Error: Loop '<old_name>' appears to be running (PID file found).
  Stop it first: ll-loop stop <old_name>
```

---

## Step 5: Collect All Changes

Gather every change that needs to be made. Do not apply anything yet — just build the
list.

### 5a. File rename

- **Scope `project`**: plain `mv` (`.loops/` is git-ignored)
  ```
  mv .loops/<old_name>.yaml .loops/<new_name>.yaml
  ```
- **Scope `builtin`**: copy into project scope (the packaged file is read-only)
  ```
  mkdir -p .loops && cp <builtin-dir>/<old_name>.yaml .loops/<new_name>.yaml
  ```

### 5b. `name:` field inside the renamed YAML

Read the YAML file and find the `name:` field at the top level. The value may be quoted
or unquoted:
```yaml
name: "old-name"   # or:
name: old-name
```

Record an Edit to replace the old name value with `new_name`.

### 5c. Sub-loop `loop:` references

Search for `loop: <old_name>` (exact bare name, no extension) across the project's
loop YAML files:

- `.loops/**/*.yaml` (includes `.loops/oracles/`)

Use Grep with pattern `loop:\s+<old_name>` across those paths. For each match, record an
Edit to replace `loop: <old_name>` with `loop: <new_name>`. Packaged built-in loops that
reference `<old_name>` are read-only and keep resolving to the packaged original — do
not try to edit them.

### 5d. Project references (docs, scripts, configs)

Search the project's own tracked files for the bare loop name — sprint YAMLs, docs, shell
aliases, `.ll/ll-config.json`:

```
Grep pattern: <old_name> across the project (exclude .loops/tmp/, .loops/runs/, .git/)
```

Record an Edit for each project file that contains the old name, replacing occurrences
with `<new_name>`.

---

## Step 6: If `--dry-run`, Print the Change Plan and Stop

Print a structured preview of every change collected in Step 5:

```
DRY RUN: rename-loop <old_name> → <new_name>  [scope: builtin|project]

FILE RENAME:
  <action> <source> → <dest>

YAML NAME FIELD:
  <file>:<line> — name: "<old_name>" → name: "<new_name>"

LOOP REFERENCES (<N> found):
  <file>:<line> — loop: <old_name> → loop: <new_name>
  ...

PROJECT REFERENCES (<N> occurrences):
  <file>:<line> — ...<old_name>... → ...<new_name>...
  ...

Total: <N> files affected, <M> changes.
No changes applied (--dry-run).
```

Stop after printing this output.

---

## Step 7: Confirm (Unless `--yes`)

If `YES` is not set, use `AskUserQuestion`:

```yaml
questions:
  - question: "Apply <N> changes to rename '<old_name>' → '<new_name>'?"
    header: "Confirm rename"
    multiSelect: false
    options:
      - label: "Yes, apply all changes (Recommended)"
        description: "Rename the file and update all <N> references"
      - label: "No, cancel"
        description: "Abort without making any changes"
```

If the user selects "No, cancel": report "Cancelled. No changes made." and stop.

---

## Step 8: Execute Changes

Apply each change collected in Step 5 in this order:

1. **Rename the file** (Bash: `mv`, or `cp` for builtin scope)
2. **Edit `name:` field** in the renamed YAML (Edit tool)
3. **Edit each sub-loop reference** (Edit tool, one file at a time)
4. **Edit project reference files** (Edit tool)

For each Edit, use `replace_all: true` when replacing the old name string to catch all
occurrences in that file in a single call.

---

## Step 9: Report Results

Print a summary of every file changed:

```
Renamed: <old_name> → <new_name>  [scope: builtin|project]

Changes applied:
  RENAMED   <source> → <dest>
  EDITED    <yaml-file>  (name: field)
  EDITED    <file> — <N> loop reference(s) updated
  EDITED    <project-file> — <N> occurrence(s)

Total: <N> files modified.
```

If any `.loops/tmp/<old_name>-*` files exist, note:
```
Note: Leftover temp files found (cosmetic, no functional impact):
  .loops/tmp/<old_name>-*
  Remove manually if desired: rm .loops/tmp/<old_name>-*
```

---

## Usage Examples

```bash
# Preview all changes without applying them
/ll:rename-loop refine-to-ready-issue refine-to-ready --dry-run

# Rename with confirmation prompt
/ll:rename-loop refine-to-ready-issue refine-to-ready

# Rename without confirmation (for automation)
/ll:rename-loop refine-to-ready-issue refine-to-ready --yes

# Rename a project-level loop
/ll:rename-loop my-custom-loop my-renamed-loop
```
