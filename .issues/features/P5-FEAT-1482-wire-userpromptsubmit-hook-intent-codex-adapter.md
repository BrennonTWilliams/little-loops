---
id: FEAT-1482
type: FEAT
priority: P5
status: open
captured_at: "2026-05-15T20:37:29Z"
discovered_date: 2026-05-15
discovered_by: capture-issue
parent: FEAT-957
---

# FEAT-1482: Wire `UserPromptSubmit` Hook Intent for Codex Adapter

## Summary

The Codex hook adapter (`hooks/adapters/codex/`) implements `SessionStart` and `PreCompact` but leaves `UserPromptSubmit` deferred. Claude Code uses this intent for the auto-prompt-optimizer hook. This issue tracks wiring it for Codex so Codex users can benefit from the same auto-prompt optimization.

## Current Behavior

`hooks/adapters/codex/README.md` event mapping table shows:

| Codex event | ll intent | Status |
|---|---|---|
| `UserPromptSubmit` | — | Deferred — Claude Code uses this for auto-prompt-optimizer; track separately |

No `UserPromptSubmit` entry exists in `hooks/adapters/codex/hooks.json`. Codex users cannot trigger the `user_prompt_submit` intent (and by extension, the auto-prompt-optimizer) via hooks.

## Expected Behavior

- `hooks/adapters/codex/hooks.json` includes a `UserPromptSubmit` handler wired to the Python dispatcher (`python -m little_loops.hooks user_prompt_submit`)
- `hooks/adapters/codex/prompt-submit.sh` (or equivalent) adapter script sets `LL_HOOK_HOST=codex` and forwards the event payload to the dispatcher
- The `user_prompt_submit` intent fires for Codex users when a prompt is submitted
- Behavior matches the Claude Code adapter's `UserPromptSubmit` handling

## Motivation

The auto-prompt-optimizer is one of ll's most visible session-time features. Codex CLI users who install little-loops get `SessionStart` and `PreCompact` but miss prompt optimization — a visible parity gap. Wiring this closes the most user-facing hook gap for Codex.

## Proposed Solution

1. **Research Codex `UserPromptSubmit` payload** — confirm the event's stdin JSON shape (fields: `hook_event_name`, `session_id`, `prompt`, `cwd`, `model`). Verify against Codex CLI docs or `codex exec --help`.
2. **Add adapter script** — create `hooks/adapters/codex/prompt-submit.sh` mirroring `hooks/adapters/codex/session-start.sh`: set `LL_HOOK_HOST=codex`, pipe stdin to `python -m little_loops.hooks user_prompt_submit`, propagate exit code.
3. **Register in hooks.json** — add a `UserPromptSubmit` entry to `hooks/adapters/codex/hooks.json` pointing to `prompt-submit.sh`.
4. **Verify Python dispatcher** — confirm `little_loops/hooks/__init__.py` handles the `user_prompt_submit` intent (it should already, since Claude Code uses it; verify the handler doesn't assume Claude Code–specific payload fields).
5. **Test** — add a test case to `scripts/tests/test_codex_adapter.py` for the new script, mirroring the `test_adapter_sets_ll_hook_host_codex` pattern.

## Integration Map

### Files to Modify

- `hooks/adapters/codex/hooks.json` — add `UserPromptSubmit` handler entry
- `hooks/adapters/codex/README.md` — update event mapping table: change `UserPromptSubmit` status from "Deferred" to "Implemented"

### Files to Create

- `hooks/adapters/codex/prompt-submit.sh` — new adapter script

### Files to Reference (not modify)

- `hooks/adapters/codex/session-start.sh` — canonical template for new adapter script
- `hooks/adapters/claude-code/` — Claude Code's `UserPromptSubmit` wiring for reference
- `scripts/tests/test_codex_adapter.py` — existing test patterns to mirror

## Implementation Steps

1. Confirm `UserPromptSubmit` payload fields from Codex CLI docs
2. Create `prompt-submit.sh` from `session-start.sh` template, replacing intent name
3. Add hook entry to `hooks.json`; keep matcher unrestricted (fire on all user prompts)
4. Verify the `user_prompt_submit` Python handler is host-agnostic
5. Add test to `test_codex_adapter.py`
6. Update README event mapping table

## Impact

- **Scope**: New shell script + hooks.json entry + one test
- **Risk**: Low — reuses existing dispatcher; only adds a new hook entry
- **Note**: Trust-hash implications: adding a new `UserPromptSubmit` entry to `.codex/hooks.json` will change the trust hash, prompting users to re-trust on next startup (per FEAT-957 trust model). Document in the PR.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `hooks/adapters/codex/README.md` | Event mapping table and subprocess contract |
| `hooks/adapters/codex/session-start.sh` | Canonical adapter script template |
| `scripts/tests/test_codex_adapter.py` | Test patterns for codex adapter scripts |

## Labels

codex, hooks, auto-prompt-optimizer

---

## Session Log
- `/ll:capture-issue` - 2026-05-15T20:37:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ac48eaf-913e-40cd-8b15-98d99f2901cc.jsonl`
