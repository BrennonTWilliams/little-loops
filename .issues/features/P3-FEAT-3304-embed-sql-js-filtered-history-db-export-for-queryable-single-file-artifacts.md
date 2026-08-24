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
---

# FEAT-3304: Embed sql.js + filtered history.db export for queryable single-file artifacts

Extend `ll-artifact` from a pre-baked-JSON stamper into a real client-side
query engine: inline `sql.js` (SQLite-to-WASM) plus a filtered/date-scoped
export of `.ll/history.db` (e.g. `ll-artifact dashboard --tables
loop_runs,usage_events --since 30d`) as base64 into the HTML. The page
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
and optional `assets/`. The renderer is **deterministic and LLM-free**:
it validates `data.json` against the manifest's `data_schema`, renders
the Jinja2 body, then stamps themed CSS vars via the existing
`load_design_tokens` / `render_as_css_vars_themed` machinery that
`policy-builder` already uses. Output lands in
`config.artifacts.default_output_dir`.

**Template language: Jinja2, not invented.** The current `.replace()`
token scheme cannot express repeated regions or conditionals, and any
source with a variable number of sections needs loops. Jinja2 is boring,
ubiquitous, sandboxable (`SandboxedEnvironment`), and Python-native.
`policy-builder` can migrate to it later or stay as-is — for this
issue, the dashboard template is the first new consumer and is built on
the shared template kit (per ENH-074), not a copy of `policy-builder`.

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
  in the page.
- Inlined `sql.js` (WASM) so the page runs arbitrary read-only SQL
  against the embedded snapshot with no network access and no build
  step at view time.
- A minimal query surface in the page: run a query, render a table,
  and at least one predefined view so the artifact is useful without
  the user writing SQL.
- Built on the shared template kit (per ENH-074), not a copy of the
  `policy-builder` template.

## Non-goals

- Any live/bridge behaviour — that is FEAT-067. The artifact must be
  fully functional and honest about its staleness in snapshot-only mode.
- Any write path or command execution — that is FEAT-068.
- Migrating `policy-builder` to Jinja2, or implementing the manifest /
  `render` system in the design doc. See *Open questions* below.

## Must address

- **Snapshot size.** A 30-day `usage_events` export can be large, and
  base64 inflates it ~33%. Define a size budget, what happens when an
  export exceeds it (fail, warn, auto-narrow), and whether the
  exported DB is `VACUUM`ed and/or stripped of indexes before encoding.
- **Staleness.** The page must display the export timestamp and the
  filter that produced it, prominently. A shared dashboard that
  silently shows month-old numbers is worse than no dashboard.
- **Schema coupling.** The page's queries are written against
  `history.db`'s schema. Decide whether the artifact pins/records a
  schema version and how it behaves against an export it wasn't built
  for.
- **`sql.js` provenance.** The WASM blob is a vendored third-party
  binary inlined into every artifact. Record where it comes from, its
  version, its license, and how it is updated — this is a supply-chain
  surface, not an asset.
- **Read-only enforcement** in the page, so a stray `DELETE` in the
  query box can't corrupt the in-memory DB mid-session and confuse the
  user.

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

## Acceptance Criteria

- [ ] `ll-artifact <dashboard-cmd> --tables … --since …` produces a
      single HTML file that opens over `file://` with no network access
      and no external assets.
- [ ] The page executes user-entered read-only SQL against the
      embedded snapshot and renders results; write statements are
      rejected client-side.
- [ ] Export scope honours the ENH-075 rules; a test asserts that
      excluded columns/tables are absent from the embedded blob (not
      merely hidden in the UI).
- [ ] The export timestamp and the filter arguments are visible in the
      rendered page.
- [ ] An export exceeding the defined size budget behaves as specified,
      with a test.
- [ ] The artifact is rendered through the ENH-074 template kit; no
      template code is copied from `policy-builder`.
- [ ] `sql.js` version, source, and license are recorded in-repo.
- [ ] `.ll/ll-config.json` accepts an `artifacts.export` block — schema updated,
      round-tripped by `BRConfig`, and covered by a test that an unknown key is
      still rejected.

## Dependencies

- **ENH-075** — export scope/redaction rules must be decided before
  the export filter is implemented. *Decided 2026-07-31; see Decisions
  section above.*
- **ENH-074** — should land alongside or just before, so this artifact
  is the kit's first consumer rather than a second copy of
  `policy-builder`.
