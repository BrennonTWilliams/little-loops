---
description: |
  Use when the user asks for a pre-implementation confidence check, wants to evaluate readiness before coding, check implementation risk, or asks "is this issue ready to implement?" Produces dual scores: Readiness (go/no-go) and Outcome Confidence (implementation risk).

  Trigger keywords: "confidence check", "pre-implementation check", "ready to implement", "implementation readiness", "confidence score", "outcome confidence"
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(find:*)
  - Bash(git:*)
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

**What to check** (type-specific):
- **BUG**: Whether the actual root cause is understood (not just symptoms)
- **FEAT**: Whether requirements are specific and testable (not just "add X")
- **ENH**: Whether current behavior issues and the rationale for change are clearly explained

**Detection method**:
1. For **bugs**: Check issue has a "Problem Analysis" or "Root Cause" section with specific file:line references
2. For **features**: Check issue has clear requirements (not just "add X" but "add X that does Y when Z")
3. For **enhancements**: Check issue explains what's wrong with current behavior and what specifically should change
4. Verify claims in the issue against actual code (do referenced files/functions exist? do they behave as described?)

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

**What to check**: How many files and how deep are the changes required?

**Detection method**:
1. Count files listed in the issue's "Integration Map" or "Files to Modify" section
2. Assess depth of changes: surface-level API changes vs. deep internal rewiring
3. Check if changes span multiple subsystems (skills, scripts, config, docs)

**Scoring**:
| Finding | Score |
|---------|-------|
| 1-2 files, isolated change in one subsystem | 25 |
| 3-5 files, changes in one or two subsystems | 18 |
| 6-10 files, changes span multiple subsystems | 10 |
| 11+ files or deep architectural changes | 0 |

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

#### Criterion D: Change Surface (0-25 points)

**What to check**: How many callers or dependents does the modified code have?

**Detection method**:
1. For each key file in the Integration Map, use Grep to count references/imports across the codebase
2. Check the issue's "Dependent Files" section for caller count
3. Higher caller count = more places that could break

**Scoring**:
| Finding | Score |
|---------|-------|
| 0-2 callers/dependents — isolated change | 25 |
| 3-5 callers/dependents — manageable surface | 18 |
| 6-10 callers/dependents — broad surface | 10 |
| 11+ callers/dependents — very wide blast radius | 0 |

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

After scoring, update the issue file's YAML frontmatter with both scores.

If the issue file has existing frontmatter (starts with `---`):
- Add or update the `confidence_score` and `outcome_confidence` fields within the frontmatter block
- Use the Edit tool to replace the frontmatter section

Example — if frontmatter is:
```yaml
---
discovered_date: 2026-02-13
discovered_by: capture-issue
---
```

Update to:
```yaml
---
discovered_date: 2026-02-13
discovered_by: capture-issue
confidence_score: 85
outcome_confidence: 62
---
```

If `confidence_score` or `outcome_confidence` already exist, replace their values with the new scores.

If the issue file has no frontmatter, add one:
```yaml
---
confidence_score: 85
outcome_confidence: 62
---
```

### Phase 4.5: Findings Write-Back

**Skip this phase if**: `CHECK_MODE` is true (no writes in check mode).

After presenting the output, determine whether there are findings to write back. Track `HAS_FINDINGS=false`; set to `true` if any of the following have content:
- **Concerns** (present when readiness tier is PROCEED WITH CAUTION)
- **Gaps to Address** (present when readiness score < 70)
- **Outcome Risk Factors** (present when outcome confidence < 60)

**Interactive mode** (`AUTO_MODE` is false):

If `HAS_FINDINGS` is true, use `AskUserQuestion` to ask:
> "Should I update the issue file to include these findings (concerns, gaps, and risk factors)?"

Options: Yes / No

**Auto mode bypass**: When `AUTO_MODE` is true and `HAS_FINDINGS` is true, skip the `AskUserQuestion` prompt and proceed automatically.

**Auto mode with no findings** (`AUTO_MODE` is true and `HAS_FINDINGS` is false): Skip (clean bill of health — no update needed).

If the user confirms (interactive) or `AUTO_MODE` is true with findings, append a `## Confidence Check Notes` section to the issue file using the Edit tool. Insert it before `## Session Log` (or before `## Status` if no session log exists):

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
- [risk 1]
_(omit this subsection if no risk factors)_
```

After appending findings (or skipping if no findings/user declined), stage the updated issue file:

```bash
git add "[issue-file-path]"
```

After the findings write-back step, append a session log entry to the issue file:

```markdown
## Session Log
- `/ll:confidence-check` - [ISO timestamp] - `[path to current session JSONL]`
```

To find the current session JSONL: look in `~/.claude/projects/` for the directory matching the current project (path encoded with dashes), find the most recently modified `.jsonl` file (excluding `agent-*`). If `## Session Log` already exists, append below the header. If not, add before `## Status` footer.

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
- Run `/ll:issue-size-review [ISSUE_ID]` — a persistent low readiness score after multiple refinement passes often signals the issue is too large or ambiguously scoped, not just under-researched

### Outcome Risk Factors (if outcome confidence < 60)
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
