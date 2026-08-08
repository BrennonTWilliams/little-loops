---
description: Refine issue files with codebase-driven research to fill knowledge gaps needed for implementation
argument-hint: "[issue-id]"
allowed-tools:
  - Read
  - Glob
  - Edit(.issues/**)
  - Task
  - Bash(git:*, ll-issues:*)
  - Bash(ll-history-context:*)
  - Bash(ll-code:*)
arguments:
  - name: issue_id
    description: Issue ID to refine (e.g., BUG-071, FEAT-225, ENH-042)
    required: true
  - name: flags
    description: "Optional flags: --auto (non-interactive), --dry-run (preview)"
    required: false
---

# Refine Issue

Enrich issue files with codebase-driven research findings. Unlike `/ll:format-issue` (which aligns structure) or `/ll:ready-issue` (which validates accuracy), this command **researches the codebase** to identify and fill knowledge gaps needed for successful implementation.

The core workflow: read the issue, research the codebase, identify what an implementer needs to know that isn't in the issue, then fill those gaps with actual findings (file paths, function signatures, behavioral analysis).

## Register: Constraints, Not Recipes

Everything this command deposits is read later by an implementer — usually a
headless automation session with no human present. What you write becomes the
ceiling on what that session can produce, so the register matters as much as
the content.

**Deposit facts and constraints. Do not deposit a route.**

| Write this | Not this | Why |
|---|---|---|
| "The new flag must round-trip through `parse_args()`; `test_parser.py::TestFlagParsing` covers the existing contract and must keep passing" | "1. Modify `parse_args()` to handle the new flag. 2. Add a test to `TestFlagParsing`." | An ordered recipe caps the implementation at the route *research time* imagined. A constraint says what must be true and leaves the route open. |
| "This codebase registers subcommands through the `_add_*_parser` helper (`cli.py:412`)" | "Follow the pattern at `cli.py:412`" | A cited example becomes something to **copy**, including that file's accidents. Naming the *rule* the example demonstrates transfers the convention without the clone. |
| "`emit_event()` has 14 callers, listed below; all assume the payload dict is never mutated" | "Update all 14 callers" | The invariant is the durable fact. Whether all 14 need touching is an implementation judgment. |

This does **not** mean writing less, or writing vaguely. Integration Map,
Root Cause, callers/dependents, and test coverage are exactly the constraints
an implementer cannot cheaply rediscover — research them hard and state them
precisely, with real paths and anchors. The shift is from *"do it this way"*
to *"here is the ground truth, and here is what must still be true when you
are done."*

Two places this bites hardest:

- **`## Implementation Steps`** — the section most prone to becoming a recipe.
  Prefer phrasing each entry as an outcome plus its verification, not an edit
  instruction. Keep concrete file references; drop the imperative sequencing
  where the order is not actually forced.
- **Pattern-finder output** — state the convention being upheld and cite the
  file as *evidence for the convention*, never as a template to reproduce.

Anything concrete deposited here will be treated as something to copy rather
than something to learn from. Where you want judgment applied, describe the
property you need rather than handing over an instance of it.

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Source dir**: `{{config.project.src_dir}}`
- **Status enum**: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled` — see `.claude/CLAUDE.md` § Issue File Format for full enum and forbidden synonyms.

## Arguments

$ARGUMENTS

- **issue_id** (required): Issue ID to refine (e.g., BUG-071, FEAT-225, ENH-042)

- **flags** (optional): Command behavior flags
  - `--auto` - Non-interactive mode: fill gaps with research findings without prompting
  - `--dry-run` - Preview what research would produce without modifying the issue file
  - `--gap-analysis` - Additive-only mode: inventory existing coverage, detect stale references and missing sections, apply only additive changes — never removes content (default for new runs)
  - `--full-rewrite` - Full-rewrite mode (legacy behavior): rewrites sections with research findings; use when you want a complete enrichment pass

## Process

### 0. Parse Flags

```bash
ISSUE_ID="${issue_id:-}"
FLAGS="${flags:-}"
AUTO_MODE=false
DRY_RUN=false
GAP_ANALYSIS=false
FULL_REWRITE=false

# Auto-enable auto mode in automation contexts
if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${LL_NON_INTERACTIVE:-}" ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi

if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
if [[ "$FLAGS" == *"--gap-analysis"* ]]; then GAP_ANALYSIS=true; fi
if [[ "$FLAGS" == *"--full-rewrite"* ]]; then FULL_REWRITE=true; fi

if [[ -z "$ISSUE_ID" ]]; then
    echo "Error: issue_id is required"
    echo "Usage: /ll:refine-issue [ISSUE_ID] [--auto] [--dry-run]"
    exit 1
fi
```

### 1. Locate Issue File

```bash
# Support both issue ID and explicit file path
if [[ "$ISSUE_ID" == *"/"* ]] || [[ "$ISSUE_ID" == *.md ]]; then
    if [ -f "$ISSUE_ID" ]; then
        FILE="$ISSUE_ID"
    else
        echo "WARNING: File not found at path: $ISSUE_ID"
        echo "Falling back to ID search..."
    fi
fi

# Search for issue file by ID
if [ -z "$FILE" ]; then
    FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)
fi

if [ -z "$FILE" ]; then
    echo "Error: Issue $ISSUE_ID not found"
    exit 1
fi
```

### 2. Analyze Issue Content

1. Read the issue file completely
2. Parse frontmatter (discovered_date, discovered_by, etc.)
3. Identify issue type from filename or ID prefix (BUG/FEAT/ENH/EPIC)
4. Extract existing sections and their content
5. **Extract key concepts** for research:
   - File paths mentioned or implied
   - Function/class/module names
   - Error messages or behavioral descriptions
   - Feature/component names
   - Configuration keys or CLI flags

### 2.5 — Query Historical Context

Run:

```bash
HIST=$(ll-history-context {{issue_id}} 2>/dev/null || true)
```

If `$HIST` is non-empty, include the output as a `## Historical Context` section in the prompt context for Step 5a gap-filling. Cap: already enforced by the CLI (5 rows max). If DB is missing or no matches, proceed without the section.

### 3. Research Codebase

Spawn parallel sub-agents to gather comprehensive context about the issue's subject matter — but only the ones the issue does not already answer.

#### 3.0 Triage the research axes first (ENH-2971)

Each agent below covers one research axis. An issue that already cites resolving, current references for an axis does not need that axis re-derived — and on a re-refine, re-deriving it is the dominant cost. Ask before spawning:

```bash
if [ "$FULL_REWRITE" = true ]; then
    TRIAGE=""   # a full rewrite does not trust what is already in the file
else
    TRIAGE=$(ll-issues research-triage "${ISSUE_ID}" --json 2>/dev/null || true)
fi
```

- **`--full-rewrite`**: skip triage entirely and spawn all 3. Triage applies on **every other path**, including plain `--auto` — that is the dominant call site, and gating on `--gap-analysis` alone would exempt most invocations.
- **Empty or unparseable `$TRIAGE`** (CLI missing, failed, any reason): spawn all 3. Fail open — the cost of failing open is today's behavior, the cost of failing closed is a silently under-researched issue.

`$TRIAGE` is a three-key object; each value has `covered` (bool) and `evidence` (string):

```json
{
  "locator":        {"covered": true,  "evidence": "Integration Map → commands/refine-issue.md"},
  "analyzer":       {"covered": false, "evidence": ""},
  "pattern_finder": {"covered": false, "evidence": ""}
}
```

**Spawn exactly one Task per axis whose `covered` is `false`** — Agent 1 for `locator`, Agent 2 for `analyzer`, Agent 3 for `pattern_finder`. Spawn them in a SINGLE message with multiple Task tool calls, and wait for their results in this same turn before proceeding. Do not spawn an agent for a covered axis, and do not substitute your own judgment for the triage verdict: it is computed from resolving file references and their change times, which you cannot check as cheaply or as reliably by reading.

A `covered` verdict already accounts for staleness — an axis whose referenced files changed after this issue's most recent `/ll:refine-issue` Session Log entry comes back `covered: false` with an `evidence` string naming the stale path. So a covered axis means "resolving *and* current", not merely "mentioned".

On a project where the Program Design gate is active for this issue (BUG-3003), `$TRIAGE` also folds in a Program Design gate override: when the `## Program Design` section is missing, empty, boilerplate, or graded non-specific, `analyzer` comes back `covered: false` regardless of what Root Cause/Current Behavior evidence — with `evidence` naming the gate as the reason. This exists so a repeatedly-deferred, already-refined issue re-spawns Agent 2 and re-reaches Step 5a instead of silently no-opping on the section Step 6.7's gate is about to fail again.

#### 3.1 Zero unmet axes — the no-op refine

If **every** axis is `covered`, spawn nothing and **skip Steps 4, 5a, and 5b entirely**. There are no research findings, and Step 4/5a's instructions ("using the research findings from Step 3", "fill gaps with research findings") would otherwise read as an invitation to write enrichment from nothing — a fabrication risk strictly worse than the wasted agent calls this triage removes.

On a project where the Program Design gate is active, this branch cannot be reached while the section is missing or non-specific — Step 3.0's override forces `analyzer` unmet. The no-op path stays entirely normal on unstamped and grandfathered projects, where the gate is inactive and the override never fires.

Proceed directly to Step 5c (if `--gap-analysis`), then Steps 6, 6.5, and 6.7. Still append the Session Log entry (Step 6.5), and report the no-op explicitly, naming what satisfied each axis:

```
No research needed — all three axes already covered:
  locator        — [evidence]
  analyzer       — [evidence]
  pattern_finder — [evidence]
Issue left unchanged.
```

A refine that correctly does nothing must still be observable as having run, or a caller cannot distinguish "already enriched" from "refine failed silently".

#### 3.05 Seed the agents from the code graph (ENH-3098)

Before dispatching the agent wave, seed it from the `ll-code` query surface so the
agents *confirm and extend* known structural facts instead of rediscovering them
with open-ended Grep sweeps.

**Read [`docs/guides/GRAPH_DISCOVERY_GUIDE.md`](../docs/guides/GRAPH_DISCOVERY_GUIDE.md)
and follow its procedure, contract, three safety rules, and staleness policy.** The
rules there are binding, not advisory — in particular, a hit is a lead until one
targeted Grep confirms it at its `path:line`, and exit `1` ("no callers") is never
trusted alone.

Skip this step entirely when: Step 3.1 applied (nothing to seed), or the provider is
unavailable (silent fallback — the agent wave runs exactly as it does today).

**Targets** are the symbols and files the issue already names — its `## Integration Map`
→ Files to Modify, Root Cause anchors, and any `path:line` references in the
description. If the issue names no concrete target, skip this step; deriving targets
is the locator's job, not this step's.

**Which axes get seeds:**

| Axis | Seeded with | Rationale |
|---|---|---|
| `locator` (Agent 1) | `importers-of`, `impact-of`, `defines` | Candidate file set to confirm and extend |
| `analyzer` (Agent 2) | `callers-of`, `callees-of` | Concrete call chain to trace |
| `pattern_finder` (Agent 3) | *nothing* | Needs semantic similarity ("how do we usually do X"), which graph edges do not express — leave unseeded |

Seed only the agents Step 3.0 actually spawns. Querying for a covered axis spends
the budget the triage exists to save.

Record the provider and freshness that served the seeds (`ll-code --json status` →
`provider`, `freshness`) on the Step 8 output report's `Graph seeds:` line — a later
reader cannot otherwise tell an index-accelerated refine from a grep-fallback one,
and the two are not equally trustworthy. Do **not** put this in the Step 6.5 Session
Log: that line's format is parsed by `issue_design_timestamp()`
(`scripts/little_loops/issues/program_design.py:406-427`) and extra text breaks the
Program Design gate's arming.

#### Agent 1: codebase-locator

Insert the `CONFIRMED SEEDS` block only when Step 3.05 produced confirmed hits; omit
the whole block otherwise (never pass an empty seed list — it reads as "there are
none", which is the negative result the safety rules forbid trusting).

```
Use Task tool with subagent_type="ll:codebase-locator"

Prompt: Find all files related to this issue:

Issue: [ISSUE-ID] - [issue title]
Key concepts: [extracted concepts from Step 2]

CONFIRMED SEEDS (from the code graph, already verified at path:line — treat as
established, do not re-derive; your job is to confirm coverage and find what
these miss):
- Importers of [target]: [path:line, ...]
- Impact set for [target]: [path, ...]
- Symbols defined in [target]: [symbol @ path:line, ...]
This list is NOT exhaustive. Absence from it is not evidence of absence.

Search for:
- Files mentioned or implied in the issue description
- Related components and dependencies
- Test files that cover affected code
- Configuration files that may be relevant
- Documentation that describes affected features

Return file paths grouped by category:
- Implementation files
- Test files
- Configuration
- Documentation
```

#### Agent 2: codebase-analyzer

```
Use Task tool with subagent_type="ll:codebase-analyzer"

Prompt: Analyze the current behavior related to this issue:

Issue: [ISSUE-ID] - [issue title]
Summary: [issue summary]

CONFIRMED SEEDS (from the code graph, already verified at path:line — treat as
established, do not re-derive; trace outward from these):
- Callers of [symbol]: [path:line, ...]
- Callees of [symbol]: [path:line, ...]
This list is NOT exhaustive. Absence from it is not evidence of absence.

Analyze:
- Current behavior of the code described in the issue
- Data flow and integration points
- How the affected component connects to the rest of the system
- Any existing error handling or edge cases

Return analysis with specific file path and anchor references (e.g., function names, class names).
```

#### Agent 3: codebase-pattern-finder

```
Use Task tool with subagent_type="ll:codebase-pattern-finder"

Prompt: Identify the conventions this codebase holds for this kind of change:

Issue: [ISSUE-ID] - [issue title]
Type: [BUG|FEAT|ENH|EPIC]

Search for:
- Similar fixes/features already in the codebase
- Established conventions for this type of change
- How this codebase tests changes of this kind
- Existing utility functions and shared modules that could be reused
- Similar logic elsewhere that suggests consolidation

For each finding, report **the rule the examples share**, then cite the file
path and anchor as evidence for that rule — e.g. "subcommands register through
a `_add_*_parser` helper (`cli.py:412`, `cli.py:487`)", not "copy `cli.py:412`".
Where two examples disagree, say so and report both — a contested convention is
a decision the implementer needs to make knowingly, not a coin-flip you make
for them.

Do not recommend an implementation approach. Report what is true about the
codebase; the route is the implementer's call.
```

#### Wait for ALL spawned agents' results synchronously in this same turn before proceeding.

### 4. Identify Knowledge Gaps

**Skip this step if Step 3.1 applied** (zero unmet axes, no agents spawned) — with no research findings there is nothing to identify gaps against, and inventing them is the failure mode 3.1 exists to prevent.

Using the research findings from Step 3, identify what information is **missing from the issue** that an implementer would need. This is **knowledge gap analysis**, not structural gap analysis.

A section can be "present" per the template but still lack the codebase-specific context an implementer needs.

#### Gap Categories by Issue Type

**For BUGs:**
| Knowledge Gap | What's Missing | Research Source |
|---------------|---------------|----------------|
| Root cause location | Which file and function/class contains the bug | codebase-analyzer |
| Affected code paths | What other code calls/depends on the buggy code | codebase-locator |
| Reproduction context | What conditions trigger the bug based on code analysis | codebase-analyzer |
| Test coverage | Which tests exist for affected code, what's untested | codebase-locator |
| Related fixes | Similar bugs fixed before — patterns to follow | codebase-pattern-finder |
| Types/signatures/call path | The concrete types, function signatures, and call chain the fix will touch | codebase-analyzer |
| New decision logic present but unspecified | A new gap kind, gate, keyword list, or threshold the fix introduces with no exact inputs/values/escape hatch pinned down | codebase-analyzer |

**For FEATs:**
| Knowledge Gap | What's Missing | Research Source |
|---------------|---------------|----------------|
| Integration surface | Where the new feature connects to existing code | codebase-locator + analyzer |
| Existing patterns | How similar features are implemented in this codebase | codebase-pattern-finder |
| API conventions | How existing public interfaces are structured | codebase-pattern-finder |
| Test patterns | How similar features are tested | codebase-pattern-finder |
| Reusable code | Existing utilities/modules to leverage | codebase-pattern-finder |
| Types/signatures/call path | The concrete types, function signatures, and call chain the feature will touch | codebase-analyzer |
| New decision logic present but unspecified | A new gap kind, gate, keyword list, or threshold the feature introduces with no exact inputs/values/escape hatch pinned down | codebase-analyzer |

**For ENHs:**
| Knowledge Gap | What's Missing | Research Source |
|---------------|---------------|----------------|
| Current implementation | How the code being enhanced currently works | codebase-analyzer |
| Refactoring surface | What needs to change and what can stay | codebase-analyzer |
| Consistency considerations | How nearby/similar code is structured | codebase-pattern-finder |
| Callers/dependents | What code uses the component being enhanced | codebase-locator |
| Existing abstractions | Shared code that already partially solves this | codebase-pattern-finder |
| Types/signatures/call path | The concrete types, function signatures, and call chain the enhancement will touch | codebase-analyzer |
| New decision logic present but unspecified | A new gap kind, gate, keyword list, or threshold the enhancement introduces with no exact inputs/values/escape hatch pinned down | codebase-analyzer |

#### Gap Detection

For each knowledge gap category relevant to the issue type:
1. Check if the issue already contains this information (with specific file path and anchor references, not vague descriptions)
2. Check if the research findings provide this information
3. If the issue lacks it but research found it: mark as **FILLABLE**
4. If neither the issue nor research provides it: mark as **UNKNOWN** (requires interactive clarification)

### 5a. Fill Gaps with Research Findings (Auto Mode)

**Skip this section if**: `AUTO_MODE` is false (interactive mode uses Step 5b instead)

**Scope boundary**: Only use `Edit` to modify files under `.issues/`. If research reveals a missing implementation (code, tests, config), document it in the issue — write it as a gap finding under `### Codebase Research Findings` (via `ll-issues fold-findings`, see § Writing Findings Blocks below). Do NOT implement code, even when the gap is small and the implementation is obvious. The `Edit` tool is restricted to `.issues/**` by the command's allowed-tools; attempting to edit code files will fail.

For each **FILLABLE** gap, update the issue with research findings.

#### Enrichment Rules

**Integration Map** — populate with real findings:
```markdown
## Integration Map

### Files to Modify
- `path/to/file.py` — [what needs to change, from analyzer findings]
- `path/to/other.py` — [related change needed, from locator findings]

### Dependent Files (Callers/Importers)
- `path/to/caller.py:42` — calls `affected_function()` [from locator]
- `path/to/importer.py:5` — imports `affected_module` [from locator]

### Conventions in Force
- [Rule this codebase holds] — evidence: `path/to/similar.py:100` [from pattern-finder]
  (state the rule; the file is cited as evidence for it, not as a template)

### Tests
- `tests/test_affected.py` — existing test coverage [from locator]
- [Suggest new test file if none exists]

### Documentation
- `docs/relevant.md` — may need updates [from locator]

### Configuration
- [Config files if relevant, from locator]

### Behavior Parity
| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `path/to/old_file.py` | [behavior] | PRESERVED / CHANGED / DROPPED | [why] |
```

**Behavior Parity** (ENH-3045): when `## Summary` or `## Proposed Solution`
names an existing file this issue rewrites, deletes, or delegates away, add
the `### Behavior Parity` subsection above — bare heading, one table per
issue, with the replaced artifact as a table column (never as heading text;
`_heading_bodies()` matches the heading anchored and exact, so a
per-artifact heading would never be detected downstream). Enumerate each of
the old file's behaviors with a disposition. Skip if no cited file is being
replaced, or if `behavior_parity_not_applicable: true` is set in
frontmatter — a human decision; refine must never set this flag itself.

**Capability-search and claim-grounding** (ENH-3045): before writing a
conclusion of the form "no existing implementation exists," search by
**capability** — the input/output shape the new code needs, and the callers
of the shared primitive that shape suggests — not by the algorithm's name; a
grep for an algorithm name finds nothing when the codebase never names it,
even when a function with the identical contract already exists under an
unrelated name. State what was searched in the resulting claim. The same
grounding applies to positive claims about existing code in `## Program
Design`: an assertion that a symbol is reusable, unchanged, or behaves a
given way must quote the specific line that makes it true — naming the
symbol only proves it resolves, not that the claim about it holds.

**Root Cause** (BUG) — populate with analyzer findings:
```markdown
## Root Cause

- **File**: `path/to/buggy_file.py`
- **Anchor**: `in function problematic_func()`
- **Cause**: [Behavioral analysis from codebase-analyzer — what the code does wrong and why]
```

**Program Design** — populate with analyzer findings (types, signatures, call path):
```markdown
## Program Design

### Types
- `FieldName: type` — [from analyzer, only if the change introduces/modifies a data shape]

### Signatures
- `function_name(param: type) -> ReturnType` — [existing or new signature the change touches, from analyzer]

### Call Path
`existing_caller` -> `new_or_modified_function` -> `existing_callee` [from analyzer/locator]

### Decision Rules
- [only when the issue proposes new decision logic — a new gap kind, gate, exit-code
  condition, keyword/phrase list, numeric threshold, or classification rule; exact
  inputs, literal keyword/threshold values, proximity/scoping rule, and the
  dismissal/escape hatch. `N/A — no new decision logic` otherwise.]
```
Fill this from `codebase-analyzer`'s anchor-level findings (function/class names,
existing signatures) — the same material Integration Map draws from, filed here
as concrete identifiers rather than prose bullets. If research genuinely cannot
produce a design (a one-line config change, a docs fix), do not pad the section
with prose that will fail the specificity check — instead, in Step 8's output
report, recommend `program_design_not_applicable: true` as a note for the
operator. **Never set this frontmatter field directly** — it is a human decision
(`program_design_gate_active`, `scripts/little_loops/issues/program_design.py:415`),
and a command that can opt itself out of a gate destroys the gate's value.

**Decision Rules** (ENH-3050): emit `### Decision Rules` only when the issue's
Proposed Solution or Expected Behavior introduces a new gap kind, gate, exit-code
condition, keyword/phrase list, numeric threshold, or classification rule. Do not
emit for issues that only modify existing logic. Escape hatch: a `### Decision
Rules` section whose body is the literal `N/A — no new decision logic` satisfies
the requirement. This section is advisory prose, not gated mechanically —
`program_design_nonspecific` continues to check only anchor resolution.

**Proposed Solution** — enrich with pattern-finder findings:
- If a Proposed Solution section exists but is vague, add a subsection with concrete implementation guidance based on similar patterns found
- If no Proposed Solution exists, add one based on how similar changes were made elsewhere

**Decision-Point Formatting (Auto Mode only)** — when the research pass is
about to deposit a decision point naming 2+ concrete alternatives with a
recommendation (e.g. prose like "Two viable resolutions: (a) ... or (b) ...
Recommendation: X for v1"), format the alternatives as bold-label blocks
instead of leaving them as unstructured prose, so Option-Count Detection
below can recognize them:

```markdown
**Option A**: [first alternative, verbatim from the research/existing text]

**Option B**: [second alternative, verbatim from the research/existing text]

**Recommended**: Option [X] — [existing rationale, preserved verbatim]
```

Place this block **inside `## Proposed Solution`** by piping it to
`ll-issues fold-findings [ISSUE-ID] --section "Proposed Solution"` (see
§ Writing Findings Blocks below — the heading and provenance line are never
hand-written). It must live under that exact H2, since that is the only
section `count_enumerable_options()`/`count_unresolved_options()` scan along
with the `_OPTION_FALLBACK_SECTIONS` fallbacks. The option block has no
leading `- ` bullets; pipe it verbatim, the command inserts it byte-for-byte.
Additive, not a rewrite of existing text — this is true regardless of where the original prose that
prompted the decision point lived (e.g. `## Open Questions`). If the
original prose sits outside `## Proposed Solution`, leave a one-line
cross-reference at its original location (e.g. "See Option A/B decision
under Proposed Solution → Codebase Research Findings") so the Preservation
Rule's intent — don't orphan human context — is still met. Do not add any
`— suffix` decoration to generated heading text; the probes match headings
by exact name. This applies only to refine-issue's own freshly-written
research findings; it does not rewrite pre-existing human-authored prose it
didn't write.

**Option-Count Detection (Auto Mode only)** — after writing to Proposed Solution:

Count distinct implementation options deposited. Detect by any of these patterns in the deposited content:
- Numbered approaches: top-level items `1. ...`, `2. ...` each describing a distinct approach
- Headed options: `### Option A`, `### Option B`, `### Option C` (etc.)
- Bold options: `**Option A**`, `**Option B**`, `**Option 1**`, `**Option 2**` (etc.)

Then update `decision_needed` in the issue's YAML frontmatter using the Edit tool (inline `---` block replacement, following `skills/confidence-check/SKILL.md` in section "Phase 4: Update Frontmatter"):
- If option count >= 2: before setting `decision_needed: true`, run
  `ll-issues check-decidable <ID>` to verify the deposited options are
  actually machine-visible to the same probe the decision gate uses. If it
  exits 0, set `decision_needed: true`. If it exits 1 (`OPTIONS_MISSING`),
  the options were deposited somewhere the probe cannot see — fix the
  placement (move the block into `## Proposed Solution` per the rule above)
  and re-check rather than setting a flag the downstream gate can never
  satisfy.
- If option count < 2: set `decision_needed: false` (or remove if absent — prevents stale `true` from a prior pass)

**Idempotency**: skip the write if `decision_needed` already has the same value (follow `skills/format-issue/SKILL.md` in section "2.5a. Testable Inference (doc-only detection)").
**Dry-run guard**: skip the frontmatter write in `--dry-run` mode; report what would have been set in the DRY RUN PREVIEW block.

**Implementation Steps** — concrete references, outcome phrasing. Each entry
names what must become true and how that is checked, not the edit to make (see
§ Register: Constraints, Not Recipes):

```markdown
## Implementation Steps

1. [Outcome + where it lands — e.g., "The new flag parses and round-trips
   through `parser.py:parse_args()`; that function owns every other flag today"]
2. [Coverage constraint — e.g., "Flag parsing is covered by a test alongside
   `test_parser.py:TestFlagParsing`, which holds the existing contract"]
3. [Verification — e.g., "`python -m pytest scripts/tests/test_parser.py -v` passes"]
```

Use imperative sequencing only where the order is genuinely forced (a migration
that must precede a read, a schema change before its consumer). Where the order
is incidental, phrasing it as a sequence invents a constraint that does not
exist and forecloses better routes.

#### Preservation Rule

**Do NOT overwrite non-empty sections** with >2 lines of meaningful text (not "TBD" or placeholders).

When a section already has meaningful content:
- **Append** research findings as a subsection or additional bullets, clearly marked
- **Do NOT replace** existing human-written or previously-refined content
- Write the findings via `ll-issues fold-findings` (§ Writing Findings Blocks below)

#### Writing Findings Blocks (ENH-2993)

**`ll-issues fold-findings` is the only route.** Never hand-`Edit` a
`### Codebase Research Findings` heading or an `_Added by …_` provenance line —
the command supplies both. Hand-writing them re-creates the sibling-block
accumulation this route exists to prevent, and § 6.7's
`duplicate_findings_block` key will fail the pass that did it.

Content goes on **stdin**, never in argv — the payload carries backticks, `$`,
`!`, em-dashes and newlines, and argv quoting is the likeliest way to corrupt
it:

```bash
ll-issues fold-findings [ISSUE-ID] --section "Integration Map" <<'EOF'
- [Finding 1 with file path and anchor reference]
- [Finding 2 with file path and anchor reference]
EOF
```

- `--section` names the parent **H2** by exact heading text (no `## ` prefix),
  matched case-insensitively. Findings are always addressed by their nearest H2
  ancestor, even when the bullets logically belong to an H3 beneath it.
- The command folds: if a findings block already exists under that H2 it
  appends beneath it, and if several have stacked up from earlier passes it
  collapses them into one first. Nothing is deleted, summarized, or deduped —
  every bullet and every earlier provenance line survives, in order.
- An absent `--section` is **created** in v2.0 template order and is a normal
  success, not an error. Exit 1 = unresolvable issue ID or empty stdin;
  exit 2 = section absent and `--no-create` was passed.
- **If `DRY_RUN` is true, pass `--dry-run`.** This write no longer inherits
  Step 6's "skip file modifications" guarantee from the `Edit(.issues/**)` tool
  restriction — the flag is what preserves it.

**Superseded-line annotation carve-out** (ENH-2995): a narrow exception to
"Do NOT replace" — when this pass's own `### Codebase Research Findings`
refute a specific directive line, **annotate** that line in place. This does
not violate the Preservation Rule: the original line is never edited,
reordered, or deleted — a marker is inserted as a new line immediately below
it.

- **Scope**: only `## Implementation Steps`, `### Files to Modify`, and
  `## Acceptance Criteria`. Never `## Summary`, `## Motivation`,
  `## Proposed Solution`, or any `### Option …` / `### Decision Rationale`
  prose.
- **Same pass only**: fires only when the refutation comes from THIS pass's
  own research findings, never from re-reading a prior pass's appended
  `### Codebase Research Findings` block.
- **Refutation test — two branches**: either qualifies.
  - **Finding-driven**: a finding names or quotes the line and asserts it is
    wrong. Correction-phrase guidance (non-exhaustive — a finding that
    plainly refutes the line in other words still qualifies): `is wrong` ·
    `does not exist` · `will not work` · `must be dropped` · `target file
    is wrong` · `is stale` · `omit entirely`.
  - **Contradiction-driven**: content this pass is appending elsewhere in
    the issue contradicts the line by implication, without a finding that
    names it directly — e.g. an elaboration that enumerates a change as
    mandatory while an existing line calls it optional. Fires only on
    content THIS pass appends, same "same pass only" scoping as above.
- **Marker text and placement**: insert as a new line immediately below the
  refuted line, indented to that line's own content column (3 spaces under a
  `1. ` step, 2 under a `- ` bullet) — never at column 0, which would both
  terminate the enclosing CommonMark list and collide with
  `_CRITERION_BULLET_PATTERN`/`_OPTION_PATTERNS` (`issue_parser.py`), which
  key on `^\d+\.`/`^[-*]`:

  ```markdown
  1. Add `pending_file: "${context.run_dir}/pending.txt"` to the loop's `context:` block
     > ⚠ Superseded — omit entirely; see § Codebase Research Findings under Implementation Steps
  ```

  The reason clause (≤10 words) is required — without it, multiple refuted
  lines in one section get byte-identical markers and a reader must
  re-derive the findings-to-line mapping by hand. This reuses the existing
  stale-anchor blockquote shape (§ 5c Gap-Analysis Mode, "Stale anchor
  repair") rather than inventing new marker syntax.
- **Idempotent**: skip the insertion if the line immediately below already
  contains the substring `⚠ Superseded` — containment on that stable prefix,
  not exact-text equality, since the reason clause varies between passes.
- **Bounded marker-removal right**: a marker is the one exception to "Do NOT
  remove any existing content under any circumstance". If this pass's
  findings no longer refute a line whose next line carries a `⚠ Superseded`
  marker, delete that marker line — silently, no tombstone. Only lines
  matching the marker convention are ever deletable; the refuted line and
  every other line stay untouchable.

### 5b. Interactive Refinement (Skip in Auto Mode)

**Skip this entire section if `AUTO_MODE` is true.**

Present research findings and ask targeted questions informed by what was found in the codebase.

#### Research Summary

First, display a summary of what was discovered:

```
Research Findings for [ISSUE-ID]:
- Found [N] related files
- Identified [key integration points]
- Found [similar patterns at file in function/class anchor]
- [Key discovery from analysis]
```

#### Research-Informed Questions

Use AskUserQuestion with **maximum 4 questions per round**, prioritized by implementation importance.

Questions must reference specific codebase findings:

```yaml
questions:
  - question: "I found that `function_name()` at `file.py:42` handles this case. Is this the right place to make changes?"
    header: "Location"
    multiSelect: false
    options:
      - label: "Yes, modify there"
        description: "Change function_name() in file.py"
      - label: "No, different location"
        description: "I'll specify the correct location"

  - question: "There are 3 callers of `affected_function()`: caller_a.py:10, caller_b.py:25, caller_c.py:50. Should all be updated?"
    header: "Scope"
    multiSelect: true
    options:
      - label: "caller_a.py"
        description: "Updates the primary usage path"
      - label: "caller_b.py"
        description: "Updates the secondary usage path"
      - label: "caller_c.py"
        description: "Updates the test helper"

  - question: "Similar implementation exists at `pattern_file.py:100`. Should this follow the same pattern?"
    header: "Pattern"
    multiSelect: false
    options:
      - label: "Yes, follow existing pattern"
        description: "Consistent with codebase conventions"
      - label: "No, different approach"
        description: "I'll explain the preferred approach"
```

For **UNKNOWN** gaps (research didn't find enough), ask open-ended questions:

```yaml
  - question: "[Specific question about what couldn't be determined from code alone]"
    header: "Context"
    multiSelect: false
    options:
      - label: "[Option based on best guess from research]"
        description: "[What research suggests]"
      - label: "[Alternative interpretation]"
        description: "[Different approach]"
```

After gathering answers, update the issue file with both research findings and user-provided context.

### 5c. Gap-Analysis Mode (Skip Unless `--gap-analysis`)

**Skip this entire section if `GAP_ANALYSIS` is false.**

Gap-analysis mode performs additive-only enrichment — it never removes existing content. The core contract: "Gap-analysis never removes existing content — it only adds or enhances."

#### 1. Parse Existing Issue into Section Map

Extract all H2 sections from the issue file and catalog their content:
- Sections present: list of H2 headings found
- Sections with meaningful content (>2 lines, not placeholder text like "TBD" or "N/A")
- Sections that are empty or contain only boilerplate

Use the H2 extraction pattern from `scripts/little_loops/issue_history/doc_synthesis.py:_extract_section()`:
```python
# re.search(r"^##\s+heading", content, re.MULTILINE) then slice to next ##
```

#### 2. Check Each Section Against Codebase Reality

For each section type, verify against current codebase state:

**Integration Map checks:**
- Referenced files: do they exist on disk? Missing = high-priority gap.
- Stale anchor references: a `file:N`-style anchor resolves when `scripts/little_loops/issues/anchors.py:resolve_anchor()` returns non-`None` **and** `N` is within the file's line count — `resolve_anchor()` clamps out-of-range line numbers to EOF, so a number past the end still returns an anchor. (`anchor_sweep.py:_sweep_file()` applies this same rule in bulk, but its `skipped_refs` is an aggregate counter with no per-reference detail — use `resolve_anchor()` when you need to know *which* reference went stale.)
- Missing callers: are there known callers of modified code not listed?

**Proposed Solution / Implementation Steps:**
- Anchor references still valid? (same `resolve_anchor()` rule as above)
- Do Implementation Steps reference all files in the Integration Map?

**Acceptance Criteria:**
- Are there code paths identified during research that have no corresponding criterion?

#### 3. Score Gaps by Impact

Adopt the `"critical"/"high"/"medium"/"low"` priority model from `scripts/little_loops/issue_history/models.py:Gap`:

| Gap Type | Priority |
|----------|----------|
| Referenced file doesn't exist on disk | high |
| Stale anchor reference (function/class gone) | medium |
| Implementation Step references file not in Integration Map | medium |
| Missing edge case in Acceptance Criteria | low |
| Required section empty or placeholder-only | medium |

#### 4. Present Gap Report

Display a prioritized gap table:

```
## Gap Analysis Report — [ISSUE-ID]

| Section | Gap | Priority | Suggestion |
|---------|-----|----------|------------|
| Integration Map | `path/to/file.py` does not exist | high | Remove or update path |
| Proposed Solution | `old_function()` not found | medium | Update anchor reference |
| Acceptance Criteria | Edge case X not covered | low | Add criterion for X |
```

If no gaps found, output:
```
✓ No gaps detected. Issue coverage is current.
```

If `AUTO_MODE` is true, proceed directly to application without prompting. Otherwise, present the gap report and confirm before applying.

#### 5. Apply Additive Changes Only

For each approved gap, use the Edit tool with append-only changes:

1. **Append** missing information to the relevant section by piping it to `ll-issues fold-findings [ISSUE-ID] --section "<H2>"` (same as Step 5a — see § Writing Findings Blocks; never hand-write the heading or provenance line). Folding is relocation only, so this mode's additive-only guarantee is unchanged.
2. **Stale anchor repair**: when `_sweep_file()` returns a stale reference, append a warning note under the section containing it:
   ```
   > ⚠ Anchor `old_function:N` no longer resolves — verify against current codebase.
   ```
3. **Do NOT** replace any existing text block with more than 2 meaningful lines
4. **Do NOT** remove any existing content under any circumstance

**Gap-analysis and max_refine_count**: Gap-analysis runs (`--gap-analysis`) do NOT count against `max_refine_count` — they are additive-only, non-destructive, and designed for repeated iterative use. Only full-rewrite passes (`--full-rewrite` or the default non-flag mode) consume the refinement budget.

#### 6. Gap-Analysis Output

```
================================================================================
GAP ANALYSIS COMPLETE: [ISSUE-ID]
================================================================================

| Gap | Priority | Applied |
|-----|----------|---------|
| [gap 1] | [priority] | ✓ Appended to [Section] |
| [gap 2] | [priority] | ✓ Stale-anchor note added |

Sections preserved verbatim: [N]
Content added: [N] additions
Content removed: 0 (gap-analysis never removes)

Run /ll:ready-issue [ISSUE-ID] to validate.
================================================================================
```

### 6. Update Issue File

**Skip file modifications if `DRY_RUN` is true.**

1. Use Edit tool to add/update sections with research findings and user input
2. Preserve existing frontmatter
3. Preserve existing non-empty sections (append, don't replace)
4. Add new sections in appropriate locations following v2.0 template ordering
5. Ensure all added file paths and references are from actual research (no placeholders in auto mode)
6. **Canonical dependency phrasing**: when any prose you write asserts that this
   issue is blocked by another issue, phrase it canonically — `Blocked by
   <ID>` / `Depends on <ID>` / `Requires <ID>` (or the synonyms `blocked on`,
   `gated on`, `waiting on`, `contingent on`, `predicated on`). Paraphrases like
   "blocking dependency unmet: BUG-3028's decision has not landed" are invisible
   to `extract_prose_deps()`, so Step 6.7's gate never fires and the
   `blocked_by` edge is never written — the issue then reads as unblocked to
   `ll-issues ready` and sprint scheduling.

### 6.5. Append Session Log

After updating the issue, use the Bash tool to append a session log entry —
**before** the Prose/Program Design Gate below, since
`program_design_gate_active()` (`scripts/little_loops/issues/program_design.py:415`)
derives arming from the most recent `/ll:refine-issue` Session Log entry
(`issue_design_timestamp()`, `:391-406`). Checking the gate before this append
would read a grandfathered issue as still grandfathered and declare success
without ever having written a design — the exact bug this ordering exists to
prevent. Do not move this append back below the gate check.

```bash
ll-issues append-log <path-to-issue-file> /ll:refine-issue
```

If `ll-issues` is not available, fall back to manually appending with **exactly** this format (backticks required):

```
- `/ll:refine-issue` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

### 6.7. Prose Dependency & Program Design Gate (FEAT-2849, BUG-3001)

After appending the session log (Step 6.5 above — order matters, see that
step's note), run `ll-issues format-check [ISSUE-ID] --format json` and
inspect the `prose_dep_drift`/`stale_prose_dep`/`program_design_nonspecific`
keys:

- **`prose_dep_drift` non-empty**: the body claims a dependency in prose
  ("Depends on ID", "Blocked by ID", "Requires ID", the synonyms "blocked on",
  "gated on", "waiting on", "contingent on", "predicated on", or a `## Blocked
  By` section) on an active issue not reflected in `blocked_by`/`depends_on`
  frontmatter. Add the missing edge via `ll-issues link [ISSUE-ID] blocked_by
  [BLOCKER-ID]` (do not silently drop the prose) and re-run `format-check` to
  confirm the drift clears.
- **`stale_prose_dep` non-empty**: the body names a `done`/`cancelled` issue
  as a blocker. Edit the prose to remove/update the stale reference — this is
  a text fix, not a frontmatter edge to add.
- **`program_design_nonspecific` non-empty**: the `## Program Design` section
  (written in Step 5a above) failed the specificity check. Revise that
  section **once** using the same analyzer findings — add or sharpen concrete
  types/signatures/call-path identifiers — and re-run `format-check` to
  confirm it clears. This is a single attempt, not a retry loop (matches the
  `prose_dep_drift` precedent above: fix once, confirm once). If it still
  fails after that one revision, do not touch `program_design_not_applicable`
  — report the still-failing gap explicitly in Step 8's output so the
  operator knows the gate is still armed. This check is naturally inert on
  unstamped/grandfathered projects: `format-check` already returns an empty
  `program_design_nonspecific` there via `program_design_gate_active()`
  semantics, so no separate skip condition is needed here.
- **`superseded_marker_count` > 0** (ENH-2992): this issue carries at least one
  `⚠ Superseded` marker in a directive section — either one this pass just
  wrote (§ 5a's carve-out) or one an earlier pass left standing. Refine
  **annotates** but never rewrites, so the contradiction stays open until
  `/ll:reconcile-issue` rewrites the section. Do not attempt the rewrite here.
  Surface it: report the count in Step 8's output and name
  `/ll:reconcile-issue [ISSUE-ID]` in the Next Steps block. This is the human
  path into a remedy that was previously reachable only via `autodev.yaml`'s
  plateau gate (measured at capture: 1,703 issues refined, 19 reconciled).
- **`duplicate_findings_block` non-empty** (ENH-2993): one or more H2s carry
  more than one `### Codebase Research Findings` block. Each entry is
  `"<H2 heading> (N)"`. Two branches, and they are not interchangeable:
  - **The entry names an H2 this pass wrote to** — the heading was hand-written
    instead of going through `ll-issues fold-findings`. Re-issue that write
    through the command (§ Writing Findings Blocks) and re-run `format-check`
    to confirm it clears. This is the adoption failure the key exists to catch.
  - **The entry names an H2 this pass did not touch** — a pre-existing stack
    from earlier passes. It is not this pass's to fix and there is no corpus
    sweep. Like `superseded_marker_count`, **report the count in Step 8's
    output and do not edit**; it folds as a side effect of a future pass that
    writes to that section.
- **`soft_dep_hard_edge` non-empty** (ENH-3046): an ID in `blocked_by`/
  `depends_on` frontmatter shares a paragraph with soft-dependency language
  ("soft dep", "optional", "nice to have", "has not landed"). The soft prose
  is usually the accurate statement and the hard edge is the mistake — move
  the ID from `blocked_by`/`depends_on` to `relates_to` via `ll-issues link
  [ISSUE-ID] relates_to [ID] --unlink [ISSUE-ID] blocked_by [ID]` (or the
  equivalent two-step edit), and **do not delete the soft-dependency prose**
  — that would silently harden a dependency that was deliberately optional.
  Re-run `format-check` to confirm it clears. No suppression escape hatch
  exists for this key.
- **AC-vs-Program-Design contradiction pass** (ENH-3046, judgment-class —
  report only, never auto-applied): read only the `## Acceptance Criteria`
  and `## Program Design` sections and identify any pair of statements that
  cannot both be satisfied (e.g. one AC requires a behavior another AC or the
  Program Design section forbids). This is not mechanical — no gap kind
  catches it, since both statements may reference the same flags/types and
  differ only in what they permit. List any findings as `[AC N] vs
  [AC M / Program Design]: [one-sentence contradiction]` in Step 8's output
  under the gate report; do not edit the issue file to resolve them.
- Skip this gate if `DRY_RUN` is true.

### 7.5. Extract Learning Targets (ENH-2209)

After appending the session log, extract external API dependencies from the issue text and auto-populate `learning_tests_required` in frontmatter.

**Skip this step** if the issue frontmatter contains `testable: false` or if `--dry-run` is set.

1. **Identify external dependencies** — Analyze the full issue text (frontmatter + body) to list all third-party packages, SDKs, and external API surfaces the implementation plan assumes behavior of. Exclude project-internal code and contract-stable stdlib (os, sys, pathlib, json, re, datetime, builtins). Return a deduplicated list of short target names (e.g. `["anthropic", "requests", "stripe"]`).

2. **Check each target against the registry** — For each extracted target, run:
   ```bash
   ll-learning-tests check --stale-aware "<target>"
   ```
   Exit 0 = proven and fresh (M proven). Exit 1 = missing, stale, or refuted (K unproven).

3. **Write to frontmatter with union-merge** — If at least one target was found:
   - Read the current `learning_tests_required` value from frontmatter (may be absent, a list, or a string).
   - Build the merged list: `existing_targets ∪ new_targets` (preserve existing entries; append new ones; deduplicate by order of first appearance).
   - Update the issue file using `update_frontmatter` with `{"learning_tests_required": merged_list}`.
   - If no targets were found, **do not** write `learning_tests_required: []` — omit the field entirely.

4. **Surface summary** — Emit a one-line summary before the output report:
   ```
   Learning targets: Found N external dependencies — M proven, K unproven. Added to `learning_tests_required`.
   ```
   If all were already proven and the frontmatter was already correct, emit:
   ```
   Learning targets: All N proven — `learning_tests_required` unchanged.
   ```
   If no external dependencies were found:
   ```
   Learning targets: None detected — `learning_tests_required` field omitted.
   ```

### 8. Output Report

```
================================================================================
ISSUE REFINED: [ISSUE-ID]
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH|EPIC]
- Title: [title]
- Mode: [Interactive | Auto] [--dry-run]

## RESEARCH SUMMARY
- Files discovered: [N]
- Integration points identified: [N]
- Similar patterns found: [N]
- Graph seeds: [N confirmed via <provider>/<freshness>] — or: none (provider unavailable) / skipped (no concrete targets)
- Key finding: [most important discovery]

## KNOWLEDGE GAPS IDENTIFIED
| Gap | Status | Source |
|-----|--------|--------|
| [Gap 1] | FILLED — [brief description of finding] | [agent] |
| [Gap 2] | FILLED — [brief description of finding] | [agent] |
| [Gap 3] | UNKNOWN — [asked user / left for implementer] | — |

## SECTIONS ENRICHED
- **Integration Map**: Populated with [N] file paths and [N] callers
- **Root Cause**: Added file path and anchor reference and behavioral analysis [BUG only]
- **Program Design**: Added [N] type(s)/signature(s) and a call path from analyzer findings — or: not applicable, recommend `program_design_not_applicable: true` [see Program Design Gate row below if still failing]
- **Implementation Steps**: Made concrete with [N] specific file references
- **[Other section]**: [What was added]

## SECTIONS PRESERVED
- **[Section]**: Existing content preserved (non-empty)
- **[Section]**: Existing content preserved

## DRY RUN PREVIEW [--dry-run only]
[Show exact enrichments that would be applied without applying them]
- Would add to Integration Map: [N] file paths
- Would update Root Cause with: [file path and anchor reference]
- Would populate Program Design with: [N] signatures and a call path
- Would enrich Implementation Steps with: [N] concrete references

## PROSE/PROGRAM DESIGN GATE [Step 6.7]
- prose_dep_drift: [clear | fixed | — ]
- stale_prose_dep: [clear | fixed | — ]
- superseded_marker_count: [N — run `/ll:reconcile-issue [ID]` | 0]
- program_design_nonspecific: [clear | revised once, now clear | STILL FAILING after one revision — operator action needed | not applicable (unarmed/grandfathered)]
- soft_dep_hard_edge: [clear | fixed (moved [ID] to relates_to) | — ]
- AC-vs-Program-Design contradictions: [none found | N found — see findings below]

## FILE STATUS
- [Modified | Not modified (--dry-run)]
- decision_needed: [true | false | not set | skipped (--dry-run)] [Auto mode only]

## NEXT STEPS
- If this pass deposited findings that refute an existing directive line (`superseded_marker_count` > 0 in Step 6.7): run `/ll:reconcile-issue [ID]` to rewrite the contradicted section. Refine only annotates the contradiction; reconcile is the only command that resolves it (ENH-2992)
- If `decision_needed: true` was set (2+ options deposited): run `/ll:decide-issue [ID]` to select the best option before wiring
- Run `/ll:wire-issue [ID]` to add integration wiring (callers, entry points, test hooks)
- Run `/ll:ready-issue [ID]` to validate the enriched issue
- Run `/ll:manage-issue` to implement
- If `/ll:ready-issue` continues to score NOT_READY after 2+ refinement passes, run `/ll:issue-size-review [ID]` — a persistent readiness gap often means the issue is too large or poorly scoped, not just under-researched
- If `program_design_nonspecific` is still failing after the single revision attempt: hand-write `## Program Design` or set `program_design_not_applicable: true` yourself — refine will not set this flag for you (it is a human decision, see Step 5a)

================================================================================
```

---

## Examples

```bash
# Interactive refinement with codebase research
/ll:refine-issue FEAT-225

# Auto-refine with codebase research (non-interactive)
/ll:refine-issue BUG-042 --auto

# Dry-run to preview what research would produce
/ll:refine-issue ENH-015 --auto --dry-run

# Gap-analysis mode: additive-only, never removes content
/ll:refine-issue ENH-100 --gap-analysis

# Full-rewrite mode (legacy behavior, now explicit)
/ll:refine-issue ENH-100 --full-rewrite --auto
```

---

## Integration

### Pipeline Position

```
/ll:capture-issue → /ll:format-issue → /ll:refine-issue → /ll:decide-issue → /ll:wire-issue → /ll:ready-issue → /ll:manage-issue
                                             │
                                             └─ (conditional) /ll:reconcile-issue — when this pass
                                                refuted an existing directive line
```

- **Before**: `/ll:format-issue` — ensures structural template compliance
- **After**: `/ll:verify-issues` or `/ll:ready-issue` — validates accuracy and completeness
- **Conditional branch**: `/ll:reconcile-issue` (ENH-2992) — refine only *annotates* a
  refuted directive line with a `⚠ Superseded` marker; reconcile is what rewrites the
  section. Shown on this canonical diagram only: the two *Typical Workflows* diagrams
  below enumerate the happy path a developer types, and a conditional remedy edge
  there would be noise.

### Typical Workflows

**Interactive workflow** (developer preparing an issue):
```
/ll:capture-issue "description" → /ll:format-issue [ID] → /ll:refine-issue [ID] → /ll:ready-issue [ID]
```

**Automated workflow** (pipeline):
```
/ll:capture-issue → /ll:format-issue [ID] --auto → /ll:refine-issue [ID] --auto → /ll:ready-issue [ID]
```

### Key Differences from Related Commands

| Aspect | format-issue | refine-issue | ready-issue |
|--------|-------------|-------------|-------------|
| **Purpose** | Template alignment | Codebase research & enrichment | Validation & gatekeeping |
| **Gap type** | Structural (missing sections) | Knowledge (missing implementation context) | Accuracy (claims vs reality) |
| **Research** | None (text inference) | Core function, per-axis gated (skips axes the issue already covers; always all 3 under `--full-rewrite`) | Optional (--deep flag) |
| **Output** | Boilerplate/inferred text | Concrete file paths, signatures, analysis | Verdict + corrections |
