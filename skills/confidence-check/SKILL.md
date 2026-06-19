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
metadata:
  short-description: Use when asked for a pre-implementation confidence check or whether an issue is 
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
     - The "Files to Touch" section enumerates >5 markdown, config, or template files
     - Each site receives a uniform substitution (e.g., adding a value to a type enum, replacing a regex string)
   - **Pattern A** applies in all other cases — function/API callers, code changes where each modified site may behave differently
2. For **Pattern A**: count references/imports across the codebase using Grep on key Integration Map files; check the issue's "Dependent Files" section for caller count
3. For **Pattern B**: evaluate the verifiability chain — does the issue include an enumerated file list, a verification grep, and an automated wiring test?

**Scoring** (apply the table matching the detected pattern). See
[rubric.md](rubric.md) for both Criterion D tables: **Pattern A — Blast Radius**
(scored by caller count, e.g. `0-2 callers` = isolated) and **Pattern B —
Enumerated Mechanical Fanout** (scored by the verifiability chain: enumerated
sites + `verification grep` + automated completeness test).

### Phase 3: Score and Recommend

**Learning Test Hard Override**: if Phase 1.5 found any `missing` or `refuted` target, output `STOP — ADDRESS GAPS` regardless of aggregate score.

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

```markdown
## Confidence Check Notes

_Added by `/ll:confidence-check` on [YYYY-MM-DD]_

**Readiness Score**: [N]/100 → [tier label]
**Outcome Confidence**: [N]/100 → [label]

### Concerns
- [concern 1]
- [concern 2]

### Gaps to Address
- [gap 1]
_(omit this subsection if no gaps)_

### Outcome Risk Factors
- [risk 1 — phrase by dominant axis: "deep per-site complexity" for low-Depth issues, "broad enumeration across N sites" for high-Breadth issues]
_(omit this subsection if no risk factors)_
```

After appending findings (or skipping if no findings), stage the updated issue file:

```bash
git add "[issue-file-path]"
```

After the findings write-back step, append a session log entry to the issue file:

```markdown
## Session Log
- `/ll:confidence-check` - [ISO timestamp] - `[path to current session JSONL]`
```

To find the current session JSONL: look in `~/.claude/projects/` for the directory matching the current project (path encoded with dashes), find the most recently modified `.jsonl` file (excluding `agent-*`). If `## Session Log` already exists, append below the header. If not, add before `## Status` footer.

### Phase 4.6: Decision-Needed Flag

**Skip this phase if**: `CHECK_MODE` is true (no writes in check mode).

After Phase 4.5 writes Outcome Risk Factors, scan the generated risk-factor content for signal phrases that indicate an unresolved decision requiring resolution before implementation. This phase only has effect when Phase 4.5 produced Outcome Risk Factors (i.e., `HAS_FINDINGS` is true and `outcome_confidence < config.commands.confidence_gate.outcome_threshold`); if Phase 4.5 was skipped, no signal phrases will be present.

**Signal phrases** (any match triggers the flag):
- "open decision"
- "unresolved decision"
- "resolve before implementing"
- "decision point"
- "either/or"
- "either...or"
- "either…or"
- "resolve before starting"
- "open question"
- "Option A/B"
- "Option A or"

If any signal phrase is found in the Outcome Risk Factors content written by Phase 4.5:

1. Use the Edit tool to update `decision_needed: true` in the issue frontmatter `---` block (same inline `---` block replacement pattern as Phase 4)
2. **Idempotency**: skip the write if `decision_needed` is already `true`
3. Log to terminal output: `✓ decision_needed set to true — unresolved decision detected in Outcome Risk Factors`

If no signal phrase is found, leave `decision_needed` unchanged.

### Phase 4.7: Missing-Artifacts Flag

**Skip this phase if**: `CHECK_MODE` is true (no writes in check mode).

After Phase 4.5 writes Outcome Risk Factors, scan the generated risk-factor content for signal phrases that indicate an absent file, unwired component, or missing artifact causing low outcome confidence. This phase only has effect when Phase 4.5 produced Outcome Risk Factors (i.e., `HAS_FINDINGS` is true and `outcome_confidence < config.commands.confidence_gate.outcome_threshold`); if Phase 4.5 was skipped, no signal phrases will be present.

**Signal phrases** (any match triggers the flag):
- "not yet created"
- "does not exist"
- "needs wiring"
- "missing artifact"
- "absent"
- "unwired component"

If any signal phrase is found in the Outcome Risk Factors content written by Phase 4.5:

**Co-Deliverable Suppression**: Before setting the flag, read the issue body for a `### Files to Create` subsection under `## Integration Map`. If the file name mentioned in the risk factor appears in that section, the absent file is a co-deliverable of this issue (it will be created as part of delivering the feature) — do NOT set `missing_artifacts: true`. Instead, proceed to Phase 4.9 to capture the implementation-order concern.

If the absent file is NOT listed in `### Files to Create` (i.e., it is a genuine pre-condition that must exist before implementation can start):

1. Use the Edit tool to update `missing_artifacts: true` in the issue frontmatter `---` block (same inline `---` block replacement pattern as Phase 4)
2. **Idempotency**: skip the write if `missing_artifacts` is already `true`
3. Log to terminal output: `✓ missing_artifacts set to true — absent file or unwired component detected in Outcome Risk Factors`

If no signal phrase is found, leave `missing_artifacts` unchanged.

### Phase 4.9: Implementation-Order Risk Flag

**Skip this phase if**: `CHECK_MODE` is true (no writes in check mode).

After Phase 4.5 writes Outcome Risk Factors, scan the generated risk-factor content for signal phrases that indicate implementation ordering advice — a recommendation to create tests or scripts before running the main feature — rather than a true pre-condition wiring gap. This phase also fires when Phase 4.7's co-deliverable suppression blocked a `missing_artifacts` write. (Only fires when Phase 4.5 produced Outcome Risk Factors; otherwise no signal phrases are present.)

**Signal phrases** (any match triggers the flag):
- "implement tests first"
- "write tests before"
- "test-first"
- "co-deliverable"
- "tests are co-deliverables"
- "implement first so"

If any signal phrase is found in the Outcome Risk Factors content written by Phase 4.5:

1. Use the Edit tool to update `implementation_order_risk: true` in the issue frontmatter `---` block (same inline `---` block replacement pattern as Phase 4)
2. **Idempotency**: skip the write if `implementation_order_risk` is already `true`
3. Log to terminal output: `✓ implementation_order_risk set to true — implementation ordering advice detected in Outcome Risk Factors`

If no signal phrase is found, leave `implementation_order_risk` unchanged.

### Phase 4.8: Large-File-Surface Suppression

**Skip this phase if**: `CHECK_MODE` is true (no writes in check mode).

After Phase 4.5 writes Outcome Risk Factors, scan the generated risk-factor content for signal phrases that indicate a penalized file surface — but only when the change is a Pattern B mechanical fanout with a complete verification chain. When that combination is detected, suppress the misleading risk phrase. (Only fires when Phase 4.5 produced Outcome Risk Factors; otherwise no signal phrases are present.)

**Signal phrases** (any match triggers the suppression check):
- "large file surface"
- "wide change surface"
- "many files touched"
- "broad surface area"

If any signal phrase is found in the Outcome Risk Factors content written by Phase 4.5, AND the issue qualifies as Pattern B (enumerated file list + verification grep present in the issue body):

1. Use the Edit tool to insert `mechanical_fanout_suppressed: true` into the issue frontmatter `---` block (after `score_change_surface` if present, otherwise alongside the other score fields)
2. **Idempotency**: skip the write if `mechanical_fanout_suppressed` is already `true`
3. Log to terminal output: `✓ mechanical_fanout_suppressed set to true — Pattern B fanout with verification chain detected; large-surface risk phrase suppressed`

If no signal phrase is found, or if the issue does not qualify as Pattern B, leave frontmatter unchanged.

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

## Output Format

Emit the single-issue report (`CONFIDENCE CHECK: [ISSUE-ID]` banner, READINESS
SCORES table, OUTCOME CONFIDENCE SCORES table, SUMMARY, RECOMMENDATION, and the
conditional Concerns / Gaps to Address / Escalation / Outcome Risk Factors
subsections). See [rubric.md](rubric.md) for the exact output-format template.

## Batch Output Format (--all mode)

When processing all issues, output a summary table after all individual
evaluations (`CONFIDENCE CHECK BATCH REPORT` banner, READINESS SUMMARY, OUTCOME
CONFIDENCE SUMMARY, RESULTS table, FRONTMATTER UPDATES). See
[rubric.md](rubric.md) for the exact batch output-format template.

## Integration with /ll:manage-issue

This skill is referenced in `/ll:manage-issue` Phase 2 as a recommended pre-planning step. When invoked within manage-issue:

- Uses research findings from Phase 1.5 (no redundant searching)
- Readiness score >=70: proceed to plan creation
- Readiness score <70: stop and report gaps (manage-issue marks as INCOMPLETE)
- Non-blocking by default — can be skipped if user prefers
- The manage-issue Phase 2.5 confidence gate reads `confidence_score` (readiness) from frontmatter — the `outcome_confidence` field is informational and does not affect the gate

## Examples

See [rubric.md](rubric.md) for worked examples: the single-issue scenario table,
the Criterion D Pattern A vs Pattern B walkthroughs, the Criterion A
Breadth × Depth walkthroughs, and the CLI usage patterns.

## Additional Resources

- [rubric.md](rubric.md) — full scoring rubric tables (Phase 2 readiness
  criteria, Phase 2b outcome criteria, Phase 3 score-to-recommendation tables),
  the single-issue and `--all` output-format templates, and worked examples.
