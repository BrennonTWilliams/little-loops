---
description: |
  Evaluates whether an issue should be implemented using an adversarial debate format. Launches two isolated background agents concurrently — one arguing for implementation, one against — each grounded in real codebase research. A third judge agent delivers a final GO or NO-GO verdict with structured reasoning, key arguments from both sides, and a deciding factor.

  Accepts one or more comma-separated Issue IDs, a sprint name, or no argument (defaults to highest-priority open issue). In --check mode, exits 0 on all GO and exits 1 on any NO-GO for FSM loop integration.

  Trigger keywords: "go no go", "go/no-go", "should I implement", "adversarial review", "worth implementing", "debate this issue", "go no go check"
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(find:*)
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(git:*)
  - Agent
  - Edit
  - AskUserQuestion
---

# Go/No-Go — Adversarial Issue Assessment

Evaluate whether one or more issues should be implemented by staging an adversarial debate between two research agents, with a neutral judge agent rendering a final GO/NO-GO verdict.

## Arguments

```
/ll:go-no-go [<issue-id>[,<issue-id>...] | <sprint-name>] [--check] [--auto]
```

| Flag | Meaning |
|------|---------|
| `--check` | Exit 0 on all GO, exit 1 on any NO-GO (FSM `evaluate: type: exit_code` gating) |
| `--auto` | Non-interactive mode (implied by `--dangerously-skip-permissions`) |

**Examples:**
```bash
/ll:go-no-go                      # evaluate highest-priority open issue
/ll:go-no-go FEAT-808             # evaluate single issue
/ll:go-no-go FEAT-808,ENH-712     # evaluate multiple issues
/ll:go-no-go sprint-improvements  # evaluate all issues in named sprint
/ll:go-no-go FEAT-808 --check     # exit 0 on GO, exit 1 on NO-GO
```

---

## Phase 1: Parse Arguments

```
ISSUE_TOKENS = []    # raw issue ID or sprint name tokens from args
ISSUE_IDS = []       # resolved list of issue IDs to evaluate
CHECK_MODE = false
AUTO_MODE = false

# Auto-enable in automation contexts
if ARGUMENTS contains "--dangerously-skip-permissions": AUTO_MODE = true

# Explicit flags
if ARGUMENTS contains "--auto": AUTO_MODE = true
if ARGUMENTS contains "--check": CHECK_MODE = true; AUTO_MODE = true

# Extract non-flag tokens
for token in ARGUMENTS:
    if token starts with "--": skip
    else if token contains ",": ISSUE_TOKENS = token.split(",")
    else if token is non-empty: ISSUE_TOKENS = [token]
```

**Token classification**: Each token is either an issue ID (e.g., `FEAT-808`) or a sprint name (e.g., `sprint-improvements`). Issue IDs match the pattern `[A-Z]+-\d+`. Sprint names do not match this pattern.

---

## Phase 2: Resolve Issues

Determine the final list of issue files to evaluate.

### Case 1: Specific issue IDs provided

For each issue ID in `ISSUE_TOKENS` that matches `[A-Z]+-\d+`:

```bash
FILE=""
for dir in .issues/{bugs,features,enhancements}/; do
    FILE=$(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | grep -E "[-_]${ID}[-_.]" | head -1)
    if [ -n "$FILE" ]; then break; fi
done

if [ -z "$FILE" ]:
    print "Error: Issue $ID not found in active issues"
    exit 1
```

### Case 2: Sprint name provided

For each token that does NOT match the issue ID pattern, treat it as a sprint name:

```bash
SPRINT_FILE=".sprints/${SPRINT_NAME}.yaml"
if [ ! -f "$SPRINT_FILE" ]:
    print "Error: Sprint '$SPRINT_NAME' not found at $SPRINT_FILE"
    exit 1

# Read the sprint YAML and parse the `issues:` list
cat "$SPRINT_FILE"
# The issues: key contains a list of issue IDs (e.g., ENH-175, FEAT-808)
# Resolve each ID to a file path using the same find pattern as Case 1
```

### Case 3: No argument (default)

Find the highest-priority open issue across all active categories:

```bash
for P in P0 P1 P2 P3 P4 P5; do
    for dir in .issues/{bugs,features,enhancements}/; do
        FILE=$(ls "$dir"/$P-*.md 2>/dev/null | sort | head -1)
        if [ -n "$FILE" ]; then break 2; fi
    done
done

if [ -z "$FILE" ]:
    print "Error: No open issues found"
    exit 1
```

---

## Phase 3: Evaluate Each Issue

For each resolved issue file, perform the following steps sequentially.

### Step 3a: Read the Issue File

Read the issue file completely. Extract and note:
- Issue ID, title, summary
- Current behavior / expected behavior
- Acceptance criteria
- Implementation steps
- Motivation / use case
- Impact section (priority, effort, risk)

### Step 3b: Launch Adversarial Agents

In a **single message**, launch both agents concurrently using the `Agent` tool with `run_in_background: true`.

**IMPORTANT**: Both agent calls MUST appear in the same message to run concurrently. Do not send them in separate messages.

#### Pro-Implementation Agent Prompt

Use this prompt for the pro-implementation agent, substituting the actual issue content:

```
You are a pro-implementation advocate for [ISSUE-ID]: "[ISSUE-TITLE]".

Your task is to research the codebase and build the strongest possible argument FOR implementing this issue right now.

Issue Summary:
[ISSUE-SUMMARY]

Acceptance Criteria:
[ACCEPTANCE-CRITERIA]

Motivation:
[MOTIVATION]

Research the codebase thoroughly to ground your argument. Use Read, Glob, Grep, and Bash tools to find relevant files. Look for:
1. How well this fits existing patterns and architecture
2. Existing code that makes implementation straightforward
3. Gaps or pain points in the current codebase that this issue addresses
4. How acceptance criteria map to concrete, achievable changes
5. Evidence that risk is low (additive changes, no regressions, well-scoped)
6. Precedents — similar issues that were successfully implemented

Produce a structured argument with these exact sections:

**IMPLEMENTATION FEASIBILITY**: How straightforward is implementation? Cite specific files, functions, and line numbers showing where changes would go.

**PATTERN FIT**: Does this align with existing architecture and conventions? Reference specific files that establish the pattern this would follow.

**CLEAR VALUE**: What concrete problem does this solve? Quantify the benefit where possible.

**LOW RISK**: Why is the risk acceptable? Show that changes are additive, reversible, or well-scoped.

**TOP 3 REASONS TO IMPLEMENT**:
1. [Most compelling reason with codebase evidence]
2. [Second reason with evidence]
3. [Third reason with evidence]

Be thorough. Cite specific files and line numbers. Argue forcefully for implementation — do not hedge.
```

#### Con-Implementation Agent Prompt

Use this prompt for the con-implementation agent, substituting the actual issue content:

```
You are a devil's advocate for [ISSUE-ID]: "[ISSUE-TITLE]".

Your task is to research the codebase and build the strongest possible argument AGAINST implementing this issue right now.

Issue Summary:
[ISSUE-SUMMARY]

Acceptance Criteria:
[ACCEPTANCE-CRITERIA]

Motivation:
[MOTIVATION]

Research the codebase thoroughly to ground your argument. Use Read, Glob, Grep, and Bash tools to find relevant files. Look for:
1. Existing functionality that already covers this need (or could with minor changes)
2. Implementation complexity hidden behind the issue's description
3. Risks: regressions, scope creep, maintenance burden, premature abstraction
4. Poor timing: dependencies not satisfied, competing priorities, incomplete prerequisites
5. Ambiguity or under-specification that would cause implementation churn
6. Whether the effort/value ratio is poor given other priorities

Produce a structured argument with these exact sections:

**EXISTING COVERAGE**: Is there already something that covers this need? Cite specific files, functions, or features that overlap.

**HIDDEN COMPLEXITY**: What complications will emerge during implementation? Show specific areas where the description understates difficulty.

**RISK FACTORS**: What could go wrong or cause regression? Name specific files or systems at risk.

**POOR TIMING**: Why is now not the right time? What prerequisites are missing or competing?

**TOP 3 REASONS NOT TO IMPLEMENT**:
1. [Most compelling reason with codebase evidence]
2. [Second reason with evidence]
3. [Third reason with evidence]

Be thorough. Cite specific files and line numbers. Argue forcefully against implementation — do not hedge.
```

### Step 3c: Wait for Completion

Wait until both background agents have completed and returned their full outputs. Do not proceed until both have finished.

### Step 3d: Launch Judge Agent

Launch a **foreground** judge agent (no `run_in_background`) using the Agent tool. Inject both argument texts as context in the prompt:

```
You are an impartial judge evaluating whether issue [ISSUE-ID]: "[ISSUE-TITLE]" should be implemented.

You have received arguments from two independent research agents who examined the codebase:

---
## FOR (Pro-Implementation Argument)

[FULL PRO-AGENT OUTPUT]

---
## AGAINST (Con-Implementation Argument)

[FULL CON-AGENT OUTPUT]

---

Your task: Render an impartial GO or NO-GO verdict based on the evidence presented.

Evaluate these dimensions:
1. **Evidence quality**: Which side has stronger codebase-grounded evidence?
2. **Argument validity**: Are the arguments logically sound? Do they address real concerns?
3. **Risk/value balance**: Does the value justify the risk and effort?
4. **Timing**: Is this the right time given the codebase state?

Produce your verdict in this EXACT format (do not add any other text):

VERDICT: [GO | NO-GO]
NO-GO REASON: [CLOSE | REFINE | SKIP]

RATIONALE:
[2-4 sentences explaining why you reached this verdict, referencing the strongest arguments from both sides]

KEY ARGUMENTS FOR:
- [Most compelling pro argument with any codebase evidence]
- [Second most compelling pro argument]

KEY ARGUMENTS AGAINST:
- [Most compelling con argument with any codebase evidence]
- [Second most compelling con argument]

DECIDING FACTOR:
[Single most important consideration that tipped the verdict in this direction]

`NO-GO REASON` rules:
- Include this line ONLY when VERDICT is NO-GO. Omit it entirely when VERDICT is GO.
- `CLOSE` — The issue is invalid, already covered by existing functionality, or fundamentally misdirected. Recommended next action: close or archive the issue.
- `REFINE` — The issue is valid but under-specified, ambiguous, or needs additional research before it can be implemented. Recommended next action: run `/ll:refine-issue` or `/ll:ready-issue`.
- `SKIP` — The issue is good but poorly timed: competing priorities, missing prerequisites, or lower value relative to other active work. Recommended next action: keep open, deprioritize, or remove from sprint.

Be decisive. Output ONLY the structured verdict above.
```

### Step 3e: Format and Display Verdict

After receiving the judge's output, parse the `VERDICT` line and, when the verdict is `NO-GO`, also parse the `NO-GO REASON` line immediately following it. Display using the `=` separator convention:

```
================================================================================
GO/NO-GO: [ISSUE-ID] — [ISSUE-TITLE]
================================================================================

### For (Pro-Implementation)
[Condensed pro arguments — 3-5 bullet points from KEY ARGUMENTS FOR and TOP 3 REASONS]

### Against (Con-Implementation)
[Condensed con arguments — 3-5 bullet points from KEY ARGUMENTS AGAINST and TOP 3 REASONS]

### Judge Verdict: GO ✓           (when verdict is GO)
### Judge Verdict: NO-GO ✗ (CLOSE | REFINE | SKIP)    (when verdict is NO-GO — show the parsed reason)

**Rationale**: [RATIONALE from judge]

**Deciding Factor**: [DECIDING FACTOR from judge]

================================================================================
```

Store both the verdict (`GO` or `NO-GO`) and, when applicable, the reason (`CLOSE`, `REFINE`, or `SKIP`) for each issue for use in Phase 4 and Phase 5.

### Step 3f: Go/No-Go Findings Write-Back

**Skip this phase if**: `CHECK_MODE` is true (no writes in check mode).

After displaying the verdict, determine whether there are significant findings to write back. Track `HAS_FINDINGS=false`; set to `true` if the judge output contains specific files, functions, or concrete evidence in KEY ARGUMENTS FOR or KEY ARGUMENTS AGAINST that are **not already present** in the issue body.

**Novelty heuristic**: Findings are significant if they mention specific file paths, function names, or concrete risks/feasibility points not already referenced in the issue body text.

**Interactive mode** (`AUTO_MODE` is false):

If `HAS_FINDINGS` is true, use `AskUserQuestion` to ask:
> "Should I update the issue file with the go/no-go findings (verdict rationale, key arguments, and deciding factor)?"

Options: Yes / No

**Auto mode bypass**: When `AUTO_MODE` is true and `HAS_FINDINGS` is true, skip the `AskUserQuestion` prompt and proceed automatically.

**No findings case**: When `HAS_FINDINGS` is false (judge output contains no novel file/function references beyond what the issue already documents): Skip (no update needed).

If the user confirms (interactive) or `AUTO_MODE` is true with findings, use the `Edit` tool to insert a `## Go/No-Go Findings` section into the issue file. Insert before `## Session Log` (or before `## Status` if no session log section exists):

```markdown
## Go/No-Go Findings

_Added by `/ll:go-no-go` on [YYYY-MM-DD]_ — **[GO | NO-GO]**

**Deciding Factor**: [DECIDING FACTOR from judge]

### Key Arguments For
- [bullet from KEY ARGUMENTS FOR]

### Key Arguments Against
- [bullet from KEY ARGUMENTS AGAINST]

### Rationale
[RATIONALE from judge]
```

After writing findings (or skipping), stage the updated issue file:

```bash
git add "[issue-file-path]"
```

---

## Phase 4: Batch Summary

When **more than one issue** was evaluated, append a summary table after all individual verdict blocks:

```
================================================================================
GO/NO-GO SUMMARY
================================================================================

| Issue ID | Title (truncated to 40 chars) | Verdict          | Deciding Factor |
|----------|-------------------------------|------------------|-----------------|
| FEAT-808 | go-no-go skill adversarial... | GO ✓             | Fits patterns   |
| ENH-712  | ...                           | NO-GO ✗ (CLOSE)  | Already covered |

================================================================================
```

---

## Phase 5: Check Mode

When `CHECK_MODE` is true, after all verdicts are displayed:

```
IF any issue received NO-GO:
    for each NO-GO issue:
        print "[ID] no-go ([REASON]): [deciding factor from judge]"
        # REASON is the parsed NO-GO REASON value: CLOSE, REFINE, or SKIP
    print "[N] issue(s) received NO-GO verdict"
    exit 1

IF all issues received GO:
    print "All [N] issue(s) received GO verdict"
    exit 0
```

This integrates with FSM `evaluate: type: exit_code` routing (0=success, 1=failure, 2+=error).

---

## Session Log

After completing all evaluations, append a session log entry to each evaluated issue file.

**Locate the session JSONL**: Search `~/.claude/projects/` for the directory whose name encodes the current working directory path (separators replaced by dashes). Find the most recently modified `.jsonl` file that does NOT start with `agent-`.

**Append to `## Session Log`** in each issue file:
```
- `/ll:go-no-go` - [ISO timestamp] - `[path to session JSONL]`
```

If `## Session Log` does not exist in the issue file, insert it before `## Status`.

Use the `Edit` tool to append the session log entry. Use Bash(`git log --format="%ai" -1`) to get the current timestamp if needed, or use the current date in ISO 8601 format.
