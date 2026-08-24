---
id: FEAT-3311
type: FEAT
title: 'Artifact templates: status + lockfile staleness detection (Phase 3)'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-24'
captured_at: '2026-08-24T03:57:16Z'
parent: EPIC-3299
depends_on:
- FEAT-3036
- FEAT-3310
labels:
- planning-hub
---

# FEAT-3311: Artifact templates: status + lockfile staleness detection (Phase 3)

## Summary

Phase 3 of FEAT-3036's artifact-template design: add `ll-artifact status`
(staleness detection) and its backing lockfile, so a refreshed artifact can
be checked against its source(s) without re-rendering.

## Current Behavior

`ll-artifact render` (Phase 1, FEAT-3036) and `refresh` (Phase 2, FEAT-3310)
have no way to report whether a rendered artifact is stale relative to its
source(s).

## Expected Behavior

`ll-artifact status [<template> ...]` compares recorded source hashes
(sha256, stored in a machine-written `<template>.llat.lock` sibling file
next to the template — never written into `manifest.yaml`, per FEAT-3036 §
Second-pass decisions -> *Lockfile is keyed by source path, not a scalar*)
against current source content hashes, reporting `FRESH` / `STALE` /
`SOURCE-MISSING` per `(template, source)` pair. Exits non-zero if anything is
stale (CI-friendly; per CLAUDE.md this is exercised by a pytest test that
invokes it, not a hosted CI workflow).

The lockfile is a mapping keyed by rendered source path (not a scalar), so it
can express EPIC-3299's primary use case (one template, many source
documents), not only "one template, one source over time":

```yaml
version: 1
renders:
  docs/risk-register.md: {sha256: ..., rendered_at: ..., output: ...}
```

## Use Case

A user maintains `quarterly-risk-report.llat/`, refreshed periodically
against `docs/risk-register.md` (FEAT-3036 / FEAT-3310). Before trusting the
last-rendered `quarterly-risk-report.html`, they run `ll-artifact status` in
CI to confirm nothing has drifted since the last refresh; a non-zero exit
fails the build if the register changed without a re-render.

## Program Design

### Call Path

`cmd_status` (new `cli/artifact/status.py`) reads the `<template>.llat.lock`
sibling file(s) beside each resolved template (via
`little_loops.artifact_templates.resolve_template`, unchanged from
FEAT-3036), computes current sha256 of each recorded source path, and
compares. `render`/`refresh` (FEAT-3036/FEAT-3310) gain a lockfile-write step
after a successful render — the sha256/rendered_at/output triple keyed by
source path, per § Second-pass decisions -> *Lockfile is keyed by source
path, not a scalar*.

### Tests

New coverage follows `test_codequery_codegraph.py`'s structural template for
sha256 content-hash staleness detection (temp dir + a rendered lockfile
fixture, assert on `.status()`'s FRESH/STALE/SOURCE-MISSING classification
and exit code) — the closest in-repo precedent (FEAT-3036 § Tests).

## Impact

- **Priority**: P3 — serves EPIC-3299's secondary use case (one template,
  one bound source refreshed over time); this is where the stated
  content-drift problem is actually killed.
- **Effort**: Medium
- **Risk**: Low — additive; no changes to Phase 1's render path or Phase 2's
  extract path.

## Acceptance Criteria

- [ ] `render` (and Phase 2's `refresh`) write/update a
      `<template-name>.llat.lock` sibling file recording sha256 + rendered_at
      + output per rendered source path.
- [ ] `ll-artifact status [<template> ...]` reports FRESH/STALE/SOURCE-MISSING
      per `(template, source)` pair and exits non-zero iff anything is stale.
- [ ] With no `<template>` args, `status` reports on every template
      discovered under `config.artifacts.templates_dir` that has a lockfile.
- [ ] A pytest test invokes `ll-artifact status` end-to-end (subprocess or
      direct `cmd_status` call) and asserts the non-zero exit on a stale
      source — this is the "CI gate" per CLAUDE.md's local-suite policy, not
      a hosted workflow.
- [ ] `docs/reference/CLI.md` documents `status` and the lockfile format.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-24 | Priority: P3
