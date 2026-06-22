# Getting Started with little-loops

## What Is little-loops?

little-loops turns Claude Code into a structured development workflow engine. The core idea: instead of one-shot prompts, you write issues — Markdown files that travel with your code and serve as rich context for AI-driven implementation. A well-formed issue tells the agent *why* something needs to change, *where* in the codebase to look, and *how* to verify it worked. The agent can then plan, implement, test, and archive the change with minimal back-and-forth from you.

The system has three layers you can use independently or together:

- **Issues** — Markdown files in `.issues/` that capture bugs, features, and enhancements. The atomic unit of work. You can use this layer alone indefinitely.
- **Sprints** — Named batch runs with dependency-aware execution ordering. Useful when you have four or more issues, or issues that must run in sequence.
- **Loops** — YAML-defined FSM automations that run recurring workflows (quality gates, scheduled scans) without repeated prompting.

The core flow in one line: **observe → capture → refine → implement → complete**.

```
observe ──→ /ll:capture-issue ──→ /ll:ready-issue ──→ /ll:manage-issue ──→ /ll:commit
 (spot it)      (record it)         (validate it)       (implement it)      (ship it)
```

---

## Installation

### Step 1: Install the Plugin

```bash
# Add the GitHub repository as a marketplace source
/plugin marketplace add BrennonTWilliams/little-loops

# Install the plugin
/plugin install ll@little-loops
```

For local development, use a local path instead:

```bash
/plugin marketplace add /path/to/little-loops
/plugin install ll@little-loops
```

### Step 2: Install the Python CLI Tools

The slash commands run inside Claude Code sessions. The CLI tools (`ll-auto`, `ll-sprint`, `ll-loop`, etc.) run from your terminal and drive automated execution.

```bash
pip install little-loops
```

### Step 3: Verify

```bash
# Terminal: confirm CLI tools are installed
ll-auto --help

# Claude Code session: confirm plugin is loaded
/ll:help
```

---

## Set Up Your Project

Run `ll-init` once per project. It auto-detects your project type and generates a starter configuration.

```bash
ll-init
```

**Detected project types:** Python, JavaScript/TypeScript, Go, Rust, Java (Maven or Gradle), and .NET. For each type, it infers sensible defaults for test commands, lint commands, and source directories. Unrecognized projects fall back to a generic template.

**What gets created:**

```
.issues/
  bugs/
  features/
  enhancements/
  epics/
.ll/ll-config.json
```

**What else happens:** `ll-init` also appends little-loops state files to your `.gitignore` (e.g. `.auto-manage-state.json`, `.ll/ll-context-state.json`) so runtime state never ends up committed.

### Flags

| Flag | What it does | When to use it |
|------|-------------|---------------|
| _(none)_ | Launches an interactive TUI to configure options step by step | Default — works for most projects |
| `--yes` | Accepts all auto-detected defaults without any confirmation prompts | Fastest path when auto-detection gets it right |
| `--force` | Overwrites an existing `.ll/ll-config.json` (TUI now pre-populates from existing values automatically, so `--force` is rarely needed) | Forcing a full template reset regardless of existing config |
| `--dry-run` | Previews what would be generated without writing any files | Checking what `ll-init` would produce before committing |
| `--plan` | Emits a JSON plan `{detected, proposed_config, host_options, warnings}` without writing anything | CI pipelines, inspection before applying, or piping into `ll-init apply --config` |
| `--enable FEATURE` | Enable an optional feature in the headless config (repeatable). Valid: `decisions`, `scratch_pad`, `session_capture`, `product`, `analytics`, `context_monitor`, `learning_tests`, `session_digest`, `prompt_optimization` | Activating optional features without the TUI |
| `--disable FEATURE` | Disable a feature (same valid names as `--enable`) | Turning off a feature that was auto-enabled |
| `--upgrade` | Act on version drift automatically (install or upgrade the pip package). Default headless mode is warn-only | CI pipelines or automation where you want hands-free upgrades |
| `--root / -C` | Set the project root directory (default: current directory) | Running `ll-init` from a different working directory |
| `--hosts HOST…` | Wire adapters for additional host CLIs: `claude-code`, `codex`, `opencode`, `pi` | Only needed if you use little-loops with multiple AI coding tools |

### Key Config Fields

The three fields most relevant to beginners:

| Field | Purpose | Example |
|-------|---------|---------|
| `project.test_cmd` | Command to run tests | `pytest scripts/tests/` |
| `project.lint_cmd` | Command to run lint/format | `ruff check scripts/` |
| `project.src_dir` | Primary source directory | `scripts/` |

Start with the auto-detected defaults.

### Existing Installation Detection

`ll-init` automatically detects whether little-loops is already installed before writing any config. The detection logic runs in both headless (`--yes`) and TUI modes:

| Detected state | What ll-init does |
|----------------|-------------------|
| Not installed (no pip package, no global plugin) | Prints a notice; **warns only** by default — pass `--upgrade` to install automatically |
| Global plugin (`ll@little-loops` via `claude plugin list --json`) | Reads the plugin version; checks marketplace for drift |
| Local dev install (editable `pip install -e`) | Reads the installed version; checks PyPI for drift |
| PyPI consumer install (`pip install little-loops`) | Reads the installed version; checks PyPI for drift |
| Version mismatch (installed ≠ PyPI latest) | Prints a notice with the upgrade command; **warns only** by default — pass `--upgrade` to upgrade automatically |
| Up to date | Proceeds silently |

When an existing `.ll/ll-config.json` is found, the TUI pre-populates every field from its current values so a re-run always starts from your actual config rather than defaults. Use `--force` to reset to template defaults instead of merging.

### After Setup

Tune individual settings interactively with `/ll:configure` — it presents every config option with its current value and lets you edit in-place. For less common options, see the [Configuration Reference](../reference/CONFIGURATION.md).

---

## Your First Workflow: Fix a Bug

The simplest complete workflow — from observation to committed fix.

### Step 1: Capture

Describe the bug in plain language. The skill creates a properly formatted issue file.

```bash
/ll:capture-issue "login button doesn't respond on mobile Safari"
#    → Creates .issues/bugs/P3-BUG-001-login-button-doesnt-respond-on-mobile-safari.md
```

The file gets a priority prefix (`P3`), type (`BUG`), globally unique ID (`001`), and a kebab-case description. Open it to review — capture fills in what it can from context and leaves placeholders for what it can't determine.

### Step 2: Validate (Optional but Recommended)

Before implementing, run a quality check. This catches missing context, vague reproduction steps, or implementation gaps that would slow down the agent.

```bash
/ll:ready-issue BUG-001
#    → Checks quality, auto-corrects what it can, flags open questions
```

For a trivial bug, skip this step and go straight to implementation. For anything you'll hand off to automated tools, the quality check pays for itself.

### Step 3: Implement

`/ll:manage-issue` handles the full implementation cycle: plan, implement, run tests, and mark the issue complete.

```bash
/ll:manage-issue bug fix BUG-001
#    → Plans → implements → runs tests → sets status: done in frontmatter
```

When it finishes, the issue file remains in `.issues/bugs/` with `status: done` in its frontmatter.

### Step 4: Commit

Review the diff, approve the commit message, and commit.

```bash
/ll:commit
#    → Reviews diff, proposes commit message, asks for approval before committing
```

The commit message follows conventional commit format. You approve before anything is written to the repo.

---

## Understanding Issue Files

A few things that trip up new users:

### Filenames

```
P2-BUG-042-sprint-runner-ignores-failed-issues.md
│  │   │   └─ kebab-case description
│  │   └─── globally unique issue number
│  └─────── type: BUG, FEAT, ENH, or EPIC
└────────── priority: P0 (critical) to P5 (low)
```

IDs are globally unique across all types — you won't have both `BUG-007` and `FEAT-007`.

### Status and Priority

Priority levels run from P0 (critical, must fix immediately) to P5 (low, nice-to-have). The priority prefix in the filename determines ordering in automated runs — `ll-auto` and `ll-sprint` process lower numbers first. You can reassign priority at any time by renaming the file or running `/ll:prioritize-issues`.

The `status` field inside the issue file tracks where the issue is in the workflow: `open`, `in_progress`, `blocked`, `deferred`, `done`, or `cancelled`. Automated tools read and update this field; you rarely need to edit it directly. See [ISSUE_MANAGEMENT_GUIDE.md](ISSUE_MANAGEMENT_GUIDE.md) for the full table and meanings.

### Directory Structure

All issues live in type directories regardless of their lifecycle state. Status is tracked via the `status` frontmatter field.

```
.issues/
  bugs/             ← BUG issues (open, in_progress, done, deferred, etc.)
  features/         ← FEAT issues (any status)
  enhancements/     ← ENH issues (any status)
  epics/            ← EPIC coordination containers (any status)
```

A completed bug stays in `.issues/bugs/` with `status: done` in its frontmatter — it is not moved.

### Use Anchors, Not Line Numbers

Code references in issue files use function and class names, not line numbers.

```markdown
# Correct
Root cause is in function `_run_wave()` in `scripts/little_loops/sprint.py`.

# Wrong — line numbers drift
Root cause is at line 1847 in sprint.py.
```

### Minimal vs. Full Template

By default, `/ll:capture-issue` creates a full v2.0 issue with all sections. Pass `--quick` to create a minimal issue (Summary + Impact only) when you just want to record an idea quickly.

```bash
/ll:capture-issue "login button broken"           # full template (default)
/ll:capture-issue "login button broken" --quick   # minimal — 5 fields only
/ll:format-issue BUG-001                          # promote minimal → full when ready to implement
```

---

## Discovering Issues You Didn't Know Existed

Three scanning commands find problems proactively. Use the table below to pick the right one:

| You want to find... | Use this command |
|--------------------|-----------------|
| Bugs, tech debt, and error handling gaps in existing code | `/ll:scan-codebase` |
| Structural problems (bad coupling, missing abstractions, inconsistencies) | `/ll:audit-architecture` |
| Feature gaps relative to what you said you wanted to build | `/ll:scan-product` |
| A single issue you spotted yourself | `/ll:capture-issue "description"` |

`/ll:scan-codebase` is the right default for most projects. `/ll:audit-architecture` is especially useful when you've just inherited an unfamiliar codebase and want to understand its systemic problems before diving in. `/ll:scan-product` requires a goals doc (`.ll/ll-goals.md`) — `ll-init` creates one automatically, or `scan-product` discovers goals automatically from your README and roadmap docs.

### After Scanning

A scan often produces more issues than you want to implement. Two commands to reduce the list:

```bash
/ll:prioritize-issues
#    → Adds P0-P5 priority prefixes to filenames based on severity and impact

/ll:tradeoff-review-issues
#    → Evaluates utility vs. complexity; recommends which to implement, update, or close
```

---

## When to Escalate

| Situation | Tool |
|-----------|------|
| 1-3 issues, no dependencies | `/ll:manage-issue` directly |
| 4+ issues, or issues with blockers | `/ll:create-sprint` + `ll-sprint run` |
| Recurring quality check (lint, tests, scans) | `ll-loop run <loop-name>` |

**`/ll:manage-issue`** works well for a few issues. It's interactive and handles one issue at a time.

**Sprints** shine when issues have dependencies. The sprint system computes execution order automatically from `blocked_by` fields, runs independent issues in parallel, and can resume after interruption.

**Loops** are for automation you'd otherwise run by hand on a schedule — a nightly quality gate, a weekly scan, a fix-and-verify cycle. You define the workflow once as a YAML file; the FSM engine executes it without prompting.

---

## Quick Reference

The ten commands you'll use most often:

| Command | What It Does |
|---------|-------------|
| `ll-init` | Auto-detect project type and create config + issue directories |
| `/ll:capture-issue` | Create an issue file from a natural-language description |
| `/ll:ready-issue` | Validate an issue for implementation readiness |
| `/ll:manage-issue` | Plan, implement, test, and complete an issue end-to-end |
| `/ll:commit` | Review diff, propose commit message, and commit with approval |
| `/ll:scan-codebase` | Static analysis to discover bugs and tech debt |
| `/ll:prioritize-issues` | Assign P0-P5 priorities to issue files |
| `/ll:create-sprint` | Create a sprint from active issues for batch execution |
| `/ll:format-issue` | Validate and normalize issue file structure |
| `/ll:refine-issue` | Fill knowledge gaps with codebase research |

For the full list: `/ll:help` or see [Command Reference](../reference/COMMANDS.md).

---

## What's Next?

Once you're comfortable with the basic workflow, each guide covers a deeper area:

| Guide | Go here when... |
|-------|----------------|
| [Issue Management Guide](ISSUE_MANAGEMENT_GUIDE.md) | You want the full refinement pipeline: normalize → prioritize → format → refine → verify |
| [Sprint Guide](SPRINT_GUIDE.md) | You have multiple issues with dependencies and want batch execution with waves |
| [Loops Guide](LOOPS_GUIDE.md) | You want to automate a recurring workflow (quality gate, fix cycle) as an FSM |
| [Session Handoff Guide](SESSION_HANDOFF.md) | Your sessions are hitting context limits and you need seamless continuation |
| [History & Session Guide](HISTORY_SESSION_GUIDE.md) | You want to query past sessions, inject historical context into planning, or analyze project trends |
| [Decisions Log Guide](DECISIONS_LOG_GUIDE.md) | You want to record architectural decisions, enforce team rules, or understand how `decision_needed` gates automation |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ll-init` fails with "project type not detected" | Run `ll-init` with the TUI (no flags) and specify `src_dir`, `test_cmd`, and `lint_cmd` manually. |
| `/ll:manage-issue` says "issue not found" | Issue IDs are case-sensitive. Run `ll-issues list` to see exact IDs. Check that the issue has `status: open` (not `done` or `cancelled`). |
| Issue doesn't appear in `ll-issues list` | The file may have a malformed filename. Run `/ll:normalize-issues` to fix naming problems. |
| You assigned P1 but the issue isn't being processed first | `ll-auto` processes by filename priority prefix. Rename the file or run `/ll:prioritize-issues` to update the prefix. |
| Commands aren't showing up in Claude Code | Run `/ll:help` — if it returns nothing, the plugin may not be loaded. Re-run `/plugin install ll@little-loops`. |

For deeper diagnostics, see [Troubleshooting](../development/TROUBLESHOOTING.md).

---

## See Also

- [README](../../README.md) — Installation, feature overview, and configuration summary
- [Command Reference](../reference/COMMANDS.md) — Full slash command reference with arguments and examples
- [Configuration Reference](../reference/CONFIGURATION.md) — All `ll-config.json` options
- [Troubleshooting](../development/TROUBLESHOOTING.md) — Common issues and diagnostic commands

---

Contributing to little-loops? Use the editable dev install instead of the PyPI package: `pip install -e "./scripts[dev]"`. See [CONTRIBUTING.md](../../CONTRIBUTING.md) for development setup and guidelines.
