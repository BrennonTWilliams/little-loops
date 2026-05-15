---
id: FEAT-1483
type: FEAT
priority: P5
status: open
captured_at: "2026-05-15T20:37:29Z"
discovered_date: 2026-05-15
discovered_by: capture-issue
parent: FEAT-957
---

# FEAT-1483: Research Slash-Command and Skill Discovery for Codex CLI

## Summary

ll's commands (`commands/*.md`) and skills (`skills/*/SKILL.md`) are natively discoverable by Claude Code via its plugin SDK. Codex CLI has no known equivalent plugin/command-discovery API. This issue tracks researching whether such a mechanism exists — and if so, what wiring is needed to make ll commands and skills discoverable from within a Codex session.

## Current Behavior

`hooks/adapters/codex/README.md` notes:

> Out of scope (tracked separately): … slash-command and skill discovery for Codex

No wiring exists. Codex users can manually invoke `ll-action` or `ll-auto` from a terminal, but cannot discover or invoke `/ll:*` commands from within an active Codex session.

## Expected Behavior

After this research spike:
- Document whether Codex CLI exposes a plugin/command-discovery API (analogous to Claude Code's `.claude-plugin/plugin.json`)
- If yes: produce a follow-on implementation issue with specific wiring steps
- If no: document the gap and close; revisit when Codex adds extensibility

## Motivation

Command discovery is what makes ll feel native inside an agent session rather than an external tool. Claude Code users get `/ll:capture-issue`, `/ll:check-code`, etc. as first-class commands. Codex users get nothing from within the session. Closing this parity gap (if the API exists) would be the highest-value codex integration work remaining.

## Proposed Solution

### Research Phase

1. **Check Codex CLI docs** for plugin, extension, or command-registration concepts:
   - `codex --help` and any `codex plugin` / `codex extension` subcommands
   - GitHub: `openai/codex` README and docs directory
   - Any `PLUGIN.md`, `extensions.md`, or API reference in the Codex CLI repo
2. **Check for config-file extensibility** — does `.codex/config.toml` support a `commands` or `tools` section analogous to Claude Code's `.claude-plugin/`?
3. **Check hooks as a proxy** — can a hook respond to slash-commands typed in the Codex TUI? (Likely no, but worth confirming.)
4. **Summarize findings** in `thoughts/research/codex-command-discovery.md`

### Decision Tree

```
Codex has a plugin/command API?
├── Yes → File FEAT-XXXX: Implement ll command wiring for Codex plugin API
│          with specific implementation steps derived from the research
└── No  → Document gap in thoughts/research/codex-command-discovery.md
           Update hooks/adapters/codex/README.md "Out of scope" note
           Close this issue as "deferred pending Codex extensibility"
```

## Integration Map

### Files to Create

- `thoughts/research/codex-command-discovery.md` — research findings

### Files to Potentially Modify (if API exists)

- `hooks/adapters/codex/README.md` — update out-of-scope note
- `.claude-plugin/plugin.json` equivalent for Codex — TBD

### Files to Reference

- `.claude-plugin/plugin.json` — Claude Code's command-discovery manifest (template)
- `hooks/adapters/codex/README.md` — current out-of-scope note
- `hooks/adapters/opencode/` — TypeScript/Bun plugin pattern (may be analogous if Codex gains a similar model)

## Implementation Steps

1. Read Codex CLI docs and GitHub repo for plugin/extension/command concepts
2. Run `codex --help` and explore all subcommands
3. Check `.codex/config.toml` schema for extensibility fields
4. Document findings in `thoughts/research/codex-command-discovery.md`
5. File follow-on implementation issue OR close as deferred

## Impact

- **Scope**: Research only — no code changes in this issue
- **Risk**: None
- **Dependency note**: This is blocked by Codex CLI's own extensibility roadmap; if the API doesn't exist today, this issue should be re-evaluated with each major Codex release

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `hooks/adapters/codex/README.md` | Current out-of-scope note on command discovery |
| `.claude-plugin/plugin.json` | Claude Code command manifest (reference for what we'd want to replicate) |
| `thoughts/research/codex-headless-invocation.md` | Prior Codex research from FEAT-1465 |

## Labels

codex, research, commands, skills

---

## Session Log
- `/ll:capture-issue` - 2026-05-15T20:37:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ac48eaf-913e-40cd-8b15-98d99f2901cc.jsonl`
