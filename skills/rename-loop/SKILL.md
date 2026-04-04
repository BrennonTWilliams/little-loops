---
description: |
  Rename a loop (built-in or project-level) and update all references to maintain full
  functionality. Updates the YAML file, its internal name: field, all loop: sub-loop
  references in other YAMLs, tests (for built-in loops), and docs.

  Trigger keywords: "rename loop", "rename a loop", "change loop name"

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
2. **Built-in**: `scripts/little_loops/loops/<old_name>.yaml` → scope = `builtin`

If neither file exists, abort:
```
Error: Loop '<old_name>' not found.
  Checked: .loops/<old_name>.yaml
           scripts/little_loops/loops/<old_name>.yaml
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

Check for an active PID file:
```bash
test -f ".loops/.running/<old_name>.pid" && echo "RUNNING" || echo "OK"
```

If `RUNNING`, abort:
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
- **Scope `builtin`**: `git mv` (file is git-tracked)
  ```
  git mv scripts/little_loops/loops/<old_name>.yaml scripts/little_loops/loops/<new_name>.yaml
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

Search for `loop: <old_name>` (exact bare name, no extension) across all loop YAML files:

- `scripts/little_loops/loops/**/*.yaml` (includes `oracles/`)
- `.loops/*.yaml`

Use Grep with pattern `loop:\s+<old_name>` across those paths. For each match, record an
Edit to replace `loop: <old_name>` with `loop: <new_name>`.

### 5d. Tests (built-in scope only)

Search `scripts/tests/` for all occurrences of the old name:

```
Grep pattern: "<old_name>" across scripts/tests/**/*.py
```

For each match, record an Edit to replace every string occurrence of `"<old_name>"` with
`"<new_name>"` and `"<old_name>.yaml"` with `"<new_name>.yaml"`.

### 5e. Documentation (built-in scope only)

Search for all occurrences of the old name in non-historical docs:

```
Grep pattern: <old_name> across docs/**/*.md, scripts/little_loops/loops/README.md
```

Record an Edit for each file that contains the old name, replacing all occurrences with
`new_name`.

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

TESTS (<N> occurrences):   [builtin only]
  <file>:<line> — "<old_name>" → "<new_name>"
  ...

DOCS (<N> occurrences):    [builtin only]
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

1. **Rename the file** (Bash: `git mv` or `mv`)
2. **Edit `name:` field** in the renamed YAML (Edit tool)
3. **Edit each sub-loop reference** (Edit tool, one file at a time)
4. **Edit test files** (Edit tool, builtin only)
5. **Edit doc files** (Edit tool, builtin only)

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
  EDITED    <test-file> — <N> occurrence(s)   [builtin only]
  EDITED    <doc-file> — <N> occurrence(s)    [builtin only]

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
