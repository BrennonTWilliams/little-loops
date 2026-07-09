<p align="center">
  <img src="https://raw.githubusercontent.com/BrennonTWilliams/little-loops/main/assets/little-loops.jpeg" alt="Little Loops Logo" width="200">
</p>

<p align="center">
  <a href="https://github.com/BrennonTWilliams/little-loops/releases">
    <img src="https://img.shields.io/github/v/release/BrennonTWilliams/little-loops?display_name=tag&style=flat-square" alt="Version">
  </a>
  <a href="https://github.com/BrennonTWilliams/little-loops/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/BrennonTWilliams/little-loops?style=flat-square" alt="License">
  </a>
  <a href="https://python.org">
    <img src="https://img.shields.io/badge/python-3.11+-blue.svg?style=flat-square&logo=python" alt="Python Version">
  </a>
  <a href="https://pypi.org/project/little-loops/">
    <img src="https://img.shields.io/pypi/v/little-loops?style=flat-square&label=PyPI" alt="PyPI Version">
  </a>
  <a href="https://docs.little-loops.ai">
    <img src="https://img.shields.io/badge/docs-little--loops.ai-blue?style=flat-square" alt="Docs">
  </a>
</p>

# little-loops

**The toolkit for long-horizon, eval-gated AI software development.**

Today's coding agents do small tasks well and ship features poorly. The model isn't the ceiling — the session is. little-loops removes it with the three things raw agents are missing: **durability** (the run outlives the chat), **consistency** (the toolbelt is the process), and **verification** (the harness is the spec).

Stop babysitting chats. Start shipping features.

```bash
pip install little-loops
ll-init                                            # detects your stack, writes config
ll-loop run general-task "fix the lint warnings"   # your first self-verifying loop
```

Built for [Claude Code](https://docs.anthropic.com/en/docs/claude-code), with host adapters for Codex, OpenCode, and Pi. MIT-licensed.

## 1. Run agents until done

The unit of work is the feature, the sprint, or the overnight optimization — not a single chat. Every loop is a finite-state machine whose state is checkpointed to disk after every transition, so runs survive terminal close, context exhaustion, and laptop sleep — `ll-loop resume` picks up mid-trajectory, exactly where it stopped. When one context window fills, session handoff carries the thread into a fresh one. And `ll-parallel` fans a sprint out across isolated git worktrees that converge without you.

*Ship features, not sessions.*

## 2. Smart tools create smart processes

Raw agents re-derive the same structural moves differently on every run. The `ll-` CLI removes that improvisation surface: context gathering, issue lifecycle, sprint moves, worktree setup, and branch naming all run as typed commands, and harnessed skills like `/ll:manage-issue` compose them into a fixed plan → implement → verify → complete sequence. The agent reasons *inside* steps, not about *which* steps to take — so two runs of the same feature land in the same shape, by construction rather than by prompting.

*Same feature, same shape, every run.*

## 3. The harness is the spec

Harness-driven development is TDD's analog for agent-built software: define what "working" looks like first, then loop until it passes. Layered gates — exit codes, output patterns, numeric metrics, LLM judges, full agentic simulation — grade every iteration cheapest-first, and failures route back into execution instead of forward into your codebase. The engineering tax that makes teams skip evals is automated away: `/ll:create-eval-from-issues` turns acceptance criteria into a runnable harness, `/ll:create-loop` derives one from a description, and `harness-optimize` hill-climbs the harness itself against a benchmark, accepting each mutation only when the score rises.

*Point at context. Get a harness.*

---

## Install

**Prerequisites:** Python 3.11+ and [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (the default host CLI).

```bash
pip install little-loops
ll-init
```

`ll-init` auto-detects your project type — Python, JS/TS, Go, Rust, Java, .NET, or generic — infers test/lint commands and source layout, scaffolds `.issues/`, and writes `.ll/ll-config.json`. Run it bare for an interactive TUI, or `ll-init --yes` to accept the detected defaults. Sanity-check the host integration any time with `ll-doctor`.

**Inside Claude Code**, add the plugin to get the `/ll:*` slash-command surface:

```bash
/plugin marketplace add BrennonTWilliams/little-loops
/plugin install ll@little-loops
```

**Using Codex CLI?** Run `ll-init --hosts codex` and `ll-adapt --host codex --apply` — see [docs/codex/getting-started.md](docs/codex/getting-started.md). OpenCode and Pi wire up the same way via `ll-init --hosts`.

<details>
<summary>Alternative install methods</summary>

**Local development install:** see [CONTRIBUTING.md](CONTRIBUTING.md).

**Manual configuration** — add to `.claude/settings.local.json`:

```json
{
  "extraKnownMarketplaces": {
    "local": {
      "source": {
        "source": "directory",
        "path": "/path/to/little-loops"
      }
    }
  },
  "enabledPlugins": {
    "ll@local": true
  }
}
```

</details>

## Your first loop

See what ships in the box:

```bash
ll-loop list
```

Built-in loops come with the package, grouped by category — issue management, code quality, planning, deep research, prompt optimization, generative harnesses, and more. Every one is plain YAML you can read in [`scripts/little_loops/loops/`](scripts/little_loops/loops/), and every one is documented in the [Built-in Loops Reference](docs/guides/LOOPS_REFERENCE.md).

Start with the universal one — hand it any goal:

```bash
ll-loop run general-task "fix the lint warnings"
```

`general-task` derives a definition of done from your goal, works the task, and grades itself against its gates before it's allowed to stop. You'll watch state transitions stream past; when the run completes, a per-state token/cost table shows exactly what each step spent.

A few more worth a first run:

```bash
ll-loop run brainstorm "ways to reduce flaky tests"   # multi-lens ideation → ranked brainstorm.md
ll-loop run fix-quality-and-tests                     # lint + format + types must pass before tests run
ll-loop run loop-router "describe your goal"          # not sure which loop? the router classifies and dispatches
```

Long runs belong in the background:

```bash
ll-loop run docs-sync --background   # detached; survives closing the terminal
ll-loop status docs-sync             # alive? which state? where's the log?
ll-loop resume docs-sync             # interrupted? continue mid-trajectory
```

> **Bounded by design.** Every run carries a step cap, per-edge cycle detection, and a repeated-failure stall detector that catches the "already done" no-op before it burns your iteration budget. Cost ceilings (`--max-cost`, per-state `cost_ceiling:`) and a host memory guard keep spend and RAM honest. And you can rehearse before paying: `ll-loop validate <name>` checks the YAML, `--dry-run --show-diagrams` prints the FSM and execution plan without running anything, `--worktree` isolates a run on its own branch.

When a built-in is *almost* right, `ll-loop install <name>` copies it into `.loops/` for local editing; `/ll:create-loop` writes a new one from a plain-language description; and any loop can invoke another as a sub-loop state, so pipelines compose instead of duplicating.

## From first loop to shipping pipeline

### Scan and triage a codebase

```bash
/ll:scan-codebase         # Find issues (technical)
/ll:prioritize-issues     # Auto-assign P0–P5 priorities
/ll:map-dependencies      # Cross-issue dependency graph
```

### Ship an issue end-to-end

```bash
/ll:manage-issue bug fix BUG-001   # Plan → implement → verify → complete
```

### Fan out a parallel sprint

```bash
ll-sprint create v2-launch --issues FEAT-001,FEAT-002,FEAT-003
ll-parallel --workers 3            # Three isolated worktrees, three features, zero babysitting
```

### Eval-driven development

```bash
/ll:create-eval-from-issues FEAT-001   # Turn acceptance criteria into a runnable harness
ll-loop validate harness-optimize      # Dry-run the FSM before paying for a real run
ll-loop run harness-optimize -b        # Score-gated hill climbing in the background
```

## What's in the box

- **28 slash commands** — issue discovery, refinement, planning, code quality, git, automation
- **9 specialized agents** — codebase analysis, quality assurance, automation, and research
- **67 skills** — deterministic harnesses for common workflows (confidence checks, issue wiring, loop creation)
- **38 typed CLI tools** — `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`, `ll-action`, and more
- **82 FSM loops** — recurring automation workflows (backlog triage, sprint building, eval harnesses)
- **Configuration system** — project-type templates for Python, JS/TS, Go, Rust, Java, .NET, and generic
- **Design tokens** — WCAG AA palette template set with FSM context injection for artifact-generating loops
- **Observability** — every run logged, archived, and queryable: `ll-loop history`, `ll-history`, and a per-project `.ll/history.db`

## Learn the system

Every user-facing guide lives in [`docs/guides/`](docs/guides/). Start with [Getting Started](docs/guides/GETTING_STARTED.md), then go where your work takes you:

| Guide | Read it when… |
|-------|---------------|
| [Getting Started](docs/guides/GETTING_STARTED.md) | You're new — mental model, first bug-fix workflow, when to escalate |
| [Loops Guide](docs/guides/LOOPS_GUIDE.md) | You're authoring or troubleshooting loops — patterns, background mode, safety guards |
| [Loops Reference](docs/guides/LOOPS_REFERENCE.md) | You're choosing a built-in loop or fragment library |
| [Issue Management](docs/guides/ISSUE_MANAGEMENT_GUIDE.md) | You're running the discovery → refine → implement pipeline |
| [Sprint Guide](docs/guides/SPRINT_GUIDE.md) | You have four or more issues, or dependencies that force an order |
| [Recursive Loops](docs/guides/RECURSIVE_LOOPS_GUIDE.md) | You want goal → plan → decompose → implement via the `rn-*` family |
| [Automatic Harnessing](docs/guides/AUTOMATIC_HARNESSING_GUIDE.md) | You're running a skill over many work items and want quality gates |
| [Harness Optimization](docs/guides/HARNESS_OPTIMIZATION_GUIDE.md) | You want to hill-climb a skill, prompt, or config against a benchmark |
| [Session Handoff](docs/guides/SESSION_HANDOFF.md) | Your runs keep hitting context limits |
| [History & Sessions](docs/guides/HISTORY_SESSION_GUIDE.md) | You want long-term observability: what ran, what changed, what was corrected |
| [Built-in Hooks](docs/guides/BUILTIN_HOOKS_GUIDE.md) | You want to see — and tune — everything that runs automatically |
| [Policy Router](docs/guides/POLICY_ROUTER_GUIDE.md) | A loop must branch on combinations of scored dimensions |
| [Learning Tests](docs/guides/LEARNING_TESTS_GUIDE.md) | You want external APIs proven before code builds on them |
| [Decisions Log](docs/guides/DECISIONS_LOG_GUIDE.md) | You want recorded decisions and enforced team rules |
| [Examples Mining](docs/guides/EXAMPLES_MINING_GUIDE.md) | You want prompts that improve from your own session history |
| [Workflow Analysis](docs/guides/WORKFLOW_ANALYSIS_GUIDE.md) | You want automation opportunities mined from message history |

## Documentation router

| You need… | Go to |
|-----------|-------|
| Everything, hosted and searchable | **[docs.little-loops.ai](https://docs.little-loops.ai)** |
| Every `ll-*` CLI tool, flag by flag | [CLI Reference](docs/reference/CLI.md) |
| Every `/ll:*` slash command | [Command Reference](docs/reference/COMMANDS.md) |
| Every config key, substitution rules, overrides | [Configuration Reference](docs/reference/CONFIGURATION.md) |
| Every built-in loop and fragment library | [Built-in Loops Reference](docs/guides/LOOPS_REFERENCE.md) |
| The FSM engine's internals — schema, evaluators, compiler | [FSM Loop System Design](docs/generalized-fsm-loop.md) |
| System design and diagrams | [Architecture Overview](docs/ARCHITECTURE.md) |
| Event schema for extension authors | [Event Schema Reference](docs/reference/EVENT-SCHEMA.md) |
| Codex CLI setup | [Getting Started with Codex](docs/codex/getting-started.md) |
| Something broke | [Troubleshooting](docs/development/TROUBLESHOOTING.md) |
| Dev setup, testing, guidelines | [Contributing](CONTRIBUTING.md) |

---

The ceiling on agent-built software isn't the model — it's the session. Remove it:

```bash
pip install little-loops && ll-init
```

## License

MIT
