---
id: ENH-3322
type: ENH
title: Chart layer for ll-artifact dashboard query results
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T01:46:57Z'
parent: EPIC-3299
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

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

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

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

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
- `/ll:capture-issue` - 2026-08-26T01:47:05 - `eadc481c-e910-429b-9281-ccfbd253d4a9.jsonl`
