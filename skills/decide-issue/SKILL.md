---
description: |
  Use when an issue has `decision_needed: true` (2+ competing implementation options) and needs the best option selected via codebase evidence and scoring. Extracts all options from the Proposed Solution section, spawns codebase-pattern-finder agents per option to gather evidence, scores each option across 4 dimensions, marks the winner inline, and clears `decision_needed`.

  Trigger keywords: "decide issue", "pick an option", "choose implementation", "resolve options", "select approach", "decision needed", "which option"
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

# Decide Issue

Resolves multi-option implementation decisions by gathering codebase evidence for each option and selecting the best fit. Where `/ll:refine-issue --auto` deposits competing approaches and sets `decision_needed: true`, this skill closes the loop — scoring every option and annotating the winner directly in the issue file.

## When to Use

Run after `/ll:refine-issue` when `decision_needed: true` is set in the issue frontmatter:
- The Proposed Solution section contains 2+ competing implementation options
- The pipeline is blocked because no single approach has been selected
- You want an evidence-based decision rather than a gut-check pick

Can also be run manually on any issue that has multiple options in its Proposed Solution, even without `decision_needed: true`.

## Arguments

```
/ll:decide-issue [<issue-id>] [--auto] [--dry-run]
```

| Flag | Meaning |
|------|---------|
| `--auto` | Non-interactive mode: write decision without prompting |
| `--dry-run` | Preview the decision without modifying the issue file |

**Examples:**
```bash
/ll:decide-issue FEAT-948
/ll:decide-issue ENH-277 --auto
/ll:decide-issue BUG-042 --auto --dry-run
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
    print "Usage: /ll:decide-issue [ISSUE_ID] [--auto] [--dry-run]"
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

Read the full issue file to extract:
- YAML frontmatter (particularly `decision_needed`)
- The full "## Proposed Solution" section text
- Issue title and type for context

---

## Phase 3: Extract Options

Scan the Proposed Solution section for options using these three patterns (in order of precedence):

### Pattern 1 — Section Headers
```
Match: lines matching /^### Option [A-Z0-9]/i
Example: ### Option A, ### Option B, ### Option C
Extract: the header text as the option title; body text until next ### or ## as option description
```

### Pattern 2 — Bold Labels
```
Match: lines starting with **Option [A-Z0-9]** or **Option [0-9]+**
Example: **Option A (recommended)**: ..., **Option B**: ...
Extract: the bold label (stripped of **) as option title; rest of the line and following paragraph as description
```

### Pattern 3 — Numbered Top-Level Items
```
Match: numbered list items at top level: /^[0-9]+\.\s+\*\*Option/ or /^[0-9]+\.\s+[A-Z][^.]+approach/
Example: 1. **Option A** (chosen): ..., 2. Use existing utility ...
Extract: the item label or leading phrase as option title; full item text as description
Note: only apply this pattern if Pattern 1 and Pattern 2 found 0 options
```

### Option Count Check

After extraction:
- If `OPTIONS` is empty: print `No options found in Proposed Solution — nothing to decide.` and exit cleanly
- If `len(OPTIONS) == 1`: print `Only one option present — no decision required. Clearing decision_needed if set.` then proceed to Phase 7 (frontmatter update only: set `decision_needed: false`)
- If `len(OPTIONS) >= 2`: proceed to Phase 4

---

## Phase 4: Gather Codebase Evidence (Parallel Agents)

Spawn one `ll:codebase-pattern-finder` Agent **per option** in a **single message** with multiple Agent tool calls. Use `run_in_background: false` and wait for all to complete before proceeding.

For each option, the agent prompt template is:

```
Use Agent tool with subagent_type="ll:codebase-pattern-finder"

Prompt:
Find codebase evidence for or against this implementation option for {{ISSUE_ID}}.

Issue: {{ISSUE_ID}} — {{issue title}}

Option being evaluated: "{{option_title}}"
Option description: {{option_description}}

Find:
1. Existing patterns that use this approach — similar implementations already in the codebase
2. Call site count — how many places currently use a similar pattern
3. Existing utilities, helpers, or modules that this option could reuse
4. Patterns that conflict with or differ from this approach (evidence against)
5. Test patterns for this type of implementation

Return:
- Evidence FOR: existing patterns, utilities, call sites (with file:line references)
- Evidence AGAINST: conflicting patterns or missing utilities that would require new infrastructure
- Reuse score: 0 (builds from scratch) to 3 (reuses existing utilities directly)
- Summary: 1-2 sentence assessment of codebase fit
```

**Wait for ALL agents to complete before proceeding to Phase 5.**

---

## Phase 5: Score Each Option

For each option, produce a score across 4 dimensions (0–3 each, 12 max):

| Dimension | 0 | 1 | 2 | 3 |
|-----------|---|---|---|---|
| **Consistency** | Contradicts existing patterns | Partial fit | Mostly consistent | Matches patterns exactly |
| **Simplicity** | High complexity, many new abstractions | Moderate complexity | Mostly straightforward | Minimal code, no new abstractions |
| **Testability** | Hard to isolate/mock | Requires significant test scaffolding | Testable with some effort | Easily unit-testable |
| **Risk** | High risk (broad surface, unknowns) | Medium risk | Low risk, contained scope | Negligible risk |

**Scoring rules:**
- Use the agent evidence from Phase 4 to inform the Consistency score (agent's `reuse_score` feeds directly)
- Apply scores based on the option description and codebase findings — not assumptions
- If two options tie, prefer the one with higher Consistency (codebase fit is the tiebreaker)
- Document specific evidence citations for each score

Produce a per-option scoring record:

```
OPTIONS_SCORED:
  - title: "Option A"
    scores: { consistency: N, simplicity: N, testability: N, risk: N }
    total: N/12
    evidence_for: [key findings]
    evidence_against: [key findings]
  - title: "Option B"
    ...

SELECTED: title of highest-scoring option
RATIONALE: 2-3 sentence explanation citing evidence
```

---

## Phase 6: Prepare Annotation

Build the annotation content before any file writes:

### Selected Option Callout

Locate the winning option's text in the issue. Insert immediately after the option's title/label line:

```markdown
> **Selected:** [option title] — [one-line rationale]
```

### Decision Rationale Subsection

Append to the end of the Proposed Solution section:

```markdown
### Decision Rationale

Decided by `/ll:decide-issue` on YYYY-MM-DD.

**Selected**: [option title]

**Reasoning**: [2-3 sentence explanation citing specific codebase evidence]

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| [Option A] | N/3 | N/3 | N/3 | N/3 | N/12 |
| [Option B] | N/3 | N/3 | N/3 | N/3 | N/12 |

**Key evidence**:
- [Option A]: [1-2 sentence evidence summary]
- [Option B]: [1-2 sentence evidence summary]
```

---

## Phase 7: Apply Changes

**If `DRY_RUN` is true**: skip all file writes — output the full annotation content in the DRY RUN PREVIEW block (see Phase 9 output report) then exit.

### 7a: Annotate Issue File

Use the Edit tool to:
1. Insert the `> **Selected:** ...` callout immediately after the winning option's title line in the Proposed Solution section
2. Append the `### Decision Rationale` subsection at the end of the Proposed Solution section (before the next `##` heading)

**Idempotency rule**: if the issue already contains a `### Decision Rationale` section, skip the annotation write and log `⚠ Decision already annotated — skipping annotation (idempotent)`. Only proceed to the frontmatter update.

### 7b: Update Frontmatter

Set `decision_needed: false` in the issue's YAML frontmatter using the Edit tool inline `---` block replacement pattern:

```
READ the current --- frontmatter block (from opening --- to closing ---)
FIND the decision_needed field:
  IF field exists: replace its value with false
  IF field absent: add decision_needed: false after the last existing field

USE Edit tool to replace the entire --- block with the updated block
```

**Idempotency**: if `decision_needed` is already `false`, skip the write and log `✓ decision_needed already false — no update needed`.

---

## Phase 8: Append Session Log

```bash
ll-issues append-log <path-to-issue-file> /ll:decide-issue
```

If `ll-issues` is not available, append manually to the Session Log section:

```
- `/ll:decide-issue` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

Stage the updated file:

```bash
git add "{{issue_file_path}}"
```

---

## Phase 9: Output Report

```
================================================================================
DECIDE ISSUE: {{ISSUE_ID}}
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH]
- Title: [title]
- Mode: [Interactive | Auto] [--dry-run]
- decision_needed was: [true | false | absent]

## OPTIONS FOUND (N total)
- Option A: [title] — [one-line description]
- Option B: [title] — [one-line description]
...

## SCORING

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| [A]    | N/3         | N/3        | N/3         | N/3  | N/12  |
| [B]    | N/3         | N/3        | N/3         | N/3  | N/12  |

## DECISION
✓ Selected: [option title] (score: N/12)

Reasoning: [2-3 sentences]

## CHANGES APPLIED
- [Annotated issue with > **Selected:** callout | Skipped (idempotent)]
- [Appended ### Decision Rationale section | Skipped (idempotent)]
- decision_needed: [set to false | already false — no change]

## DRY RUN PREVIEW  ← only shown when --dry-run
---
[Full annotation content that would be written]
---

## FILE STATUS
- [Modified | Not modified (--dry-run | nothing to change)]

## NEXT STEPS
- Run `/ll:wire-issue {{ISSUE_ID}}` to add integration wiring (callers, entry points, test hooks)
- Run `/ll:ready-issue {{ISSUE_ID}}` to validate the issue is ready to implement
- Run `/ll:manage-issue feature implement {{ISSUE_ID}}` to implement

================================================================================
```

---

## Integration

### Pipeline Position

```
/ll:capture-issue → /ll:format-issue → /ll:refine-issue → /ll:decide-issue → /ll:wire-issue → /ll:ready-issue → /ll:manage-issue
```

- **Before**: `/ll:refine-issue --auto` — deposits implementation options, sets `decision_needed: true`
- **After**: `/ll:wire-issue` — traces callers and integration points for the now-selected implementation approach

### When to Use vs. Related Commands

| Skill | Purpose |
|-------|---------|
| `refine-issue` | Fills knowledge gaps; may deposit competing options |
| `decide-issue` | Selects the best option from competing alternatives using codebase evidence |
| `wire-issue` | Traces all wiring touchpoints for the selected implementation |
| `confidence-check` | Evaluates implementation readiness score |

`decide-issue` is specifically for the "refine-issue deposited multiple options but hasn't selected one" problem. It consumes `decision_needed: true` and produces a clear, annotated winner so the pipeline can continue.
