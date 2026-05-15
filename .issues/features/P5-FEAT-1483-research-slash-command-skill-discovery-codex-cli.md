---
id: FEAT-1483
type: FEAT
priority: P5
status: open
captured_at: "2026-05-15T20:37:29Z"
discovered_date: 2026-05-15
discovered_by: capture-issue
parent: FEAT-957
decision_needed: false
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
- `docs/reference/HOST_COMPATIBILITY.md` — update `[^cmds]` footnote and parity matrix `✗` cells after research concludes (regardless of whether a discovery API exists) [Agent 2 finding]
- `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md` — replace `(unfiled)` child-issue entries with actual filed FEAT IDs after filing follow-ons [Agent 2 finding]

### Files to Reference

- `.claude-plugin/plugin.json` — Claude Code's command-discovery manifest (template)
- `hooks/adapters/codex/README.md` — current out-of-scope note
- `hooks/adapters/opencode/` — TypeScript/Bun plugin pattern (may be analogous if Codex gains a similar model)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Primary research lead**: `docs/reference/HOST_COMPATIBILITY.md` (lines 44–52) — the parity matrix footnote `[^cmds]` already documents that **Codex reads `.codex/prompts/`** for slash-command discovery. The research question is now more targeted: what is the `.codex/prompts/` file format, and does Codex have any equivalent surface for skills/agents?

- `docs/reference/HOST_COMPATIBILITY.md` — parity matrix showing `✗` for both Codex command and skill discovery; footnote `[^cmds]` records the known path (`.codex/prompts/`) and two implementation options; **must be updated** after research resolves the format question
- `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md` — umbrella epic that already has the two follow-on FEATs outlined as `(unfiled)`: slash-command bridge via `.codex/prompts/` and skill discovery (or permanent-gap documentation); file against this epic when closing or spawning follow-ons
- `thoughts/research/codex-headless-invocation.md` — **format template** for the output artifact `thoughts/research/codex-command-discovery.md`; follow its `Status/Sources/Flag-table/Capability-map/Gating-recommendation` structure; also notes that the `codex` binary is **not installed on the dev host** (last verified 2026-05-15) — external research required
- `hooks/adapters/opencode/index.ts` — TypeScript/Bun plugin via `@opencode-ai/plugin` v1.2.27; **not analogous** to Codex — Codex is Rust-based with no TypeScript SDK (confirmed in `hooks/adapters/codex/README.md`); plugin surface in OpenCode only wires hook events, not command/skill discovery anyway
- `scripts/little_loops/host_runner.py:HostCapabilities` — frozen dataclass with capability flags (`streaming`, `permission_skip`, `agent_select`, `tool_allowlist`); if research confirms a Codex command-discovery API, a `command_discovery` flag may be warranted here for the orchestration layer

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_host_runner.py` — conditional: if `command_discovery: bool = False` is added to `HostCapabilities` in a follow-on issue, update `TestCodexRunner::test_capabilities_disable_agent_and_tools` (line 278–283) to assert the new field; follow the existing pattern of one assertion per capability flag [Agent 3 finding]
- `docs/reference/API.md` — conditional: if `command_discovery` flag is added, the `HostCapabilities` fields table under `little_loops.host_runner` needs a new row [Agent 2 finding]
- `docs/ARCHITECTURE.md` — conditional: if `command_discovery` flag is added, the "Host Runner Layer" field enumeration `(streaming, permission_skip, agent_select, tool_allowlist)` becomes stale [Agent 2 finding]

## Implementation Steps

1. Read Codex CLI docs and GitHub repo for plugin/extension/command concepts
2. Run `codex --help` and explore all subcommands
3. Check `.codex/config.toml` schema for extensibility fields
4. Document findings in `thoughts/research/codex-command-discovery.md`
5. File follow-on implementation issue OR close as deferred

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 0 (before external research)**: Read `docs/reference/HOST_COMPATIBILITY.md` footnote `[^cmds]` and `EPIC-1463` — both already document that Codex reads `.codex/prompts/` and outline the two implementation paths; this narrows Step 1 to verifying the `.codex/prompts/` format and discovering any skill/agent surface
- **Step 2 caveat**: ~~`codex` binary is not installed on the dev host~~ — `codex` is now installed via npm (2026-05-15); `codex --help` and subcommand exploration can be run locally
- **Step 3 refinement**: Check `~/.codex/config.toml` (user-level, not project-level) in addition to `.codex/config.toml` — the trust-hash mechanism documented in `hooks/adapters/codex/README.md` shows that user config lives at `~/.codex/config.toml`; look for a `[commands]` or `[plugins]` section
- **Output artifact format**: Follow `thoughts/research/codex-headless-invocation.md` structure (`Status`, `Sources`, table, `Capability map`, `Gating recommendation`) when writing `thoughts/research/codex-command-discovery.md`
- **Binary available**: `codex` installed via npm on dev host (2026-05-15) — all steps can be run locally; no need for GitHub-only research path
- **Step 5 filing target**: File any follow-on FEATs as children of `EPIC-1463` (it already has the two `(unfiled)` slots: slash-command bridge + skill discovery)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/HOST_COMPATIBILITY.md` — revise `[^cmds]` footnote and the `✗` cells in the "Slash-command and skill discovery" parity row to reference `thoughts/research/codex-command-discovery.md` and reflect the research outcome
7. Update `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md` — replace the two `(unfiled)` child-issue entries with actual filed FEAT IDs (or a "closed as deferred" note if no API exists)

## Impact

- **Scope**: Research only — no code changes in this issue
- **Risk**: None
- **Dependency note**: This is blocked by Codex CLI's own extensibility roadmap; if the API doesn't exist today, this issue should be re-evaluated with each major Codex release

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `hooks/adapters/codex/README.md` | Current out-of-scope note on command discovery |
| `.claude-plugin/plugin.json` | Claude Code command manifest (reference for what we'd want to replicate) |
| `thoughts/research/codex-headless-invocation.md` | Prior Codex research from FEAT-1465; format template for output artifact |
| `docs/reference/HOST_COMPATIBILITY.md` | Parity matrix; footnote [^cmds] already documents `.codex/prompts/` as the Codex command path and the two implementation options |
| `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md` | Umbrella epic; has `(unfiled)` slots for slash-command bridge FEAT and skill-discovery FEAT |

## Labels

codex, research, commands, skills

---

## Session Log
- `/ll:refine-issue` - 2026-05-15T21:25:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c6fcfa4-b17c-4d21-8cbb-87bc6c248119.jsonl`
- `/ll:wire-issue` - 2026-05-15T21:15:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdf8b29b-c64d-4fd5-9d5c-9082345d0652.jsonl`
- `/ll:refine-issue` - 2026-05-15T21:08:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d42dbf9b-cc4b-408b-9155-54a52d42f2f2.jsonl`
- `manual update` - 2026-05-15 - codex installed via npm on dev host; binary blocker resolved, all research steps now runnable locally; `depends_on: FEAT-1481` added
- `/ll:capture-issue` - 2026-05-15T20:37:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ac48eaf-913e-40cd-8b15-98d99f2901cc.jsonl`
