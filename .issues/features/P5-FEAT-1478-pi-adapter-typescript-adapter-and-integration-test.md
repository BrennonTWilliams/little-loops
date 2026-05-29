---
id: FEAT-1478
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

## Status

**Open** | Created: 2026-05-15 | Priority: P5

## Session Log
- `/ll:verify-issues` - 2026-05-23T00:35:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:issue-size-review` - 2026-05-15T20:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f91d7b90-f81d-4224-83bd-e6b959badcd1.jsonl`
