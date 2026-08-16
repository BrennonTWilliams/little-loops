---
name: wire-issue
description: Use when a refined issue is missing integration points or wiring in the implementation plan.
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
  - Bash(ll-code:*)
  - Agent
metadata:
  short-description: Use when a refined issue is missing integration points or wiring in the implemen
trigger_fixtures:
  should_fire:
    - "this refined issue is missing integration points and wiring in the implementation plan"
    - "add missing wiring and integration points to this issue's plan"
  should_not_fire:
    - "fix this issue's template structure"
    - "select the winning implementation option"
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
if ARGUMENTS contains "--dangerously-skip-permissions" or env LL_NON_INTERACTIVE is set or env DANGEROUSLY_SKIP_PERMISSIONS is set: AUTO_MODE = true

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
FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)

if [ -z "$FILE" ]; then
    echo "Error: Issue $ISSUE_ID not found"
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
```

**Replacement parity (ENH-3045)**: also extract `REPLACED_ARTIFACTS` — files
the issue names (in Summary/Proposed Solution/Files to Modify) alongside a
replacement keyword (delete/remove/replace/rewrite/supersede/delegate) that
resolve to a real tracked file. Full extraction procedure and the Phase 4/8a
work it drives: [behavior-parity.md](behavior-parity.md).

**Key symbol extraction rules:**
- Scan all sections for backtick-quoted names: `foo.py`, `ClassName`, `function_name()`, `--flag`, `config_key`
- Extract module names from `import` or `from X import` snippets if present
- Extract CLI command names from usage examples
- These symbols drive the wiring search in Phase 4

---

## Phase 3.5: Static Coupling Layer

Run `ll-issues decisions list --type=coupling --format=json 2>/dev/null`. Skip silently if unavailable or if no entries match `files_to_modify`. Infer change archetype from the issue title (`add-cli-command`, `add-config-key`, `add-event-type`, …) and load that bundle via `--archetype`; merge results. Collect matched `then_check` targets into `MUST_AUDIT` (tier: `hard`→blocking in agent prompts + Implementation Steps; `soft`→advisory; `fyi`→report only). Prepend `MUST_AUDIT` to Phase 4 agent prompts. Full procedure in [static-coupling-layer.md](static-coupling-layer.md).
---
## Phase 3.6: Graph-Accelerated Discovery

Seed Phase 4 candidates (callers, importers, impacted files) from `ll-code --json` before manual tracing, then confirm each hit with one targeted Grep at its `path:line`. Three safety rules, verbatim: **(1) silent fallback** — if `ll-code --json status` reports `available: false` or a query exits `2`, skip and run the current Phase 4 flow (zero regression); **(2) confirm-before-map** — every positive hit is a hint, verified by one Grep before it enters the Integration Map; **(3) never trust negatives** — exit `1` ("no callers") is never trusted alone, run the current exploratory pass for that target. If `freshness == "stale"`, treat all candidates as leads and widen confirmation. Confirmed candidates feed Phase 4 Agent 1's "Already-known callers:" and "Key symbols to trace:" slots. Full procedure in [graph-discovery-layer.md](graph-discovery-layer.md).
---

## Phase 3.7: Prose Dependency Gate (FEAT-2849) — see [prose-dependency-gate.md](prose-dependency-gate.md).
---
## Phase 4: Run Wiring Research (3 Parallel Agents)

Spawn all 3 agents in a **single message** with multiple Agent tool calls, each with `run_in_background: false`, and wait for their results in this same turn before proceeding.

### Agent 1: Caller and Importer Tracer (codebase-locator)

```
Use Agent tool with subagent_type="ll:codebase-locator"

Prompt:
Trace every file that imports, calls, or depends on the code being changed by this issue.

Issue: {{ISSUE_ID}} — {{issue title}}
Key symbols to trace: {{key_symbols from Phase 3}}
Files already known to be modified: {{files_to_modify from Phase 3}}
Already-known callers: {{known_callers from Phase 3}}
{{MUST_AUDIT block from Phase 3.5 if non-empty}}

Find:
1. Direct importers — files that `import` or `from X import` any key symbol
2. Callers — files that call any function/class from the key symbols
3. Test files — any test file that covers or exercises code in files_to_modify
4. Plugin/manifest registrations — plugin.json, __init__.py exports, commands/ listings, skills/ directories, agents/ listings, hooks/hooks.json that reference the affected files or symbols
5. Config files — ll-config.json, settings.json, .claude/CLAUDE.md entries that mention affected areas
6. If `REPLACED_ARTIFACTS` is non-empty: locate every behavior of each replaced file, and before concluding "no existing implementation exists" for any capability, search by capability (input/output shape, callers of the shared primitive) rather than by algorithm name — see [behavior-parity.md](behavior-parity.md). State what was searched in the resulting claim.
7. Conditional branches (ENH-3050): if the plan states a conditional fallback naming an alternate implementation target ("if X overflows, do Y", "otherwise extract to", "fall back to"), wire Y's touchpoints as first-class.

Return file paths grouped by:
- Direct importers
- Callers / consumers
- Test files
- Registration / manifest files
- Config files

Exclude files already in the "already known" lists.

IMPORTANT: If you see "File unchanged since last read" when reading a file,
do NOT re-read it — use the content from your earlier read.
If a search returns results identical to a prior search, do NOT repeat it.
Stop and synthesize your findings immediately.

Track which files and search patterns you have already queried.
Do NOT re-query the same file path or the same grep pattern a second time.
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
6. Gate consumers (ENH-3050): if the change adds/alters a field in a CLI's `--format json` output or an exit-code condition, grep the CLI invocation string (not the Python symbol) across `scripts/little_loops/loops/`, `hooks/`, `skills/`, `commands/`, `docs/`.

Return analysis with specific anchor-based references (function/class names) for each coupling found.
Exclude files already known from the issue.

IMPORTANT: If you see "File unchanged since last read" when reading a file,
do NOT re-read it — use the content from your earlier read.
If a search returns results identical to a prior search, do NOT repeat it.
Stop and synthesize your findings immediately.

Track which files and search patterns you have already queried.
Do NOT re-query the same file path or the same grep pattern a second time.
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
6. Same capability-search and claim-grounding requirement as Agent 1 — see [behavior-parity.md](behavior-parity.md)

Return examples with anchor-based references (function/class names).
Distinguish between: existing tests to update vs. new tests to write vs. tests that may break.

IMPORTANT: If you see "File unchanged since last read" when reading a file,
do NOT re-read it — use the content from your earlier read.
If a search returns results identical to a prior search, do NOT repeat it.
Stop and synthesize your findings immediately.

Track which files and search patterns you have already queried.
Do NOT re-query the same file path or the same grep pattern a second time.
```

#### Wait for ALL 3 agents' results synchronously in this same turn before proceeding.

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
  gate_consumers: [loop/hook/skill/command/doc files reading a changed CLI JSON field or exit code]
  conditional_branches: [touchpoints of an alternate implementation target named by a conditional fallback]
  new_impl_steps: [phases that should be added to Implementation Steps based on missing files]
```

**Signal-to-noise filter** — skip adding a file if:
- The file has `status: done` (already done)
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

**Callers / importers** — append to the "Dependent Files (Callers/Importers)" subsection (create it if absent). `gate_consumers` and `conditional_branches` (ENH-3050) also route here, not to a new heading:

```markdown
### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `path/to/caller.py` — calls `affected_function()` in `handle_request()` [Agent 1 finding]
- `path/to/importer.py` — imports `affected_module` in `module_init()` [Agent 1 finding]
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
- `docs/relevant.md` — describes `affected_function()` under section "Function Reference" [Agent 2 finding]
- `commands/some-command.md` — mentions the old CLI flag, needs updating [Agent 2 finding]
```

**Tests** — append to a "Tests" subsection:

```markdown
### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `tests/test_affected.py` — existing coverage, update for new behavior [Agent 3 finding]
- `tests/test_new_feature.py` — new test file needed, follow pattern in `tests/test_similar.py` [Agent 3 finding]
- `tests/test_integration.py` — calls old API in `test_handle_request()`, will break — update [Agent 3 finding]
```

**Behavior Parity** (ENH-3045) — when `REPLACED_ARTIFACTS` (Phase 3) is
non-empty, append a `### Behavior Parity` subsection — bare heading, one
table per issue, replaced artifact as a table column (never heading text).
Skip if `REPLACED_ARTIFACTS` is empty or `behavior_parity_not_applicable:
true` is set. Full template and rationale: [behavior-parity.md](behavior-parity.md).

**Config / schema** — append to a "Configuration" subsection:

```markdown
### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — add new config key definition [Agent 2 finding]
- `.ll/ll-config.json` — update default values section [Agent 2 finding]
```

### 8b: Implementation Steps Updates

If `new_impl_steps` is non-empty, append a wiring-specific phase to the existing `## Implementation Steps` section.
Use plain `-` bullets for these entries. Do **not** continue the parent
list's numbering — the Wiring Phase is a distinct set of touchpoints and
makes no claim about position in the parent sequence.

```markdown
### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `path/to/caller.py` — adjust calls to `changed_function()` with new signature
- Update `tests/test_affected.py` — adapt existing tests to new behavior
- Register in `plugin.json` — add entry for new skill/command
- Update `docs/relevant.md` — reflect changed behavior in documentation
```

### 8c: Preservation Rule & Contradiction Carve-Out

**Do NOT overwrite** any existing content. Only append. Mark all wiring additions with:

```
_Wiring pass added by `/ll:wire-issue`:_
```

**Contradiction-marking carve-out** (ported from ENH-2995, ENH-3049): a narrow
exception — when content **this pass is appending** contradicts a line in
`## Implementation Steps`, `### Files to Modify`, or `## Acceptance Criteria`,
annotate that line instead of leaving the contradiction silent. Never
`## Summary`, `## Motivation`, `## Proposed Solution`, or `### Option …` /
`### Decision Rationale` prose.

- **Provenance (wire-specific)**: fires only on content this pass is
  appending — an Integration Map bullet or a Wiring Phase entry — never from
  re-reading a prior pass's already-appended blocks. Wire has no
  `### Codebase Research Findings` heading to key on.
- **Marker text and placement**: insert `> ⚠ Superseded — <reason ≤10 words>`
  as a new line immediately below the contradicted line, indented to that
  line's content column (3 spaces under `1. `, 2 under `- `) — never column 0.
- **Idempotent**: skip if the line below already contains `⚠ Superseded`.
- **No marker-removal right for wire**: markers carry no provenance, so wire
  cannot distinguish its own markers from refine's. Wire may only **insert**
  markers and must **never delete** one — that right stays with
  `/ll:refine-issue` alone.

---

## Phase 9: Append Session Log

```bash
ll-issues append-log <path-to-issue-file> /ll:wire-issue
```

If `ll-issues` is not available, append manually:

```
- `/ll:wire-issue` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

```bash
git add "{{config.issues.base_dir}}/[category]/[filename]"
```

After staging, extract learning targets per [learning-targets.md](learning-targets.md) (identify deps, check registry with `--stale-aware`, union-merge `learning_tests_required`, emit summary). Skip if `testable: false` or `--dry-run`.

---

## Phase 10: Output Report

See [output-report.md](output-report.md) for the verbatim report template — emit it with the bracketed values substituted.

---

## Integration

### Pipeline Position

```
/ll:capture-issue → /ll:format-issue → /ll:refine-issue → /ll:decide-issue → /ll:wire-issue → /ll:ready-issue → /ll:manage-issue
```

- **Before**: `/ll:decide-issue` — selects among competing options if `decision_needed: true` was set
- **After**: `/ll:ready-issue` or `/ll:confidence-check` — validates the now-complete issue

### When to Use vs. Related Commands

| Skill | Purpose | Gap type addressed |
|-------|---------|-------------------|
| `refine-issue` | Codebase research to fill knowledge gaps | Root cause, patterns, current behavior |
| `ready-issue` | Validate accuracy of all claims in the issue | Correctness, stale references |
| `confidence-check` | Evaluate readiness and implementation risk | Readiness score, complexity, ambiguity |

Use `wire-issue` specifically when the implementation plan doesn't account for all files that need to change.
