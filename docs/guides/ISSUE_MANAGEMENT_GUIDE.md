# Issue Management Guide

## When to Use This Guide

Use the full refinement pipeline when you have multiple issues to prepare for a sprint, or when implementing a feature that requires careful planning. For a quick bug fix, skip to the [Fix a Bug in 5 Steps](#fix-a-bug-in-5-steps) recipe in Common Workflows.

---

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
  bugs/          ← bugs (any status)
  features/      ← features (any status)
  enhancements/  ← enhancements (any status)
  epics/         ← epics (coordination containers, not directly implementable)
```

**Filename format**: `P[0-5]-[TYPE]-[NNN]-description-with-dashes.md`

```
P2-BUG-042-sprint-runner-ignores-failed-issues.md
│  │   │   └─ kebab-case description
│  │   └─── globally unique issue number
│  └─────── type: BUG, FEAT, ENH, or EPIC
└────────── priority: P0 (critical) to P5 (low)
```

> **Status vs. Directory**: The `status:` frontmatter field drives CLI tools — `ll-issues list`, `ll-auto`, `ll-sprint`, and similar commands all filter by this field. The directory (`bugs/`, `features/`, etc.) is just organization by type. A completed bug stays in `.issues/bugs/` with `status: done`; it is never moved. Scanning for open work means filtering by `status: open`, not by directory.

Issue files use YAML-style frontmatter for metadata, followed by Markdown sections. The v2.0 template (see [Issue Template Guide](../reference/ISSUE_TEMPLATE.md)) adds four high-value sections: Motivation, Integration Map, Implementation Steps, and Root Cause (BUG only).

```yaml
---
id: BUG-042
title: Fix login timeout
status: open
priority: P2
parent: ENH-040            # parent issue this was decomposed from (omit if top-level)
blocked_by: []             # hard dependencies — must complete before this issue starts
depends_on: []             # soft ordering prerequisites — wave-gated (scheduled after), non-fatal if absent
relates_to: []             # thematically related issues (no ordering constraint)
duplicate_of:              # set when closing as duplicate of another issue
---
```

For the full frontmatter schema, see the [Issue Template reference](../reference/ISSUE_TEMPLATE.md).

**Code references always use anchors, not line numbers.** Write `in function _cmd_sprint_run()`, not `at line 1847`. Line numbers drift; function names don't.

## The Lifecycle

Issues move through seven states (plus Deferred, a parking state outside the main flow):

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
  │ Validating │  ← refinement pipeline (normalize → format → refine → decide → wire → verify → tradeoff → align → link-epics)
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
  │ Completed │  ← status: done set in frontmatter, committed
  └───────────┘

  ┌───────────┐
  │ Deferred  │  ← status: deferred set in frontmatter, parked for later
  └───────────┘
```

Issues can also be **deferred** (parked for later) using `/ll:manage-issue <type> defer <ID>` and later restored with `undefer`.

### Frontmatter `status` Values

The lifecycle diagram above shows conceptual workflow phases. The frontmatter `status` field uses a separate set of semantic values that automated tools (e.g., `ll-auto`, `/ll:manage-issue`) read and write:

| Value | Meaning |
|-------|---------|
| `open` | Newly captured, not yet started |
| `in_progress` | Currently being worked on |
| `blocked` | Waiting on an external dependency or decision |
| `deferred` | Parked for later; not actively being worked on |
| `done` | Work finished and committed |
| `cancelled` | Decided not to implement or closed without a code change |

Synonyms (`complete`, `completed`, `finished`, `closed`, `wip`, `in-progress`, `in progress`) are silently coerced to canonical values on read; authors don't need to worry about fixing them manually.

A `deferred` transition also stamps `deferred_by` (`human` by default, or `automation` when
`rn-implement`'s remediation circuit-breaker parks an issue), plus `deferred_reason` and
`deferred_date`. Run `ll-issues deferred-triage` to see the cross-run backlog of
automation-deferred issues — grouped by reason and sorted by age — so parked issues don't
silently disappear from view; human-deferred issues are intentionally excluded from that report.

As noted in [Issue File Anatomy](#issue-file-anatomy), CLI tools bucket issues by this `status` field, never by directory location.

Not every issue goes through every state. A trivial bug fix might go Discovered → Ready → Completed in one session. A large feature might stay in Validating for multiple refinement cycles.

---

## Phase 1: Discovering Issues

### Capturing from Conversation

When you notice a bug, identify a missing feature, or want to record an improvement during a conversation, `/ll:capture-issue` turns your observation into a properly formatted issue file.

Run it with no arguments and it reviews recent conversation context:

```
/ll:capture-issue
```

The skill determines the issue type (BUG/FEAT/ENH/EPIC), fills in what it can from context, assigns a unique ID, and creates the file in the appropriate `.issues/` subdirectory.

### Capturing with Description

Pass a natural-language description to skip the context-analysis step:

```
/ll:capture-issue "sprint runner crashes when issue has merge conflicts"
/ll:capture-issue "add --retry-failed flag to ll-sprint run"
```

The description becomes the seed for the issue title and Summary field. Capture creates a minimal issue — just enough to record the idea. Enrichment happens in Phase 2.

### Linking a New Issue to an EPIC

Pass `--parent EPIC-NNN` to auto-wire the new issue as a child of an existing EPIC:

```
/ll:capture-issue "Add retry logic to sprint runner" --parent EPIC-1663
/ll:capture-issue "Fix log output truncation" --parent EPIC-1626 --quick
```

This does two things atomically:
1. Sets `parent: EPIC-NNN` in the new issue's frontmatter.
2. Adds the new issue ID to the EPIC's `## Children` section.

Use `--quick` alongside `--parent` to create a minimal template when capturing many child tasks at once.

### Scanning the Codebase

To find issues you didn't know existed, use the scanning commands:

- `/ll:scan-codebase` — analyzes code for bugs, technical debt, and improvement opportunities; creates issue files for each finding
- `/ll:scan-product` — analyzes codebase against your `ll-goals.md` document to find feature gaps and UX problems (`ll-init` creates `.ll/ll-goals.md` automatically for new projects; if absent, scan-product discovers goals from existing docs)

Both commands can generate many issues at once. Run them when onboarding to a new codebase or doing a periodic audit, then use `/ll:prioritize-issues` and `/ll:tradeoff-review-issues` to cull the low-value ones before investing in refinement.

### Quick vs. Full Templates

`/ll:capture-issue` uses the template style set in `.ll/ll-config.json` (`issues.capture_template`, default: `"full"`). Pass `--quick` to force the minimal template (Summary, Current Behavior, Expected Behavior, Impact, and Status) regardless of config. The `/ll:format-issue` command (Phase 2) promotes a minimal issue to the full v2.0 template.

---

## Phase 2: Refining Issues

### The Refinement Pipeline

Refinement transforms raw captures into implementation-ready issues. **You don't need all ten steps on every issue** — use the decision tree below to pick your path:

```
What kind of issue is it?
│
├─ Small bug (< 1 day to fix, root cause obvious)
│    → normalize → wire → manage-issue
│
├─ Medium issue (known problem, needs codebase research)
│    → normalize → format --auto → refine → wire → verify → manage-issue
│
└─ Large feature or complex change
     → all 10 steps below
```

The full pipeline in order:

```
1.  normalize-issues    ← fix filenames (missing IDs, bad format)
2.  prioritize-issues   ← set P0-P5 prefix
3.  format-issue        ← promote to v2.0 template
4.  refine-issue        ← research codebase, fill knowledge gaps
5.  decide-issue        ← resolve competing options (only if decision_needed: true)
6.  wire-issue          ← complete integration map (callers, config, docs, tests)
7.  verify-issues       ← test claims against actual code
8.  tradeoff-review-issues ← prune low-value issues before investing more time
9.  align-issues        ← validate issues against key documents for relevance
10. link-epics          ← wire unparented issues to the right EPIC
```

> See [Decisions Log Guide](DECISIONS_LOG_GUIDE.md) for the full decisions system: how `decision_needed` gates automation, the four entry types (`decision`, `rule`, `exception`, `coupling`), and how `ll-issues decisions sync` propagates required rules to `.ll/ll.local.md`.

### Fixing Filenames

```
/ll:normalize-issues
```

Scans all issue files for naming problems: missing priority prefix, missing or duplicate ID numbers, incorrect type codes, malformed descriptions. Renames files to match the convention (renames files only — does not edit issue content). Run this after any bulk import or after manually creating files.

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

**Priority heuristics:**

| Situation | Likely priority |
|-----------|----------------|
| Production outage, data loss, security breach | P0 |
| Users actively blocked right now, no workaround | P1 |
| Silent data corruption (even if not user-visible) | P1 |
| Important feature broken, workaround exists | P2 |
| Normal bugs, nice-to-have improvements | P3 |
| Polish, minor edge cases, "while we're in there" | P4 |
| Cosmetic, highly speculative, may never do | P5 |

### Formatting to Template v2.0

```
/ll:format-issue                     ← interactive: asks Q&A for each section
/ll:format-issue --auto              ← non-interactive: fills gaps automatically
/ll:format-issue BUG-042              ← target a specific issue (uses ISSUE_ID, not a file path)
```

Promotes a minimal issue to the full v2.0 structure. In interactive mode, the skill asks clarifying questions to populate new sections (Motivation, Integration Map, Implementation Steps, Root Cause). In `--auto` mode, it makes its best guess from existing content.

Use interactive mode for high-priority issues where quality matters. Use `--auto` during bulk refinement.

### Enriching with Codebase Research

```
/ll:refine-issue [issue-id]          ← refine one issue (issue_id required)
```

Searches the actual codebase to fill knowledge gaps in each issue. It reads relevant files, traces call paths, finds callers and similar patterns, then populates or updates:

- **Root Cause** — where and why the bug occurs
- **Integration Map** — all files that will need changes
- **Proposed Solution** — concrete code examples using real function names
- **Implementation Steps** — high-level outline grounded in actual code structure

This is the most valuable refinement step for implementation accuracy. An issue with a well-researched Integration Map leads to complete changes; one without it leads to isolated fixes that break callers.

### Completing the Integration Map (Wiring Pass)

```
/ll:wire-issue [issue-id]            ← wire one issue (issue_id required)
/ll:wire-issue [issue-id] --auto     ← non-interactive
```

A post-refinement pass focused on **completeness of the Integration Map**. Where `refine-issue` fills knowledge gaps broadly, `wire-issue` traces everything that must change due to the planned implementation:

- **Callers and importers** — every call site that references the changed code
- **Config references** — config keys, environment variables, CLI flags affected
- **Doc mentions** — documentation sections that describe the changed behavior
- **Test coverage** — tests that exercise the affected code paths
- **Side-effect files** — plugin manifests, `__init__.py` exports, registration hooks

Run after `refine-issue` when the Integration Map looks thin — callers underspecified, test coverage missing, or side-effect files absent. Use `--dry-run` to preview what would be added without modifying the issue file.

**Flags:** `--auto` — non-interactive mode for FSM (finite-state machine) loop automation. `--dry-run` — preview proposed additions.

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

**Flags:** `--auto` — non-interactive mode for FSM loop automation. Skips user approval and does not move resolved issues.

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

Issues that pass validation have their Status updated to `Ready`. Issues that fail get specific improvement notes — `ready-issue` will auto-correct what it can and flag what requires human attention. Issues that are fundamentally invalid (e.g., the bug doesn't exist) are closed via `status: cancelled` with a "Closed: invalid" resolution note.

### Confidence Scoring

```
/ll:confidence-check                 ← check all active issues
/ll:confidence-check P2-BUG-042-... ← check one issue
/ll:confidence-check --all --auto   ← batch, non-interactive
/ll:confidence-check --sprint my-sprint ← sprint-scoped pre-flight check
```

Complementary to `ready-issue`, this skill evaluates implementation readiness from the agent's perspective. It produces two scores:

- **Readiness Score** (0-100) — go/no-go for starting implementation. Evaluates five criteria: problem clarity, solution specificity, codebase context, test strategy, and risk understanding. If the issue declares `learning_tests_required` targets and any are `missing` or `refuted`, a hard STOP — ADDRESS GAPS is forced regardless of aggregate score.
- **Outcome Confidence Score** (0-100) — predicted implementation risk. Evaluates: correctness likelihood, completeness likelihood, test coverage likelihood, and no-regression likelihood.

Both scores are persisted to the issue's frontmatter as `confidence_score` and `outcome_confidence`. Use these during sprint planning to sequence high-confidence issues first.

#### Escalation after low readiness scores

When readiness score stays below 70 after 2+ refinement passes, `confidence-check` branches on `score_ambiguity` (Criterion C — 0–25):

- **`score_ambiguity ≤ 10`** — competing implementation options are unresolved. When `confidence-check` identifies an unresolved decision in its Outcome Risk Factors prose, it automatically sets `decision_needed: true` in the issue frontmatter (BUG-1278 fix). Automated pipelines will then invoke `/ll:decide-issue` via the decision gate; for manual runs, execute `/ll:decide-issue` directly to select one option and clear the flag. FSM callers (`rn-remediate`, `autodev`) pre-check decidability with `/ll:decide-issue --validate-only` (or its deterministic companion `ll-issues check-decidable <ID>`, ENH-2443) — a `decision_needed: true` issue whose `## Proposed Solution` has no enumerable options routes through one bounded `/ll:refine-issue --auto` deposit-options retry before `decide` runs, rather than escalating straight to manual review with no diagnostic.
- **`score_ambiguity > 10`** — the issue is too large or under-researched. Run `/ll:issue-size-review` to decompose it into independently-shippable pieces.

This replaces the old behavior of always routing to `/ll:issue-size-review` regardless of cause. (ENH-1250)

### Size Review & Decomposition

```
/ll:issue-size-review
/ll:issue-size-review --sprint my-sprint ← sprint-scoped size audit
```

Reviews active issues for scope. Issues estimated at more than one session's work (typically >4 hours or >~200 LOC) are flagged for decomposition. The skill proposes how to split them: identifying a core issue and N satellite issues that can each be implemented independently.

**Flags:** `--auto` — non-interactive mode for FSM loop automation. Auto-decomposes only issues scoring >=8, with a qualitative-skip guard: if `score_ambiguity ≥ 18` and `score_complexity ≥ 18` and `outcome_confidence` is set, the issue is skipped rather than decomposed (low confidence is qualitative, not a scope problem — run `/ll:refine-issue` or `/ll:wire-issue` instead). `--sprint <name>` — scope to issues in the named sprint only.

#### Decomposition principle: independently shippable

When splitting an issue, each child must be **independently shippable** — it produces a meaningful PR on its own. The governing test: "can this child be merged without its siblings and still be useful?"

The key constraint: **do not split tests and docs from the code they cover**. A child issue called "tests and documentation for X" that depends on a sibling to implement X cannot ship independently and will leave main temporarily broken. Instead, split along *capability seams*: each child implements a complete vertical slice of behavior including its own tests.

Examples:
- **Good split**: `FEAT-A: parse YAML frontmatter with inline arrays` + `FEAT-B: prefer frontmatter blocked_by over body sections` — each is testable and mergeable independently.
- **Bad split**: `FEAT-A: wire decide-issue pipeline` + `FEAT-B: tests and docs for decide-issue` — FEAT-B has no standalone value and leaves FEAT-A untested until FEAT-B merges. When `config.commands.tdd_mode` is `true`, FEAT-A is *itself* problematic: wiring is part of the TDD cycle, so a wiring-only child can only be tested with mocks until FEAT-B lands — defeating fast feedback and risking mock/prod divergence. (ENH-1320)

(ENH-1242)

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

**Flags:** `--auto` — non-interactive mode for FSM loop automation. Applies only HIGH-confidence proposals.

---

## Phase 4: Implementing Issues

### Planning First

```
/ll:manage-issue [type] plan [issue-id]
```

Before writing code, generate a detailed implementation plan. The skill reads the issue, researches the codebase, and produces a step-by-step plan that you approve before execution begins. The plan covers:

- Exact files to modify (with current content reviewed)
- Function-level changes for each file
- Test plan (what to add/modify/check)
- Risk assessment and edge cases

Planning separately from implementing catches misunderstandings early. An incorrect plan costs minutes to correct; incorrect code costs hours.

### Implementing

```
/ll:manage-issue bug fix [issue-id]             ← for bugs
/ll:manage-issue feature implement [issue-id]   ← for features
/ll:manage-issue enhancement improve [issue-id] ← for enhancements
```

Executes the approved plan. The skill works through each step, modifying files, writing tests, and verifying as it goes. After each significant change, it checks that existing tests still pass.

The `type` argument is required (`bug`, `feature`, or `enhancement`).

### The No Open Questions Rule

`manage-issue` will not start implementation while open questions remain in the issue. If the Proposed Solution says "approach A or approach B — TBD," the skill stops and asks you to decide. This is intentional: implementation decisions made mid-flight are often wrong and hard to reverse.

Resolve all open questions during Phase 2 (refine) or at the start of Phase 4 (plan). The issue file should read like a specification with a clear answer to every "how" question before code is written.

### Completing an Issue

When implementation finishes and tests pass:

1. Set `status: done` in the issue file's frontmatter
2. Update its Status footer: `**Completed** | Completed: 2026-02-24 | [commit hash]`
3. Commit with a conventional commit message referencing the issue

```bash
git add .issues/[type]/P2-BUG-042-...md [changed files]
git commit -m "fix(sprint): retry failed issues after orchestrator run (BUG-042)"
```

Or use `/ll:commit` to have the skill draft the commit message from the diff and issue context.

---

## Browsing Issues by Epic

`ll-issues list` groups issues by type by default. Use `--group-by epic` to see issues grouped under their parent EPIC instead — useful when planning or reviewing work for a specific initiative:

```bash
ll-issues list --group-by epic
```

Output shows each open EPIC as a header, with its child issues (those with a matching `parent:` frontmatter field) nested beneath it. Issues without a `parent:` appear in an `Unparented` bucket at the end. A child that is itself a `type: EPIC` (a nested EPIC) is listed in its own `Sub-EPICs (k)` sub-section beneath the parent heading, each with its own `(j/m done)` rollup — it is never silently dropped from the visible list even though it also counts toward the parent's `(N/M done)` badge (BUG-2480). The flag works alongside all standard filters (`--type`, `--priority`, `--status`):

```bash
ll-issues list --group-by epic --status open --priority P0,P1
# → P0/P1 open issues grouped by their parent EPIC
```

---

## Running Issues in Bulk

When you have many issues to process, the CLI tools can handle them in bulk without manual prompting between each one.

### Sequential: ll-auto

```bash
ll-auto                              ← process all active issues one by one
ll-auto --only BUG-042,FEAT-100      ← process a comma-separated list of specific issues
ll-auto --dry-run                    ← preview what would be processed
```

Processes issues one at a time, in priority order (P0 first). After each issue, it commits the result and moves to the next. Safe and predictable; slower than parallel.

### Parallel: ll-parallel

```bash
ll-parallel --workers 3             ← process 3 issues simultaneously
```

Runs multiple issues in separate git worktrees simultaneously. Each worker gets an isolated branch; the coordinator merges results. Significantly faster than sequential, but requires issues to have non-overlapping file changes. Run `/ll:map-dependencies` first to identify conflicts.

### Sprint-Based: ll-sprint

```bash
ll-sprint create sprint-name --issues BUG-001,FEAT-010   ← create a sprint from issues
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
5. /ll:manage-issue bug fix <issue-id>
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
4. /ll:audit-issue-conflicts       ← detect conflicting requirements across issues
5. /ll:tradeoff-review-issues      ← prune low-value issues
6. /ll:format-issue --auto         ← promote survivors to v2.0 template
7. /ll:refine-issue [issue-id]     ← enrich with codebase research (run per issue)
8. /ll:verify-issues               ← test claims against code
9. /ll:ready-issue                 ← validate quality gate
10. /ll:map-dependencies           ← identify ordering constraints
11. /ll:issue-size-review          ← decompose anything too large
12. /ll:create-sprint              ← curate and sequence the sprint
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

---

## Edge Cases

### Reopen a Completed Issue

When a fix regresses or an issue was closed prematurely:

```
1. Update frontmatter: set status from `done` back to `open` using the Edit tool
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
