# Confidence Check — Rubric Tables & Output Templates

Companion reference for `skills/confidence-check/SKILL.md`. This file holds the
full scoring rubric tables (Phase 2 readiness criteria, Phase 2b outcome
criteria), the Phase 3 score-to-recommendation tables, the output-format
templates, and the worked examples. The SKILL.md flow points here at each
extraction site. Behavior is unchanged — this is progressive disclosure only.

---

## Arguments Reference

- **issue_id** (optional): Issue ID to evaluate (e.g., `ENH-277`, `BUG-042`)
  - If provided, evaluates that specific issue
  - If omitted with `--all`, processes all active issues
  - If omitted without `--all`, expects to be invoked within a manage-issue context

- **flags** (optional): Command behavior flags
  - `--auto` — Non-interactive mode (skip user prompts, use defaults)
  - `--all` — Evaluate all active issues (bugs/, features/, enhancements/), skip completed/ and deferred/. Implies `--auto`.
  - `--check` — Check-only mode for FSM loop evaluators. Run all evaluation logic without writes, print one line per failing issue (`[ID] check: score N/100 (below threshold)`), exit 1 if any fail, exit 0 if all pass. Implies `--auto`.
  - `--sprint <name>` — Scope evaluation to only the issues listed in the named sprint definition (`.sprints/<name>.yaml`). Implies `--auto`. Cannot be combined with `--all`.

---

## Issue Discovery — Mode Mechanics

The SKILL.md "Issue Discovery" section points here for the per-mode resolution
logic. Arguments are parsed in the SKILL.md Arguments section
(`ISSUE_ID`, `AUTO_MODE`, `ALL_MODE`, `CHECK_MODE`, `SPRINT_NAME`).

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

---

## Phase 1.5 — Pre-Fetch Learning Test Context

Check `learning_tests_required` from issue frontmatter; if present and non-empty, run `ll-learning-tests check` per target and build an injection block.

```bash
LT_TARGETS=$(ll-issues show "${ISSUE_ID}" --json 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
v = d.get('learning_tests_required')
print(v or '')" 2>/dev/null || true)

LT_STOP=false
LT_ROWS=""

if [ -n "$LT_TARGETS" ]; then
    IFS=',' read -ra TARGETS <<< "$LT_TARGETS"
    for target in "${TARGETS[@]}"; do
        target=$(echo "$target" | xargs)
        result=$(ll-learning-tests check "$target" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$result" ]; then
            status=$(echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','unknown'))")
            notes=""
            if [ "$status" = "refuted" ]; then
                notes=$(echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('refutation_summary',''))")
                LT_STOP=true
            fi
        else
            status="missing"
            LT_STOP=true
        fi
        LT_ROWS+="| \"$target\" | $status | $notes |\n"
    done
fi
```

`ll-learning-tests check "<target>"` exit semantics: exit 0 + JSON stdout → record found (`status` is `"proven"`, `"stale"`, or `"refuted"`); exit 1 + no stdout → record not found (treat as `"missing"`). Do **not** use `--stale-aware`; that flag collapses stale+missing into a single exit 1 and loses the distinction needed for differential scoring.

**Auto-provision**: If any target's status is `missing` or `refuted` after the script above, invoke `Skill("explore-api", "<target>")` for each such target before proceeding. After each invocation completes, re-run `ll-learning-tests check "<target>"` and update that target's row in `LT_ROWS` with the refreshed status and notes. Re-evaluate `LT_STOP`: reset to `false`, then set to `true` only if any target is still `missing` or `refuted` after provisioning.

When `LT_ROWS` is non-empty, inject the following **Learning Test Context** block into Phase 2 assessment:

```
## Learning Test Context

The following external API assumptions are declared in this issue's frontmatter:

| Target | Status | Notes |
|--------|--------|-------|
| "<target>" | proven/stale/refuted/missing | [refutation summary if refuted] |
```

If `learning_tests_required` is absent or empty, omit this block entirely (no placeholder).

### Learning Test Status Scoring (Criterion 1 Modifier)

These modifiers apply on top of Criterion 1 when `learning_tests_required` is present:

| Target Status | Score Modifier | Action |
|---------------|----------------|--------|
| proven | 0 | No penalty |
| stale | −5 | API may have changed; verify before implementing |
| refuted | −10 | Assumption disproven; forces STOP — ADDRESS GAPS |
| missing | −10 | No test record found; forces STOP — ADDRESS GAPS |

Any `missing` or `refuted` target triggers the **Phase 3 hard override**: output `STOP — ADDRESS GAPS` regardless of aggregate readiness score (see SKILL.md Phase 3).

---

## Phase 2 — Readiness Scoring Tables (0-20 points each)

### Criterion 1: No Duplicate Implementations

| Finding | Score |
|---------|-------|
| No existing implementation found | 20 |
| Related code exists but doesn't solve the problem | 15 |
| Partial implementation exists (needs extension, not duplication) | 10 |
| Near-complete implementation already exists | 0 |

### Criterion 2: Architecture Compliance

| Finding | Score |
|---------|-------|
| Approach matches established patterns completely | 20 |
| Mostly matches, minor deviations justified | 15 |
| Partially matches, some concerns about fit | 10 |
| Contradicts established patterns or creates parallel pathways | 0 |

### Criterion 3: Problem Understanding (type-specific table)

Use the table matching the issue type.

**BUG** ("Root cause identified"):
| Finding | Score |
|---------|-------|
| Root cause clearly identified with code references that check out | 20 |
| Root cause described but code references not fully verified | 15 |
| Symptoms described but root cause is inferred/assumed | 10 |
| Only symptoms described, no analysis of underlying cause | 0 |

**FEAT** ("Requirements clarity"):
| Finding | Score |
|---------|-------|
| Concrete requirements with scenarios and testable acceptance criteria | 20 |
| Requirements present but some vague or missing edge cases | 15 |
| High-level requirements, significant details need inference | 10 |
| Vague "add X" with no specifics about behavior or scenarios | 0 |

**ENH** ("Rationale well-understood"):
| Finding | Score |
|---------|-------|
| Current behavior issues explained with specific changes and rationale | 20 |
| Rationale present but some changes underspecified | 15 |
| General dissatisfaction described, specific changes partially clear | 10 |
| Only symptoms noted, no analysis of what should change or why | 0 |

**EPIC** ("Coordination scope and child issues defined"):
| Finding | Score |
|---------|-------|
| Coordination scope clearly bounded; all child issues enumerated, each individually plannable | 20 |
| Scope clear; most children enumerated but 1-2 are placeholders or vague | 15 |
| Scope present but child issues partially listed; significant decomposition still needed | 10 |
| Vague coordination intent with no enumerated children, or scope unbounded | 0 |

> **Note**: EPICs are coordination containers, not directly implementable. A high
> readiness score for an EPIC means it is ready to drive a sprint or hand off
> children to `/ll:manage-issue`, NOT that it is itself ready to implement.

### Criterion 4: Issue Well-Specified

| Finding | Score |
|---------|-------|
| Clear acceptance criteria, specific files, defined scope | 20 |
| Most details present, 1-2 minor gaps fillable from context | 15 |
| Key details missing but inferrable from codebase research | 10 |
| Vague requirements, significant guesswork needed | 0 |

### Criterion 5: Dependencies Satisfied

| Finding | Score |
|---------|-------|
| No dependencies, or all dependencies satisfied | 20 |
| Minor dependencies unresolved but non-blocking | 15 |
| Some dependencies unresolved, workarounds possible | 10 |
| Critical dependencies unresolved, cannot proceed | 0 |

---

## Phase 2b — Outcome Confidence Scoring Tables (0-25 points each, max 100)

### Criterion A: Complexity (Breadth + Depth)

Apply both sub-tables and sum Breadth + Depth for the criterion total.

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

### Criterion B: Test Coverage

| Finding | Score |
|---------|-------|
| All modified modules have corresponding tests or validation | 25 |
| Most modified modules are tested (>50%) | 18 |
| Few modules tested, failures may go undetected | 10 |
| No tests exist for modified areas | 0 |

### Criterion C: Ambiguity

| Finding | Score |
|---------|-------|
| No ambiguity — solution is fully specified with single clear approach | 25 |
| Minor open questions that can be resolved during implementation | 18 |
| Several design decisions left open, will require judgment calls | 10 |
| Fundamental approach unclear, multiple competing options unresolved | 0 |

### Criterion D: Change Surface / Fanout Verifiability

Apply the table matching the detected pattern.

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

---

## Phase 3 — Score-to-Recommendation Tables

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

The readiness score drives the go/no-go recommendation; the outcome confidence
is informational context for planning.

---

## Output Format (single issue)

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

---

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
