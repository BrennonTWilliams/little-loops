---
id: ENH-1718
title: Enable `PreToolUse` by default for Codex adapter
type: ENH
priority: P4
status: open
captured_at: "2026-05-26T02:23:05Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1463
labels: [codex, hooks, host-compat]
---

# ENH-1718: Enable `PreToolUse` by default for Codex adapter

## Summary

`PreToolUse` was shipped opt-in only in FEAT-1489 despite the FEAT-1488 benchmark measuring p95 ≈ 10ms — well under the 200ms wire-by-default threshold. The conservative opt-in decision means any feature that depends on `PreToolUse` (duplicate-ID checks, context monitoring at tool boundaries, future rate-limit enforcement) silently does not fire for default Codex users.

## Motivation

FEAT-1489's resolution explicitly tied the opt-in/default decision to the benchmark gate: wire `pre_tool_use` opt-in-only if p95 < 200ms, or implement a sidecar if p95 ≥ 400ms. The measured p95 ≈ 10ms satisfies the threshold. Shipping as opt-in was therefore more conservative than the stated criteria required. Default enablement closes the gap with no user-visible latency cost.

## Current Behavior

`hooks/adapters/codex/hooks.json` has no `PreToolUse` entry. The Python handler (`scripts/little_loops/hooks/pre_tool_use.py`) exists and is registered in `_dispatch_table()`, but neither the Codex `hooks.json` nor the OpenCode `index.ts` enables it by default. Codex users who want PreToolUse must manually add the entry to their `.codex/hooks.json`.

## Expected Behavior

`hooks/adapters/codex/hooks.json` includes a `PreToolUse` entry pointing to a `pre-tool-use.sh` adapter script, matching the `PostToolUse` shape (timeout: 5s). Codex users get PreToolUse firing automatically after `/ll:init --codex`, consistent with the Claude Code default behavior.

## Acceptance Criteria

- `hooks/adapters/codex/hooks.json` includes a `PreToolUse` entry with `timeout: 5` and `statusMessage: "Checking tool use..."`
- `hooks/adapters/codex/pre-tool-use.sh` exists, is executable, sets `LL_HOOK_HOST=codex`, invokes `python -m little_loops.hooks pre_tool_use`
- `scripts/tests/test_codex_adapter.py` covers the new script (file-exists, executable, LL_HOOK_HOST sentinel, hooks.json presence)
- `docs/reference/HOST_COMPATIBILITY.md` `pre_tool_use` Codex CLI cell updated from `(opt-in)[^hot]` to `✓`
- `hooks/adapters/codex/README.md` event table updated: `PreToolUse` row reflects default enablement

## Implementation Steps

1. Create `hooks/adapters/codex/pre-tool-use.sh` — 4-line shim mirroring `post-tool-use.sh`, replacing intent with `pre_tool_use`
2. Add `PreToolUse` entry to `hooks/adapters/codex/hooks.json` mirroring the `PostToolUse` shape (no `matcher`, `timeout: 5`, `statusMessage: "Checking tool use..."`)
3. Update `scripts/tests/test_codex_adapter.py` — add `PRE_TOOL_USE` path constant; extend `test_adapter_files_exist`, `test_adapter_scripts_are_executable`; add `test_hooks_json_has_pre_tool_use` and `test_pre_tool_use_sets_ll_hook_host_codex`
4. Flip `pre_tool_use` Codex CLI cell in `docs/reference/HOST_COMPATIBILITY.md` from `(opt-in)[^hot]` to `✓`; update or remove `[^hot]` footnote for Codex
5. Update `hooks/adapters/codex/README.md` event table

## Notes

- Trust-hash churn: adding `PreToolUse` to `hooks/adapters/codex/hooks.json` changes the file hash; existing Codex users will be prompted to re-trust on next startup. Document in PR.
- `pre_tool_use.py` handler is already a no-op (`LLHookResult(exit_code=0)`) — no behavioral change until a consumer populates it.
- Benchmark evidence on record: `scripts/tests/bench_opencode_adapter.py` p95 ≈ 10ms (from FEAT-1489 resolution), well under `_DECISION_TARGET_MS = 200`.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `hooks/adapters/codex/hooks.json` | File to modify — add `PreToolUse` entry |
| `hooks/adapters/codex/post-tool-use.sh` | Direct template for the new script |
| `docs/reference/HOST_COMPATIBILITY.md` | `pre_tool_use` row to flip |
| `scripts/tests/bench_opencode_adapter.py` | Benchmark evidence justifying default enablement |

## Status

**Open** | Created: 2026-05-26 | Priority: P4

## Session Log
- `/ll:verify-issues` - 2026-05-31T02:30:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:23:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e210ff4-bcab-4372-9c8c-a0ba98da62d5.jsonl`
