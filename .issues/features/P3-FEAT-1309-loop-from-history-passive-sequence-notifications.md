---
captured_at: "2026-05-01T17:31:53Z"
discovered_date: "2026-05-01"
discovered_by: capture-issue
---

# FEAT-1309: Loop-from-history passive sequence notifications

## Summary

Add passive notifications to `/ll:loop-suggester` so repeated 3+ step sequences detected across recent `~/.claude` session logs surface as opt-in, dismissable suggestions at session start, instead of waiting for the user to invoke the command explicitly.

## Current Behavior

`/ll:loop-suggester` runs only on demand: the user must invoke it explicitly with message history. Repeated multi-step sequences across recent sessions are never surfaced proactively, so candidate automations remain undiscovered until the user happens to ask.

## Expected Behavior

A `--passive-scan` mode plus a config-gated `SessionStart`/`Stop` hook walks recent `~/.claude/projects/<project>/*.jsonl`, mines n-grams of length ≥ `min_sequence_length` that occur ≥ `min_occurrences` times within `window_days`, and emits a single non-blocking notification line per qualifying sequence. `--dismiss <id>` suppresses a sequence for at least `cooldown_days`. The hook is default-off; existing on-demand behavior is unchanged.

## Motivation

`/ll:loop-suggester` currently only proposes loops on demand — the user must explicitly run it and pass message history. Users don't know when their behavior has crossed a "this is now a habit" threshold, so candidate automations sit undiscovered. Push the existing pattern detection further so it surfaces proposals proactively when a repeated 3+ step sequence is observed across recent `~/.claude` session logs.

## Use Case

A user has, over the last month, repeatedly run `/ll:capture-issue` → `/ll:refine-issue` → `/ll:ready-issue` on individual issues. After the 8th occurrence in 30 days, the harness emits a passive notification at session start (or after the next `Stop` hook fires):

> "I noticed you do `/ll:capture-issue` → `/ll:refine-issue` → `/ll:ready-issue` 8 times in the last 30 days. Want this as a loop? Run `/ll:create-loop` or dismiss with `/ll:loop-suggester --dismiss capture-refine-ready`."

The notification is informational, non-blocking, and remembers dismissals so it doesn't nag.

## API/Interface

New surface area on top of the existing command:

- `/ll:loop-suggester --passive-scan` — run sequence detection across logs in `~/.claude/projects/<project>/*.jsonl`, emit any sequences crossing the threshold to stdout in a notification-friendly format. No-op if nothing crosses the threshold.
- `/ll:loop-suggester --dismiss <sequence-id>` — record a dismissal (in `.ll/loop-suggester-dismissals.json` or similar) so that sequence stops triggering until reset.
- Hook integration: a `SessionStart` (or `Stop`) hook entry that invokes `--passive-scan` and prints the notification line via the user-facing channel. Hook is opt-in via `.ll/ll-config.json` under e.g. `loop_suggester.passive_notifications.enabled`.

Config additions (new keys under `loop_suggester` in `ll-config.json`):

- `passive_notifications.enabled` (bool, default `false`) — gate the hook entirely.
- `passive_notifications.min_occurrences` (int, default `5`) — threshold before a sequence is surfaced.
- `passive_notifications.window_days` (int, default `30`) — lookback window.
- `passive_notifications.min_sequence_length` (int, default `3`) — minimum steps in a sequence.
- `passive_notifications.cooldown_days` (int, default `7`) — re-suggest cadence after dismissal.

## Implementation Steps

1. Audit existing pattern-detection logic in `ll-workflows` (`scripts/little_loops/cli/workflows.py`), `/ll:analyze-history`, and `commands/loop-suggester.md` BEFORE writing any new mining code. Identify whether the n-gram detection here can be served by extracting/reusing one of those existing helpers, and only fall back to a parallel implementation if reuse is genuinely unworkable. Then extract the chosen logic into a single reusable Python helper in `scripts/little_loops/` so all three callers (on-demand command, passive scan, and the existing analysis paths) share one detector.
2. Add a sequence-mining pass that walks recent `~/.claude/projects/<project>/*.jsonl`, extracts user-action events (slash commands, skill invocations), and finds n-grams of length ≥ `min_sequence_length` that occur ≥ `min_occurrences` times within `window_days`.
3. Implement dismissal/cooldown state in a small JSON file under `.ll/` keyed by a stable sequence id (e.g. hash of the ordered step names).
4. Add `--passive-scan` and `--dismiss` argument paths to `commands/loop-suggester.md`.
5. Add a `SessionStart` (or `Stop`) hook in `hooks/hooks.json` that invokes the passive scan when the config flag is on, and renders any output as a single-line notification (`ℹ️ Loop suggestion: …`).
6. Tests: unit tests for the n-gram detector (in `scripts/tests/`), and a smoke test that the hook is a no-op when disabled or below threshold.
7. Docs: update `commands/loop-suggester.md` description + `docs/` if there is a relevant automation doc.

## Acceptance Criteria

- Running `/ll:loop-suggester --passive-scan` against a fixture log with a 3-step sequence repeated ≥ `min_occurrences` times in the window prints a single proposal line; running it against a log without such a sequence prints nothing.
- `--dismiss <id>` suppresses that sequence for at least `cooldown_days`.
- The `SessionStart`/`Stop` hook is gated by config and is a no-op (zero stdout, zero blocking) when disabled.
- Existing `/ll:loop-suggester` (no-flag, on-demand) behavior is unchanged.
- `python -m pytest scripts/tests/` passes including new tests covering the n-gram detector and dismissal state.

## Impact

- **Priority**: P3 - Discoverability improvement; complements rather than replaces existing on-demand path.
- **Effort**: Medium - Extract pattern detection to shared helper, add n-gram mining, dismissal state, hook wiring, and tests.
- **Risk**: Low - Hook is opt-in and gated by config; default-off means no noise for existing users.
- **Breaking Change**: No - Additive surface; existing `/ll:loop-suggester` behavior preserved.

## Labels

feature, loop-suggester, automation, hooks, notifications, captured

## Related Key Documentation

| Category | Document | Why It's Relevant |
|----------|----------|-------------------|
| guidelines | `.claude/CLAUDE.md` | Skills-over-Agents preference; commands/* layout; how new commands are wired in. |
| architecture | `docs/ARCHITECTURE.md` | Where hooks, commands, and the Python package fit; correct home for the shared n-gram helper. |

## Status

- **State**: Open
- **Priority**: P3
- **Type**: FEAT

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:format-issue` - 2026-05-01T17:38:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1483ec77-4cf9-4aca-8312-065f15a52a5f.jsonl`
- `/ll:capture-issue` - 2026-05-01T17:31:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c39518f0-2048-46ca-aa4c-975a04a64be5.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Two clarifications from 2026-05-01 audit:

1. **Reuse existing pattern detection.** Implementation Step 1 is updated to require auditing `ll-workflows`, `/ll:analyze-history`, and `commands/loop-suggester.md` BEFORE writing any new n-gram miner. Extract a single shared helper and have all three callers use it; only build a parallel implementation if reuse is genuinely unworkable.
2. **Suggested loops remain learning-state-agnostic.** Loop scaffolds emitted by passive scan should not pre-declare `type: learning` (FEAT-1283). The suggester emits skeletons; users add learning-gate states later by hand.
