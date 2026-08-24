---
id: FEAT-3036
title: Artifact templates design
type: FEAT
priority: P3
status: open
discovered_date: 2026-08-03
labels:
- planning-hub
parent: EPIC-3299
depends_on:
- FEAT-2301
relates_to:
- FEAT-3308
- FEAT-3309
- ENH-3035
- FEAT-3304
verify_verdict: VALID
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

**Phase 4 — `templatize` + native emission.** Split out into its own children:
**FEAT-3308** (`ll-artifact templatize`, with round-trip verification) and
**FEAT-3309** (loop→artifact handoff and the `artifact_mode: template`
loop-output contract).

**Phase ordering (revised 2026-08-23).** Phase 4 is no longer scheduled last. Per
EPIC-3299 § Use Cases, `templatize` is the entry point for the primary use case
(one template, many source documents); Phase 3's staleness detection serves the
secondary one (one bound source over time). The earlier "Phases 1–3 deliver the
value even if Phase 4 slips" framing held only for the secondary case. Phase 1
(`render`) remains a hard prerequisite for everything, including FEAT-3308.

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

### Template packaging, engine, and hash storage (decided 2026-08-23)

**Decision: a directory template (`.llat/`), Jinja2 via `SandboxedEnvironment`,
and a separate lockfile for hashes.** These three were listed as open questions
here while ENH-3035's Design Context already treated them as settled — a
contradiction `/ll:verify-issues` flagged on 2026-08-12. They are settled here,
in the hub, so ENH-3035 can extract against a fixed target and FEAT-3304's
"the kit gets extracted twice" risk is closed.

- **Packaging: directory (`.llat/`), not a single-file bundle.** Simpler for v1,
  diffable, and lets `assets/` exist without an encoding scheme. A single-file
  bundle travels better and stays a possible later addition — it is an export
  format, not the authoring format.
- **Engine: Jinja2, sandboxed.** The `.replace()` scheme in
  `cli/artifact.py:132-137` cannot express repeated regions, which FEAT-3308's
  round-trip requirement makes mandatory (N sections → N cards must be a loop,
  not unrolled). **`jinja2` is not currently a dependency** —
  `scripts/pyproject.toml:40-59` lists only pyyaml, ruamel.yaml, wcwidth,
  questionary, rich, anthropic, psutil. Per CLAUDE.md's minimize-dependencies
  rule, the pin must carry a justifying comment in the `anthropic` style. The
  only in-repo precedent for placeholder rendering is `sed`-based `{{name}}`
  substitution in `cli-anything-bootstrap.yaml:453-466`, which is not a
  substitute.
  - **Delimiters must be chosen against generated content.** Templates produced
    by FEAT-3308 are carved out of self-contained HTML containing inline JS and
    CSS; `{{`/`{%` can collide with template literals and style blocks. Fix the
    delimiter set (or a region-marker convention) as part of Phase 1, and cover
    it with a fixture that contains colliding content.
- **Hashes: lockfile, not written back into `manifest.yaml`.** Keeps the manifest
  human-owned and hand-editable; machine state lives beside it. This is the same
  split as `.ll/ll.local.md`'s machine-written `## Active Rules` section.
- **Template location: `artifacts/templates/` under the project root**,
  configurable. Blocker: `ArtifactsConfig`
  (`config/features.py:369-384`) has exactly one field, `default_output_dir`, and
  `config-schema.json:1870-1880` sets `additionalProperties: false` — the schema
  will reject a templates-dir key until it is added. Same blocker applies to the
  `artifacts.export` block the 2026-07-31 decisions above assume.

**Still open here:** how `extract` invokes the LLM (see below).

## Open questions

- How does `extract` invoke the LLM — through existing loop/agent machinery or
  a direct call? Reusing loop machinery buys logging/session-store integration
  for free.
- Non-HTML artifact types (images, diagrams): render step differs (e.g. SVG
  template → PNG rasterization). Manifest `renderer` field is the extension
  point; out of scope for v1.


## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:47 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
