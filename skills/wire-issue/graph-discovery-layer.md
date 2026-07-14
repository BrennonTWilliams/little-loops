# Wire-Issue: Graph-Accelerated Discovery (Phase 3.6)

Loaded by `/ll:wire-issue` Phase 3.6. Added by ENH-2578 (EPIC-2575).

## Overview

Seed Phase 4 candidates (callers, importers, impacted files) from the `ll-code`
query surface **before** the exhaustive agent tracing, then spend the remaining
budget *confirming* those candidates with one targeted Grep each — instead of
discovering them from scratch. The written output (Integration Map) is
format-identical to today; only *how* candidates are found changes. `--auto` and
`--dry-run` behavior are unchanged.

`ll-code` seeds are **hints, not verdicts.** Every candidate is confirmed at its
`path:line` before it enters the Integration Map, and negative results are never
trusted alone.

## Procedure

```bash
# 1. Probe the provider (silent fallback on unavailable / error).
STATUS=$(ll-code --json status 2>/dev/null)
# available:false in STATUS, or a non-zero (exit 2) provider error → skip this
# phase entirely and proceed with the current Phase 4 flow (zero regression).

# 2. For each planned change target (symbol or file) from the issue's
#    Implementation Steps / Files to Modify, gather candidate wiring:
ll-code --json callers-of   <symbol>   # who calls it
ll-code --json importers-of <path>     # who imports the module
ll-code --json impact-of    <path>     # transitive impact set (tests/config/docs)

# 3. Confirm each positive hit with ONE targeted Grep at its path:line before it
#    enters the Integration Map. A confirmed hit is added like any Agent 1 finding.
#
# 4. Feed confirmed candidates into Phase 4 Agent 1's "Already-known callers:" and
#    "Key symbols to trace:" slots so the agents confirm/extend rather than
#    rediscover.
```

## `ll-code` contract (see `docs/reference/CLI.md` § `ll-code`)

- `ll-code --json status` → `{provider, available, freshness, indexed_at, detail, capabilities}`.
- Query subcommands (`callers-of`/`callees-of`/`importers-of`/`defines`/`references`/`impact-of`)
  → `{provider, freshness, query, results:[{path,line,symbol,kind,confidence,provider}]}`
  where `confidence` is `"exact"|"heuristic"`.
- **Exit codes**: `0` = hits, `1` = no hits, `2` = provider error / unsupported query.
- Every query response also echoes top-level `freshness`, so this phase can gate
  on staleness without a separate `status` call.

## The three safety rules (encode verbatim)

1. **Silent fallback.** If `ll-code --json status` reports `available: false` or a
   query exits `2` (provider error / unsupported), skip the graph phase and run
   the current exploratory Phase 4 flow. Zero regression when no provider exists.
2. **Confirm-before-map.** Every positive hit is a lead, not a verdict. Confirm it
   with one Grep at its `path:line` before it enters the Integration Map.
3. **Never trust negatives.** Exit `1` ("no callers") is the negative result that
   is NEVER trusted alone — run the current exploratory pass for that target.

## Staleness handling

If `freshness == "stale"` (an index-backed provider whose index lags the working
tree — future ENH-2577 `codegraph` provider; the day-one `FallbackProvider` is
always `fresh`), treat **all** candidates as leads only and widen confirmation to
the current exploratory flow for anything wiring-critical.

## Measurement note (fallback-only caveat)

The only registered provider today is `FallbackProvider` (grep/AST), which reads
the working tree directly and is always `available: True, freshness: "fresh"`. So
"graph phase enabled" currently measures *structured-query-then-confirm vs.
open-ended agent tracing*, **not** index acceleration. Record this caveat in the
EPIC-2575 write-up so the go/no-go isn't misread; a second measurement pass may be
warranted once ENH-2577's index-backed provider lands.
