---
id: EPIC-2257
title: "Multi-host generalization \u2014 portfolio coordination"
type: EPIC
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
decision_ref: ARCHITECTURE-048, ARCHITECTURE-049
labels:
- epic
- host-compat
- portfolio
- tracking
- coordination
relates_to:
- EPIC-1463
- EPIC-2178
- EPIC-2258
- FEAT-2274
- FEAT-2387
- FEAT-2391
- FEAT-2392
- FEAT-2393
---

# EPIC-2257: Multi-host generalization — portfolio coordination

## Summary

Umbrella epic owning the **cross-host** concerns that the per-host epics
(EPIC-1463 Codex, EPIC-2178 Gemini, EPIC-2258 omp) each kept re-deriving
independently: host **priority order** and the **shared per-host
infrastructure** (conformance suite, skill/command adapters, config probe,
init flag, project-context file).

Created from the 2026-06-24 host-generalization planning assessment
(`thoughts/audits/2026-06-24-host-generalization-planning-assessment.md`),
which found four per-host epics plus one orphan FEAT with no portfolio-level
owner — so each epic independently re-specified the same children.

## Decisions this epic ratifies

- **Host order** (ARCHITECTURE-048): Codex (landed, polish only) → Gemini
  (next full host) → omp/oh-my-pi (first-class, after Gemini). Vanilla Pi
  (pi-mono) is **cancelled** — omp supersedes it.
- **Generic, host-parameterized adapters** (ARCHITECTURE-049): the shared
  per-host children are built **once** as host-parameterized components taking
  a host arg, not N bespoke copies. Collapses ~6–8 duplicated children.

## Goal

Every supported host (Codex, Gemini, omp) reaches the same parity bar through
**shared** generic infrastructure, with the host order and the
generic-vs-bespoke decision owned in one place instead of re-litigated per
epic.

## Scope

**In scope:**

- Host priority order (owned here; per-host epics sequence under it).
- Generic shared-infrastructure issues that replace bespoke per-host children:
  - **FEAT-2259** — generic host-parameterized conformance harness
    (replaces bespoke FEAT-1721 / FEAT-1716 / FEAT-2192).
  - **FEAT-2260** — generic host-parameterized skill + command adapter
    (`--host` arg; replaces `ll-adapt-*-for-codex` duplication and
    FEAT-2188 / FEAT-2189).
  - **FEAT-2387** — generic host-parameterized `ll-init --upgrade` surface
    refresh (per-host plugin update / adapter regeneration + gen-version
    stamping; depends on BUG-2266 for scope-aware detection). The plan
    (2026-06-25) referred to this as "FEAT-2267" — when filed it received the
    real ID 2387.
- Tracking the per-host epics as they sequence: EPIC-1463 (Codex polish),
  EPIC-2178 (Gemini), EPIC-2258 (omp).

**Out of scope:**

- Host-specific work that genuinely cannot be parameterized (hook adapters —
  lifecycle events differ most per host; those stay per-host under each epic).
- Implementation of any individual host's runner/probe/hook adapter (owned by
  the per-host epics).

## Children

All three generic shared-infrastructure children are complete — the
host-parameterized infrastructure this epic owns is fully landed. Remaining
portfolio work is in the tracked per-host epics below.

- **FEAT-2259** — Generic host-parameterized conformance harness (**done**)
- **FEAT-2260** — Generic host-parameterized skill + command adapter (**done**)
- **FEAT-2387** — Generic host-parameterized `ll-init --upgrade` surface refresh
  (**done**; shipped via commits `e3180a9b` / `dd9f5dbb` on 2026-06-29 as
  `_dispatch_host_upgrade()` + `_warn_adapter_staleness()` + gen-version
  stamping in `.codex/hooks.json`). Scope-aware install-detection prerequisite
  **BUG-2266** also done. BUG-2266 is a `relates_to` precursor, not a child of
  this epic. The plan (2026-06-25) referred to this work as "FEAT-2267" — when
  filed it received the real ID 2387.

## Tracked sub-epics (sequenced under this epic)

- **EPIC-2279** — Wheel-self-sufficient package data + unified asset resolver
  (**done**, 12/12 children resolved) — packaged host-agnostic `templates/` /
  `hooks/` / `assets/` into the wheel so `ll-init` + section loading + the prompt
  hook + the Codex adapter work on every host via pip; landed FEAT-2274 + the
  BUG-2271 / BUG-2273 / BUG-2275 / BUG-2276 / BUG-2278 resolver fixes + ENH-2272
  deploy + ENH-2277 prevention gate (`ll-verify-package-data`).

## Tracked per-host epics (sequenced under this epic)

- **EPIC-1463** — Codex CLI interop (landed; polish remaining)
- **EPIC-2178** — Gemini CLI host adapter (next full host)
- **EPIC-2258** — oh-my-pi (omp) host adapter (first-class, after Gemini)

## Acceptance Criteria

- Host order is recorded once (ARCHITECTURE-048) and every per-host epic
  references it rather than re-deriving priority.
- FEAT-2259, FEAT-2260, and FEAT-2387 all landed as generic components
  (**all done**) — and the bespoke per-host conformance / skill / command
  children are either folded into them or explicitly closed as superseded
  (e.g. EPIC-2178's FEAT-2188 / FEAT-2189 / FEAT-2192, cancelled 2026-06-25).
- `HOST_COMPATIBILITY.md` columns for every active host are driven by the
  generic conformance harness output.

## Impact

- **Priority**: P4 — coordination layer above the active host epics.
- **Effort**: Small (this epic is coordination; the work lives in children).
- **Risk**: Low — planning/consolidation, no behavioral change.
- **Breaking Change**: No.

## Verification Notes

- **2026-06-26** (/ll:verify-issues): Updated Children, Tracked sub-epics prose,
  and the "FEAT-2259 and FEAT-2260 land as generic components" acceptance
  criterion to reflect that FEAT-2259 landed (`done`) and EPIC-2279 is 100%
  complete; FEAT-2260 remains pending. Cross-references/backlinks left unchanged.

- **2026-06-30** (bookkeeping refresh): FEAT-2260 (status `done`) and **FEAT-2387**
  (status `done` — note: the plan called this "FEAT-2267", but when filed it
  received the real ID 2387; updated all references in this epic accordingly
  on 2026-07-02), with prerequisite BUG-2266 `done`, had stale "pending" /
  "unblocked" prose in Children and Acceptance Criteria. Updated both — **all
  three generic shared-infrastructure children (FEAT-2259 / FEAT-2260 /
  FEAT-2387) are now complete**, so this epic's host-parameterized infrastructure
  is fully landed. Remaining portfolio work is entirely in the tracked per-host
  epics (EPIC-1463 / EPIC-2178 / EPIC-2258, all `open`); epic stays `open` as the
  coordination shell until those sequence through.

- **2026-06-30** (relationship normalization): The three tracked per-host epics
  were linked inconsistently — EPIC-1463 and EPIC-2178 via `relates_to` only,
  but EPIC-2258 additionally via `parent: EPIC-2257`. Since `ll-issues
  epic-progress` counts direct `parent:` children non-recursively, EPIC-2258 was
  being folded into this coordination epic's completion %. Removed `parent:
  EPIC-2257` from EPIC-2258 (its `relates_to` already back-links here) and added
  EPIC-2258 to this epic's `relates_to` for bidirectional symmetry with the other
  two. Per-host epics are now uniformly tracked via `relates_to` + the "Tracked
  per-host epics" prose section, not `parent:`. `epic-progress` now reports 6/6
  (100%) on the directly-owned generic children.

## Status

**Open** | Created: 2026-06-24 | Priority: P4
