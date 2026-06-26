---
id: EPIC-2257
title: Multi-host generalization — portfolio coordination
type: epic
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
decision_ref: ARCHITECTURE-048, ARCHITECTURE-049
labels: [epic, host-compat, portfolio, tracking, coordination]
relates_to: [EPIC-1463, EPIC-2178, FEAT-2274]
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
  - **FEAT-2267** — generic host-parameterized `ll-init --upgrade` surface
    refresh (per-host plugin update / adapter regeneration + gen-version
    stamping; depends on BUG-2266 for scope-aware detection).
- Tracking the per-host epics as they sequence: EPIC-1463 (Codex polish),
  EPIC-2178 (Gemini), EPIC-2258 (omp).

**Out of scope:**

- Host-specific work that genuinely cannot be parameterized (hook adapters —
  lifecycle events differ most per host; those stay per-host under each epic).
- Implementation of any individual host's runner/probe/hook adapter (owned by
  the per-host epics).

## Children

- **FEAT-2259** — Generic host-parameterized conformance harness
- **FEAT-2260** — Generic host-parameterized skill + command adapter
- **FEAT-2267** — Generic host-parameterized `ll-init --upgrade` surface refresh
  (scope-aware install detection prerequisite **BUG-2266** is done; FEAT-2267 is
  unblocked. BUG-2266 is a `relates_to` precursor, not a child of this epic.)

## Tracked sub-epics (sequenced under this epic)

- **EPIC-2279** — Wheel-self-sufficient package data + unified asset resolver
  (packages host-agnostic `templates/` / `hooks/` / `assets/` into the wheel so
  `ll-init` + section loading + the prompt hook + the Codex adapter work on every
  host via pip; owns FEAT-2274 + the BUG-2271 / BUG-2273 / BUG-2275 / BUG-2276 /
  BUG-2278 resolver fixes + ENH-2272 deploy + ENH-2277 prevention gate).

## Tracked per-host epics (sequenced under this epic)

- **EPIC-1463** — Codex CLI interop (landed; polish remaining)
- **EPIC-2178** — Gemini CLI host adapter (next full host)
- **EPIC-2258** — oh-my-pi (omp) host adapter (first-class, after Gemini)

## Acceptance Criteria

- Host order is recorded once (ARCHITECTURE-048) and every per-host epic
  references it rather than re-deriving priority.
- FEAT-2259 and FEAT-2260 land as generic components, and the bespoke
  per-host conformance / skill / command children are either folded into them
  or explicitly closed as superseded.
- `HOST_COMPATIBILITY.md` columns for every active host are driven by the
  generic conformance harness output.

## Impact

- **Priority**: P4 — coordination layer above the active host epics.
- **Effort**: Small (this epic is coordination; the work lives in children).
- **Risk**: Low — planning/consolidation, no behavioral change.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-24 | Priority: P4
