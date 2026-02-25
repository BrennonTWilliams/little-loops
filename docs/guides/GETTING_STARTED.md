# Getting Started with little-loops

## What Is little-loops?

little-loops turns Claude Code into a structured development workflow engine. The core idea: instead of one-shot prompts, you write issues — Markdown files that travel with your code and serve as rich context for AI-driven implementation. A well-formed issue tells the agent *why* something needs to change, *where* in the codebase to look, and *how* to verify it worked. The agent can then plan, implement, test, and archive the change with minimal back-and-forth from you.

The system has three layers you can use independently or together:

- **Issues** — Markdown files in `.issues/` that capture bugs, features, and enhancements. The atomic unit of work. You can use this layer alone indefinitely.
- **Sprints** — Named batch runs with dependency-aware execution ordering. Useful when you have four or more issues, or issues that must run in sequence.
- **Loops** — YAML-defined FSM automations that run recurring workflows (quality gates, scheduled scans) without repeated prompting.

The core flow in one line: **observe → capture → refine → implement → complete**.

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
pip install -e "./scripts[dev]"
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

Run `/ll:init` once per project. It auto-detects your project type and generates a starter configuration.

```bash
/ll:init
```

What it detects: Python, JavaScript/TypeScript, Go, Rust, Java (Maven or Gradle), and .NET projects. For each type, it infers sensible defaults for test commands, lint commands, and source directories.

What it creates:

```
.issues/
  bugs/
  features/
  enhancements/
  completed/
.claude/ll-config.json
```

The three config fields most relevant to beginners:

| Field | Purpose | Example |
|-------|---------|---------|
| `project.test_cmd` | Command to run tests | `pytest scripts/tests/` |
| `project.lint_cmd` | Command to run lint/format | `ruff check scripts/` |
| `project.src_dir` | Primary source directory | `scripts/` |

Start with the auto-detected defaults. Use `/ll:configure` later to tune individual settings.

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

`/ll:manage-issue` handles the full implementation cycle: plan, implement, run tests, and move the issue to completed.

```bash
/ll:manage-issue bug fix BUG-001
#    → Plans → implements → runs tests → moves issue to .issues/completed/
```

When it finishes, the issue file is gone from `.issues/bugs/` and has moved to `.issues/completed/`.

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

### Filename Format

```
P2-BUG-042-sprint-runner-ignores-failed-issues.md
│  │   │   └─ kebab-case description
│  │   └─── globally unique issue number
│  └─────── type: BUG, FEAT, or ENH
└────────── priority: P0 (critical) to P5 (low)
```

IDs are globally unique across all types — you won't have both `BUG-007` and `FEAT-007`.

### The `completed/` Directory

`.issues/completed/` is a **sibling** of `bugs/`, `features/`, and `enhancements/` — not nested inside any of them.

```
.issues/
  bugs/             ← active bugs
  features/         ← active features
  enhancements/     ← active enhancements
  completed/        ← ALL completed issues (bugs, features, and enhancements)
```

A completed bug moves to `.issues/completed/P2-BUG-042-...md`, not `.issues/bugs/completed/`.

### Use Anchors, Not Line Numbers

Code references in issue files use function and class names, not line numbers.

```markdown
# Correct
Root cause is in function `_run_wave()` in `scripts/little_loops/sprint.py`.

# Wrong — line numbers drift
Root cause is at line 1847 in sprint.py.
```

### Minimal vs. Full Template

`/ll:capture-issue` creates a full template by default. For quick capture without filling in every section, use the issue file directly — run `/ll:format-issue` later to fill in missing sections when you're ready to implement.

---

## Discovering Issues You Didn't Know Existed

Two commands for finding problems and gaps proactively, without waiting for them to surface in production.

### Scan the Codebase

```bash
/ll:scan-codebase
#    → Static analysis: finds bugs, tech debt, and missing error handling
```

Creates issue files for anything it finds. Run this periodically or after major refactors.

### Scan Against Your Product Goals

```bash
/ll:scan-product
#    → Compares codebase against your goals document, finds feature gaps
```

Requires a product goals file (configured in `ll-config.json`). Useful for identifying what the codebase is missing relative to what you said you wanted to build.

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

The eight commands you'll use most often:

| Command | What It Does |
|---------|-------------|
| `/ll:init` | Auto-detect project type and create config + issue directories |
| `/ll:capture-issue` | Create an issue file from a natural-language description |
| `/ll:ready-issue` | Validate an issue for implementation readiness |
| `/ll:manage-issue` | Plan, implement, test, and complete an issue end-to-end |
| `/ll:commit` | Review diff, propose commit message, and commit with approval |
| `/ll:scan-codebase` | Static analysis to discover bugs and tech debt |
| `/ll:prioritize-issues` | Assign P0-P5 priorities to issue files |
| `/ll:create-sprint` | Create a sprint from active issues for batch execution |

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

---

## See Also

- [README](../../README.md) — Installation, feature overview, and configuration summary
- [Command Reference](../reference/COMMANDS.md) — Full slash command reference with arguments and examples
- [Configuration Reference](../reference/CONFIGURATION.md) — All `ll-config.json` options
- [Troubleshooting](../development/TROUBLESHOOTING.md) — Common issues and diagnostic commands
