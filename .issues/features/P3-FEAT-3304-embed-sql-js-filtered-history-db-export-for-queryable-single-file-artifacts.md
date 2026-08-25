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
  in the page.
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
  the only code that reads it. Expect to hit the same
  `additionalProperties: false` blocker FEAT-3036's `templates_dir` change opens
  up — coordinate so the two schema edits do not collide.

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
      rejected client-side.
- [ ] Export scope honours the ENH-075 rules; a test asserts that
      excluded columns/tables are absent from the embedded blob (not
      merely hidden in the UI).
- [ ] The export timestamp and the filter arguments are visible in the
      rendered page.
- [ ] An export exceeding the defined size budget behaves as specified,
      with a test.
- [ ] The artifact is rendered through the ENH-3035 template kit; no
      template code is copied from `policy-builder`.
- [ ] `sql.js` version, source, and license are recorded in-repo.
- [ ] `.ll/ll-config.json` accepts an `artifacts.export` block — schema updated,
      round-tripped by `BRConfig`, and covered by a test that an unknown key is
      still rejected.

## Dependencies

- **ENH-075** — export scope/redaction rules must be decided before
  the export filter is implemented. *Decided 2026-07-31; see Decisions
  section above.*
- **ENH-3035** — should land alongside or just before, so this artifact
  is the kit's first consumer rather than a second copy of
  `policy-builder`.

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
- New `ArtifactsExportConfig`-shaped nested block on `ArtifactsConfig` (`scripts/little_loops/config/features.py:369-403`) — mode: `str` (`"shareable"` default | `"local"`), allowlist additions, and an allowlist version marker, mirroring the two-level nesting `AnalyticsCaptureConfig` already uses (`config/core.py:340-342`)
- The shareable allowlist itself is a `table -> [columns]` mapping; the closest existing typed precedent for a table-name allowlist is `_EXPORT_TABLE_MAP: dict[str, tuple[str, str]]` (`session_store/queries.py:89-110`), which maps a public type name to `(table_name, timestamp_column)` — column-level projection has no existing type to extend

### Signatures
- `ArtifactsConfig.from_dict(cls, data: dict[str, Any]) -> ArtifactsConfig` (`config/features.py:396`) — extend to read `data.get("export", {})`
- `BRConfig.to_dict()` (`config/core.py:917-922`) — extend with the new field, per the `templatize_max_input_bytes`/`promotion_dir` precedent
- `export_history(db, *, tables=None, since=None, include_messages=False) -> Generator[dict, None, None]` (`session_store/queries.py:151-211`) — existing table+`--since` filtering for `loop_runs`/`usage_events`; does `SELECT *` with no column projection, so ENH-075's column allowlist needs a new wrapper, not a modification of this function's existing callers (`ll-session export` in `cli/session.py`)
- `cmd_dashboard(args: argparse.Namespace, logger: Logger) -> int` / `add_dashboard_parser(subparsers) -> None` (new, `cli/artifact/dashboard.py`) — following the exact `(argparse.Namespace, Logger) -> int` contract used by `cmd_render` (`render.py:72-168`) and `cmd_status` (`status.py:119-165`): builds `config = BRConfig(Path.cwd())` inside the function body, wraps the body in `except Exception as exc: logger.error(str(exc)); return 1`
- `stamp_page_shell(template_text: str, *, active_theme: str, css_vars: str) -> str` and `themed_css_vars(config: object) -> str` (`artifact_template_kit.py:18,52`) — the two shared kit functions this dashboard template calls; artifact-specific stamping (the sql.js WASM blob, the base64 DB snapshot) follows the same `.replace("/*__NAME__*/", ...)` pattern used by `policy_builder.py:77-94`, applied after the shared kit call

### Call Path
`main_artifact()` (`cli/artifact/__init__.py`) → `cmd_dashboard(args, logger)` → `BRConfig(Path.cwd())` → `config.artifacts.export` (mode/allowlist/allowlist_version) → filtered row selection over `loop_runs`/`usage_events` (table+`--since` windowing reuses `export_history()`'s `_EXPORT_TABLE_MAP` shape; column-level projection per the ENH-075 allowlist is new) → `VACUUM`/index-stripping decision (open, see Must address) → base64-encode the filtered DB snapshot + vendored sql.js WASM → `themed_css_vars(config)` + `stamp_page_shell(template, active_theme=..., css_vars=...)` → dashboard-specific `.replace()` stamping of the two base64 blobs and the export timestamp/filter-args placeholders → write single HTML to `config.artifacts.default_output_dir`

### Decision Rules
N/A — no new decision logic has been finalized by research. The size-budget policy (fail/warn/auto-narrow) and the VACUUM/index-stripping choice remain open decisions under § Must address → Snapshot size; research found no existing warn/auto-narrow precedent anywhere in this codebase (every existing size-ceiling field is hard-fail-before-call, e.g. `templatize_max_input_bytes` at `templatize.py:846-854`), which narrows but does not resolve the choice — left for implementer/decision, not fabricated here.

## Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Resolve the Program Design contradiction first (see Integration Map → Dependent Files): decide whether `cmd_dashboard` routes through `artifact_templates.py`'s `render_template()`/`resolve_template()` (a real `.llat/` template, `manifest.yaml` with `theme: design-tokens`) or stays a `policy_builder.py`-style direct `stamp_page_shell`/`themed_css_vars` + `.replace()` stamp — then update Program Design § Call Path/Signatures to match, since the AC "rendered through the ENH-3035 template kit; no template code is copied from `policy-builder`" is only verifiable once this is settled
- Add a column-allowlist wrapper around `export_history()`/`_EXPORT_TABLE_MAP` as a new function or kwarg, not a restructure of the existing module-level dicts, to avoid breaking `TestExportTableRegistration` (`test_session_store_queries.py:209-257`); keep `session_id` in scope for `context_pressure_event`/`advisor_consult_event` projections so `test_session_store_queries.py:167,206` keep passing
- Update `scripts/little_loops/cli/artifact/__init__.py:1-24` module docstring with a `dashboard` bullet (FEAT-3304 tag) and add a matching `Examples:`/exit-code entry to `main_artifact()`'s epilog (`__init__.py:71-104`)
- Update `docs/reference/CLI.md` (`dashboard` subcommand table row + subsection) and `docs/reference/CONFIGURATION.md:912-929` (`export` key row/JSON example)
- Write the base64-round-trip test (decode the embedded blob out of generated HTML, compare to source bytes) — no existing test in the repo does this; the AC's exclusion test needs it, not just an assert-absent check
- Add `TestSchemaValueParity`'s `"ArtifactsConfig": "artifacts"` parity coverage (`test_config_schema.py:1343`) for the new `export` field, alongside the `test_artifacts_in_schema`/`test_analytics_in_schema` nested-block assertions already scoped

## Session Log
- `/ll:wire-issue` - 2026-08-25T20:20:31 - `c8f2587f-3ca1-4ca9-b1e5-e2886b741049.jsonl`
- `/ll:refine-issue` - 2026-08-25T20:03:01 - `2733569a-0f64-4a8b-99df-20a4c329cea3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-24T16:12:08 - `69c375ac-5c89-44f2-a3fc-ad8aa6520c60.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-24T16:09:47 - `e9d09067-3305-47ef-b629-2fdf32a510b0.jsonl`
