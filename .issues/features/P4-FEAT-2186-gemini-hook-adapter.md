---
id: FEAT-2186
title: Hook adapter — hooks/adapters/gemini/ translating gemini-cli events to LLHookEvent
type: feature
status: open
priority: P4
parent: EPIC-2178
depends_on: [FEAT-2179, ENH-2184]
decision_needed: false
decision_ref: ARCHITECTURE-046
captured_at: "2026-06-15T00:00:00Z"
discovered_date: 2026-06-15
discovered_by: capture-issue
labels: [gemini, host-compat, hooks]
---

# FEAT-2186: Hook adapter — hooks/adapters/gemini/

## Summary

Create `hooks/adapters/gemini/` with adapter scripts that translate gemini-cli
lifecycle events into `LLHookEvent` format and invoke the ll hook handler.
Analogous to `hooks/adapters/codex/` and `hooks/adapters/claude-code/`.

## Current Behavior

Gemini CLI users have no hook adapter. None of the ll hook intents
(`session_start`, `pre_compact`, `pre_tool_use`, `post_tool_use`, etc.) fire
during Gemini lifecycle events, so history capture, context injection, and tool
auditing are unavailable when little-loops runs under Gemini. Only
`hooks/adapters/codex/`, `hooks/adapters/claude-code/`, and
`hooks/adapters/opencode/` exist; `hooks/adapters/gemini/` does not.

## Expected Behavior

`hooks/adapters/gemini/` exists with adapter scripts that mirror the Codex and
Claude Code adapters. Gemini lifecycle events (`SessionStart`, `PreCompress`,
`BeforeTool`, `AfterTool`, etc.) are translated into `LLHookEvent` format and
dispatched to the host-agnostic ll hook handler, so history capture, context
injection, and tool auditing behave the same as under Claude Code. Users
activate the adapter via `ll:configure --gemini`, which injects the hook entries
into `.gemini/settings.json`.

## Motivation

Gemini is one of the four hosts targeted by the host-compatibility epic
(EPIC-2178). Without the hook adapter, a Gemini user gets none of little-loops'
lifecycle automation — the analytics, history, and context-injection features
silently no-op. The adapter is the bridge that makes ll's host-agnostic hook
handler reachable from Gemini, bringing Gemini to parity with Codex and Claude
Code. The work is low-risk and additive: Gemini's stdin/stdout JSON hook
protocol is identical to Claude Code's, so the existing handler is reused as-is.

## Decision — RATIFIED 2026-06-24 (Option A; see ARCHITECTURE-046)

**Resolved: Option A** — inject hook entries into `.gemini/settings.json` via
`ll:configure --gemini`. Lower complexity, mirrors the existing
`hooks/adapters/claude-code/` pattern, and the ll hook handler is already
host-agnostic. Extension packaging (Option B) is deferred to a separate
enhancement if extension-based distribution is later wanted. The original
decision framing is preserved below for context.

Gemini hooks can be registered in two ways (FEAT-2179):
- **Option A**: Inject entries into `.gemini/settings.json` under `hooks:` — user
  activates by running `ll:configure --gemini` which patches their local
  `settings.json`.
- **Option B**: Package hooks as a Gemini Extension (`~/.gemini/extensions/ll/`)
  with a `gemini-extension.json` manifest — user installs the extension once.

`hooks migrate --from-claude` exists but migrates Claude Code hooks, not ll hooks.

**Option A is recommended**: lower complexity, same pattern as the Claude Code
adapter (`hooks/adapters/claude-code/`), and the ll hook handler is already
host-agnostic. Extension packaging (Option B) is a separate enhancement.

## Use Case

A Gemini user installs little-loops. `session_start`, `pre_compact`, `pre_tool_use`,
and `post_tool_use` ll hook intents fire when Gemini lifecycle events occur —
enabling history capture, context injection, and tool auditing.

## Event Mapping (from FEAT-2179)

| Gemini event | ll intent |
|-------------|-----------|
| `SessionStart` | `session_start` |
| `PreCompress` | `pre_compact` |
| `BeforeAgent` | `user_prompt_submit` |
| `BeforeTool` | `pre_tool_use` |
| `AfterTool` | `post_tool_use` |
| `SessionEnd` | `session_end` |

New events with no current ll intent (not wired in this issue):
`AfterAgent`, `BeforeModel`, `AfterModel`, `BeforeToolSelection`, `Notification`.

Protocol: stdin/stdout JSON — identical to Claude Code hooks. `CLAUDE_PROJECT_DIR`
alias is provided by Gemini for compatibility.

## Integration Map

### Files to Modify
- `ll:configure` command — add a `--gemini` path that injects the adapter's hook
  entries into `.gemini/settings.json` (see Implementation Step 8).

### New Files
- See [API/Interface § New Files](#apiinterface) for the full list of adapter
  scripts, `hooks.json`, `README.md`, and the test module.

### Dependent Files (Callers/Importers)
- The host-agnostic ll hook handler invoked by the adapter scripts — reused
  unchanged (`scripts/little_loops/hooks/`).

### Similar Patterns
- `hooks/adapters/codex/` — closest pattern to follow (per-host adapter subdir).
- `hooks/adapters/claude-code/` — alternate reference; same stdin/stdout JSON
  protocol Gemini uses.

### Tests
- `scripts/tests/test_gemini_adapter.py` — new; assert event→intent mapping and
  that each adapter script dispatches the correct `LLHookEvent`.

### Documentation
- `hooks/adapters/gemini/README.md` — installation instructions + event mapping.
- `docs/reference/HOST_COMPATIBILITY.md` — note Gemini hook support once landed.

### Configuration
- `.gemini/settings.json` — user-local file patched by `ll:configure --gemini`.

## Implementation Steps

1. Create `hooks/adapters/gemini/` directory.
2. Create `hooks/adapters/gemini/hooks.json` — event→handler mapping for the 6
   events above.
3. Create `hooks/adapters/gemini/session-start.sh` — wraps `session_start` intent.
4. Create `hooks/adapters/gemini/pre-compact.sh` — wraps `pre_compact` intent.
5. Create `hooks/adapters/gemini/pre-tool-use.sh` — wraps `pre_tool_use` intent.
6. Create `hooks/adapters/gemini/post-tool-use.sh` — wraps `post_tool_use` intent.
7. Create `hooks/adapters/gemini/README.md` — installation instructions and event
   mapping table.
8. Create `ll:configure --gemini` extension (or document manual installation) to
   inject hook entries into `.gemini/settings.json`.
9. Add tests in `scripts/tests/test_gemini_adapter.py`.

## Acceptance Criteria

- `hooks/adapters/gemini/hooks.json` exists with all 6 event mappings.
- A `SessionStart` event from Gemini triggers the `session_start` ll intent handler.
- A `BeforeTool` event triggers `pre_tool_use`.
- `hooks/adapters/gemini/README.md` documents how to activate the adapter.
- Tests pass.

## API/Interface

### New Files

- `hooks/adapters/gemini/hooks.json`
- `hooks/adapters/gemini/session-start.sh`
- `hooks/adapters/gemini/pre-compact.sh`
- `hooks/adapters/gemini/pre-tool-use.sh`
- `hooks/adapters/gemini/post-tool-use.sh`
- `hooks/adapters/gemini/README.md`
- `scripts/tests/test_gemini_adapter.py`

### Reference

- `hooks/adapters/codex/` — pattern to follow
- `hooks/adapters/claude-code/` — alternate reference

## Impact

- **Priority**: P4 — Gemini is a later-phase host in EPIC-2178; blocked behind FEAT-2179 and ENH-2184 and not on the critical path for the primary (Claude Code / Codex) hosts.
- **Effort**: S–M (4–8 hours)
- **Risk**: Low — additive; Gemini's hook protocol is stdin/stdout JSON, same as Claude Code
- **Breaking Change**: No

## Related Key Documentation

- `thoughts/research/gemini-cli-surface.md` — FEAT-2179 research spike confirming
  the stdin/stdout JSON hook protocol.
- `docs/reference/HOST_COMPATIBILITY.md` — host capability matrix.

_Run `/ll:normalize-issues` to discover and link additional relevant docs._

---

## Verification Notes

2026-06-18 (UNSTARTED): `hooks/adapters/gemini/` directory does not exist. FEAT-2179 (research spike) is complete — `thoughts/research/gemini-cli-surface.md` exists and confirms stdin/stdout JSON hook protocol identical to Claude Code. ENH-2184 (GeminiRunner stub) not yet implemented; this issue's `depends_on` correctly captures that ordering.

- **2026-06-26** (/ll:verify-issues): Corrected Current Behavior — added `hooks/adapters/opencode/` to the list of existing adapter subdirs (previously omitted, only codex and claude-code were listed); the central claim that `hooks/adapters/gemini/` is absent remains accurate.

**Open** | Created: 2026-06-15 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-06-26T23:20:04 - `9c24a548-31d7-49d9-b376-2665d69b3ab4.jsonl`
