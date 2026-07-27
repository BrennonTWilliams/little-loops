---
id: ENH-2836
type: ENH
priority: P2
status: open
parent: EPIC-2765
captured_at: "2026-07-27T00:08:18Z"
discovered_date: 2026-07-27
discovered_by: capture-issue
labels: [cli, doctor, docs, dx]
---

# ENH-2836: ll-check-links conflates network timeouts with broken links

## Summary

`ll-check-links` reports unreachable-due-to-network-timeout external URLs as
`Broken`, indistinguishable from genuine 404s, and exits 1 on the aggregate
count. Because `ll-doctor --full` aggregates the `ll-verify-*`/`ll-check-links`
family (FEAT-2795), a flaky or offline network turns the documented preflight
gate red for reasons that have nothing to do with the repo's correctness.

## Current Behavior

A run on 2026-07-26 produced:

```
Summary:
  Total links: 3515
  Valid: 1207
  Broken: 326
  Internal refs: 1591
  Ignored: 391
```

with individual entries reading `Error: Connection error: timed out`. Exit code
is `1` (verified directly, not inferred from a piped `$?`).

326 "broken" of 3515 is large enough that the report carries no actionable
signal: a genuinely broken link committed today would be indistinguishable from
the timeout noise. In practice the check is read as "always red, ignore it,"
which is the failure mode that makes a gate worthless.

Note the ratio: 1207 valid + 326 broken = 1533 external links attempted, so
roughly **21% of external checks fail on timeout alone**.

## Expected Behavior

Timeout / DNS / connection-refused outcomes are a distinct category from an
HTTP error response, and are reported and exit-coded separately:

- **Broken** — the host answered and said no (404, 410, 500). Fails the gate.
- **Unreachable** — no usable answer (timeout, DNS failure, connection reset).
  Reported for visibility but does **not** fail the gate by default.

Exit 1 only on the `Broken` count. Offer a flag (e.g. `--strict-network`) for
callers that genuinely want unreachable treated as failure, and consider
`--offline` / `--skip-external` to check internal refs only.

## Motivation

`ll-doctor` is documented as the preflight gate for little-loops, and
FEAT-2795 folds this command into `ll-doctor --full`. A gate that fails on
ambient network conditions trains users to ignore it — and an ignored gate
catches nothing. The repo has no hosted CI, so local gates are the *only*
enforcement layer; their signal-to-noise ratio is load-bearing.

This also interacts with the exit-code semantics FEAT-2793 settled: the
check-registry protocol splits error-tier from warn-tier severity. "Unreachable
external host" is the archetypal warn-tier result and should flow through that
split rather than hard-failing.

## Proposed Solution

1. Classify each external-link failure at the point of capture. The requests /
   urllib exception type already distinguishes these — a timeout raises a
   different exception than a 404 response, so no heuristic string-matching on
   error text is needed.
2. Add an `Unreachable: N` line to the summary, separate from `Broken: N`.
3. Gate the exit code on `Broken` only.
4. Register the check with the FEAT-2793 check-registry at **warn** severity for
   unreachable and **error** severity for broken, so `ll-doctor --full`
   inherits the split rather than reimplementing it.
5. Consider a short retry (1 retry, backoff) before classifying as unreachable,
   and a bounded per-host concurrency cap — a chunk of the 326 may be one slow
   host being hit serially until it times out.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/` link-checker module (entry point `ll-check-links`) | classify failure modes; split summary counters; gate exit code on broken-only |
| `ll-doctor --full` aggregation (FEAT-2795) | consume the severity split rather than the raw exit code |
| `scripts/tests/` | tests for each classification using a stubbed fetcher; no live network in tests |

## Implementation Steps

1. Locate the link-checker implementation behind the `ll-check-links` entry
   point and identify where external fetch exceptions are caught.
2. Introduce a `LinkOutcome` enum (`VALID`, `BROKEN`, `UNREACHABLE`, `IGNORED`).
3. Map exception types to outcomes; keep HTTP status codes on the `BROKEN` path.
4. Split the summary rendering and the exit-code computation.
5. Add `--strict-network` to restore the old behavior for callers that want it.
6. Add tests with an injected fake fetcher covering: 404 -> broken, timeout ->
   unreachable, 200 -> valid, and exit codes for each combination.
7. Re-run against the real repo and record the new broken/unreachable split.

## Impact

- **Users**: `ll-doctor --full` becomes trustworthy offline and on flaky
  networks; a red result once again means something is actually wrong.
- **Risk**: Low. Strictly a reclassification of results the command already
  produces; no change to what is fetched.
- **Effort**: Small — the exception types are already distinct at the catch
  site.
- **Backwards compatibility**: Exit code becomes *less* strict by default,
  which could mask genuinely-broken links for anyone relying on the aggregate.
  Mitigated by keeping both counts visible and offering `--strict-network`.

## Success Metrics

- With the network unavailable, `ll-check-links` exits 0 and reports all
  external links as unreachable rather than broken.
- A deliberately broken internal link still exits 1.
- `ll-doctor --full` passes on a machine with no network access.

## Scope Boundaries

**In scope**: failure classification, summary output, exit-code semantics,
optional retry/concurrency tuning.

**Out of scope**: fixing any link the checker finds genuinely broken; rewriting
the crawler; adding link checking to new file types.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | Orchestration layers and CLI surface |
| `.claude/CLAUDE.md` § Testing & CI Policy | Local gates are the only enforcement layer; no hosted CI |

## Context

Identified while verifying documentation after a CLI color-palette change. The
new `docs/development/CLI_COLOR_PALETTE.md` contains no links, yet
`ll-check-links` still reported 326 broken — all external timeouts — making it
impossible to use the command to confirm the doc was clean.

## Session Log
- `/ll:capture-issue` - 2026-07-27T00:08:18Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2c83098-37d1-4d7b-86d1-fbf55d285134.jsonl`

---

## Status

open
