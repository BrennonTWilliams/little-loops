---
id: FEAT-1474
type: FEAT
priority: P5
status: done
parent: FEAT-992
size: Very Large
decision_needed: false
confidence_score: 98
outcome_confidence: 70
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
completed_at: 2026-05-15T00:00:00Z
---

# FEAT-1474: Pi Adapter Core — TypeScript Adapter, Config Candidate, Schema, and Tests

## Summary

Implement the core Pi Coding Agent host adapter: create the TypeScript hook adapter under `hooks/adapters/pi/`, add the Pi config candidate to `config/core.py`, update `config-schema.json`, and write all associated tests. This is the primary deliverable for Pi plugin compatibility.

## Parent Issue

Decomposed from FEAT-992: Add Pi Coding Agent Plugin Compatibility

## Acceptance Criteria

- `hooks/adapters/pi/index.ts` exists and wires `session_start` (filtered by `reason === "startup"`) and `session_before_compact` to `python -m little_loops.hooks` via `node:child_process.spawn()` with `LL_HOOK_HOST=pi`
- `hooks/adapters/pi/package.json` lists `@earendil-works/pi-coding-agent` as a dev dependency with `"type": "module"`
- `hooks/adapters/pi/README.md` has event-mapping table and install instructions
- `scripts/little_loops/config/core.py` has `PI_CONFIG_DIR = ".pi"` constant and an `elif host == "pi" or state_dir == PI_CONFIG_DIR:` branch in `_config_candidates()`
- `config-schema.json` includes `"pi"` in `hooks.properties.host.enum`
- All tests pass: `python -m pytest scripts/tests/ -k pi`
- Existing Claude Code, OpenCode, and Codex CLI behavior is unchanged (no regressions)

## Proposed Solution

### Step 1: Confirm FEAT-957 Complete

Verify `hooks/adapters/codex/` exists and `_config_candidates()` in `config/core.py` has the `codex` branch — use these as templates. (FEAT-957 was marked complete per git log `2b4b3962`.)

### Step 2: Add Pi Config Candidate

In `scripts/little_loops/config/core.py` (~line 36), add:
```python
PI_CONFIG_DIR = ".pi"
```

In `_config_candidates()` (~lines 84-88), add branch mirroring the codex branch at line 85:
```python
elif host == "pi" or state_dir == PI_CONFIG_DIR:
    candidates.append(project_root / PI_CONFIG_DIR / CONFIG_FILENAME)
```

### Step 3: Create TypeScript Adapter

```typescript
// hooks/adapters/pi/index.ts — thin transport, no logic
import { spawn } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const spawnIntent = (intent: string, payload: unknown, cwd: string) =>
  new Promise<{ stdout: string; stderr: string; exitCode: number }>((resolve) => {
    const proc = spawn("python", ["-m", "little_loops.hooks", intent], {
      cwd,
      env: { ...process.env, LL_HOOK_HOST: "pi" },
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "", stderr = "";
    proc.stdout.on("data", (d: Buffer) => { stdout += d.toString(); });
    proc.stderr.on("data", (d: Buffer) => { stderr += d.toString(); });
    proc.stdin.write(JSON.stringify(payload ?? {}));
    proc.stdin.end();
    proc.on("close", (exitCode) => resolve({ stdout, stderr, exitCode: exitCode ?? 1 }));
  });

export default function (pi: ExtensionAPI) {
  pi.on("session_start", async (event, ctx) => {
    if (event.reason !== "startup") return;
    const { stdout, stderr, exitCode } = await spawnIntent("session_start", event, ctx.cwd);
    if (stderr) console.error(stderr);
    if (exitCode === 2) throw new Error(stderr || "session_start blocked");
    return stdout ? JSON.parse(stdout) : undefined;
  });

  pi.on("session_before_compact", async (event, ctx) => {
    const { stderr, exitCode } = await spawnIntent("pre_compact", event, ctx.cwd);
    if (stderr) console.error(stderr);
    if (exitCode !== 0 && exitCode !== 2) throw new Error(stderr || `pre_compact failed (exit ${exitCode})`);
  });
}
```

`hooks/adapters/pi/package.json`:
```json
{
  "type": "module",
  "devDependencies": {
    "@earendil-works/pi-coding-agent": "*"
  }
}
```

`hooks/adapters/pi/README.md`: event→intent mapping table, subprocess contract, no-trust-dialog note, install steps.

### Step 4: Update Config Schema

In `config-schema.json`, add `"pi"` to `hooks.properties.host.enum`.

### Step 5: Write Tests (TDD — wiring included per tdd_mode=true)

- `scripts/tests/test_pi_adapter.py` (new) — mirror `test_codex_adapter.py` and `test_opencode_adapter.py`; skip if Node.js absent; verify `LL_HOOK_HOST=pi` propagation with sentinel-file pattern; verify `session_start`/`session_before_compact` dispatch
- `scripts/tests/test_config.py:TestResolveConfigPath` — add Pi probe-order tests mirroring `test_codex_path_takes_precedence_when_host_codex` with `LL_HOOK_HOST=pi` and `.pi/ll-config.json`
- `scripts/tests/test_config_schema.py:test_hooks_in_schema` — update exact-equality assertion to include `"pi"` in `hooks.host.enum`
- `scripts/tests/test_hook_intents.py:TestHooksMainModule` — add `test_ll_hook_host_env_var_propagates_pi` mirroring the codex variant
- `scripts/tests/test_host_runner.py:TestPiRunner` — replace the 4 `pytest.raises(HostNotConfigured, match="FEAT-992")` assertions with argv-snapshot tests following `TestCodexRunner` as template; add `test_capabilities_*` for Pi's `HostCapabilities`
- `scripts/tests/test_hook_session_start.py` — add Pi parallel of `test_falls_back_to_codex_dir_config`: set `LL_HOOK_HOST=pi`, create `.pi/ll-config.json`, assert it is loaded through the session-start handler

### Step 6: Verify Acceptance Criteria

Run `python -m pytest scripts/tests/ -k pi` and verify all pass.

### Step 7: Update Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` — add Pi column to Hook intents, Config probe, Adapter locations, and Installation tables; update FEAT-992 tracking bullet from "deferred" to resolved
- `docs/reference/API.md` — update `PiRunner` row (remove "stub / raises HostNotConfigured" and FEAT-992 reference); remove PiRunner from "stub runners" in the `HostNotConfigured` description
- `docs/ARCHITECTURE.md` — update `PiRunner` row in "Host Runner Layer" table from "stub / research deferred" to active
- `docs/development/TROUBLESHOOTING.md` — remove `PiRunner` from stub runner list in `HostNotConfigured` troubleshooting entry
- `scripts/little_loops/config/core.py` — also update `OrchestrationConfig` docstring: change `"pi" (reserved for FEAT-992)` to reflect that `"pi"` is now active in both enum locations

## Files to Create

- `hooks/adapters/pi/index.ts`
- `hooks/adapters/pi/package.json`
- `hooks/adapters/pi/README.md`
- `scripts/tests/test_pi_adapter.py`

## Files to Modify

- `scripts/little_loops/config/core.py` — `PI_CONFIG_DIR` constant + `_config_candidates()` branch + `OrchestrationConfig` docstring (remove FEAT-992 reservation note)
- `scripts/little_loops/host_runner.py` — wire `PiRunner.build_*` methods (currently all raise `HostNotConfigured`); update capabilities if needed
- `config-schema.json` — add `"pi"` to `hooks.properties.host.enum`
- `scripts/tests/test_config.py` — Pi probe-order test cases
- `scripts/tests/test_config_schema.py` — update exact-equality assertion
- `scripts/tests/test_hook_intents.py` — `LL_HOOK_HOST=pi` propagation test
- `scripts/tests/test_host_runner.py` — replace stub raises with argv-snapshot tests; update `test_pirunner_probe_returns_stub_not_raise`
- `scripts/tests/test_hook_session_start.py` — Pi session-start config-load test
- `docs/reference/HOST_COMPATIBILITY.md` — add Pi column to all host-comparison tables; update FEAT-992 tracking bullet
- `docs/reference/API.md` — update PiRunner runner table row; remove PiRunner from HostNotConfigured stub list
- `docs/ARCHITECTURE.md` — update PiRunner row in Host Runner Layer table
- `docs/development/TROUBLESHOOTING.md` — remove PiRunner from HostNotConfigured stub list

## Integration Map

### Files to Create
- `hooks/adapters/pi/index.ts` — TypeScript adapter using `node:child_process.spawn()` with `LL_HOOK_HOST=pi`; no `hooks.json` needed (Pi uses TypeScript SDK `pi.on()` registration, not a JSON manifest like Codex)
- `hooks/adapters/pi/package.json` — `@earendil-works/pi-coding-agent` as dependency, `"type": "module"`, Node engine (not Bun)
- `hooks/adapters/pi/README.md` — event→intent mapping table; distinguish from Codex (no `hooks.json`) and OpenCode (Bun→Node difference)
- `scripts/tests/test_pi_adapter.py` — Node.js-gated; skip guard uses `shutil.which("node")` (not `bun`); sentinel-file pattern mirrors `test_opencode_adapter.py:TestOpenCodeAdapterIntegration.test_adapter_sets_ll_hook_host_opencode` but invokes via `node driver.mjs` instead of `bun run driver.ts`

### Files to Modify (with exact anchors)
- `scripts/little_loops/config/core.py:34–36` — add `PI_CONFIG_DIR = ".pi"` after `CODEX_CONFIG_DIR = ".codex"` (line 36)
- `scripts/little_loops/config/core.py:84–89` — `_config_candidates()`: add `elif host == "pi" or state_dir == PI_CONFIG_DIR:` branch; the existing codex branch at lines 85–86 is the exact template
- `config-schema.json:1102–1104` — add `"pi"` to `hooks.properties.host.enum`; note `orchestration.host_cli` at line 1113 already has `"pi"` (the two enums are currently inconsistent)
- `scripts/tests/test_config.py:1040` — add Pi probe-order tests after `TestResolveConfigPath.test_codex_path_takes_precedence_when_host_codex`
- `scripts/tests/test_config_schema.py:155` — update exact-equality: `host["enum"] == ["claude-code", "opencode", "codex", "pi"]`
- `scripts/tests/test_hook_intents.py:359` — add Pi parallel after `TestHooksMainModule.test_ll_hook_host_env_var_propagates_codex`
- `scripts/tests/test_host_runner.py:337–392` — `TestPiRunner`: replace 4 `HostNotConfigured(match="FEAT-992")` raise assertions with argv-snapshot tests; **also update** `test_pirunner_probe_returns_stub_not_raise` (line 357) which currently verifies that the probed `PiRunner` raises FEAT-992 — this test must be updated once `build_*` is wired
- `scripts/tests/test_hook_session_start.py:64` — add Pi parallel of `TestSessionStartConfigLoad.test_falls_back_to_codex_dir_config`

### Missing from Files to Modify (discovered via research)
- `scripts/little_loops/host_runner.py:478–532` — **`PiRunner` class currently raises `HostNotConfigured("Pi orchestration not yet wired — see FEAT-992...")` in ALL four `build_*` methods.** The AC says to replace the 4 test raises with argv-snapshot tests, which requires wiring `PiRunner.build_*` to actually construct commands. `host_runner.py` must be added to the Files to Modify list. Current capabilities: `HostCapabilities()` with all four flags `False`; `detect()` returns `shutil.which("pi") is not None`. Pi is already in `_HOST_RUNNER_REGISTRY` and `_PROBE_ORDER` (unlike Codex/OpenCode which are gated from auto-probe).

### Test Templates
- `scripts/tests/test_opencode_adapter.py:TestOpenCodeAdapterIntegration` — primary template for `test_pi_adapter.py` (both TypeScript; Pi swaps Bun for Node and `"session.created"` for `"session_start"`)
- `scripts/tests/test_codex_adapter.py:TestCodexAdapterIntegration` — sentinel-file pattern reference (lines 27–34 for skip guard + constants)
- `scripts/tests/test_config.py:1040` — `test_codex_path_takes_precedence_when_host_codex` in `TestResolveConfigPath`
- `scripts/tests/test_config_schema.py:155` — exact assertion line to update
- `scripts/tests/test_hook_intents.py:359` — `test_ll_hook_host_env_var_propagates_codex` in `TestHooksMainModule`
- `scripts/tests/test_host_runner.py:165` — `TestCodexRunner`; `test_codex_runner_flag_translation` at line 194 is the canonical argv-snapshot form
- `scripts/tests/test_hook_session_start.py:64` — `test_falls_back_to_codex_dir_config` in `TestSessionStartConfigLoad`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/action.py` — calls `resolve_host()` in `ll-action` CLI; transparent beneficiary of PiRunner wiring, no code change needed [Agent 1 finding]
- `scripts/little_loops/subprocess_utils.py` — calls `resolve_host()` for subprocess invocation; transparent beneficiary [Agent 1 finding]
- `scripts/little_loops/fsm/handoff_handler.py` — calls `resolve_host()` to spawn continuation sessions [Agent 1 finding]
- `scripts/little_loops/parallel/worker_pool.py` — calls `resolve_host()` within worker pool execution [Agent 1 finding]
- `scripts/little_loops/hooks/session_start.py` — calls `resolve_config_path()` which uses `_config_candidates()`; will automatically probe `.pi/ll-config.json` once the new branch is added [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md` — major update: add Pi column to Hook intents, Config probe, Adapter locations, and Installation tables; update FEAT-992 tracking bullet from "deferred" to resolved [Agent 2 finding]
- `docs/reference/API.md` — update `PiRunner` runner table row (remove "stub" status and FEAT-992 reference); remove `PiRunner` from "stub runners" sentence in `HostNotConfigured` description [Agent 2 finding]
- `docs/ARCHITECTURE.md` — update `PiRunner` row in "Host Runner Layer" table from "Stub for the Raspberry Pi host (FEAT-992 research deferred)" to active [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — remove `PiRunner` from stub runner list in `HostNotConfigured` troubleshooting entry [Agent 2 finding]

## Similar Patterns

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `hooks/adapters/opencode/index.ts` — closest TypeScript analog; uses `Bun.spawn()` (replace with `node:child_process.spawn()`), `@opencode-ai/plugin`, event names `"session.created"`/`"session.compacted"` (Pi uses `"session_start"`/`"session_before_compact"` per SDK)
- `hooks/adapters/codex/` — Bash adapter (not TypeScript); event-filter pattern via `"matcher": "startup"` in `hooks.json`; **Pi does NOT use a `hooks.json`** — Pi's SDK uses `pi.on()` registration
- `scripts/little_loops/config/core.py:34–36` + `85–86` — exact 2-line codex constant + branch to copy for Pi
- `hooks/adapters/opencode/package.json` — has `name`, `version`, `private`, `type`, `main`, `dependencies` (not `devDependencies`); Pi's `package.json` uses `devDependencies` per AC — verify with Pi SDK docs

## Impact

- **Priority**: P5
- **Effort**: Medium
- **Risk**: Low — additive; no changes to core logic

## Status

**Open** | Created: 2026-05-15 | Priority: P5

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-15_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- Broad change surface (16 files; Breadth 16+ → 0/12) — per-site depth is Local/Mechanical; risk is coordination overhead, not implementation complexity. Follow templates closely to keep this routine.
- Pi SDK `@earendil-works/pi-coding-agent` event names (`session_start`, `session_before_compact`) and `package.json` field convention (`devDependencies` vs `dependencies`) are cited from research but not verified against official SDK docs — resolve this at the start of Step 3 before writing the adapter.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-15
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- FEAT-1477: Pi Adapter — Python Backend: Config, Host Runner, Schema, and Tests
- FEAT-1478: Pi Adapter — TypeScript Adapter and Integration Test

Note: Step 7 (documentation) is already covered by sibling issue FEAT-1476 (Pi Adapter Documentation), intentionally out of scope for both children.

## Session Log
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/053074c0-5fd9-49d9-98ac-aa095139a02e.jsonl`
- `/ll:wire-issue` - 2026-05-15T19:42:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/61670883-6417-4cac-ab8f-ed56648a4270.jsonl`
- `/ll:refine-issue` - 2026-05-15T19:36:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3d981b6-3175-434b-95bb-c4779b895642.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59179ce1-13d5-40c7-bdca-8b3c6117c43e.jsonl`
- `/ll:issue-size-review` - 2026-05-15T20:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f91d7b90-f81d-4224-83bd-e6b959badcd1.jsonl`
