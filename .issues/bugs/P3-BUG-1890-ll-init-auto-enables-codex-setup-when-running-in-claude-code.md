---
id: BUG-1890
title: "ll:init auto-enables Codex setup when running in Claude Code"
status: open
priority: P3
type: BUG
captured_at: "2026-06-03T04:04:46Z"
discovered_date: "2026-06-03"
discovered_by: capture-issue
---

# BUG-1890: ll:init auto-enables Codex setup when running in Claude Code

## Summary

Running `/ll:init` inside Claude Code writes `.codex/hooks.json` even when the user never asked for Codex integration. The Codex auto-detection logic (`command -v codex || [ -d ".codex" ]`) is host-blind: it fires whenever `codex` is on PATH or a `.codex/` directory already exists, regardless of the active host CLI. As a result, Claude Code users who also happen to have Codex installed get Codex artifacts silently injected, violating the principle that each host should configure itself through its own init flow.

## Steps to Reproduce

1. Install both Claude Code and the Codex CLI (or have an existing `.codex/` dir).
2. Open a new project in Claude Code.
3. Run `/ll:init`.
4. Observe: `.codex/hooks.json` is created and the completion message says `[Codex] .codex/hooks.json written.`

## Expected Behavior

When running in Claude Code, `/ll:init` should only set up Claude Code artifacts. Codex artifacts (`.codex/hooks.json`) should be created only when running `/ll:init` inside Codex (or when `--codex` is explicitly passed).

## Actual Behavior

`.codex/hooks.json` is written unconditionally when `codex` is on PATH or `.codex/` already exists, even during a Claude Code session. Completion output includes:

```
Created: .codex/hooks.json (Codex CLI hook adapter)
[Codex] .codex/hooks.json written. Codex will show a hook-trust dialog on next session start...
```

## Root Cause

`skills/init/SKILL.md` line ~60: the auto-detection guard is:

```bash
if command -v codex >/dev/null 2>&1 || [ -d ".codex" ]; then CODEX=true; fi
```

This checks tool availability on the machine, not which host is currently running the skill. It needs to incorporate `resolve_host()` (or an equivalent env-var check, e.g. `$CLAUDE_CODE_SESSION` / `$LL_HOST_CLI`) so that Codex setup is only auto-enabled when the active host is Codex.

## Proposed Fix

Wrap the auto-detect block in a host guard:

```bash
CURRENT_HOST=$(ll-doctor --print-host 2>/dev/null || echo "unknown")
if [[ "$CURRENT_HOST" != "claude-code" ]]; then
    if command -v codex >/dev/null 2>&1 || [ -d ".codex" ]; then CODEX=true; fi
fi
```

Or rely on `LL_HOST_CLI` if the host runner already exports it. The key invariant: auto-detection should never promote `CODEX=true` when the active host is Claude Code (or any non-Codex host).

## Impact

- Creates unexpected files in user repositories without explicit opt-in.
- Confusing UX: the Codex hook-trust dialog appears in the next Codex session for a project the user never intended to configure for Codex.
- Violates the least-surprise principle: each host should own its own initialization.

## Session Log
- `/ll:capture-issue` - 2026-06-03T04:04:46Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5a9ea643-815c-4ba4-a65c-06a79d2602a1.jsonl`
