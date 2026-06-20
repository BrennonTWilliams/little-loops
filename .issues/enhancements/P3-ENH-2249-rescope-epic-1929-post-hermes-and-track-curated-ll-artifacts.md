---
id: ENH-2249
title: Re-scope EPIC-1929 HITL adapters post-Hermes and track curated .ll artifacts
status: done
priority: P3
type: ENH
discovered_date: 2026-06-20
completed_at: 2026-06-20 19:24:00+00:00
discovered_by: manual
parent: null
relates_to: [EPIC-1929, FEAT-1930, FEAT-1932, FEAT-2102, EPIC-2196]
labels:
  - hermes
  - hitl
  - scope
  - repo
  - gitignore
---

# ENH-2249: Re-scope EPIC-1929 HITL adapters post-Hermes and track curated .ll artifacts

## Summary

Two related pieces of backlog hygiene completed in one session, both triggered by
the Hermes integration (EPIC-2196, `done`) landing:

1. **Re-scoped EPIC-1929** (Async HITL Communication Adapter Framework) so it no
   longer builds bespoke per-channel transports that Hermes now provides.
2. **Fixed a `.gitignore` defect** that silently prevented the repo-root `.ll/`
   curated artifacts (`decisions.yaml`, the Learning Test Registry) from being
   tracked.

## Motivation

The Hermes integration treats little-loops as its execution layer and already
reaches the operator on text/Telegram/etc., consuming ll events via its webhook +
EventBus. That obsoletes the *transport-building* half of EPIC-1929 but **not** its
core: Hermes cannot pause/resume an FSM mid-run — the `human_approval` state
primitive still has to live in `executor.py`. The epic needed to be split along
that line rather than blanket-deferred or cancelled.

Separately, while logging the re-scope as formal decisions, `.ll/decisions.yaml`
turned out to be untracked — surfacing a `.gitignore` rule that swallowed the
whole repo-root `.ll/` directory.

## Work Completed

### 1. EPIC-1929 re-scope (commit `9b9c67b1`)

- **FEAT-1932** (PushNotification adapter) — **cancelled**. Bespoke push transport
  duplicates Hermes and depended on a `PushNotification` tool that never existed
  in the codebase (a hard blocker flagged in every verification pass since
  2026-06-05). Replaced by an EventBus adapter folded into FEAT-1930.
- **FEAT-2102** (adapter-swap integration test) — **deferred**. Its config-only
  swap test needs a second adapter; with push cancelled only `terminal` remains.
  Revive and retarget terminal↔eventbus once FEAT-1930's eventbus adapter lands.
- **FEAT-1930** (adapter protocol) — **re-scoped** to two adapters (`terminal` +
  `eventbus`). This resolves the issue's Open Question #2 (event-bus vs.
  file-poller) in favor of the event bus — the surface Hermes already subscribes
  to. Protocol surface (`send_alert`/`await_response`/`supports_async`) and the
  `CommunicationAdapterExtension` (Option B) decision are unchanged.
- **FEAT-1794** (`human_approval` FSM state) and **FEAT-1931** (terminal adapter)
  — kept, unchanged; the transport-agnostic core survives.
- **EPIC-1929** — added a dated re-scope note reconciling its scope/acceptance
  gates so the epic prose no longer contradicts its children.
- Logged three decisions: **SCOPE-038** (cancel FEAT-1932), **SCOPE-039** (defer
  FEAT-2102), **ARCHITECTURE-040** (re-scope FEAT-1930).
- `ll-deps validate` exits 0 — no cycles or broken refs introduced.

### 2. `.gitignore` fix for curated `.ll/` artifacts (commit `519a5e77`)

- **Root cause**: the `**/.ll/` rule (intended for nested dirs like
  `.issues/epics/.ll/`) also matched the repo-root `.ll/`, silently ignoring
  curated artifacts added after the rule. `.ll/ll-config.json` survived only by
  predating it.
- **Fix**: added `!/.ll/` to re-include the root directory. A bare
  `!.ll/decisions.yaml` cannot work — git won't re-include a file whose parent
  directory is excluded.
- Verified behavior: `decisions.yaml` + `learning-tests/` now tracked;
  `history.db`, `*.lock`, state JSON, and continue-prompt files remain
  individually ignored; nested `.issues/epics/.ll/` stays ignored.
- Committed `.ll/decisions.yaml` and the full `.ll/learning-tests/` registry
  (curated `.md` records **plus** the `raw/` proof output each record references —
  tracking `.md` alone would leave every `raw_output_path` pointer dangling).

## Acceptance Criteria

- [x] FEAT-1932 status `cancelled` with rationale in body
- [x] FEAT-2102 status `deferred` with revival plan in body
- [x] FEAT-1930 re-scoped to terminal + eventbus; Open Question #2 resolved
- [x] EPIC-1929 reconciled with a dated re-scope note
- [x] Decisions logged (SCOPE-038, SCOPE-039, ARCHITECTURE-040)
- [x] `git check-ignore` confirms `.ll/decisions.yaml` tracked, noisy files still
      ignored, nested `.ll/` still ignored
- [x] `.ll/decisions.yaml` and `.ll/learning-tests/` committed

## Files Touched

- `.issues/epics/P2-EPIC-1929-async-hitl-communication-adapter-framework.md`
- `.issues/features/P2-FEAT-1930-communication-adapter-protocol.md`
- `.issues/features/P2-FEAT-1932-push-notification-hitl-adapter.md`
- `.issues/features/P2-FEAT-2102-adapter-swap-integration-test-for-human-approval-fsm-state.md`
- `.gitignore`
- `.ll/decisions.yaml` (newly tracked), `.ll/learning-tests/` (newly tracked)

## Notes / Follow-ups

- Branch `chore/rescope-epic-1929-post-hermes` holds both commits (`9b9c67b1`,
  `519a5e77`); not yet pushed / no PR opened.
- FEAT-2102's `blocked_by` still lists the cancelled FEAT-1932 by design — kept as
  a historical record, with the cleanup (drop to `[FEAT-1930, FEAT-1931]`)
  documented in its deferral note for revival time.
- The `eventbus` adapter implied by the FEAT-1930 re-scope is not yet a tracked
  child issue — consider scoping it under EPIC-1929 when FEAT-1930 starts.

## Status

done


## Session Log
- `hook:posttooluse-status-done` - 2026-06-20T19:24:55 - `593afd0e-4957-4fc4-9c68-91c5bafdcaf2.jsonl`
