---
id: FEAT-2123
title: Surface per-invocation token usage from Codex and OpenCode runners
type: FEAT
priority: P3
status: open
captured_at: "2026-06-13T00:00:00Z"
discovered_date: 2026-06-13
discovered_by: capture-issue
parent: EPIC-1463
relates_to: [FEAT-1462, FEAT-1623, FEAT-1721, FEAT-2122, EPIC-2456]
depends_on: [ENH-2461]
labels: [codex, opencode, host-runner, observability, host-compat]
---

# FEAT-2123: Surface per-invocation token usage from Codex and OpenCode runners

## Summary

Per-invocation token usage is reported only for `claude`-backed runs. The
`HOST_COMPATIBILITY.md` `Token reporting` row marks both OpenCode and Codex
`✗`, and the `[^tok]` footnote previously deferred this to **EPIC-1744 — which
is the unrelated, completed "FSM Loop Hardening" epic.** That was an orphaned
dead-link: token-reporting parity for non-Claude hosts had no real tracking
issue. This issue is that tracking surface.

## Motivation

`on_usage_detailed` in `subprocess_utils.run_claude_command()` fires only for
`claude` runs because OpenCode and Codex do not expose per-invocation token
usage in their streaming output. Consequences for Codex/OpenCode-hosted runs:

- No `usage.jsonl` file written for `ll-loop` runs.
- No per-state cost table in `ll-loop run` output.
- `ll-ctx-stats` and any cost analytics are blind to non-Claude hosts.

This blocks a defensible "first-class parity" claim for observability: a Codex
user cannot see what their loops cost.

## Use Case

**Who**: A developer running `ll-loop` on a Codex or OpenCode host

**Context**: When running automation loops (`ll-loop run`) on a non-Claude host
and wanting to understand per-invocation token costs and loop efficiency

**Goal**: See the per-state cost table in `ll-loop run` output and have
`usage.jsonl` populated, just like Claude-backed runs

**Outcome**: Token usage is surfaced (or formally documented as a permanent host
limitation), enabling a defensible parity claim for observability across all
supported hosts

## Current Behavior

- `ll-doctor` reports `Token reporting: ✗` for OpenCode and Codex.
- `[^tok]` footnote in `HOST_COMPATIBILITY.md` now points here (was EPIC-1744).
- FEAT-1623's per-tool byte metrics (`.ll/history.db`) work on all hosts, but
  *token* usage specifically is Claude-only.

## Expected Behavior

Per-invocation token usage is surfaced for Codex (and OpenCode where feasible),
or the gap is formally documented as a permanent host limitation with the
evidence that proves it.

## Acceptance Criteria

- Research note: does `codex exec` expose token usage anywhere (final JSON
  event, `--json` summary, stderr summary line, or a session-log file)? Same
  question for OpenCode. Record findings with quoted evidence.
- If a usage source exists: `CodexRunner` (and/or `OpenCodeRunner`) parses it
  and invokes the `on_usage_detailed` callback so `usage.jsonl` and the
  `ll-loop run` cost table populate on those hosts.
- `HostCapabilities` / `ll-doctor` flips `Token reporting` to ✓ (or `partial`)
  for any host where usage is surfaced.
- If no usage source exists for a host: `[^tok]` is updated to a documented
  permanent-gap marker citing the research note (not a tracking placeholder).
- `scripts/tests/` coverage for the parse path on any wired host.

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — `on_usage_detailed` callback / `run_claude_command()`
- `scripts/little_loops/host_runner.py` — `CodexRunner` / `OpenCodeRunner`
- `docs/reference/HOST_COMPATIBILITY.md` — `[^tok]` footnote update + `Token reporting` row

### Dependent Files (Callers/Importers)
- TBD — `grep -r "on_usage_detailed" scripts/` to find all consumers
- `ll-loop` run output (cost table rendering)
- `.ll/usage.jsonl` write path

### Similar Patterns
- FEAT-1623 per-tool byte metrics (`.ll/history.db`) — analogous host-agnostic callback pattern

### Tests
- `scripts/tests/` — add coverage for parse path on any wired host (per Acceptance Criteria)

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — flip `Token reporting` row to ✓ or `partial`

### Configuration
- N/A

## Implementation Steps

1. Research Codex and OpenCode event payloads for token usage data (check
   `codex exec --json`, stderr summary, session-log files, `--output-schema`)
2. Document findings with quoted evidence; update `[^tok]` footnote accordingly
3. If usage source found: implement parse path in `CodexRunner` / `OpenCodeRunner`
   to invoke `on_usage_detailed` with the same callback signature as the Claude path
4. Update `HostCapabilities` / `ll-doctor` to flip `Token reporting` to ✓ or `partial`
5. Add `scripts/tests/` coverage for the parse path on the wired host(s)
6. If no usage source exists: mark `[^tok]` as a permanent-gap footnote citing the research note

## Notes

- Codex's `--output-schema` (ENH-1530) and final-message JSON may carry a
  usage block — check the terminal `codex exec` event payload first.
- Keep the callback contract identical to the Claude path so downstream
  consumers (`usage.jsonl`, cost table, `ll-ctx-stats`) need no host-specific
  branching.

## Impact

- **Priority**: P3 — Observability gap for non-Claude hosts; not blocking core
  functionality but limits the "first-class parity" claim
- **Effort**: Medium — Requires research into Codex/OpenCode event payloads,
  then parse-path implementation if a usage source exists
- **Risk**: Low — Additive change; existing Claude callback contract unchanged;
  non-Claude paths are currently silent (no regression risk)
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/subprocess_utils.py` | `on_usage_detailed` callback |
| `scripts/little_loops/host_runner.py` | `CodexRunner` / `OpenCodeRunner` |
| `docs/reference/HOST_COMPATIBILITY.md` | `[^tok]` footnote now points here |
| FEAT-1623 | Per-tool byte metrics (related observability work) |

## Status

**Open** | Created: 2026-06-13 | Priority: P3

## Verification Notes (2026-06-17)

- Code references accurate: `on_usage_detailed` callback in `subprocess_utils.py:289/446`, `CodexRunner` at `host_runner.py:351`, `OpenCodeRunner` at `:626` — all confirmed present.
- The `[^tok]` footnote referencing EPIC-1744 is stale; EPIC-1744 is an unrelated completed epic. Verify that `HOST_COMPATIBILITY.md` footnote still links to this ID and update or remove.

## Session Log
- backlog-grooming - 2026-07-03T00:00:00Z - Consolidated the token-telemetry workstream: sequenced after ENH-2461 (`depends_on: [ENH-2461]` — the Claude-host persistence path lands first via the existing `on_usage_detailed` callback, then this issue extends the same contract to Codex/OpenCode). Decoupled from FEAT-2122 (P4 spawn-model research) — the usage-parsing research here does not depend on spawn-model behavior; FEAT-2122 moved to `relates_to`. Also linked to EPIC-2456 (F5/F6 cost-telemetry features share this callback surface).
- `/ll:audit-issue-conflicts` - 2026-06-25T21:25:33 - `91915c5b-d793-486c-a140-be4dd3d8ca1f.jsonl`
- `/ll:verify-issues` - 2026-06-17T00:00:00 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:format-issue` - 2026-06-13T23:48:43 - `b252dabd-1baf-4665-95fb-2099fac23f7c.jsonl`
