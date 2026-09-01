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
relates_to:
- FEAT-1462
- FEAT-1623
- FEAT-1721
- FEAT-2122
- EPIC-2456
depends_on:
- ENH-2461
labels:
- codex
- opencode
- host-runner
- observability
- host-compat
verify_verdict: VALID
learning_tests_required:
- opencode
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

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- FEAT-1623's per-tool byte-metrics callback (`scripts/little_loops/hooks/post_tool_use.py`) — cited in this issue's Notes as an "analogous host-agnostic callback pattern" — is structurally different from what this issue needs: it operates on an already-normalized `LLHookEvent.payload` produced by each host's *adapter layer*, not on a raw per-host subprocess stream. Cross-host differences there are absorbed upstream in the adapter, with only small "host-tolerant accessor" fallbacks inside the handler (e.g. `tool_response` vs `tool_output`).
- Token usage has no adapter-layer equivalent: it must be parsed directly out of each host's own subprocess JSON stream inside `run_claude_command()` (`subprocess_utils.py`), not through a hook-handler payload. Any implementation should extend the existing shared per-line parser with a Codex-specific event-type branch (mirroring how that same function already special-cases Claude's `"result"` event type), rather than modeling the change on FEAT-1623's hook-handler shape.

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Assumption-safety check on the downstream chain: only `fsm/persistence.py:1010`'s `"input_tokens" in event` gate is a hard existence check. Every other reader downstream (`CostReport.from_usage_jsonl()`, `cost_graph.py:222` and siblings) uses `.get(..., 0) or 0` / `.get("model", "unknown")` defensively. This means the real bottleneck for Codex/OpenCode is entirely upstream — `ActionResult.usage_events` is simply always empty for those hosts today, so both sinks are silently skipped, not fed malformed data. A parse-path fix only needs to make `run_claude_command()` produce non-empty `TokenUsage` objects for Codex/OpenCode; nothing downstream needs defensive changes.
- `TokenUsage`'s `cache_read_tokens`/`cache_creation_tokens` fields map directly to Anthropic prompt-caching semantics, and `is_batch` is explicitly documented as Claude-specific (Message Batches API discount eligibility). Whether Codex/OpenCode expose an equivalent cache-read/cache-creation split, or have any analogous batch-dispatch concept, is unresearched anywhere in this repo — if a usage source is confirmed, the research note should state explicitly whether these three fields default to `0`/`False` for Codex/OpenCode or whether host-specific reinterpretation is needed.

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — `on_usage_detailed` callback / `run_claude_command()`
- `scripts/little_loops/host_runner.py` — `CodexRunner` / `OpenCodeRunner`
- `docs/reference/HOST_COMPATIBILITY.md` — `[^tok]` footnote update + `Token reporting` row

### Dependent Files (Callers/Importers)
- TBD — `grep -r "on_usage_detailed" scripts/` to find all consumers
- `ll-loop` run output (cost table rendering)
- `.ll/usage.jsonl` write path
- `scripts/little_loops/subprocess_utils.py:674` — invokes `on_usage_detailed` inside `run_claude_command()`'s `"result"` event branch
- `scripts/little_loops/fsm/runners.py:225` — `DefaultActionRunner.run()::_collect_usage` closure wraps the callback and accumulates into `ActionResult.usage_events`
- `scripts/little_loops/fsm/executor.py:2410-2427` — sums `result.usage_events` into the `action_complete` event payload
- `scripts/little_loops/fsm/persistence.py` `_handle_event()` — writes a `usage.jsonl` row gated on `"input_tokens" in event`
- `scripts/little_loops/cli/loop/_helpers.py` `_print_usage_summary()` — reads `usage.jsonl` via `CostReport.from_usage_jsonl()` and prints the per-state cost table

### Similar Patterns
- FEAT-1623 per-tool byte metrics (`.ll/history.db`) — analogous host-agnostic callback pattern

### Tests
- `scripts/tests/` — add coverage for parse path on any wired host (per Acceptance Criteria)

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — flip `Token reporting` row to ✓ or `partial`

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- No confirmed usage/token field exists yet in Codex's `--json` NDJSON stream schema — `thoughts/research/codex-headless-invocation.md` (cited by `CodexRunner`'s class docstring) documents flag translation only and contains zero mentions of `usage`/`tokens`; the research question in this issue's own Acceptance Criteria #1 is still open and unanswered by any existing doc or code.
- `OpenCodeRunner.build_streaming()` (`scripts/little_loops/host_runner.py:871-888`) unconditionally raises `HostNotConfigured` — no subprocess is ever spawned for OpenCode today, so there is no output stream to parse for a usage source until OpenCode orchestration itself is wired (a separate, larger gap than this issue's scope).
- The stream-json event parser in `run_claude_command()` (`scripts/little_loops/subprocess_utils.py:616-716`) applies uniformly to whatever binary `resolve_host()` selected — there is no `runner.name`/binary branch gating it today. A confirmed Codex usage source would need its own event-type branch inside this same shared loop (or a parallel per-runner parser), not a new independent code path.
- The `[^tok]` footnote in `docs/reference/HOST_COMPATIBILITY.md` already exists and already correctly cites **FEAT-2123** by name (not EPIC-1744). This issue's own Summary states the footnote was an "orphaned dead-link" to EPIC-1744 — the 2026-08-10 Verification Note already flagged that claim as stale, and this pass confirms the footnote's current content is accurate. Only the Summary's own outdated description of the footnote needs correcting; the footnote itself does not.
- No `HostCapabilities` field or `CapabilityEntry` named for "token reporting" exists anywhere in `scripts/little_loops/host_runner.py` today — the `Token reporting` row in `HOST_COMPATIBILITY.md` is hand-maintained Markdown only, not computed by `ll-doctor`. Precedent exists for a `CapabilityEntry`-only capability with no matching `HostCapabilities` boolean field (`claude_md_suppression`, present in all 4 runners' `describe_capabilities()` without a matching dataclass field) — this is the shape a new `token_reporting`-style `CapabilityEntry` could follow without necessarily adding a `HostCapabilities` field.

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- The Integration Map's "TBD — grep -r on_usage_detailed" placeholder is now resolved concretely: `DefaultActionRunner.run()::_collect_usage` closure (`fsm/runners.py:222-225`, fires only inside the prompt-mode branch, lines 192-282 — the shell-command branch has no usage concept at all) -> `FSMExecutor._run_action()` sums `result.usage_events` into `action_complete` payload (`fsm/executor.py:2410-2427`) and also appends every `(state, usage)` pair into `self._usage_events_collected` -> two independent sinks: (A) `PersistentExecutor._handle_event()` writes `usage.jsonl`, hard-gated on `"input_tokens" in event` (`fsm/persistence.py:1010`); (B) `FSMExecutor._finish()` (`fsm/executor.py:3877-3898`) calls `record_usage_event()` (`session_store/writers.py:1509`) per collected pair into the `usage_events` SQLite table, gated on `BRConfig(...).analytics_capture.usage_events`, best-effort (`except Exception: pass`).
- ENH-2461 (`depends_on`) is confirmed `status: done`, `completed_at: 2026-07-13`. It landed a *different* design than its own original plan: Option C, an independent `usage_events` table populated post-hoc by `_backfill_usage_events()` (`session_store/writers.py:2987`) parsing `raw_events`, not a live writer off `on_usage_detailed`. Its own Addendum 2 deferred the live writer (citing `_run_action()` not threading `on_usage_detailed` through). That live writer was built separately as ENH-2724 (`record_usage_event()` call in `FSMExecutor._finish()`), not part of ENH-2461's own commit. Both existing sinks are already fully host-agnostic downstream of `ActionResult.usage_events` — extending parity for Codex/OpenCode requires touching only the upstream parser in `run_claude_command()`, nothing in either sink.
- `claude_md_suppression` (present in all 4 runners' `describe_capabilities()`, `host_runner.py:536,844,1210,1396`) is the confirmed precedent for a `CapabilityEntry`-only capability with no matching `HostCapabilities` dataclass field; `cli/doctor.py:96` additionally special-cases it via `_ADVISORY_CAPABILITIES = frozenset({"claude_md_suppression"})` for how `ll-doctor` renders an advisory-only (non-boolean-gated) capability — a second precedent worth following if a `token_reporting`-style entry is added without a corresponding dataclass field.
- Test precedent for a capability-status assertion: `scripts/tests/test_cli_doctor.py:123,139` (`CapabilityEntry("claude_md_suppression", ...)`, `test_claude_md_suppression_reported_unsupported`) — template for asserting `ll-doctor`'s rendering of a new advisory-only capability.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

Concrete types, signatures, and call path for extending the existing `on_usage_detailed` callback contract to Codex/OpenCode.

### Types
(`scripts/little_loops/subprocess_utils.py:62-74`) — `TokenUsage` fields any Codex/OpenCode-sourced usage data would need to populate:
- `input_tokens: int`
- `output_tokens: int`
- `cache_read_tokens: int`
- `cache_creation_tokens: int`
- `model: str`
- `is_batch: bool = False`

### Signatures
- `run_claude_command(command: str, *, on_usage_detailed: DetailedUsageCallback | None = None)` (`subprocess_utils.py:422-432`) — existing, unmodified contract; invokes the callback only from the `etype == "result"` branch of its per-line stdout parser (`:665-697`), gated on `if on_usage_detailed and usage:`.
- `CodexRunner.build_streaming(prompt: str) -> HostInvocation` (`host_runner.py:661`) — builds a `codex exec --json ...` invocation (Codex's NDJSON streaming mode); the returned `HostInvocation` carries no usage-parsing logic of its own — all event parsing happens in `run_claude_command()`'s shared loop, not per-runner code in `host_runner.py`.
- `OpenCodeRunner.build_streaming(prompt: str) -> HostInvocation` (`host_runner.py:871-888`) — unconditionally raises `HostNotConfigured` today, so no invocation exists yet to extend.

### Call Path
Codex `codex exec --json` subprocess stdout -> `run_claude_command()`'s per-line `json.loads()` loop (`subprocess_utils.py:616-716`, host-agnostic, no binary-name branch today) -> (once a Codex event-type carrying usage is confirmed by research) a new event-type branch invoking `on_usage_detailed(TokenUsage(...))` -> `DefaultActionRunner.run()::_collect_usage` closure (`fsm/runners.py:225`) -> `FSMExecutor` sums `result.usage_events` into the `action_complete` payload (`executor.py:2410-2427`) -> `PersistentExecutor._handle_event()` writes a `usage.jsonl` row gated on `"input_tokens" in event` (`fsm/persistence.py`) -> `ll-loop run`'s `_print_usage_summary()` reads `CostReport.from_usage_jsonl()` and prints the cost table (`cli/loop/_helpers.py`)

### Decision Rules
N/A — no new decision logic. This issue's only decision point is the research question itself (does a usage source exist for Codex/OpenCode), which is scoped by Acceptance Criteria as a research note with quoted evidence, not a runtime gate, threshold, or keyword list.

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

### 2026-08-10 (`/ll:verify-issues`)

Verified 2026-08-10: core gap still real — `on_usage_detailed` (`subprocess_utils.py:353`) still only fires for the claude runner; `CodexRunner`/`OpenCodeRunner` exist in `host_runner.py` without it. However, the issue's claim that the `[^tok]` footnote in `HOST_COMPATIBILITY.md:177` is an orphaned dead-link to EPIC-1744 is now stale — that footnote already correctly self-cites FEAT-2123. Update or drop that part of the Summary.

## Session Log
- `/ll:refine-issue` - 2026-09-01T02:54:09 - `02c2a272-7226-4055-8f34-6d4118279276.jsonl`
- `/ll:refine-issue` - 2026-08-31T18:16:19 - `79825ede-998a-42fa-9870-aab9ce64b599.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:08:31 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:24 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- backlog-grooming - 2026-07-03T00:00:00Z - Consolidated the token-telemetry workstream: sequenced after ENH-2461 (`depends_on: [ENH-2461]` — the Claude-host persistence path lands first via the existing `on_usage_detailed` callback, then this issue extends the same contract to Codex/OpenCode). Decoupled from FEAT-2122 (P4 spawn-model research) — the usage-parsing research here does not depend on spawn-model behavior; FEAT-2122 moved to `relates_to`. Also linked to EPIC-2456 (F5/F6 cost-telemetry features share this callback surface).
- `/ll:audit-issue-conflicts` - 2026-06-25T21:25:33 - `91915c5b-d793-486c-a140-be4dd3d8ca1f.jsonl`
- `/ll:verify-issues` - 2026-06-17T00:00:00 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:format-issue` - 2026-06-13T23:48:43 - `b252dabd-1baf-4665-95fb-2099fac23f7c.jsonl`
