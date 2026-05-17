---
captured_at: "2026-05-17T07:28:10Z"
discovered_date: "2026-05-17"
discovered_by: capture-issue
status: open
---

# FEAT-1546: Add `ll-loop next-loop` sub-command to suggest next loop from execution history

## Summary

Add a new `ll-loop next-loop` sub-command (or top-level `ll-next-loop`) that inspects loop execution history under `.loops/.history/` and suggests the next FSM loop to run, along with the right input/context parameters. Enables "auto-continue" workflows where the system can pick up the next obvious task (e.g., spawn another `autodev` run against currently-active issues) without the human specifying which loop to execute.

## Motivation

When the human user steps away (sleep, lunch, meeting), the obvious next loop run is often inferable from recent history — e.g. `autodev` has been run 12 times in the past week against active issues, so the natural continuation is another `autodev` pass. Today, the human has to manually choose the loop and its inputs every time, which prevents fully unattended chaining and scheduling. `next-loop` closes that gap: it picks the loop and the parameters, so `/loop`, scheduled jobs, or on-completion hooks can dispatch follow-up work without a human in the loop.

## Current Behavior

- `ll-loop run <name>` requires the user to know both the loop name and its parameters.
- `.loops/.history/<timestamp>-<loop-name>/` records every past run but nothing reads it for prediction.
- `/ll:loop-suggester` exists, but suggests *new loops to author* from message history (FEAT-219, FEAT-716), not which *existing loop* to run next.
- Auto-chaining a follow-up loop requires the caller to hard-code the loop name and inputs.

## Expected Behavior

`ll-loop next-loop` (default count = 1):

1. Scans `.loops/.history/` for loop run frequency, recency, and outcome.
2. Picks the loop with the strongest historical signal (frequency × recency, weighted toward successful completions).
3. If the loop accepts parameters (input arg, `--context key=value`), derives sensible defaults from project state — e.g. for `autodev`, pass the current set of `status: open` issue IDs as input.
4. Prints a suggestion the caller can act on, with both a human-readable summary and a machine-readable form (JSON / shell-ready command line).
5. With `--count N`, returns the top N candidates instead of just one.

Should compose cleanly with `/loop`, `/ll:schedule`, and on-completion hooks so a finishing loop can dispatch the next one.

## Use Case

User runs `/ll:schedule "ll-loop next-loop --execute" --every 2h` before stepping away. Every two hours, the scheduler invokes `next-loop`, which inspects history, picks `autodev`, pulls the current `status: open` issue list as input, and either prints the command or (with `--execute`) directly runs it. The user wakes up to a stack of attempted issues instead of an idle queue.

## API / Interface

New surface area:

- `ll-loop next-loop [--count N] [--format text|json] [--execute] [--exclude <name>...]`
  - Default `--count 1`.
  - `--format json` emits a list of `{loop, input, context, score, rationale, command}` objects suitable for piping into other tools.
  - `--execute` runs the top suggestion immediately via the same code path as `ll-loop run`.
  - `--exclude` skips named loops (e.g. exclude the loop that just finished if calling from an on-completion hook to avoid trivial self-loops).

Parameter-suggestion contract:

- For loops that declare a parameter shape (input arg, context keys) in their YAML, `next-loop` should resolve those to concrete values from project state where there is an obvious mapping (e.g. `autodev` → active issue IDs; `refine-to-ready-issue` → most-recently-captured issue lacking `ready: true`).
- Where no mapping is known, fall back to the same default the loop's YAML declares, or omit the parameter and flag it in `rationale`.

## Implementation Steps

1. Add a `next-loop` sub-parser under `scripts/little_loops/cli/loop/__main__.py` (alongside `run`, `info`, `lifecycle`, etc.).
2. New module `scripts/little_loops/cli/loop/next_loop.py`:
   - Read `.loops/.history/` directory listing; group by loop name.
   - Compute score per loop: weighted blend of count, recency (days-since-last-run decay), and success rate (from run metadata, if recorded — otherwise treat all as equal).
   - For the top-scored loop(s), look up the loop YAML to learn its parameter shape.
3. Add a small parameter-resolver registry mapping loop name → callable that returns suggested input/context (e.g. `autodev` → active issues via the existing `ll-issues list` code path).
4. Wire `--execute` to call the existing run path used by `ll-loop run`.
5. Emit JSON and text output formats; ensure JSON is stable for downstream tooling.

## Acceptance Criteria

- `ll-loop next-loop` prints exactly one suggestion by default, including loop name and concrete parameter values.
- `ll-loop next-loop --count 3` prints three ranked suggestions.
- `ll-loop next-loop --format json` emits valid JSON with `loop`, `input`, `context`, `score`, `rationale`, and `command` keys.
- For `autodev`, the suggested input matches the current set of active issue IDs (verifiable against `ll-issues list --status open`).
- `--execute` runs the top suggestion through the same code path as `ll-loop run` (no duplicate runner logic).
- Empty history produces a clear "no history available" message and exit code 1, not a crash.
- Unit tests cover: ranking, parameter resolution for at least one parameterized loop, JSON output stability, and the empty-history case.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Loop runner and history layout |
| `.claude/CLAUDE.md` | CLI tool conventions and `ll-*` entry-point pattern |

## Session Log
- `/ll:capture-issue` - 2026-05-17T07:28:10Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dce8ab13-a2bf-4753-b7b8-76c3a497a18f.jsonl`

---

## Status

Open
