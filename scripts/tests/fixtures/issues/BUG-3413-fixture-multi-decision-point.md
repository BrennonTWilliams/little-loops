---
id: BUG-9820
title: Fixture — multi-decision-point Proposed Solution (BUG-3413)
type: bug
status: open
priority: P3
decision_needed: false
---

# BUG-9820: Fixture — multi-decision-point Proposed Solution (BUG-3413)

## Summary

Golden fixture for `/ll:decide-issue` Phase 7c (BUG-3413) — four independent,
`**Decision point:**`-delimited decision points in one `## Proposed Solution`
section (the FEAT-3409 shape). Decision point 3's winning identifier,
`HistoryConfig`, must never be reported as a rejected-option leftover just
because it isn't decision point 1's winner.

## Proposed Solution

**Decision point: Malformed-manifest posture**

**Option A**: Skip malformed manifests silently.

**Option B**: Log and skip malformed manifests.

**Option C**: Fail hard on a malformed manifest.

> **Selected:** Option C — failing hard surfaces bad state early.

**Decision point: Watch strategy**

**Option A**: Poll workspace state on an interval.

**Option B**: Watch workspace state via filesystem events.

> **Selected:** Option B — polling is simpler operationally.

**Decision point: Config registration path**

**Option A**: Register `HistoryConfig` in the project config schema.

**Option B**: Register `LegacyConfig` in the project config schema.

> **Selected:** Option A — `HistoryConfig` matches the existing naming convention.

**Decision point: Manifest path key**

**Option A**: Store the manifest path under `manifest_path`.

**Option B**: Store the manifest path under `legacy_manifest_path`.

> **Selected:** Option A — `manifest_path` is the established name.

### Decision Rationale

All four decision points resolved above.

## Implementation Steps

1. Register `HistoryConfig` in the project config schema.
2. Do not fall back to `LegacyConfig` — it was rejected in decision point 3.

## Status

**Open** | Created: 2026-09-08 | Priority: P3
