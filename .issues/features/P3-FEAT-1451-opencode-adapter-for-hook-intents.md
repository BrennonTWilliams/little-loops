---
id: FEAT-1451
type: FEAT
priority: P3
status: done
parent: FEAT-1116
discovered_date: 2026-05-12
discovered_by: issue-size-review
completed_at: 2026-05-12T03:01:19Z
decision_needed: false
confidence_score: 98
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1451: OpenCode Adapter for Hook Intents

## Summary

Write the OpenCode TypeScript plugin adapter that shells out to `python -m little_loops.hooks <intent>` for SessionStart and PreCompact. This replaces FEAT-961's parallel reimplementation approach. Coordinate with FEAT-961 before executing.

## Parent Issue

Decomposed from FEAT-1116: Hook-Intent Abstraction Layer for Multi-Host Support

## Depends On

- FEAT-1449 (PreCompact Python core handler must exist)
- FEAT-1450 (SessionStart Python core handler must exist)

## Scope

Covers FEAT-1116 Implementation Step 6.

**Decision 3 (from FEAT-1116)**: The OpenCode adapter ships as shell-out first — no FFI, no persistent sidecar in the MVP. The OpenCode TS plugin invokes `python -m little_loops.hooks <intent>` per hook call.

- Create `hooks/adapters/opencode/` directory with TS plugin adapter
- Adapter covers `SessionStart` and `PreCompact` intents (MVP scope)
- When extending to hot-path intents (`PreToolUse`/`PostToolUse`), include **latency measurement** as an explicit deliverable so any sidecar follow-up is data-driven
- **Coordinate with FEAT-961** before executing: if FEAT-961 merges its parallel reimplementation first, the adapter approach arrives too late to replace it

## New Files to Create

- `hooks/adapters/opencode/` — TS plugin adapter directory
- `hooks/adapters/opencode/index.ts` — OpenCode `Plugin` entry point that registers `session.created` and `session.compacted` handlers
- `hooks/adapters/opencode/package.json` — `{ "name": "@ll/opencode-adapter", "type": "module" }` pinning `@opencode-ai/plugin` (v1.2.27 per FEAT-961 reference) and the Bun runtime
- `hooks/adapters/opencode/tsconfig.json` — minimal TS config for Bun-flavored ESM
- `hooks/adapters/opencode/README.md` — install/registration instructions for OpenCode users
- `scripts/tests/test_opencode_adapter.py` (or sibling TS smoke test) — verifies the adapter's spawned-subprocess contract against the same Python dispatcher

## Integration Map

### Reference Adapters to Mirror (Claude Code — the canonical template)

- `hooks/adapters/claude-code/session-start.sh` — three-line shell wrapper: `INPUT=$(cat); echo "$INPUT" | python -m little_loops.hooks session_start; exit $?`
- `hooks/adapters/claude-code/precompact.sh` — same shape, different intent

The TS adapter mirrors this exactly: spawn `python -m little_loops.hooks <intent>`, pipe the host's event payload to stdin, propagate exit code, and surface stdout/stderr back to OpenCode.

### Python Dispatcher (host-agnostic — already exists)

- `scripts/little_loops/hooks/__init__.py` in `main_hooks()` — CLI dispatcher; reads JSON from stdin, builds `LLHookEvent`, calls handler, writes `result.stdout` to stdout / `result.feedback` to stderr / returns `result.exit_code`. **Currently hardcodes `host="claude-code"`** at the construction site (see Proposed Solution Option A vs B).
- `scripts/little_loops/hooks/__main__.py` — module entry that calls `main_hooks()`
- `scripts/little_loops/hooks/types.py` in `LLHookEvent`, `LLHookResult` — wire dataclasses; `LLHookEvent.host` docstring already enumerates `"opencode"` as an expected value
- `scripts/little_loops/hooks/session_start.py` in `handle()` — returns merged-config JSON on `result.stdout`, status lines on `result.feedback`, `exit_code=0`
- `scripts/little_loops/hooks/pre_compact.py` in `handle()` — returns `exit_code=2` with feedback string on success; reads `event.payload["transcript_path"]`

### Subprocess Contract for the TS Adapter

| Channel | Direction | Format |
|---|---|---|
| stdin | adapter → python | Raw JSON dict (the host's event payload — for `pre_compact` must include `transcript_path`) |
| stdout | python → adapter | Raw bytes; for `session_start` this is the merged config JSON (consumed by OpenCode as session context); empty for `pre_compact` |
| stderr | python → adapter | Human-readable status/feedback lines |
| exit code | python → adapter | `0` = pass, `2` = block + inject feedback, `1` = unknown intent (hard error) |
| cwd | adapter sets | Must be the project root so the Python handlers' `Path.cwd()` resolves `.ll/ll-config.json` and writes `.ll/ll-precompact-state.json` correctly |

### OpenCode Event → Intent Mapping (MVP scope: 2 of 6 events)

| OpenCode event | ll intent | Python invocation |
|---|---|---|
| `session.created` | `session_start` | `python -m little_loops.hooks session_start` |
| `session.compacted` | `pre_compact` | `python -m little_loops.hooks pre_compact` |
| `tool.execute.before` | (deferred — hot path) | — |
| `tool.execute.after` | (deferred — hot path) | — |
| `session.idle` | (deferred) | — |
| `tui.prompt.append` | (deferred) | — |

Hot-path events (`tool.execute.before/after`) are deferred per FEAT-1116 Decision 3 until latency is measured.

### Wiring (Host-Side)

- Claude Code wires adapters in `hooks/hooks.json` under `SessionStart` / `PreCompact` events (one entry each)
- OpenCode has no equivalent JSON config: registration happens **inside** `hooks/adapters/opencode/index.ts` by returning the handler map from the `Plugin` function (per `@opencode-ai/plugin` v1.2.27 API in FEAT-961 reference design)

### Tests

- `scripts/tests/test_hook_intents.py` in `TestHooksMainModule` — module-level subprocess dispatch tests (template for OpenCode adapter integration tests that verify subprocess exit codes, stdout/stderr routing, and cwd-dependent file writes)
- `scripts/tests/test_hooks_integration.py` in `TestSessionStartValidation` — shows the `subprocess.run([str(script)], input=<json>, capture_output=True, text=True, timeout=5)` pattern that adapter tests should follow
- `scripts/tests/test_hook_session_start.py`, `test_hook_pre_compact.py` — Python-direct handler tests; not changed by this issue but show the underlying behavior the adapter must round-trip

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_pre_compact.py` — **Correction**: the actual pre_compact handler test file on disk is `test_pre_compact.py` (not `test_hook_pre_compact.py` referenced above — that file does not exist); not changed by this issue but documents the handler behavior the adapter must round-trip
- `test_env_var_overrides_config_threshold` in `scripts/tests/test_hooks_integration.py` — shows the `os.environ.copy()` + `env=env` kwarg pattern for injecting `LL_HOOK_HOST` env var in new Option A tests (within `TestContextMonitor` class)
- **Note: No Bun/TypeScript test runner exists in this project** — `scripts/tests/test_opencode_adapter.py` must be a Python subprocess test only; invoke the adapter via `subprocess.run(["bun", "hooks/adapters/opencode/index.ts"], ...)` with a `pytest.importorskip`-style skip if Bun is unavailable; follow the `cwd=str(tmp_path)` pattern from `TestHooksMainModule.test_dispatch_pre_compact_happy_path` rather than `os.chdir`

### Related Issues (Coordination Surface)

- `.issues/completed/P3-FEAT-1116-hook-intent-abstraction-layer.md` — parent epic; Decision 3 fixes the shell-out architecture
- `.issues/completed/P4-FEAT-961-opencode-js-ts-plugin.md` — **superseded 2026-04-22**; safe to proceed without coordination since no parallel reimplementation work was merged. The "coordinate with FEAT-961" acceptance criterion in this issue can be marked satisfied: FEAT-961 is closed and contains no merged code under `opencode-plugin/`. Its preserved event-mapping table and Bun/`@opencode-ai/plugin` v1.2.27 SDK references remain valuable as design input for this thinner adapter.
- `.issues/completed/P3-FEAT-1449-precompact-intent-python-core-and-claude-code-adapter.md` — completed dependency
- `.issues/features/P3-FEAT-1450-sessionstart-intent-python-core-and-claude-code-adapter.md` — completed dependency

### Documentation

- `docs/ARCHITECTURE.md` — needs a sibling subsection under "hooks/adapters/" describing the OpenCode adapter, mirroring the Claude Code adapter description

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md` — 3 coupling points: (1) chmod list at ~line 807 for adapter scripts; (2) manual test snippet at ~lines 1006–1009 showing `python -m little_loops.hooks pre_compact` (add `LL_HOOK_HOST=opencode` variant if Option A); (3) lock timeout note at ~line 1040 that names `claude-code/precompact.sh` (add OpenCode parallel). Low priority but required for multi-host doc completeness.
- `docs/reference/API.md` — `## Module Overview` table has no row for `little_loops.hooks`; if Option A adds `--host` flag, `main_hooks()` CLI signature is undocumented until FEAT-1453. Not blocking for FEAT-1451 (assigned to FEAT-1453).

## Proposed Solution

Build a thin TypeScript plugin under `hooks/adapters/opencode/` that mirrors the shape of `hooks/adapters/claude-code/session-start.sh` and `precompact.sh`: spawn `python -m little_loops.hooks <intent>`, pipe the host's event payload as JSON to stdin, surface stdout/stderr/exit-code back to OpenCode. No logic lives in TypeScript — the adapter is purely a transport.

### Plugin Skeleton (mirrors FEAT-961 design, slimmed to 2 intents)

```typescript
// hooks/adapters/opencode/index.ts
import type { Plugin } from "@opencode-ai/plugin";

const spawnIntent = async (
  intent: "session_start" | "pre_compact",
  payload: unknown,
  cwd: string,
): Promise<{ stdout: string; stderr: string; exitCode: number }> => {
  const proc = Bun.spawn(["python", "-m", "little_loops.hooks", intent], {
    cwd,
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
  });
  proc.stdin.write(JSON.stringify(payload ?? {}));
  proc.stdin.end();
  const [stdout, stderr] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
  ]);
  const exitCode = await proc.exited;
  return { stdout, stderr, exitCode };
};

const plugin: Plugin = async (ctx) => ({
  "session.created": async (input) => {
    const { stdout, stderr, exitCode } = await spawnIntent("session_start", input, ctx.cwd);
    if (stderr) console.error(stderr);
    if (exitCode === 2) throw new Error(stderr || "session_start blocked");
    return stdout ? JSON.parse(stdout) : undefined;
  },
  "session.compacted": async (input) => {
    const { stderr, exitCode } = await spawnIntent("pre_compact", input, ctx.cwd);
    if (stderr) console.error(stderr);
    // exitCode === 2 is the success path for pre_compact (feedback-only)
  },
});

export default plugin;
```

### Open Decision — Host Identifier Passthrough

`main_hooks()` in `scripts/little_loops/hooks/__init__.py:86-91` constructs the `LLHookEvent` with `host="claude-code"` hardcoded. No CLI/env mechanism exists today to override it. Two options for handling this in FEAT-1451's scope:

**Option A — Pass-through host identifier (correctness-first)**
> **Selected:** Option A — Pass-through host identifier — `LL_HOOK_HOST` env var reuses the established `LL_*` override convention (~2 lines in `main_hooks`) and the test pattern exists verbatim in `test_hooks_integration.py`; deferring contradicts both `LLHookEvent.host`'s docstring and the schema enum already enforced by a learning test.

Extend `main_hooks` to accept the host via `--host opencode` CLI flag or `LL_HOOK_HOST=opencode` environment variable. The OpenCode adapter then sets it. Pros: `LLHookEvent.host` reflects reality, enabling host-specific branching in future handlers (already foreshadowed in `LLHookEvent` docstring). Cons: small scope creep into `main_hooks`; needs a tiny test in `test_hook_intents.py` covering the override.

**Option B — Defer host-aware branching (minimal-change MVP)**

Leave `host="claude-code"` hardcoded; document it as a known limitation. The current `session_start.handle` and `pre_compact.handle` do not branch on `event.host`, so the discrepancy is observable only in logs. Pros: zero change to `main_hooks` and existing tests. Cons: a future hot-path intent that needs to branch on host will require Option A retroactively; logs/observability for OpenCode appear under the "claude-code" host bucket.

**Recommendation**: Option A. The added surface area is ~5 lines in `main_hooks` and a single new test; deferring it makes a downstream issue inherit a cross-cutting refactor.

### Latency Measurement (deliverable, not implementation)

Hot-path intents are out of scope for this issue. Per FEAT-1116 Decision 3, before any future issue adds `tool.execute.before/after` handlers, this issue must land **a documented latency target and measurement method**, e.g. a section in `hooks/adapters/opencode/README.md` defining:

- Target: end-to-end `Bun.spawn → python interpreter cold start → handler → exit` should remain ≤ N ms (suggested initial target: 200 ms p95 on dev hardware, refined by measurement)
- Method: a benchmark script under `scripts/tests/bench_opencode_adapter.py` that times 100 sequential invocations of each intent
- Decision rule: if measured p95 > target by 2x, a follow-up issue must propose a persistent sidecar before hot-path intents are added

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-11.

**Selected**: Option A — Pass-through host identifier (correctness-first)

**Reasoning**: The `LL_HOOK_HOST` env var path for Option A reuses the established `LL_*` override convention (`LL_HANDOFF_THRESHOLD`, `LL_CONTEXT_LIMIT`) and requires only `os.environ.get("LL_HOOK_HOST", "claude-code")` in `main_hooks()` — approximately 2 lines and one new test. The `os.environ.copy()` + `env=env` subprocess test pattern already exists verbatim at 6 call sites in `test_hooks_integration.py`. Deferring (Option B) would leave `config-schema.json`'s `host` enum and `LLHookEvent.host`'s "adapters set this" docstring as documented-but-inert design intent, and would force a retroactive cross-cutting refactor once any hot-path intent needs host-specific branching.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 2/3 | 3/3 | 3/3 | 3/3 | 11/12 |
| Option B | 1/3 | 3/3 | 3/3 | 3/3 | 10/12 |

**Key evidence**:
- **Option A**: `os.environ.get("LL_HOOK_HOST", "claude-code")` in `__init__.py:86` is the only change site; test pattern is verbatim at `test_hooks_integration.py:247-256`; `LLHookEvent.host` docstring and `config-schema.json` both already enumerate `"opencode"` as a first-class value
- **Option B**: Zero code changes, but `config-schema.json:1097-1108` (learning-test-enforced) and `types.py:25-27` ("adapters set this") both document intent that Option B silently contradicts; creates a known-limitation with no code-level marker

## Implementation Steps

1. **Scaffold the adapter directory**: create `hooks/adapters/opencode/{index.ts, package.json, tsconfig.json, README.md}`. Pin `@opencode-ai/plugin@1.2.27` (the SDK version validated in FEAT-961) and set `"type": "module"`.
2. **Implement the spawn-and-translate plugin** in `index.ts`, matching the skeleton above. Use Bun's `Bun.spawn` (confirmed available per FEAT-961 runtime notes — OpenCode runs on Bun).
3. **(If Option A chosen)** Extend `main_hooks` in `scripts/little_loops/hooks/__init__.py:86-91` to accept `--host` via `sys.argv` or `LL_HOOK_HOST` env, defaulting to `claude-code`. Add a corresponding test in `scripts/tests/test_hook_intents.py` in `TestHooksMainModule` modeled after the existing `test_dispatch_pre_compact_happy_path` pattern.
4. **Write the adapter integration test** at `scripts/tests/test_opencode_adapter.py`: invoke `bun hooks/adapters/opencode/index.ts` with crafted event JSON on stdin (or import the module under Bun's test runner if available) and assert against the Python dispatcher's observable behavior — config JSON on stdout for `session.created`, state file `.ll/ll-precompact-state.json` written for `session.compacted`. Mirror the `os.chdir(tmp_path)` + `subprocess.run(..., capture_output=True, text=True, timeout=5)` pattern from `scripts/tests/test_hooks_integration.py` in `TestSessionStartValidation`.
5. **Document the latency target** in `hooks/adapters/opencode/README.md` per the "Latency Measurement" section above; do NOT add hot-path handlers yet.
6. **Update `docs/ARCHITECTURE.md`** with an `adapters/opencode/` subsection mirroring the existing `adapters/claude-code/` description.
7. **Run** `python -m pytest scripts/tests/ -v`, `ruff check scripts/`, `python -m mypy scripts/little_loops/` to verify Python-side changes; if Bun is available locally, `bun install` under `hooks/adapters/opencode/` and a smoke `bun run index.ts` driven by a saved fixture JSON.
8. **Mark the FEAT-961 coordination criterion satisfied** in the Acceptance Criteria below (FEAT-961 is already in `completed/` as Superseded; no parallel reimplementation exists to coordinate with).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Handle `--host` flag without shifting positional args** — if Option A is chosen, implement using `argparse` (or explicit flag scanning before positional extraction); the current `intent = sys.argv[1]` in `main_hooks()` breaks if `--host opencode` precedes the intent positional arg. Existing `TestHooksMainModule` tests pass `"pre_compact"` / `"session_start"` as `sys.argv[1]` and will fail if positional indexing shifts.
10. **Use correct pre_compact test file name** — the file on disk is `scripts/tests/test_pre_compact.py` (not `test_hook_pre_compact.py`); when implementing step 3 (Option A `--host` test), model the new `TestHooksMainModule` test after `TestHandleHappyPath` in `test_pre_compact.py`.
11. **Python-only adapter test** — no Bun/TS test runner exists in this project; `scripts/tests/test_opencode_adapter.py` must invoke the adapter via `subprocess.run(["bun", "hooks/adapters/opencode/index.ts"], ...)` from Python (mark test with `pytest.mark.skipif(shutil.which("bun") is None, ...)`).
12. **Update `docs/development/TROUBLESHOOTING.md`** — add OpenCode adapter paths alongside Claude Code adapter references at the 3 coupling points (chmod, manual test snippet, lock timeout note). Low priority, deferred to after the adapter is functional.

## Test Strategy

- **Adapter→dispatcher round-trip (integration)**: spawn the TS adapter with a fixture event JSON on stdin in a `tmp_path` cwd; assert that `.ll/ll-precompact-state.json` is created (pre_compact) or that stdout returns valid config JSON (session_start). Pattern: `scripts/tests/test_hooks_integration.py` in `TestSessionStartValidation`.
- **Dispatcher CLI contract (unit)**: if Option A is chosen, add a test in `scripts/tests/test_hook_intents.py` in `TestHooksMainModule` that asserts `--host opencode` propagates to `LLHookEvent.host` (verified by a handler stub or by capturing the constructed event).
- **No new tests are needed for `session_start.handle` or `pre_compact.handle` themselves** — they are covered by `test_hook_session_start.py` and `test_hook_pre_compact.py` and the adapter does not change their behavior.

## Acceptance Criteria

- OpenCode adapter exists under `hooks/adapters/opencode/` with `index.ts`, `package.json`, `tsconfig.json`, and `README.md`
- Adapter invokes `python -m little_loops.hooks session_start` (on OpenCode's `session.created`) and `python -m little_loops.hooks pre_compact` (on OpenCode's `session.compacted`), piping the host event as JSON to stdin and propagating exit code + stdout + stderr
- Subprocess cwd is set to the project root so `.ll/ll-config.json` resolution and `.ll/ll-precompact-state.json` writes by the Python handlers land correctly
- Adapter integration test in `scripts/tests/test_opencode_adapter.py` (or equivalent under Bun) round-trips a fixture event and asserts the observable Python-side effect (config JSON on stdout for `session_start`, state file written for `pre_compact`)
- Host identifier decision (Option A or B in Proposed Solution) is resolved and implemented; if Option A, `LLHookEvent.host == "opencode"` is observable in tests
- FEAT-961 coordination: confirmed no parallel reimplementation exists (FEAT-961 is Closed-Superseded in `completed/`); criterion considered satisfied
- Latency measurement deliverable documented in `hooks/adapters/opencode/README.md` before any hot-path intent (PreToolUse/PostToolUse) is added in a follow-up
- `docs/ARCHITECTURE.md` updated with the `adapters/opencode/` subsection

## Resolution

Implemented the OpenCode TypeScript plugin adapter at `hooks/adapters/opencode/` as a thin shell-out to the host-agnostic Python dispatcher (`python -m little_loops.hooks <intent>`), per FEAT-1116 Decision 3. The adapter handles `session.created` → `session_start` and `session.compacted` → `pre_compact`; hot-path events remain deferred until latency is measured.

**Option A (host pass-through) implemented**: `main_hooks` in `scripts/little_loops/hooks/__init__.py` now reads `LL_HOOK_HOST` (defaults to `"claude-code"`), and the OpenCode adapter sets it to `"opencode"` on the subprocess env. Two new tests in `test_hook_intents.py::TestHooksMainModule` (`test_ll_hook_host_env_var_propagates`, `test_ll_hook_host_defaults_to_claude_code`) verify both branches via an in-process dispatch-table stub.

**Files created**:
- `hooks/adapters/opencode/index.ts` — Bun-runtime plugin, pins `@opencode-ai/plugin@1.2.27` via package.json (type-only import; runtime works without `bun install`)
- `hooks/adapters/opencode/package.json`, `tsconfig.json`, `README.md` — including the latency-target deliverable (≤200ms p95, 2× margin triggers persistent-sidecar follow-up before hot-path intents)
- `scripts/tests/test_opencode_adapter.py` — 4 integration tests via `bun run`; auto-skip when Bun is absent. Covers: file presence, `session.compacted` writes `.ll/ll-precompact-state.json`, `session.created` runs `session_start`, and an env-passthrough sentinel proving `LL_HOOK_HOST=opencode` reaches the Python process.

**Files modified**:
- `scripts/little_loops/hooks/__init__.py` — one-line change: `host=os.environ.get("LL_HOOK_HOST", "claude-code")`
- `docs/ARCHITECTURE.md` — directory tree updated with `adapters/opencode/` sibling entry
- `docs/development/TROUBLESHOOTING.md` — chmod note clarifying TS adapter is loaded not chmod'd; manual-test snippet shows `LL_HOOK_HOST=opencode` variant; lock-timeout reference now names both adapters

**Verification**: 122 hook-related tests pass (`test_hook_intents.py`, `test_opencode_adapter.py`, `test_hooks_integration.py`, `test_pre_compact.py`, `test_hook_session_start.py`); `ruff check` clean; `mypy` clean on `scripts/little_loops/hooks/`. The 7 pre-existing failures in `test_generate_schemas.py` and `test_update_skill.py` are unrelated to this issue (confirmed by stash + re-run on main).

**FEAT-961 coordination**: confirmed satisfied — FEAT-961 is closed-superseded in `completed/` with no merged code under `opencode-plugin/`. No coordination action needed.

## Session Log
- `/ll:manage-issue` - 2026-05-12T03:01:19Z - `0010190c-509e-453e-bb85-c00575d1e590.jsonl`
- `/ll:ready-issue` - 2026-05-12T02:53:38 - `32543bcd-a253-4ee9-87ee-301403e10e71.jsonl`
- `/ll:confidence-check` - 2026-05-11T13:00:00Z - `b5b2f42b-04f0-4341-9723-efefed356cb7.jsonl`
- `/ll:decide-issue` - 2026-05-12T02:50:07 - `98d73f4b-834a-4108-9319-530bb8656795.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `7b61d370-da92-44ed-abfb-762382787185.jsonl`
- `/ll:wire-issue` - 2026-05-12T02:43:59 - `8a767877-9515-44f2-9f9a-b6c52f44c6fd.jsonl`
- `/ll:refine-issue` - 2026-05-12T02:37:22 - `55ea351a-2d37-481a-9c15-9798006684c9.jsonl`
- `/ll:issue-size-review` - 2026-05-12T00:20:02 - `5cb0dc9a-fd6f-4945-97b0-ad6acec56482.jsonl`
