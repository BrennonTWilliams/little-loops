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

A dev toolkit for long-horizon, eval-gated AI software development. Built as a Claude Code plugin.

little-loops gives AI agents three things they're missing: **durability** (the run outlives the session), **consistency** (the toolbelt is the process), and **verification** (the eval is the spec). Together they remove the invisible ceiling that keeps agents doing small tasks well and shipping features poorly.

## The three claims

### 1. The session ends. The run doesn't.

The unit of work is the feature, the sprint, or the overnight optimization — not a single chat. Runs survive terminal close, context exhaustion, and laptop sleep. Parallel sprints fan out across isolated worktrees and complete independently of your terminal.

- **`ll-parallel`** — kick off N concurrent feature implementations in isolated worktrees. Walk away. They converge without you.
- **`--background` + `ll-loop resume`** — runs survive terminal close, sleep, and reboot. Resume picks up exactly where it stopped, mid-trajectory.
- **`harness-optimize`** — score-gated overnight optimization runs. Accept-or-revert each mutation. If interrupted, resume to the highest-scoring commit.
- **Session handoff** — a fresh context picks up mid-issue without losing the thread. Context limits stop being a planning constraint.

*Ship features, not sessions.*

### 2. The toolbelt is the process.

Raw agents re-derive the same structural moves differently each run. The `ll-` CLI removes the improvisation surface: context gathering, issue lifecycle, sprint moves, and worktree setup all run as typed commands. Two runs of the same feature land in the same shape — by construction, not by prompting.

- **21 typed CLI tools** (`ll-issue`, `ll-sprint`, `ll-loop`, `ll-parallel`, `ll-action`, etc.) — structural work runs as commands, not improvised tool calls
- **`/ll:manage-issue`** — composes the CLIs into a fixed plan → implement → verify → complete sequence. The agent reasons *inside* steps, not about *which* steps to take
- **Skill harnesses** (`/ll:ready-issue`, `/ll:wire-issue`, `/ll:confidence-check`) — same inputs, same gates, same outputs
- **Worktree setup, branch naming, issue ID generation** — mechanical operations that produce identical structure across runs

*Same feature, same shape, every run.*

### 3. The harness is the spec. And the harness writes itself.

Eval-driven development: TDD's analog for agent-built software. Define what "working" looks like first, then iterate until the harness passes. The eval grades, writes, and improves itself — removing the harness engineering tax that keeps most teams skipping evals entirely.

**The eval grades:**
- Six layered gate types — exit code, deterministic external state, full agentic user simulation, LLM-as-judge, diff size invariant, no-op detection
- Cheapest gates run first. Failures route back to execution rather than advancing
- Stall detection catches the "already done" no-op that silently burns through iteration budgets

**The eval writes itself:**
- `/ll:create-eval-from-issues` — turn an issue's acceptance criteria into a runnable harness in under a minute
- `/ll:create-loop` — auto-derive the full evaluation pipeline from your project config
- Annotated templates and `ll-loop validate` — dry-run the FSM before paying for a real run

**The eval improves itself:**
- `harness-optimize` — hill-climbing on harness artifacts. One targeted edit per iteration, benchmark, accept on rising score, revert otherwise
- APO loop category with five prompt-optimization strategies — point it at a prompt, converge to a target score
- `/ll:audit-loop-run` — four-valued verdict (`met` / `phantom` / `partial` / `degraded`) catches failure modes humans miss

*Point at an issue. Get a harness.*

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

<details>
<summary>Alternative install methods</summary>

**From local path (development):**

```bash
/plugin marketplace add /path/to/little-loops
/plugin install ll@little-loops
```

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

### Scan and triage a codebase

```bash
/ll:init                  # Auto-detect project type, generate config
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

## What's included

- **28 slash commands** — issue discovery, refinement, planning, code quality, git, automation
- **8 specialized agents** — codebase analysis, pattern finding, consistency checking, web research
- **28 skills** — deterministic harnesses for common workflows (confidence checks, issue wiring, loop creation)
- **22 CLI tools** — `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`, `ll-action`, and more
- **47 FSM loops** — recurring automation workflows (backlog triage, sprint building, eval harnesses)
- **Configuration system** — project-type templates for Python, JS/TS, Go, Rust, Java, .NET, and generic

Full reference: [Command Reference](docs/reference/COMMANDS.md) · [CLI Reference](docs/reference/CLI.md)

---

## Documentation

- **[docs.little-loops.ai](https://docs.little-loops.ai)** — hosted docs (searchable, dark mode, mobile)
- [Configuration Reference](docs/reference/CONFIGURATION.md) — all options, variable substitution, overrides
- [Loops Guide](docs/guides/LOOPS_GUIDE.md) — FSM YAML authoring, loop patterns, practical examples
- [Session Handoff Guide](docs/guides/SESSION_HANDOFF.md) — context management and continuation
- [Architecture Overview](docs/ARCHITECTURE.md) — system design and diagrams
- [Troubleshooting](docs/development/TROUBLESHOOTING.md) — common issues and solutions
- [Contributing](CONTRIBUTING.md) — development setup, testing, guidelines

## License

MIT
