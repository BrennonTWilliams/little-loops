# Issue Management Guide

## What Is Issue Management?

Issues in little-loops are structured Markdown files that capture bugs, features, and enhancements as first-class objects. They're not tickets in an external system — they live in your repository, travel with your code, and serve as the primary input to automated implementation tools.

The workflow exists because AI agents need rich context to implement correctly. A raw "fix the login bug" prompt leads to guesswork. A well-formed issue with a root cause analysis, integration map, and implementation steps gives the agent exactly what it needs to make a correct, focused change.

```
Human observation  →  Issue file  →  Refinement  →  Implementation  →  Commit  →  Completed
     (discovery)      (capture)      (enrichment)    (manage-issue)    (merge)     (archive)
```

The commands guide you through this flow. You don't need to run all of them on every issue — a quick bug fix might skip straight from capture to implementation. A large feature might cycle through the full pipeline multiple times.

## Issue File Anatomy

Issue files live in `.issues/` and follow a strict naming convention:

```
.issues/
  bugs/          ← active bugs
  features/      ← active features
  enhancements/  ← active enhancements
  completed/     ← archived issues (sibling directory, not a subdirectory of bugs/)
  deferred/      ← parked issues (not active, not completed)
```

**Filename format**: `P[0-5]-[TYPE]-[NNN]-description-with-dashes.md`

```
P2-BUG-042-sprint-runner-ignores-failed-issues.md
│  │   │   └─ kebab-case description
│  │   └─── globally unique issue number
│  └─────── type: BUG, FEAT, or ENH
└────────── priority: P0 (critical) to P5 (low)
```

> **Common pitfall**: `completed/` and `deferred/` are siblings of `bugs/`, `features/`, and `enhancements/` — not nested inside them. A completed bug moves to `.issues/completed/`, not `.issues/bugs/completed/`. Similarly, a deferred issue moves to `.issues/deferred/`.

Issue files use YAML-style frontmatter for metadata, followed by Markdown sections. The v2.0 template (see [Issue Template Guide](../reference/ISSUE_TEMPLATE.md)) adds four high-value sections: Motivation, Integration Map, Implementation Steps, and Root Cause (BUG only).

**Code references always use anchors, not line numbers.** Write `in function _cmd_sprint_run()`, not `at line 1847`. Line numbers drift; function names don't.

## The Lifecycle

Issues move through seven states:

```
  ┌────────────┐
  │ Discovered │  ← raw capture, minimal fields
  └────────────┘
        │
        ▼
  ┌─────────────┐
  │ Prioritized │  ← P0-P5 prefix added to filename
  └─────────────┘
        │
        ▼
  ┌────────────┐
  │ Validating │  ← refinement pipeline (normalize → format → refine → verify → tradeoff)
  └────────────┘
        │
        ▼
  ┌───────┐
  │ Ready │  ← passes /ll:ready-issue quality gate
  └───────┘
        │
        ▼
  ┌────────────┐
  │ InProgress │  ← manage-issue is actively working on it
  └────────────┘
        │
        ▼
  ┌───────────┐
  │ Verifying │  ← tests pass, code review, /ll:run-tests
  └───────────┘
        │
        ▼
  ┌───────────┐
  │ Completed │  ← moved to .issues/completed/, committed
  └───────────┘

  ┌───────────┐
  │ Deferred  │  ← moved to .issues/deferred/, parked for later
  └───────────┘
```

Issues can also be **deferred** (parked for later) using `/ll:manage-issue <type> defer <ID>` and later restored with `undefer`.

Not every issue goes through every state. A trivial bug fix might go Discovered → Ready → Completed in one session. A large feature might stay in Validating for multiple refinement cycles.

---

## Phase 1: Discovering Issues

### Capturing from Conversation

When you notice a bug, identify a missing feature, or want to record an improvement during a conversation, `/ll:capture-issue` turns your observation into a properly formatted issue file.

Run it with no arguments and it reviews recent conversation context:

```
/ll:capture-issue
```

The skill determines the issue type (BUG/FEAT/ENH), fills in what it can from context, assigns a unique ID, and creates the file in the appropriate `.issues/` subdirectory.

### Capturing with Description

Pass a natural-language description to skip the context-analysis step:

```
/ll:capture-issue "sprint runner crashes when issue has merge conflicts"
/ll:capture-issue "add --retry-failed flag to ll-sprint run"
```

The description becomes the seed for the issue title and Summary field. Capture creates a minimal issue — just enough to record the idea. Enrichment happens in Phase 2.

### Scanning the Codebase

To find issues you didn't know existed, use the scanning commands:

- `/ll:scan-codebase` — analyzes code for bugs, technical debt, and improvement opportunities; creates issue files for each finding
- `/ll:scan-product` — analyzes codebase against your `ll-goals.md` document to find feature gaps and UX problems

Both commands can generate many issues at once. Run them when onboarding to a new codebase or doing a periodic audit, then use `/ll:prioritize-issues` and `/ll:tradeoff-review-issues` to cull the low-value ones before investing in refinement.

### Quick vs. Full Templates

Newly captured issues use the **minimal template** — Summary, Current Behavior, Expected Behavior, Impact, and Status. This is intentional: capture fast, refine deliberately. The `/ll:format-issue` command (Phase 2) promotes a minimal issue to the full v2.0 template.

---

## Phase 2: Refining Issues

### The Refinement Pipeline

Refinement transforms raw captures into implementation-ready issues. The steps run in order, each building on the previous:

```
1. normalize-issues    ← fix filenames (missing IDs, bad format)
2. prioritize-issues   ← set P0-P5 prefix
3. format-issue        ← promote to v2.0 template
4. refine-issue        ← research codebase, fill gaps
5. verify-issues       ← test claims against actual code
6. tradeoff-review-issues ← prune low-value issues
```

You don't have to run all six on every issue. A well-described issue captured from conversation might skip normalize and go straight to format → refine → verify.

### Fixing Filenames

```
/ll:normalize-issues
```

Scans all issue files for naming problems: missing priority prefix, missing or duplicate ID numbers, incorrect type codes, malformed descriptions. Renames files to match the convention. Run this after any bulk import or after manually creating files.

### Setting Priorities

```
/ll:prioritize-issues
```

Analyzes issue content and assigns a P0-P5 priority prefix to each filename. The AI considers severity, user impact, blast radius, and effort.

| Priority | Meaning | Examples |
|----------|---------|---------|
| P0 | Critical — stop everything | Production outage, data loss, security breach |
| P1 | High — fix this sprint | Core feature broken, workflow blocker |
| P2 | Medium — fix soon | Important bug, meaningful improvement |
| P3 | Normal — standard backlog | Nice-to-have, non-critical bugs |
| P4 | Low — when convenient | Polish, minor edge cases |
| P5 | Minimal — won't miss it | Cosmetic, highly speculative |

After prioritization, review the assignments. The AI doesn't know your deadlines or business context — you might move P3s up or P1s down.

### Formatting to Template v2.0

```
/ll:format-issue                     ← interactive: asks Q&A for each section
/ll:format-issue --auto              ← non-interactive: fills gaps automatically
/ll:format-issue P2-BUG-042-...md   ← target a specific file
```

Promotes a minimal issue to the full v2.0 structure. In interactive mode, the skill asks clarifying questions to populate new sections (Motivation, Integration Map, Implementation Steps, Root Cause). In `--auto` mode, it makes its best guess from existing content.

Use interactive mode for high-priority issues where quality matters. Use `--auto` during bulk refinement.

### Enriching with Codebase Research

```
/ll:refine-issue                     ← refine all issues
/ll:refine-issue P2-BUG-042-...md   ← refine one issue
```

Searches the actual codebase to fill knowledge gaps in each issue. It reads relevant files, traces call paths, finds callers and similar patterns, then populates or updates:

- **Root Cause** — where and why the bug occurs
- **Integration Map** — all files that will need changes
- **Proposed Solution** — concrete code examples using real function names
- **Implementation Steps** — high-level outline grounded in actual code structure

This is the most valuable refinement step for implementation accuracy. An issue with a well-researched Integration Map leads to complete changes; one without it leads to isolated fixes that break callers.

### Verifying Against Codebase

```
/ll:verify-issues
```

Reads each issue and tests its claims against the actual codebase. Checks that:
- Referenced files exist
- Referenced functions/anchors exist
- Described behavior matches the code
- Impact and effort estimates are plausible

Flags issues with incorrect claims (file moved, function renamed, behavior already fixed) and either updates them or recommends closure. Run this before a sprint to avoid implementing against stale information.

### Pruning Low-Value Issues

```
/ll:tradeoff-review-issues
```

Evaluates each active issue for utility vs. complexity. Recommends one of:
- **Implement** — clear value, tractable effort
- **Update** — valid idea but needs more information before proceeding
- **Close** — speculative, low-value, or superseded by other work

Use this to sense-check your backlog before sprint planning. A backlog with 200 issues is paralyzing; one with 30 well-chosen issues is actionable.

---

## Phase 3: Validating Issues

### The Validation Gate

```
/ll:ready-issue                      ← validate all issues
/ll:ready-issue P2-BUG-042-...md    ← validate one issue
```

`ready-issue` is the quality gate between "refined" and "implementation-ready." It performs a comprehensive review:

- Summary is one sentence combining WHAT and WHY
- Current/Expected Behavior are specific and concrete
- Impact includes justifications (not just "P2 / Medium / Low")
- Integration Map covers all affected files
- Implementation Steps are present and high-level
- No deprecated sections used
- Proposed Solution uses anchors, not line numbers
- For BUGs: Root Cause identifies file + function anchor + explanation
- For FEATs: Acceptance Criteria are individually testable

Issues that pass validation have their Status updated to `Ready`. Issues that fail get specific improvement notes — `ready-issue` will auto-correct what it can and flag what requires human attention. Issues that are fundamentally invalid (e.g., the bug doesn't exist) are moved to `completed/` with a "Closed: invalid" status.

### Confidence Scoring

```
/ll:confidence-check                 ← check all active issues
/ll:confidence-check P2-BUG-042-... ← check one issue
/ll:confidence-check --all --auto   ← batch, non-interactive
```

Complementary to `ready-issue`, this skill evaluates implementation readiness from the agent's perspective. It produces two scores:

- **Readiness Score** (0-100) — go/no-go for starting implementation. Evaluates five criteria: problem clarity, solution specificity, codebase context, test strategy, and risk understanding.
- **Outcome Confidence Score** (0-100) — predicted implementation risk. Evaluates: correctness likelihood, completeness likelihood, test coverage likelihood, and no-regression likelihood.

Both scores are persisted to the issue's frontmatter as `confidence_score` and `outcome_confidence`. Use these during sprint planning to sequence high-confidence issues first.

### Size Review & Decomposition

```
/ll:issue-size-review
```

Reviews active issues for scope. Issues estimated at more than one session's work (typically >4 hours or >~200 LOC) are flagged for decomposition. The skill proposes how to split them: identifying a core issue and N satellite issues that can each be implemented independently.

Decomposed issues reference each other via the `blocked_by` field. Implementing in dependency order prevents integration conflicts.

### Dependency Mapping

```
/ll:map-dependencies
```

Analyzes active issues for cross-issue dependencies based on shared file overlap, then:
- Validates existing `blocked_by` references (catches references to closed or non-existent issues)
- Proposes new `blocked_by` relationships where none were declared
- Identifies contention hotspots (many issues touching the same file)

Run this before sprint planning. Issues with unresolved dependencies shouldn't be batched for parallel execution — they'll conflict at merge time.

---

## Phase 4: Implementing Issues

### Planning First

```
/ll:manage-issue plan [issue-id]
```

Before writing code, generate a detailed implementation plan. The skill reads the issue, researches the codebase, and produces a step-by-step plan that you approve before execution begins. The plan covers:

- Exact files to modify (with current content reviewed)
- Function-level changes for each file
- Test plan (what to add/modify/check)
- Risk assessment and edge cases

Planning separately from implementing catches misunderstandings early. An incorrect plan costs minutes to correct; incorrect code costs hours.

### Implementing

```
/ll:manage-issue fix [issue-id]        ← for bugs
/ll:manage-issue implement [issue-id]  ← for features
/ll:manage-issue improve [issue-id]    ← for enhancements
```

Executes the approved plan. The skill works through each step, modifying files, writing tests, and verifying as it goes. After each significant change, it checks that existing tests still pass.

If you don't specify a type, `manage-issue` infers it from the issue filename.

### The No Open Questions Rule

`manage-issue` will not start implementation while open questions remain in the issue. If the Proposed Solution says "approach A or approach B — TBD," the skill stops and asks you to decide. This is intentional: implementation decisions made mid-flight are often wrong and hard to reverse.

Resolve all open questions during Phase 2 (refine) or at the start of Phase 4 (plan). The issue file should read like a specification with a clear answer to every "how" question before code is written.

### Completing an Issue

When implementation finishes and tests pass:

1. Move the issue file to `.issues/completed/`
2. Update its Status footer: `**Completed** | Completed: 2026-02-24 | [commit hash]`
3. Commit with a conventional commit message referencing the issue

```bash
git add .issues/completed/P2-BUG-042-...md [changed files]
git commit -m "fix(sprint): retry failed issues after orchestrator run (BUG-042)"
```

Or use `/ll:commit` to have the skill draft the commit message from the diff and issue context.

---

## Automation: Batch Processing

When you have many issues to process, the CLI tools can handle them in bulk without manual prompting between each one.

### Sequential: ll-auto

```bash
ll-auto                              ← process all active issues one by one
ll-auto --issue P2-BUG-042-...md    ← process a specific issue
ll-auto --dry-run                    ← preview what would be processed
```

Processes issues one at a time, in priority order (P0 first). After each issue, it commits the result and moves to the next. Safe and predictable; slower than parallel.

### Parallel: ll-parallel

```bash
ll-parallel --workers 3             ← process 3 issues simultaneously
ll-parallel --sprint sprint-name    ← process issues in a sprint
```

Runs multiple issues in separate git worktrees simultaneously. Each worker gets an isolated branch; the coordinator merges results. Significantly faster than sequential, but requires issues to have non-overlapping file changes. Run `/ll:map-dependencies` first to identify conflicts.

### Sprint-Based: ll-sprint

```bash
ll-sprint create sprint-name        ← create a sprint from issues
ll-sprint run sprint-name           ← execute the sprint
ll-sprint show sprint-name          ← inspect sprint details and wave structure
```

A sprint is a curated list of issues grouped for a work session. Use `/ll:create-sprint` to interactively select and sequence issues, then `ll-sprint run` to execute them. Sprints support resume (pick up where you left off after an interruption) and wave-based execution (group independent issues for parallel processing).

---

## Common Workflows (Recipes)

### Fix a Bug in 5 Steps

The minimal path from observation to merged fix:

```
1. /ll:capture-issue "description of the bug"
2. /ll:format-issue --auto
3. /ll:refine-issue <file>
4. /ll:ready-issue <file>
5. /ll:manage-issue fix <issue-id>
   → /ll:commit
```

Skip `normalize-issues` and `prioritize-issues` if you're capturing and fixing immediately. Skip `verify-issues` and `tradeoff-review-issues` for known, confirmed bugs.

### Plan a Feature Sprint

When you want to queue up a week of work:

```
1. /ll:scan-codebase               ← find issues you didn't know existed
   /ll:scan-product                ← find feature gaps against goals
2. /ll:normalize-issues            ← fix any naming problems
3. /ll:prioritize-issues           ← assign P0-P5 to all issues
4. /ll:tradeoff-review-issues      ← prune low-value issues
5. /ll:format-issue --auto         ← promote survivors to v2.0 template
6. /ll:refine-issue                ← enrich with codebase research
7. /ll:verify-issues               ← test claims against code
8. /ll:ready-issue                 ← validate quality gate
9. /ll:map-dependencies            ← identify ordering constraints
10. /ll:issue-size-review          ← decompose anything too large
11. /ll:create-sprint              ← curate and sequence the sprint
    ll-sprint run sprint-name      ← execute
```

### Triage a New Codebase

When you inherit an unfamiliar project and need to understand what's broken:

```
1. /ll:scan-codebase               ← discover issues from static analysis
2. /ll:audit-architecture          ← identify structural problems
3. /ll:normalize-issues            ← clean up any existing issues
4. /ll:prioritize-issues           ← sort by severity
5. /ll:tradeoff-review-issues      ← keep only actionable issues
6. /ll:map-dependencies            ← understand coupling
```

After triage, you have a prioritized backlog of real problems with dependency ordering. Start with P0/P1 issues and work down.

### Reopen a Completed Issue

When a fix regresses or an issue was closed prematurely:

```
1. Move file from .issues/completed/ back to the appropriate type directory
   e.g.: .issues/completed/P2-BUG-042-...md → .issues/bugs/P2-BUG-042-...md
2. Update Status footer: **Reopened** | Reopened: 2026-02-24 | Reason: regression in commit abc123
3. Add a "Reopen Note" section explaining what changed
4. Run /ll:verify-issues <file> to refresh codebase claims
5. Continue from Phase 3 (validate) or Phase 4 (implement)
```

---

## See Also

- [Command Reference](../reference/COMMANDS.md) — complete flag documentation for every `/ll:` command
- [Issue Template Guide](../reference/ISSUE_TEMPLATE.md) — v2.0 template sections, examples, and quality checklists
- [Sprint Guide](SPRINT_GUIDE.md) — batch-process issues with dependency-aware waves, parallelism, and resume
- [Loops Guide](LOOPS_GUIDE.md) — automate multi-step issue workflows with FSM loops
- [Session Handoff](SESSION_HANDOFF.md) — continue issue work across sessions
- `/ll:issue-workflow` — quick reference card for the issue lifecycle
- `/ll:help` — full list of available commands
