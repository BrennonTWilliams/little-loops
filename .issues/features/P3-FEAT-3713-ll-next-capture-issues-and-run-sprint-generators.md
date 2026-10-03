---
id: FEAT-3713
type: FEAT
title: ll-next capture-issues and run-sprint generators
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:45:16Z'
parent: EPIC-3710
blocked_by:
- FEAT-3561
- FEAT-3711
---

# FEAT-3713: ll-next capture-issues and run-sprint generators

## Summary

Add capture-issues (a configured codebase scan) and run-sprint generators with pinned axes, meaningful eligibility gates, pure filesystem/config loading and FEAT-3711's shared read-only HistorySnapshot. This is the only additional dependency compared with the original split: one history reader is shared, and missing history degrades honestly. Keep the existing verb names; the capture description explicitly says it recommends a scan, not an arbitrary single-issue capture.

## Current Behavior

The core covers implement-issue, refine-issue, resolve-blocker and run-loop. Sprint directory is configurable; SprintManager's constructor creates it, and Sprint.from_dict reads the clock for a default creation date. The sprint executor builds a member-only dependency graph that drops outside prerequisites and dispatches every nonterminal declared member. Its CLI telemetry records `exit_code=0` for a normal handler return of 1, so that field does not establish success. Orchestration rows identify per-issue picks and contain no sprint name, and the temporary sprint-state file is removed after completion. Skill invocation args do not reliably record the actual historical scan scope. These sources cannot be treated as complete sprint/scan history merely because they exist.

## Expected Behavior

Recommend existing valid sprint definitions and scans with configured, existing scope when their persisted/computed evidence supports doing that work. Show concrete commands with all inputs resolved, distinguish unavailable history from never-run/never-scanned, and leave automatic acceptance unknown when exact target attribution cannot be proved. No auto-clustering, execution, directory creation, history migration or new telemetry-producing subsystem.

## Motivation

These two verbs round out real project choices, but broad scan events and per-issue orchestration outcomes must not fabricate target-specific freshness. Pinning eligibility/curves and using the shared reader makes the recommendations inspectable and repeatable.

## Proposed Solution

### Sources, identity and actions

| Verb | Source / action |
|---|---|
| run-sprint | Existing YAML in effective `config.sprints.sprints_dir`, resolved relative to the project root; one candidate per valid named definition with eligible remaining leaf issues. Emit shell argv `ll-sprint run NAME` through shlex.join. No ephemeral EPIC sprint or auto-clustering. |
| capture-issues | One candidate for the **entire configured scan scope**, using effective scan.focus_dirs and exclude_patterns. Require at least one existing eligible directory; diagnose empty/nonexistent/invalid scope. Display plain `/ll:scan-codebase` and describe its configured directories beside it. The command's `--focus` means a concern such as security, not a directory argument; do not invent a scope flag/positional argument. |

Sprint target is `sprint:NAME`; validate file stem/declared name resolves the same command target and quote it literally. Scan target_key is `scan:SCOPE_HASH`: deterministic hash of normalized project-relative directories plus exclude patterns, with readable target `project` and a separate scope description (`--explain capture-issues project` resolves the current scope). A changed scope cannot inherit freshness or explicit recommendation identity from an old scope. Keep the hash local/deterministic, not an absolute-path credential-bearing payload.

Pin scope canonicalization: normalize project-relative paths/separators and harmless `.` segments, deduplicate and sort directory entries, and canonicalize exclusions without changing their matching semantics. Equivalent scope ordering hashes identically; changing exclusions or directory meaning changes identity. Validate traversal/symlink targets against the project's declared scan boundary, and use the same scope matcher for commit counting and evidence qualification. Do not compare a textual path prefix (`src` versus `src-extra`) or use a different exclusion matcher for the history axis.

### run-sprint eligibility and scoring

- Load definitions through a pure read-only parser, **not SprintManager or an unadapted Sprint.from_dict**, and inject issue content/config/HistorySnapshot. An omitted creation date stays missing; do not read the clock to invent it. Invalid YAML/name/options, missing referenced issue, EPIC member or cycles reject that definition with a diagnostic; deduplicate repeated member IDs before denominators/waves, recording the normalization without editing the YAML.
- Remaining work means `open`/`blocked` leaves after known `done`/`cancelled` are removed. Deferred/in-progress issues remain in the global nonterminal dependency graph and continue to block edges; they are not runnable members. Because the emitted plain `ll-sprint run NAME` currently dispatches all nonterminal declared members, any declared deferred/in-progress member vetoes the candidate with a diagnostic. Do not silently score a subset while emitting a command for the whole definition. Partial `--only` recommendations are outside this slice. No remaining eligible work yields no candidate. A known active sprint/run-state match vetoes recommending a duplicate run; no history is not proof one is active or idle.
- Use the full-project graph to check each remaining member's prerequisites before constructing sprint-local waves. Any unresolved nonterminal prerequisite outside the remaining sprint members, unknown prerequisite, or relevant cycle vetoes the entire run-sprint candidate; the current executor drops outside edges, so a ready first wave cannot make a later externally blocked wave safe. Diagnose unrelated project cycles separately without rejecting an otherwise independent sprint.
- Once outside prerequisites are proven satisfied, construct waves over only the remaining sprint members with their internal edges. **Do not compute global execution waves and project them onto the sprint**: `get_execution_waves` marks every preceding global wave processed, which would invent completion of outside work. The first sprint-local wave must be nonempty and **all** its members satisfy the core's implementation status/dependency/readiness gates. Later-wave unreadiness reduces ready share and remains explicit; internal prerequisites are still pending until the executor actually completes them. Do not change ll-sprint's execution policy in this generator issue.
- Ready share denominator is distinct remaining `open`/`blocked` members; numerator is those passing all core implementation gates. Mean priority uses those same members, not terminal/deferred siblings. No divide-by-zero or priority inferred from another issue.

| Axis | Weight | Raw / bounded curve |
|---|---|---|
| ready-and-unblocked share | 0.50 | Share in `[0,1]` under the core readiness policy. |
| mean priority | 0.30 | Mean of the core bounded priority scores for remaining members; if any member priority is invalid/missing the axis stays missing, rather than averaging a selectively known subset or inventing P0. |
| time since last known run | 0.20 | `min(1, age_days / 30)` from exact qualified sprint history; missing/unparseable/future-only history stays missing. |

Qualified sprint history is `cli_events` for binary ll-sprint with verified parsed args `run NAME`, exact name, complete argument capture, no help/version/dry-run/plan-only flags and a valid completed-wrapper time derived from ts + duration_ms. This is evidence of an ended named invocation with `outcome_unknown`, not a successful or productive sprint. The current `cli_event_context` only sees exceptions, so a normally returned failure is incorrectly recorded as `exit_code=0`; do not use that zero as proof of success. Missing duration/time fields do not fabricate completion. Filtered invocations retain their arguments in provenance and cannot accept a differently scoped offer. Per-issue orchestration_runs, issue membership overlap and deleted sprint-state files cannot establish the named sprint's last run. Any future success-based qualification needs verified producer timing/version provenance; historical zeros do not become trustworthy retroactively.

### capture-issues eligibility and scoring

Pin `next.verbs.capture-issues.stale_days=14`, `activity_threshold=20` scoped commits, and `unknown_history_lookback_days=30`, with positive numeric/integer validation and keyed local merge/reset behavior. These thresholds are initial defaults, not optimized claims.

- With a verified scoped scan timestamp, recommend when its age is at least stale_days **or** scoped commits since that timestamp reach activity_threshold. If scan freshness is unknown, count scoped commits over the fixed lookback and recommend only when the activity threshold is met, labeled `scan-freshness-unknown` rather than asserting the project was never scanned. A missing DB must not permanently exclude scans in an active repository.
- Count distinct commits reachable from current HEAD at/before as_of that touch normalized scope after exclusions, once per commit across overlapping directories. Use batched git metadata, not one subprocess per directory/commit; a missing/non-git repository makes the commit axis unknown, never zero. Without either verified stale evidence or enough known activity, emit no scan candidate with an insufficient-evidence diagnostic.
- Only a scan-codebase producer that proves this exact configured scope (including exclusions) can establish last-scan freshness/automatic attribution. `capture-issue`, scan-product, a concern-limited `--focus` scan, arbitrary matching args or absence of recent events do not prove a full scoped scan. Existing unscoped skill_events remain unknown; do not infer historical config from today's settings. A completed zero-finding scan is still a scan when scope/completion is actually recorded.
- No new scan-tracking store or dispatcher in this slice. If existing telemetry cannot prove scope, the timestamp axis/automatic acceptance remains unknown; the activity-backed candidate and explicit accept still work. Tests supply both verified and unavailable evidence through the shared reader.

| Axis | Weight | Raw / bounded curve |
|---|---|---|
| scoped commits / information freshness | 0.60 | `min(1, commit_count / activity_threshold)` since verified scan, else within the explicit lookback. |
| scan age | 0.40 | `min(1, age_days / stale_days)` for a verified exact-scope scan; otherwise missing. |

### Selection, config and acceptance integration

Append canonical verbs after run-loop in order `run-sprint`, `capture-issues`. Extend generator dispatch, supported --type/explain values, default available-bucket top policy, cap settings, namespaced dedup/alternate metadata and generated output Schema fixtures. Selection algorithm remains the shared round-robin/opt-in-pressure algorithm, but its **vocabulary and configuration contract** change; do not claim selection needs no integration.

Add consumed next.verbs weights/caps/scan thresholds with complete config root/export/serialization/schema/docs wiring; hard gates retain the core's fixed policy and effective confidence thresholds. Reuse the core's positive-weight coverage, geometric floor, tri-state gates and consumer validation. History reads use FEAT-3711's deadline/backend/snapshot seam; generators do no live DB queries or writes and --no-record/explain remain write-free. No additional history schema migration.

Register a sprint adapter for the exact qualified CLI evidence above; delayed completion is usable only when available by as_of, with outcome unknown. Register a scan adapter only for proven exact-scope/completion evidence, otherwise leave it unavailable. Acceptance means a matching invocation/acknowledgement; it never proves work quality. Maintain the core action_key/target_key/action_fingerprint contract and FEAT-3711's one-evidence/one-offer attribution; reuse its shared argument parser and inspection view. Do not let capture-issue accept a scan or per-issue picks accept a sprint recommendation.

## Integration Map

### Files to Modify

- FEAT-3561 candidate/snapshot/selection vocabulary, CLI dispatch/type/explain and generated output Schema; FEAT-3711 shared read-only snapshot/producer registration.
- Pure sprint loader/validation adapters around `scripts/little_loops/sprint.py` and dependency wave helpers, with no constructor side effects or altered ll-sprint execution behavior.
- `config/{features,core,__init__}.py`, `config-schema.json`, focused generator/history/selection/consumer tests.
- `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md`, `docs/reference/API.md`.

## Program Design

### Types

- Reuse ProjectState, HistorySnapshot, AxisScore, GateResult and Candidate. Source availability and missing reasons remain typed data, not invented scores.

### Signatures

- `generate_run_sprint_candidates(state: ProjectState, history: HistorySnapshot) -> list[Candidate]` — pure, existing definitions and full-graph eligibility only.
- `generate_capture_candidates(state: ProjectState, history: HistorySnapshot) -> list[Candidate]` — configured-scope stale/activity evidence, with explicit unknown history.

### Call Path

Pure sprint-content parser using the existing Sprint/SprintOptions data model with explicit validation → full-project prerequisite checks → `DependencyGraph.get_execution_waves` over the proven self-contained remaining member graph → `generate_run_sprint_candidates` (new). Batched git scope adapter + shared history snapshot → `generate_capture_candidates` (new). Both feed core bounded axes/gates/coverage → shared bucket-order/selection → rendering/recording. Existing anchors live in `sprint.py` and `dependency_graph.py`; do not construct the side-effecting SprintManager or read the clock through Sprint.from_dict.

## Implementation Steps

1. Implement after FEAT-3561 and FEAT-3711's shared reader; pin two verbs' weights, curves, gates, scope identity and exact producer qualifications.
2. Add pure sprint/scope/commit adapters with absence/invalid/external dependency cases before wiring dispatch.
3. Extend consumed config, selection vocabulary/output Schema/explain and producer registration; keep unknown producer states explicit.
4. Run fixed-clock fixtures, no-write/backend-degradation/invocation tests and update docs.

## Scope Boundaries

- **In scope:** two generators, explicit sources/axes/gates/weights/thresholds, shared history adapters and vocabulary/config/schema/docs integration.
- **Out of scope:** auto-clustered/EPIC sprints, execute, new scan telemetry store/dispatcher, changing existing sprint/scan execution, learned thresholds, finding-backed verbs.

## Impact

- **Priority:** P3
- **Effort:** Medium — pure adapters and existing reader integration.
- **Risk:** Medium — unverifiable scope and outside-sprint dependencies; mitigated by exact identity and unknown/fail-closed diagnostics.
- **Breaking Change:** No; extends available recommendations without altering existing executors.

## Use Case

A user with a fully ready first sprint wave sees the named sprint. A project with enough recent scoped commits and no trustworthy scan history can still receive a scan suggestion, with freshness explicitly unknown instead of an invented last-scan age.

## Acceptance Criteria

- [ ] Pure generators honor configured directories/scope and never create directories, run actions, write history or migrate; absent/invalid sources produce diagnostics and no invented action.
- [ ] Sprint fixtures cover terminal/deferred/in-progress/EPIC/missing/duplicate members, relevant and unrelated cycles, external blockers/prerequisites on first and later members, nonempty fully ready member-only first wave, later-wave unreadiness and known active sprint exclusion. Deferred/in-progress declared members and any unresolved outside prerequisite veto the whole emitted plain run command; global-wave projection cannot invent prerequisite completion.
- [ ] Sprint history uses exact parsed non-dry-run ended named CLI evidence with outcome unknown; a handler returning 1 while telemetry records 0 cannot establish success. Per-issue orchestration and temporary state do not fabricate recency/acceptance, and different/truncated filters or arguments cannot match an offer.
- [ ] Capture fixtures cover empty/missing scope, verified stale/fresh/zero-finding scan, unknown history with sufficient/insufficient activity, concern-limited/unrelated events, scope/exclusion changes, overlapping directories, excluded paths and non-git state.
- [ ] Fixed weights/curves/thresholds and positive-weight coverage are pinned; config consumer/schema/export/serialization/merge/reset/error tests pass.
- [ ] Canonical order, omitted-top opportunity, caps/dedup, --type/explain/Schema and optional pressure integration cover all six verbs, including collisions between issue/loop/sprint display names.
- [ ] Producer adapters prove exact target/action or remain unavailable/unknown; explicit accept works without treating capture-issue as a scan. Shared backend/deadline/no-record behavior is preserved and no history migration is added.
- [ ] Required invocations are copyable with literal quoting/no invented scope flag; docs and `python -m pytest scripts/tests/` pass.

## Related Key Documentation

- `docs/reference/CLI.md` — sprint run, scan-codebase and next vocabulary.
- `docs/reference/CONFIGURATION.md` — sprint directory, scan scope and per-verb settings.
- `docs/reference/API.md` — shared snapshot and pure adapters.

## Review Notes

- 2026-10-03: Pre-implementation/Opus review pinned sources/curves/thresholds, made global sprint dependencies and no-side-effect loading explicit, rejected unscoped scan/per-issue sprint attribution, and added the shared-history dependency and six-verb selection wiring. Retained the taxonomy and avoided a new scan telemetry subsystem.
- 2026-10-03: Follow-up review reproduced global-wave projection inventing outside prerequisite completion and cli_event_context recording zero for a returned failure. Added full-graph preflight plus member-only waves, vetoes matching the actual unfiltered executor, a clock-free sprint parser, and outcome-unknown invocation recency. Executor/telemetry repairs remain separate from this generator slice.

## Status

**Open** | Created: 2026-10-03 | Priority: P3
