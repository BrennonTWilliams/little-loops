---
id: FEAT-3158
title: Hook adapter — hooks/adapters/qwen + ll-init wiring + managed settings block
type: FEAT
status: done
priority: P2
parent: EPIC-3154
depends_on:
- FEAT-3155
captured_at: '2026-08-13T01:28:37Z'
discovered_date: 2026-08-12
discovered_by: capture-issue
labels:
- qwen
- host-compat
completed_at: '2026-08-13T03:30:00Z'
---

# FEAT-3158: Hook adapter — hooks/adapters/qwen + ll-init wiring + managed settings block

## Summary

Land the Qwen hook adapter (Option A — settings injection, per
ARCHITECTURE-046 as ratified for Gemini) and its `ll-init` wiring.
`ll-init --hosts qwen` writes a **managed, marker-delimited `hooks` block
into the project's `.qwen/settings.json`**, gen-version stamped for
`ll-init --upgrade` regeneration (FEAT-2387 machinery), never touching keys
outside the block. Each shim exports `LL_HOOK_HOST=qwen` and pipes stdin to
`python -m little_loops.hooks <intent>`. Shims live at
`scripts/little_loops/hooks/adapters/qwen/` (wheel-packaged per EPIC-2279's
asset resolver).

Critical path with ENH-3156. Settings scope (project vs user
`~/.qwen/settings.json`) is decided by FEAT-3155 R2 — if project-scope hooks
don't fire under `qwen -p` (the Kimi BUG-2921 failure mode), install to user
scope instead; same managed-block machinery, different target.

## Motivation

Hooks are how ll's host-agnostic Python intent layer receives lifecycle
events. Qwen's hook protocol is Claude-compatible by design (17 events,
same stdin/stdout JSON shape, exit 0/2 semantics), so adapters are thin
transports — all logic stays in the Python layer. The managed config block
is the hook route headless automation can rely on (BUG-2921 lesson).

## Implementation Steps

1. Create `scripts/little_loops/hooks/adapters/qwen/` with one shim per
   wired intent (session-start, drift-check, pre-compact, precompact-handoff,
   prompt-submit, pre-tool-use, post-tool-use, edit-batch-nudge, session-end,
   subagent-start, subagent-stop) + a settings-block template with
   `{{LL_PLUGIN_ROOT}}`/`{{LL_GEN_VERSION}}` placeholders + README (adapter
   contract, event→intent table, payload-drift notes — per
   `hooks/adapters/kimi/README.md` style).
2. Shims follow the universal contract: `INPUT=$(cat)` →
   `export LL_HOOK_HOST=qwen` → pipe to `python -m little_loops.hooks <intent>`
   (interpreter via `$LL_PYTHON` → `python3` → `python`), plus the Kimi-style
   re-`cd` to the payload's `cwd` (BUG-2921 hardening, cheap up front).
3. Wire the v1 event set (9 Qwen event types → 10 intents + 2 legacy
   scripts): SessionStart (`session_start` + `drift_check`), PreCompact
   (`pre_compact` + `pre_compact_handoff`), UserPromptSubmit, PreToolUse
   (`write_file|edit` matcher), PostToolUse (`*` → `post_tool_use`;
   `write_file|edit` → `edit_batch_nudge`), SessionEnd, SubagentStart,
   SubagentStop, Stop (legacy `context-handoff-sentinel.sh` +
   `session-cleanup.sh`). Full Claude-plugin parity; one event beyond Kimi's
   eight (Stop). Matchers use Qwen runtime tool ids (`write_file|edit`,
   `run_shell_command`), not Claude names.
4. `install_qwen_adapter()` in `init/writers.py` (managed
   `.qwen/settings.json` block per the codex/kimi writers); add qwen to
   `AGENTS_MD_HOSTS` so the shared `write_agents_md()` fires (Qwen reads
   `AGENTS.md` natively).
5. Wire `init/cli.py` (`_KNOWN_HOSTS`, `_detect_hosts()` probing the `qwen`
   binary / `.qwen/` dir LAST, `_dispatch_host_adapters()`, `--hosts` help)
   and `init/tui.py` checkbox.
6. Tests mirroring `test_kimi_adapter.py` in `scripts/tests/test_qwen_adapter.py`.

## Integration Map

### Files to Modify

- `scripts/little_loops/init/cli.py` — `_KNOWN_HOSTS`, `_detect_hosts()`, `_dispatch_host_adapters()`, `--hosts` help
- `scripts/little_loops/init/tui.py` — host checkbox
- `scripts/little_loops/init/writers.py` — `install_qwen_adapter()`, `AGENTS_MD_HOSTS`

### New Files

- `scripts/little_loops/hooks/adapters/qwen/` — shims, settings-block template, README
- `scripts/tests/test_qwen_adapter.py`

### Dependent Files

- `scripts/little_loops/hooks/__init__.py` — `main_hooks` dispatch (no new intents in v1)
- `.qwen/settings.json` (project, written by `ll-init` at runtime)

## Impact

- **Priority**: P2 — critical path with ENH-3156; the epic's hook success metrics depend on it.
- **Effort**: M — 11 shims + template + install writer + init wiring + tests.
- **Risk**: Medium — settings-scope decision gated on FEAT-3155 R2; fallback to user scope is the same machinery.
- **Breaking Change**: No.

## Verification Notes

2026-08-12 (DONE): Adapter landed per the spike findings.
- `scripts/little_loops/hooks/adapters/qwen/`: 12 shims (11 intent shims +
  `stop.sh` legacy resolver) + `settings-block.json` template. All shims
  export `LL_HOOK_HOST=qwen`, re-cd to the payload `cwd` (BUG-2921
  hardening), and resolve the interpreter via `$LL_PYTHON` → python3 → python.
- Managed-block design diverges from kimi's raw TOML markers out of
  necessity: JSON has no comments, so `install_qwen_adapter()` performs a
  **structured JSON merge** into project `.qwen/settings.json` — managed
  entries identified by `ll:`-prefixed `name` fields, gen-version stamped in
  `description` (`ll-gen:<version>`); every other key and third-party hook
  entry is preserved verbatim. First implementation of ARCHITECTURE-046
  Option A (ratified for Gemini, landed first on Qwen).
- Stop wiring: `stop.sh` resolves `$CLAUDE_PLUGIN_ROOT`/`$LL_PLUGIN_ROOT`
  legacy `context-handoff-sentinel.sh` + `session-cleanup.sh` at runtime and
  no-ops gracefully when absent (those scripts are not wheel-packaged).
- Matchers use Qwen runtime tool ids (`write_file|edit`, `.*`); timeouts in
  milliseconds (Qwen unit). SessionEnd wired natively (documented as
  interactive-only — spike found it does not fire under `-p`).
- ll-init wiring: `_KNOWN_HOSTS` + `_detect_hosts()` (appended last) +
  dispatch branch + `--hosts` help text + `has_qwen` plan option + TUI
  checkbox/label; `AGENTS_MD_HOSTS += "qwen"`.
- README at `hooks/adapters/qwen/README.md` (repo-root convention).
- Tests: `scripts/tests/test_qwen_adapter.py` — 23 passed (sentinels,
  template rendering, matcher policy, end-to-end shim dispatch via bash +
  stub dispatcher, writer merge/idempotence/force/corruption/dry-run).
  `test_init_core.py` (272) + `test_init_audit_fixes.py` (37) stay green.

## Session Log
- `/ll:capture-issue` - 2026-08-13T01:28:37Z - qwen-code host integration report capture

---

**Done** | Created: 2026-08-12 | Completed: 2026-08-12 | Priority: P2
