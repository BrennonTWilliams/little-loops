---
id: EPIC-3687
type: EPIC
title: 'Brainstorm engine optional capabilities: grounding, materialize, pre-mortem'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T05:35:56Z'
labels:
- loops
- brainstorm
relates_to:
- EPIC-3581
---

# EPIC-3687: Brainstorm engine optional capabilities: grounding, materialize, pre-mortem

## Summary

Deliver three optional, profile-gated capabilities for the EPIC-3581 core engine: codebase anchor validation (FEAT-3584), visual materialize/image-or-HTML judging (FEAT-3585), and annotate-only pre-mortem (FEAT-3586). ENH-3734 owns their combined verification and cumulative budget. This epic is independent of core closure after its implementation prerequisites land.

## Goal

Each optional capability works independently, degrades visibly where appropriate, preserves ranked portfolio integrity, and composes within an executable cumulative budget. Every promised closing check has a child owner.

## Scope

In scope: the three capabilities, each one's safe enablement/preset flip/routing/tests/reference run, and combined optional integration. Web evidence/reserve promotion and reframe are deferred follow-ups and **do not gate v1 closure**. Existence-only anchor checks do not certify semantic support; image codes are capability sanity signals; pre-mortem flags do not demote winners.

## Ordering and Ownership

FEAT-3584/3585/3586 depend on FEAT-3667 -> FEAT-3582 -> FEAT-3583 and remain independent of one another. Each change widens BUILT_CAPABILITIES, flips only its own target preset knobs, adds explicit routes, updates exact step/time/guard values for its cost, and records its own reference run. Grounding owns bounded discovery/probes and a whole-operation deadline before shortlisting. Materialize owns an original-shortlist snapshot, digest-only expected-code metadata, static-wrapper PNG compositing and a committed manifest reused on replay; its asset digests extend the core judging-input fingerprint. The first optional child replaces a literal max_steps==60 assertion with one derived from the built paths; later children extend it. Engine/YAML constants must change together, including the post-tournament tail when pre-mortem is enabled.

ENH-3734 runs after all three capabilities plus FEAT-3596's core evidence. It owns the eight-combination matrix, targeted filtering/fallback/skip failures, one mixed reference run and final cumulative budget. It has no reverse dependency on the core epic. No v1 reserve-promotion fixture is required while web grounding remains unbuilt.

Current executor constraints are shared across children: zero rate-limit waits require both zero retry/wait knobs **and** rate_limit_long_wait_ladder:[0]; API/infra retries still consume visits/backoff. Runner exceptions may retain old captures, so error/skip/fallback decisions need fixed route status or verified current-attempt identity. Raw captures use the core printf/:shell transport. Grounding shares bounded exact-identity indexes rooted in consuming configuration; materialize staging is bound to attempt/input/source hashes. ENH-3734 executes real deterministic engine actions with stub prompts/browser and advances the executor clock in budget fixtures. Nominal success must fit; retry-driven cap failure and outer timeout remain distinct outcomes, not guaranteed successful completion.

Materialize's existing input snapshot and the finisher's capability-gated portfolio snapshot are persisted before prompt dispatch and verified on resume/error paths; current mutated files cannot replace the original fingerprint. FEAT-3586 owns that additive portfolio publication in its enablement change, with zero additional visits and no artifact when disabled. Core fixtures disable every optional knob and ENH-3734 explicitly sets all three per case, so preset flips cannot change earlier evidence/tests.

**Provisional until the core lands (2026-10-07).** These children and ENH-3734 were hardened against unbuilt surfaces over several spec-only rounds, and EPIC-3581's spec freeze applies. Before starting any of them, reconcile it (`/ll:reconcile-issue`, `/ll:confidence-check`) against the landed core and re-evaluate its value against the core's measured results; FEAT-3585 and FEAT-3586 are the heaviest per unit of value. Cancelling an optional child is a legitimate outcome: it resolves ENH-3734's `blocked_by`, counts toward closure of this epic, and shrinks ENH-3734's matrix to 2^k over the capabilities actually built (deterministic fixtures plus one live all-on run). Budget increments follow EPIC-3581 § Budget sizing rule (one retry allowance per prompt visit; the all-retries bound is informational). Deliver serially on main (EPIC-3581 § Delivery mode and spec freeze).

## Children

- **FEAT-3584** — Brainstorm codebase grounding with bounded anchor validation (open; v1 implementation scope is codebase only; web deferred).
- **FEAT-3585** — Brainstorm materialize state: rendered mockups judged visually (open; source-valid fallback, no schedule restart).
- **FEAT-3586** — Brainstorm optional pre-mortem finisher (open; annotate-only, host failure skips annotations).
- **ENH-3734** — Brainstorm optional capability integration and cumulative budget verification (open; closes the coverage/budget ownership gap).

## Success Metrics

- Each feature enables its capability/preset/routes in the same change; no shipped profile names an unbuilt feature.
- Codebase false anchors are excluded before shortlist; unknown (including non-Git discovery and deadline exhaustion) stays visible and eligible. Symbols mentioned only in issue/runtime prose do not validate. Valid new paths are not penalized for being new.
- Visual runs never judge unauthored candidates; degraded judging uses valid sources, records image/html mode separately from its cause, and checks finalist floors before judging. A completed render manifest replays without new codes/calls; changed source/PNG inputs fail rather than corrupting committed verdicts. Digest-only code metadata improves the sanity check without claiming read isolation.
- Pre-mortem data/host failure/timeout preserves bodies, ranking, slots and sink content, flags a skip and continues. Successful annotations remain risks/kill criteria, with fatal flags visible but non-gating.
- Three individual reference runs plus ENH-3734's mixed run/actual usage/import origin are recorded; deterministic combination fixtures require no live browser/LLM.
- The mixed run enables all three capabilities and demonstrates verified grounding, image judging and successful annotations. All-unknown/degraded/skipped runs remain failure-path evidence. Optional CLI extensions are explicitly owned/tested while core disabled semantics remain compatible.
- Cumulative step/time guards include bounded retry behavior, browser deadlines, salvage, two post-tournament calls, every sink and finalization. Both loops validate and the local suite passes.
- Four children resolve to done/cancelled; deferred web/reframe work does not hold this epic open.

## Integration Map

### Files to Modify
- scripts/little_loops/brainstorm_engine.py — each optional command/report extension and capability allowlist.
- scripts/little_loops/loops/brainstorm.yaml / brainstorm-tournament.yaml — optional routing/prompt/budget changes owned by the feature adding them.
- Existing profile JSONs — only corresponding capability flips.
- scripts/tests/test_brainstorm_engine.py / test_brainstorm.py — individual and ENH-3734 combination coverage.

### Behavior Parity

| Artifact | Behavior | Disposition |
|---|---|---|
| brainstorm.yaml | Disabled capability/core paths | Preserved with zero extra visits |
| brainstorm_engine.py | Ranked portfolio/sink data | Preserved; only eligibility filtering and annotation flags are extended |
| brainstorm.yaml / engine guards | Core budget | Extended per capability and verified cumulatively by ENH-3734 |

## Impact

- **Priority**: P3 — optional value beyond the working core.
- **Effort**: Large — three capabilities and combined verification.
- **Risk**: Medium — browser and timeout/fallback interactions need measured evidence.
- **Breaking Change**: No.

## Review Notes

_2026-10-07 pre-implementation review, `/ll:advise` with claude-opus-5-5 (confidence 0.78); issue edits only:_ marked the optional children provisional until the core lands, made cancellation an explicit allowed outcome (FEAT-3586 is P4 yet gates epic closure), and replaced all-retries budget derivation with EPIC-3581's sizing rule. No capability contract changed; no new measurements.

_2026-10-05 follow-up, `/ll:advise` with Opus (confidence 0.72):_ accepted bounded/non-Git grounding, source/manifest replay and a specified stamp mechanism. Kept the existing fewer-than-two-source failure rather than the advisor's proposed text fallback; unauthored candidates remain ineligible. Grounding's deadline belongs to pre-tournament cost, and stamped-PNG/browser learning proof remains required. No new live evidence or changes to annotate-only pre-mortem were necessary.

## Composition Review

Reviewed 2026-10-06 against all four open children and the current executor, with `/ll:advise` using claude-opus-5-5 (confidence 0.74). **Disposition: KEEP.** All four children are on-theme and recently active, with individual enablement/evidence and combined coverage already owned. Grounding's bounded existence-only contract needs no new slice. Keep the independent optional order and ENH-3734 closeout; no child is missing and optional work does not block core closure.

Clarified persistent input checks for materialize/pre-mortem and the hybrid runner in combined implementation steps; FEAT-3586's effort is Medium. The advisor considered mutation-guard changes optional; persisting the already-required pre-dispatch fingerprint makes the existing promise executable across resume without new states/calls. Recompute alone would trust inputs the prompt may have changed. Browser learning proof and all live capability measurements remain pending implementation.

## Status

**Open** | Created: 2026-09-30 | Priority: P3
## Session Log
- Pre-implementation review (`/ll:advise` with claude-opus-5-5, confidence 0.78; issue edits only) - 2026-10-07
- Implementation-readiness review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.74; issue revisions only) - 2026-10-06
- Follow-up pre-implementation review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.72; no new live measurements) - 2026-10-05
- Pre-implementation review and directive reconciliation (Codex; Opus consult unavailable: advisor task budget exhausted) - 2026-10-05
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:29 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
