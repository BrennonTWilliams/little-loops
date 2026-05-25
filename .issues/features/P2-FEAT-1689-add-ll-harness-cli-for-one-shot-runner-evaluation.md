---
id: FEAT-1689
type: FEAT
title: "add ll-harness CLI for one-shot runner evaluation"
priority: P2
status: open
discovered_date: 2026-05-25
discovered_by: capture-issue
captured_at: "2026-05-25T00:00:03Z"
labels:
  - cli
  - harness
  - evaluation
  - captured
---

# FEAT-1689: add ll-harness CLI for one-shot runner evaluation

## Summary

Add an `ll-harness` CLI that runs any supported runner (skill, shell command, MCP tool, or raw prompt) once, evaluates the output against user-supplied criteria, and exits 0 on pass / non-zero on fail. Unlike `ll-loop run`, there is no FSM retry machinery — this is a gate tool for CI, spot-checking, and quick iteration feedback.

## Current Behavior

There is no way to evaluate a single skill invocation (or any other runner) against pass/fail criteria without authoring a full FSM loop YAML. The closest tools are `ll-loop run` (requires a loop file), `ll-action` (invokes a skill as one-shot but produces no evaluation), and the eval harness skill `/ll:create-eval-from-issues` (generates a YAML, doesn't run an inline check).

## Expected Behavior

```
ll-harness skill ll:check-code               # run skill, evaluate exit code
ll-harness cmd "python -m pytest scripts/"   # run shell command, evaluate exit code
ll-harness mcp pencil:get_screenshot --args '{"node_id":"123"}' --semantic "screenshot shows a login form"
ll-harness prompt "Summarize this file: ..."  --semantic "summary mentions Python"
```

The CLI:
1. Dispatches to the appropriate runner based on the first positional argument (`skill`, `cmd`, `mcp`, `prompt`)
2. Captures stdout, stderr, and exit code
3. Evaluates the output against the supplied criteria (`--exit-code INT`, `--semantic TEXT`, or both)
4. Prints a structured pass/fail report to stdout
5. Exits 0 on pass, 1 on fail, 2 on internal error

## Acceptance Criteria

- `ll-harness skill <name>` invokes the skill via `host_runner.py` and exits 0 when no evaluator criteria are supplied and the runner completed without error
- `ll-harness cmd <shell-string>` executes the shell command and captures stdout, stderr, and exit code
- `ll-harness mcp <server:tool> --args <JSON>` calls the MCP tool and captures its result
- `ll-harness prompt <text>` sends a raw prompt to Claude and captures the completion
- `--exit-code INT`: exits 1 when captured exit code does not match INT; exits 0 when it matches
- `--semantic TEXT`: exits 1 when the LLM judge returns `fail` or `needs_work`; exits 0 on `pass`
- When both `--exit-code` and `--semantic` are supplied, both must pass for exit 0 (criteria are ANDed)
- When no criteria are supplied, the tool exits 0 if the runner completed and 2 on timeout/internal error
- Structured pass/fail report is always printed to stdout in the format specified under "Output format"
- `--output json` produces machine-readable JSON with all fields (runner, exit, semantic, result, output)
- `--timeout SECONDS` kills the runner after the specified time and exits 2

## Motivation

Fills the gap between "run a thing" and "evaluate a thing" without requiring loop authorship. Key use cases:
- **CI gates**: `ll-harness skill ll:check-code --exit-code 0` in a pre-push hook
- **Spot-checking**: quickly verify a skill or prompt meets a bar during development without creating a loop YAML
- **Debugging**: isolate a single runner to confirm output before wiring it into a loop
- **Prompt evaluation**: test a raw prompt against criteria before promoting it to a skill

## Use Case

A developer adds a new skill and wants to confirm it produces acceptable output before publishing. They run `ll-harness skill ll:my-new-skill --semantic "output contains a summary section"`. The CLI invokes the skill, runs a semantic check against the criterion, prints `PASS` or `FAIL` with the captured output, and exits appropriately. No loop file needed, no issue required.

## Proposed Solution

### Runner dispatch

Four runner types, each mapping to existing infrastructure:

| Subcommand | Mechanism | Notes |
|---|---|---|
| `skill <name> [args]` | `resolve_host().build_streaming(...)` + skill invocation | Reuses `host_runner.py` |
| `cmd <shell-string>` | `subprocess.run(shell=True)` | Escape hatch for anything else |
| `mcp <server:tool> --args <JSON>` | MCP client call via existing MCP machinery | Returns JSON result |
| `prompt <text>` | Direct Claude API call via `anthropic` SDK | Raw completion, no skill wrapper |

### Evaluator

Two independent criteria, both optional (no criteria = always pass after run):
- `--exit-code INT` — compare captured exit code
- `--semantic TEXT` — call `check_semantic` (existing FSM evaluator logic) on captured output; structured LLM judge returning `pass`/`fail`/`needs_work`

Criteria are ANDed when both supplied.

### Output format

```
Runner:   skill ll:check-code
Exit:     0
Semantic: [not checked]
Result:   PASS
---
[captured stdout]
```

### Entry point

New script `scripts/little_loops/cli/ll_harness.py` registered as `ll-harness` in `pyproject.toml` `[project.scripts]`.

## API/Interface

```
usage: ll-harness <runner-type> <target> [runner-args...] [evaluator-flags]

Runner types:
  skill <name> [args...]        Invoke a little-loops skill
  cmd <shell-string>            Run a shell command
  mcp <server:tool> [--args J]  Call an MCP tool with JSON args
  prompt <text>                 Send a raw prompt to Claude

Evaluator flags:
  --exit-code INT               Expected exit code (default: not checked)
  --semantic TEXT               Natural-language criterion for output evaluation

Global flags:
  --timeout SECONDS             Runner timeout (default: 120)
  --output {text,json}          Output format (default: text)
  --verbose                     Show full captured output even on pass

Exit codes:
  0  PASS
  1  FAIL
  2  Internal error / timeout
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/ll_harness.py` — new entry point (create)
- `scripts/pyproject.toml` — register `ll-harness` in `[project.scripts]`
- `.claude/CLAUDE.md` — add `ll-harness` to CLI Tools list

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` — reused for `skill` runner dispatch
- `scripts/little_loops/fsm/evaluators.py` (or equivalent) — reused for `--semantic` check_semantic logic

### Similar Patterns
- `scripts/little_loops/cli/ll_action.py` — one-shot skill invocation pattern to follow
- `scripts/little_loops/cli/ll_loop.py` — runner + evaluator wiring reference

### Tests
- `scripts/tests/test_ll_harness.py` — new test file covering all four runner types and both evaluator criteria

### Documentation
- `docs/reference/API.md` — add `ll-harness` section
- `README.md` or CLI Tools section in CLAUDE.md — mention `ll-harness`

### Configuration
- N/A — no new config keys required; inherits `orchestration.host_cli` for skill/prompt runners

## Implementation Steps

1. Scaffold `ll_harness.py` CLI entry point with argparse subcommand dispatch (`skill`, `cmd`, `mcp`, `prompt`)
2. Implement runner adapters — `skill` via `host_runner.py`, `cmd` via subprocess, `mcp` via existing MCP client, `prompt` via anthropic SDK
3. Implement evaluator — exit-code comparator and `--semantic` judge (reuse or extract `check_semantic` from FSM evaluators)
4. Wire output formatter (text + JSON modes) and exit-code protocol (0/1/2)
5. Register in `pyproject.toml`, add tests, update CLAUDE.md CLI list

## Impact

- **Priority**: P2 — fills a real gap in the CLI landscape; enables CI gates and prompt-dev workflows that currently require a full loop YAML
- **Effort**: Medium — four runner adapters + evaluator reuse; `skill` and `--semantic` have the most unknowns
- **Risk**: Low — additive new CLI; no changes to existing runner or FSM paths
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`cli`, `harness`, `evaluation`, `captured`

---

## Session Log
- `/ll:format-issue` - 2026-05-25T00:03:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/416c5fec-1865-4920-b2f5-18bbcefc1861.jsonl`
- `/ll:capture-issue` - 2026-05-25T00:00:03Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1c5270a-50e9-4065-961e-edfcb5f51b85.jsonl`

---

**Open** | Created: 2026-05-25 | Priority: P2
