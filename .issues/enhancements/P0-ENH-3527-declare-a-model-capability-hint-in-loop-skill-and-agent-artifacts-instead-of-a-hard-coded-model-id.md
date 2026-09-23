---
id: 3527
title: Declare a model capability hint in loop, skill, and agent artifacts instead of a hard-coded model id
type: ENH
priority: P0
status: open
discovered_date: '2026-09-23'
labels:
- multi-host
- loops
---

# Declare a model capability hint in loop, skill, and agent artifacts instead of a hard-coded model id

## Summary

Any artifact that names a concrete model id carries a value it cannot keep current: model ids change on a release cadence the artifacts do not track, and the id that is correct on one host is meaningless on another. Both failures show up as a loop that ran fine last month and now errors on a name. Replace the id with a capability-class hint the artifact declares — a small closed vocabulary along the lines of `coding`, `reasoning`, and `burst` — and let the host adapter resolve it to whatever that host currently offers. The artifact then states what kind of model the step needs, which is the part that is actually stable, and the mapping lives in one place per host where a rename is a single edit.

## Design

One field and one resolution step:

- Loop, skill, and agent artifacts declare a capability-class hint from a closed vocabulary — `coding` | `reasoning` | `burst` — instead of a hard-coded model id.
- The host adapter owns the hint → concrete-id mapping, one table per host, so a model rename is a single edit in one place.
- The hint is what survives: an artifact moved between hosts resolves to whatever the target host currently offers, with no artifact edit.
- Composes with the existing model-tier-by-task guidance by giving that guidance a machine-readable place to live.
- Additive: artifacts that still carry a literal model id keep working.

## Acceptance Criteria

- [ ] Loop, skill, and agent artifacts can declare a model capability hint from a closed vocabulary (`coding`, `reasoning`, `burst`).
- [ ] The host adapter resolves the hint to a concrete model id for the current host at run time.
- [ ] A model id rename requires editing exactly one mapping entry per host.
- [ ] An artifact moved between hosts resolves to the target host's current model without any artifact edit.
- [ ] Existing artifacts carrying hard-coded model ids continue to run unchanged.
