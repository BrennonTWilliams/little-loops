---
id: ENH-3528
title: Read the host's authoritative token counts where exposed; estimate only where they are not
type: ENH
priority: P0
status: open
discovered_date: '2026-09-23'
labels:
- observability
- multi-host
---

# Read the host's authoritative token counts where exposed; estimate only where they are not

## Summary

An estimated token count presented in the same column, same units, and same formatting as a measured one is an accuracy claim the project does not actually hold — and token-cost is the metric this project leads with. Model measured-vs-estimated as a per-host capability rather than an implementation detail, and surface it. Where a host exposes its own authoritative token counts, read them and delete the estimator on that path. Where it does not, keep estimating and label the number as an estimate wherever it is rendered or exported. Two hosts with two strategies and no forced uniformity is the correct outcome; a single blended number that is sometimes measured and sometimes guessed is not.

## Current Behavior

`ll-ctx-stats` (`little_loops.cli.ctx_stats`) renders token figures without distinguishing measured from estimated. The `.ll/ll-context-state.json` fallback path (`_render_fallback`) prints "Estimated tokens in context" from `estimated_tokens`, and the context-pressure render is documented as "rough by design", yet both share units and formatting with figures read from host logs. `HostCapabilities` (`little_loops.host_runner`) and `HostCapabilityEntry` (`little_loops.adapters.capabilities`) carry no field describing how a host's token counts are obtained, so any measured-vs-estimated decision would have to be branched at call sites.

## Expected Behavior

Each host declares its token-count strategy (`measured` or `estimated`) in the host capability map. `ll-ctx-stats` text and JSON output label every estimated figure as an estimate and carry a per-figure `source`. Hosts that publish authoritative counts have those counts read on the log-ingestion path, with the estimator removed from that path; hosts without them keep estimating, labeled.

## Scope Boundaries

- **In scope**: capability-map field for token-count source; estimate labeling in `ll-ctx-stats` render and JSON export; reading authoritative counts for one host that exposes them; recording `source` alongside stored figures.
- **Out of scope**: improving estimator accuracy; forcing a uniform strategy across hosts; adding token counting for hosts with no log-ingestion seam; changing non-token metrics.

## Design

The capability belongs in the host capability map, not in an ad-hoc branch at each call site. It splits into two independently shippable halves, and the cheap one should not wait on the expensive one:

- **Labeling** (self-contained, no new ingestion required): mark estimated figures as estimates in `ll-ctx-stats` output and in anything that exports them. This removes the false precision immediately.
- **Reading authoritative counts** (lands on the host log-ingestion seam): parse a host that publishes its own token counts, prefer those over the estimator on that path, and record the measured/estimated source alongside the figure.

Where a host exposes authoritative counts, the estimator on that path is deleted rather than bypassed, so the two strategies stay visibly distinct.

## Acceptance Criteria

- [ ] `ll-ctx-stats` output labels estimated token figures as estimates, in every render and export path.
- [ ] The measured-vs-estimated strategy is modelled as a per-host capability in the host capability map, not branched per call site.
- [ ] For a host that exposes authoritative token counts, its counts are read and the estimator on that path is deleted.
- [ ] For a host that exposes no counts, estimation is kept and the figures remain labeled as estimates.
- [ ] Every rendered or exported token figure carries (or is traceable to) its source: measured or estimated.

## Program Design

### Types

- `TokenSource = Literal["measured", "estimated"]`
- `HostCapabilityEntry.token_source: TokenSource = "estimated"`

### Signatures

- `token_source_for(host: str) -> TokenSource` — looks up `HOST_CAPABILITIES[host].token_source`
- `_render_fallback(state: dict[str, Any], logger: Logger) -> None` — labels figures as estimates
- `_aggregate_usage_events(db_path: Path) -> dict[str, Any] | None` — includes `source` per figure

### Call Path

`main_ctx_stats` -> `_aggregate_usage_events` -> `token_source_for` -> `HOST_CAPABILITIES`

## Impact

- **Priority**: P0 - token cost is the project's lead metric; unlabeled estimates are a false accuracy claim
- **Effort**: Medium - labeling half is small; the authoritative-read half depends on the log-ingestion seam
- **Risk**: Low - additive capability field and output labels
- **Breaking Change**: No (JSON output gains a `source` key)

## Status

**Open** | Created: 2026-09-23 | Priority: P0


## Session Log
- `/ll:format-issue` - 2026-09-23T22:59:16 - `f909c28b-1081-4c2f-b215-fc2794a9d5b6.jsonl`
