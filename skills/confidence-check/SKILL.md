---
name: confidence-check
description: Use when asked for a pre-implementation confidence check or whether an issue is ready to implement.
args: "ISSUE_ID"
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(find:*)
  - Bash(git:*)
  - Bash(ll-history-context:*)
  - Bash(ll-learning-tests:*)
  - Bash(ll-issues:*)
metadata:
  short-description: Use when asked for a pre-implementation confidence check or whether an issue is 
trigger_fixtures:
  should_fire:
    - "run a pre-implementation confidence check on whether this issue is ready to implement"
    - "check confidence that this issue is ready to implement"
  should_not_fire:
    - "select the winning implementation option for this issue"
    - "adversarial review of whether this issue is worth implementing"
---

# Confidence Check Skill

Pre-implementation assessment that validates readiness to begin coding and estimates outcome confidence. Produces dual scores: a Readiness Score (are preconditions met?) and an Outcome Confidence Score (will implementation succeed cleanly?). Uses research findings from Phase 1.5 (or standalone research) to evaluate both dimensions.

## When to Activate

- Before implementation in `/ll:manage-issue` (recommended step in Phase 2)
- When unsure whether an issue is ready for coding
- After deep research, to evaluate whether findings support the approach
- User asks "is this ready to implement?" or similar

## Arguments

$ARGUMENTS

Parse arguments for issue ID and flags:

```bash
ISSUE_ID=""
AUTO_MODE=false
ALL_MODE=false
CHECK_MODE=false
SPRINT_NAME=""

# Auto-enable in automation contexts
if [[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${LL_NON_INTERACTIVE:-}" ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then AUTO_MODE=true; fi

# Explicit flags
if [[ "$ARGUMENTS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$ARGUMENTS" == *"--all"* ]]; then ALL_MODE=true; fi
if [[ "$ARGUMENTS" == *"--check"* ]]; then CHECK_MODE=true; AUTO_MODE=true; fi
if [[ "$ARGUMENTS" =~ --sprint[[:space:]]+([^[:space:]]+) ]]; then SPRINT_NAME="${BASH_REMATCH[1]}"; fi

# Extract issue ID (non-flag argument)
for token in $ARGUMENTS; do
    case "$token" in
        --*) ;; # skip flags
        *) ISSUE_ID="$token" ;;
    esac
done

# Validate: --all cannot be combined with a specific issue ID
if [[ "$ALL_MODE" == true ]] && [[ -n "$ISSUE_ID" ]]; then
    echo "Error: --all flag cannot be combined with a specific issue ID"
    echo "Usage: /ll:confidence-check --all"
    exit 1
fi

# Validate: --sprint cannot be combined with --all
if [[ "$ALL_MODE" == true ]] && [[ -n "$SPRINT_NAME" ]]; then
    echo "Error: --sprint and --all cannot be combined"
    exit 1
fi

# --all implies --auto (batch processing is inherently non-interactive)
if [[ "$ALL_MODE" == true ]]; then
    AUTO_MODE=true
fi

# --sprint implies --auto (sprint batch is inherently non-interactive)
if [[ -n "$SPRINT_NAME" ]]; then AUTO_MODE=true; fi
```

See [rubric.md](rubric.md) for the full **Arguments Reference**: `issue_id`
(optional) and the `--auto`, `--all`, `--check`, and `--sprint <name>` flag
semantics.

## Issue Discovery

Resolve which issue file(s) to evaluate based on the parsed flags. See
[rubric.md](rubric.md) for the per-mode resolution bash:

- **Single Issue Mode** (default) — `ISSUE_ID` provided: resolve via
  `ll-issues path`. If no `ISSUE_ID` and not `--all`, expect a manage-issue
  context where research findings are already available.
- **Batch Mode** (`--all`) — collect all active issue files from `bugs/`,
  `features/`, `enhancements/`, then iterate the full workflow (Phases 1-4) per
  issue, collecting results for the batch summary.
- **Sprint Mode** (`--sprint <name>`) — load issue IDs from
  `.sprints/<name>.yaml`, resolve each via `ll-issues path`, then iterate
  exactly as in Batch Mode. The batch summary header reads
  `Sprint: <name> (N issues)` instead of `--all mode`.

## Workflow

### Phase 1: Gather Context

If invoked standalone (not within manage-issue):
1. Read the issue file
2. Use Glob/Grep to find related files mentioned in the issue
3. Check for existing implementations

After loading the issue file, run:

```bash
HIST=$(ll-history-context {{issue_id}} 2>/dev/null || true)
```

Each matched correction is a −0.1 signal on the Outcome Confidence Score. Cap: at most 5 corrections included; if 0 matches, Outcome Confidence Score is unaffected.

If invoked within manage-issue: use the research findings already gathered in Phase 1.5.

### Phase 1.5: Pre-Fetch Learning Test Context

See [rubric.md](rubric.md) § Phase 1.5 for the full bash invocation pattern, Learning Test Context block format, and `ll-learning-tests check` status semantics.

### Phase 1.6: Pre-Fetch Program Design Gate (ENH-2852)

Run the deterministic structural linter and capture only the Program Design verdict:

```bash
FC_JSON=$(ll-issues format-check {{issue_id}} --format json 2>/dev/null || true)
PD_GAP=$(echo "$FC_JSON" \
  | python -c "import json,sys; print('; '.join(json.load(sys.stdin).get('program_design_nonspecific', [])))" 2>/dev/null || true)
PD_FAIL=$(ll-issues check-design {{issue_id}} >/dev/null 2>&1 && echo "" || echo "yes")
```

`PD_GAP` is the reason-string detail for display: non-empty means the section is present
but non-specific (prose with no signature-shaped line, or no repo-resolvable `Call Path`
anchor). `PD_FAIL` (ENH-2967, `ll-issues check-design`) is the single owned verdict —
non-empty when the gate fails for any of the three reasons (`PD_GAP`'s non-specific case,
or the section missing/empty entirely); do not re-derive that OR by hand here. Both are
empty/inert when the project has not armed the gate (no
`.ll/program-design-cutover.json` stamp), when the issue is grandfathered, or when it
carries `program_design_not_applicable: true`. Do **not** re-judge specificity yourself;
the CLI is the single source of truth so the verdict is deterministic.

### Phase 1.7: Pre-Fetch Dependencies Gate (BUG-3051)

Resolve each ID in the issue's `blocked_by` frontmatter list and check whether it is
actually resolved:

```bash
DEP_FAIL=""
DEP_ROWS=""
# <!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) for a one-off JSON field extraction, not a reimplemented algorithm -->
BLOCKED_BY=$(ll-issues show {{issue_id}} --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); v=d.get('blocked_by') or []; print(','.join(v) if isinstance(v, list) else v)" 2>/dev/null || true)

if [ -n "$BLOCKED_BY" ]; then
    IFS=',' read -ra DEPS <<< "$BLOCKED_BY"
    for dep in "${DEPS[@]}"; do
        dep=$(echo "$dep" | xargs)
        [ -z "$dep" ] && continue
        # <!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) for a one-off JSON field extraction, not a reimplemented algorithm -->
        dep_status=$(ll-issues show "$dep" --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','unknown').lower())" 2>/dev/null || echo "unknown")
        case "$dep_status" in
            done|completed|cancelled) ;;
            *) DEP_FAIL="yes"; DEP_ROWS+="$dep ($dep_status), " ;;
        esac
    done
fi
```

`ll-issues show --json` emits `status` display-cased (e.g. `"Completed"` for `done`), so the
check lowercases before matching. Per `.claude/CLAUDE.md` § Issue File Format, `deferred` is
explicitly **non-terminal** for `blocked_by`/`depends_on` edges — only `done`/`cancelled`
(displayed as `completed`/`cancelled`) resolve a dependency; anything else (`open`,
`in_progress`, `blocked`, `deferred`) leaves `DEP_FAIL` set. `DEP_FAIL` is empty/inert when the
issue has no `blocked_by` list or every listed ID is resolved.

### Phase 1.8: Pre-Fetch Claim and Parity Gaps (ENH-3047)

Extract the parity and claim gap keys from the same `$FC_JSON` payload Phase 1.6 already
captured — do **not** issue a second `format-check` call:

```bash
# <!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) for a one-off JSON field extraction, not a reimplemented algorithm -->
PARITY_GAP=$(echo "$FC_JSON" | python -c "import json,sys; print('; '.join(json.load(sys.stdin).get('missing_behavior_parity', [])))" 2>/dev/null || true)
# <!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) for a one-off JSON field extraction, not a reimplemented algorithm -->
CLAIM_GAP=$(echo "$FC_JSON" | python -c "import json,sys; d=json.load(sys.stdin); print('; '.join(d.get('stale_symbol_ref', []) + d.get('stale_cli_flag', [])))" 2>/dev/null || true)
# <!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) for a one-off JSON field extraction, not a reimplemented algorithm -->
DECISION_GAP=$(echo "$FC_JSON" | python -c "import json,sys; print('; '.join(json.load(sys.stdin).get('unapplied_decision', [])))" 2>/dev/null || true)
# <!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) for a one-off JSON field extraction, not a reimplemented algorithm -->
STRUCT_GAP=$(echo "$FC_JSON" | python -c "import json,sys; d=json.load(sys.stdin); D={'Summary','Acceptance Criteria'}; print('; '.join(d.get('template_placeholders', []) + d.get('boilerplate', []) + [m for m in d.get('missing', []) if m in D]))" 2>/dev/null || true)
```

`PARITY_GAP` is non-empty when the issue is missing a `### Behavior Parity` subsection
describing what it replaces. `CLAIM_GAP` is non-empty when the issue asserts a symbol or CLI
flag against the codebase that did not resolve (`stale_symbol_ref` + `stale_cli_flag`
combined). `DECISION_GAP` (ENH-3256) is non-empty when the issue records a `> **Selected:**`
decision while a rejected option's discriminating identifier still appears, unmarked, in a
directive section (`unapplied_decision`) — a decision *record* that was never actually
*applied*. All four are empty/inert on the present-but-empty case — an issue with no gaps
leaves Criterion 4/Criterion C's scoring untouched. Do **not** re-judge either signal yourself;
the CLI is the single source of truth for whether a reference resolves or a decision was
applied. `CLAIM_GAP` is **advisory input to Criterion 4 only** — it caps the criterion (see
[rubric.md](rubric.md) Criterion 4) and must not be escalated to a `STOP` verdict, because
forward-looking design/planning claims legitimately do not resolve yet. `DECISION_GAP` is
**advisory input to Criterion C only** — it caps the criterion (see [rubric.md](rubric.md)
Criterion C) and, like `CLAIM_GAP`, must never be escalated to a `STOP` verdict.

`STRUCT_GAP` (ENH-3257) is **advisory input to Criterion 4 only** — it caps the criterion (see
[rubric.md](rubric.md) Criterion 4) and, like `CLAIM_GAP`, must never be escalated to a `STOP`
verdict. It combines `template_placeholders` and `boilerplate` (taken unfiltered) with
`missing`, filtered to the directive allowlist `{Summary, Acceptance Criteria}` — ceremonial
`missing` entries (`Status`, `Impact`, etc.) do not contribute, since a structural-section
absence covered by a stronger hard override elsewhere carries no additional signal here, and
the rest carry no signal about specification quality. Remedy differs by key: `format-check
--fix` repairs `boilerplate` and structurally inserts `missing` sections, but
`template_placeholders` has no `--fix` — it is literal template debris that needs authored
content.

### Phase 2: Five-Point Assessment

Evaluate each criterion and assign a score (0-20 points each):

#### Criterion 1: No Duplicate Implementations (0-20 points)

**What to check**: Whether code already exists that solves this problem.

**Detection method**:
1. Extract key terms from the issue title and summary (function names, feature names, concepts)
2. Use Grep to search for those terms in `{{config.project.src_dir}}`
3. Check `{{config.issues.base_dir}}/completed/` for previously resolved issues with similar titles
4. Search for TODO/FIXME comments that reference the same problem

**Scoring**: See [rubric.md](rubric.md) for the Criterion 1 scoring table.

#### Criterion 2: Architecture Compliance (0-20 points)

**What to check**: Whether the proposed approach fits existing patterns.

**Detection method**:
1. Identify what type of component is being added/modified (skill, command, script, hook, config)
2. Find 2-3 existing examples of the same component type
3. Compare the proposed approach against established patterns:
   - File location matches convention (e.g., skills go in `skills/`, commands in `commands/`)
   - Naming follows project convention (kebab-case directories, SKILL.md/command.md files)
   - Integration points use established mechanisms (Skill tool, Task tool, config references)
4. Check if the issue's "Files to Modify" section aligns with where similar changes were made

**Scoring**: See [rubric.md](rubric.md) for the Criterion 2 scoring table.

#### Criterion 3: Problem Understanding (0-20 points)

Use the type-specific label for this criterion:
- **BUG**: "Root cause identified"
- **FEAT**: "Requirements clarity"
- **ENH**: "Rationale well-understood"
- **EPIC**: "Coordination scope and child issues defined"

**What to check** (type-specific):
- **BUG**: Whether the actual root cause is understood (not just symptoms)
- **FEAT**: Whether requirements are specific and testable (not just "add X")
- **ENH**: Whether current behavior issues and the rationale for change are clearly explained
- **EPIC**: Whether coordination scope is bounded and child issues are enumerated and individually plannable

**Detection method**:
1. For **bugs**: Check issue has a "Problem Analysis" or "Root Cause" section with specific file:line references
2. For **features**: Check issue has clear requirements (not just "add X" but "add X that does Y when Z")
3. For **enhancements**: Check issue explains what's wrong with current behavior and what specifically should change
4. For **epics**: Check the EPIC has a defined coordination scope (what it groups and why), an enumerated list of child issues (via `children:` frontmatter or `parent: EPIC-NNN` references in child issues), and that each child is itself implementable (not a placeholder)
5. Verify claims in the issue against actual code (do referenced files/functions exist? do they behave as described?)

**Scoring** (use the table matching the issue type): See [rubric.md](rubric.md)
for the per-type Criterion 3 scoring tables (BUG / FEAT / ENH / EPIC) and the
note on EPICs as coordination containers.

#### Criterion 4: Issue Well-Specified (0-20 points)

**What to check**: Whether the issue has enough detail to implement without guessing.

**Detection method**:
1. Check for acceptance criteria or "Expected Behavior" section
2. Check for specific files to modify (not just "update the code")
3. Check for scope boundaries ("What We're NOT Doing" or "Out of scope")
4. Check that implementation steps are actionable (not vague like "improve performance")

**Scoring**: See [rubric.md](rubric.md) for the Criterion 4 scoring table.

#### Criterion 5: Dependencies Satisfied (0-20 points)

**What to check**: Whether blocking issues are resolved and required infrastructure exists.

**Detection method**:
1. Check issue for "Blocked By" or "Dependencies" sections
2. If dependencies listed, verify they exist in `{{config.issues.base_dir}}/completed/`
3. Check that files/modules referenced in the issue actually exist
4. Verify any required configuration or infrastructure is in place

**Scoring**: See [rubric.md](rubric.md) for the Criterion 5 scoring table.

### Phase 2b: Outcome Confidence Assessment

After the five-point readiness assessment, evaluate outcome confidence — the probability that implementation will succeed without major problems. This is a separate dimension from readiness.

Evaluate each criterion and assign a score (0-25 points each, max 100):

#### Criterion A: Complexity (0-25 points)

**What to check**: What is the shape of the change — how many distinct sites are touched (Breadth) and how complex is each site change (Depth)?

**Detection method**:

**Breadth** — count of distinct change sites:
1. Count files listed in the issue's "Integration Map" or "Files to Modify" section
2. Check if changes span multiple subsystems (skills, scripts, config, docs)

**Depth** — per-site change complexity, judged on the typical site (not the worst):
1. Read the change descriptions: "substitute", "add row", "schema row", "doc edit" → Mechanical
2. Look for "logic change", "function body", "contained" → Local
3. Look for "shared state", "cross-module", "multi-function" → Moderate
4. Look for "restructure", "rewiring", "contract changes", "architectural" → Deep

**Scoring** (apply both sub-tables and sum **Breadth (0-12 points)** +
**Depth (0-13 points)** for the criterion total). See [rubric.md](rubric.md)
for the full Breadth and Depth scoring tables.

#### Criterion B: Test Coverage (0-25 points)

**What to check**: Are the areas being modified covered by tests?

**Detection method**:
1. For each file in the Integration Map, check if a corresponding test file exists (use Glob for patterns like `tests/test_*.py`, `tests/*_test.py`)
2. For skills/commands (markdown-only), check if integration tests or usage examples exist
3. Note: Skills defined only in `.md` files have no direct unit tests — score based on whether the modified area has any automated validation

**Scoring**: See [rubric.md](rubric.md) for the Criterion B scoring table.

#### Criterion C: Ambiguity (0-25 points)

**What to check**: Are there unresolved design decisions or open questions in the issue?

**Detection method**:
1. Search issue text for ambiguity indicators: "TBD", "TODO", "open question", "decide", "either...or", "Option A/B" without resolution
2. Check if the "Proposed Solution" section presents alternatives without choosing one
3. Check for phrases like "requires design", "suggested", "might include"

**Scoring**: See [rubric.md](rubric.md) for the Criterion C scoring table.

#### Criterion D: Change Surface / Fanout Verifiability (0-25 points)

**What to check**: What is the change's blast radius — and if it's a mechanical sweep, how well-enumerated and verifiable is the fanout?

**Detection method**:
1. Classify the change as **Pattern A** (code blast radius) or **Pattern B** (enumerated mechanical fanout):
   - **Pattern B** applies when ALL of the following are true:
     - The issue body uses language like "all", "every", "across", or "each" alongside a specific list of files
     - The "Files to Touch" section enumerates >5 files — markdown, config, template, **or source-code call sites**
     - Each site receives a uniform, mechanical substitution (e.g., adding a value to a type enum, replacing a regex string, threading one signal through each call site identically) — not a per-site behavioral change
   - **Pattern A** applies in all other cases — function/API callers, code changes where each modified site may behave differently or requires site-specific judgment
2. For **Pattern A**: count references/imports across the codebase using Grep on key Integration Map files; check the issue's "Dependent Files" section for caller count
3. For **Pattern B**: evaluate the verifiability chain — does the issue include an enumerated file list, a verification grep, and an automated wiring test?

**Scoring** (apply the table matching the detected pattern). See
[rubric.md](rubric.md) for both Criterion D tables: **Pattern A — Blast Radius**
(scored by caller count, e.g. `0-2 callers` = isolated) and **Pattern B —
Enumerated Mechanical Fanout** (scored by the verifiability chain: enumerated
sites + `verification grep` + automated completeness test).

### Phase 3: Score and Recommend

**Learning Test Hard Override**: if Phase 1.5 found any `missing` or `refuted` target, output `STOP — ADDRESS GAPS` regardless of aggregate score.

**Program Design Hard Override** (ENH-2852/ENH-2967): if Phase 1.6 set `PD_FAIL` to a non-empty value, output `STOP — ADDRESS GAPS` regardless of aggregate score, and include the reason verbatim from `PD_GAP` under **Gaps to Address** (when `PD_GAP` is itself empty — a missing/empty section rather than a non-specific one — state that directly instead). The remedy is to populate `## Program Design` with the concrete types, signatures, and call path (run `/ll:refine-issue` or `/ll:reconcile-issue`), or — for genuinely trivial work — to set `program_design_not_applicable: true` in the issue frontmatter. Both `PD_*` values are empty/inert whenever the gate is off, so this override is inert in unstamped projects.

**Dependencies Hard Override** (BUG-3051): if Phase 1.7 set `DEP_FAIL` to a non-empty value, output `STOP — ADDRESS GAPS` regardless of aggregate score, listing the unresolved `blocked_by` ID(s) and their status from `DEP_ROWS` under **Gaps to Address**. The remedy is to wait for (or prioritize) the blocking issue(s), or to remove the dependency from `blocked_by` if it no longer applies. `DEP_FAIL` is empty/inert whenever the issue has no `blocked_by` frontmatter list or every listed ID already resolved (`done`/`cancelled`), so this override does not affect issues without unresolved hard dependencies. This is additive to Criterion 5's existing 0-20 scoring, which is unchanged for the non-blocking case ("Minor dependencies unresolved but non-blocking" still scores 15).

Sum all readiness and outcome criterion scores (max 100 each). See [rubric.md](rubric.md) for the score-to-recommendation tables and recommendation tiers. The readiness score drives the go/no-go recommendation; outcome confidence is informational.

### Phase 4: Update Frontmatter

After scoring, persist both aggregate scores and the four per-dimension scores from Phase 2b into the issue file's YAML frontmatter via the CLI. Use `Bash` to run:

```bash
ll-issues set-scores [ISSUE-ID] \
  --confidence [confidence_score] \
  --outcome [outcome_confidence] \
  --score-complexity [score_A] \
  --score-test-coverage [score_B] \
  --score-ambiguity [score_C] \
  --score-change-surface [score_D]
```

Replace `[ISSUE-ID]` with the actual issue identifier (e.g., `BUG-1307`) and the bracketed placeholders with the integer values from Phase 2b and Phase 3.

The four `score_*` values are the per-criterion integer scores (0–25 each):
- `--score-complexity` — Criterion A score
- `--score-test-coverage` — Criterion B score
- `--score-ambiguity` — Criterion C score
- `--score-change-surface` — Criterion D score

The CLI writes idempotently: existing fields are overwritten, unrelated frontmatter fields are preserved, and missing frontmatter is created from scratch. Do **not** use the `Edit` tool to write these fields — the CLI is the single source of truth for score persistence and is much harder to accidentally skip.

### Phase 4.5: Findings Write-Back

**Skip this phase if**: `CHECK_MODE` is true (no writes in check mode).

After presenting the output, determine whether there are findings to write back. Track `HAS_FINDINGS=false`; set to `true` if any of the following have content:
- **Concerns** (present when readiness tier is PROCEED WITH CAUTION)
- **Gaps to Address** (present when readiness score < 70)
- **Outcome Risk Factors** (present when outcome confidence < config.commands.confidence_gate.outcome_threshold, default: 75)

If `HAS_FINDINGS` is false: skip (clean bill of health — no update needed).

If `HAS_FINDINGS` is true, append a `## Confidence Check Notes` section to the issue file using the Edit tool. Insert it before `## Session Log` (or before `## Status` if no session log exists):

See [rubric.md](rubric.md) § Confidence Check Notes template for the exact
section to append.

After appending findings (or skipping if no findings), stage the updated issue file:

```bash
git add "[issue-file-path]"
```

After the findings write-back step, append a session log entry to the issue file. Use the Bash tool:

```bash
ll-issues append-log <path-to-issue-file> /ll:confidence-check
```

If `ll-issues` is not available, fall back to manually appending with **exactly** this format (backticks required). If `## Session Log` already exists, append below the header; if not, add before the `## Status` footer:

```
- `/ll:confidence-check` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

### Phase 4.6: Flag Write-Back

**Skip this phase if**: `CHECK_MODE` is true (no writes in check mode).

Phase 4.5 already wrote Outcome Risk Factors findings to the issue's `## Confidence Check Notes` section (or determined there were none to write). Delegate turning those findings into `decision_needed` / `missing_artifacts` / `implementation_order_risk` / `spike_needed` frontmatter flags to the CLI — the phrase-list + numeric-gate rules (`FLAG_RULES`, `scripts/little_loops/cli/issues/set_flags.py`) are the single source of truth, not this skill (ENH-2946):

```bash
ll-issues set-flags [ISSUE-ID]
```

With no `--from-notes`, this reads the issue's own `## Confidence Check Notes` section (the one Phase 4.5 just wrote) and stamps whichever flags matched. It only has effect when that section shows outcome-risk factors (`outcome_confidence` below `config.commands.confidence_gate.outcome_threshold`) — if Phase 4.5 wrote nothing, no phrase can match. It is **set-only**: an existing `true` flag is never cleared by a re-run whose notes no longer match; clearing stays owned by `/ll:decide-issue`.

Do **not** re-scan for signal phrases yourself, and do **not** use the Edit tool to write these flags — the CLI is the single source of truth (same precedent as Phase 4's `set-scores` write-back above). Log the CLI's own output to the terminal.

**External-API note**: `set-flags` does not attempt to distinguish an unproven *internal* mechanism from a third-party package/SDK/external API surface (its module docstring documents this as an intentional non-port — that judgment call stays here). If `spike_needed` comes back `true` but the matched risk factor actually names an external API surface, treat it as `/ll:explore-api` + `learning_tests_required` territory instead: apply the same exclusion heuristic as `/ll:refine-issue` Step 7.5 learning-target extraction (mirrored from `learning_tests/extractor.py:_EXTRACTION_PROMPT` — project-internal code, Python builtins, and contract-stable stdlib are excluded; anything else outside those exclusions is external) and route via `/ll:decide-issue` to clear the flag rather than spiking.

### Auto Mode Behavior

When `AUTO_MODE` is true: skip any AskUserQuestion prompts (make autonomous
decisions), do not pause for user confirmation between issues in batch mode, use
defaults for any decisions that would normally require input, and continue
processing even if individual issues score below threshold. When `AUTO_MODE` is
false (interactive, single issue): behavior unchanged.

### Check Mode Behavior (--check)

When `CHECK_MODE` is true, run as an FSM loop evaluator:

1. Run all evaluation logic (readiness + outcome confidence scoring) without writing to issue frontmatter
2. For each issue: if readiness score < 70, print `[ID] check: score N/100 (below threshold)`; if >= 70, skip (passes gate)
3. After all issues: if any failed, print `N issues not ready` then `exit 1`; if all passed, print `All issues pass confidence check` then `exit 0`

This integrates with FSM `evaluate: type: exit_code` routing (0=success, 1=failure, 2+=error).

## Output Format, Integration & Examples

See [reference.md](reference.md) for the single-issue and `--all` batch
output-format sections, `/ll:manage-issue` integration notes, worked examples,
and additional resources. Full scoring rubric tables and output-format templates
live in [rubric.md](rubric.md).
