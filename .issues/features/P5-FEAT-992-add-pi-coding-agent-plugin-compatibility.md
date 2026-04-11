---
id: FEAT-992
type: FEAT
priority: P5
status: open
discovered_date: 2026-04-08
discovered_by: capture-issue
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

TBD - requires investigation of Pi Coding Agent's plugin/hook API (see https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent). Follow the same pattern as:
- FEAT-769 / FEAT-959 / FEAT-960 / FEAT-961 — OpenCode plugin (shell hooks + JS/TS plugin)
- FEAT-957 — Codex CLI plugin

Key questions to resolve:
1. Does Pi have a plugin/extension API? What format (JS/TS, Python, shell)?
2. What lifecycle events are exposed (session start, tool call, compact, etc.)?
3. How does Pi resolve config/commands directories?

## Integration Map

### Files to Modify
- TBD - requires investigation of Pi Coding Agent plugin API

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/init.py` — `ll:init` entrypoint; will need `--pi` flag similar to planned `--codex` flag in FEAT-957
- `.claude-plugin/plugin.json` — may need Pi-specific manifest section

### Similar Patterns
- FEAT-957 (`P5-FEAT-957-add-openai-codex-cli-plugin-compatibility.md`) — closest parallel; follow same structure
- FEAT-961 (`P4-FEAT-961-opencode-js-ts-plugin.md`) — JS/TS plugin pattern if Pi uses a similar API
- FEAT-959 / FEAT-960 — path abstraction pattern if Pi needs its own config directory resolution

### Tests
- TBD - follow test patterns from FEAT-957 / FEAT-961

## API/Interface

```python
# Example interface/signature (TBD pending Pi plugin API investigation)
```

## Implementation Steps

1. **Investigate Pi Coding Agent plugin API** — read https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent; document lifecycle events, plugin format, config directory conventions
2. **Design plugin bridge** — follow FEAT-957 or FEAT-961 pattern depending on Pi's plugin format
3. **Implement plugin** — wire all session hooks to Pi lifecycle events
4. **Add `ll:init --pi` support** — detect Pi presence, scaffold plugin registration
5. **Test** — verify commands, skills, and all hooks fire correctly in Pi

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

**Verdict**: VALID — Speculative issue; no Pi Coding Agent plugin work has started. No `pi-plugin/` directory exists. Referenced FEAT-769/959/960/961 patterns remain in open state.

— Verified 2026-04-11

## Session Log
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:capture-issue` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba99d353-3f2a-47f1-ac66-f55be7e50744.jsonl`
