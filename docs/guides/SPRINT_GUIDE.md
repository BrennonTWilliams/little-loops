# Sprint Guide

## When to Use This Guide

Use a sprint when you have 4 or more issues, or issues with dependencies that must run in order. For 1–3 independent issues, `/ll:manage-issue` is simpler. For recurring automated workflows, use a loop instead — a YAML-defined finite-state machine (FSM) workflow; see the [Loops Guide](LOOPS_GUIDE.md).

**Sprint sizing guidance:**
- **1–5 issues** — focused burst (a morning's work)
- **5–20 issues** — weekly sprint
- **20+ issues** — run `/ll:map-dependencies` first; a large sprint benefits from explicit dependency ordering before it runs

---

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

### `blocked_by` vs `depends_on`

Two relationship fields affect sprint scheduling differently:

| Field | Arrow | Effect on sprint |
|-------|-------|-----------------|
| `blocked_by` | `──→` (hard dependency) | Soft ordering — wave-gated when practical, but a ready prerequisite may still be pulled into the same wave to fill capacity |
| `depends_on` | `-->` (soft ordering) | Not wave-gated — recorded for context and `ll-deps` validation but does not delay execution |

Use `blocked_by` when ISSUE-A **cannot start** until ISSUE-B is merged (e.g., ISSUE-A calls an API that ISSUE-B introduces). Use `depends_on` when the ordering is recommended but the issues can technically proceed in parallel (e.g., ISSUE-A tests a subsystem that ISSUE-B improves, but ISSUE-A is still valid without ISSUE-B).

### Single vs. Multi-Issue Waves

- **Single-issue wave**: runs in-place without worktree overhead (fast path)
- **Multi-issue wave**: each issue runs in its own git worktree in parallel, up to `max_workers` at once
- **Merge coordination**: parallel workers do not share the main working directory; merge coordination may subsequently integrate their commits into the base checkout.

> **What is a worktree?** A git worktree is an isolated checkout of your repository at a temporary directory. Each issue in a multi-issue wave gets its own worktree so the agents don't share file state or context — they work in parallel without interfering with each other. Your main working directory is never touched during the run.

### File Contention Splitting

When two issues in the same wave touch the same files, running them in parallel would cause merge conflicts. The system detects this automatically using the Integration Map sections of each issue file, and splits the wave into sequential sub-waves:

```
Wave 2 (2 issues, serialized — file overlap [min_files=2, ratio=0.25]):
  Step 1/2:
    └── FEAT-002: Add middleware layer (P2)
  Step 2/2:
    └── FEAT-003: Update middleware config (P2)
  Contended files: src/middleware.py, src/config.py
  Tune: dependency_mapping.overlap_min_files / overlap_min_ratio in ll-config.json
```

Sub-waves are displayed as a single logical wave in the execution plan. The user sees "Wave 2 (serialized)" rather than two separate waves — the contention is handled transparently. The effective threshold values are shown in the wave header so users can tune `dependency_mapping` in `.ll/ll-config.json` if the sprint over-serializes.

**Both thresholds must be crossed to trigger serialization** — crossing just one is not enough. An issue pair sharing 3 files out of 100 total (high count, low ratio) will not serialize unless both `overlap_min_files` and `overlap_min_ratio` are exceeded simultaneously. Raise either threshold in `.ll/ll-config.json` to reduce over-serialization on large issue sets.

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
| `options.max_workers` | no | Max parallel workers per wave (default: 2) |
| `options.max_iterations` | no | Max Claude iterations per issue (default: 100) |

Issue IDs in the sprint list are resolved to actual files at runtime. The sprint itself only stores IDs — the file search happens when you run.

---

## Creating a Sprint

### Interactive: `/ll:create-sprint`

```
/ll:create-sprint
```

The interactive skill walks you through sprint creation:

1. **Goal clarification** — asks what you're trying to accomplish
2. **Auto-grouping** — proposes issue groupings based on your backlog; you select or reject each
3. **Dependency validation** — checks that blocked issues are included or have their blockers satisfied
4. **Confirmation** — shows the proposed sprint before writing the YAML

The skill proposes seven auto-grouping strategies:

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
ll-sprint create sprint-name --issues BUG-001,FEAT-010,ENH-020 --skip BUG-001    # exclude specific IDs
ll-sprint create sprint-name --issues BUG-001,FEAT-010,ENH-020 --type bug,feat   # filter by issue type
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

**EPIC awareness**: When any sprint member has a `parent:` field referencing an EPIC, the review also produces an **EPIC Context** section. For each touched EPIC, it resolves the full active-children set (via `ll-issues list --group-by epic`) and computes the delta — EPIC children not in the sprint. If a delta member is listed in any sprint member's `blocked_by:`, the review flags it as a critical-path blocker gap and offers to add it to the sprint. This prevents the common mid-sprint stall where a manually curated sprint includes the "interesting" children of an EPIC but skips the blocker.

The skill is interactive: it proposes changes and you approve or reject each one. Accepted changes are applied via `ll-sprint edit`. When you're done reviewing, the sprint is ready to run.

> **When to review**: any time more than a day has passed since you built the sprint, or after running `/ll:refine-issue` or `/ll:verify-issues` on issues in the sprint.

---

## Running a Sprint

```bash
ll-sprint run sprint-name
ll-sprint run sprint-name --dry-run                       # show plan without executing
ll-sprint run sprint-name --max-workers 3
ll-sprint run sprint-name --timeout 7200
ll-sprint run sprint-name --skip BUG-010                  # exclude specific issues
ll-sprint run sprint-name --only BUG-001,FEAT-010         # run only these issues (allowlist)
ll-sprint run sprint-name --type bug,feat                 # filter by issue type at run time
ll-sprint run sprint-name --skip-analysis                 # bypass pre-execution dependency analysis
ll-sprint run sprint-name --quiet                         # suppress progress output
ll-sprint run sprint-name --handoff-threshold 80          # context window handoff threshold (1–100)
ll-sprint run sprint-name --feature-branches              # enable feature-branch mode (overrides config)
ll-sprint run sprint-name --skip-learning-gate            # bypass learning-test gate checks

# ll-auto also supports the same flag for its per-issue gate:
ll-auto --skip-learning-gate                              # bypass per-issue learning-test gate
```

The `--handoff-threshold` flag controls when Claude Code hands off to a fresh session mid-issue. During a long-running issue, Claude's context window fills up as it reads files, runs tools, and accumulates output. When context usage reaches the threshold (expressed as a percentage from 1 to 100), the runner writes a continuation prompt and starts a new session to complete the remaining work. Lower values trigger handoff earlier and more conservatively; higher values let sessions run longer before handing off. The default is 80 (hand off at 80% context usage).

### Pre-flight

Before the first wave runs, `ll-sprint` validates the sprint:

- Issue files exist on disk
- No dependency cycles
- Wave structure computed and displayed
- Completed and cancelled issues are logged individually and surfaced in a pre-validation summary rather than silently skipped
- Issues with `status: done` or `status: cancelled` in frontmatter are auto-skipped silently; if all issues are already completed, the sprint exits with success immediately

The execution plan is printed before any work begins:

```
======================================================================
EXECUTION PLAN (5 issues, 3 waves)
======================================================================

Wave 1 (parallel):
  ├── FEAT-001: Add middleware layer (P2)
  └── BUG-010: Fix null check in parser (P1)

Wave 2 (parallel, after Wave 1):
  ├── FEAT-002: Extend middleware config (P2)
  │   └── blocked by: FEAT-001
  └── FEAT-003: Update middleware tests (P2)
      └── blocked by: FEAT-001

Wave 3 (serial, after Wave 2):
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

- **Single-issue wave**: `/ll:manage-issue` runs in-place (no worktree overhead) — this is the same skill used for individual issue implementation, invoked automatically by the sprint runner
- **Multi-issue wave**: `ParallelOrchestrator` creates a git worktree for each issue, runs them in parallel, then the merge coordinator integrates results. With `use_feature_branches: true` in `.ll/ll-config.json`, auto-merge is skipped and each issue produces a PR-ready `feature/<id>-<slug>` branch instead — use this for PR-based CI/CD workflows.

> **Coverage boundary**: `use_feature_branches` only applies to multi-issue waves dispatched through `ParallelOrchestrator`. Single-issue waves and contention sub-waves always run in-place on the current branch — no worktree is created and no feature branch is produced for those issues. When `use_feature_branches` is set and a wave runs in-place, `ll-sprint` emits a one-time warning naming the branch the work lands on. Dependency chains that produce all single-issue waves will see this warning for every sprint run; if per-issue feature branches are required for all issues, avoid all-sequential dependency chains or track the follow-up enhancement.
>
> **State checkpoint cadence** (ENH-2530): State is checkpointed after each execution wave or contention sub-wave completes, not only after each logical dependency wave — so a refined sub-wave plan that splits a wave into N serialized steps yields N checkpoints, one per sub-wave.

After each wave completes:
- State is checkpointed to `.sprint-state.json`
- Execution continues to the next wave

### Feature-Branch / PR-Based Workflow

By default, multi-issue waves auto-merge each worktree back to the current branch. To use a PR-based CI/CD workflow instead, set `parallel.use_feature_branches: true` in `.ll/ll-config.json` — or pass `--feature-branches` on the CLI to override config for a single run.

**What changes when feature branches are enabled:**

- Each issue in a multi-issue wave gets a `feature/<id>-<slug>` branch (e.g., `feature/bug-001-fix-null-ptr`) instead of the temporary `parallel/<id>-<timestamp>` branch
- Auto-merge is skipped — branches survive as PR-ready
- `branch: feature/<id>-<slug>` is written to the issue's frontmatter for traceability
- The issue stays at `status: in_progress` until the PR merges; use `ll-sync` to reconcile status once merged (ENH-2182)

**Optional push and PR sub-flags** (both default `false`):

| Config key | Default | Effect |
|---|---|---|
| `push_feature_branches` | `false` | Push the branch to `remote_name` (default `origin`) via `git push --force-with-lease` after worker success |
| `open_pr_for_feature_branches` | `false` | Open a draft PR via `gh pr create` after push; records `pr_url:` on the issue; requires `push_feature_branches: true` and `gh auth status` |

Set `push_feature_branches: true` to push branches automatically after each issue finishes. Add `open_pr_for_feature_branches: true` to also open a draft PR and record `pr_url:` on the issue. If `gh` is unavailable or unauthenticated, the push proceeds but the PR step is skipped with a warning.

### Cleaning up merged feature branches

Feature branches (`feature/<id>-<slug>`) are retained intentionally after each worker finishes — the branch survives worktree cleanup so you can push, open a PR, and run CI. Once a PR has merged, the local ref is no longer needed. Over many runs the main repo accumulates stale `feature/` refs; use the opt-in prune to reclaim them.

```bash
# Preview what would be deleted (safe to run any time)
ll-parallel --prune-merged-branches --dry-run

# Delete branches already merged into the base branch
ll-parallel --prune-merged-branches
```

**What is pruned:** local `feature/*` branches that are fully merged into `parallel.base_branch` (auto-detected when unset: the repository's `origin/HEAD` default branch, else the current branch, else `main`; an explicit `parallel.base_branch` config value overrides detection). The currently checked-out branch and the base branch are never deleted.

**Squash/rebase merges:** `git branch --merged` only detects fast-forward and merge-commit histories. If your repository uses squash or rebase merges, install `gh` and authenticate (`gh auth login`) — `ll-parallel --prune-merged-branches` will cross-check PR state via `gh pr view` and prune those branches too. Without `gh`, squash/rebase-merged branches are left untouched.

**Scope:** only *local* branches are affected. GitHub's "delete branch on merge" setting governs the remote refs.

### Per-EPIC Integration Branch

When a multi-issue wave is dominated by children of a single EPIC, running each child as its own transient worktree and merging straight back to the base branch produces a noisy, hard-to-review PR surface — every child touches overlapping areas and conflicts at the base. The `epic_branches` config group (FEAT-2449, FEAT-2453) solves this by giving all children of an EPIC one shared integration branch that lives above the base branch.

**What changes when per-EPIC branches are enabled:**

- All children of an EPIC share one integration branch (named `epic/<EPIC-ID>-<slug>`, e.g. `epic/EPIC-2451-per-epic-integration-branch-strategy`)
- Each child forks from that branch (not from `parallel.base_branch`) and merges back into it, so intermediate conflicts surface at the EPIC branch instead of at the base
- When the last EPIC child completes, the orchestrator opens a single EPIC-level merge/PR from `epic/<EPIC-ID>-<slug>` into the base branch — one PR per EPIC instead of one per child
- If any child fails the EPIC is **not** merged; the partial-failure gate holds the EPIC branch open until the failing child is rerun or removed
- Standalone (parentless) issues follow the previous per-worker behavior — `epic_branches` only affects children that share a `parent:` EPIC

**Opt-in:**

| Config key | Default | Effect |
|---|---|---|
| `epic_branches.enabled` | `false` | When `true`, route children of the same EPIC to a single shared `epic/<id>-<slug>` branch and merge PR target. See [Configuration Reference](../reference/CONFIGURATION.md#parallel) for the full set. |
| `epic_branches.prefix` | `"epic/"` | Prefix for the integration branch name; the branch composes as `f"{prefix}{epic_id.lower()}-{slug}"` (e.g. `epic/epic-2339-foo`). `{slug}` is the kebab-cased EPIC title. |
| `epic_branches.merge_to_base_on_complete` | `true` | When `true`, the EPIC integration branch is merged back to `base_branch` after the last child completes. Set `false` to leave it un-merged for manual review. |
| `epic_branches.open_pr` | `false` | When `true`, open a PR for the EPIC integration branch via the `gh` CLI on completion. Requires `gh` installed and authenticated. |
| `epic_branches.verify_before_merge` | `false` | When `true`, check out the EPIC branch tip in a scratch worktree and run `test_cmd`/`lint_cmd` against it before merge-to-base or PR-open. A failure blocks the merge/PR-open, leaves the branch open for retry on the next completion event, and is surfaced in the run summary instead of silently logged (ENH-2603). |

`ll-sprint run sprint-name` needs no flag for config-driven runs — the orchestrator decides per wave whether to use the EPIC integration branch based on `epic_branches.enabled` and each issue's `parent:` field. To toggle the mode for a single run without editing config, pass `--epic-branches` (or `--no-epic-branches`) to `ll-parallel` or `ll-sprint run`; the flag overrides `parallel.epic_branches.enabled` for that invocation.

**Interaction with `use_feature_branches`:** the two flags are orthogonal. `use_feature_branches` governs *individual-issue* branch behavior (`feature/<id>-<slug>`, no auto-merge, manual PR). `epic_branches` governs *EPIC-level* integration (one shared branch per EPIC, single EPIC-level PR on completion). They are not designed to combine — if you enable both, the per-EPIC branching wins for children of an EPIC (so the per-issue `feature/` branch is skipped inside an EPIC); standalone issues still get per-issue `feature/` branches. Most teams pick one or the other:

- Use `epic_branches` when you plan work as coordinated EPICs and want one review surface per EPIC
- Use `use_feature_branches` when each issue ships independently and you don't plan work under EPICs

**When to enable `epic_branches`:**

- Multi-issue waves dominated by EPIC children (the common `ll-sprint create` shape when the sprint includes children of an EPIC)
- You want one PR per EPIC instead of N per EPIC child
- You're willing to delay the base-branch merge until the entire EPIC completes (no partial merges)

**When *not* to enable `epic_branches`:**

- Sprints composed mostly of standalone (parentless) issues — no benefit, since the per-EPIC routing never fires
- Sprints where you need each child merge to land independently as soon as it completes — partial-failure semantics will hold back the entire EPIC branch on any single child failure
- You're already using a git-flow / GitHub-ruleset workflow that branches per-issue to `feature/` and you don't want one-EPIC-one-PR

The EPIC merge path lives in `merge_coordinator`'s EPIC-aware router (see [merge coordinator internals](../development/MERGE-COORDINATOR.md)); orchestrator wires per-issue results through `WorkerResult.epic_branch` (see [API Reference — WorkerResult](../reference/API.md#workerresult)).

This same merge/verify/PR behavior is also available outside `ll-parallel`/`ll-sprint`: the `auto-refine-and-implement` FSM loop (used by `ll-loop run auto-refine-and-implement --context scope=EPIC-NNN` and its `sprint-refine-and-implement` alias) honors the same `epic_branches` config keys via a `merge_epic_branch` state, sharing the underlying free functions with the orchestrator path above (BUG-2614). See [LOOPS_REFERENCE.md § auto-refine-and-implement](LOOPS_REFERENCE.md#auto-refine-and-implement--full-backlog-refine-and-implement-loop).

**Not to be confused with `ll-parallel --epic-branches` / `ll-sprint --epic-branches` (ENH-2601):** everything above describes the `WorkerPool`/orchestrator path — `ll-parallel`, `ll-sprint run`, and the `--epic-branches` CLI flag documented in [CLI Reference](../reference/CLI.md). The FSM loops `auto-refine-and-implement` / `sprint-refine-and-implement` are a **separate** code path with no CLI flag of their own: when invoked with `scope=EPIC-NNN` and `parallel.epic_branches.enabled: true`, they read the same config group to *create* (not merge) the `epic/<EPIC-ID>-<slug>` branch via a `checkout_epic_branch` state before delegating to `autodev`, and add a post-implementation `verify` state whose pass/fail/skip verdict is folded into that run's `summary.json`. Since ENH-2609, `delegate` runs `autodev` inside a scratch worktree attached to that branch, so the refine+implement commits land on `epic/<EPIC-ID>-<slug>` without the main tree's checkout changing — no manual `git checkout` is needed. After verification, `merge_epic_branch` honors `parallel.epic_branches.merge_to_base_on_complete`, `open_pr`, and `verify_before_merge`; it merges or opens the configured PR once all EPIC children are done. See [LOOPS_REFERENCE.md § auto-refine-and-implement](LOOPS_REFERENCE.md#auto-refine-and-implement--full-backlog-refine-and-implement-loop).

### Failed Issues

If an issue fails during a **multi-issue parallel wave**, the runner:

1. Records the failure
2. Retries once sequentially (outside the worktree)
3. If the retry also fails, marks it as failed and continues with the next wave

Issues that fail in a **single-issue wave** are immediately marked as failed — no retry is attempted.

A sprint with some failures still completes — it doesn't stop at the first failure. Failed issues are reported in the summary with their reason.

### Diagnosing a Failed Issue

```bash
ll-sprint show sprint-name        # see which issues failed and their error messages
```

The show output includes a **Failed Issues** section with the error output from each failure. Common causes:
- Issue file has open questions (`manage-issue` requires all questions answered before starting)
- Test command fails before the agent can even begin (pre-existing test failures)
- Context limit hit mid-issue (lower `--handoff-threshold` and re-run)

To re-run only the failed issues without re-running the whole sprint:

```bash
ll-sprint run sprint-name --only FAILED-ID-1,FAILED-ID-2
```

If the issue itself needs fixing before re-running (missing context, vague implementation steps), update it first:

```bash
/ll:refine-issue FAILED-ID-1      # add missing context
ll-sprint run sprint-name --only FAILED-ID-1
```

### Graceful Shutdown

Send `Ctrl+C` once to request graceful shutdown. The runner finishes the current wave, saves state, and exits. Send `Ctrl+C` again to force immediate exit (state is still saved before exit).

---

## Handling Interruptions (Resume)

If a sprint is interrupted — by `Ctrl+C`, a system restart, or a tool crash — you can resume it exactly where it left off using `ll-sprint run sprint-name --resume`. Sprint state persists across interruptions. The state file lives at `.sprint-state.json` in the repository root and contains:

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

The runner reads `.sprint-state.json`, finds the first incomplete wave or sub-wave, and starts there. Completed issues from earlier waves are skipped automatically. Crash recovery is reliable only for graceful `Ctrl+C` or after a previously-saved checkpoint; an abrupt restart that lands between waves will leave a gap in the checkpoint log.

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
ll-sprint delete sprint-1                          # delete a sprint entirely
```

`--prune` scans each issue ID in the sprint and removes any that are completed (`status: done` or `status: cancelled` in frontmatter) or whose file no longer exists on disk. Use this to clean up a sprint that's been running for a while.

`--revalidate` re-reads the dependency graph after edits and updates any ordering implications. Run this after adding new issues to ensure wave groupings are still accurate.

**Edit vs. recreate**: Edit when you're making minor adjustments to an existing sprint. Recreate (delete + create) when the scope has changed significantly or you want `/ll:create-sprint` to re-run its auto-grouping logic.

---

## Inspecting Sprints

```bash
ll-sprint list                          # all sprints, one per line
ll-sprint list --verbose                # sprints with issue counts and descriptions
ll-sprint list --json                   # output as JSON array
ll-sprint show sprint-1                 # sprint details + wave visualization
ll-sprint show sprint-1 --json          # structured JSON output
ll-sprint show sprint-1 --skip-analysis # skip dependency analysis step
ll-sprint analyze sprint-1              # file conflict analysis
ll-sprint analyze sprint-1 --format json
```

`ll-sprint show` is the primary inspection command. It displays the sprint YAML contents, validates that all issue files exist, and renders the dependency graph and wave structure — the same execution plan you'd see at the start of a run. The output also includes:

- **Composition breakdown** — issue count by type (BUG/FEAT/ENH/EPIC) and priority distribution
- **Sprint run state** — progress from `.sprint-state.json` if the sprint has been started (only present on `ll-sprint run`, not on `ll-sprint show`)
- **Issue file paths** — full paths included in `ll-sprint show --json` for easy machine consumption (text output uses issue IDs only)
- **Readiness/confidence scores** — per-issue scores from any completed confidence checks
- **Issue file paths** — full paths shown in the execution plan for easy navigation
- **Human-friendly timestamps** — relative time suffixes (e.g., "3 days ago") on dated fields

Use `--json` to get all fields as structured JSON for scripting or integration.

`ll-sprint analyze` focuses specifically on file overlap. It reads each issue's Integration Map and reports which files are touched by multiple issues, which pairs would contend, and which would be forced into sub-waves. Use this when planning a sprint with many issues touching the same subsystems.

---

## Configuration

Sprint behavior is configured in `.ll/ll-config.json` under the `sprints` key:

```json
{
  "sprints": {
    "sprints_dir": ".sprints",
    "default_timeout": 3600,
    "default_max_workers": 2
  }
}
```

| Option | Default | Description |
|--------|---------|-------------|
| `sprints_dir` | `.sprints` | Directory where sprint YAML files are stored |
| `default_timeout` | `3600` | Per-issue timeout in seconds (1 hour) |
| `default_max_workers` | `2` | Max parallel workers per wave (also overridable per sprint via `options.max_workers` / `--max-workers`) |
| `max_issue_wall_clock_time` | `2700` | Hard wall-clock cap per issue in seconds (45 min); enforced via SIGALRM |
| `parallel.timeout_per_issue` | `2700` | Timeout for multi-issue waves (mirrors `max_issue_wall_clock_time`; in-place single-issue waves use `sprints.max_issue_wall_clock_time` instead) |

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
3. /ll:refine-issue <issue-id>      ← run once per captured issue
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
1. Create issues with blocked_by (hard) or depends_on (soft) fields:
     FEAT-010 has no blockers
     FEAT-011 blocked_by: [FEAT-010]   # hard stop — wave-gated
     FEAT-012 depends_on: [FEAT-010]   # soft ordering — not wave-gated
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

### Picking Up After a Partial Failure

When a sprint finishes but some issues failed, address failures without re-running the whole sprint:

```
1. ll-sprint show sprint-name              ← review which issues failed and why
2. /ll:refine-issue ISSUE-ID               ← investigate and update each failed issue
3. ll-sprint edit sprint-name --prune      ← remove any issues that are now completed/invalid
4. ll-sprint run sprint-name --only FAILED-ID-1,FAILED-ID-2
                                           ← re-run only the failed issues
5. ll-sprint show sprint-name              ← confirm all issues completed
```

If a failed issue blocks downstream issues, fix it first — the wave structure ensures dependents run after.

### Pre-PR Quality Sprint

Run code quality loops before opening a PR, then address any issues found:

```
1. /ll:check-code all                ← run lint, types, and format checks
2. /ll:scan-codebase                 ← capture any issues found
3. /ll:create-sprint                 ← sprint the findings
4. ll-sprint run quality-fixes
5. /ll:open-pr
```

### Full "Plan a Feature Sprint" Pipeline

The complete workflow from empty backlog to executed sprint is documented in detail in the [Issue Management Guide](ISSUE_MANAGEMENT_GUIDE.md). That guide covers every refinement step — discovery, enrichment, quality gates, and dependency mapping — before handing off to `ll-sprint` for execution. Start there if you are setting up a sprint from scratch.

---

## See Also

- [Issue Management Guide](ISSUE_MANAGEMENT_GUIDE.md) — refinement pipeline to run before sprint creation
- [Loops Guide](LOOPS_GUIDE.md) — create custom FSM loops for recurring sprint workflows
- `/ll:map-dependencies` — discover and validate cross-issue dependencies before building a sprint
- `/ll:issue-size-review` — decompose oversized issues before adding them to a sprint
- `/ll:review-sprint` — health check an existing sprint before running
- `ll-sprint --help` — full CLI reference for all subcommands and flags
