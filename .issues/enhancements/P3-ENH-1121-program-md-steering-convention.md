---
discovered_date: "2026-04-16"
discovered_by: capture-issue
source: ~/.claude/plans/review-this-open-source-cosmic-galaxy.md
---

# ENH-1121: `.ll/program.md` Steering Convention for Long-Horizon Loop Runs

## Summary

Adopt a single canonical human-authored steering file — `.ll/program.md` — as the directive input for long-horizon, unattended loop runs (initially `harness-optimize`, FEAT-1120). Running `ll-loop run harness-optimize` with no args reads `.ll/program.md` and kicks off. Existing workflows are untouched; the file is optional.

## Current Pain Point

Steering for long-horizon runs today is spread across `CLAUDE.md`, `.ll/ll-config.json`, issue files, and per-invocation CLI args. A user who wants to kick off an overnight harness-optimization run has no single place to write "here's what I want optimized, here's the task set, here's the budget, here are the constraints." autoagent's `program.md` is the most distinctive UX idea in that project — a single file owns the directive, so the user edits one thing and walks away.

## Motivation

This enhancement would:
- Give long-horizon runs a single, obvious steering surface. The user edits one file instead of threading args through the CLI.
- Make overnight runs replayable — `program.md` is the durable record of what the run was *told* to do, not just what flags it received.
- Lower the effort ceiling for harness-optimize and any future long-horizon loops: typing `ll-loop run harness-optimize` should Just Work if the user has populated `.ll/program.md`.

## Expected Behavior

- `.ll/program.md` is a markdown file with a conventional (but not rigid) structure:
  - **Directive** — free-form prose of what to optimize and why
  - **Targets** — file paths / globs the loop may mutate
  - **Benchmark** — task directory and scorer to use
  - **Budget** — wall-clock / $ / token cap (pairs with long-horizon run UX if that ships later)
  - **Constraints** — free-form guardrails (e.g., "don't touch CLAUDE.md section between `<!-- frozen -->` markers")
- `ll-loop run harness-optimize` with no args reads `.ll/program.md`. CLI args override file values when both are present.
- Absent `.ll/program.md`, the command prints a helpful message pointing at a scaffold command (or a doc link) and exits non-zero.
- The file is optional and specific to loops that opt into it. No existing loop's behavior changes.

## Use Case

**Who**: Power user kicking off an overnight harness-optimization run

**Context**: Wants to walk away for 8+ hours and come back to a branch of accepted mutations

**Goal**: Edit `.ll/program.md` once, run `ll-loop run harness-optimize`, close the laptop

**Outcome**: The loop reads the directive, uses the declared targets/benchmark/budget, and produces an auditable trajectory keyed to a single durable input file

## Proposed Solution

### `scripts/little_loops/cli/loop.py`

- When `ll-loop run <name>` is called with no args (or with `--program-md`), check for `.ll/program.md`. If present, parse and merge into the loop's initial context.
- Precedence: CLI args > `program.md` > loop defaults.
- Parsing can be pragmatic (find known section headings, extract code-fenced blocks for path lists). No schema required yet — the convention emerges; formalize only if drift shows up.

### `scripts/little_loops/loops/harness-optimize.yaml` (FEAT-1120)

First consumer. `load_directive` state reads `.ll/program.md` via the CLI-provided context.

### Documentation

- `docs/reference/program-md.md` — the convention, recommended sections, examples
- `/ll:help` — mention the file for relevant loops
- Optional scaffold: `ll-init` or a new `/ll:init-program` command can seed a starter `.ll/program.md`

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` | Current steering surface — program.md does not replace it, it complements it for loop runs |
| `.ll/ll-config.json` | Machine config — orthogonal to program.md (which is prose directive) |
| `docs/ARCHITECTURE.md` | FSM loop execution, context propagation |

## Acceptance Criteria

- [ ] `ll-loop run <name>` reads `.ll/program.md` when present and merges parsed fields into loop context
- [ ] CLI args override file values; absent file is not an error for loops that don't require it
- [ ] `harness-optimize` (FEAT-1120) consumes the file's Directive/Targets/Benchmark fields
- [ ] `docs/reference/program-md.md` documents the convention with a worked example
- [ ] Unit test covers: file present + parsed, file absent + graceful fallback, CLI override wins
- [ ] No regression: existing loops unaffected (`python -m pytest scripts/tests/`)

## Dependencies

Related: FEAT-1120 (harness-optimize loop) — first consumer. This enhancement is useful but not required for FEAT-1120 to ship; it can land alongside or shortly after.

## Session Log
- `/ll:capture-issue` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2fb1a4ee-5512-43ed-b858-2a21a4738fb8.jsonl`

---

## Status

Open
