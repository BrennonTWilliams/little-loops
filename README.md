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

**The toolkit for long-horizon, eval-gated AI software development.** Built as a Claude Code plugin.

Today's agents do small tasks well and ship features poorly. little-loops removes that ceiling with three things they're missing: **durability** (the run outlives the session), **consistency** (the toolbelt is the process), and **verification** (the harness is the spec).

Stop babysitting chats. Start shipping features.

## 1. Chat sessions are holding you back. Run asynchronous agents until done — scale without limits.

The unit of work is the feature, the sprint, or the overnight optimization — not a single chat. Runs survive terminal close, context exhaustion, and laptop sleep. Parallel sprints fan out across isolated worktrees and complete independently of your terminal.

- **`ll-parallel`** — kick off N concurrent feature implementations in isolated worktrees. Walk away. They converge without you.
- **`--background` + `ll-loop resume`** — runs survive terminal close, sleep, and reboot. Resume picks up exactly where it stopped, mid-trajectory.
- **`harness-optimize`** — score-gated overnight optimization runs. Accept-or-revert each mutation. If interrupted, resume to the highest-scoring commit.
- **Session handoff** — a fresh context picks up mid-issue without losing the thread. Context limits stop being a planning constraint.

*Ship features, not sessions.*

## 2. Smart tools create smart processes.

Raw agents re-derive the same structural moves differently each run. The `ll-` CLI removes the improvisation surface: context gathering, issue lifecycle, sprint moves, and worktree setup all run as typed commands. Two runs of the same feature land in the same shape — by construction, not by prompting.

- **35 typed CLI tools** (`ll-issues`, `ll-sprint`, `ll-loop`, `ll-parallel`, `ll-action`, etc.) — structural work runs as commands, not improvised tool calls
- **`/ll:manage-issue`** — composes the CLIs into a fixed plan → implement → verify → complete sequence. The agent reasons *inside* steps, not about *which* steps to take
- **Skill harnesses** (`/ll:ready-issue`, `/ll:wire-issue`, `/ll:confidence-check`) — same inputs, same gates, same outputs
- **Worktree setup, branch naming, issue ID generation** — mechanical operations that produce identical structure across runs

*Same feature, same shape, every run.*

## 3. Harness-driven development is awesome. And hard. Auto-generate autonomous harnesses and let your agents go anywhere.

Harness-driven development is TDD's analog for agent-built software: define what "working" looks like first, then iterate until the harness passes. little-loops grades, writes, and improves the harness for you — removing the engineering tax that keeps most teams skipping evals entirely.

**The harness grades:**
- Twelve layered gate types (exit code through full agentic simulation), cheapest first — failures route back to execution, not forward
- Stall detection catches the "already done" no-op that silently burns through iteration budgets

**The harness writes itself:**
- `/ll:create-eval-from-issues` — turn an issue's acceptance criteria into a runnable harness in under a minute
- `/ll:create-loop` — auto-derive the full harness from your project config
- `ll-loop validate` — dry-run the FSM before paying for a real run

**The harness improves itself:**
- `harness-optimize` — hill-climbing on harness artifacts. One targeted edit per iteration, benchmark, accept on rising score, revert otherwise
- Prompt optimization loops — point at a prompt, converge to a target score
- `/ll:audit-loop-run` — four-valued verdict catches failure modes humans miss

→ [Loops Guide](docs/guides/LOOPS_GUIDE.md) for gate types, FSM authoring, and harness patterns

*Point at context. Get a harness.*

---

## Install

**Prerequisites:** [Claude Code](https://docs.anthropic.com/en/docs/claude-code) + Python 3.11+

```bash
# Add the GitHub repository as a marketplace
/plugin marketplace add BrennonTWilliams/little-loops

# Install the plugin
/plugin install ll@little-loops

# Install CLI tools (for ll-parallel, ll-loop, ll-auto, etc.)
pip install little-loops
```

**Using Codex CLI?** See [docs/codex/getting-started.md](docs/codex/getting-started.md) — run `ll-init --hosts codex` and `ll-adapt-skills-for-codex --apply` to get started.

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

---

## First 60 seconds

Four ways to feel the difference, top to bottom:

### Scan and triage a codebase

```bash
ll-init                   # Auto-detect project type, generate config
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

---

## What's in the box

- **28 slash commands** — issue discovery, refinement, planning, code quality, git, automation
- **9 specialized agents** — codebase analysis, quality assurance, automation, and research
- **36 skills** — deterministic harnesses for common workflows (confidence checks, issue wiring, loop creation)
- **35 CLI tools** — `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`, `ll-action`, and more
- **94 FSM loops** — recurring automation workflows (backlog triage, sprint building, eval harnesses)
- **Configuration system** — project-type templates for Python, JS/TS, Go, Rust, Java, .NET, and generic
- **Design tokens** — WCAG AA palette template set with FSM context injection for artifact-generating loops

Full reference: [Command Reference](docs/reference/COMMANDS.md) · [CLI Reference](docs/reference/CLI.md)

---

## Documentation

- **[docs.little-loops.ai](https://docs.little-loops.ai)** — hosted docs (searchable, dark mode, mobile)
- [Configuration Reference](docs/reference/CONFIGURATION.md) — all options, variable substitution, overrides
- [Loops Guide](docs/guides/LOOPS_GUIDE.md) — FSM YAML authoring, loop patterns, practical examples
- [Harness Optimization Guide](docs/guides/HARNESS_OPTIMIZATION_GUIDE.md) — iteratively optimizing skills, commands, and configs against a benchmark
- [Session Handoff Guide](docs/guides/SESSION_HANDOFF.md) — context management and continuation
- [Architecture Overview](docs/ARCHITECTURE.md) — system design and diagrams
- [Troubleshooting](docs/development/TROUBLESHOOTING.md) — common issues and solutions
- [Contributing](CONTRIBUTING.md) — development setup, testing, guidelines

## License

MIT
