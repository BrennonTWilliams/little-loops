---
id: EPIC-3299
type: EPIC
title: 'Artifact templates: deterministic render, cheap refresh, shared kit'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-23'
captured_at: '2026-08-23T06:04:55Z'
labels:
- artifact
- ll-artifact
- templates
---

# EPIC-3299: Artifact templates: deterministic render, cheap refresh, shared kit

## Summary

Artifacts produced by little-loops — the `ll-artifact policy-builder` visual
builder, the planned sql.js and loop-fleet dashboards, and anything an FSM loop
emits as HTML — are today one-off snapshots. Each is a hand-built template that
goes stale the moment its source document changes, and refreshing one re-pays
the entire LLM refinement cost. Each new one is copied from `policy-builder`
and drifts from it.

This epic makes artifacts a *system*: presentation is refined once and captured
as a reusable template, data is cheap to re-extract, and rendering is a pure,
deterministic, LLM-free function of the two.

## Motivation

This work was collected under EPIC-2087 (Loop Harness Quality & Evaluation
Tooling) on 2026-08-04 by an automated `/ll:link-epics` pass, and FEAT-2301
arrived there earlier via an unparented sweep. Neither move was a scoping
decision, and the fit is poor in both directions:

- EPIC-2087's stated goal is making loops *measurably* correct — static
  validation rules, Wilson CIs on baselines, cross-host comparison, eval-task
  generation. Artifact rendering and staleness detection serve none of it.
- EPIC-2087's own Out-of-Scope list names "UI or dashboard for loop quality
  metrics" and "Loop authoring wizard changes," which is a fair description of
  FEAT-2301.
- The consequence is that EPIC-2087 is complete against every criterion it
  states, but cannot close, and this artifact work has no epic that describes
  what it is actually trying to do.

Splitting it out gives the artifact work a scope statement of its own and lets
the phased plan already written into FEAT-3036 hang its implementation children
somewhere coherent.

## Integration Map

- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — the
  template the kit is factored out of
- `scripts/little_loops/templates/policy_builder_core.mjs` — emit/validate
  core; unchanged by the extraction
- `scripts/tests/test_policy_builder_node_gate.py` — the node conformance
  gate that must keep passing across the refactor
- `load_design_tokens` / `render_as_css_vars_themed` — existing token
  stamping, to be pulled out as its own callable unit
- `ll-artifact` CLI — gains `render`, `extract`, `refresh`, `status`,
  `templatize` alongside the existing `policy-builder` subcommand

## Impact

Unblocks EPIC-2087's closure. Turns per-artifact drift from an accepted cost
into a detectable, CI-hookable state. Phases 1–3 of FEAT-3036 deliver the
drift-killing value even if phase 4 (`templatize`) slips.

## Goal

`template + data.json → artifact` as a pure function, with a shared template
kit underneath so a second and third artifact build on one set of conventions
instead of three divergent copies of `policy-builder`.

## Scope

### In Scope

- Artifact template format: manifest, data contract, schema validation
- Deterministic render path with no LLM in it
- LLM extraction of `source → data.json` against a template's declared schema
- Staleness detection between a bound source and its last render
- A shared template kit (page shell, design-token stamping, asset inlining)
  factored out of `policy-builder` and adopted by it
- Post-hoc `templatize` of an existing artifact, verified by round-trip fidelity

### Out of Scope

- Restyling or redesigning existing artifacts
- Any build step or runtime dependency at view time — artifacts stay
  single-file and self-contained
- The history.db write-bridge and live-query work (tracked separately); this
  epic depends on its export-policy decisions but does not deliver them
- Loop evaluation and harness-quality measurement (EPIC-2087)

## Children

- **FEAT-3036** — Artifact templates design *(planning hub; carries the
  four-phase plan and the 2026-07-31 recorded decisions on shareable export
  sets, the SQL exposure boundary, and bridge lifecycle)*
- **ENH-3035** — Factor a shared artifact template kit out of the
  policy-builder template
- **FEAT-2301** — Visual builder for policy-router and rubric FSM loops (UX
  shell) — **done**; the `policy-builder` template this epic generalizes, and
  the sole consumer ENH-3035 must port onto the kit
- **FEAT-3304** — Embed sql.js + filtered history.db export for queryable
  single-file artifacts — foundation-tier dashboard artifact; first consumer
  of the ENH-3035 shared template kit

FEAT-3036's phases 1–4 are expected to decompose into further children as they
are scoped.

## Success Metrics

- A second artifact ships on the shared kit rather than a copied template.
- Re-rendering an artifact after a source change costs one extraction call and
  a string render, with no FSM refinement loop.
- `policy-builder` renders byte-identically (or with reviewed, intentional
  diffs) after being ported onto the kit.

## Related Key Documentation

- `docs/ARCHITECTURE.md`
- `docs/reference/CLI.md` — `ll-artifact`
- `.issues/features/P4-FEAT-3036-artifact-templates-design.md` — the design
  hub; read this before scoping any child

## Status

**Open** | Created: 2026-08-23 | Priority: P3
