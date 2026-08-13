---
id: FEAT-3160
title: qwen-extension.json packaging + marketplace install path
type: FEAT
status: done
priority: P2
parent: EPIC-3154
captured_at: '2026-08-13T01:28:37Z'
discovered_date: 2026-08-12
discovered_by: capture-issue
labels:
- qwen
- host-compat
completed_at: '2026-08-13T04:15:00Z'
---

# FEAT-3160: qwen-extension.json packaging + marketplace install path

## Summary

Add a repo-root `qwen-extension.json` (the `kimi.plugin.json` analog) as the
native Qwen interactive/TUI packaging path: `name: ll`,
`commands`/`skills`/`agents` dir pointers, hooks via `hooks/hooks.json`
(file-based, so `${CLAUDE_PLUGIN_ROOT}`-style substitution applies).
Install: `qwen extensions install <repo-url>` or `qwen extensions link .`
for dev; `--scope project` supported. Document the Claude-marketplace
zero-artifact path too: `qwen extensions install
BrennonTWilliams/little-loops:ll` (auto-conversion), with caveats observed
by FEAT-3155 R3 verbatim.

## Motivation

Qwen Code installs Claude Code marketplace plugins natively, so ll's
existing `.claude-plugin/plugin.json` is already a zero-new-artifact
interactive install path — but conversion fidelity (hooks, matcher
translation, `/ll:*` namespacing) needs one live verification (FEAT-3155
R3). A native manifest is the first-party route. Headless automation never
depends on EITHER for hooks — FEAT-3158's managed `.qwen/settings.json`
block covers it. That is the lesson of BUG-2921 (kimi plugin-manifest hooks
inert under `-p`) applied up front.

## Implementation Steps

1. Write repo-root `qwen-extension.json`: `name: ll`, version, `commands`,
   `skills`, `agents` dir pointers, hooks reference.
2. Provide/verify the extension-path `hooks/hooks.json` (Qwen accepts the
   Claude hook JSON shape; matchers must use Qwen runtime tool ids).
3. Document both install paths in `docs/qwen/getting-started.md` (ENH-3162
   lands the docs; this child records the verified install commands +
   caveats).
4. Live-install verification per FEAT-3155 R3 (marketplace conversion,
   matcher translation, `${CLAUDE_PLUGIN_ROOT}` resolution, `/ll:*`
   namespace).

## Integration Map

### Files to Modify

- None existing (docs consumed by ENH-3162).

### New Files

- `qwen-extension.json` — native extension manifest (repo root)
- extension-path `hooks/hooks.json` (if distinct from the Claude plugin one)

### Dependent Files

- `.claude-plugin/plugin.json` + `marketplace.json` — marketplace auto-conversion inputs
- `docs/qwen/getting-started.md` — install instructions (ENH-3162)

## Impact

- **Priority**: P2 — independent track; interactive convenience, not the automation path.
- **Effort**: S — one manifest + install verification.
- **Risk**: Medium-Low — conversion fidelity unknown until R3 verified; native manifest + settings adapter never depend on it.
- **Breaking Change**: No.

## Verification Notes

2026-08-12 (DONE): Repo-root `qwen-extension.json` landed (name `ll`,
version 1.155.0, `commands`/`skills`/`agents` dir pointers). Key upgrade
over the marketplace path: hooks are **inline in the manifest** with
Qwen-native matchers and `${extensionPath}${/}…` hydration — inline hooks
take priority over `hooks/hooks.json` per the bundled extension-creator
skill, so the native path avoids the matcher-translation gap the FEAT-3155
R3 probe found in the marketplace conversion (Claude tool names copied
verbatim, never matching Qwen runtime ids). Live-verified: `qwen extensions
link .` ingested the manifest cleanly (commands + 9 agents loaded; clean
`qwen extensions uninstall` afterwards). Marketplace zero-artifact path
(`qwen extensions install BrennonTWilliams/little-loops:ll`) documented with
observed caveats in the spike artifact; both install paths land in
`docs/qwen/getting-started.md` (ENH-3162).

## Session Log
- `/ll:capture-issue` - 2026-08-13T01:28:37Z - qwen-code host integration report capture

---

**Done** | Created: 2026-08-12 | Completed: 2026-08-12 | Priority: P2
