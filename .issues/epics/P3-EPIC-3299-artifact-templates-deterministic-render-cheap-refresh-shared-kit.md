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

## Use Cases

The epic serves two distinct shapes. They are named separately because they pull
sequencing in opposite directions and earlier drafts of this epic only wrote down
the second.

### A. Fan-out reuse — one template, many sources *(primary; drives sequencing)*

A user generates an HTML artifact from an FSM loop (`html-anything`,
`html-website-generator`, `interactive-component-generator`, `pixi-data-viz`, …)
to review one architecture planning document. The artifact is good — the loop paid
for that — and expensive: these artifacts are large, self-contained single files,
which also makes them costly for an agent to edit after the fact. The user saves it
as a template and then views their *other eleven* planning documents through the
same template, paying one small extraction call each instead of eleven more
refinement runs.

This is the shape the epic exists for. Its entry point is `templatize`
(**FEAT-3308**) and the loop handoff that makes a run artifact reachable at all
(**FEAT-3309**). Neither is served by staleness detection.

### B. Temporal refresh — one template, one bound source over time *(secondary)*

An artifact is bound to a source document; the source changes; the artifact goes
stale. `status` detects it and `refresh` re-extracts and re-renders. This is what
the manifest's `source: {path, sha256}` block and the Phase-3 lockfile serve.

**Sequencing rule:** where A and B compete, A wins. Phase 3 (staleness) is real
value but must not be scheduled ahead of the fan-out path; conversely, a template
must be usable against an arbitrary source, not only its bound one, and batch
rendering across a set of sources is in scope for A.

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
  `templatize` alongside the existing `policy-builder` and `design-md export`
  subcommands (now a package, `scripts/little_loops/cli/artifact/__init__.py`,
  entry point `main_artifact()` at `:66`; the `render`/`templatize`/`extract`/
  `refresh`/`status` subcommands already exist as `render.py`, `templatize.py`,
  `extract.py`, `lockfile.py`, `status.py` in that package)
- `scripts/little_loops/config/features.py:441` (`ArtifactsConfig`, now has
  `default_output_dir`, `templatize_max_input_bytes`, and `promotion_dir`) and
  `:405` (`ArtifactsExportConfig` — `mode`, `max_artifact_bytes` — FEAT-3304's
  `artifacts.export` block; it now exists, contrary to this section's earlier
  claim)
- The HTML loop family — `html-website-generator.yaml:78`,
  `html-anything.yaml:133`, `interactive-component-generator.yaml:211,399`,
  `generative-art.yaml:104`, `pixi-generative-art.yaml:108`, `pixi-data-viz.yaml`,
  `p5js-sketch-generator.yaml`, `vega-viz.yaml:262`, `hitl-md.yaml:167` — all write
  `${run_dir}/index.html` and terminate. `hitl-md.yaml:256-263` and
  `vega-viz.yaml:505-513` already hand-code a `cp` out of the run dir: prior art
  that loop authors want the handoff FEAT-3309 provides
- `cli/loop/header.py:57` (`_artifact_lines`, moved from the now-dissolved
  `cli/loop/_helpers.py`) and `fsm/persistence.py:552-598` (`archive_run`,
  copies only `summary.json`) — the runner reports artifact paths but does not
  retain artifacts
- `design_tokens.py:572` (`render_as_prompt_context`, called from
  `fsm/context_seed.py:66-73`, also moved out of the dissolved `_helpers.py`)
  — loops receive design tokens as *prompt text*, so generated artifacts have
  token values baked in as literals; the kit stamps them as CSS vars at render
  time. Two token paths that must be reconciled (FEAT-3308)

## Impact

Unblocks EPIC-2087's closure. Turns per-artifact drift from an accepted cost
into a detectable, CI-hookable state, and — the larger prize — turns every
expensive loop-generated artifact into a reusable asset instead of a one-off.

**Correction to an earlier framing:** this epic previously stated that Phases 1–3
of FEAT-3036 "deliver the drift-killing value even if phase 4 (`templatize`)
slips." That is true only for use case B. For use case A, `templatize`
(FEAT-3308) *is* the value: without it, obtaining a template means hand-carving a
manifest and Jinja2 body out of a ~100KB self-contained HTML file — the exact
manual cost this epic exists to remove. Phase 4 is no longer scheduled last.

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
- Rendering one template across a set of sources (batch/fan-out), not only
  against a single bound source
- The loop→artifact handoff: promoting a run's deliverable, and the
  `artifact_mode: template` native-emission contract

### Out of Scope

- Restyling or redesigning existing artifacts
- Any build step or runtime dependency at view time — artifacts stay
  single-file and self-contained
- The history.db write-bridge and live-query work (tracked separately); this
  epic depends on its export-policy decisions but does not deliver them
- Loop evaluation and harness-quality measurement (EPIC-2087)

## Children

Two lineages run under this epic. Keeping them distinct matters: the first four
children are all descendants of the hand-built `policy-builder` artifact, and if
they are the only ones that ship, the epic improves little-loops' internal
dashboards and leaves the loop-generated artifacts (use case A) untouched.

### Fan-out lineage — loop-generated artifacts (use case A)

- **FEAT-3308** — `ll-artifact templatize`: save a generated artifact as a
  reusable template *(split out of FEAT-3036 Phase 4; the epic's user-facing
  entry point)*
- **FEAT-3309** — Loop→artifact handoff: promote a run artifact to a durable path
  *(Part A; makes a run artifact reachable at all)*
- **FEAT-3318** — `artifact_mode: template`: loops emit template + data natively
  *(split out of FEAT-3309 as Part B on 2026-08-24; owns FEAT-3036 design
  principle 1, which was previously unowned — depends on FEAT-3309)*

### Platform / dashboard lineage — hand-built artifacts (use case B and shared plumbing)

- **FEAT-3036** — Artifact templates design *(planning hub; carries the
  four-phase plan and the 2026-07-31 recorded decisions on shareable export
  sets, the SQL exposure boundary, and bridge lifecycle)*
- **ENH-3035** — Factor a shared artifact template kit out of the
  policy-builder template
- **FEAT-2301** — Visual builder for policy-router and rubric FSM loops (UX
  shell) — **done**; the `policy-builder` template this epic generalizes, and
  the sole consumer ENH-3035 must port onto the kit
- **FEAT-3304** — Embed sql.js + filtered history.db export for queryable
  single-file artifacts — foundation-tier dashboard artifact; second consumer
  of the ENH-3035 shared template kit

FEAT-3036's Phases 1–3 are expected to decompose into further children as they
are scoped; Phase 4 is now FEAT-3308.
- **FEAT-3310** — Artifact templates: extract + refresh (Phase 2) (open)
- **FEAT-3311** — Artifact templates: status + lockfile staleness detection (Phase 3) (open)
- **ENH-3319** — Rewrite baked-in design-token literals to var() references in templatize output (open)
- **FEAT-3320** — html-anything template-mode generate prompt (artifact_mode pilot) (open)
- **ENH-3322** — Chart layer for ll-artifact dashboard query results (open)







## Success Metrics

- **A loop-generated artifact is templatized and re-rendered against a second,
  different source document with no FSM run** — the use-case-A proof. This is
  the metric the epic is graded on.
- A generated artifact is reachable after its run without the user copying a
  path out of terminal scrollback.
- Re-rendering an artifact after a source change costs one extraction call and
  a string render, with no FSM refinement loop.
- The shared kit's consumers include at least one templatized loop artifact, not
  only dashboards — otherwise the kit has been shaped by the wrong workload.
- `policy-builder` renders byte-identically (or with reviewed, intentional
  diffs) after being ported onto the kit.

## Related Key Documentation

- `docs/ARCHITECTURE.md`
- `docs/reference/CLI.md` — `ll-artifact`
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — the design
  hub; read this before scoping any child

## Verification Notes

2026-09-03 (`/ll:verify-issues`): 14/15 children done, ENH-3322 correctly
`deferred`. The `scripts/little_loops/cli/artifact.py:275` citation was
stale — that module is now a package (`cli/artifact/`); corrected to the
current entry point (`cli/artifact/__init__.py:66`, `main_artifact()`) and
noted that the `render`/`extract`/`refresh`/`status`/`templatize`
subcommands this epic scoped as goals already exist in that package.

2026-09-03 (`/ll:verify-issues`, follow-up pass): three more stale/incorrect
citations found and corrected. `cli/loop/_helpers.py:1258`/`:1416-1424` were
stale — that module was dissolved into `cli/loop/header.py`, `runner.py`,
`summary.py`, and `fsm/context_seed.py` during recent module decomposition;
`_artifact_lines` is now at `header.py:57` and `render_as_prompt_context` is
at `design_tokens.py:572` (called from `fsm/context_seed.py:66-73`). The
claim that the `artifacts.export` config block "does not exist yet" is now
**factually wrong**: `ArtifactsExportConfig` (`mode`, `max_artifact_bytes`)
exists at `config/features.py:405`, and `ArtifactsConfig` moved to `:441`
and gained two more fields (`templatize_max_input_bytes`, `promotion_dir`)
since this epic was scoped.

## Status

**Open** | Created: 2026-08-23 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-09-03T17:51:48 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:13 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
