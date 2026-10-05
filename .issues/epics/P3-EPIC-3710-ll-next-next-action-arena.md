---
id: EPIC-3710
type: EPIC
title: 'll-next: next-action arena'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:44:30Z'
relates_to:
- FEAT-3714
- FEAT-3722
- ENH-3720
- BUG-3737
---

# EPIC-3710: ll-next: next-action arena

## Summary

Deliver `ll-next`, an advisory CLI that recommends the next project action across a fixed menu of verbs (implement, refine, resolve-blocker, run-loop, run-sprint, capture-issues) using auditable, deterministic scoring and explicit eligibility evidence. Split out of FEAT-3561 after an Opus pre-implementation review (2026-10-03), then slimmed by further Opus reviews (2026-10-04): core CLI first, then a shared read-only history reader, recommendation events with explicit acceptance and extra generators. The historical backtest was cancelled after its source audit found insufficient clean-base confirmed-manual evidence. Default output is one canonical pass, giving each available verb one opportunity without second-round padding after target dedup; capture-issues is an activity-gated singleton with freshness unknown, rather than an invented freshness score.

**Closure criterion:** `ll-next` ships for six verbs with documented gates, per-verb coverage/evidence-only behavior, unavailable-data behavior and exit codes; recommendation events and explicit acknowledgements never fabricate ignored labels and require project ownership/existing schema; the core checkpoint and six-verb command-usability checks are recorded. Ambiguous duplicate issue-source IDs fail closed for targets/prerequisites. Sprint offers require metadata/status readiness for all remaining members, with only internal dependency gates pending; liveness is unknown, and overlapping sprint/issue actions are labeled as alternatives. Sprint history distinguishes a qualified observed invocation witness from an exact latest run, disclosing incomplete coverage and optimistic witness-age scoring. History-independent modes perform no application writes; read modes disclose SQLite-managed WAL/SHM sidecars without main-DB/schema mutation. FEAT-3712's source-audit no-go supplies the permitted insufficient-evidence outcome instead of a diagnostic report. `--execute`, learned weights, LLM reranking, activity pressure/automatic attribution (FEAT-3722), scan-age/freshness telemetry and the three finding-backed verbs are out of scope.

## Impact

- **Priority:** P3 — project-wide decision support; advisory only.
- **Effort:** Large across four active slices; each independently reviewable.
- **Risk:** High — persuasive but wrong rankings from stale signals. Mitigated by lower-bounded curves, explicit missing-data states, unknown-not-ignored acceptance, and a go/pause check after the core.
- **Breaking Change:** No; existing `next-*` CLIs are untouched.

## Children

- **FEAT-3561** — `ll-next` core: advisory CLI, four generators, gates/coverage, round-robin fill (open; FEAT-3681 prerequisite is done)
- **FEAT-3721** — shared read-only `HistorySnapshot` reader, local-only (open; blocked by FEAT-3561; independent prerequisite BUG-3737 is done)
- **FEAT-3711** — recommendation events, `accept`/`feedback` explicit acceptance (open; blocked by FEAT-3561 and FEAT-3721)
- **FEAT-3712** — As-of `implement-issue` backtest diagnostic report (**cancelled**; pre-implementation source audit: no supported structured source supplies the required clean recorded base paired with confirmed-manual choice provenance; full design retained)
- **FEAT-3713** — capture-issues and run-sprint generators (open; blocked by FEAT-3561 and FEAT-3721)

## Goal

A user can ask "what should I do next?" and get a short, legible, evidence-backed list across action types, with every missing signal, veto and fallback reported rather than guessed.

## Scope

Five linked children: four open, one cancelled. The core owns the CLI/output Schema, pure snapshot/scoring (lower-bounded curves at nominal defaults, no coverage multiplier) and round-robin fill with no history access/writes; it ends with an implement-ranking comparison plus mixed-verb usefulness checkpoint. FEAT-3721 owns the shared local-only reader with a measured initial 50,000-ID work window, 200-ID range queries filtered by CLI binary, 2,000 returned-row and 64 KiB argument limits, an extensible typed-request seam and explicit 250 ms read-lock waits plus the completed ENH-3720 shared 1-second read deadline (with its nonpreemptive limits). A complete qualified witness can support the explicitly limited sprint axis despite bounded truncation; no witness/failed or unscoped reads remain missing. Relative LL_HISTORY_DB keeps the shared resolver's original-cwd semantics with a frozen absolute target and documented root/subdirectory exception. Independent prerequisite BUG-3737 repairs literal SQLite file-URI handling for existing readers; the new reader/writer consume that helper. Exact recommendation lookup/probe SQL and schema fixtures ship with FEAT-3711’s migration, not a synthetic future table in the reader slice. The events child owns the only history migration and a narrow existing-store no-ensure write seam; normal recommendations never initialize/migrate history. Extra generators reuse the reader without depending on events: sprint ranking plus an activity-only scan offer with unknown freshness, immutable definition/scope provenance and bounded streaming git evidence. ENH-3720’s read primitive is done and reused; write-deadline and remote consumer work remain outside v1.

## Related prerequisites / detached and deferred work (not children)

- **BUG-3737** (P2, done 2026-10-05) — literal SQLite file-URI repair is landed, including `little_loops.sqlite_uri.sqlite_file_uri` and both read-only backend branches. Satisfies FEAT-3721's prerequisite and supplies FEAT-3711's future `mode=rw` URI helper; consume the fix rather than implementing it again.

- **FEAT-3714** (P4, deferred) — persisted findings store for `pay-tech-debt`, `update-docs` and `meta` verbs. No persisted source exists today (`.ll/ll-doc-drift-state.json` holds only `last_check_ts`), so those generators cannot ship honestly. Detached because deferred is non-terminal and would strand the epic branch.
- **FEAT-3681** (done 2026-10-05) — scorer extraction and lazy `NextConfig` foundation are landed; prerequisite of FEAT-3561, already detached from this epic. Extend the existing utility/config APIs rather than extracting them again.
- **FEAT-3722** (P4, deferred) — `ProducerEvidence` automatic observed-acceptance attribution and opt-in activity pressure, cut from FEAT-3711 (observational, nothing to attribute yet). Full design preserved there.
- **ENH-3720** (P4, done 2026-10-04) — cross-backend strict read-deadline plumbing (`backend.py`/`libsql.py`/`hrana.py`), split from FEAT-3711. Reuse its optional read primitive now; it does not provide write deadlines or itself activate remote ll-next. v1 stays local-only.
- Decision-rule compliance gate and decisions-based historical-signal axis — deferred until decision rules carry machine-evaluable scope (today only issue-scoped structure is machine-readable).

## Implementation order

FEAT-3561 (walking-skeleton checkpoint and recorded go/pause decision for all follow-ons) → FEAT-3721 → FEAT-3711 and FEAT-3713. FEAT-3681 and BUG-3737 are done as of 2026-10-05; their dependency links remain for provenance and no longer block starting the corresponding work. The last two feature slices remain logically independent, but integrate them sequentially (or rebase the second onto the first) because both extend the CLI/config/output Schema; test both arrival orders with the same final six-verb/event contract and lossless offered-action provenance. The core owns a shared verb registry and published output-version rule, independent of history SCHEMA_VERSION. FEAT-3712's source audit already ran independently of core implementation and cancelled that slice. FEAT-3711 claims the next free history schema version at implementation time (currently 59 → 60 if still free); derive the write-readiness floor from that migration rather than hardcoding this example. ENH-3678/ENH-3679 are done and supply rebuild gating/per-lock timeout seams; readers must pass their own 250 ms timeout explicitly, and recording must avoid implicit schema setup. Deliberate initialization uses existing `ll-session migrate`; readers share the completed ENH-3720 deadline; write deadlines and remote activation need separate future scope.

Scoring/selection determinism is over captured ProjectState/HistorySnapshot evidence, including coverage; live wall-clock budgets can vary evidence availability for the same `as_of`. Loop offers explicitly bind top-level definition bytes and resolved inputs, with independently refreshed expanded assessments; fingerprint equality does not prove inherited/imported behavior equality or permit offer suppression. Explicit acknowledgement remains per recorded ID/payload. Deferred FEAT-3722 carries the stronger offer/producer source-proof prerequisite for automatic attribution.

## Review Notes

- 2026-10-04: Code/schema audit plus `/ll:advise` with Opus (confidence 0.78) corrected failing curve-factor defaults, impossible index/deadline promises, missing project ownership and source/coverage handoffs. Removed unused scan-freshness/weight machinery and producer-registration leftovers. All five original children remain linked for progress accounting; FEAT-3712 is terminally cancelled with a recorded source-contract no-go, avoiding a deferred child that would strand closure.

- 2026-10-05: Four-open-child review with Opus (confidence 0.72) corrected runtime command identity, all-member sprint readiness and unprovable liveness, capped fan-out computation, default selection/extension contracts, and exact-feedback observation semantics. Updated landed ENH-3720 usage and documented a reproduced SQLite-managed sidecar exception. Kept the four active slices; did not revive FEAT-3712 or expand to remote/automatic attribution. Opus proposed cutting sprint recency/cancelling FEAT-3721 as an optional simplification; retained their consumed local-only seam. Its proposed ready-share deletion assumed no internal pending edges, so retained that axis as the initially runnable fraction. No new child is required.

- 2026-10-05 (additional review): Source audit and `/ll:advise --signal user_requested --host claude-code --model opus` (0.76) tightened offer identity and bounded work without changing the four-feature decomposition. Corrected priority authority to filename-first without guessed P5 metadata; pinned sprint definition digest versus mutable member provenance, stored scan scope, name-based/definition-unknown sprint recency and lossless event extension handoff. Added fixed streaming git budgets with lower-bound/unknown activity semantics and rename evidence. Reproduced special-character SQLite URI wrong-file creation and captured independent prerequisite BUG-3737, wired to FEAT-3721; existing readers can be fixed before the core. Opus's sprint minimum-evidence suggestion was already covered, so retained the current rule. All open children are on-theme, none are stalled, and no additional feature child is needed; implementation still starts with the external prerequisites/core and preserves the recorded checkpoint before follow-ons.

- 2026-10-05 (identity/bounded-history review): Code-backed probes and `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.78; "CONDITIONAL GO") found the remaining material core hazard: duplicate source IDs can silently overwrite graph nodes or falsely resolve blockers via a terminal copy. Added an all-status ambiguity inventory and shared sprint-member gates. A local 10.1 GB store sample confirmed the former 2,000-ID window spans only about 7.5 hours; adopted measured bounded binary-filtered ranges and explicitly limited observed-witness sprint scoring rather than pretending to know the latest run. Kept the narrow CLI argument projection guard, cwd-relative LL_HISTORY_DB semantics and literal POSIX Git-path fixtures. Rejected a general recommendation-payload size framework and kept default gitignore behavior. All four open children remain on-theme and unstalled; no additional child, remote support or automatic attribution is required. Start FEAT-3681/core and the independent BUG-3737 prerequisite, then retain the existing maintainer checkpoint before follow-ons.

- 2026-10-05 (implementation-contract review): `/ll:advise --signal user_requested --host claude-code --model opus` returned "CONDITIONAL GO" (confidence 0.74); the focused identity consult selected an explicit top-level-only fingerprint scope (0.80). Updated completed prerequisites and current history version 59, cross-consumer config isolation, acceptance integrity, deadline/row-error classification, sprint argument grammar/options and conditional determinism. Source probes reproduced silently ignored acceptance constraints and changed imported behavior under an unchanged top-level digest. Retained the independent blocked-status veto: open internally sequenced members already exercise the pending-dependency allowance, so recorded edges do not justify waiving a blocked status. Kept all four children and the existing checkpoint; no new child is needed. The broader automatic-attribution proof was recorded only as a revival precondition in deferred FEAT-3722. Opus dissent favored cutting sprint recency if its bounded reader becomes expensive; retain the consumed seam and reassess that tradeoff at the checkpoint. No implementation or confidence rescore is claimed.

## Status

**Open** | Created: 2026-10-03 | Priority: P3
