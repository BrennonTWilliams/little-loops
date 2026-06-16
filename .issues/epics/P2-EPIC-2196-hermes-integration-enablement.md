---
id: EPIC-2196
type: EPIC
priority: P2
status: open
captured_at: 2026-06-16T18:21:36Z
discovered_date: 2026-06-16
discovered_by: scope-epic
relates_to: [ENH-2197, ENH-2198, ENH-2199, ENH-2200, FEAT-1680]
labels: [hermes, integration, cli, enablement]
---

# EPIC: Hermes Integration Enablement (little-loops side)

## Summary

The little-loops-side CLI and contract gaps that the Hermes PM integration
(`PRD-Hermes-Integration-v4.md`) depends on. v4's reality check confirmed that
most of the integration's infrastructure already ships in little-loops
(`LLExtension`/`ExtensionLoader`/`wire_extensions()`, 37 event schemas, five
transports, per-state `StateConfig.model`, `--json` on `ll-loop list/status` and
`ll-issues list`). This EPIC tracks only the small, well-bounded set of enabling
gaps that remain on the little-loops side. **All Hermes-repo deliverables
(`hermes_little_loops` package, webhook endpoint, `portfolio.db`, read/action
tools, persona, rituals, slash commands) are explicitly out of scope** — they
cannot be implemented in this repo.

## Motivation

The Hermes integration treats little-loops as its execution layer, consumed via
CLI and the EventBus/extension surface. Two PRD claims that the integration's
design leans on turned out to be false against the current codebase:

1. `ll-loop run --model <id>` "passes through to the host" — **does not exist**;
   only `--llm-model` (evaluator/judge model) exists. Hermes's `ll_route`
   provider strategy is blocked without a run-level host-action model flag.
2. `ll-loop list --json --visibility public` "already handles this" — **no
   `--visibility` flag exists**; the loop-router's dispatch catalog can't filter
   to routable loops.

Shipping these enablement items unblocks Hermes Phase 1 (`ll_route`, loop-router
dispatch) without any speculative Hermes-side work landing here.

## Goal

Close the little-loops-side prerequisites so a Hermes integration built against
v4 can dispatch loops with a model preference, discover only routable loops, and
consume stable `--json` contracts — with accurate integration docs.

## Scope

**In scope (little-loops repo only):**
- `ll-loop run --model` host-action passthrough (keystone)
- `ll-loop list --visibility` inheritance-aware filter
- `--json` output contract stability for the surfaces Hermes consumes
- Integration doc corrections (event schema / transports)
- session_end hook handler — already shipped via **FEAT-1680** (`done`); linked for traceability only

**Out of scope (Hermes repo):**
- `hermes_little_loops` pip package / `LLExtension` implementation
- `POST /hermes/v1/ll-event` webhook endpoint
- `portfolio.db` and cross-project aggregation
- Read/action tools (`ll_portfolio`, `ll_briefing`, `ll_status`, `ll_events`, `ll_route`, `ll_ritual`)
- PM persona, rituals, `/setup` / `/project` / `/persona` slash commands

## Children

- **ENH-2197** — Add `ll-loop run --model` host-action passthrough flag (keystone — blocks Hermes `ll_route`)
- **ENH-2198** — Add `ll-loop list --visibility public|internal|example` inheritance-aware filter
- **ENH-2199** — Document and guarantee `--json` output contract stability for `ll-loop list/status` and `ll-issues list`
- **ENH-2200** — Fix integration docs: five transports and `SQLiteTransport` location in `EVENT-SCHEMA.md`/transport docs
- **FEAT-1680** — session_end hook handler sweeping stale cross-issue status refs (EG-4 — **already `done`**, handler is `hooks/sweep_stale_refs.py`; linked for traceability, no work remaining)

## Success Metrics

- `ll-loop run --model <id>` propagates the model to host-CLI actions for every
  state that doesn't set its own `model:`, verified by a test asserting the
  host invocation receives `--model`.
- `ll-loop list --json --visibility public` returns only runnable, public loops
  (resolving `from:` chains); `--visibility all` reveals stubs.
- `--json` schemas for `ll-loop list/status` and `ll-issues list` are documented
  and covered by snapshot tests that fail on unannounced breaking changes.
- Integration docs report the correct transport count and locations.

## Integration Map

- `scripts/little_loops/cli/loop/run.py` — `--model` arg + wiring to executor/runners
- `scripts/little_loops/fsm/runners.py` — host-action `--model` passthrough (per-state default)
- `scripts/little_loops/cli/loop/__init__.py` — `list` subcommand `--visibility` arg
- `scripts/little_loops/cli/loop/` (list/status handlers), `scripts/little_loops/cli/issues/__init__.py` — `--json` output shape
- `docs/reference/EVENT-SCHEMA.md`, transport docs — corrections
- Source PRD: `PRD-Hermes-Integration-v4.md` (§ "little-loops Enablement Gaps")

## Impact

Unblocks Hermes Phase 1. Low risk: all children are additive CLI flags, doc
guarantees, or doc corrections; no behavior change to existing loop execution
when the new flags are unset.

## Labels

hermes, integration, cli, enablement

## Status

open

## Session Log
- `/ll:scope-epic` - 2026-06-16T18:21:36Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/28e2fc45-6074-4cad-ba16-088878d2a86f.jsonl`
