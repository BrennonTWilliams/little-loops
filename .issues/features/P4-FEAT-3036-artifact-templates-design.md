---
id: 3036
title: Artifact templates design
type: FEAT
priority: P4
status: open
discovered_date: 2026-08-03
labels:
- planning-hub
parent: EPIC-2087
---

# FEAT-3036: Artifact templates design

Generalize the `ll-artifact policy-builder` precedent into a reusable artifact
template system. Today each artifact produced by an FSM loop is a one-off snapshot
that goes stale when its source document changes; refreshing it re-pays the
entire refinement cost. The fix is to separate presentation (paid once at
template creation) from data (cheap to refresh).

## Insight

The expensive thing the FSM loop refines is mostly **presentation and structure** —
layout, information hierarchy, styling, interactions. That part is source-independent.
The part that goes stale is the **data**. If we separate the two, we pay the
refinement cost once and the regeneration cost approaches zero.

`ll-artifact policy-builder` (a hand-built template with stamp points
`/*__GRAMMAR_SPEC_JSON__*/`, `/*__THEMED_CSS_VARS__*/`, `/*__SKILL_CATALOG_JSON__*/`
plus a deterministic render step) is the end-state in miniature. This design
generalizes that pattern so templates are user-creatable from FSM-loop outputs
instead of hand-built.

## Design principles

1. **Never lose the separation.** Artifact-producing FSM loops should emit
   template + data natively; post-hoc extraction is a second, lossier path.
2. **Keep the LLM out of the render path.** Rendering is a pure function:
   `template + data.json → artifact`. Deterministic, reproducible, testable.
3. **Templates declare a data contract.** Every template ships a manifest stating
   exactly what data it needs. Schema validation before render.
4. **Round-trip fidelity is the fitness function.** Re-render the extracted
   template with extracted data and diff against the original artifact.

## Artifact Template layout

A directory (or single bundled file, TBD) containing:

```
my-report.llat/
  manifest.yaml       # identity, data schema, source binding, render config
  template.html.j2    # Jinja2 body (or .md.j2, .svg.j2, ...)
  assets/             # optional inlined-at-render assets
```

`manifest.yaml` sketch:

```yaml
name: quarterly-risk-report
version: 1
renderer: jinja2
output: quarterly-risk-report.html
theme: design-tokens          # stamp themed CSS vars like policy-builder does
data_schema:                  # JSON Schema for data.json
  type: object
  required: [title, generated_from, sections]
  properties:
    title: {type: string}
    generated_from: {type: string}
    sections:
      type: array
      items:
        type: object
        required: [heading, body, severity]
        properties:
          heading: {type: string}
          body: {type: string}
          severity: {enum: [low, medium, high]}
source:
  path: docs/risk-register.md   # default bound source
  sha256: <hash at last render> # staleness detection
extraction:
  prompt: |                     # guidance for the LLM extraction step
    Map the risk register document to the schema. One section per
    top-level risk; severity from the "Impact" column.
```

**Template language: Jinja2, not invented.** The current `.replace()` token
scheme cannot express repeated regions or conditionals. Jinja2 is boring,
ubiquitous, sandboxable, and Python-native. `policy-builder` can migrate later
or stay as-is.

## CLI surface

```
ll-artifact render <template> [--data data.json] [-o DIR]
    Deterministic stamp. No LLM. Validates data against the schema first.

ll-artifact extract <template> <source-file> [-o data.json]
    LLM step: map source → data.json per the manifest's schema +
    extraction prompt. Fails loudly if output doesn't validate.

ll-artifact refresh <template> [<source-file>]
    extract + render in one shot, against the bound source by default.

ll-artifact status [<template> ...]
    Compare bound-source hashes to last-render hashes; report FRESH /
    STALE / SOURCE-MISSING per template. Exit non-zero if anything is
    stale (CI-hookable).

ll-artifact templatize <artifact> <source-file> [-o template-dir]
    Post-hoc extraction loop (Phase 4): produce template + data from an
    existing FSM-loop artifact, verified by round-trip fidelity.

ll-artifact policy-builder
    Existing subcommand; unchanged. Long-term it becomes a bundled
    template rendered through the same pipeline.
```

## Regeneration pipeline

```
source.md ──(extract: LLM, schema-checked)──> data.json ──(render: pure)──> artifact.html
                                                            ▲
                                              template.j2 + design tokens
```

Cost model: refinement (FSM loop) paid once at template creation; each refresh
costs one small extraction call + a string render. `render` alone (data supplied)
costs zero LLM tokens.

## Phased plan

**Phase 1 — Template format + `render`.** Manifest schema, Jinja2 renderer,
design-token stamping, `ArtifactsConfig` output-dir handling, schema validation.
Hand-author one real template (candidate: convert an existing FSM-loop HTML
artifact by hand) as the reference fixture. Pure-Python, fully unit-testable,
zero LLM.

**Phase 2 — `extract` + `refresh`.** LLM source→data mapping honoring
`extraction.prompt`, fail-closed schema validation, `refresh` composition.

**Phase 3 — Staleness: `status` + lockfile.** Source hashing at render time,
`status` reporting with CI-friendly exit codes. This is where the stated drift
problem is actually killed.

**Phase 4 — `templatize` loop + native emission.** The artifact→template FSM
loop with round-trip verification, and the `artifact_mode: template` loop-output
contract. Gnarliest part, deliberately last; Phases 1–3 deliver the drift-killing
value even if Phase 4 slips.

## Recorded decisions (2026-07-31)

### What history.db data may be embedded in a shareable artifact

**Decision: two export modes, shareable-allowlisted by default, with the mode
and allowlist user-configurable in `.ll/ll-config.json`.**

- Default export embeds only the registered shareable set. Explicit local mode
  (`ll-artifact render --local`) may embed anything for personal use.
- Every artifact is visibly stamped with the mode (and allowlist version) that
  produced it.
- Configuration lives in `.ll/ll-config.json` (`artifacts.export` block).

**Initial shareable export set:**

- `loop_runs`: `run_id`, `loop_name`, `started_at`, `ended_at`, `final_state`,
  `iterations`, `terminated_by`, `evaluator_score`, `failure_terminal`, `branch`,
  `head_sha`. Excluded: `error`, `diagnostics_path`.
- `usage_events`: `ts`, `session_id`, `model`, `state`, `input_tokens`,
  `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`,
  `cost_usd`, `provider_vendor`, `run_id`, `invocation_id`.

Everything else (prompts, corrections, message/file/tool events, issue bodies)
is excluded from shareable exports until explicitly added by config.

**Standing rules:** absolute filesystem paths never permitted in shareable
snapshots; free-text fields embeddable only in local mode.

### SQL exposure boundary for interactive artifacts

**Decision: raw SQL on the embedded snapshot; named queries only on the live bridge.**

- Browser-side ad-hoc SQL runs only against the inert sql.js snapshot, already
  filtered at export time under the shareable policy.
- The loop-fleet bridge exposes a registered named-query set (`/query?name=…`)
  and nothing else.
- Artifact queries are not guaranteed to survive the snapshot→live upgrade
  unchanged.

### Tier-2 bridge lifecycle

**Decision: both lifecycles, run-scoped as the default path.**

- `ll-loop run` / `ll-parallel` auto-start a bridge if none is listening and tear
  down only what they started. An explicitly started daemon is detected and
  reused; a run never kills a daemon it did not start.
- The sql.js dashboard implements only the run-scoped path at minimum.
- Artifacts must define the degraded state: when the expected bridge is gone,
  the artifact falls back to snapshot-only rendering with a visible "live data
  unavailable" indicator.

## Open questions

- Template packaging: directory (`.llat/`) vs. single-file bundle? Directory is
  simpler for v1; single-file travels better.
- Where do templates live? Proposal: `artifacts/templates/` under project root,
  configurable via `ArtifactsConfig`.
- Lockfile vs. writing hashes back into `manifest.yaml`? Lockfile keeps the
  manifest human-owned; leaning lockfile.
- How does `extract` invoke the LLM — through existing loop/agent machinery or
  a direct call? Reusing loop machinery buys logging/session-store integration
  for free.
- Non-HTML artifact types (images, diagrams): render step differs (e.g. SVG
  template → PNG rasterization). Manifest `renderer` field is the extension
  point; out of scope for v1.
