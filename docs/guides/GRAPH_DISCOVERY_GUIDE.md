# Graph-Accelerated Discovery Guide

The shared contract for seeding a skill's codebase-research phase from the
`ll-code` query surface (EPIC-2575) instead of discovering everything with
open-ended Grep sweeps.

This file is the **canonical** statement of the `ll-code` seeding contract, the
safety rules, and staleness handling. Consumers keep only their own
phase-specific procedure and link here — one place to fix when the contract
moves.

## Consumers

| Skill / command | Phase | Consumer doc |
|---|---|---|
| `/ll:wire-issue` | Phase 3.6 | [`skills/wire-issue/graph-discovery-layer.md`](../../skills/wire-issue/graph-discovery-layer.md) |
| `/ll:refine-issue` | Step 3.05 | [`commands/refine-issue.md`](../../commands/refine-issue.md) § 3.05 |
| `/ll:verify-issues` | §2B.0 | [`commands/verify-issues.md`](../../commands/verify-issues.md) § B.0 |

`/ll:verify-issues` follows the same procedure and safety rules as the other two
consumers, but under a stricter local rule: it mutates issue state (verdicts,
`status`), so a graph result there may only corroborate or correct a verdict, never
originate one. `callers-of`/`references` exiting `1` ("no callers") is never
sufficient by itself to reach `RESOLVED` or `INVALID` — see § B.0 in the consumer
doc for the full statement. It also queries `defines`/`callers-of`/`references`
only; `impact-of` is out of scope there because regression detection already has a
deterministic git-history signal.

## Why the orchestrator queries, not the agents

`ll-code` is a CLI, so reaching it requires `Bash`. Agent frontmatter (`agents/*.md`)
takes bare tool *names* — it cannot express the `Bash(ll-code:*)` scoping that a
command's `allowed-tools` can. Wiring `ll-code` into `ll:codebase-locator` /
`ll:codebase-analyzer` / `ll:codebase-pattern-finder` would therefore mean granting
three read-only, document-don't-modify agents unrestricted shell.

It would also be redundant: those agents are dispatched as a parallel wave, so each
would re-probe `status`, re-derive the same symbol set, and return three
independently-deduped candidate lists.

So the **orchestrator** (the command/skill body, which already has scoped `Bash`)
runs the queries once and passes confirmed candidates *into* the agent prompts as
already-known facts. The agents then confirm and extend rather than rediscover.

## Procedure

```bash
# 1. Probe the provider (silent fallback on unavailable / error).
STATUS=$(ll-code --json status 2>/dev/null)
# available:false in STATUS, or a non-zero (exit 2) provider error → skip the
# graph phase entirely and run the consumer's normal exploratory flow.

# 2. For each change target (symbol or file) the issue names, gather candidates:
ll-code --json callers-of   <symbol>   # who calls it
ll-code --json importers-of <path>     # who imports the module
ll-code --json impact-of    <path>     # transitive impact set (tests/config/docs)

# 3. Confirm each positive hit with ONE targeted Grep at its path:line before it
#    is treated as a fact.

# 4. Hand confirmed candidates to the consumer's agent wave as seeds.
```

Query only what the provider advertises: `status.capabilities` is a list drawn from
`callers_of`, `callees_of`, `defines`, `impact_of`, `importers_of`, `references`
(underscored, unlike the hyphenated subcommand names). A subcommand outside that
list exits `2`; treat it exactly like an unavailable provider for that one query
rather than aborting the phase.

## Contract

See [`docs/reference/CLI.md` § `ll-code`](../reference/CLI.md#ll-code) — authoritative.

- `ll-code --json status` → `{provider, available, freshness, indexed_at, detail, capabilities}`.
- Query subcommands (`callers-of`/`callees-of`/`importers-of`/`defines`/`references`/`impact-of`)
  → `{provider, freshness, query, results:[{path,line,symbol,kind,confidence,provider}]}`
  where `confidence` is `"exact"|"heuristic"`.
- **Exit codes**: `0` = hits, `1` = no hits, `2` = provider error / unsupported query.
- Every query response also echoes top-level `freshness`, so a phase can gate on
  staleness without a separate `status` call.

## The three safety rules (encode verbatim)

1. **Silent fallback.** If `ll-code --json status` reports `available: false` or a
   query exits `2` (provider error / unsupported), skip the graph phase and run the
   consumer's normal exploratory flow. Zero regression when no provider exists.
2. **Confirm-before-use.** Every positive hit is a lead, not a verdict. Confirm it
   with one Grep at its `path:line` before it is written down or handed to an agent
   as an established fact.
3. **Never trust negatives.** Exit `1` ("no callers") is the negative result that is
   NEVER trusted alone — run the normal exploratory pass for that target.

## Staleness handling

If `freshness == "stale"` (an index-backed provider whose index lags the working
tree — the `codegraph` provider; the `FallbackProvider` reads the working tree
directly and is always `fresh`), treat **all** candidates as leads only and widen
confirmation to the normal exploratory flow for anything correctness-critical.

With `code_query.codegraph.auto_sync` enabled (default, ENH-2863), `stale` should be
transient rather than steady-state — the provider self-heals via `codegraph sync
--quiet` on the read that observes staleness, so a run that hits `stale` is usually
the one-time straggler before the next `status()` reports `fresh` again. It is still
observable in practice, so the widening above is a live path, not a formality.

## Provider note

Both providers are real today: `FallbackProvider` (grep/AST, no index, always
available) and `codegraph` (ENH-2613, a read-only reader over `.codegraph/codegraph.db`,
`exact` confidence, all six capabilities including `impact_of` per ENH-3092).
`--provider auto` prefers `codegraph` when its index is available.

The distinction matters when reading measurements: on `FallbackProvider` a graph
phase measures *structured-query-then-confirm vs. open-ended agent tracing*; on
`codegraph` it additionally measures index acceleration. A benchmark that does not
record which provider served it cannot tell those apart.
