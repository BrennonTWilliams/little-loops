---
id: FEAT-2186
title: Hook adapter — hooks/adapters/gemini/ translating gemini-cli events to LLHookEvent
type: feature
status: open
priority: P4
parent: EPIC-2178
depends_on: [FEAT-2179, ENH-2184]
decision_needed: true
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

## Decision Needed

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

- **Effort**: S–M (4–8 hours)
- **Risk**: Low — additive; Gemini's hook protocol is stdin/stdout JSON, same as Claude Code
- **Breaking Change**: No

---

**Open** | Created: 2026-06-15 | Priority: P4
