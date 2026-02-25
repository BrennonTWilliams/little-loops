# Sprint Guide

## What Is a Sprint?

A sprint is a named, persistent list of issues executed as a coordinated batch. It lives in `.sprints/` as a YAML file, travels with your repository, and can be paused and resumed across sessions.

Why use a sprint instead of running issues one at a time?

- **Batching** — queue up a day or week of work, then execute hands-free
- **Dependency awareness** — the system computes execution order automatically; you don't sequence by hand
- **Parallelism** — independent issues run simultaneously in isolated worktrees
- **Resume** — if execution is interrupted, pick up exactly where you left off

The three batch tools each serve a different need:

| Tool | Best for |
|------|---------|
| `ll-auto` | Sequential, unordered queue; simplest setup, no dependencies needed |
| `ll-parallel` | Ad-hoc parallel run of a few independent issues |
| `ll-sprint` | Curated list with dependency ordering, waves, file contention handling, and resume |

For anything beyond a few issues or anything with known dependencies, use `ll-sprint`.

---

## How Waves Work

The most important concept in sprint execution is the **wave**. A wave is a group of issues that can run at the same time because none of them depend on each other.

The system computes waves automatically by performing a topological sort of the dependency graph:

```
Given issues and their blockers:
  FEAT-001  (no blockers)
  BUG-010   (no blockers)
  FEAT-002  (blocked by FEAT-001)
  FEAT-003  (blocked by FEAT-001)
  FEAT-004  (blocked by FEAT-002, FEAT-003)

Wave 1: FEAT-001, BUG-010    ← parallel (no blockers)
Wave 2: FEAT-002, FEAT-003   ← parallel (Wave 1 done)
Wave 3: FEAT-004             ← solo (Wave 2 done)
```

You don't configure waves — you configure dependencies (via the `blocked_by` field in issue files), and the system derives the wave structure.

### Single vs. Multi-Issue Waves

- **Single-issue wave**: runs in-place without worktree overhead (fast path)
- **Multi-issue wave**: each issue runs in its own git worktree in parallel, up to `max_workers` at once

### File Contention Splitting

When two issues in the same wave touch the same files, running them in parallel would cause merge conflicts. The system detects this automatically using the Integration Map sections of each issue file, and splits the wave into sequential sub-waves:

```
Wave 2 (2 issues, serialized — file overlap):
  Step 1/2:
    └── FEAT-002: Add middleware layer (P2)
  Step 2/2:
    └── FEAT-003: Update middleware config (P2)
  Contended files: src/middleware.py, src/config.py
```

Sub-waves are displayed as a single logical wave in the execution plan. The user sees "Wave 2 (serialized)" rather than two separate waves — the contention is handled transparently.

---

## Sprint File Anatomy

Sprint files live in `.sprints/` and follow a simple YAML format:

```yaml
name: bug-fixes
description: "All active P1-P2 bug fixes for the sprint"
created: "2026-02-13T10:00:00+00:00"
issues:
  - BUG-372
  - BUG-403
  - BUG-415
options:
  timeout: 3600
  max_workers: 4
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Sprint identifier; used as filename (`<name>.yaml`) |
| `description` | no | Human-readable purpose for the sprint |
| `created` | yes | ISO 8601 timestamp; set automatically on creation |
| `issues` | yes | List of issue IDs (e.g., `BUG-001`, `FEAT-010`) |
| `options.timeout` | no | Per-issue timeout in seconds (default: 3600) |
| `options.max_workers` | no | Max parallel workers per wave (default: from config) |

Issue IDs in the sprint list are resolved to actual files at runtime. The sprint itself only stores IDs — the file search happens when you run.

---

## Creating a Sprint

### Interactive: /ll:create-sprint

```
/ll:create-sprint
```

The interactive skill walks you through sprint creation:

1. **Goal clarification** — asks what you're trying to accomplish
2. **Auto-grouping** — proposes issue groupings based on your backlog; you select or reject each
3. **Dependency validation** — checks that blocked issues are included or have their blockers satisfied
4. **Confirmation** — shows the proposed sprint before writing the YAML

The skill proposes six auto-grouping strategies:

| Strategy | Groups issues by |
|----------|-----------------|
| Priority cluster | P0-P1 together, P2-P3 together, etc. |
| Type cluster | All bugs, all features, all enhancements |
| No-blockers sprint | Only issues with no dependencies (fully parallelizable) |
| Theme-based | Keyword clusters: test coverage, performance, security, docs |
| Component/file-based | Issues touching the same files or directories |
| Goal-aligned | Mapped against `ll-goals.md` if present |

You can accept one strategy, mix strategies, or skip auto-grouping and specify issues directly.

### Direct CLI

```bash
ll-sprint create sprint-name --issues BUG-001,FEAT-010,ENH-020
ll-sprint create sprint-name --issues BUG-001,FEAT-010 --description "Q1 fixes"
ll-sprint create sprint-name --issues BUG-001,FEAT-010 --max-workers 3 --timeout 7200
```

The CLI creates a sprint immediately without interactive prompting. Use this when you already know exactly which issues to include.

---

## Reviewing Before Running

Before executing a sprint, especially if issues have been refined since the sprint was created, run a health check:

```
/ll:review-sprint bug-fixes
```

The skill performs a six-phase analysis:

1. **Staleness check** — are issue files still current, or have they been superseded?
2. **Priority drift** — have priorities changed since the sprint was built?
3. **Dependency cycles** — would execution deadlock?
4. **File contention warnings** — which issues will serialize and why?
5. **Backlog scan** — are there related issues not in the sprint that belong?
6. **Removal proposals** — issues that are completed, invalid, or out of scope

The skill is interactive: it proposes changes and you approve or reject each one. Accepted changes are applied via `ll-sprint edit`. When you're done reviewing, the sprint is ready to run.

> **When to review**: any time more than a day has passed since you built the sprint, or after running `/ll:refine-issue` or `/ll:verify-issues` on issues in the sprint.

---

## Running a Sprint

```bash
ll-sprint run sprint-name
ll-sprint run sprint-name --dry-run       # show plan without executing
ll-sprint run sprint-name --max-workers 3
ll-sprint run sprint-name --timeout 7200
ll-sprint run sprint-name --skip BUG-010  # exclude specific issues
```

### Pre-flight

Before the first wave runs, `ll-sprint` validates the sprint:

- Issue files exist on disk
- No dependency cycles
- Wave structure computed and displayed

The execution plan is printed before any work begins:

```
======================================================================
EXECUTION PLAN (5 issues, 3 waves)
======================================================================

Wave 1 (parallel):
  ├── FEAT-001: Add middleware layer (P2)
  └── BUG-010: Fix null check in parser (P1)

Wave 2 (after Wave 1) parallel:
  ├── FEAT-002: Extend middleware config (P2)
  │   └── blocked by: FEAT-001
  └── FEAT-003: Update middleware tests (P2)
      └── blocked by: FEAT-001

Wave 3 (after Wave 2):
  └── FEAT-004: Integration tests for middleware (P3)
      blocked by: FEAT-002, FEAT-003

======================================================================
DEPENDENCY GRAPH
======================================================================

  FEAT-001 ──→ FEAT-002 ──→ FEAT-004
  FEAT-001 ──→ FEAT-003 ──→ FEAT-004

Legend: ──→ blocks (must complete before)
```

Use `--dry-run` to see this plan without executing anything.

### Wave Execution

Each wave runs as follows:

- **Single-issue wave**: `manage-issue` runs in-place (no worktree overhead)
- **Multi-issue wave**: `ParallelOrchestrator` creates a git worktree for each issue, runs them in parallel, then the merge coordinator integrates results

After each wave completes:
- State is checkpointed to `.sprint-state.json`
- Execution continues to the next wave

### Failed Issues

If an issue fails within a wave, the runner:

1. Records the failure
2. Retries once sequentially (outside the worktree)
3. If the retry also fails, marks it as failed and continues with the next wave

A sprint with some failures still completes — it doesn't stop at the first failure. Failed issues are reported in the summary with their reason.

### Graceful Shutdown

Send `Ctrl+C` once to request graceful shutdown. The runner finishes the current wave, saves state, and exits. Send `Ctrl+C` again to force immediate exit (state is still saved before exit).

---

## Handling Interruptions (Resume)

Sprint state persists across interruptions. The state file lives at `.sprint-state.json` in the repository root and contains:

- Sprint name and which wave is current
- Completed and failed issue IDs
- Per-issue timing
- Start time and last checkpoint timestamp

State is checkpointed after each wave (not after each issue). This means:

- If execution stops mid-wave, that wave's issues restart from scratch on resume
- If execution stops between waves, resume starts cleanly at the next wave

To resume an interrupted sprint:

```bash
ll-sprint run sprint-name --resume
```

The runner reads `.sprint-state.json`, finds the first incomplete wave, and starts there. Completed issues from earlier waves are skipped automatically.

State is automatically deleted when the sprint completes successfully. If you want to force a fresh start (discarding resume state), run without `--resume`:

```bash
ll-sprint run sprint-name          # clears state and starts over
```

---

## Editing a Sprint

Add or remove issues from an existing sprint:

```bash
ll-sprint edit sprint-1 --add BUG-099,FEAT-020    # add issues
ll-sprint edit sprint-1 --remove BUG-010           # remove issues
ll-sprint edit sprint-1 --prune                    # remove completed/invalid refs
ll-sprint edit sprint-1 --revalidate               # re-run dependency analysis
```

`--prune` scans each issue ID in the sprint and removes any that no longer have a file on disk (either completed and archived, or deleted). Use this to clean up a sprint that's been running for a while.

`--revalidate` re-reads the dependency graph after edits and updates any ordering implications. Run this after adding new issues to ensure wave groupings are still accurate.

**Edit vs. recreate**: Edit when you're making minor adjustments to an existing sprint. Recreate (delete + create) when the scope has changed significantly or you want `/ll:create-sprint` to re-run its auto-grouping logic.

---

## Inspecting Sprints

```bash
ll-sprint list                   # all sprints, one per line
ll-sprint list --verbose         # sprints with issue counts and descriptions
ll-sprint show sprint-1          # sprint details + wave visualization
ll-sprint analyze sprint-1       # file conflict analysis
ll-sprint analyze sprint-1 --format json
```

`ll-sprint show` is the primary inspection command. It displays the sprint YAML contents, validates that all issue files exist, and renders the dependency graph and wave structure — the same execution plan you'd see at the start of a run.

`ll-sprint analyze` focuses specifically on file overlap. It reads each issue's Integration Map and reports which files are touched by multiple issues, which pairs would contend, and which would be forced into sub-waves. Use this when planning a sprint with many issues touching the same subsystems.

---

## Configuration

Sprint behavior is configured in `.claude/ll-config.json` under the `sprints` key:

```json
{
  "sprints": {
    "sprints_dir": ".sprints",
    "default_timeout": 3600,
    "default_max_workers": 4
  }
}
```

| Option | Default | Description |
|--------|---------|-------------|
| `sprints_dir` | `.sprints` | Directory where sprint YAML files are stored |
| `default_timeout` | `3600` | Per-issue timeout in seconds (1 hour) |
| `default_max_workers` | `4` | Max parallel workers per wave |

Per-sprint options (in the YAML `options` block) override the project config for that sprint. CLI flags (`--max-workers`, `--timeout`) override both.

---

## Common Recipes

### Quick Bug-Fix Sprint

Capture recent bugs, enrich them, and run a sprint in one session:

```
1. /ll:capture-issue "description of bug 1"
   /ll:capture-issue "description of bug 2"
   /ll:capture-issue "description of bug 3"
2. /ll:format-issue --auto
3. /ll:refine-issue
4. /ll:ready-issue
5. /ll:create-sprint               ← pick "all bugs" auto-group
   ll-sprint run bug-sprint
```

### Themed Sprint (Test Coverage)

Build a sprint from issues related to a specific theme:

```
1. /ll:scan-codebase               ← discovers test gaps as ENH issues
2. /ll:prioritize-issues
3. /ll:tradeoff-review-issues
4. /ll:create-sprint               ← pick "theme: test coverage" auto-group
5. /ll:review-sprint test-sprint   ← health check before running
   ll-sprint run test-sprint
```

### Sprint with Dependencies

When issues have a natural ordering, dependency-aware sprinting is the key advantage:

```
1. Create issues with blocked_by fields:
     FEAT-010 has no blockers
     FEAT-011 blocked_by: [FEAT-010]
     FEAT-012 blocked_by: [FEAT-010]
     FEAT-013 blocked_by: [FEAT-011, FEAT-012]
2. /ll:map-dependencies            ← validates the graph, proposes missing edges
3. ll-sprint create feature-sprint --issues FEAT-010,FEAT-011,FEAT-012,FEAT-013
4. ll-sprint show feature-sprint   ← confirm wave structure:
     Wave 1: FEAT-010
     Wave 2: FEAT-011, FEAT-012 (parallel)
     Wave 3: FEAT-013
5. ll-sprint run feature-sprint
```

### Resume an Interrupted Sprint

```
# Sprint was interrupted mid-run
ll-sprint run sprint-name --resume    ← finds .sprint-state.json, continues

# Or inspect state first
ll-sprint show sprint-name            ← see which issues completed/failed
ll-sprint run sprint-name --resume
```

### Pre-PR Quality Sprint

Run code quality loops before opening a PR, then address any issues found:

```
1. ll-loop run quality-gate          ← built-in invariants loop (lint/types/format/tests)
2. /ll:scan-codebase                 ← capture any issues found
3. /ll:create-sprint                 ← sprint the findings
4. ll-sprint run quality-fixes
5. /ll:open-pr
```

### Full "Plan a Feature Sprint" Pipeline

The complete workflow from empty backlog to executed sprint (also in the Issue Management Guide):

```
1.  /ll:scan-codebase               ← find issues you didn't know existed
    /ll:scan-product                ← find feature gaps against goals
2.  /ll:normalize-issues            ← fix any naming problems
3.  /ll:prioritize-issues           ← assign P0-P5 to all issues
4.  /ll:tradeoff-review-issues      ← prune low-value issues
5.  /ll:format-issue --auto         ← promote survivors to v2.0 template
6.  /ll:refine-issue                ← enrich with codebase research
7.  /ll:verify-issues               ← test claims against code
8.  /ll:ready-issue                 ← validate quality gate
9.  /ll:map-dependencies            ← identify ordering constraints
10. /ll:issue-size-review           ← decompose anything too large
11. /ll:create-sprint               ← curate and sequence the sprint
    /ll:review-sprint <name>        ← health check
    ll-sprint run <name>            ← execute
```

---

## See Also

- [Issue Management Guide](ISSUE_MANAGEMENT_GUIDE.md) — refinement pipeline to run before sprint creation
- [Loops Guide](LOOPS_GUIDE.md) — the `sprint-execution` built-in loop for loop-driven sprint workflows
- `/ll:map-dependencies` — discover and validate cross-issue dependencies before building a sprint
- `/ll:issue-size-review` — decompose oversized issues before adding them to a sprint
- `/ll:review-sprint` — health check an existing sprint before running
- `ll-sprint --help` — full CLI reference for all subcommands and flags
