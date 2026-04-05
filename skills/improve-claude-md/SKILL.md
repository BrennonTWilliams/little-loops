---
description: |
  Use when the user asks to improve or rewrite CLAUDE.md, restructure instructions using
  <important if> blocks, or increase LLM instruction adherence. Apply the 9-step rewrite
  algorithm to wrap each section in a condition block scoped to when it is relevant.

  Trigger keywords: "improve claude md", "rewrite claude md", "important if blocks",
  "instruction adherence", "restructure claude md", "scope instructions"
argument-hint: "[--dry-run] [--file path]"
allowed-tools:
  - Read
  - Glob
  - Edit
  - Bash(git:*)
arguments:
  - name: flags
    description: "Optional flags: --dry-run (preview without writing), --file <path> (target file)"
    required: false
---

# Improve CLAUDE.md

Rewrite a project's `CLAUDE.md` using `<important if="condition">` XML blocks, improving LLM
instruction adherence by scoping each section to the tasks where it is actually relevant.

## Background

Claude Code injects a system reminder that CLAUDE.md content "may or may not be relevant to your
tasks," which causes Claude to selectively ignore sections. Wrapping instructions in
`<important if="condition">` blocks signals relevance explicitly — Claude attends to the section
only when the condition matches the current task. Foundational context (project identity, directory
map, tech stack) stays **bare** because it is relevant to 90%+ of tasks.

## Arguments

$ARGUMENTS

- **flags** (optional): Modify behavior
  - `--dry-run` — Preview the rewrite plan without modifying any file
  - `--file <path>` — Target a specific CLAUDE.md path (default: `.claude/CLAUDE.md` or `./CLAUDE.md`)

## Algorithm Reference

See `algorithm.md` in this directory for the full condition-example library, step-by-step
decision criteria, and narrow vs. broad condition guidance.

## Process

### Step 0: Parse Flags and Resolve Target File

```bash
FLAGS="${flags:-}"
DRY_RUN=false
FILE_ARG=""

if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
FILE_ARG=$(echo "$FLAGS" | grep -oP '(?<=--file )\S+' || true)

# Default CLAUDE.md resolution
if [[ -z "$FILE_ARG" ]]; then
    if [[ -f ".claude/CLAUDE.md" ]]; then
        FILE_ARG=".claude/CLAUDE.md"
    elif [[ -f "CLAUDE.md" ]]; then
        FILE_ARG="CLAUDE.md"
    else
        echo "Error: no CLAUDE.md found (.claude/CLAUDE.md or ./CLAUDE.md)"
        exit 1
    fi
fi
echo "Target: $FILE_ARG"
echo "Dry run: $DRY_RUN"
```

### Step 1: Read the Target File

Use the Read tool to load the full contents of `$FILE_ARG`.

### Step 2: Parse Into Sections

Identify all top-level sections (`##` headings) and their content. For each section, determine:
- What kind of information it contains
- When that information would actually be relevant to a task
- Whether it falls into the "foundational" or "conditional" category

### Step 3: Apply the 9-Step Rewrite Algorithm

Work through the file section by section, applying each step in order:

**Step 1 — Project Identity**: Keep bare. Never wrap. Always relevant.
- Project name, description, what this codebase does

**Step 2 — Directory Map**: Keep bare. Never wrap.
- The key directory listing (where to find things)
- Condense to essential entries only; remove noise

**Step 3 — Tech Stack**: Keep bare. Condense if verbose.
- Language, major frameworks, config files

**Step 4 — Commands**: Wrap together in a single block.
```xml
<important if="you need to run commands, build, test, lint, or start the project">
[commands table — NEVER omit any command, preserve the exact table]
</important>
```
Hard constraint: **never drop any command**. If a command table exists, it must survive intact.

**Step 5 — Rules and Conventions**: Break apart. Each rule gets its own narrow-condition block.
- Bad: one `<important if="writing code">` block containing 10 rules
- Good: 10 separate blocks, each with a specific condition (see `algorithm.md` for examples)
- Condition must be narrow: "you are adding imports" not "you are writing code"

**Step 6 — Domain Sections**: Wrap each section in its own block.
- Testing patterns → `<important if="you are writing or running tests">`
- API conventions → `<important if="you are working on API endpoints or HTTP handlers">`
- Database patterns → `<important if="you are writing queries or database migrations">`
- Auth conventions → `<important if="you are implementing authentication or authorization">`
- UI components → `<important if="you are building UI components or frontend code">`

**Step 7 — Delete Linter-Territory**: Remove style rules already enforced by the linter/formatter.
- Line length, indentation, import ordering, trailing whitespace, quote style
- These rules create noise; the linter is authoritative
- If a rule says "run `ruff format`" that's a command (Step 4); keep it
- If it says "use 4-space indentation" and ruff enforces this, delete it

**Step 8 — Delete Code Snippets**: Replace with file path references.
- Instead of embedding a 10-line example: "See `src/utils/example.py` for the pattern"
- Keep code snippets only if they are non-obvious one-liners that couldn't be found by reading a file

**Step 9 — Delete Vague Instructions**: Remove non-actionable guidance.
- "Write clean code" → delete
- "Be careful" → delete
- "Follow best practices" → delete
- Keep instructions only if they specify a concrete, verifiable behavior

### Step 4: Generate Diff Summary

After applying the algorithm, output a diff summary showing every change:

```
## Rewrite Summary — $FILE_ARG

### Wrapped in <important if> blocks
+ Step 4 (Commands): wrapped commands table
  Condition: "you need to run commands, build, test, lint, or start the project"
+ Step 5 (Rule): "Use dataclasses for data structures"
  Condition: "you are defining new data models or classes"
+ Step 6 (Testing): Testing patterns section
  Condition: "you are writing or running tests"

### Deleted (linter-territory — Step 7)
- "Use 4-space indentation" (enforced by ruff)
- "Max line length 88" (enforced by ruff)

### Deleted (code snippets replaced with references — Step 8)
- 15-line dataclass example → "See scripts/little_loops/models.py"

### Deleted (vague instructions — Step 9)
- "Write clean, readable code"

### Left bare (foundational)
  Project identity, directory map, tech stack
```

Use `-` prefix for deletions and `+` prefix for additions/wraps.

### Step 5: Apply Changes (if not --dry-run)

```bash
if [[ "$DRY_RUN" == false ]]; then
    # Use the Edit tool to apply the rewritten content to $FILE_ARG
    # Write the full restructured content in a single Edit operation
    echo "✓ Rewrote $FILE_ARG"
else
    echo "DRY-RUN: no changes written. Re-run without --dry-run to apply."
fi
```

Use the **Edit tool** to write the restructured content back to `$FILE_ARG`.
Do not use Bash redirection — use the Edit tool so the change is visible in the review diff.

### Step 6: Final Report

```
## Result

  File: $FILE_ARG
  Mode: [LIVE | DRY-RUN]

  Sections wrapped:   N
  Rules broken out:   N
  Lines deleted:      ~N (linter: N, snippets: N, vague: N)
  Foundational bare:  N sections

  [WRITTEN] Changes applied to $FILE_ARG
  -- or --
  [DRY-RUN] No changes written. Re-run without --dry-run to apply.
```
