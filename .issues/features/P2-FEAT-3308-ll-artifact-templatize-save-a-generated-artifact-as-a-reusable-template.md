---
id: FEAT-3308
title: '`ll-artifact templatize`: save a generated artifact as a reusable template'
type: FEAT
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-23'
parent: EPIC-3299
depends_on:
- FEAT-3036
relates_to:
- FEAT-3309
- ENH-3035
labels:
- artifact
- ll-artifact
- templates
---

# FEAT-3308: `ll-artifact templatize`: save a generated artifact as a reusable template

## Summary

Split out of FEAT-3036 Phase 4. Take an existing single-file HTML artifact — the
kind `html-website-generator`, `interactive-component-generator`, `html-anything`,
`pixi-data-viz` and friends emit into `${run_dir}/index.html` — plus the source
document it was generated from, and produce a reusable artifact template: the
manifest (with a `data_schema`), the templated body, and the `data.json` that
re-renders the original. Verified by round-trip fidelity.

This is the epic's **fan-out entry point**: it is how a user who liked one
artifact gets to view a second, third and twentieth document through it without
re-running the generating FSM loop.

## Current Behavior

`templatize` exists only as a ~6-line paragraph in FEAT-3036's phased plan,
described as "the gnarliest part, deliberately last," with the parent epic
stating that Phases 1–3 "deliver the drift-killing value even if Phase 4 slips."
No code exists: `grep -rn templatize scripts/` returns nothing.

Consequently the only way to obtain a template today is to hand-author one —
manifest, schema and templated body carved by hand out of a ~100KB self-contained
HTML file. That is the exact expensive manual work the epic exists to remove, and
it is the reason artifacts from the HTML loop family stay one-off.

## Expected Behavior

```bash
ll-artifact templatize .loops/runs/html-anything/index.html docs/ARCHITECTURE.md \
    -o artifacts/templates/arch-review
```

produces a template directory that (a) validates, (b) re-renders byte-identically
(or with reviewed, intentional diffs) against the extracted `data.json`, and (c)
can then be pointed at any *other* architecture planning document via
`ll-artifact refresh`/`extract`.

## Motivation

The user-facing story the epic is for: a user generates an HTML artifact to review
one architecture planning document, finds it useful, and wants to view *all* their
architecture planning documents through it. Without `templatize`, that story has no
implementation — the generated artifact is a dead end and each additional document
costs another full FSM refinement run.

Deferring this to last inverts the epic's value: Phases 1–3 serve temporal refresh
of one bound source, which is the secondary use case (see EPIC-3299 § Use Cases).

## Proposed Solution

Three stages, each independently testable:

1. **Region discovery (LLM).** Given `artifact.html` and `source.md`, identify the
   spans of the artifact that are *derived from the source* versus the spans that
   are presentation. Emit a candidate `data_schema` plus the extracted `data.json`.
   Repeated regions (per-section cards, list rows) must be detected as arrays, not
   flattened — this is the whole reason the design chose Jinja2 over the
   `.replace()` scheme in `cli/artifact.py:132-137`.
2. **Body templating (deterministic).** Replace each discovered region with the
   corresponding Jinja2 expression/block, leaving everything else byte-identical.
3. **Round-trip verify (deterministic).** `render(template, data.json)` and diff
   against the original artifact. A non-empty diff outside a declared tolerance is
   a hard failure — the fitness function, not an advisory warning.

Failure is loud and non-destructive: on a failed round trip, write the candidate
template plus the diff to the output dir and exit non-zero, so the user can hand-fix
rather than silently receive a lossy template.

### Design-token stamp points

The HTML loops receive design tokens as **prompt text** —
`cli/loop/_helpers.py:1416-1424` seeds `context["design_tokens_context"]` via
`render_as_prompt_context`. A generated artifact therefore has token values baked in
as literal hex. The template kit (ENH-3035) stamps tokens **at render time** as CSS
variables via `render_as_css_vars_themed` (`design_tokens.py:688`).

`templatize` must reconcile the two: recognize baked literal token values in the
artifact's CSS and lift them back into stamp points, or the round trip will pass on a
template that is permanently un-themeable and drifts from every other kit artifact.
If full lifting is out of reach for v1, the command must *report* the unlifted
literals rather than silently accept them.

## Use Case

A user runs `/ll:create-loop`-generated `html-anything` over one architecture
planning document and gets a review artifact they like. They run
`ll-artifact templatize` on it, then `ll-artifact refresh` (or a batch render, see
FEAT-3309/EPIC-3299) against their other eleven planning documents,
paying one small extraction call each instead of twelve FSM refinement runs.

## Program Design

### Types

- `TemplatizeResult: {template_dir: Path, data: dict, diff: str | None, unlifted_tokens: list[str]}`

### Signatures

- `cmd_templatize(args: argparse.Namespace, logger: Logger) -> int`
- `discover_regions(artifact_html: str, source_text: str, prompt: str | None) -> tuple[dict, dict]` — returns `(data_schema, data)`
- `apply_regions(artifact_html: str, regions: dict) -> str` — deterministic body templating
- `verify_round_trip(template_dir: Path, data: dict, original: str) -> str | None` — returns a diff or None
- `lift_token_literals(css: str, tokens: DesignTokens) -> tuple[str, list[str]]`

### Call Path

`main_artifact` (`cli/artifact.py:275`) -> `cmd_templatize` -> `discover_regions`
-> `apply_regions` -> `verify_round_trip` -> `render` (FEAT-3036 Phase 1) ->
`render_as_css_vars_themed` (`design_tokens.py:688`)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact.py` — new `templatize` subparser + handler alongside `policy-builder` (`:301`) and `design-md export` (`:313`)
- `docs/reference/CLI.md` § `ll-artifact` (line ~4455) — new subcommand section

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:52,110` — `main_artifact` re-export; unchanged

### Similar Patterns
- `cmd_policy_builder` (`cli/artifact.py:98`) — the existing stamp-and-write shape
- `hitl-md.yaml:256-263`, `vega-viz.yaml:505-513` — hand-written loop states that already copy `${run_dir}/index.html` out; prior art for wanting artifacts to outlive a run

### Tests
- New test module under `scripts/tests/` (`test_artifact_templatize`) — round-trip fidelity against a checked-in fixture artifact + source pair
- `scripts/tests/test_policy_builder_emit.py` — unaffected, but the node gate (`test_policy_builder_node_gate.py`) must stay green

### Documentation
- `docs/reference/CLI.md`, `docs/ARCHITECTURE.md`

### Configuration
- `scripts/little_loops/config-schema.json` § `artifacts` (`:1870-1880`) — currently exactly one field (`default_output_dir`) with `additionalProperties: false`; a templates directory setting needs adding there before this lands

## Implementation Steps

1. Land FEAT-3036 Phase 1 (`render` + manifest format) — hard dependency.
2. Implement `apply_regions` + `verify_round_trip` deterministically, driven by a hand-written region map fixture (no LLM in the test path).
3. Implement `discover_regions` as the LLM stage, fail-closed against the emitted schema.
4. Add token-literal lifting and the unlifted-literals report.
5. Wire the subcommand, docs, and the fixture round-trip test.

## Acceptance Criteria

- [ ] `ll-artifact templatize <artifact> <source> -o <dir>` produces a template directory that `ll-artifact render` accepts.
- [ ] Round-trip: rendering the produced template with the produced `data.json` reproduces the original artifact byte-identically, or the command exits non-zero and writes the diff.
- [ ] A repeated region in the source (N sections → N cards) is templatized as a Jinja2 loop over an array, not unrolled — asserted by a test with N=2 and N=5 data.
- [ ] Baked design-token literals are lifted into stamp points, or explicitly reported as unlifted; a test asserts the report is non-silent.
- [ ] The resulting template renders correctly against a *second, different* source document of the same kind — the fan-out case, not just the round trip.
- [ ] The generating FSM loop is not invoked at any point in `templatize` or in subsequent renders.

## Impact

- **Priority**: P2 — this is the epic's user-facing entry point; the epic's stated value is not deliverable without it. Raised above the P3 dashboard-lineage children deliberately.
- **Effort**: Large — region discovery over an opaque self-contained file is the hard problem in the epic.
- **Risk**: Medium — round-trip fidelity is a hard, automatable gate, which bounds the risk of a lossy result shipping silently.
- **Breaking Change**: No — new subcommand.

## Related Key Documentation

- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design hub; read first
- `docs/reference/CLI.md` — `ll-artifact`

## Status

**Open** | Created: 2026-08-23 | Priority: P2
