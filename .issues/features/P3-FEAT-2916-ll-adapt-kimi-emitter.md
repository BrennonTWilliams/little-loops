---
id: FEAT-2916
title: ll-adapt emitter for kimi-code (atomic with HOST_COMPATIBILITY adapter row)
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

# FEAT-2916: ll-adapt emitter for kimi-code (atomic with HOST_COMPATIBILITY adapter row)

## Summary

New `scripts/little_loops/adapters/kimi.py` implementing `HostEmitter` — a
near-passthrough, since the FEAT-2911 spike verified kimi tolerates
little-loops frontmatter as-is: skills → `.kimi-code/skills/`, commands →
plain `.md`, agents → `.kimi-code/agents/*.md` with `subagents="native"` (no
degraded mode). Keyed `"kimi-code"` in both `_EMITTER_MAP` and
`HOST_CAPABILITIES`.

## Motivation

The emitter is what makes the `/ll:*` skills/commands/agents installable on
kimi via the generic EPIC-2257 tooling (`ll-adapt --host kimi-code`).
ATOMICITY: the `HOST_CAPABILITIES` entry and the Adapter Host Capabilities
row in `docs/reference/HOST_COMPATIBILITY.md` must land in the SAME commit —
`ll-verify-host-map` check 1 is bidirectional, so `ll-doctor --full` goes red
between phases otherwise.

## Implementation Steps

1. Implement `scripts/little_loops/adapters/kimi.py` (`HostEmitter`):
   skills → `.kimi-code/skills/`, commands → plain `.md`, agents →
   `.kimi-code/agents/*.md` with `subagents="native"`.
2. Add the `"kimi-code"` entry to `_EMITTER_MAP`
   (`scripts/little_loops/adapters/core.py:48-52`).
3. Add the `"kimi-code"` entry to `HOST_CAPABILITIES`
   (`scripts/little_loops/adapters/capabilities.py:64-118`) — deliberately
   suffixed, breaking the un-suffixed emitter convention (see EPIC-2910
   naming decisions).
4. Land the Adapter Host Capabilities row in
   `docs/reference/HOST_COMPATIBILITY.md` in the SAME commit as step 3.
5. Verify: `ll-adapt --host kimi-code --apply` succeeds and
   `ll-verify-host-map` stays green.

## Integration Map

### Files to Modify

- `scripts/little_loops/adapters/core.py` — `_EMITTER_MAP` entry
- `scripts/little_loops/adapters/capabilities.py` — `HOST_CAPABILITIES` entry
- `docs/reference/HOST_COMPATIBILITY.md` — Adapter Host Capabilities row (same commit as the capabilities entry)

### New Files

- `scripts/little_loops/adapters/kimi.py`

### Dependent Files

- `scripts/little_loops/cli/doctor.py` — `ll-doctor --full` runs `ll-verify-host-map`
- `docs/reference/HOST_COMPATIBILITY.md` — remaining kimi-code cells land in ENH-2919

## Impact

- **Priority**: P3 — independent of the runner critical path.
- **Effort**: S — near-passthrough emitter; spike verified format tolerance.
- **Risk**: Low — the atomicity requirement (capabilities entry + matrix row in one commit) is the main hazard.
- **Breaking Change**: No.

## Session Log
- `/ll:verify-issues` - 2026-07-29T20:54:14 - `7dce485a-c75c-400c-ac56-53fcf2521623.jsonl`
- `/ll:capture-issue` - 2026-07-29T15:55:00Z - kimi-code host adapter planning session

---

**Open** | Created: 2026-07-29 | Priority: P3
