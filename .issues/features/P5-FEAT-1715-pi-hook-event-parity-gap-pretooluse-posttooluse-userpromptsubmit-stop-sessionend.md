---
id: FEAT-1715
title: Pi hook-event parity gap (PreToolUse / PostToolUse / UserPromptSubmit / Stop / SessionEnd)
type: FEAT
status: open
priority: P5
captured_at: "2026-05-26T02:06:59Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1713
relates_to: [FEAT-992, FEAT-1478]
depends_on: [FEAT-1476]
blocked_by: [FEAT-1719]
labels: [feat, captured, pi-adapter, hooks, host-compat, upstream-coordination]
---

# FEAT-1715: Pi hook-event parity gap (PreToolUse / PostToolUse / UserPromptSubmit / Stop / SessionEnd)

## Summary

Pi's extension SDK exposes only `session_start` and `session_before_compact`
events. FEAT-1478's adapter wires both; FEAT-992's acceptance table is
exhaustive at those two. Every other hook in `hooks/hooks.json` —
PreToolUse, PostToolUse, UserPromptSubmit, Stop, SessionEnd, Notification,
etc. — has no Pi equivalent. context-monitor, optimize-prompt,
duplicate-ID checks, and the rest of the lifecycle automation will
**silently fail to fire** on Pi.

This issue audits the gap, decides per-event whether to (a) request an
upstream pi-mono PR exposing the event, (b) approximate via the existing
2 events, or (c) document the gap as accepted, and tracks the resulting
work.

## Motivation

Without explicit acknowledgement of the hook-parity gap, users running
`ll:init --pi` will get a "Pi works with little-loops!" message and then
hit silent functional regressions versus Claude Code: their prompts won't
be optimized, context monitoring won't warn at the 50% threshold,
duplicate-ID hooks won't block writes. That is worse than not supporting
Pi at all because the failure mode is invisible.

Concrete current state (from FEAT-1478):

| Pi event | ll hook intent | Wired? |
|---|---|---|
| `session_start` (reason=startup) | `session_start` | ✓ FEAT-1478 |
| `session_before_compact` | `pre_compact` | ✓ FEAT-1478 |
| _(none)_ | `PreToolUse` | ✗ |
| _(none)_ | `PostToolUse` | ✗ |
| _(none)_ | `UserPromptSubmit` | ✗ |
| _(none)_ | `Stop` | ✗ |
| _(none)_ | `SessionEnd` | ✗ |
| _(none)_ | `post_compact` | ✗ |

For comparison, OpenCode's adapter wires the equivalent of all of these;
Codex deferred `pre_tool_use` / `post_tool_use` for latency reasons but
the gap is documented (EPIC-1463).

## Acceptance Criteria

- A research note (`thoughts/research/pi-hook-event-parity.md` or
  equivalent) enumerating every ll hook intent and Pi's offered event
  surface, with a per-intent decision: **wire**, **upstream PR**, or
  **document as accepted gap**
- For any "wire" decisions: a child issue (or amendment to FEAT-1478)
  that adds the wiring
- For any "upstream PR" decisions: an issue, draft PR, or recorded ask
  filed against `https://github.com/badlogic/pi-mono` with a link from
  this issue
- For any "accepted gap" decisions: a row in `docs/reference/HOST_COMPATIBILITY.md`'s
  Pi column explicitly marking that intent ✗ with a footnote citing this
  issue
- `hooks/adapters/pi/README.md` updated to enumerate the parity matrix
  so users running `ll:init --pi` know what does and doesn't fire

## Use Case

A user installs little-loops on a Pi project and types a prompt. With
this issue done, they either (a) see optimize-prompt fire as in Claude
Code (because the event was either wired or upstreamed), or (b) get a
clear up-front statement in the Pi adapter README that prompt
optimization is not available on Pi — instead of silent absence.

## Proposed Solution

### Step 1: Enumerate ll's hook intent surface

Cross-reference `hooks/hooks.json` and `scripts/little_loops/hooks/`
handler list to produce the authoritative ll hook intent list (one
column).

### Step 2: Enumerate Pi's extension event surface

Read `@earendil-works/pi-coding-agent` SDK exports and the pi-mono
README. List every event Pi can dispatch to an extension.

### Step 3: Map and decide

For each ll intent, classify Pi coverage as:

- **Direct match** — wire via additional `pi.on(...)` registrations in
  `hooks/adapters/pi/index.ts` (becomes child issue, or amends
  FEAT-1478 if FEAT-1478 not yet merged)
- **No match, upstream-worthy** — file an issue against pi-mono asking
  for the event; record the link
- **No match, accept gap** — record rationale (e.g. Pi's permission model
  removes the need; the feature is N/A under Pi's design)

### Step 4: Document the decisions

- Update `docs/reference/HOST_COMPATIBILITY.md` Pi column
- Update `hooks/adapters/pi/README.md` event-mapping table
- Create child issues for any "wire" decisions

## Integration Map

### Files to Create
- `thoughts/research/pi-hook-event-parity.md` — audit + decisions
- One child issue per "wire" decision (typed `FEAT` or `ENH`,
  `parent: FEAT-1715`)

### Files to Modify
- `hooks/adapters/pi/README.md` — event-mapping table updated with full
  parity matrix (created by FEAT-1478; this issue extends it)
- `docs/reference/HOST_COMPATIBILITY.md` — Pi column reflects the
  per-intent decisions

### Reference Files (Read-Only)
- `hooks/hooks.json` — authoritative ll hook event registration
- `scripts/little_loops/hooks/` — handler list confirms the intent enum
- `hooks/adapters/claude-code/` — full parity reference adapter
- `hooks/adapters/opencode/index.ts` — close analog (TS adapter wiring
  multiple lifecycle events)

## Out of Scope

- Actually wiring new `pi.on(...)` registrations — that happens in the
  child issues this one spawns (or as amendments to FEAT-1478 if it
  hasn't merged yet)
- Pi MCP server support (orthogonal capability gap)
- Pi permission-model reconciliation (handled separately if it warrants
  capture)

## Dependencies

- Depends informationally on FEAT-1478 / FEAT-992 for the current 2-event
  baseline being concrete (not blocking — the audit can run in parallel)
- Any "upstream PR" decisions block on pi-mono maintainer response —
  treat as a long-tail follow-up, not a release blocker

## Impact

- **Priority**: P5 — matches Pi-adapter tier; gap is acknowledged-but-not-urgent
- **Effort**: Audit is small; per-event wiring varies; upstream PRs are
  open-ended
- **Risk**: Low for the audit; medium for the implementations because
  some may need cooperation from pi-mono maintainers

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Pi column captures per-intent parity decisions |
| `docs/claude-code/write-a-hook.md` | Canonical hook intent semantics; defines what each Pi event would need to provide |

## Labels

`feat`, `pi-adapter`, `hooks`, `host-compat`, `upstream-coordination`, `captured`

## Status

**Open** | Created: 2026-05-26 | Priority: P5

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-31T21:34:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/922ffae8-14ce-45e5-a71a-02187250e8c9.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:06:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3eaac8be-eba9-48b8-a2d9-322df5114921.jsonl`
