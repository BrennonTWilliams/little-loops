---
id: FEAT-1478
title: Pi Adapter — TypeScript Adapter and Integration Test
type: FEAT
priority: P5
status: open
parent: EPIC-1622
---

# FEAT-1478: Pi Adapter — TypeScript Adapter and Integration Test

## Summary

Create the TypeScript hook adapter under `hooks/adapters/pi/` (index.ts, package.json, README.md) and write `test_pi_adapter.py` to verify `LL_HOOK_HOST=pi` propagation and event dispatch. This is a pure creation task — no existing Python files are modified.

## Parent Issue

Decomposed from FEAT-1474: Pi Adapter Core — TypeScript Adapter, Config Candidate, Schema, and Tests

## Acceptance Criteria

- `hooks/adapters/pi/index.ts` wires `session_start` (filtered by `reason === "startup"`) and `session_before_compact` to `python -m little_loops.hooks` via `node:child_process.spawn()` with `LL_HOOK_HOST=pi`
- `hooks/adapters/pi/package.json` lists `@earendil-works/pi-coding-agent` as a dev dependency with `"type": "module"`
- `hooks/adapters/pi/README.md` has event-mapping table (session_start → session_start intent, session_before_compact → pre_compact intent) and install instructions
- `scripts/tests/test_pi_adapter.py` passes: Node.js-gated; verifies `LL_HOOK_HOST=pi` propagation with sentinel-file pattern; verifies `session_start`/`session_before_compact` dispatch

## Proposed Solution

### Step 1: Verify Pi SDK Event Names

Before writing the adapter, confirm `@earendil-works/pi-coding-agent` event names (`session_start`, `session_before_compact`) and whether `devDependencies` vs `dependencies` is correct in `package.json` — the AC cites research but these should be verified against the SDK docs or `node_modules` if available.

### Step 2: Create TypeScript Adapter

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

### Step 3: Create package.json

```json
{
  "type": "module",
  "devDependencies": {
    "@earendil-works/pi-coding-agent": "*"
  }
}
```

### Step 4: Create README.md

Include: event→intent mapping table, subprocess contract (stdin JSON payload, stdout JSON response, exit 2 = block), no-trust-dialog note, install steps (copy or symlink to `.pi/extensions/`).

Distinguish from similar adapters:
- Unlike Codex: no `hooks.json` — Pi uses `pi.on()` TypeScript registration
- Unlike OpenCode: uses Node.js (`node:child_process`) not Bun (`Bun.spawn()`)

### Step 5: Write Integration Test

`scripts/tests/test_pi_adapter.py` — mirror `test_opencode_adapter.py:TestOpenCodeAdapterIntegration`:
- Skip guard: `shutil.which("node")` (not `bun`)
- Sentinel-file pattern: write a sentinel file from the Python hook handler, verify it exists after running the adapter via `node driver.mjs`
- Verify `LL_HOOK_HOST=pi` is propagated to the Python subprocess
- Verify `session_start` dispatch (with `reason === "startup"` filter)
- Verify `session_before_compact` dispatch

Template reference: `test_opencode_adapter.py:TestOpenCodeAdapterIntegration.test_adapter_sets_ll_hook_host_opencode` — Pi swaps Bun for Node and `"session.created"` for `"session_start"`.

## Files to Create

- `hooks/adapters/pi/index.ts`
- `hooks/adapters/pi/package.json`
- `hooks/adapters/pi/README.md`
- `scripts/tests/test_pi_adapter.py`

## Notes

- No `hooks.json` is needed — Pi uses TypeScript SDK `pi.on()` registration, not a JSON manifest like Codex.
- Pi uses Node.js (not Bun) — use `node:child_process.spawn()` not `Bun.spawn()`.
- No trust dialog in Pi — extensions auto-load with full permissions.
- This child is parallel with FEAT-1477 (Python backend) — neither depends on the other.

## Impact

- **Priority**: P5
- **Effort**: Small-Medium
- **Risk**: Low — pure creation, no modifications to existing files

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-28): The README.md event-mapping table is a **baseline** reflecting only the 2 Pi SDK events known at implementation time (`session_start`, `session_before_compact`). A full parity matrix documenting 6+ unsupported hook intents (PreToolUse, PostToolUse, UserPromptSubmit, Stop, SessionEnd, post_compact) will be added by FEAT-1715, which layers on top of this baseline. The adapter ships knowing its own limits.

**Note** (added by `/ll:audit-issue-conflicts`): `hooks/adapters/pi/README.md` (created by this issue) covers adapter-local event mapping and install instructions. `docs/reference/HOST_COMPATIBILITY.md` (updated by FEAT-1476) is the authoritative host-level parity table. The README should cross-reference HOST_COMPATIBILITY.md as the canonical source for the full parity matrix — it is NOT the authoritative doc itself. Doc file edits to HOST_COMPATIBILITY.md are FEAT-1476's scope; the README is this issue's scope.

## Status

**Open** | Created: 2026-05-15 | Priority: P5


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): The `test_pi_adapter.py` test suite in this issue verifies **TypeScript-layer** behavior: that the `index.ts` adapter correctly sets `LL_HOOK_HOST=pi` in the environment before spawning Python. FEAT-1480 separately tests **Python-side routing**: that the Python intent dispatcher reads `LL_HOOK_HOST=pi` and routes to the correct handler. Assertion ownership: this issue owns "subprocess env contains `LL_HOOK_HOST=pi`"; FEAT-1480 owns "Python routing fires the correct intent given `LL_HOOK_HOST=pi` already set." Do not duplicate Python routing assertions in `test_pi_adapter.py`.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:02 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:54 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:48:17 - `6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:10 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:13 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:44 - `2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:issue-size-review` - 2026-05-15T20:10:00 - `f91d7b90-f81d-4224-83bd-e6b959badcd1.jsonl`
