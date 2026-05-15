---
id: FEAT-992
type: FEAT
priority: P5
status: done
discovered_date: 2026-04-08
discovered_by: capture-issue
blocked_by:
- FEAT-957
confidence_score: 90
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
decision_needed: false
missing_artifacts: true
size: Very Large
---

# FEAT-992: Add Pi Coding Agent Plugin Compatibility

## Summary

Pi Coding Agent (https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent) is a terminal AI coding agent. This issue tracks adding Pi plugin support so that ll's full feature set — commands, skills, and session hooks — works in Pi projects, following the same pattern established by FEAT-769 (OpenCode) and FEAT-957 (Codex CLI).

## Current Behavior

little-loops has no Pi Coding Agent plugin layer. Commands and skills may work via any compatible path fallback Pi supports, but session hooks (context monitoring, duplicate ID checks, config loading) do not fire because there is no Pi plugin wiring them to lifecycle events.

## Expected Behavior

A user running Pi Coding Agent can install little-loops and get all commands, skills, and session hooks working at parity with the Claude Code experience.

## Acceptance Criteria

- All `/ll:*` slash commands work in a Pi project without modification
- All skills work in a Pi project without modification
- Session lifecycle hooks fire via a Pi plugin (config loading, duplicate ID check, context monitoring, compact/cleanup)
- Config resolves from Pi's config directory when present, falls back to `.claude/ll-config.json`
- `ll:init --pi` detects Pi Coding Agent presence and offers to register the plugin
- Existing Claude Code, OpenCode, and Codex CLI behavior is unchanged (no regressions)

## Motivation

Pi Coding Agent expands the AI coding tool ecosystem beyond Claude Code. Supporting it follows the same extensibility philosophy as FEAT-957 and FEAT-961: the content layer (commands, skills) is already platform-agnostic — only the hook execution layer needs a plugin bridge. Capturing Pi now ensures the compatibility track stays ahead of adoption.

## Use Case

A developer uses Pi Coding Agent. They discover little-loops and want its issue management and loop automation. Commands and skills may load, but context monitoring and duplicate ID checks don't fire because there's no plugin wiring. With this feature, `ll:init --pi` sets up the plugin and gives them full parity.

## Proposed Solution

Pi has a TypeScript-first extension system (auto-discovered via jiti, no compilation step). Create `hooks/adapters/pi/index.ts` following the OpenCode pattern (`hooks/adapters/opencode/index.ts`) but using Node.js `child_process.spawn()` instead of `Bun.spawn()`, since Pi uses jiti (not Bun).

### Pi Plugin API (researched from https://github.com/badlogic/pi-mono)

**Format**: TypeScript/JavaScript default-export factory function receiving `ExtensionAPI` from `@earendil-works/pi-coding-agent`.

**Event mapping**:
| Pi event | Filter | ll intent |
|---|---|---|
| `session_start` | `reason === "startup"` | `session_start` |
| `session_before_compact` | — | `pre_compact` |

**Registration**: Drop `.ts` file in `.pi/extensions/` (project-local) or `~/.pi/agent/extensions/` (global). No trust dialog — Pi auto-loads with full permissions.

**Config directory**: `.pi/` (project-local), analogous to `.codex/` for Codex. Config candidate: `.pi/ll-config.json`.

### Implementation Approach

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
    // stdout is merged config JSON — Pi doesn't consume it directly, but returning it
    // makes it available for extension chaining if needed.
    return stdout ? JSON.parse(stdout) : undefined;
  });

  pi.on("session_before_compact", async (event, ctx) => {
    const { stderr, exitCode } = await spawnIntent("pre_compact", event, ctx.cwd);
    if (stderr) console.error(stderr);
    if (exitCode !== 0 && exitCode !== 2) throw new Error(stderr || `pre_compact failed (exit ${exitCode})`);
  });
}
```

**Installation**: `ll:init --pi` symlinks or copies `hooks/adapters/pi/index.ts` into `.pi/extensions/ll-hooks.ts` (or writes a re-export). No `{{LL_PLUGIN_ROOT}}`-substituted template needed — Pi resolves extensions by directory scan, not a config-file command string.

## Integration Map

### Files to Create (new)
- `hooks/adapters/pi/index.ts` — TypeScript extension adapter; `pi.on("session_start")` → `python -m little_loops.hooks session_start`, `pi.on("session_before_compact")` → `python -m little_loops.hooks pre_compact`; sets `LL_HOOK_HOST=pi` via `child_process.spawn` env
- `hooks/adapters/pi/package.json` — `@earendil-works/pi-coding-agent` as dev dependency; `"type": "module"`; no Bun requirement
- `hooks/adapters/pi/README.md` — event→intent mapping table, subprocess contract, no-trust-dialog note, install steps

### Files to Modify
- `scripts/little_loops/config/core.py:_config_candidates()` (line 84–88) — add `elif host == "pi" or state_dir == PI_CONFIG_DIR: candidates.append(project_root / PI_CONFIG_DIR / CONFIG_FILENAME)` branch; add `PI_CONFIG_DIR = ".pi"` constant alongside `CODEX_CONFIG_DIR`
- `scripts/little_loops/host_runner.py:PiRunner` — flesh out the four stub `build_*` methods once Pi's headless CLI flags are confirmed (binary is `pi`; `detect()` already uses `shutil.which("pi")`); update `capabilities` to reflect Pi's actual surface
- `config-schema.json` — add `"pi"` to `hooks.properties.host.enum` (already present in `orchestration.host_cli.enum`)
- `skills/init/SKILL.md` — add `--pi` flag to Step 1 parse block; add Step 8.5 variant that writes/symlinks `hooks/adapters/pi/index.ts` into `.pi/extensions/ll-hooks.ts`
- `docs/reference/HOST_COMPATIBILITY.md` — add Pi rows to hook-intents table (`session_start ✓`, `pre_compact ✓`) and config-probe-paths table (`.pi/ll-config.json` → `.ll/ll-config.json`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config/core.py:resolve_config_path()` (line 92) — reads `LL_HOOK_HOST` from env; picks up Pi automatically once `_config_candidates()` has the branch; no call-site changes needed
- `scripts/little_loops/host_runner.py:_PROBE_ORDER` (line 554) — `("pi", "pi")` already present; no change needed

### Similar Patterns
- `hooks/adapters/opencode/index.ts` — closest analog (TypeScript adapter, same spawn-intent pattern); replace `Bun.spawn()` with `node:child_process.spawn()` and `@opencode-ai/plugin` with `@earendil-works/pi-coding-agent`'s `ExtensionAPI`
- `hooks/adapters/codex/session-start.sh` + `hooks/adapters/codex/hooks.json` — reference for event-filter pattern (`matcher: "startup"` → Pi's `reason === "startup"` guard)
- `scripts/little_loops/config/core.py:85–86` — exact 2-line pattern to copy for Pi's `.pi/` config candidate

### Tests
- `scripts/tests/test_pi_adapter.py` (new) — mirror `test_codex_adapter.py` and `test_opencode_adapter.py`; skip if Node.js absent; verify `LL_HOOK_HOST=pi` propagation with sentinel-file pattern; verify `session_start`/`session_before_compact` dispatch
- `scripts/tests/test_config.py:TestResolveConfigPath` — add Pi probe-order tests mirroring `test_codex_path_takes_precedence_when_host_codex` with `LL_HOOK_HOST=pi` and `.pi/ll-config.json`
- `scripts/tests/test_config_schema.py:test_hooks_in_schema` — update exact-equality assertion to include `"pi"` in `hooks.host.enum`
- `scripts/tests/test_hook_intents.py:TestHooksMainModule` — add `test_ll_hook_host_env_var_propagates_pi` mirroring the codex variant

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_host_runner.py:TestPiRunner` — 4 existing tests use `pytest.raises(HostNotConfigured, match="FEAT-992")` for `build_streaming`, `build_blocking_json`, `build_version_check`, `build_detached`; all **will break** once build methods are implemented — update to argv-snapshot assertions following `TestCodexRunner` pattern [Agent 3 finding]
- `scripts/tests/test_hook_session_start.py` — add Pi parallel of `test_falls_back_to_codex_dir_config`: set `LL_HOOK_HOST=pi`, create `.pi/ll-config.json`, assert it is loaded through the session-start handler [Agent 2 finding]

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/tests/test_host_runner.py:TestPiRunner.test_pirunner_probe_returns_stub_not_raise` — a **fifth** `pytest.raises(HostNotConfigured, match="FEAT-992")` call exists inside this test (the probe-returns check) that is NOT counted in the "4 tests" note above; it also breaks when `build_streaming` is implemented — the second half of the compound assertion must become a valid-invocation check following `TestCodexRunner` [Agent 3 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — Pi column in hook-intents and config tables
- `hooks/adapters/pi/README.md` — install instructions + event mapping table

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — update `PiRunner` row in component table (~line 570, remove "research deferred" annotation); add Pi entry to `hooks/adapters/` directory tree listing (~line 89) [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — `HostNotConfigured` entry (~line 308) lists Pi as a stub runner; remove Pi from that note once `PiRunner.build_*` methods are implemented [Agent 2 finding]
- `docs/reference/API.md` — `little_loops.host_runner` section has `PiRunner` row with status `stub`; update to `✓ wired` (or `gated`) when build methods ship [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — add Pi-specific config probe-order documentation (`.pi/ll-config.json` candidate) under the `hooks.host` enum description, analogous to the Codex coverage in `HOST_COMPATIBILITY.md` [Agent 2 finding]

_Wiring pass 2 added by `/ll:wire-issue`:_
- `docs/claude-code/write-a-hook.md` — "The three concrete adapters" section enumerates exactly Claude Code, OpenCode, Codex; add Pi as a fourth; update the Mermaid diagram label `HOST[Host event<br/>Claude Code or OpenCode]` to include Pi; append `hooks/adapters/pi/index.ts` to the adapter-locations prose [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` — `host` field property table example list reads `"claude-code"`, `"opencode"`, `"codex"`; add `"pi"` [Agent 2 finding]
- `docs/development/TESTING.md` — `run_hook_intent` fixture docstring enumerates `"claude-code"`, `"opencode"`, `"codex"` as valid `host` argument values; add `"pi"` [Agent 2 finding]
- `CHANGELOG.md` — no Pi adapter entry exists in any child issue scope; add entry under the active release section when Pi ships (none of FEAT-1474, 1475, 1476 mention CHANGELOG) [Agent 2 finding]
- `hooks/adapters/codex/README.md` — "See also" / sibling adapter section lists Claude Code and OpenCode; add Pi once `hooks/adapters/pi/` exists [Agent 2 finding]
- `hooks/adapters/opencode/README.md` — "See also" section lists `hooks/adapters/claude-code/` and `hooks/adapters/codex/`; add Pi sibling [Agent 2 finding]

## API/Interface

```python
# Example interface/signature (TBD pending Pi plugin API investigation)
```

## Implementation Steps

1. **Confirm FEAT-957 is complete** — verify `hooks/adapters/codex/` exists and `_config_candidates()` in `config/core.py` has the `codex` branch; use these as the template for all Pi work

2. **Add Pi config candidate** (`scripts/little_loops/config/core.py:69–89`) — add `PI_CONFIG_DIR = ".pi"` constant after line 36; add `elif host == "pi" or state_dir == PI_CONFIG_DIR:` branch in `_config_candidates()` mirroring the codex branch at line 85

3. **Create TypeScript adapter** (`hooks/adapters/pi/`) — create `index.ts` using Node.js `child_process.spawn()` with `LL_HOOK_HOST=pi`; wire `session_start` (filter `reason === "startup"`) and `session_before_compact`; create `package.json` with `@earendil-works/pi-coding-agent` dev dependency; create `README.md` with event-mapping table

4. **Update config schema** (`config-schema.json`) — add `"pi"` to `hooks.properties.host.enum`; update `test_config_schema.py:test_hooks_in_schema` exact-equality assertion

5. **Add `ll:init --pi` support** (`skills/init/SKILL.md`) — add `--pi` flag to Step 1 parse block; add auto-detection via `command -v pi` or `[ -d ".pi" ]`; add Step 8.5 variant that copies/symlinks `hooks/adapters/pi/index.ts` to `.pi/extensions/ll-hooks.ts` (create `.pi/extensions/` if absent)

6. **Flesh out `PiRunner`** (`scripts/little_loops/host_runner.py`) — once Pi headless CLI flags are confirmed, implement `build_streaming()`, `build_blocking_json()`, `build_version_check()`, `build_detached()` and update `capabilities`; binary is `pi`, `detect()` via `shutil.which("pi")` already wired

7. **Write tests** — `test_pi_adapter.py` (Node.js subprocess + sentinel-file LL_HOOK_HOST check); `test_config.py` Pi probe-order cases; `test_hook_intents.py` LL_HOOK_HOST=pi in-process case

8. **Update docs** (`docs/reference/HOST_COMPATIBILITY.md`) — add Pi rows/columns to hook-intents and config-probe-paths tables; add Pi to adapter-locations list

9. **Verify acceptance criteria** — run `python -m pytest scripts/tests/ -k pi` and perform a manual smoke test in a Pi project with `ll:init --pi` followed by a fresh session

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/tests/test_host_runner.py:TestPiRunner` — replace the 4 `pytest.raises(HostNotConfigured, match="FEAT-992")` assertions with argv-snapshot tests following `TestCodexRunner` as the template; also add `test_capabilities_*` for Pi's `HostCapabilities`
11. Add Pi parallel in `scripts/tests/test_hook_session_start.py` — `LL_HOOK_HOST=pi` + `.pi/ll-config.json` asserts config loads through session-start handler
12. Update `docs/ARCHITECTURE.md` — remove "research deferred" from `PiRunner` component table row; add `pi/` entry to the `hooks/adapters/` directory listing
13. Update `docs/development/TROUBLESHOOTING.md` — remove Pi from the stub-runner list in the `HostNotConfigured` section
14. Update `docs/reference/API.md` — change `PiRunner` status from `stub` to `✓ wired` in the `little_loops.host_runner` runner table
15. Update `docs/reference/CONFIGURATION.md` — add Pi config probe-order note under `hooks.host` enum (`.pi/ll-config.json` probe path)
16. Fix `test_pirunner_probe_returns_stub_not_raise` compound assertion — this test has a FIFTH `match="FEAT-992"` not counted in step 10; the second half (which calls `build_streaming` and expects `HostNotConfigured`) must become a valid-invocation check once build methods are implemented
17. Update `docs/claude-code/write-a-hook.md` — rename "three concrete adapters" → "four concrete adapters"; update Mermaid diagram label; append `hooks/adapters/pi/index.ts` to adapter-locations prose
18. Update `docs/reference/EVENT-SCHEMA.md` — add `"pi"` to the `host` field example identifier list in the `LLHookEvent` properties table
19. Update `docs/development/TESTING.md` — add `"pi"` to `run_hook_intent` fixture docstring `host` argument example values
20. Add `CHANGELOG.md` entry for Pi adapter (none of FEAT-1474/1475/1476 list this file; must be done at release time)
21. Update `hooks/adapters/codex/README.md` and `hooks/adapters/opencode/README.md` — add Pi sibling link to each adapter's "See also" section

## Impact

- **Priority**: P5 - Low (ecosystem breadth, no urgent user demand yet)
- **Effort**: Small/Medium — pattern is well-established from OpenCode and Codex work; size depends on Pi's plugin API
- **Risk**: Low — additive; no changes to core logic
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `integration`, `plugin`, `compatibility`, `captured`

## Status

**Open** | Created: 2026-04-08 | Priority: P5

## Verification Notes

**Verdict**: NEEDS_UPDATE — Verified 2026-05-14

- **FEAT-1116 completed** (hook-intent abstraction). Removed from `blocked_by`.
- **FEAT-769 completed** (OpenCode adapter at `hooks/adapters/opencode/`).
- Still blocked by **FEAT-957** (canonical pattern for non-Claude-Code host adapter).
- Issue body remains TBD-heavy; should be re-refined once FEAT-957's `hooks/adapters/codex/` adapter ships and establishes the reusable template.

### Prior verifications
- 2026-04-11 — VALID; speculative with no Pi plugin work started.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-15_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- Wide site count (6-15 distinct files) with local per-site depth — breadth penalty is real but each site is straightforward; plan for careful enumeration during implementation
- `test_pi_adapter.py` does not exist yet — without this file, `LL_HOOK_HOST=pi` propagation and hook dispatch go untested; must be created as part of the implementation
- PiRunner `build_*` methods deferred pending Pi headless CLI flags — step 6 is out of scope for hook-compatibility acceptance criteria but needs follow-up after implementation

## Session Log
- `/ll:wire-issue` - 2026-05-15T19:27:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/25c8d618-48d9-413c-b4d1-bf120fb005aa.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59179ce1-13d5-40c7-bdca-8b3c6117c43e.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f40e61dc-0ba4-4eed-9f2d-a0c02e6abba1.jsonl`
- `/ll:wire-issue` - 2026-05-15T19:14:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65073b58-975f-4c54-8cb6-45ef5cec32a5.jsonl`
- `/ll:refine-issue` - 2026-05-15T19:09:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86b9a4a2-e55c-44e9-9243-346092efdc81.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T19:40:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d630f0d-2126-4eb0-8da2-2057ea37658f.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-19T01:16:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c7ed14d-9621-459d-9f93-384968b2e6f6.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:capture-issue` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba99d353-3f2a-47f1-ac66-f55be7e50744.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-15
- **Reason**: Issue too large for single session (size score 11/11 — Very Large)

### Decomposed Into
- FEAT-1474: Pi adapter core — TypeScript adapter, config candidate, schema, and tests
- FEAT-1475: Pi adapter init skill — ll:init --pi support
- FEAT-1476: Pi adapter documentation

> Step 6 (flesh out PiRunner build_* methods) is explicitly deferred pending Pi headless CLI flag research. It is out of scope for hook-compatibility acceptance criteria.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Blocked by FEAT-957 (establishes the plugin-compatibility pattern + reusable config-resolution abstraction) and FEAT-918 (event streaming lifecycle that plugin hooks must target). Reuse the config-directory-resolution abstraction introduced by FEAT-957 rather than independently patching `config/core.py` and `lib/common.sh`.

**Note** (added by `/ll:audit-issue-conflicts`, 2026-05-01): Once FEAT-957 publishes its event-mapping table (host event → ll hook intent) referencing the FEAT-1116 hook-intent contract, FEAT-992 MUST reuse that mapping rather than inventing a parallel Pi-event → ll-hook mapping. Before scaffolding `pi-plugin/`, verify FEAT-957's mapping table exists and confirm whether Pi's lifecycle event names cleanly project onto it. If they don't, update the shared mapping table jointly with FEAT-957 rather than diverging.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-10): This issue implements a **Host Adapter** (Pi Coding Agent integration), NOT an Extension in the FEAT-917 sense. Host adapters have no PyPI manifest and are NOT discoverable via `ll extensions` commands. Do not reference FEAT-917's extension registry from this issue's implementation. The canonical naming: "Extensions" = PyPI packages (`little-loops-ext-*`); "Host Adapters" = per-host wiring under `hooks/adapters/`.
