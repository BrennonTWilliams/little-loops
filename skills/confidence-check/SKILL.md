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
if [[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]]; then AUTO_MODE=true; fi

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

- **issue_id** (optional): Issue ID to evaluate (e.g., `ENH-277`, `BUG-042`)
  - If provided, evaluates that specific issue
  - If omitted with `--all`, processes all active issues
  - If omitted without `--all`, expects to be invoked within a manage-issue context

- **flags** (optional): Command behavior flags
  - `--auto` — Non-interactive mode (skip user prompts, use defaults)
  - `--all` — Evaluate all active issues (bugs/, features/, enhancements/), skip completed/ and deferred/. Implies `--auto`.
  - `--check` — Check-only mode for FSM loop evaluators. Run all evaluation logic without writes, print one line per failing issue (`[ID] check: score N/100 (below threshold)`), exit 1 if any fail, exit 0 if all pass. Implies `--auto`.
  - `--sprint <name>` — Scope evaluation to only the issues listed in the named sprint definition (`.sprints/<name>.yaml`). Implies `--auto`. Cannot be combined with `--all`.

## Issue Discovery

### Single Issue Mode (default)

If `ISSUE_ID` is provided, locate the issue file by ID:

```bash
FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)

if [ -z "$FILE" ]; then
    echo "Error: Issue $ISSUE_ID not found"
    exit 1
fi
```

If no `ISSUE_ID` and not `--all`: expect to be invoked within a manage-issue context where research findings are already available.

### Batch Mode (--all)

When `ALL_MODE` is true, collect all active issue files:

```bash
declare -a ISSUE_FILES
for dir in {{config.issues.base_dir}}/{bugs,features,enhancements}/; do
    if [ -d "$dir" ]; then
        while IFS= read -r file; do
            ISSUE_FILES+=("$file")
        done < <(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | sort)
    fi
done

if [[ ${#ISSUE_FILES[@]} -eq 0 ]]; then
    echo "No active issues found"
    exit 0
fi

echo "Found ${#ISSUE_FILES[@]} active issues to evaluate"
```

When in batch mode, iterate through `ISSUE_FILES` and run the full workflow (Phases 1-4) for each issue, collecting results for the batch summary.

### Sprint Mode (--sprint)

When `SPRINT_NAME` is provided, load issues from the sprint definition instead of scanning all active directories:

```bash
SPRINT_FILE=".sprints/${SPRINT_NAME}.yaml"
if [ ! -f "$SPRINT_FILE" ]; then
    echo "Error: Sprint '$SPRINT_NAME' not found at $SPRINT_FILE"
    exit 1
fi

# Read the sprint YAML and resolve each issue ID to a file path
# The issues: key is a flat list of bare ID strings (e.g., ENH-175, FEAT-808)
# Use the Read tool on $SPRINT_FILE to get the issues list, then resolve each ID:
declare -a ISSUE_FILES
# For each ID in the sprint's issues: list:
for id in <sprint-issue-ids>; do
    FILE=$(ll-issues path "${id}" 2>/dev/null)
    if [ -n "$FILE" ]; then
        ISSUE_FILES+=("$FILE")
    else
        echo "Warning: Sprint issue $id not found (skipping)"
    fi
done

if [[ ${#ISSUE_FILES[@]} -eq 0 ]]; then
    echo "No active issues found for sprint '$SPRINT_NAME'"
    exit 0
fi

echo "Sprint: $SPRINT_NAME (${#ISSUE_FILES[@]} issues)"
```

After building `ISSUE_FILES`, iterate and evaluate exactly as in Batch Mode. The batch summary header should read `Sprint: <name> (N issues)` instead of `--all mode`.

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

### Phase 2: Five-Point Assessment

Evaluate each criterion and assign a score (0-20 points each):

#### Criterion 1: No Duplicate Implementations (0-20 points)

**What to check**: Whether code already exists that solves this problem.

**Detection method**:
1. Extract key terms from the issue title and summary (function names, feature names, concepts)
2. Use Grep to search for those terms in `{{config.project.src_dir}}`
3. Check `{{config.issues.base_dir}}/completed/` for previously resolved issues with similar titles
4. Search for TODO/FIXME comments that reference the same problem

**Scoring**:
| Finding | Score |
|---------|-------|
| No existing implementation found | 20 |
| Related code exists but doesn't solve the problem | 15 |
| Partial implementation exists (needs extension, not duplication) | 10 |
| Near-complete implementation already exists | 0 |

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

**Scoring**:
| Finding | Score |
|---------|-------|
| Approach matches established patterns completely | 20 |
| Mostly matches, minor deviations justified | 15 |
| Partially matches, some concerns about fit | 10 |
| Contradicts established patterns or creates parallel pathways | 0 |

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

**Scoring** (use the table matching the issue type):

**BUG**:
| Finding | Score |
|---------|-------|
| Root cause clearly identified with code references that check out | 20 |
| Root cause described but code references not fully verified | 15 |
| Symptoms described but root cause is inferred/assumed | 10 |
| Only symptoms described, no analysis of underlying cause | 0 |

**FEAT**:
| Finding | Score |
|---------|-------|
| Concrete requirements with scenarios and testable acceptance criteria | 20 |
| Requirements present but some vague or missing edge cases | 15 |
| High-level requirements, significant details need inference | 10 |
| Vague "add X" with no specifics about behavior or scenarios | 0 |

**ENH**:
| Finding | Score |
|---------|-------|
| Current behavior issues explained with specific changes and rationale | 20 |
| Rationale present but some changes underspecified | 15 |
| General dissatisfaction described, specific changes partially clear | 10 |
| Only symptoms noted, no analysis of what should change or why | 0 |

**EPIC**:
| Finding | Score |
|---------|-------|
| Coordination scope clearly bounded; all child issues enumerated, each individually plannable | 20 |
| Scope clear; most children enumerated but 1-2 are placeholders or vague | 15 |
| Scope present but child issues partially listed; significant decomposition still needed | 10 |
| Vague coordination intent with no enumerated children, or scope unbounded | 0 |

> **Note**: EPICs are coordination containers, not directly implementable. A high readiness score for an EPIC means it is ready to drive a sprint or hand off children to `/ll:manage-issue`, NOT that it is itself ready to implement.

#### Criterion 4: Issue Well-Specified (0-20 points)

**What to check**: Whether the issue has enough detail to implement without guessing.

**Detection method**:
1. Check for acceptance criteria or "Expected Behavior" section
2. Check for specific files to modify (not just "update the code")
3. Check for scope boundaries ("What We're NOT Doing" or "Out of scope")
4. Check that implementation steps are actionable (not vague like "improve performance")

**Scoring**:
| Finding | Score |
|---------|-------|
| Clear acceptance criteria, specific files, defined scope | 20 |
| Most details present, 1-2 minor gaps fillable from context | 15 |
| Key details missing but inferrable from codebase research | 10 |
| Vague requirements, significant guesswork needed | 0 |

#### Criterion 5: Dependencies Satisfied (0-20 points)

**What to check**: Whether blocking issues are resolved and required infrastructure exists.

**Detection method**:
1. Check issue for "Blocked By" or "Dependencies" sections
2. If dependencies listed, verify they exist in `{{config.issues.base_dir}}/completed/`
3. Check that files/modules referenced in the issue actually exist
4. Verify any required configuration or infrastructure is in place

**Scoring**:
| Finding | Score |
|---------|-------|
| No dependencies, or all dependencies satisfied | 20 |
| Minor dependencies unresolved but non-blocking | 15 |
| Some dependencies unresolved, workarounds possible | 10 |
| Critical dependencies unresolved, cannot proceed | 0 |

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

**Scoring** (apply both tables and sum Breadth + Depth for the criterion total):

**Breadth (0-12 points)** — number of distinct change sites:
| Finding | Score |
|---------|-------|
| 1-2 sites | 12 |
| 3-5 sites | 9 |
| 6-15 sites | 5 |
| 16+ sites | 0 |

**Depth (0-13 points)** — per-site change complexity:
| Finding | Score |
|---------|-------|
| Mechanical/uniform — text substitution, type-list addition, schema row, doc edit | 13 |
| Local — small function or method body, contained logic change | 9 |
| Moderate — multi-function or cross-module logic with shared state | 5 |
| Deep — architectural rewiring, control-flow restructuring, contract changes | 0 |

#### Criterion B: Test Coverage (0-25 points)

**What to check**: Are the areas being modified covered by tests?

**Detection method**:
1. For each file in the Integration Map, check if a corresponding test file exists (use Glob for patterns like `tests/test_*.py`, `tests/*_test.py`)
2. For skills/commands (markdown-only), check if integration tests or usage examples exist
3. Note: Skills defined only in `.md` files have no direct unit tests — score based on whether the modified area has any automated validation

**Scoring**:
| Finding | Score |
|---------|-------|
| All modified modules have corresponding tests or validation | 25 |
| Most modified modules are tested (>50%) | 18 |
| Few modules tested, failures may go undetected | 10 |
| No tests exist for modified areas | 0 |

#### Criterion C: Ambiguity (0-25 points)

**What to check**: Are there unresolved design decisions or open questions in the issue?

**Detection method**:
1. Search issue text for ambiguity indicators: "TBD", "TODO", "open question", "decide", "either...or", "Option A/B" without resolution
2. Check if the "Proposed Solution" section presents alternatives without choosing one
3. Check for phrases like "requires design", "suggested", "might include"

**Scoring**:
| Finding | Score |
|---------|-------|
| No ambiguity — solution is fully specified with single clear approach | 25 |
| Minor open questions that can be resolved during implementation | 18 |
| Several design decisions left open, will require judgment calls | 10 |
| Fundamental approach unclear, multiple competing options unresolved | 0 |

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

**Scoring** (apply the table matching the detected pattern):

**Pattern A — Blast Radius** (code changes, callers, API surface):
| Finding | Score |
|---------|-------|
| 0-2 callers/dependents — isolated change | 25 |
| 3-5 callers/dependents — manageable surface | 18 |
| 6-10 callers/dependents — broad surface | 10 |
| 11+ callers/dependents — very wide blast radius | 0 |

**Pattern B — Enumerated Mechanical Fanout** (uniform substitutions across an enumerated file list):
| Finding | Score |
|---------|-------|
| Sites enumerated + verification grep + automated test asserting completeness | 25 |
| Sites enumerated + verification grep, no automated test | 18 |
| Sites enumerated, no verification command | 10 |
| Sites not enumerated (unbounded sweep) | 0 |

### Phase 3: Score and Recommend

Sum all readiness criterion scores (max 100) and all outcome criterion scores (max 100).

**Readiness Score** — determines go/no-go:

| Total Score | Recommendation | Action |
|-------------|---------------|--------|
| **90-100** | PROCEED | Begin implementation |
| **70-89** | PROCEED WITH CAUTION | List specific concerns, then proceed |
| **50-69** | STOP — ADDRESS GAPS | List gaps that must be resolved before implementation |
| **0-49** | STOP — NOT READY | Mark issue as NOT_READY with specific reasons |

**Outcome Confidence** — estimates implementation risk:

| Total Score | Label | Interpretation |
|-------------|-------|----------------|
| **80-100** | HIGH CONFIDENCE | Implementation likely to succeed cleanly |
| **60-79** | MODERATE | Expect some iteration or surprises |
| **40-59** | LOW | Expect significant iteration; plan extra time |
| **0-39** | VERY LOW | High implementation risk; consider de-risking first |

Combine both scores in the final output. The readiness score drives the go/no-go recommendation; the outcome confidence is informational context for planning.

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

After Phase 4.5 writes Outcome Risk Factors, scan the generated risk-factor content for signal phrases that indicate implementation ordering advice — a recommendation to create tests or scripts before running the main feature — rather than a true pre-condition wiring gap. This phase also fires when Phase 4.7's co-deliverable suppression blocked a `missing_artifacts` write.

This phase only has effect when Phase 4.5 produced Outcome Risk Factors (i.e., `HAS_FINDINGS` is true and `outcome_confidence < config.commands.confidence_gate.outcome_threshold`); if Phase 4.5 was skipped, no signal phrases will be present.

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

After Phase 4.5 writes Outcome Risk Factors, scan the generated risk-factor content for signal phrases that indicate a penalized file surface — but only when the change is a Pattern B mechanical fanout with a complete verification chain. When that combination is detected, suppress the misleading risk phrase.

This phase only has effect when Phase 4.5 produced Outcome Risk Factors (i.e., `HAS_FINDINGS` is true and `outcome_confidence < config.commands.confidence_gate.outcome_threshold`); if Phase 4.5 was skipped, no signal phrases will be present.

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

When `AUTO_MODE` is true:
- Skip any AskUserQuestion prompts (make autonomous decisions)
- Do not pause for user confirmation between issues in batch mode
- Use defaults for any decisions that would normally require user input
- Continue processing even if individual issues score below threshold

When `AUTO_MODE` is false (interactive, single issue):
- Behavior unchanged from current implementation

### Check Mode Behavior (--check)

When `CHECK_MODE` is true, run as an FSM loop evaluator:

1. Run all evaluation logic (readiness + outcome confidence scoring) without writing to issue frontmatter
2. For each issue evaluated:
   - If readiness score < 70: print `[ID] check: score N/100 (below threshold)`
   - If readiness score >= 70: skip (passes gate)
3. After all issues evaluated:
   - If any failed: print `N issues not ready`, then `exit 1`
   - If all passed: print `All issues pass confidence check`, then `exit 0`

This integrates with FSM `evaluate: type: exit_code` routing (0=success, 1=failure, 2+=error).

## Output Format

```
================================================================================
CONFIDENCE CHECK: [ISSUE-ID]
================================================================================

## READINESS SCORES

| Criterion                  | Score | Details                    |
|---------------------------|-------|----------------------------|
| No duplicate implementations | XX/20 | [Brief finding]           |
| Architecture compliance     | XX/20 | [Brief finding]           |
| [Type-specific Criterion 3 label] | XX/20 | [Brief finding]           |
| Issue well-specified        | XX/20 | [Brief finding]           |
| Dependencies satisfied      | XX/20 | [Brief finding]           |

## OUTCOME CONFIDENCE SCORES

| Criterion       | Score | Details                              |
|-----------------|-------|--------------------------------------|
| Complexity      | XX/25 | [Brief finding]                      |
| Test coverage   | XX/25 | [Brief finding]                      |
| Ambiguity       | XX/25 | [Brief finding]                      |
| Change surface  | XX/25 | [Brief finding]                      |

## SUMMARY

READINESS SCORE:    XX/100 → [PROCEED | PROCEED WITH CAUTION | STOP — ADDRESS GAPS | STOP — NOT READY]
OUTCOME CONFIDENCE: XX/100 → [HIGH CONFIDENCE | MODERATE | LOW | VERY LOW]

## RECOMMENDATION: [readiness tier]

### Concerns (if any)
- [Specific concern with reference]

### Gaps to Address (if readiness score < 70)
- [Gap 1: what's missing and how to fix]
- [Gap 2: what's missing and how to fix]

### Escalation (if readiness score < 70 after 2+ prior refinement passes)

- **Unresolved options (score_ambiguity ≤ 10)**: Run `/ll:decide-issue [ISSUE_ID]` — competing implementation options are blocking readiness; selecting one clears the ambiguity.
- **Issue too large (score_ambiguity > 10)**: Run `/ll:issue-size-review [ISSUE_ID]` — a persistent broad readiness gap after multiple refinement passes often signals the issue needs decomposition rather than more research.

### Outcome Risk Factors (if outcome confidence < outcome_threshold)
- [Risk 1: what may cause implementation difficulty]
- [Risk 2: mitigation suggestion]

================================================================================
```

## Batch Output Format (--all mode)

When processing all issues, output a summary table after all individual evaluations:

```
================================================================================
CONFIDENCE CHECK BATCH REPORT: --all mode | Sprint: <name> (N issues)
================================================================================

## READINESS SUMMARY
- Issues evaluated: XX
- PROCEED (90-100): X
- PROCEED WITH CAUTION (70-89): X
- STOP — ADDRESS GAPS (50-69): X
- STOP — NOT READY (0-49): X

## OUTCOME CONFIDENCE SUMMARY
- HIGH CONFIDENCE (80-100): X
- MODERATE (60-79): X
- LOW (40-59): X
- VERY LOW (0-39): X

## RESULTS

| Issue ID | Title | Readiness | Outcome | Recommendation | Key Concern |
|----------|-------|-----------|---------|----------------|-------------|
| BUG-001 | Fix login | 85/100 | 72/100 | PROCEED WITH CAUTION | Partial impl exists |
| FEAT-042 | Add dark mode | 92/100 | 90/100 | PROCEED | — |
| ENH-089 | Improve perf | 55/100 | 35/100 | STOP — ADDRESS GAPS | Vague reqs, high risk |

## FRONTMATTER UPDATES
- .issues/bugs/P2-BUG-001-fix-login.md — confidence_score: 85, outcome_confidence: 72
- .issues/features/P1-FEAT-042-add-dark-mode.md — confidence_score: 92, outcome_confidence: 90
- .issues/enhancements/P3-ENH-089-improve-perf.md — confidence_score: 55, outcome_confidence: 35

================================================================================
```

## Integration with /ll:manage-issue

This skill is referenced in `/ll:manage-issue` Phase 2 as a recommended pre-planning step. When invoked within manage-issue:

- Uses research findings from Phase 1.5 (no redundant searching)
- Readiness score >=70: proceed to plan creation
- Readiness score <70: stop and report gaps (manage-issue marks as INCOMPLETE)
- Non-blocking by default — can be skipped if user prefers
- The manage-issue Phase 2.5 confidence gate reads `confidence_score` (readiness) from frontmatter — the `outcome_confidence` field is informational and does not affect the gate

## Examples

### Single Issue

| Scenario | Readiness | Outcome | Interpretation |
|----------|-----------|---------|----------------|
| Well-specified bug, 1 file, tests exist | 90: PROCEED | 90: HIGH | Strong go signal |
| Vague feature, 20 files, no tests | 45: STOP | 20: VERY LOW | Refine issue first |
| Ready enhancement, 8 files, some ambiguity | 85: PROCEED WITH CAUTION | 50: LOW | Start, but expect iteration |
| Blocked dependency, simple fix | 55: STOP | 80: HIGH | Unblock first, then easy win |

### Criterion D Pattern A vs Pattern B

The following examples illustrate how Criterion D distinguishes code blast radius (Pattern A) from a fully-enumerated mechanical fanout (Pattern B).

**Pattern A — code blast radius** (function renamed; callers in 15 files across 3 modules):
| Criterion | Score | Rationale |
|-----------|-------|-----------|
| Change Surface / Fanout Verifiability | 0/25 | 15 callers across modules — very wide blast radius; each call site may behave differently |

**Pattern B — enumerated mechanical fanout** (43 markdown files; uniform `BUG\|FEAT\|ENH` → `BUG\|FEAT\|ENH\|EPIC` regex substitution; verification grep provided; doc-wiring pytest specified):
| Criterion | Score | Rationale |
|-----------|-------|-----------|
| Change Surface / Fanout Verifiability | 25/25 | All 43 sites enumerated in "Files to Touch"; verification grep proves completeness; automated wiring test specified — full Pattern B chain present |

**Pattern B — enumerated fanout, no verification** (12 config files; uniform field addition; file list present but no grep or test):
| Criterion | Score | Rationale |
|-----------|-------|-----------|
| Change Surface / Fanout Verifiability | 10/25 | Sites enumerated but no verification command — completeness unproven |

### Criterion A Breadth × Depth

The following examples illustrate how Criterion A distinguishes wide-shallow sweeps from narrow-deep refactors.

**Wide-shallow sweep** (43-file uniform regex substitution; each site is a one-line text replacement; files enumerated in "Files to Touch"):
| Criterion | Score | Rationale |
|-----------|-------|-----------|
| Complexity — Breadth | 0/12 | 43 sites — exceeds 16+, wide enumeration |
| Complexity — Depth | 13/13 | Mechanical: uniform text substitution across all sites |
| **Criterion A total** | **13/25** | Breadth 0 + Depth 13 — correctly reflects low per-site risk despite file count |

**Narrow-deep refactor** (3-file change; restructures the dependency injection core; alters shared contracts across callers):
| Criterion | Score | Rationale |
|-----------|-------|-----------|
| Complexity — Breadth | 9/12 | 3 sites — small enumeration |
| Complexity — Depth | 0/13 | Deep: architectural rewiring with contract changes |
| **Criterion A total** | **9/25** | Breadth 9 + Depth 0 — correctly scores lower than file count alone would suggest |

**Simple isolated change** (1-2 files; small method body update; no shared state):
| Criterion | Score | Rationale |
|-----------|-------|-----------|
| Complexity — Breadth | 12/12 | 1-2 sites — fully isolated |
| Complexity — Depth | 13/13 | Mechanical/Local: contained method body change |
| **Criterion A total** | **25/25** | Full score — common case unchanged |

### Usage Patterns

```bash
# Single issue, interactive
/ll:confidence-check ENH-277

# Single issue, non-interactive
/ll:confidence-check ENH-277 --auto

# All active issues (--auto is implied)
/ll:confidence-check --all

# All active issues, explicit --auto (also works)
/ll:confidence-check --all --auto

# Check-only mode for FSM loop evaluators (exit 0 if all pass, exit 1 if any fail)
/ll:confidence-check --all --check
/ll:confidence-check ENH-277 --check

# Sprint-scoped: evaluate only the issues in a named sprint
/ll:confidence-check --sprint my-sprint
/ll:confidence-check --sprint my-sprint --auto
```
