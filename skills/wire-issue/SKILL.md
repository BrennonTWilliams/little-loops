---
description: |
  Use when a refined issue is missing integration points, incomplete wiring in the implementation plan, or related files that need updating due to the planned changes. Traces all callers, importers, config references, doc mentions, test coverage, and CLI/registration hooks that an implementation must touch.

  Trigger keywords: "wire issue", "missing integration points", "complete the wiring", "fill integration map", "trace dependencies", "find all callers", "wiring pass", "integration gaps"
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(find:*)
  - Bash(ls:*)
  - Bash(wc:*)
  - Bash(git:*)
  - Bash(ll-issues:*)
  - Agent
---

# Wire Issue

A post-refinement pass that traces the full codebase wiring for an issue's planned changes. Where `/ll:refine-issue` fills knowledge gaps broadly (root cause, patterns, behavior), this skill focuses on **completeness of the Integration Map** and **wiring in the implementation plan** — finding every file that must change, every caller that may break, every config key, doc section, or test that needs touching.

## When to Use

Run after `/ll:refine-issue` when you suspect the integration map is incomplete:
- Callers and importers are missing or underspecified
- Implementation Steps list files to change but not what calls them
- Config, docs, or CLI registrations that reference the changed area are absent
- Tests that cover the affected code aren't listed
- Side-effect files (plugin manifests, __init__.py exports, CLAUDE.md listings) are not mentioned

## Arguments

```
/ll:wire-issue [<issue-id>] [--auto] [--dry-run]
```

| Flag | Meaning |
|------|---------|
| `--auto` | Non-interactive mode: write findings without prompting |
| `--dry-run` | Preview what would be added without modifying the issue file |

**Examples:**
```bash
/ll:wire-issue FEAT-948
/ll:wire-issue ENH-277 --auto
/ll:wire-issue BUG-042 --auto --dry-run
```

---

## Phase 1: Parse Arguments

```
ISSUE_ID = ""
AUTO_MODE = false
DRY_RUN = false

# Auto-enable in automation contexts
if ARGUMENTS contains "--dangerously-skip-permissions": AUTO_MODE = true

# Explicit flags
if ARGUMENTS contains "--auto": AUTO_MODE = true
if ARGUMENTS contains "--dry-run": DRY_RUN = true

# Extract issue ID (first non-flag token)
for token in ARGUMENTS:
    if not starts with "--": ISSUE_ID = token; break

if ISSUE_ID is empty:
    print "Error: issue_id is required"
    print "Usage: /ll:wire-issue [ISSUE_ID] [--auto] [--dry-run]"
    exit 1
```

---

## Phase 2: Locate Issue File

```bash
FILE=""
for dir in {{config.issues.base_dir}}/*/; do
    if [ "$(basename "$dir")" = "{{config.issues.completed_dir}}" ] || \
       [ "$(basename "$dir")" = "{{config.issues.deferred_dir}}" ]; then
        continue
    fi
    if [ -d "$dir" ]; then
        FILE=$(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null \
               | grep -E "[-_]${ISSUE_ID}[-_.]" | head -1)
        if [ -n "$FILE" ]; then echo "Found: $FILE"; break; fi
    fi
done

if [ -z "$FILE" ]; then
    echo "Error: Issue $ISSUE_ID not found in active issues"
    exit 1
fi
```

---

## Phase 3: Extract Existing Wiring Context

Read the full issue file and extract:

1. **Planned change targets** — files already listed in "Files to Modify" or "Integration Map"
2. **Already-known callers** — files in "Dependent Files (Callers/Importers)"
3. **Known tests** — files in any "Tests" subsection of Integration Map
4. **Known docs** — files in any "Documentation" subsection
5. **Key symbols** — function names, class names, CLI flags, config keys, module names that the planned changes will touch
6. **Implementation Steps** — what phases are already described

Produce a structured summary:

```
EXISTING_WIRING:
  files_to_modify: [list of paths already in the issue]
  known_callers: [list]
  known_tests: [list]
  known_docs: [list]
  key_symbols: [function/class/module names extracted from issue text]
  implementation_steps_count: N
```

**Key symbol extraction rules:**
- Scan all sections for backtick-quoted names: `foo.py`, `ClassName`, `function_name()`, `--flag`, `config_key`
- Extract module names from `import` or `from X import` snippets if present
- Extract CLI command names from usage examples
- These symbols drive the wiring search in Phase 4

---

## Phase 4: Run Wiring Research (3 Parallel Agents)

Spawn all 3 agents in a **single message** with multiple Agent tool calls.

### Agent 1: Caller and Importer Tracer (codebase-locator)

```
Use Agent tool with subagent_type="ll:codebase-locator"

Prompt:
Trace every file that imports, calls, or depends on the code being changed by this issue.

Issue: {{ISSUE_ID}} — {{issue title}}
Key symbols to trace: {{key_symbols from Phase 3}}
Files already known to be modified: {{files_to_modify from Phase 3}}
Already-known callers: {{known_callers from Phase 3}}

Find:
1. Direct importers — files that `import` or `from X import` any key symbol
2. Callers — files that call any function/class from the key symbols
3. Test files — any test file that covers or exercises code in files_to_modify
4. Plugin/manifest registrations — plugin.json, __init__.py exports, commands/ listings, skills/ directories, agents/ listings, hooks/hooks.json that reference the affected files or symbols
5. Config files — ll-config.json, settings.json, .claude/CLAUDE.md entries that mention affected areas

Return file paths grouped by:
- Direct importers
- Callers / consumers
- Test files
- Registration / manifest files
- Config files

Exclude files already in the "already known" lists.
```

### Agent 2: Side-Effect Surface Tracer (codebase-analyzer)

```
Use Agent tool with subagent_type="ll:codebase-analyzer"

Prompt:
Analyze the full side-effect surface of the planned changes in this issue — every place that will need to change beyond the primary implementation files.

Issue: {{ISSUE_ID}} — {{issue title}}
Primary files being changed: {{files_to_modify from Phase 3}}
Key symbols: {{key_symbols from Phase 3}}

Analyze:
1. Public API / interface contracts — if any public function/class signature changes, who consumes it?
2. Documentation coupling — which doc files (docs/*.md, CLAUDE.md, README.md, CONTRIBUTING.md, commands/*.md, skills/*/SKILL.md) mention the changed functions, commands, or config keys?
3. CLI and command coupling — if any CLI flags or commands change, what references them in help text, docs, or other commands?
4. Error message / log coupling — if error messages or log labels change, are there tests that assert on those strings?
5. Schema / config coupling — if config keys or schema change, what reads or validates those keys?

Return analysis with specific file:line references for each coupling found.
Exclude files already known from the issue.
```

### Agent 3: Test Gap Finder (codebase-pattern-finder)

```
Use Agent tool with subagent_type="ll:codebase-pattern-finder"

Prompt:
Find existing test coverage and identify test gaps for the planned changes in this issue.

Issue: {{ISSUE_ID}} — {{issue title}}
Files being changed: {{files_to_modify from Phase 3}}
Already-known tests: {{known_tests from Phase 3}}

Find:
1. Existing test files that cover the files being changed (by naming convention or import analysis)
2. Test patterns used for similar changes elsewhere (so new tests follow conventions)
3. Tests that will likely break due to the planned changes (call the changed functions with the old API)
4. Integration or end-to-end test files that exercise the affected functionality
5. If no tests exist for the changed area, show the test pattern to follow from the closest similar test file

Return examples with file:line references.
Distinguish between: existing tests to update vs. new tests to write vs. tests that may break.
```

#### Wait for ALL 3 agents to complete before proceeding.

---

## Phase 5: Diff — Find Missing Wiring

Compare the 3 agents' findings against `EXISTING_WIRING` extracted in Phase 3.

For each category, compute what's NEW (not already in the issue):

```
MISSING_WIRING:
  callers_to_add: [files from Agent 1 callers not in known_callers]
  importers_to_add: [files from Agent 1 importers not in files_to_modify or known_callers]
  tests_to_add: [files from Agent 1 + 3 tests not in known_tests]
  tests_to_update: [tests Agent 3 flagged as likely breaking]
  registrations_to_add: [manifest/plugin/config files not in files_to_modify]
  docs_to_add: [doc files from Agent 2 not in known_docs]
  cli_coupling: [CLI/command files from Agent 2 that need updating]
  schema_coupling: [config/schema files from Agent 2 that need updating]
  new_impl_steps: [phases that should be added to Implementation Steps based on missing files]
```

**Signal-to-noise filter** — skip adding a file if:
- The file is in `completed/` (already done)
- The file is an auto-generated artifact (e.g., `*.pyc`, `__pycache__`)
- The coupling is a test that already explicitly checks "this won't change" (test intent mismatch)

---

## Phase 6: Determine Whether to Proceed

If `MISSING_WIRING` is entirely empty across all categories:

```
No missing wiring found — the Integration Map and Implementation Steps are already complete.

Files already covered: [list existing coverage]
```

Exit cleanly without modifying the issue.

---

## Phase 7: Present Findings (Interactive Mode Only)

**Skip if `AUTO_MODE` is true — proceed directly to Phase 8.**

Display a summary of what was found:

```
Wiring Gaps Found for {{ISSUE_ID}}:

  Callers/importers missing from Integration Map: N
  Registration/manifest files missing: N
  Docs that need updating: N
  Tests to add or update: N
  Implementation Steps gaps: N
```

Show the specific findings grouped by category, then use `AskUserQuestion`:

```yaml
questions:
  - question: "Found N wiring gaps. Should I update the issue with these findings?"
    header: "Apply wiring update"
    multiSelect: false
    options:
      - label: "Yes, update the Integration Map and Implementation Steps"
        description: "Adds missing callers, docs, tests, and registrations to the issue"
      - label: "No, just show me the findings"
        description: "Display the gaps without modifying the file"
```

If the user declines, print the full findings and exit without modifying.

---

## Phase 8: Update Issue File

**Skip all file modifications if `DRY_RUN` is true.**

Update the issue using the Edit tool with the following rules:

### 8a: Integration Map Updates

Locate the `## Integration Map` section (or `### Files to Modify` subsection). Add missing entries:

**Callers / importers** — append to the "Dependent Files (Callers/Importers)" subsection (create it if absent):

```markdown
### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `path/to/caller.py:42` — calls `affected_function()` [Agent 1 finding]
- `path/to/importer.py:5` — imports `affected_module` [Agent 1 finding]
```

**Registration / manifest files** — append to "Files to Modify" (these must be edited as part of the implementation):

```markdown
- `path/to/plugin.json` — register new skill/command entry [Agent 1 finding]
- `path/to/__init__.py` — export new public symbol [Agent 1 finding]
```

**Documentation** — append to a "Documentation" subsection:

```markdown
### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/relevant.md:23` — describes `affected_function()`, needs updating [Agent 2 finding]
- `commands/some-command.md` — mentions the old CLI flag, needs updating [Agent 2 finding]
```

**Tests** — append to a "Tests" subsection:

```markdown
### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `tests/test_affected.py` — existing coverage, update for new behavior [Agent 3 finding]
- `tests/test_new_feature.py` — new test file needed, follow pattern in `tests/test_similar.py` [Agent 3 finding]
- `tests/test_integration.py:88` — calls old API, will break — update [Agent 3 finding]
```

**Config / schema** — append to a "Configuration" subsection:

```markdown
### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — add new config key definition [Agent 2 finding]
- `.ll/ll-config.json` — update default values section [Agent 2 finding]
```

### 8b: Implementation Steps Updates

If `new_impl_steps` is non-empty, append a wiring-specific phase to the existing `## Implementation Steps` section:

```markdown
### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

N. Update `path/to/caller.py` — adjust calls to `changed_function()` with new signature
N+1. Update `tests/test_affected.py` — adapt existing tests to new behavior
N+2. Register in `plugin.json` — add entry for new skill/command
N+3. Update `docs/relevant.md` — reflect changed behavior in documentation
```

### 8c: Preservation Rule

**Do NOT overwrite** any existing content. Only append. Mark all wiring additions with:

```
_Wiring pass added by `/ll:wire-issue`:_
```

---

## Phase 9: Append Session Log

```bash
ll-issues append-log <path-to-issue-file> /ll:wire-issue
```

If `ll-issues` is not available, append manually:

```
- `/ll:wire-issue` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

Stage the updated file:

```bash
git add "{{config.issues.base_dir}}/[category]/[filename]"
```

---

## Phase 10: Output Report

```
================================================================================
WIRE ISSUE: {{ISSUE_ID}}
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH]
- Title: [title]
- Mode: [Interactive | Auto] [--dry-run]

## WIRING RESEARCH SUMMARY
- Agents run: Caller Tracer, Side-Effect Tracer, Test Gap Finder
- Key symbols traced: [N] (e.g., function_name, ClassName, --flag)

## MISSING WIRING FOUND

| Category | Count | Files |
|----------|-------|-------|
| Callers/Importers | N | [brief list] |
| Registrations/Manifests | N | [brief list] |
| Documentation | N | [brief list] |
| Tests (update) | N | [brief list] |
| Tests (new) | N | [brief list] |
| Config/Schema | N | [brief list] |
| Impl Step gaps | N | [brief descriptions] |

## INTEGRATION MAP CHANGES

### Added to Dependent Files
- `path/to/caller.py:42` — calls `affected_fn()`
...

### Added to Files to Modify
- `plugin.json` — registration entry needed
...

### Added to Documentation
- `docs/api.md:15` — describes changed interface
...

### Added to Tests
- `tests/test_affected.py` — update for new behavior
- `tests/test_new.py` — new test file needed
...

## IMPLEMENTATION STEPS CHANGES
- [N] new steps added to Wiring Phase

## FILE STATUS
- [Modified | Not modified (--dry-run | nothing to add)]

## NEXT STEPS
- Run `/ll:confidence-check {{ISSUE_ID}}` to re-evaluate readiness with full wiring
- Run `/ll:ready-issue {{ISSUE_ID}}` to validate the enriched issue
- Run `/ll:manage-issue` to implement

================================================================================
```

---

## Integration

### Pipeline Position

```
/ll:capture-issue → /ll:format-issue → /ll:refine-issue → /ll:wire-issue → /ll:ready-issue → /ll:manage-issue
```

- **Before**: `/ll:refine-issue` — fills knowledge gaps (root cause, patterns, behavior)
- **After**: `/ll:ready-issue` or `/ll:confidence-check` — validates the now-complete issue

### When to Use vs. Related Commands

| Skill | Purpose | Gap type addressed |
|-------|---------|-------------------|
| `refine-issue` | Codebase research to fill implementation knowledge | Root cause, patterns, current behavior |
| `wire-issue` | Trace all wiring touchpoints the implementation must hit | Missing callers, registrations, docs, tests |
| `ready-issue` | Validate accuracy of all claims in the issue | Correctness, stale references |
| `confidence-check` | Evaluate readiness and implementation risk | Readiness score, complexity, ambiguity |

`wire-issue` is specifically for the "I refined the issue but the implementation plan still doesn't account for all the files that need to change" problem.
