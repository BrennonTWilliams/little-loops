---
id: EPIC-2575
title: Code Knowledge Graph Adapter — Query Protocol, Providers & Skill Integration
type: EPIC
priority: P3
status: open
discovered_date: 2026-07-10
discovered_by: capture-issue
labels: [epic, code-intelligence, adapters, token-cost, cli, captured]
relates_to: [FEAT-2576, ENH-2577, ENH-2578]
---

# EPIC-2575: Code Knowledge Graph Adapter — Query Protocol, Providers & Skill Integration

## Summary

Give `/ll:` skills and `ll-*` commands an optional, pluggable way to answer structural code questions — "who calls X", "who imports Y", "what breaks if these files change" — from a pre-built code knowledge graph instead of open-ended Grep/Glob exploration. The three children cover the full path from abstraction to measured payoff: a tiny query protocol with a grep/AST fallback provider and an `ll-code` CLI surface (FEAT-2576), a provider backed by the codegraph SQLite index already sitting at `.codegraph/codegraph.db` with first-class staleness detection (ENH-2577), and a graph-first discovery phase in `/ll:wire-issue` with before/after token measurement that gates any further skill rollout (ENH-2578).

Design rules carried through all children: the protocol is shaped by the queries our skills actually ask, not by any one tool's feature set; the no-graph fallback is a first-class provider of the same protocol (never `if graph_available` branches scattered through skills); and graph answers are **discovery hints that narrow the search**, always confirmed by targeted Grep before any destructive or wiring-critical conclusion.

## Motivation

Captured 2026-07-10 from a Cowork design discussion. Discovery-heavy skills — `/ll:wire-issue` ("every caller that may break, every config key, doc section, or test that needs touching"), `/ll:find-dead-code`, `/ll:audit-architecture`, `/ll:refine-issue`, `/ll:scan-codebase` — burn agent tokens on repeated Grep/Glob rounds that a graph index answers in one cheap call. The cost compounds in autodev loops, where the same structural queries repeat for every issue against the same codebase; a shared index amortizes across the whole run. This directly serves EPIC-2456 (token cost reduction).

The ecosystem has converged on local, agent-oriented code knowledge graph tools (colbymchenry/codegraph — local SQLite, MCP-native, already indexed in this repo; GitNexus; others), but their surfaces differ wildly (SQLite vs. browser-side vs. Cypher endpoints). The repo's own `HostEmitter` protocol + lazy registry in `scripts/little_loops/adapters/core.py` (FEAT-2391) is the proven in-house pattern for exactly this shape of optional, host-parameterized integration.

The main risk is staleness, not integration: loops mutate the codebase continuously while the index is a point-in-time snapshot. A stale "no callers found" that leads `/ll:find-dead-code` to delete live code is the failure mode this epic is designed against — hence the freshness contract in FEAT-2576, staleness detection in ENH-2577, and the hints-not-verdicts rule everywhere.

## Children

- **FEAT-2576** (P3, unblocked) — `CodeQueryProvider` protocol (`callers_of`, `callees_of`, `importers_of`, `defines`, `references`, `impact_of`, `capabilities`, `status`), registry-backed resolver modeled on `adapters/core.py`, grep/AST **fallback provider** as the day-one reference implementation, and the `ll-code` CLI command skills can call via Bash allowlists.
- **ENH-2577** (P3, blocked by FEAT-2576) — codegraph provider: read-only queries against `.codegraph/codegraph.db`, capability declaration, staleness detection (index mtime vs. git HEAD + dirty files) with a configurable `strict | warn | off` policy, and a `code_query` config block.
- **ENH-2578** (P3, blocked by FEAT-2576 + ENH-2577) — `/ll:wire-issue` graph-first discovery phase (seed candidates via `ll-code`, confirm via targeted Grep, silent fallback to today's flow when no provider is fresh), plus before/after token/turn measurement on benchmark issues that decides whether `/ll:find-dead-code` and `/ll:audit-architecture` follow.

## Scope

### In scope

- The `little_loops/codequery/` protocol, registry, fallback provider, and `ll-code` CLI (FEAT-2576)
- One real graph provider: codegraph SQLite, with staleness policy and config (ENH-2577)
- One skill integration as testbed plus the measurement that justifies (or kills) wider rollout (ENH-2578)

### Out of scope

- GitNexus and other browser-first/client-side tools — poor fit for headless CLI loops; the protocol leaves room for a future provider but none is built here
- Index *building* or auto-reindex daemons — indexing stays the external tool's job; we only read and report freshness
- Rolling graph-first discovery into `/ll:find-dead-code`, `/ll:audit-architecture`, `/ll:refine-issue`, `/ll:scan-codebase` — mechanical follow-ups gated on ENH-2578's measured win
- Replacing `dependency_mapper` / `dependency_graph.py` (issue-level dependencies) — different domain; they may later *consume* `ll-code` but are untouched here

## Implementation Order

1. **FEAT-2576** first — protocol + fallback provider + CLI. Shipping the fallback as the first provider proves the abstraction with a real implementation and makes every later consumer degradation-safe by construction.
2. **ENH-2577** second — the codegraph provider slots in behind the already-stable protocol; staleness policy lands with the first provider that can actually go stale.
3. **ENH-2578** last — wire-issue integration plus measurement. Further skill rollouts are justified by measured token/turn deltas, not assumption; if the delta is a wash, the epic closes with the fallback-only protocol as a no-regression refactor.
