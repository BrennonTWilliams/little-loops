---
id: FEAT-2263
title: omp hook-event parity audit
type: feature
status: open
priority: P4
testable: false
discovered_date: 2026-06-24
discovered_by: planning-assessment
parent: EPIC-2258
depends_on: [FEAT-1850]
labels: [host-compat, omp, hooks, parity]
relates_to: [FEAT-2261]
---

# FEAT-2263: omp hook-event parity audit

## Summary

Audit oh-my-pi's hook-event surface against the ll intent set and record which
ll intents (`pre_tool_use`, `post_tool_use`, `user_prompt_submit`, `stop`,
`session_end`, …) omp can fire natively vs. which are absent. Absorbs the intent
of the cancelled vanilla-Pi parity issue FEAT-1715, adapted to omp's richer
event model.

## Current Behavior

omp's hook-event surface has not been audited against the ll intent set. The
omp hook-intent rows in `HOST_COMPATIBILITY.md` are unpopulated/unknown, and
`hooks/adapters/omp/README.md` carries no verified parity matrix. The parity
gap is assumed to be narrower than vanilla pi-mono's (omp exposes more
lifecycle events) but this is unmeasured.

## Expected Behavior

A research doc (`thoughts/research/omp-hook-event-parity.md`) records the omp→ll
event mapping and any gaps (ll intents with no omp equivalent). The
`HOST_COMPATIBILITY.md` omp hook-intent rows are fully populated
(✓ / ✗-linked / N/A) with no unknown cells, and the
`hooks/adapters/omp/README.md` parity matrix matches the audit.

## Motivation

omp's SDK exposes more lifecycle events than vanilla pi-mono, so the parity gap
should be narrower — but it must be measured, not assumed, before
`HOST_COMPATIBILITY.md` claims any omp hook cell. This audit feeds FEAT-2261's
event mapping.

## Acceptance Criteria

- `thoughts/research/omp-hook-event-parity.md` records the omp→ll event mapping
  and any gaps (events with no omp equivalent).
- `HOST_COMPATIBILITY.md` omp hook-intent rows are populated (✓ / ✗-linked / N/A)
  — no unknown cells.
- `hooks/adapters/omp/README.md` parity matrix matches the audit (cross-check
  with FEAT-2261).

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis._

### Files to Create (Deliverables)

- `thoughts/research/omp-hook-event-parity.md` — NEW research doc recording the
  omp→ll event mapping. Model structure on `thoughts/research/gemini-cli-surface.md`:
  header block (`Status:` / `Last verified:` / `Research issue: FEAT-2263` / omp
  version pin), Q-sections each opening with a one-line **bolded finding**, an
  "Event inventory and ll intent mapping" table with columns
  `omp event | ll intent | Advisory? | Input extras | ll handler relevance`, a gaps
  list, and a closing "Capability map" code block sketching `OmpRunner`'s
  `HostCapabilities`.

### Files to Modify

- `docs/reference/HOST_COMPATIBILITY.md` — currently has **no omp column at all**
  (only Claude Code, OpenCode, Codex CLI, Gemini CLI). The audit must: (a) add an omp
  column to the `## Hook intents` table; (b) add an omp row to `## Adapter locations`;
  (c) add an `[^omp]` footnote modeled on the existing `[^gemini]` footnote (tracking
  epic EPIC-2258, research-spike FEAT-2263, artifact path, gating statement); and
  (d) add a `## Tracking issues` bullet for FEAT-2263. The existing `[^orch]` footnote
  already records that omp supersedes the frozen Pi column once `OmpRunner` lands.

### Files Validated Against (owned by FEAT-2261, not created here)

- `hooks/adapters/omp/README.md` — does **not exist yet** (FEAT-2261 creates it). This
  audit's third acceptance criterion is a *cross-check*: the README's "Event → Intent
  Mapping" parity matrix must agree with this audit. Model that README table on
  `hooks/adapters/codex/README.md` (4 columns: `event key | ll intent | Python
  invocation | Status`).

### Reference Templates (read-only)

- `thoughts/research/gemini-cli-surface.md` — structural template for the research doc
  (analogue cited in this issue's Reference section).
- `thoughts/research/hot-path-hook-intents.md` — alt research-decision doc format.
- `hooks/adapters/codex/README.md` — 4-column adapter-README parity table.
- `hooks/adapters/opencode/README.md` — alt 3-column adapter-README format.

### Source of Truth — the Complete ll Hook Intent Set

- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` and the `_USAGE`
  string enumerate the **canonical 7 ll intents** omp must be scored against (this
  issue's body lists them with a trailing "…"; these seven are the complete set):
  `session_start`, `user_prompt_submit`, `pre_tool_use`, `post_tool_use`,
  `pre_compact`, `pre_compact_handoff`, `session_end`. Note `pre_compact_handoff` is
  currently wired only on Claude Code, and only Claude Code maps `Stop` → `session_end`.
- `scripts/little_loops/hooks/types.py` — `LLHookEvent` / `LLHookResult` envelopes
  (host native event → `LLHookEvent` → handler `handle()` → `LLHookResult` → adapter
  relays stdout/stderr/exit-code). `LL_HOOK_HOST` selects the host; absent ⇒
  `claude-code`.

### Cell-Convention Note

The acceptance criteria say "✓ / ✗-linked / N/A", but the established convention in
`HOST_COMPATIBILITY.md` for a *gap with a known native event* is
`(deferred)[^omp] — `OmpEventName`` (native event named inline), not a bare `✗`.
Reserve `✗[^footnote]` for capability tables; use `(deferred)[^omp]` for hook-intent
gaps so the cell still names omp's event and the audit reads as "no current consumer"
rather than "impossible".

### Dependency / Blocker

- `depends_on: FEAT-1850` (OmpRunner) — `OmpRunner` is **not yet registered** in
  `scripts/little_loops/host_runner.py:_HOST_RUNNER_REGISTRY` (keys today:
  `claude-code`, `codex`, `opencode`, `pi`) nor in `_PROBE_ORDER`. The audit needs
  omp's native event names, which FEAT-1850's runner work surfaces. FEAT-2261 (omp
  adapter) consumes this audit's mapping; do not start until FEAT-1850 lands.

## Implementation Steps

_Added by `/ll:refine-issue` — concrete steps grounded in actual file references._

1. **Enumerate omp's native hook events** (gated on FEAT-1850). Inspect the oh-my-pi
   SDK/plugin surface for its lifecycle event names and advisory/blocking semantics,
   mirroring how `gemini-cli-surface.md` § Q2 enumerated Gemini's 11 events.
2. **Map omp events → the 7 ll intents** from
   `scripts/little_loops/hooks/__init__.py:_dispatch_table()`. For each ll intent,
   record the omp equivalent (or "none"), whether it is advisory-only vs. can block,
   and any matcher/scoping needed.
3. **Write `thoughts/research/omp-hook-event-parity.md`** following the
   `gemini-cli-surface.md` template (header block, event-inventory table, gaps list,
   `HostCapabilities` capability-map block).
4. **Add the omp column to `docs/reference/HOST_COMPATIBILITY.md` § Hook intents**
   using the cell convention above, plus the `[^omp]` footnote, the `## Adapter
   locations` row, and the `## Tracking issues` FEAT-2263 bullet. No unknown cells.
5. **Cross-check against `hooks/adapters/omp/README.md`** (created by FEAT-2261);
   reconcile any divergence with FEAT-2261 so all three artifacts agree.
6. **Verify**: zero unknown cells in the omp column; research doc, HOST_COMPATIBILITY
   matrix, and adapter README are mutually consistent.

## Reference

- FEAT-1715 (cancelled) — canonical Pi parity-audit framework to mirror.
- `thoughts/research/gemini-cli-surface.md` — analogous host-surface research doc.

## Impact

- **Effort**: S–M (research + matrix update).
- **Risk**: Low — research/docs; may surface upstream oh-my-pi gaps.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-24 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-06-26T23:06:47 - `66288c91-3410-40d5-8af7-af4d0cb1a3f8.jsonl`
- `/ll:format-issue` - 2026-06-26T22:57:21 - `ae5ff08e-cca8-4e62-8e12-44cfb2069975.jsonl`
