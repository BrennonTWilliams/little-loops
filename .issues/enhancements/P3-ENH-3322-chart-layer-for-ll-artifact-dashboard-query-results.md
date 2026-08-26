---
id: ENH-3322
type: ENH
title: Chart layer for ll-artifact dashboard query results
priority: P3
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T01:46:57Z'
parent: EPIC-3299
learning_tests_required:
  - jinja2
---

# ENH-3322: Chart layer for ll-artifact dashboard query results

## Summary

`ll-artifact dashboard` renders every query result as an HTML table and
nothing else. Add an opt-in chart layer to the packaged `dashboard.llat`
template so a result set can be drawn as a bar/line/scatter chart, with the
viz library vendored and inlined the same way `sql.js` already is — no
network, no build step, `file://`-safe.

## Current Behavior

`renderTable()` in `templates/dashboard.llat/template.html.j2` builds a
`<table>` from the stepped result rows, capped at `RENDER_ROW_CAP` (500,
`cli/artifact/dashboard.py:44`) with the true total reported alongside. The
page's `PREDEFINED` array holds two SQL views ("Loop runs by final state",
"Cost by model"). There is no charting code and no viz library vendored in the
package.

## Expected Behavior

For a result set whose shape supports it, the page offers a chart rendering
alongside the table — the user picks the chart type and which columns map to
which axis (or a predefined view declares that mapping up front) — and the
chart renders offline from the same in-memory rows. The table remains the
default and the fallback; a result set that cannot be charted says so instead
of erroring.

## Motivation

FEAT-3304 deliberately shipped a table-only page: its Scope names "A minimal
query surface in the page: run a query, render a table, and at least one
predefined view so the artifact is useful without the user writing SQL," and
its acceptance criterion asks for "at least one predefined view." That was the
right call for the foundation tier — the expensive, hard part was the
snapshot/export/redaction substrate, not the presentation.

The consequence is that the shipped dashboard reads as underwhelming relative
to its 1.9 MB: `templates/dashboard.llat/template.html.j2` is ~10 KB of page,
and almost all of the bytes are the WASM binary plus the gzipped snapshot. The
questions people actually bring to a history snapshot — cost over time, run
outcomes by state, model mix — are shape questions, and a 500-row table is a
poor answer to a shape question.

This is also the first real test of whether the ENH-3035 shared kit can carry a
second presentation concern, and EPIC-3299 names a "cost dashboard" and
"loop-fleet history explorer" as future consumers that would reuse it.

## Proposed Solution

The codebase already has two non-reconciled conventions for embedding a chart
library in a generated artifact: the vendor-and-inline pattern `sql.js`
establishes (`assets/vendor/sql.js/`, base64/text into the `data` dict, zero
network requests), and the CDN-`<script src>` pattern `loops/vega-viz.yaml`
uses to load `vega`/`vega-lite`/`vega-embed` from `cdn.jsdelivr.net` at view
time. The CDN route is incompatible with this issue's own acceptance
criterion ("offline over `file://` with no network request"), so the
vendor-and-inline route is the only one that satisfies the AC — this is a
constraint the existing AC already settles, not an open choice.

Within that constraint, whether the chosen library ships as pure UTF-8
JS (can ride through `load_assets()`'s `assets/` dir, or verbatim in `data`
like `sql_wasm_js`) or includes a WASM/binary component (must go through the
manual `data`+base64 path `sql-wasm.wasm` uses today, since `load_assets()`
has no bytes mode — `artifact_templates.py:295-308`) is a property of the
library picked, not a design decision to resolve here.

`PREDEFINED` entries are currently `{label, sql}` only
(`template.html.j2:122-132`), consumed by `buildViews()`/`runQuery()`
(`template.html.j2:230-280`) with no per-view metadata field — a view
"declaring its own chart mapping" (Implementation Step 5) requires extending
that object shape. Neither `renderTable()` nor `runQuery()` performs any
shape validation on the stepped `columns`/`rows` today — they accept any
column count/type combination unconditionally (`template.html.j2:188-266`).
The "a result set that cannot be charted says so instead of erroring" AC has
no existing groundwork to build on; the exact eligibility check (e.g. a
minimum numeric-column count) is left to the implementer — research found no
precedent for it in this codebase.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/dashboard.py` — `data` dict assembly
  (`dashboard.py:217-230`) is where any new chart-data/vendor key is added;
  size checks read the same `data`/rendered output (`dashboard.py:184-191`,
  `:244-253`)
- `scripts/little_loops/templates/dashboard.llat/template.html.j2` —
  `renderTable()` (`:188-223`), `runQuery()` (`:230-266`),
  `PREDEFINED`/`buildViews()` (`:122-132`, `:268-280`)
- `scripts/little_loops/templates/dashboard.llat/manifest.yaml` —
  `data_schema` (whole file; new required keys go here)
- `scripts/little_loops/package_data.py` — `PACKAGE_DATA_ASSETS`
  (`:82-84` is the sql.js registration block; a new vendored library needs
  its own tuples here, one per file)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/__init__.py:196` — `main_artifact` calls
  `cmd_dashboard`
- `scripts/little_loops/artifact_templates.py` — `validate_top_level_data`
  call site (`dashboard.py:233`) and `render_template` call site
  (`dashboard.py:239`) both live in `cmd_dashboard`
- `scripts/tests/test_feat3304_artifact_dashboard.py` — full existing
  dashboard test suite (row cap, `PREDEFINED` views, package-data
  registration, provenance, size ceilings, Node runtime gate)
- `scripts/tests/test_package_data_manifest.py` — `PACKAGE_DATA_ASSETS`
  completeness/no-duplicates checks

### Conventions in Force
- Third-party binaries vendor under `assets/vendor/<pkg>/` with a sibling
  `PROVENANCE.md` (version/source/SHA-256/license/update-procedure tables) —
  evidence: `assets/vendor/sql.js/PROVENANCE.md`
- Every vendored/template file is registered as one tuple per file in
  `PACKAGE_DATA_ASSETS` — no directory-glob form exists — evidence:
  `package_data.py:79` (comment stating the rule), `:82-84`; enforced by the
  set-equality check `test_every_template_and_vendor_file_is_registered_in_package_data`
  (`test_feat3304_artifact_dashboard.py:544-557`)
- `validate_top_level_data()` must run before `render_template()` — enforced
  by a source-order assertion, `test_data_payload_is_validated_before_rendering`
  (`test_feat3304_artifact_dashboard.py:571-580`)
- Every `[[= key =]]` placeholder added to `template.html.j2` must have a
  matching `data_schema` property — enforced by
  `test_template_body_avoids_jinja_delimiters_in_inline_js`
  (`test_feat3304_artifact_dashboard.py:596-607`)
- A vendored JS glue blob inlined into an inline `<script>` tag must not
  contain a literal `</script>` substring — enforced by
  `test_glue_contains_no_literal_closing_script_tag`
  (`test_feat3304_artifact_dashboard.py:616`); the same risk applies to any
  new vendored chart library inlined the same way

### Tests
- `scripts/tests/test_feat3304_artifact_dashboard.py` — existing coverage to
  extend (classes: `TestSizeCeilings`, `TestVendoredSqlJs`,
  `TestTemplatePipeline`, `TestDashboardNodeRuntimeGate`, etc.)
- `scripts/tests/test_package_data_manifest.py` — registry completeness
- `scripts/tests/js/feat3304/feat3304_dashboard_runtime.test.mjs` — Node
  `--test` runtime gate exercising the generated page's actual JS engine
  behavior (skips gracefully without Node ≥ 22)
- `scripts/tests/test_wheel_smoke.py` — installed-wheel smoke test; a grep
  for `dashboard`/`sql.js`/`vendor` found no matches, so the AC "renders from
  an installed wheel, not only a source checkout" currently has no test
  coverage anywhere to extend — this AC needs new test coverage, not an
  existing one to update

### Documentation
- `docs/reference/CLI.md:4548` — `ll-artifact dashboard` section (exit
  codes, size ceiling, flags)

### Configuration
- `scripts/little_loops/config/features.py:393,400` —
  `ArtifactsExportConfig.max_artifact_bytes` (default `8_000_000`)

## Program Design

### Types
N/A — no new data types beyond scalar chart-config string(s), unless a
structured chart-data payload key is added to `data_schema` (the current
`dashboard.llat` manifest has no precedent for an array/object-typed key —
all its `data_schema` properties are scalar strings/integers, see
`manifest.yaml:6-35`).

### Signatures
- `cmd_dashboard` (`dashboard.py:127`) — the `data` dict literal at
  `dashboard.py:217-230` is the single site any new chart-data or vendored-
  library key must be added to before the `validate_top_level_data` call
- `validate_top_level_data(data, schema)` (`artifact_templates.py:250-256`)
  — must run before `render_template`, source-order enforced (see Conventions
  in Force above)
- `render_template(template, data, config) -> str` (`artifact_templates.py:321-345`)
  — pure function; must not import `host_runner`/`anthropic`
  (`artifact_templates.py:321-327` docstring)
- `load_assets(root) -> dict[str, str]` (`artifact_templates.py:295-308`) —
  UTF-8 text only, no bytes mode ("Binary assets ... out of scope for v1")

### Call Path
`cmd_dashboard` (`data` dict assembly, `dashboard.py:217-230`) ->
`validate_top_level_data` (`dashboard.py:233`) -> `render_template`
(`dashboard.py:239`) -> `template.html.j2` `runQuery()`/`renderTable()`
(client-side, `template.html.j2:188-266`)

### Decision Rules
N/A — no new decision logic. The chart-eligibility check ("a result set
whose shape does not support the selected chart" per Expected Behavior) is a
new judgment the page must make, but neither the issue nor research pins
down its exact inputs/threshold (e.g. minimum numeric-column count) — this
is an open implementer decision, not a rule this pass can specify from
codebase evidence.

## Implementation Steps

1. Pick and vendor a viz library under `assets/vendor/<lib>/` with a
   `PROVENANCE.md` (version, source, SHA-256, license, update procedure),
   mirroring `assets/vendor/sql.js/PROVENANCE.md`, and register every file in
   `PACKAGE_DATA_ASSETS` (`package_data.py:82-84` is the pattern — one tuple
   per file).
2. Inline it through the `data` dict in `cmd_dashboard`, not the template's
   `assets/`: `load_assets()` reads UTF-8 text only, which is why
   `sql-wasm.wasm` is base64'd into `data` today (FEAT-3304 D5). A
   text-only JS library can ride in `data` verbatim like `sql_wasm_js` does.
3. Add the corresponding key(s) to `dashboard.llat/manifest.yaml`'s
   `data_schema` — it is `required`-listed and validated by
   `validate_top_level_data` at `cli/artifact/dashboard.py:233`.
4. Add the chart render path to the template beside `renderTable()`, driven by
   the same stepped rows, plus a column/axis picker.
5. Extend `PREDEFINED` entries so a view can declare its own chart mapping.

## Scope Boundaries

Out of scope for this enhancement:

- The export, redaction, or snapshot path — this is presentation only,
  layered on top of the already-shipped `dashboard.llat` page.
- The live bridge (FEAT-067) or command execution (FEAT-068) — no new
  runtime capability, just a client-side rendering of the same stepped rows.
- `ll-logs stats` telemetry (ENH-1921) — a different lineage and a different
  surface; not touched or reused here.
- The CDN-based (`vega`/`vega-lite`/`vega-embed` from `cdn.jsdelivr.net`)
  charting pattern used by `loops/vega-viz.yaml` — ruled out by this issue's
  own "no network request" acceptance criterion, not adopted or reconciled.
- New CLI flags on `add_dashboard_parser` — the chart layer is a page-side
  capability; a flag to omit the library for size reasons is left for a
  future issue if wanted.
- Defining the exact chart-eligibility threshold (e.g. minimum numeric-column
  count) beyond "falls back to the table when the shape doesn't fit" — left
  to the implementer, per Program Design § Decision Rules.

## Impact

- **Priority**: P3 - Presentation-layer improvement to an already-shipped,
  functional dashboard (FEAT-3304); no user is blocked without it, but it
  meaningfully increases the dashboard's day-to-day value per Motivation.
- **Effort**: Medium - Touches five files (`dashboard.py`, `template.html.j2`,
  `manifest.yaml`, `package_data.py`, plus new vendor assets) and needs new
  test coverage in three suites (Python, Node runtime gate, wheel smoke), but
  reuses the established vendor-and-inline pattern from `sql.js` rather than
  inventing one.
- **Risk**: Low - Additive and opt-in; the table remains the default and
  fallback, and no existing export/redaction/snapshot code path changes.
- **Breaking Change**: No

## API/Interface

No new CLI flags are required — the chart layer is a page-side capability, not
an export-time one. If a flag is wanted later (e.g. omitting the library to
save bytes), it belongs on `add_dashboard_parser` in
`cli/artifact/dashboard.py:278`.

## Considerations

- **Size budget.** `artifacts.export.max_artifact_bytes` defaults to 8 MB
  (`config/features.py:393`); the observed 2026-08-18 export was 1,972,719
  bytes. The library's inlined weight is a permanent per-artifact tax on every
  dashboard, charted or not, so it should be weighed against that headroom —
  a small plotting library is a much better fit here than a full grammar-of-
  graphics stack.
- **Escaping.** The template renders with `autoescape=False` and every stamped
  value is escaped at the call site (FEAT-3304 D18). Any new stamped key must
  follow that rule.
- **Row cap interaction.** `RENDER_ROW_CAP` bounds what is *rendered*, not what
  the query returns; a chart aggregating a large result may want a different
  bound than a table, and the page must stay honest about which rows it drew.
- **Scope boundary.** This is presentation only. It does not touch the export,
  redaction, or snapshot path, and it is not the live bridge (FEAT-067) or
  command execution (FEAT-068).
- **Not ENH-1921.** That issue is an `ll-logs stats` telemetry dashboard — a
  different lineage and a different surface.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- **CDN route ruled out by AC, not by convention alone.** `loops/vega-viz.yaml`
  loads `vega`/`vega-lite`/`vega-embed` from `cdn.jsdelivr.net` at view time —
  a second, non-reconciled "chart in a generated artifact" pattern already in
  this codebase. It conflicts with this issue's own "no network request" AC,
  so the vendor-and-inline route (matching `sql.js`) is the only one that
  satisfies the issue as written.
- **Wheel-smoke coverage gap.** `scripts/tests/test_wheel_smoke.py` has no
  `dashboard`/`sql.js`/`vendor` references today — the AC "still renders from
  an installed wheel" has no existing test anywhere to extend; it needs new
  coverage.
- **No shape-eligibility precedent.** `renderTable()`/`runQuery()`
  (`template.html.j2:188-266`) perform no column/row shape validation today —
  the "chart-ineligible result falls back to the table" AC introduces new
  logic with no existing groundwork, and its exact eligibility threshold is
  unspecified by both the issue and this research pass.

## Acceptance Criteria

- [ ] A query result is renderable as at least one chart type in the generated
      dashboard, offline over `file://` with no network request.
- [ ] At least one `PREDEFINED` view renders as a chart with no user SQL and no
      manual axis mapping.
- [ ] The table rendering remains available and is the fallback for a result
      set whose shape does not support the selected chart.
- [ ] The viz library is vendored with a `PROVENANCE.md` recording version,
      source, SHA-256, license, and update procedure, and every vendored file
      is registered in `PACKAGE_DATA_ASSETS` (one tuple per file), asserted by
      the existing package-data verification.
- [ ] The dashboard still renders from an installed wheel, not only a source
      checkout.
- [ ] A generated dashboard over `artifacts.export.max_artifact_bytes` still
      exits 1 without writing a file, with the library included in the measured
      size.
- [ ] The chart layer is added to the packaged `.llat` template and rendered
      through `render_template()`; no template code is copied from
      `policy-builder`.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-artifact`
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md`

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-08-26T03:07:55 - `c2ae49bb-0dbe-4c5e-b4c2-48b717101019.jsonl`
- `/ll:refine-issue` - 2026-08-26T01:57:24 - `c4a0c837-47fd-4eac-899a-346eee9fe946.jsonl`
- `/ll:capture-issue` - 2026-08-26T01:47:05 - `eadc481c-e910-429b-9281-ccfbd253d4a9.jsonl`
