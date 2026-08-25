---
id: FEAT-3304
title: Embed sql.js + filtered history.db export for queryable single-file artifacts
type: FEAT
priority: P3
status: open
discovered_date: '2026-08-23'
parent: EPIC-3299
relates_to:
- ENH-3035
- FEAT-3036
labels:
- artifact
- history-db
depends_on:
- FEAT-3309
- ENH-3035
learning_tests_required:
- sql.js
- jinja2
confidence_score: 90
outcome_confidence: 69
score_complexity: 14
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 20
---

# FEAT-3304: Embed sql.js + filtered history.db export for queryable single-file artifacts

## Summary

Extend `ll-artifact` from a pre-baked-JSON stamper into a real client-side
query engine: inline `sql.js` (SQLite-to-WASM) plus a filtered/date-scoped
export of `.ll/history.db` (e.g. `ll-artifact dashboard --tables
loop_run,usage_event --since 2026-07-26`) as gzip+base64 into the HTML. The page
stays 100% `file://`-safe and shareable but gains arbitrary drill-down
(filters, group-bys) instead of only the views predicted at generation
time. Key design surface: the export-filter shape and a shared
page-template kit that factors out `policy-builder`'s design-token
stamping so future artifacts (cost dashboard, backlog impact-effort
board, loop-fleet history explorer) can reuse it. This is the foundation
tier — Tier 2 (live bridge, FEAT-067) and Tier 3 (command execution,
FEAT-068) both build on it.

## Background — `ll-artifact` template pipeline

FSM loops produce high-quality artifacts because the loop's refinement
iterations polish them, but each artifact is a one-off snapshot: as soon
as the source document changes, the artifact drifts. Re-running the full
FSM loop re-pays the entire refinement cost for what is usually only a
data change. The expensive thing the loop refines is mostly
**presentation and structure** (layout, hierarchy, styling,
interactions); the part that goes stale is **data**. Separating the two
means refinement is paid once and regeneration approaches zero.

The pipeline this issue participates in:

```
source.md ──(extract: LLM, schema-checked)──> data.json ──(render: pure)──> artifact.html
                                                            ▲
                                              template.j2 + design tokens
```

A template is a directory containing `manifest.yaml` (identity, data
schema, source binding, render config), `template.html.j2` (Jinja2 body),
and optional `assets/`. The pipeline is **deterministic and LLM-free**:
`data.json` is validated against the manifest's `data_schema`, the Jinja2
body is rendered, and themed CSS vars are stamped via the existing
`load_design_tokens` / `render_as_css_vars_themed` machinery that
`policy-builder` already uses. Output lands in
`config.artifacts.default_output_dir`.

*Correction (2026-08-25, second review):* the **validation step is the
CLI's, not the renderer's** — `render_template()`
(`artifact_templates.py:317-341`) never calls `validate_top_level_data`;
`cmd_render` does, at `cli/artifact/render.py:119`. See **D14**.

**Template language: Jinja2, not invented.** The current `.replace()`
token scheme cannot express repeated regions or conditionals, and any
source with a variable number of sections needs loops. Jinja2 is boring,
ubiquitous, sandboxable (`SandboxedEnvironment`), and Python-native.
`policy-builder` can migrate to it later or stay as-is — for this
issue, the dashboard template is the first new consumer and is built on
the shared template kit (per ENH-3035), not a copy of `policy-builder`.

**Phased plan.** This issue lands the snapshot tier of the dashboard on
top of Phase-1 (`render`) plus the export-filter primitive. `extract`/
`refresh`/`status`/`templatize` are independent phases; this issue does
not block on them.

## Decisions (2026-07-31) — directly governing this issue

Recorded from hub decision issues ENH-075, ENH-069, ENH-073 (EPIC-070
gates), decided 2026-07-31. These decisions settle the three policy
questions this issue must answer; they are reproduced in full because
the artifact's behaviour is a direct downstream consequence of them.

### ENH-075 — What `history.db` data may be embedded in a shareable artifact

**Decision: two export modes, shareable-allowlisted by default, with
the mode and allowlist user-configurable in `.ll/ll-config.json`.**

- The default export embeds only the registered shareable set. An
  explicit local mode (e.g. `ll-artifact render --local`) may embed
  anything for personal use.
- Every artifact is visibly stamped with the mode (and allowlist
  version) that produced it, so a recipient can tell what they are
  looking at.
- Configuration lives in `.ll/ll-config.json` (e.g. an
  `artifacts.export` block): the default mode and any project-specific
  additions to the shareable set are declared there, not passed ad hoc.
  `--tables` selects from the effective allowlist and cannot widen it in
  shareable mode.

**Initial shareable export set** (columns not listed are excluded):

- `loop_runs`: `run_id`, `loop_name`, `started_at`, `ended_at`,
  `final_state`, `iterations`, `terminated_by`, `evaluator_score`,
  `failure_terminal`, `branch`, `head_sha`. Excluded: `error` (free
  text), `diagnostics_path` (absolute path).
- `usage_events`: `ts`, `session_id`, `model`, `state`, `input_tokens`,
  `output_tokens`, `cache_read_input_tokens`,
  `cache_creation_input_tokens`, `cost_usd`, `provider_vendor`,
  `run_id`, `invocation_id`.

Everything else — prompts, corrections, message/file/tool events, issue
bodies — is excluded from shareable exports until explicitly added by a
config or registry change.

**Standing rules:** absolute filesystem paths are never permitted in a
shareable snapshot; free-text fields (user prompts, corrections, issue
bodies) are embeddable only in local mode. The Tier-2 bridge (FEAT-067)
serves the unfiltered database and is exempt from this policy because
nothing leaves the host — that trust distinction is deliberate.

### ENH-069 — SQL exposure boundary for interactive artifacts

**Decision: raw SQL on the embedded snapshot; named queries only on the
live bridge.**

- Browser-side ad-hoc SQL runs only against the inert `sql.js` snapshot,
  which was already filtered at export time under ENH-075's policy —
  export-time filtering stays the single place data scope is decided.
- FEAT-067's bridge exposes a registered named-query set
  (`/query?name=…`) and nothing else, matching FEAT-068's write-side
  "never direct exec" allowlist model so read and write share one
  enforcement story.
- Artifact queries are not guaranteed to survive the snapshot→live
  upgrade unchanged: live mode is allowed a narrower surface by
  design. The named-query registry ships with the artifact template kit;
  additions are project-config changes, not runtime.

### ENH-073 — Tier-2 bridge lifecycle

**Decision: both lifecycles, run-scoped as the default path.**

- `ll-loop run` / `ll-parallel` auto-start a bridge if none is listening
  and tear down only what they started. An explicitly started daemon
  (`ll-artifact serve`) is detected and reused; a run never kills a
  daemon it did not start (ownership is recorded at spawn, e.g. PID
  file provenance).
- FEAT-067 implements only the run-scoped path at minimum; daemon
  detection/reuse and `ll-artifact serve` may be deferred to Tier 3
  alongside FEAT-068.
- Artifacts must define the degraded state: when the expected bridge
  is gone, the artifact falls back to snapshot-only rendering with a
  visible "live data unavailable" indicator — degraded is a designed
  state, not an accident.
- A queued FEAT-068 command may outlive a run-scoped bridge; its
  result is persisted by the queue and surfaced on the next bridge
  start rather than delivered live.

## Scope

- A new `ll-artifact dashboard` (name provisional) subcommand that
  exports a filtered subset of `.ll/history.db` and stamps it,
  base64-encoded, into a single self-contained HTML file.
- Export filtering by table (`--tables`) and by time window (`--since`),
  with the redaction/scope rules from ENH-075 applied at export time —
  export-time filtering is the only place data scope is decided (per
  ENH-069's framing), so it must be correct here rather than patched
  in the page. `--tables` takes the **type names** that are the keys of
  `_EXPORT_TABLE_MAP` (`loop_run`, `usage_event`), matching `ll-session
  export`; `--since` takes ISO 8601 or `YYYY-MM-DD`, matching
  `cli/session.py:549-554`. See Decisions (2026-08-25) D3/D4.
- Inlined `sql.js` (WASM) so the page runs arbitrary read-only SQL
  against the embedded snapshot with no network access and no build
  step at view time.
- A minimal query surface in the page: run a query, render a table,
  and at least one predefined view so the artifact is useful without
  the user writing SQL.
- Built on the shared template kit (per ENH-3035), not a copy of the
  `policy-builder` template.

## Non-goals

- Any live/bridge behaviour — that is FEAT-067. The artifact must be
  fully functional and honest about its staleness in snapshot-only mode.
- Any write path or command execution — that is FEAT-068.
- Migrating `policy-builder` to Jinja2, or implementing the manifest /
  `render` system in the design doc. See *Open questions* below.

## Decisions (2026-08-25) — pre-implementation review

Measured against this repo's real `.ll/history.db` (6.6 GB; `usage_events`
353,544 rows total, 149,614 in the last 30 days; `loop_runs` 1,114 / 641).
Building the exact ENH-075-allowlisted 30-day snapshot produced:

| encoding | size |
| --- | --- |
| snapshot `.db` (fresh `CREATE TABLE … AS SELECT`) | 17.4 MB |
| base64 of raw | 23.3 MB |
| **gzip → base64** | **4.1 MB** |

The issue's own headline example therefore produced a ~25 MB HTML file
before `sql.js` was added. Snapshot size is not a budget footnote; it
dictates the encoding. These decisions follow from that.

**D1 — The embedded snapshot is gzipped, then base64-encoded.** The page
inflates it with `DecompressionStream('gzip')`, which is available in
every current browser and works over `file://` with no library. 5.6×
smaller than raw base64 on the measured 30-day export, which is what
makes the headline example shippable at all.

**D2 — The snapshot is built by `ATTACH` + `CREATE TABLE … AS SELECT`.**
Open the source DB read-only (`file:…?mode=ro`), `ATTACH` a scratch file
DB, and materialize one table per selected type with the ENH-075 column
allowlist as the projection list and the `--since` predicate on that
type's timestamp column. Read the resulting file's bytes.

*This resolves the `VACUUM`/index-stripping question: neither is needed.*
A freshly created attached DB carries no indexes and no free pages.

*Proven 2026-08-25 by spike.* `ATTACH` of a writable scratch DB from a
`file:…?mode=ro` connection succeeds — `mode=ro` scopes read-only to the *main*
database, it does not set `query_only` on the connection — and
`CREATE TABLE snap.<t> AS SELECT … FROM main.<t>` writes to the attachment. The
resulting file carries `sqlite_master` entries for the tables only (no index
rows) and `PRAGMA freelist_count` = 0, exactly as D2 assumes. Source-side
indexes are not copied.

*This also corrects the Call Path.* `export_history()`
(`session_store/queries.py:151-211`) yields **dicts** for JSONL; `sql.js`
needs a **SQLite file**. There is no path from one to the other short of
re-inserting every row. The column-allowlist helper is a **sibling** of
`export_history()` sharing `_EXPORT_TABLE_MAP`, not a wrapper around it —
which also leaves `TestExportTableRegistration` untouched.

**D3 — `--tables` takes type names, not physical table names.** The keys
of `_EXPORT_TABLE_MAP` (`loop_run`, `usage_event`), so the flag means the
same thing here as in `ll-session export`. The ENH-075 allowlist below is
written in physical table names; the implementation maps through
`_EXPORT_TABLE_MAP` rather than restating either vocabulary.

**D4 — `--since` takes ISO 8601 or `YYYY-MM-DD`, not `30d`.** No
relative-duration parser exists in the package, and `ll-session`'s
`--since` already established this shape (`cli/session.py:549-554`).
Building a duration parser is out of scope; the `30d` spelling has been
removed from this issue.

**D5 — The dashboard is a real `.llat/` template rendered through
`render_template()`.** Not a `policy_builder.py`-style direct
`stamp_page_shell()` + `.replace()` stamp. `manifest.yaml` declares
`theme: design-tokens`, so `build_ll_namespace()`
(`artifact_templates.py:311-318`) invokes `themed_css_vars()` implicitly.
This resolves the Program Design contradiction the wiring pass flagged.

*Blocker the contradiction note missed:* `load_assets()`
(`artifact_templates.py:296-306`) reads assets as **UTF-8 text only** and
explicitly declares binary/data-URI assets out of scope for v1. The
vendored `sql-wasm.wasm` therefore **cannot** live in the template's
`assets/` directory. `cmd_dashboard` base64-encodes it and passes it in
the `data` dict to `render_template()`. Extending `load_assets()` for
binary assets was considered and rejected for this issue: it changes
FEAT-3036 shared code for one consumer's benefit.

**D6 — Client-side write rejection is a UX guardrail, not a security
boundary.** The user owns the bytes and the console; nothing about an
in-memory `sql.js` DB can be enforced against them. It does not need to
be — data scope is settled at export time, which is exactly ENH-069's
point. Do not describe it as a boundary in code comments or in the page.

*Mechanism revised 2026-08-25 by the `sql.js` learning test*
(`.ll/learning-tests/sqljs.md`, sql.js 1.14.2). Three measured facts change
the implementation:

- sql.js has **no built-in read-only mode**: a bare `DELETE` mutates the
  in-memory DB.
- `db.exec()` runs **every** semicolon-separated statement in one call, so a
  leading-`SELECT`/`WITH` check on its own is *not* sufficient — `SELECT 1;
  DELETE FROM loop_runs;` passes that check and deletes.
- `PRAGMA query_only = 1` **is** honoured by sql.js and rejects writes at the
  engine level with `attempt to write a readonly database`. It is reversible
  from the query box (`PRAGMA query_only = 0`), which is precisely why this is
  a guardrail and not a boundary.

Implement as: set `PRAGMA query_only = 1` immediately after every
instantiation (the real enforcement), plus a submitted-text check that rejects
multi-statement input and any `PRAGMA` — the text check exists to give a clear
error message, not to be the enforcement. Pair both with the **"reset
snapshot"** action that re-instantiates the DB from the embedded bytes;
re-instantiation was proven to restore mutated rows.

**D7 — Size budget: hard-fail before write, measured on final HTML
bytes.** New `artifacts.export.max_artifact_bytes`, default `8000000`.
*Calibration (added 2026-08-25):* the default is set against this repo's
measured 30-day export — 4.1 MB gzip+base64 snapshot plus the measured
~0.92 MB `sql.js` floor (D8) ≈ 5.0 MB, leaving ~3 MB of headroom, i.e. roughly
a 55-60-day window on a 6.6 GB `history.db` before the ceiling bites. State
this in the CLI help and the docs so the first hard-fail is read as the
designed behaviour it is, not as a bug.
Final rendered HTML size is the quantity that actually bites the user, so
it is the one measured — not the raw snapshot. Hard-fail (exit 1, naming
the measured size and the limit) matches every existing size ceiling in
this codebase (`templatize_max_input_bytes`, `templatize.py:846-854`); no
warn-only or auto-narrow ceiling exists anywhere here, and this issue does
not introduce the first one.

**D8 — `sql.js` provenance lives at
`scripts/little_loops/assets/vendor/sql.js/PROVENANCE.md`.** Records
version, upstream URL, SHA-256 of each vendored file, and the MIT license
text (SQLite itself is public domain). This establishes the codebase's
first vendored-binary provenance convention — there is no existing one to
follow. The `.wasm` and its JS glue must also be registered in
`PACKAGE_DATA_ASSETS` (`package_data.py`), **one tuple per file** — the
manifest has no directory-glob form.

*Measured 2026-08-25 (learning test).* Pin **sql.js 1.14.2**, vendoring the
two files from its `dist/`:

| file | raw | as embedded |
| --- | --- | --- |
| `sql-wasm.wasm` | 658,410 B | 877,880 B (base64) |
| `sql-wasm.js` (glue) | 46,535 B | 46,535 B (text, verbatim) |
| **fixed floor per artifact** | | **~924 KB** |

This corrects the "roughly 1–1.5 MB raw / ~2 MB base64" estimate under
§ Must address → Snapshot size: the real floor is well under half that.
`dist/` also ships `sql-wasm-browser.{js,wasm}` (644 KB wasm) — a build with
the Node `fs` shims stripped. The universal `sql-wasm.js` is proven to work
with `wasmBinary` and is the default choice; if the implementer prefers the
browser build, the swap is a one-line provenance/`PACKAGE_DATA_ASSETS` change
and saves ~20 KB, not a design decision. Also note that ~700 KB of vendored
binary enters git, the sdist, and every wheel — a one-time repo-weight cost
worth stating in the provenance file.

**D9 — The dashboard `.llat/` template ships inside the package and is
resolved by path, not by `templates_dir`.** `resolve_template()`
(`artifact_templates.py:70-85`) tries a filesystem path, then
`config.artifacts.templates_dir` — which is *project-local*
(`artifacts/templates`, `render.py:85-88`). There is no built-in-template
discovery path anywhere in the codebase today, so D5's "render it as a real
`.llat/` template" has no home without this decision. The template ships at
`scripts/little_loops/templates/dashboard.llat/` and `cmd_dashboard` resolves
it with `importlib.resources.files("little_loops").joinpath("templates",
"dashboard.llat")`, handing the resulting path to `resolve_template()`'s
path-first branch. Precedent: `design_md.py:11,36` already resolves packaged
built-in profiles exactly this way, and `mcp_server/templates/issues-view.html`
is the precedent for a packaged HTML template. Every file of the template
directory (`manifest.yaml`, `template.html.j2`, anything under `assets/`)
needs its own `PACKAGE_DATA_ASSETS` tuple. A `--template` override that lets a
project point at its own `.llat/` is optional and not required by any AC.

**D10 — Template-engine constraints, pinned so they are not rediscovered at
debug time.** `build_environment()` (`artifact_templates.py:267-279`) is
frozen and non-default:

- Delimiters are `[[= =]]`, `[[% %]]`, `[[# #]]` — **not** `{{ }}`. Inline JS
  in the template body must not contain a literal `[[=` or `[[%`.
- `autoescape=False`. This is what lets the multi-megabyte base64 blobs
  through byte-exact; do not "fix" it, and do not rely on escaping anywhere in
  the body.
- `undefined=StrictUndefined`. Every key the body references must be present
  in `data` or the render raises `DataValidationError`.

Values passed through `data` are never scanned as template source, so the
vendored glue's own contents cannot collide with the delimiters. Note also
that `load_assets()` is UTF-8-text-only for the **`.wasm` only** — the
`sql-wasm.js` glue *is* text and may live in the template's `assets/` (reached
as `ll.assets['sql-wasm.js']`), which is cleaner than base64-encoding it. The
Call Path's "read vendored `sql-wasm.wasm` + JS glue → base64" over-applies
D5: only the `.wasm` needs base64.

**D11 — Schema-version divergence is detected at export time, not view
time.** The prior AC ("renders a visible mismatch warning when opened against
a snapshot it was not built for") is not implementable: the artifact *contains*
its snapshot, so there is nothing for it to mismatch against once written.
Worse, D2's `CREATE TABLE … AS SELECT` copies only the selected tables, so the
`meta` table that holds `schema_version` (`schema.py:1308`) is **not** in the
snapshot at all. The implementable control is: read the source DB's recorded
`schema_version`, compare it against the installed code's `SCHEMA_VERSION`
(`session_store/schema.py:25`, currently `45`), stamp **both** into the page,
and emit a visible export-time warning when they differ. The page shows the
version it was built from as provenance; it does not attempt runtime
detection.

**D12 — The base ENH-075 allowlist is a code constant; config carries only
additions plus a version.** ENH-075's `table -> [columns]` map has no home in
the current design — config holds "additions" and an "allowlist version", but
nothing defines the base set or what the version means. Land the base set as a
module-level constant beside `_EXPORT_TABLE_MAP` (`session_store/queries.py:89`),
e.g. `_SHAREABLE_COLUMNS: dict[str, list[str]]` keyed by physical table name,
with `_SHAREABLE_ALLOWLIST_VERSION: int = 1` next to it. The rule: any edit to
the constant bumps the version in the same commit, and a test asserts the two
change together (hash the constant, pin the hash against the version). Without
this, the AC's "stamped with the allowlist version" stamps an unmanaged string
and the control it is supposed to provide does not exist.

**D13 — `--since` on `loop_run` filters `ended_at`, which silently drops
in-flight runs.** `_EXPORT_TABLE_MAP["loop_run"]` is `("loop_runs",
"ended_at")`; a run that is still executing, or that crashed without writing
an end timestamp, has `ended_at IS NULL` and is excluded by any `>=` predicate.
Filter on `COALESCE(ended_at, started_at)` for `loop_run` so a windowed export
includes runs that started inside the window, and say so in the page's filter
stamp. If the implementer prefers the simpler `ended_at` semantics, that is
acceptable — but it must then be stated in the CLI help and the page, not left
as a silent omission.

## Decisions (2026-08-25) — third pre-implementation review

Seven findings from re-checking the load-bearing claims above against the
code. Two corrections to what this issue asserts, five previously
unspecified behaviours that would otherwise be decided at debug time.

*Verified correct in the same pass (recorded so they are not re-checked):*
every column in the ENH-075 allowlist exists in the live schema
(`PRAGMA table_info` on `loop_runs` and `usage_events`, 2026-08-25), and D9's
`importlib.resources` precedent is real — `cli/artifact/design_md.py` already
does `Path(str(packaged))` on a `files(...).joinpath(...)` result.

**D14 — `cmd_dashboard` must call `validate_top_level_data()` itself.**
`render_template()` (`artifact_templates.py:317-341`) does **not** validate
`data` against the manifest's `data_schema`; it builds the context and
renders. The validation is the caller's, done by `cmd_render` at
`cli/artifact/render.py:119`. If `cmd_dashboard` omits it, the dashboard
manifest's `data_schema` is decorative — declared, never enforced, and a
missing key surfaces only as a `StrictUndefined` error from deep inside the
body. Call `validate_top_level_data(data, manifest["data_schema"])` before
`render_template()`, matching `render.py`'s order.

**D15 — The output filename comes from the manifest; the default directory
must not be the project root.** `render` writes to `output_dir /
template.manifest["output"]` (`render.py:67`), and `--output` there names a
**directory**, not a file (`render.py:58-62`, `:193`). Two consequences this
issue had left open:

- The dashboard's `manifest.yaml` must declare an `output:` filename —
  `history-dashboard.html`.
- `config.artifacts.default_output_dir` defaults to `"."`
  (`features.py:389`), so a no-flag `ll-artifact dashboard` drops a ~5 MB HTML
  file into the project root. FEAT-3309 introduced `promotion_dir`
  (`.loops/artifacts`, inside the gitignored tree) for exactly this reason.
  The dashboard defaults to `config.artifacts.promotion_dir`, not
  `default_output_dir`; `--output` (a directory, matching `render`) overrides.

**D16 — `--tables` defaults to the shareable set, `--since` is effectively
required, and the size ceiling gets a cheap pre-check.** Three coupled points:

- `--tables` defaults to the keys the shareable allowlist covers
  (`loop_run,usage_event`) — **not** `_EXPORT_DEFAULT_TABLES`
  (`queries.py:112+`), which is 20 types and has no ENH-075 allowlist entry
  for 18 of them.
- `--since` has no default, and omitting it means all history: 353,544
  `usage_events` on this repo, ~24× the measured 30-day export.
- D7 measures the **final rendered HTML**, which means the all-history path
  materializes the snapshot, gzips it, base64-encodes it and renders the
  template — hundreds of MB of peak RSS — *before* it hard-fails. Add a cheap
  pre-check: after `build_snapshot_db()` writes the scratch file, compare
  `dest.stat().st_size` against `max_artifact_bytes` and fail there if the raw
  snapshot alone already exceeds the ceiling. The final-HTML check (D7) stays
  as the authoritative one; this is a fast path out, not a replacement.
- Both failure messages name `--since` as the remedy, since narrowing the
  window is the only user-side fix.

**D17 — The page caps rendered result rows.** A 30-day snapshot holds
~150,000 `usage_events` rows; `SELECT * FROM usage_events` in the query box
builds 150,000 DOM rows and hangs the tab. This is the most likely first-use
failure of the feature. The page renders at most `N` rows (500) and displays
"showing 500 of 149,614 rows" above the table. Chosen over auto-appending a
`LIMIT` to the user's SQL: rewriting submitted SQL fights D6's
single-statement text check, breaks aggregate queries, and lies about what ran.
Capping at the render step leaves the query honest and the count truthful.

**D18 — `autoescape=False` means `cmd_dashboard` owns escaping.** D10 notes
the setting is what lets the multi-megabyte blobs through byte-exact; the same
setting means everything *else* in `data` — the filter stamp (`--since`,
`--tables`), the export mode, the schema versions — is written into the page
raw. Those values are constrained by parsing and allowlisting today, so there
is no live defect; the rule is stated so it survives the next flag added:
**any value placed in `data` must already be validated or escaped by
`cmd_dashboard`, because the environment will not do it.**

**D19 — Read `schema_version` inline on D2's read-only connection.** There is
no public accessor: `_current_version()` is private (`schema.py:1299`) and the
public schema-report dict that wraps it (`schema.py:1531`) walks `PRAGMA
index_list` for every table — far too heavy for one integer. Issue
`SELECT value FROM meta WHERE key = 'schema_version'` on the connection D2
already opens.

*And state why D2's raw `sqlite3.connect("file:…?mode=ro", uri=True)` matters:*
the store's normal open path **migrates on open** (`schema.py:1340-1382`).
Routing the export through it would mutate the user's `history.db` as a side
effect of generating a read-only artifact. The raw read-only connection is not
a convenience — it is the reason the export is safe to run against a live DB.

**D20 — Convert the packaged template path to `Path` before handing it over.**
`resolve_template(template_arg: str, templates_dir: Path)`
(`artifact_templates.py:70`) takes a **`str`** and calls `Path(template_arg)`
on it; `importlib.resources.files(...).joinpath(...)` returns a `Traversable`.
Follow `design_md.py`'s `Path(str(packaged))` conversion. Simpler still, and
preferred: skip `resolve_template()` entirely and call `load_manifest(root)`
on the packaged path directly — the path is known at that point, so there is
nothing to resolve, and `resolve_template()`'s `templates_dir` fallback branch
is project-local (D9) and can only produce a misleading error message here.

## Decisions (2026-08-25) — fourth pre-implementation review

Three previously unspecified surfaces, pinned so they are not decided at
implementation time. The load-bearing claims from earlier passes were
re-verified against the code in the same review (`_EXPORT_TABLE_MAP` keys,
the `meta`/`schema_version` query at `schema.py:1308`, the frozen Jinja
environment, `load_assets()` UTF-8-only, `promotion_dir`, `render_template()`
not validating) — all hold.

**D21 — `artifacts.export` v1 config shape is `{mode, max_artifact_bytes}`
only; the ENH-075 "additions" field is deferred.** D12 pinned the base
allowlist as a code constant but left the config side at "carries additions"
with no shape — and `additionalProperties: false` means the schema must be
written exactly, so an unpinned shape gets invented at implementation time.
Deferring it is the better cut: no AC requires additions, and an unversioned
project-local widening would muddy the allowlist-version stamp (base v1 +
silent local additions makes the stamp ambiguous, undercutting the control it
exists to provide). When a consumer actually needs additions, the field lands
as its own small issue that must also answer how the stamp reflects them
(e.g. "v1 + project additions"). This narrows ENH-075's recorded sketch; the
narrowing is deliberate and recorded here rather than silently.

**D22 — In `--local` mode, `--tables` may select any `_EXPORT_TABLE_MAP`
type, exported as `SELECT *`.** ENH-075's "local mode may embed anything"
implied this but no decision stated it. Shareable mode: `--tables` selects
from the shareable types only (D16) with the column projection applied.
Local mode: any of the 20 type names is accepted; types without a
`_SHAREABLE_COLUMNS` entry export all columns; the `--since` predicate still
uses that type's `_EXPORT_TABLE_MAP` timestamp column. The default when
`--tables` is absent stays `loop_run,usage_event` in both modes — local mode
widens what *may* be selected, not what is selected silently.

**D23 — Verify the vendored `sql-wasm.js` glue contains no literal
`</script>` before wiring it inline.** D10 covers the Jinja delimiters, but
the glue is injected as text inside an inline `<script>` tag, and a
`</script>` anywhere in the minified emscripten output truncates the script
in the browser — a failure the Node learning test cannot catch. One grep of
the vendored file at vendoring time, plus a test asserting the substring is
absent from the vendored glue (so a future version bump re-proves it). If a
future version ever hits, the fallback is embedding the glue base64 like the
wasm.

**D13 (amended) — the `COALESCE(ended_at, started_at)` semantics gets a
test.** The fourth review noted D13 had a Decision Rule but no assertion:
add a test that a `loop_runs` row with `ended_at IS NULL` and `started_at`
inside the window is present in the recovered snapshot.

**D17 (amended) — bound memory, not just DOM.** The render cap stops DOM
explosion, but `db.exec()` still materializes every result row into JS
arrays first (~150k on the measured 30-day snapshot). Use
`db.prepare()`/`step()` instead: collect rows only up to the cap, keep
stepping to count the true total, then `free()` the statement. Same honest
"showing 500 of N" line, bounded memory, still no rewriting of the user's
SQL.

## Must address

- **Snapshot size.** *Resolved by D1 (gzip+base64), D2 (no `VACUUM`/index
  stripping needed), and D7 (hard-fail at
  `artifacts.export.max_artifact_bytes`, measured on final HTML).*
  *Floor measured 2026-08-25 (D8):* `sql.js` 1.14.2 contributes a **fixed
  floor of ~924 KB** to every artifact (877,880 B base64 `.wasm` + 46,535 B
  glue) — not the 1–1.5 MB raw / ~2 MB base64 originally estimated. Counted
  against D7's ceiling in that decision's calibration note.
- **Staleness.** The page must display the export timestamp and the
  filter that produced it, prominently. A shared dashboard that
  silently shows month-old numbers is worse than no dashboard.
- **Schema coupling.** The page's queries are written against
  `history.db`'s schema. The artifact records the schema version it was
  exported from. *Scoped by D11:* divergence is detected **at export time**
  (source DB's recorded `schema_version` vs the installed `SCHEMA_VERSION`),
  not at view time — the artifact contains its own snapshot and has nothing to
  mismatch against once written, and the `meta` table holding the version is
  not even copied by D2's `CREATE TABLE … AS SELECT`.
- **`sql.js` provenance.** *Resolved by D8.* The WASM blob is a vendored
  third-party binary inlined into every artifact — a supply-chain
  surface, not an asset. Record source, version, hash, license, and the
  update procedure.
- **Read-only enforcement** in the page, so a stray `DELETE` in the
  query box can't corrupt the in-memory DB mid-session and confuse the
  user. *Scoped by D6: `PRAGMA query_only = 1` (proven to work) plus a
  multi-statement/`PRAGMA` text check for error messaging, plus a reset
  action — a guardrail, not a boundary. A leading-`SELECT` check alone was
  measured to be insufficient.*
- **`wasmBinary` is mandatory.** Over `file://`, `sql.js`'s default
  `locateFile` fetch of the `.wasm` is blocked — initialize with
  `wasmBinary: <decoded bytes>`. *Proven 2026-08-25:* with `wasmBinary`,
  `initSqlJs` completes and issues no `fetch()` at all; without it, sql.js
  resolves `sql-wasm.wasm` through `locateFile` — the fetch that has nowhere
  to go over `file://`. Note also that `initSqlJs` memoizes its module, so a
  second call with different options returns the first instance.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

**sql.js provenance convention gap**: no `VENDORED.md` or third-party-asset ledger exists in this codebase. The only established provenance convention is an inline comment directly above a dependency pin in `scripts/pyproject.toml` (e.g. the `anthropic` pin, `pyproject.toml:46-51`, per CLAUDE.md's own callout). `scripts/little_loops/assets/` holds only first-party ASCII art with no license/provenance comment attached — there is no existing precedent to follow for recording a vendored binary's version/license/source; this issue would establish the first one. Any vendored sql.js WASM asset must also be registered in `scripts/little_loops/package_data.py`'s `PACKAGE_DATA_ASSETS` manifest to pass `test_package_data_manifest.py`'s completeness check.

## Open questions

- ~~The design doc proposes a manifest + Jinja2 `render` pipeline as the
  general artifact system. ENH-074's "template kit" and that pipeline
  overlap. Decide whether this issue builds on the doc's Phase-1 render
  system or on a lighter kit, before ENH-074 extracts anything —
  otherwise the kit gets extracted twice.~~
  **Resolved 2026-08-23 in FEAT-3036** (§ Template packaging, engine, and hash
  storage): one system, not two — `.llat/` directory templates rendered by
  sandboxed Jinja2, hashes in a lockfile. ENH-3035's kit is the shared-parts
  layer *of* that pipeline, not an alternative to it. This issue's dashboard
  template is authored against that shape.

- **Config schema blocker.** The 2026-07-31 ENH-075 decision reproduced above
  assumes an `artifacts.export` block in `.ll/ll-config.json`. It does not
  exist: `ArtifactsConfig` (`config/features.py:369-384`) has exactly one field,
  `default_output_dir`, and `config-schema.json:1870-1880` sets
  `additionalProperties: false`, so the schema will reject an `export` key
  outright. Adding the block — mode, allowlist, allowlist version — is in scope
  for this issue and must land before the export filter, since the filter reads it.
  **Confirmed 2026-08-23**: FEAT-3036 explicitly scopes itself to
  `artifacts.templates_dir` only and hands `artifacts.export` to this issue, as
  the only code that reads it.
  **Coordination concern retired 2026-08-25**: FEAT-3036's `templates_dir` is
  already merged into `config-schema.json` (verified present alongside
  `templatize_max_input_bytes` and `promotion_dir`). There is no in-flight schema
  edit left to collide with; adding `artifacts.export` is an ordinary
  three-touch-point addition per § Conventions in Force.

- **Export mode is not a `render` flag.** The ENH-075 text above sketches
  `ll-artifact render --local`. FEAT-3036 rejected that (2026-08-23, second
  pass): `render` is a pure `template + data.json → artifact` function and must
  not read ambient database state. The mode flag belongs on this issue's
  export-side subcommand (`ll-artifact <dashboard-cmd> --local`), where the
  history.db read actually happens.

## Acceptance Criteria

- [ ] `ll-artifact <dashboard-cmd> --tables … --since …` produces a
      single HTML file that opens over `file://` with no network access
      and no external assets.
- [ ] The page executes user-entered read-only SQL against the
      embedded snapshot and renders results; write statements are
      rejected client-side, and a "reset snapshot" action re-instantiates
      the DB from the embedded bytes (per D6). The rejection is enforced by
      `PRAGMA query_only = 1`, and a test asserts that the multi-statement
      input `SELECT 1; DELETE FROM loop_runs;` does not mutate the DB — the
      case a leading-`SELECT` check alone was measured to miss.
- [ ] Export scope honours the ENH-075 rules; a test **gunzips and
      base64-decodes the embedded blob back out of the generated HTML,
      opens it as a SQLite DB, and asserts the excluded columns/tables
      are absent from its schema** — not merely hidden in the UI, and not
      merely absent as a substring.
- [ ] The export timestamp and the filter arguments are visible in the
      rendered page.
- [ ] The page is visibly stamped with the export **mode**
      (`shareable`/`local`) and the **allowlist version** that produced
      it, per ENH-075. This is the control that stops a `--local` export
      being shared unknowingly, so it is asserted by a test for both
      modes.
- [ ] The artifact records the `history.db` **schema version** it was
      exported from, and the export emits a visible warning when the source
      DB's recorded `schema_version` differs from the installed
      `SCHEMA_VERSION` (per D11). Tested by exporting from a DB whose
      recorded version has been altered.
- [ ] The page ships **at least one predefined view** that renders
      without the user writing any SQL (per § Scope).
- [ ] An export whose final HTML exceeds
      `artifacts.export.max_artifact_bytes` exits 1 naming the measured
      size and the limit, writing no file, with a test (per D7).
- [ ] The artifact is rendered through `render_template()` as a real
      `.llat/` template with `theme: design-tokens` (per D5); no template
      code is copied from `policy-builder`, and `cmd_dashboard` does not
      call `stamp_page_shell()` directly.
- [ ] `sql.js` version, source, SHA-256, license, and update procedure are
      recorded at `scripts/little_loops/assets/vendor/sql.js/PROVENANCE.md`,
      and every vendored file is registered in `PACKAGE_DATA_ASSETS` (one
      tuple per file).
- [ ] The dashboard `.llat/` template is resolved from **inside the package**
      via `importlib.resources` (per D9) and renders from an installed wheel,
      not only from a source checkout — every template file registered in
      `PACKAGE_DATA_ASSETS`.
- [ ] The ENH-075 base allowlist is a module-level constant with a version
      marker beside it (per D12), and a test fails if the constant changes
      without the version being bumped in the same commit.
- [ ] `.ll/ll-config.json` accepts an `artifacts.export` block with exactly
      `mode` and `max_artifact_bytes` (per D21 — no "additions" field in v1) —
      schema updated, round-tripped by `BRConfig`, and covered by a test that
      an unknown key is still rejected.
- [ ] `cmd_dashboard` validates its `data` payload against the dashboard
      manifest's `data_schema` before rendering (per D14), with a test that a
      payload missing a required key raises `DataValidationError` rather than
      surfacing as a `StrictUndefined` render error.
- [ ] A query returning more rows than the page's render cap displays at most
      the cap and states the true total ("showing 500 of N rows"), per D17,
      with a test asserting the submitted SQL is passed to `sql.js`
      unmodified — the cap is applied at render via `prepare()`/`step()`
      (rows collected only up to the cap), not by rewriting the query.
- [ ] With no `--tables`, the export covers exactly the shareable-allowlist
      types (`loop_run`, `usage_event`) and not `_EXPORT_DEFAULT_TABLES`'s
      full set (per D16), asserted by a test on the recovered snapshot schema.
- [ ] A raw snapshot that already exceeds `max_artifact_bytes` fails before
      gzip/base64/render (per D16), with a test asserting no render occurred —
      the final-HTML ceiling (D7) remains separately tested.
- [ ] Generating a dashboard leaves the source `.ll/history.db` byte-identical
      (per D19 — the export must not travel the migrating open path), asserted
      by hashing the DB file before and after an export run.
- [ ] A `loop_runs` row with `ended_at IS NULL` and `started_at` inside the
      `--since` window is present in the recovered snapshot (per D13's
      `COALESCE` semantics), asserted by a test.
- [ ] The vendored `sql-wasm.js` glue contains no literal `</script>`
      substring (per D23), asserted by a test against the vendored file so a
      version bump re-proves it.

## Dependencies

- **ENH-075** — export scope/redaction rules must be decided before
  the export filter is implemented. *Decided 2026-07-31; see Decisions
  section above.*
- **ENH-3035** — should land alongside or just before, so this artifact
  is the kit's first consumer rather than a second copy of
  `policy-builder`. *Done 2026-08-25.*
- **FEAT-3309** — frontmatter `depends_on` edge, omitted from this prose
  list until 2026-08-25. *Done 2026-08-25.* (ENH-075 is a decision, not a
  work item, so it is deliberately absent from frontmatter.)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

Both frontmatter `depends_on` entries are now `status: done`: **ENH-3035** (completed 2026-08-25T16:14:52Z, `verify_verdict: VALID`) produced `artifact_template_kit.py`, whose own header docstring already names this issue as its intended second consumer; **FEAT-3309** (completed 2026-08-25T01:18:33Z) landed independently. Neither blocker is currently open — this issue is unblocked on both `depends_on` edges as of this pass.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/config/features.py:369-403` — `ArtifactsConfig` dataclass; needs a new `export` field (mode/allowlist/allowlist_version), following the same `.get(key, default)` composition every other field uses in `from_dict()`
- `scripts/little_loops/config/core.py:339` — `BRConfig.__init__` constructs `ArtifactsConfig.from_dict(self._raw_config.get("artifacts", {}))`; a two-level-nesting precedent for reading a nested sub-block already exists at line 340-342 (`AnalyticsCaptureConfig.from_dict(self._raw_config.get("analytics", {}).get("capture", {}))`)
- `scripts/little_loops/config/core.py:917-922` — `BRConfig.to_dict()`; every `ArtifactsConfig` field must also round-trip through here (confirmed as the precedent both `templatize_max_input_bytes` and `promotion_dir` followed)
- `scripts/little_loops/config-schema.json:1875-1899` — `artifacts` object, `additionalProperties: false`; add a nested `export` object here following the `analytics.capture` shape at `config-schema.json:1922-1966` (itself `"type": "object"` with its own `"properties"` and its own `"additionalProperties": false`)
- `scripts/little_loops/cli/artifact/__init__.py` — `main_artifact()` dispatcher (lines 60-179): add `add_dashboard_parser(subparsers)` to the import list and call site (alongside line 153-157), and a new `if args.command == "dashboard": return cmd_dashboard(args, logger)` branch
- New `scripts/little_loops/cli/artifact/dashboard.py` — following the `add_<name>_parser(subparsers)` + `cmd_<name>(args: argparse.Namespace, logger: Logger) -> int` pair convention used by `render.py`/`status.py` (one file per subcommand, per `cli/artifact/__init__.py:18-23`'s stated convention)
- `scripts/little_loops/session_store/queries.py:88-211` — `export_history()` / `_EXPORT_TABLE_MAP` already maps `"loop_run": ("loop_runs", "ended_at")` and `"usage_event": ("usage_events", "ts")` and implements a parameterized `--since` filter, but does `SELECT *` per table with no column-level projection — ENH-075's per-column allowlist has no existing implementation to reuse and needs a new projection layer
- `scripts/little_loops/package_data.py` — `PACKAGE_DATA_ASSETS` manifest; a vendored sql.js WASM binary must be registered here to pass `test_package_data_manifest.py`'s completeness check
- `scripts/little_loops/artifact_template_kit.py` — its own header docstring (lines 1-13) already names "the sql.js dashboard (FEAT-3304)" as an anticipated second consumer of `themed_css_vars()`/`stamp_page_shell()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py` — existing `ll-session export` CLI already exercises `export_history()`'s `--tables`/`--since` surface; a live, tested precedent for the same flag shape this issue's `--tables loop_runs,usage_events --since 30d` example uses
- `scripts/little_loops/cli/history_context.py`, `scripts/little_loops/cli/ctx_stats.py` — other code reading `.ll/history.db` directly (FTS5 queries, per-tool byte metrics respectively); not reusable for export filtering but confirm the DB is read from multiple call sites today

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/__init__.py:89,185` — imports and re-exports `export_history` in `__all__`; a column-projection wrapper added for ENH-075 filtering should be re-exported alongside it if it becomes public
- `scripts/little_loops/cli/artifact/render.py:25-26,64,88`, `scripts/little_loops/cli/artifact/templatize.py:30,556`, `scripts/little_loops/cli/artifact/status.py:20,140`, `scripts/little_loops/cli/artifact/extract.py:35,199,254` — every existing `ll-artifact` subcommand that touches templates goes through `artifact_templates.py`'s `render_template()`/`resolve_template()`, **not** through `artifact_template_kit.py`'s `stamp_page_shell`/`themed_css_vars` directly (that direct-call pattern is unique to the pre-FEAT-3036 `policy_builder.py`). See Program Design contradiction note below.
- `scripts/little_loops/fsm/persistence.py:825,866` — FSM loop artifact-mode rendering also calls `render_template()` directly, confirming it as the single established rendering entry point every `.llat`-shaped artifact goes through today
- `scripts/little_loops/cli/__init__.py:52,110` — `from little_loops.cli.artifact import main_artifact`; re-exports it. `scripts/pyproject.toml:77` — `ll-artifact = "little_loops.cli:main_artifact"` console-script entry point the new `dashboard` subcommand rides on (no edit needed, confirms the wiring path)
- `scripts/little_loops/cli/verify_package_data.py:10,152` (`ll-verify-package-data`) and `scripts/tests/test_wheel_smoke.py:103` — both already iterate `PACKAGE_DATA_ASSETS` generically; a new vendored sql.js WASM tuple is picked up automatically, no separate edit needed here beyond the `package_data.py` registration already listed under Files to Modify
- `.ll/learning-tests/hatchling.md:19` — existing learning-test note already states "PACKAGE_DATA_ASSETS registration is required," corroborating the Files to Modify entry

**Program Design contradiction (found by wiring pass, not corrected here — Program Design is refine-issue's section):** the issue's own resolved Open Question ("one system, not two — `.llat/` directory templates... this issue's dashboard template is authored against that shape") and AC ("rendered through the ENH-3035 template kit; no template code is copied from `policy-builder`") point at routing `dashboard.py` through `artifact_templates.py`'s `render_template()`/`resolve_template()` (a real `.llat/` template with `manifest.yaml` + `theme: design-tokens`, letting `build_ll_namespace()` at `artifact_templates.py:311-318` invoke `themed_css_vars()` implicitly). The Program Design § Call Path as currently written instead has `cmd_dashboard` call `stamp_page_shell`/`themed_css_vars` directly followed by dashboard-specific `.replace()` stamping — the exact `policy_builder.py:61-94` idiom that predates FEAT-3036 and that the AC says not to copy. Implementer must pick one and reconcile the Call Path/Signatures text accordingly before AC "rendered through the ENH-3035 template kit" can be verified.

### Conventions in Force
- Subcommands register via an `add_*_parser(subparsers)` + `cmd_*(args, logger) -> int` pair, one file per subcommand under `cli/artifact/` — evidence: `render.py` (`add_render_parser`, `cmd_render` at line 72), `status.py` (`add_status_parser` at line 168, `cmd_status` at line 119). The two oldest subcommands (`policy-builder`, `design-md export`) predate this split and register inline in `__init__.py:108-151` — not retrofitted, and not the pattern to follow for a new subcommand.
- Adding a nested config block under `additionalProperties: false` is three hand-edited, hand-tested touch points with no schema-generation helper: (1) `config-schema.json` properties + its own nested `additionalProperties: false`, (2) a dataclass field + `from_dict()` default + a matching key in `BRConfig.to_dict()`, (3) a `test_config_schema.py` test asserting the key's presence/type/default. Evidence: `templatize_max_input_bytes` (FEAT-3315) and `promotion_dir` (FEAT-3309) were both added in lockstep across `config-schema.json:1888-1897`, `features.py:391-403`, `core.py:920-921`, and `test_config_schema.py:494-495`.
- No vendored third-party binary/license ledger (no `VENDORED.md`) exists in this codebase. The only established provenance convention is an inline comment directly above a pin in `scripts/pyproject.toml` (see the `anthropic` pin, `pyproject.toml:46-51`) — CLAUDE.md's own callout. `scripts/little_loops/assets/` holds only first-party ASCII art with no license/provenance comment convention attached.
- Negative-content assertions on generated artifacts use a bare `assert "<needle>" not in <content>` per excluded token, inline in the test function — no shared "assert-absent" helper. Evidence: `test_mcp_server.py:501-518` (`test_ui_issues_view_html_is_self_contained_with_no_network_references`, asserting `"http://"`, `"fetch("`, `"XMLHttpRequest"` are all absent from generated self-contained HTML) and `test_enh3035_artifact_template_kit.py:50`.
- Size-ceiling fields are hard-fail-before-call, not warn/auto-narrow. Evidence: `ArtifactsConfig.templatize_max_input_bytes` (`features.py:392`, default `400000`, bytes not tokens) is enforced at `templatize.py:846-854` and reused unchanged (not duplicated) at `extract.py:136-141` for a different measured quantity; `test_feat3310_artifact_extract.py:266-269` is the test precedent. No warn-only or auto-narrow variant of a size ceiling exists anywhere in this codebase.
- Base64/binary embedding into a self-contained HTML artifact has no existing precedent anywhere in `scripts/little_loops` (confirmed by two independent searches). The only existing "single self-contained HTML" mechanism is plain `str.replace()` substitution of `/*__NAME__*/`-style comment placeholders, chained one-per-placeholder — evidence: `policy_builder.py:77-94` (`html.replace("/*__GRAMMAR_SPEC_JSON__*/", grammar_json)` etc.) and the shared subset in `artifact_template_kit.py:52-71`'s `stamp_page_shell()`, which documents that a missing placeholder is a silent no-op, not an error.

### Tests
- `scripts/tests/test_config_schema.py:473-495` (`test_artifacts_in_schema`) — direct template for a new `export`-block assertion; `test_analytics_in_schema` at line 497 is the nested-sub-object precedent (`analytics.capture`)
- `scripts/tests/test_artifact_discover.py`, `test_artifact_templatize.py`, `test_feat3310_artifact_extract.py`, `test_feat3311_artifact_status.py`, `test_feat3036_artifact_templates.py`, `test_enh3035_artifact_template_kit.py` — per-subcommand naming convention (`test_<issue-id>_artifact_<subcommand>.py`) a new dashboard test file should follow
- `scripts/tests/test_package_data_manifest.py` — any new vendored sql.js WASM asset registered in `package_data.py` must pass this completeness check
- `scripts/tests/test_mcp_server.py:501-518` — pattern to follow for the AC's "excluded columns/tables are absent from the embedded blob" test (bare `assert "<needle>" not in <content>`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_queries.py` — `TestExportContextPressureEvent`/`TestExportAdvisorConsultEvent` (lines 149-207) assert `rows[0]["session_id"] == "s1"`; a column-allowlist wrapper must keep `session_id` in scope for these two record types or these tests break. `TestExportTableRegistration` (lines 209-257) pins `_EXPORT_TABLE_MAP`/`_EXPORT_DEFAULT_TABLES` set equality and the derived `--tables` help text — safe if the ENH-075 column allowlist is added as a new wrapper/kwarg rather than a restructure of these two module-level dicts; must be updated in lockstep if it isn't
- `scripts/tests/test_config_schema.py:478,1343` (`TestSchemaValueParity`) — maps `"ArtifactsConfig": "artifacts"`; a new `export` field must stay in parity here too, not just in `test_artifacts_in_schema`
- `scripts/tests/test_feat3036_artifact_templates.py` — `TestResolveTemplate` (line 94) and `TestRenderTemplate` (line 283, incl. `test_render_module_imports_nothing_from_host_runner_or_anthropic` at 355) are the direct precedent for testing a `.llat`-pipeline consumer, if the Program Design contradiction above is resolved toward routing `dashboard.py` through `render_template()`/`resolve_template()`. `TestArtifactCLIDispatchRender.test_render_dispatches_to_handler` (516-526) is the exact CLI-dispatch-mock pattern (`patch("little_loops.cli.artifact.cmd_render", ...)`) a `TestArtifactCLIDispatchDashboard` should mirror once `add_dashboard_parser`/`cmd_dashboard` land
- **Confirmed gap**: no test in `scripts/tests/` decodes an embedded base64 blob back out of generated HTML and compares it to source bytes — the AC's "excluded columns/tables are absent from the embedded blob" test needs this round-trip decode-and-compare, not just the assert-absent pattern from `test_mcp_server.py`

### Documentation
- `docs/reference/CLI.md` (~lines 4455-4563) — documents existing `ll-artifact` subcommands; a new `dashboard` subcommand needs an entry here
- `docs/ARCHITECTURE.md` (~line 893, "Artifact Control Layer") and `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — the canonical contract already classifies `html-anything.yaml`-style dashboards as level-1 "notify", reserving level 2/3 for the FEAT-067/FEAT-068 tiers this issue explicitly builds toward
- `docs/reference/CONFIGURATION.md` — already cross-references FEAT-3304 for the `artifacts` config keys

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:4455-4471` — subcommand table + shared "Exit codes:" line lists `policy-builder`/`design-md export`/`render`/`templatize`/`extract`/`refresh`/`status`; add a `dashboard` row + `#### ll-artifact dashboard` subsection (pattern at e.g. `~4512` for `render`), plus a size-budget exit-code carve-out parallel to `templatize`'s/`status`'s own exit-code notes if the "Must address → Snapshot size" decision resolves to a non-zero-exit failure mode
- `docs/reference/CONFIGURATION.md:912-929` — `### artifacts` section's key table (916-921) and JSON example (923-929) need a new `export` row/block once `ArtifactsConfig.export` lands, mirroring how `promotion_dir`/`templatize_max_input_bytes` were each added as a table row + JSON key
- `docs/ARCHITECTURE.md:1027-1031` ("Project-enriched artifacts") — cites `ll-artifact policy-builder`/`ll-artifact templatize` as the running stamping-pattern examples; if the Program Design contradiction (see Dependent Files above) resolves toward the `.llat` pipeline, the dashboard is a second example worth citing here for consistency
- `docs/reference/API.md` — module-reference entries for any new public symbols in `cli/artifact/dashboard.py` or a new export-projection wrapper in `session_store/queries.py`
- `scripts/little_loops/cli/artifact/__init__.py:1-24` (module docstring) — every existing subcommand is listed here with a one-line description + FEAT tag (`policy-builder` FEAT-2301, `render` FEAT-3036, etc.); add a `dashboard` bullet tagged FEAT-3304, and a matching `Examples:`/`Exit codes:` entry in `main_artifact()`'s epilog (`__init__.py:71-104`)

### Configuration
- `.ll/ll-config.json` — where a project's `artifacts.export` block would actually be set; `ArtifactsConfig.from_dict()` is `.get(key, default)`-based with no exceptions, so a project that has never touched `artifacts.export` degrades to hardcoded defaults with no error path (same behavior every other `ArtifactsConfig`/nested-config field has today)

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

### Types
- New `ArtifactsExportConfig`-shaped nested block on `ArtifactsConfig` (`scripts/little_loops/config/features.py:369-403`) — exactly two fields in v1 per **D21**: `mode: str` (`"shareable"` default | `"local"`) and `max_artifact_bytes: int` (default `8000000`, **D7**), mirroring the two-level nesting `AnalyticsCaptureConfig` already uses (`config/core.py:340-342`). The ENH-075 "additions" field is deferred (**D21**). Per **D12** the allowlist **version** is not a config field — it is a code constant beside the base allowlist, so a shared artifact's stamp cannot be forged by editing local config
- The shareable allowlist itself is a `table -> [columns]` mapping; the closest existing typed precedent for a table-name allowlist is `_EXPORT_TABLE_MAP: dict[str, tuple[str, str]]` (`session_store/queries.py:89-110`), which maps a public type name to `(table_name, timestamp_column)` — column-level projection has no existing type to extend
- Per **D12**, that mapping is a **code constant**, not config: `_SHAREABLE_COLUMNS: dict[str, list[str]]` keyed by physical table name, plus `_SHAREABLE_ALLOWLIST_VERSION: int = 1`, both module-level in `session_store/queries.py` beside `_EXPORT_TABLE_MAP`. `artifacts.export` config carries only the default mode and `max_artifact_bytes` (**D21** — additions deferred) — never the base set itself

### Signatures
- `ArtifactsConfig.from_dict(cls, data: dict[str, Any]) -> ArtifactsConfig` (`config/features.py:396`) — extend to read `data.get("export", {})`
- `BRConfig.to_dict()` (`config/core.py:917-922`) — extend with the new field, per the `templatize_max_input_bytes`/`promotion_dir` precedent
- `export_history(db, *, tables=None, since=None, include_messages=False) -> Generator[dict, None, None]` (`session_store/queries.py:151-211`) — **not on this issue's call path.** It yields dicts for JSONL; `sql.js` needs a SQLite *file*, and there is no path from one to the other short of re-inserting every row (**D2**). The new snapshot builder is a **sibling** function sharing `_EXPORT_TABLE_MAP`, not a wrapper around `export_history()` — which also leaves `TestExportTableRegistration` and `export_history()`'s existing caller (`ll-session export`) untouched.
- New snapshot builder, e.g. `build_snapshot_db(db: Path, dest: Path, *, tables: list[str], since: str | None, columns: dict[str, list[str]]) -> None` (`session_store/queries.py`) — `ATTACH` + `CREATE TABLE … AS SELECT` per **D2**; re-export alongside `export_history` in `session_store/__init__.py:89,185` if made public
- `cmd_dashboard(args: argparse.Namespace, logger: Logger) -> int` / `add_dashboard_parser(subparsers) -> None` (new, `cli/artifact/dashboard.py`) — following the exact `(argparse.Namespace, Logger) -> int` contract used by `cmd_render` (`render.py:72-168`) and `cmd_status` (`status.py:119-165`): builds `config = BRConfig(Path.cwd())` inside the function body, wraps the body in `except Exception as exc: logger.error(str(exc)); return 1`
- `importlib.resources.files("little_loops").joinpath("templates", "dashboard.llat")` — **how the built-in template is found** (**D9**). `resolve_template()` only knows a filesystem path and the *project-local* `config.artifacts.templates_dir`; `cmd_dashboard` supplies the packaged path so the path-first branch takes it. Precedent: `cli/artifact/design_md.py:11,36`
- `render_template(template: ArtifactTemplate, data: dict[str, Any], config: object) -> str` / `resolve_template(...)` (`artifact_templates.py`) — **the rendering entry point** (**D5**). `themed_css_vars()` is reached implicitly via `build_ll_namespace()` (`artifact_templates.py:311-318`) because `manifest.yaml` declares `theme: design-tokens`; `cmd_dashboard` does **not** call `stamp_page_shell()` or `themed_css_vars()` directly — that direct-call idiom is `policy_builder.py:77-94`'s and is what the AC forbids copying.
- `load_assets(root: Path) -> dict[str, str]` (`artifact_templates.py:296-306`) — **constraint, not a call site**: reads assets as UTF-8 text only and declares binary/data-URI assets out of scope for v1. The vendored `sql-wasm.wasm` therefore cannot live in the template's `assets/`; `cmd_dashboard` base64-encodes it into `data` instead (**D5**). Extending this function for binary assets was considered and rejected — it changes FEAT-3036 shared code for one consumer.

### Call Path

_Superseded 2026-08-25 by Decisions D1/D2/D5. The prior Call Path routed
through `export_history()` and direct `stamp_page_shell()` stamping; both
were wrong (see D2 and D5)._

`main_artifact()` (`cli/artifact/__init__.py`)
→ `cmd_dashboard(args, logger)`
→ `BRConfig(Path.cwd())` → `config.artifacts.export` (mode / allowlist / allowlist_version / max_artifact_bytes)
→ resolve `--tables` type names through `_EXPORT_TABLE_MAP` to `(table, ts_col)`; intersect with the effective ENH-075 column allowlist (in `shareable` mode `--tables` selects from the allowlist and cannot widen it)
→ open source DB read-only (`file:.ll/history.db?mode=ro`), `ATTACH` a scratch file DB, `CREATE TABLE snap.<table> AS SELECT <allowlisted cols> FROM <table> [WHERE <ts_col> >= ?]` per selected type (**D2** — no `VACUUM`, no index stripping: a freshly created DB has neither)
→ default `--tables` to the shareable types (`loop_run,usage_event`) when the flag is absent (**D16**); the raw `sqlite3.connect("file:…?mode=ro", uri=True)` is deliberate — the store's normal open path migrates on open (`schema.py:1340-1382`) and would mutate the user's DB (**D19**)
→ pre-check `dest.stat().st_size` against `max_artifact_bytes` and fail here if the raw snapshot alone already exceeds it, naming `--since` (**D16** — the D7 final-HTML check still runs, this is only the cheap early exit)
→ read the source DB's recorded `schema_version` via `SELECT value FROM meta WHERE key = 'schema_version'` on that same read-only connection (no public accessor exists — `_current_version()` is private, **D19**) and compare against `SCHEMA_VERSION` (`session_store/schema.py:25`); warn visibly on divergence (**D11** — the `meta` table is *not* copied into the snapshot, so the version must be read here and passed in `data`)
→ read scratch DB bytes → `gzip.compress()` → `base64.b64encode()` (**D1**)
→ read vendored `sql-wasm.wasm` → base64 (**D8**: 658,410 B → 877,880 B). The `sql-wasm.js` glue is UTF-8 text and rides in the template's `assets/` as `ll.assets['sql-wasm.js']`, not through base64 (**D10**)
→ resolve the packaged `dashboard.llat` via `importlib.resources` (**D9**), converting the `Traversable` with `Path(str(...))` and calling `load_manifest(root)` directly rather than `resolve_template()`, whose `templates_dir` fallback is project-local and can only mislead here (**D20**)
→ `validate_top_level_data(data, manifest["data_schema"])` — the renderer does **not** do this; `cmd_render` does it at `render.py:119` and `cmd_dashboard` must too (**D14**)
→ `render_template(template, data, config)` with `data` carrying: the gzip+base64 snapshot, the base64 WASM, export timestamp, filter args, export mode, allowlist version, source + installed schema versions (**D5** — only the WASM cannot go in `assets/`, which is UTF-8-text-only; the glue can, **D10**)
  — `manifest.yaml` declares `theme: design-tokens`, so `build_ll_namespace()` supplies `ll.theme_css` via `themed_css_vars()` implicitly; `cmd_dashboard` never calls `stamp_page_shell()` itself
→ measure `len(rendered_html)`; if `> config.artifacts.export.max_artifact_bytes`, log the measured size and the limit and `return 1` **without writing a file** (**D7**)
→ write single HTML to `--output` (a **directory**, matching `render.py:58-62`) or `config.artifacts.promotion_dir`, under the manifest's declared `output:` filename `history-dashboard.html` (**D15** — not `default_output_dir`, which is `"."` and would drop ~5 MB into the project root)

### Decision Rules

- **Size ceiling** — hard-fail before write, measured on final rendered
  HTML bytes against `artifacts.export.max_artifact_bytes` (default
  `8000000`). Matches every existing size ceiling in this codebase
  (`templatize_max_input_bytes`, `templatize.py:846-854`); no warn-only or
  auto-narrow ceiling exists here and this issue does not add the first.
  See **D7**.
- **`VACUUM` / index stripping** — not performed. Resolved by the
  `CREATE TABLE … AS SELECT` construction (**D2**), which produces a DB
  with no indexes and no free pages by definition.
- **Mode → allowlist** — `shareable` (default) projects only the ENH-075
  columns; `--local` lifts the column projection for personal use. In local
  mode `--tables` may select any `_EXPORT_TABLE_MAP` type (`SELECT *` for
  types without a `_SHAREABLE_COLUMNS` entry); the default table set stays
  `loop_run,usage_event` in both modes (**D22**). Both modes stamp the mode
  and allowlist version into the page (**D6**, AC).
- **Write rejection** — `PRAGMA query_only = 1` at every instantiation is the
  enforcement; the submitted-text check (single statement, no `PRAGMA`) exists
  for the error message. A leading-`SELECT` check alone is insufficient
  (**D6**, measured).
- **Schema-version divergence** — export-time comparison and a visible
  warning; never a view-time check (**D11**).
- **`--since` on `loop_run`** — `COALESCE(ended_at, started_at)`, so in-flight
  runs are not silently dropped; whichever semantics is chosen is stated in
  the CLI help and the page's filter stamp (**D13**).
- **Flag defaults** — `--tables` defaults to the shareable types
  (`loop_run,usage_event`), never `_EXPORT_DEFAULT_TABLES`; `--since` has no
  default and every size failure names it as the remedy (**D16**).
- **Data validation** — the caller validates, not the renderer
  (`render.py:119` is the precedent, `render_template()` does not) (**D14**).
- **Escaping** — `autoescape=False`, so every value in `data` is validated or
  escaped by `cmd_dashboard` before it goes in (**D18**).
- **Result rows** — capped at the render step with a truthful total via
  `prepare()`/`step()` (rows collected only up to the cap, stepping continues
  to count); the user's SQL is never rewritten (**D17**, amended).
- **Source DB** — opened raw read-only and never through the migrating open
  path, so an export cannot mutate `history.db` (**D19**).

## Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Resolve the Program Design contradiction first: decide whether `cmd_dashboard` routes through `render_template()`/`resolve_template()` or stays a `policy_builder.py`-style direct stamp.~~ **Resolved 2026-08-25 by D5**: real `.llat/` template through `render_template()`; the WASM rides in `data`, not `assets/` (which is UTF-8-text-only). § Call Path and § Signatures updated to match.
- ~~Add a column-allowlist wrapper around `export_history()`.~~ **Corrected 2026-08-25 by D2**: a *sibling* snapshot builder sharing `_EXPORT_TABLE_MAP`, not a wrapper — `export_history()` yields dicts and cannot produce the SQLite file `sql.js` needs. `TestExportTableRegistration` (`test_session_store_queries.py:209-257`) and the `session_id` projections at `test_session_store_queries.py:167,206` are untouched by construction, since `export_history()` is not modified at all.
- Implement the gzip+base64 encoding (D1) and the `DecompressionStream('gzip')` inflate in-page; initialize `sql.js` with `wasmBinary` (the `file://` `locateFile` fetch is blocked). Both proven — see `.ll/learning-tests/sqljs.md`
- Ship the `dashboard.llat` template inside the package and resolve it via `importlib.resources` (**D9**); register every template file *and* both vendored sql.js files in `PACKAGE_DATA_ASSETS` as one tuple each
- Land `_SHAREABLE_COLUMNS` / `_SHAREABLE_ALLOWLIST_VERSION` beside `_EXPORT_TABLE_MAP` (**D12**) with the version-bump lockstep test
- Read and stamp the source `schema_version` vs installed `SCHEMA_VERSION` at export time (**D11**); the `meta` table is not in the snapshot
- Honour the frozen Jinja environment's non-default delimiters `[[= =]]` / `[[% %]]` in the template body (**D10**) — inline JS must not contain a literal `[[=` or `[[%`
- Update `scripts/little_loops/cli/artifact/__init__.py:1-24` module docstring with a `dashboard` bullet (FEAT-3304 tag) and add a matching `Examples:`/exit-code entry to `main_artifact()`'s epilog (`__init__.py:71-104`)
- Update `docs/reference/CLI.md` (`dashboard` subcommand table row + subsection) and `docs/reference/CONFIGURATION.md:912-929` (`export` key row/JSON example)
- Write the round-trip test: extract the embedded blob from the generated HTML, base64-decode, **gunzip** (per D1), open as SQLite, and assert on the recovered *schema* that excluded columns/tables are absent — no existing test in the repo does this, and an assert-absent substring check is not sufficient for the AC
- Add the `artifacts.export.max_artifact_bytes` hard-fail test (D7) and the mode/allowlist-version stamp test for both `shareable` and `--local` (AC)
- Call `validate_top_level_data()` in `cmd_dashboard` before `render_template()` (**D14**) — `render_template()` does not validate, and the dashboard manifest's `data_schema` is unenforced without this
- Declare `output: history-dashboard.html` in the dashboard `manifest.yaml` and default the output directory to `config.artifacts.promotion_dir`, not `default_output_dir` (**D15**); `--output` names a *directory*, matching `render.py:58-62`
- Default `--tables` to `loop_run,usage_event` and add the raw-snapshot size pre-check with a `--since`-naming error (**D16**)
- Implement the page's result-row cap with a truthful "showing N of M" line, without rewriting submitted SQL, using `prepare()`/`step()` so at most cap rows are materialized (**D17**, amended)
- Grep the vendored `sql-wasm.js` for a literal `</script>` at vendoring time and add the assert-absent test (**D23**); fall back to base64-embedding the glue if a future version hits
- Add the D13 `COALESCE` test: an `ended_at IS NULL` run started inside the window appears in the recovered snapshot
- Read `schema_version` inline on the read-only connection; never route the export through the store's migrating open path, and add the before/after DB-hash test (**D19**)
- Convert the `importlib.resources` `Traversable` with `Path(str(...))` and call `load_manifest()` directly instead of `resolve_template()` (**D20**)
- Add `TestSchemaValueParity`'s `"ArtifactsConfig": "artifacts"` parity coverage (`test_config_schema.py:1343`) for the new `export` field, alongside the `test_artifacts_in_schema`/`test_analytics_in_schema` nested-block assertions already scoped

## Confidence Check Notes

**Readiness: 97/100 — Learning Test Hard Override CLEARED 2026-08-25.**
**Outcome Confidence: 69/100** (unchanged as a score; the two risk factors
below are narrowed, not eliminated — see the resolution note).

### Gaps to Address

- ~~**Learning test hard override.** `learning_tests_required` names `sql.js` and
  `jinja2`. `jinja2` is proven (5/0/0, 2026-08-23). `sql.js` has **no record at
  all** in the Learning Test Registry (`ll-learning-tests check sql.js` →
  "no record found"). Every AC and Decision (D1, D6, "wasmBinary is mandatory")
  depends on specific `sql.js` runtime behavior over `file://`
  (`DecompressionStream('gzip')` interop, `wasmBinary` init bypassing
  `locateFile`, write-statement rejection, in-memory DB reset) that is asserted
  in prose but not yet proven against the actual vendored binary. This is an
  external third-party API surface (per the Confidence Check skill's exclusion
  heuristic), so the remedy is `/ll:explore-api sql.js` (or an equivalent
  learning-test spike) before implementation, not a spike routed through
  `set-flags`.~~
  **Resolved 2026-08-25**: `.ll/learning-tests/sqljs.md` — status `proven`,
  10 claims `pass`, 1 `untested`, against sql.js 1.14.2 under node v22.22.3
  (raw output at `.ll/learning-tests/raw/sqljs.txt`). It proved `wasmBinary`
  init with zero `fetch()`, `DecompressionStream('gzip')` byte-exact
  round-trip, snapshot open + column projection, `PRAGMA query_only`
  enforcement, reset-by-re-instantiation, and the ~924 KB fixed floor — and
  **refuted** two things the issue had assumed: that a leading-`SELECT` check
  suffices (it does not; `db.exec()` runs every `;`-separated statement) and
  that the floor is ~2 MB. D6 and D8 were rewritten accordingly.
  *The one `untested` claim* is that the same behaviour holds in a browser
  over `file://` — the proof ran under Node, which exercises the same sql.js
  build and the same `DecompressionStream` API but is not the shipping
  environment. First implementation step should be to open a generated
  artifact in a real browser over `file://` before building out the UI.
  The **ATTACH-from-`mode=ro`** assumption in D2 was separately proven by
  spike (see D2's proof note).

### Outcome Risk Factors

- **Complexity (14/25).** Breadth spans 7+ files across four subsystems
  (config schema/dataclass, CLI dispatch, `session_store/queries.py`,
  `package_data.py`, the `.llat` template pipeline, docs). Depth includes the
  codebase's first vendored binary asset, first base64/gzip embedding into a
  self-contained artifact, and first client-side WASM query engine — none of
  which have an existing pattern to copy end-to-end even though each piece
  individually cites a precedent.
- **Test Coverage (15/25).** The Tests/Wiring sections cite strong per-piece
  precedents (`test_artifacts_in_schema`, `TestExportTableRegistration`,
  `test_package_data_manifest.py`), but the AC's own "gunzip + base64-decode +
  open as SQLite + assert schema" round-trip test has **no existing test in
  the repo to model** — confirmed by the issue's own wiring pass. This is
  novel test-authoring, not a copy of an established pattern.

### Confidence factors (not gaps)

- Program Design gate passes (`ll-issues check-design` clean); the
  Program-Design contradiction the wiring pass originally flagged was
  resolved by D5 and the Call Path/Signatures were rewritten to match.
- Both `depends_on` edges (ENH-3035, FEAT-3309) are `status: done`.
- `CLAIM_GAP` (`ll-artifact dashboard`, `ll-artifact render --local`,
  `ll-artifact serve` not found in the codebase) is expected — these are the
  subcommand/flags this issue itself introduces, not stale references.
- `STRUCT_GAP` flags a missing `## Summary` header, but the issue opens with
  an equivalent summary paragraph directly under the title — cosmetic only.

## Session Log
- `/ll:confidence-check` - 2026-08-25T21:36:37 - `41c23674-8ae1-4ab5-afa3-ad0ce2e1075c.jsonl`
- fourth pre-implementation review - 2026-08-25 - added D21–D23 and amended D13/D17: pinned the `artifacts.export` v1 config shape to `{mode, max_artifact_bytes}` and deferred ENH-075's "additions" field (unversioned local widening would make the allowlist-version stamp ambiguous), stated local-mode table scope (any `_EXPORT_TABLE_MAP` type, `SELECT *`, same defaults), added the `</script>`-in-glue check the Node learning test cannot catch, gave D13 a test, and bounded the result-row cap's memory via `prepare()`/`step()`. Re-verified earlier passes' load-bearing claims against the code in the same review — all hold. Three ACs updated/added
- third pre-implementation review - 2026-08-25 - added D14–D20 and five ACs from re-checking the issue's load-bearing claims against the code: corrected the Background's false "the renderer validates `data.json`" claim (validation is `cmd_render`'s, `render.py:119`) and the packaged-template handoff (`resolve_template()` takes `str`, `importlib.resources` yields a `Traversable`); specified the previously-open output filename/default directory (`promotion_dir`, not the `"."` project root), the `--tables`/`--since` defaults plus a cheap raw-snapshot size pre-check ahead of D7's final-HTML ceiling, the page's result-row cap (~150k rows would hang the tab), the `autoescape=False` escaping ownership rule, and the inline `schema_version` read with the reason D2's raw `mode=ro` connect matters (the store's normal open path migrates on open). Verified in the same pass: every ENH-075 allowlist column exists in the live schema, and D9's `importlib.resources` precedent is real
- second pre-implementation review - 2026-08-25 - cleared the learning-test hard override (`/ll:explore-api sql.js` → `.ll/learning-tests/sqljs.md`, proven), proved D2's ATTACH-from-`mode=ro` construction by spike, rewrote D6 (`PRAGMA query_only` + multi-statement check; a leading-`SELECT` check was measured insufficient) and D8 (measured ~924 KB floor, not ~2 MB), and added D9–D13: packaged `.llat` resolution via `importlib.resources`, the frozen Jinja delimiter/autoescape constraints, export-time schema-version comparison (the prior view-time AC was not implementable), the allowlist-constant + version-bump rule, and `COALESCE(ended_at, started_at)` for `--since`
- `/ll:confidence-check` - 2026-08-25T20:56:17 - `57fafff8-bb8c-4f8b-a447-cf4d8ece9758.jsonl`
- pre-implementation review - 2026-08-25 - added Decisions D1–D8 (measured a real 30-day export against the live 6.6 GB `.ll/history.db`: 17.4 MB raw / 23.3 MB base64 / 4.1 MB gzip+base64), resolved the Program Design contradiction toward the `.llat` pipeline, corrected the `export_history()` call path, retired the FEAT-3036 schema-collision concern, and added five ACs (mode/allowlist stamp, schema version, predefined view, size hard-fail, provenance path)
- `/ll:wire-issue` - 2026-08-25T20:20:31 - `c8f2587f-3ca1-4ca9-b1e5-e2886b741049.jsonl`
- `/ll:refine-issue` - 2026-08-25T20:03:01 - `2733569a-0f64-4a8b-99df-20a4c329cea3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-24T16:12:08 - `69c375ac-5c89-44f2-a3fc-ad8aa6520c60.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-24T16:09:47 - `e9d09067-3305-47ef-b629-2fdf32a510b0.jsonl`
