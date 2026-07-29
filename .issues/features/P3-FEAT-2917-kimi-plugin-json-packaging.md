---
id: FEAT-2917
title: kimi.plugin.json packaging (kimi-native install path)
type: FEAT
status: done
priority: P3
parent: EPIC-2910
captured_at: '2026-07-29T15:55:00Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- kimi
- host-compat
completed_at: '2026-07-29T20:54:06Z'
---

# FEAT-2917: kimi.plugin.json packaging (kimi-native install path)

## Summary

Add a repo-root `kimi.plugin.json`: name `"ll"`, skills `"./skills/"`,
commands `"./commands/"`, a hooks array referencing the packaged adapter
shims from FEAT-2915, and an optional `sessionStart.skill`. Plus a README
install section for the kimi-native path.

## Motivation

`kimi.plugin.json` is the kimi-native install path — `kimi /plugins install
<path-or-github-url>` gives kimi users `/ll:*` commands and active hooks
without running `ll-init`. Plugin id `ll` preserves the `/ll:<command>`
namespace (EPIC-2910 naming decisions). Installs are per-user (kimi
limitation), which the README section must note.

## Implementation Steps

1. Add `kimi.plugin.json` at the repo root: name `"ll"`, skills
   `"./skills/"`, commands `"./commands/"`, hooks array referencing the
   packaged shims from FEAT-2915, optional `sessionStart.skill`.
2. README install section: `kimi /plugins install <path-or-github-url>`,
   noting installs are per-user (kimi limitation).
3. Manual exit criteria: `/plugins install` of the repo in the kimi TUI
   shows `/ll:*` commands and hooks active.

## Integration Map

### Files to Modify

- `README.md` — kimi install section

### New Files

- `kimi.plugin.json` — plugin manifest (repo root)

### Dependent Files

- `scripts/little_loops/hooks/adapters/kimi/` — shim paths referenced by the manifest (FEAT-2915)
- `docs/kimi/` — onboarding docs point at this install path (ENH-2919)

## Impact

- **Priority**: P3 — independent packaging track.
- **Effort**: XS–S — one manifest plus a README section.
- **Risk**: Low — additive; manual verification required since plugin install is TUI-driven.
- **Breaking Change**: No.

## Session Log
- `/ll:verify-issues` - 2026-07-29T20:54:15 - `7dce485a-c75c-400c-ac56-53fcf2521623.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-29T20:39:42 - `7dce485a-c75c-400c-ac56-53fcf2521623.jsonl`
- `/ll:capture-issue` - 2026-07-29T15:55:00Z - kimi-code host adapter planning session

---

**Open** | Created: 2026-07-29 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The kimi-native plugin install path provides active hooks for interactive TUI sessions only. Per BUG-2921, print mode (`kimi -p`) does not fire plugin hooks, so headless automation (`ll-auto` via `kimi -p`) still requires the config.toml managed block from `ll-init --hosts kimi-code`. The README install section in this issue's scope must carry this caveat; do not present the plugin path as replacing `ll-init` for headless use.
