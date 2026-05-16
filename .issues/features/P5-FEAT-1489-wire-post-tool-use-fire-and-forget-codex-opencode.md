---
id: FEAT-1489
type: FEAT
priority: P5
status: open
captured_at: '2026-05-16T01:32:44Z'
discovered_date: 2026-05-16
discovered_by: manage-issue
parent: EPIC-1463
decision_needed: false
testable: true
---

# FEAT-1489: Wire post_tool_use (fire-and-forget) for Codex and OpenCode; benchmark pre_tool_use

## Summary

FEAT-1488 research concluded: wire `post_tool_use` as fire-and-forget for Codex and
OpenCode immediately (no blocking, zero user-visible overhead); run the benchmark script
`scripts/tests/bench_opencode_adapter.py` to measure cold-start p95; then wire
`pre_tool_use` opt-in-only if p95 < 200ms, or implement a sidecar if p95 ≥ 400ms.

## Current Behavior

`post_tool_use` and `pre_tool_use` are listed as `(deferred)` in the Codex and OpenCode
adapter event→intent tables. No handler module or adapter wiring exists for either
intent on these hosts. The benchmark script does not exist.

## Expected Behavior

After this issue:
- `scripts/tests/bench_opencode_adapter.py` measures OpenCode adapter cold-start p95 and
  prints a decision verdict against the 200ms / 400ms thresholds.
- `post_tool_use` is wired for Codex (`PostToolUse` in `hooks.json`) and OpenCode
  (`tool.execute.after` in `index.ts`) as fire-and-forget (no await on subprocess exit).
- `scripts/little_loops/hooks/post_tool_use.py` handler module exists with a no-op
  `handle()` ready for consumers to populate.
- `pre_tool_use` is wired opt-in-only if the benchmark shows p95 < 200ms; otherwise a
  follow-up issue is filed for sidecar implementation.
- `docs/reference/HOST_COMPATIBILITY.md` `[^hot]` footnote updated with measured p95.

## Use Case

**Who**: Any future consumer needing per-tool observability (audit logging, token
budgeting, rate-limit enforcement) on Codex or OpenCode

**Context**: FEAT-1488 produced the written decision; this issue executes it

**Goal**: Green `post_tool_use` cells for Codex and OpenCode in the parity matrix;
benchmark data on record; decision on `pre_tool_use` wiring

## Acceptance Criteria

- [ ] `scripts/tests/bench_opencode_adapter.py` runs and prints min/median/p95/max for `session_start`; p95 decision verdict recorded in `hooks/adapters/opencode/README.md ## Latency Target`
- [ ] `scripts/little_loops/hooks/post_tool_use.py` exists with `handle(event: LLHookEvent) -> LLHookResult` returning a pass result
- [ ] `hooks/adapters/codex/hooks.json` includes a `PostToolUse` matcher invoking a `post-tool-use.sh` adapter script (fire-and-forget: no blocking exit wait)
- [ ] `hooks/adapters/opencode/index.ts` handles `tool.execute.after` via `spawnIntent("post_tool_use", ...)` without awaiting exit code (fire-and-forget)
- [ ] `scripts/little_loops/hooks/__init__.py` `_dispatch_table()` includes `post_tool_use` entry; `_USAGE` string updated
- [ ] `docs/reference/HOST_COMPATIBILITY.md` `post_tool_use` cells for OpenCode and Codex updated from `(deferred)` to `✓`
- [ ] `pre_tool_use` wired opt-in-only OR follow-up issue filed for sidecar, based on benchmark result

## Motivation

`post_tool_use` as fire-and-forget is the clearest quick win from the FEAT-1488
research: zero user-visible latency cost, unblocks audit-logging and metrics consumers,
minimal code change. The benchmark script also satisfies the README gate that blocks
hot-path intent wiring.

## Proposed Solution

1. Create `scripts/little_loops/hooks/post_tool_use.py` — no-op handler following
   `scripts/little_loops/hooks/session_start.py` pattern
2. Add `"post_tool_use": post_tool_use.handle` to `_dispatch_table()` in
   `scripts/little_loops/hooks/__init__.py`; update `_USAGE` string
3. Create `hooks/adapters/codex/post-tool-use.sh` — follow `prompt-submit.sh` pattern;
   add `PostToolUse` to `hooks/adapters/codex/hooks.json` (timeout: 5s, fire-and-forget)
4. Add `tool.execute.after` handler to `hooks/adapters/opencode/index.ts` using
   `spawnIntent` without awaiting `proc.exited`
5. Run `scripts/tests/bench_opencode_adapter.py`; record p95 in
   `hooks/adapters/opencode/README.md ## Latency Target`
6. Based on benchmark: wire `pre_tool_use` opt-in-only OR file sidecar issue
7. Update `docs/reference/HOST_COMPATIBILITY.md` parity cells

## Integration Map

### Files to Create

- `scripts/little_loops/hooks/post_tool_use.py` — follow `session_start.py` pattern
- `hooks/adapters/codex/post-tool-use.sh` — follow `prompt-submit.sh` pattern
- `scripts/tests/test_hook_post_tool_use.py` — follow `test_hook_session_start.py` pattern

### Files to Modify

- `scripts/little_loops/hooks/__init__.py` — add `post_tool_use` to `_dispatch_table()`; update `_USAGE`
- `hooks/adapters/codex/hooks.json` — add `PostToolUse` matcher (note: changes require user re-trust per Codex trust-hash model)
- `hooks/adapters/opencode/index.ts` — add `tool.execute.after` handler; extend `Intent` type alias
- `docs/reference/HOST_COMPATIBILITY.md` — flip `post_tool_use` cells; update `[^hot]` footnote with p95 measurement
- `hooks/adapters/opencode/README.md` — record p95 benchmark result in `## Latency Target`
- `scripts/tests/test_hook_intents.py` — add `test_dispatch_post_tool_use_happy_path`; fix `test_dispatch_unknown_intent` error message assertion

### Conditional (based on benchmark result)

If p95 < 200ms:
- `scripts/little_loops/hooks/pre_tool_use.py` — create no-op handler
- `hooks/adapters/codex/pre-tool-use.sh` — create adapter script
- `hooks/adapters/opencode/index.ts` — add `tool.execute.before` handler (synchronous)
- `hooks/adapters/codex/hooks.json` — add `PreToolUse` matcher with opt-in config gate
- `docs/reference/HOST_COMPATIBILITY.md` — flip `pre_tool_use` cells

If p95 ≥ 400ms:
- File new issue: implement `UnixSocketTransport`-based sidecar for `pre_tool_use`

### Dependent Files (Callers/Importers)

- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` and `main_hooks()` call all handler modules; any caller of `main_hooks` indirectly depends on new handler
- `hooks/adapters/codex/hooks.json` — trust-hash changes require user re-trust; document in PR

### Similar Patterns

- `scripts/little_loops/hooks/session_start.py` — handler module pattern to follow for `post_tool_use.py`
- `hooks/adapters/codex/prompt-submit.sh` — adapter shell script pattern for `post-tool-use.sh`
- `hooks/adapters/opencode/index.ts` existing intent handlers — `spawnIntent` pattern for `tool.execute.after`
- `scripts/tests/test_hook_session_start.py` — test pattern for new `test_hook_post_tool_use.py`

### Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — `post_tool_use` parity cells and `[^hot]` footnote
- `hooks/adapters/opencode/README.md` — `## Latency Target` section for p95 benchmark result
- `hooks/adapters/codex/hooks.json` — trust-hash re-trust note for PR description

### Configuration

- `hooks/adapters/codex/hooks.json` — adding `PostToolUse` matcher triggers trust-hash invalidation; users must re-trust

## Impact

- **Priority**: P5 — no current consumer; unblocking future work
- **Effort**: Small-to-Medium
- **Risk**: Low — additive only; `PostToolUse` matcher in `hooks.json` causes user re-trust prompt (trust-hash churn); document in PR
- **Breaking Change**: No (hook trust prompt is not a breaking change, it's expected)

## Implementation Steps

1. Create `post_tool_use.py` handler module following `session_start.py` pattern
2. Register handler in `_dispatch_table()` and update `_USAGE` string in `hooks/__init__.py`
3. Wire Codex adapter — fire-and-forget shell script + `PostToolUse` matcher in `hooks.json`
4. Wire OpenCode adapter — `tool.execute.after` handler in `index.ts`, `spawnIntent` without awaiting exit
5. Run benchmark script; record p95 in `hooks/adapters/opencode/README.md ## Latency Target`
6. Decision gate: wire `pre_tool_use` opt-in (p95 < 200ms) OR file sidecar issue (p95 ≥ 400ms)
7. Flip `post_tool_use` parity cells in `HOST_COMPATIBILITY.md`; update `[^hot]` footnote with measured p95

## Related Key Documentation

- Parent epic: EPIC-1463
- Research spike: FEAT-1488 (`thoughts/research/hot-path-hook-intents.md`)
- Benchmark script: `scripts/tests/bench_opencode_adapter.py` (created by FEAT-1488)

## Labels

codex, opencode, host-compat, hooks

## Status

**Open** | Created: 2026-05-16 | Priority: P5


## Session Log
- `/ll:format-issue` - 2026-05-16T03:45:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0311cf7-493f-4a79-bc9d-67419d002020.jsonl`
