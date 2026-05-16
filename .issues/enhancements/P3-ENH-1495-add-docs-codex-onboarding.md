---
id: ENH-1495
type: ENH
priority: P3
status: open
captured_at: "2026-05-16T13:04:12Z"
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
blocked_by: [FEAT-1493, FEAT-1496]
labels: [captured, codex, docs, onboarding]
testable: false
---

# ENH-1495: Add `docs/codex/` user-facing onboarding walkthrough

## Summary

The repo has `docs/claude-code/` with user-facing onboarding content for Claude Code users, but no equivalent for Codex. `docs/reference/HOST_COMPATIBILITY.md` is maintainer-oriented (a capability matrix), not a walkthrough. New Codex users have no entry-point doc explaining how to install, configure, and use little-loops with the Codex CLI.

## Current Behavior

- `docs/claude-code/` — exists, contains user-facing setup and usage guidance
- `docs/codex/` — does not exist
- `docs/reference/HOST_COMPATIBILITY.md` — capability matrix, requires reading to understand which features map across hosts; not an onboarding doc
- `hooks/adapters/codex/README.md` — adapter-internal documentation about hook shims and trust hashes; not user-facing

A Codex user has to read three different files to assemble a mental model of how to set up and run ll.

## Expected Behavior

A new `docs/codex/` directory exists with at least:

- `docs/codex/README.md` — landing page: what works, what doesn't, how to install
- `docs/codex/getting-started.md` — install steps (including `/ll:init --codex`), trust prompt walkthrough, first-run verification
- `docs/codex/usage.md` — running ll-auto/ll-parallel/ll-sprint/ll-loop under `LL_HOST_CLI=codex`, invoking skills, current limitations (no `--agent` / `--tools` translation)

Top-level `README.md` links to `docs/codex/` alongside `docs/claude-code/`.

## Motivation

Codex integration is technically present (host runner, hook adapter, skills adaptation all implemented and tested), but a new user has no obvious starting point. The audit's recommendation: "claim first-class parity" requires not just code, but discoverability. A 15-minute walkthrough doc closes the gap between "works if you know what to do" and "works if you read the README".

## Proposed Solution

1. Mirror the structure of `docs/claude-code/` (read it first to set the bar for parity)
2. Pull existing content from `hooks/adapters/codex/README.md` (the trust-hash and install-flow content) and rewrite for a user audience
3. Add a "Current Limitations" section calling out the gaps tracked by EPIC-1463 (and FEAT-1493 / FEAT-1496 once they land)
4. Link from top-level `README.md` and from `docs/reference/HOST_COMPATIBILITY.md`

## Integration Map

### Files to Create
- `docs/codex/README.md`
- `docs/codex/getting-started.md`
- `docs/codex/usage.md`

### Files to Modify
- `README.md` — add Codex entry alongside Claude Code section
- `docs/reference/HOST_COMPATIBILITY.md` — cross-link to the new user docs

### Similar Patterns
- `docs/claude-code/` — structural reference

## Implementation Steps

1. Inventory `docs/claude-code/` content to establish parity bar
2. Draft `docs/codex/README.md` lifting from `hooks/adapters/codex/README.md` and `HOST_COMPATIBILITY.md` Codex column
3. Draft `getting-started.md` covering `/ll:init --codex`, trust-prompt acceptance, smoke test
4. Draft `usage.md` covering orchestration CLIs under `LL_HOST_CLI=codex` and skill invocation
5. Add cross-links from top-level `README.md` and `HOST_COMPATIBILITY.md`
6. Run `ll-check-links` on the new pages

## Impact

- **Priority**: P3 — Visible-to-users parity item, but not blocking
- **Effort**: Small/Medium — mostly content; little code
- **Risk**: Low — Docs only
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Source of truth for what works; the new docs translate this for users |
| `.claude/CLAUDE.md` | Lists `ll-adapt-skills-for-codex` and Codex-related CLI tools |

## Labels

`enh`, `captured`, `codex`, `docs`, `onboarding`

## Status

**Open** | Created: 2026-05-16 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-16T13:04:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f112cdc-ed18-410c-85e1-0d7cc45aa863.jsonl`
