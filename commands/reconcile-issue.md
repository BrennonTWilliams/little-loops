---
description: Rewrite an issue's Implementation Steps, Acceptance Criteria, and Files to Modify in place from its own accumulated research findings, without appending or bulldozing human prose
argument-hint: "[issue-id]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(ll-issues:*)
  - Bash(git:*)
disable-model-invocation: true
arguments:
  - name: issue_id
    description: Issue ID to reconcile (e.g., FEAT-2672, BUG-004)
    required: true
  - name: flags
    description: "Optional flags: --check (report the plateau verdict without writing, for FSM evaluators)"
    required: false
---

# Reconcile Issue

You are tasked with **reconciling an issue's directive sections against its own
accumulated research**. Over a long refine/spike/confidence-check cycle,
`/ll:refine-issue` and `/ll:confidence-check` only **append** new "Codebase
Research Findings" bullets — they never rewrite the issue's own Implementation
Steps / Acceptance Criteria / Files to Modify to match. When those directive
sections contradict the findings, `/ll:confidence-check` re-flags the same
Concern every pass and the Readiness score plateaus.

Your job is a **targeted, in-place rewrite** of exactly three sections so they
reflect the accumulated findings — **not** another appended finding, and **not**
a wholesale rewrite.

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Status enum**: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled` — see `.claude/CLAUDE.md` § Issue File Format for full enum and forbidden synonyms.

## Contract (read this first — it is binding)

**Rewrite ONLY these three directive sections, in place:**
1. `## Implementation Steps`
2. `## Acceptance Criteria`
3. `### Files to Modify` (under `## Integration Map`)

**Preserve untouched — never edit, reorder, or delete:**
- `## Summary`, `## Motivation`, `## Current Behavior`, `## Expected Behavior`
- `## Proposed Solution` and any `### Option …` / `### Decision Rationale`
  (human-authored prose and recorded decisions)
- `### Codebase Research Findings`, `### Wiring Phase`, `### Similar Patterns`,
  `### Constraints`, `## Confidence Check Notes`, `## Session Log`, `## Status`
- Every other section not in the rewrite list above.

**Source of truth for the rewrite:** the issue's own `### Codebase Research
Findings` and `### Wiring Phase` (and any `### Decision Rationale` that selected
an option). You are reconciling the issue *against itself* — do not go re-research
the codebase (that is `/ll:refine-issue`'s job) and do not verify paths against
the tree (that is `/ll:ready-issue`'s job).

**Every rewritten claim must trace to an existing finding.** Do not invent new
requirements. If a directive bullet has no supporting finding, leave it as-is and
note it under `## CONCERNS`.

## Process

### 0. Parse Flags

```bash
FLAGS="${flags:-}"
CHECK_MODE=false
if [[ "$FLAGS" == *"--check"* ]]; then CHECK_MODE=true; fi
```

### 1. Find Issue File

```bash
ISSUE_FILE=$(ll-issues path "${issue_id}" 2>/dev/null)
```

If no file is found, print `## VERDICT` / `NOT_READY` and stop.

### 2. Arm the one-shot guard

**Immediately** (before any rewrite, and even in `--check` mode's absence),
set `reconcile_attempted: true` in the issue's YAML frontmatter using the Edit
tool. This mirrors `/ll:spike`'s `spike_attempted` convention and arms
`autodev.yaml`'s `check_reconcile_needed` one-shot guard so reconcile runs at
most once per issue per autodev run — set it whether or not any section actually
needs rewriting, so a no-op reconcile still disarms the guard.

Skip this write only when `CHECK_MODE` is true (check mode never writes).

### 3. Read the issue and its findings

Read the full issue file. Extract:
- The current text of the three directive sections.
- Every bullet under `### Codebase Research Findings` and `### Wiring Phase`.
- The selected option / decision under `### Decision Rationale` (if present) —
  the directive sections must describe the **selected** mechanism, not a
  superseded one.

### 4. Detect contradictions

For each of the three directive sections, compare its claims against the
findings. A section is **stale** when it describes a mechanism, file, step, or
acceptance condition that a later finding corrected, superseded, or contradicted.

If **no** section is stale (directives already match findings), this is a no-op:
emit verdict `RECONCILED` with an empty `## CORRECTIONS_MADE` (`None`) and stop
after the session-log append. Do not manufacture edits.

### 5. Rewrite the stale sections in place

Using the Edit tool, rewrite only the stale directive sections so they reflect
the findings. Rules:
- Keep the section's heading and overall shape (numbered steps stay numbered;
  AC stays a `- [ ]` checklist; Files to Modify stays a bulleted file list).
- Replace superseded content; do not append a parallel "corrected" block beside
  the stale one (that reproduces the append-only bug this skill exists to fix).
- Preserve any bullets that are still accurate.
- Cite the driving finding inline where it clarifies (e.g. a short parenthetical),
  but keep the section directive and terse — this is not a findings dump.

### 6. Append Session Log entry

```bash
ll-issues append-log "$ISSUE_FILE" /ll:reconcile-issue
```

If `ll-issues` is unavailable, append manually with exactly this format
(backticks required):

```
- `/ll:reconcile-issue` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

### 7. Check Mode Behavior (--check)

When `CHECK_MODE` is true: run steps 3-4 only (no frontmatter write, no rewrite,
no session log). Then:
- If ≥1 section is stale (a reconcilable plateau exists): print
  `[ID] reconcile: NEEDED` and `exit 0`.
- Otherwise: print `[ID] reconcile: CLEAN` and `exit 1`.

This integrates with FSM `evaluate: type: exit_code` routing.

## Output Format

```markdown
## VERDICT
[RECONCILED|NOT_READY]

## VALIDATED_FILE
[REQUIRED for ALL verdicts — absolute path to the reconciled issue file]

## SECTIONS_REWRITTEN
- Implementation Steps: [rewritten | unchanged]
- Acceptance Criteria: [rewritten | unchanged]
- Files to Modify: [rewritten | unchanged]

## CORRECTIONS_MADE
- [reconcile] Rewrote Implementation Steps 1-3 to describe the corrected <X>
  mechanism (per Codebase Research Finding: "<short quote>")
- [reconcile] Updated AC bullet 2 to match the <Y> finding
- [reconcile] Removed superseded "Files to Modify" entry <path> (finding: <…>)
- [Or "None" if nothing was stale]

## CONCERNS
- [Any directive bullet with no supporting finding, left as-is]
- [Or "None"]

## NEXT_STEPS
- [Re-run `/ll:confidence-check [ISSUE_ID]` to re-score against the reconciled body]
```

**Correction category** (new with this command):
- `[reconcile]` — a directive section (Implementation Steps / Acceptance Criteria
  / Files to Modify) rewritten in place to match the issue's own accumulated
  research findings.

**IMPORTANT**: The `## VALIDATED_FILE` section is REQUIRED for all verdicts so
automation can confirm the correct file was processed. Never omit it.

---

## Arguments

$ARGUMENTS

- **issue_id** (required): Issue ID to reconcile (e.g., `FEAT-2672`).
- **flags** (optional): `--check` — report the plateau verdict without writing
  (exit 0 if a reconcilable plateau exists, exit 1 if the body is already clean).

---

## Examples

```bash
# Reconcile a plateaued issue's directive sections against its findings
/ll:reconcile-issue FEAT-2672

# Check-only: does a reconcilable plateau exist? (for FSM evaluators)
/ll:reconcile-issue FEAT-2672 --check
```

---

## Integration

- Called by `autodev.yaml`'s `reconcile_current` state when
  `check_reconcile_needed` detects a post-spike Readiness plateau (ENH-2689).
- User-invocable directly to unstick an issue whose directive sections have
  drifted from its accumulated research.
- Distinct from `/ll:refine-issue` (appends research), `/ll:ready-issue`
  (reconciles issue ↔ codebase accuracy), and `/ll:wire-issue` (adds integration
  touchpoints). This command reconciles the issue **against itself**.
