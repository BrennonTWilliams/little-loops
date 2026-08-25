---
id: ENH-3035
title: Factor a shared artifact template kit out of the policy-builder template
type: ENH
priority: P3
status: done
discovered_date: 2026-08-03
completed_at: '2026-08-25T16:14:52Z'
labels:
- artifact
- ll-artifact
parent: EPIC-3299
relates_to:
- FEAT-3308
- FEAT-3309
- FEAT-3304
- FEAT-3036
verify_verdict: VALID
learning_tests_required:
- jinja2
confidence_score: 90
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3035: Factor a shared artifact template kit out of the policy-builder template

## Summary

Extract the reusable parts of the policy-builder HTML template into a small shared
template kit — page shell, design-token stamping, and the common head/asset-inlining
path — so the sql.js dashboard, templatized loop artifacts, and future artifacts build
on one set of conventions instead of each copying and drifting from policy-builder.
This is a refactor with a known shape, not an open design question; it was bundled
into the policy-builder template's decision gate and is split out because it pays
off the moment a second artifact template exists.

## Current Behavior

Each artifact template (currently only `policy-builder`) owns its own copy of the
page shell, design-token stamping, and head/asset-inlining logic inline. Design-token
stamping (`_themed_css_vars`) lives inside
`scripts/little_loops/cli/artifact/policy_builder.py`, and `artifact_templates.py`'s
`build_ll_namespace()` already reaches back into that CLI-command module to reuse it —
the general-purpose module depends on the single-consumer one, backwards from the
intended shape.

## Expected Behavior

A shared template kit module exists as the single home for the page shell,
design-token stamping (a separately callable unit), and the head/asset-inlining
path. `policy-builder` is ported onto the kit and renders byte-identically (or with
reviewed, intentional diffs) to its pre-port output. At least one templatized
loop-generated artifact also renders through the kit, so it's validated against the
epic's actual workload, not just the policy-builder dashboard shape.

## Motivation

The parent epic exists in part to stop artifacts "accreting inconsistent per-artifact
conventions." Deferring this refactor until the Tier-3 gate guarantees exactly that:
the sql.js dashboard and each subsequent artifact ship a template copied from
policy-builder, and the kit is then extracted from several divergent copies rather
than one.

_(Earlier revisions of this section named a "loop-fleet dashboard" as a second
motivating consumer. No such artifact exists or is planned — the name collides
with the unrelated `ll-logs` loop-fleet **harvester** (`cli/logs.py`), a telemetry
feature with no artifact-rendering surface. Removed to stop implementers chasing
it.)_

## Design Context

The artifact-templates design generalizes the policy-builder pattern: a `manifest.yaml`
+ Jinja2 body + assets layout under `.llat/`, with deterministic rendering
(`template + data.json → artifact`) and a separation of refinement (paid once at
template creation) from regeneration (cheap).

The template kit is the implementation vehicle for that design's shared parts: the
page shell, design-token stamping (via existing `load_design_tokens` /
`render_as_css_vars_themed`), and the head/asset-inlining path that policy-builder
currently does inline.

## Scope

- Identify what in the policy-builder template is genuinely artifact-agnostic
  (shell, token stamping, inlining) versus policy-builder-specific.
- Extract the agnostic parts into a template kit with a stable entry point.
- Pull design-token stamping out as its own unit, so token changes land in one place.
- Port policy-builder onto the kit — the refactor is not done until its sole
  existing consumer uses it.

## Non-goals

- Restyling or redesigning any existing artifact.
- Introducing a template engine or build step; artifacts stay single-file and
  dependency-free at view time.

## Scope Boundaries

- Out of scope: building the sql.js dashboard (FEAT-3304) or porting it onto the
  kit — that obligation lives on FEAT-3304's own AC, not here (see "Not an AC
  here" above and Sequencing below).
- Out of scope: `templatize.py` changes to auto-lift baked-in token literals into
  `var(--…)` references (the rejected "broad reading" in Decisions) — that is
  separate feature work to be filed as its own ENH, not extraction.
- Out of scope: restyling/redesigning any existing artifact, or introducing a
  template engine/build step (see Non-goals above).

## Acceptance Criteria

- [x] A shared template kit module exists with a documented entry point.
- [x] Design-token stamping is a separately callable unit, not inlined in a template.
- [x] A golden HTML fixture of `cmd_policy_builder`'s output is captured **before**
      the port, on a project with `design_tokens` configured (this repo's
      `warm-paper` + `dark` config exercises the themed path, so the fixture covers
      the token-stamping branch rather than the degraded empty-block branch).
- [x] policy-builder renders byte-identically to that fixture (or with reviewed,
      intentional diffs) after being ported onto the kit.
- [x] **At least one templatized loop-generated artifact renders through the kit**
      (see Consumer mix below). A kit validated only by policy-builder has been
      validated against the wrong workload.
- [x] The kit's token-stamping unit **accepts** a body whose token values were baked
      in as literals by a loop's prompt-time `design_tokens_context` — i.e. stamping
      such a body through the kit succeeds without error rather than requiring a body
      authored with stamp points. This is the **narrow** reading: a test-level
      guarantee, no `templatize.py` changes (see Decisions below).

**Not an AC here:** "the sql.js dashboard is built on the kit." FEAT-3304 is still
open with no code, and that obligation is already recorded as an AC *on FEAT-3304*
("The artifact is rendered through the ENH-3035 template kit; no template code is
copied from `policy-builder`"). Duplicating it here would make this issue
unsatisfiable — it would require either building a throwaway sql.js fixture purely
to check a box, or blocking on FEAT-3304. Treat it as a **sequencing note** (see
Sequencing), not a gate on this issue.

⚠ Superseded: the earlier "hand-templatized fallback if FEAT-3308 hasn't landed"
escape hatch (referenced in Consumer mix) is moot — FEAT-3308 and FEAT-3309 both
landed `status: done` on 2026-08-25, so the third-consumer AC above is satisfied
with a real `ll-artifact templatize` output; do not build the fallback path.

## Decisions

**2026-08-25 — templatize reachability is the narrow reading.** The last AC asks
only that the kit's stamping unit *accept* a body carrying baked-in token literals.
It does **not** ask `templatize` to rewrite those literals into `var(--…)`
references. The rejected broad reading — having `build_manifest()` set
`manifest["theme"] = "design-tokens"` when `_report_unlifted_tokens` finds matching
literals — is actively wrong as stated: it would stamp `theme_css` vars into a body
that still carries the literals, leaving the vars unreferenced *and* the literals
unlifted. That is dead weight, not token lifting. Real literal→`var()` rewriting is
new feature work well beyond "extraction" and belongs in a separate ENH; file it
rather than absorbing it here.

Consequences: `build_manifest()` is unchanged, and
`_write_unlifted_tokens_report()`'s `_comment` string stays accurate as written —
the corresponding Wiring Phase item is void (see the strike-through there).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- On the last AC ("kit's token-stamping unit is reachable from the templatize token-lifting path"): `templatize.py`'s `build_manifest()` (line 519-537) never sets `manifest["theme"] = "design-tokens"`, and `_report_unlifted_tokens` (line 717-740, calling `load_design_tokens` at line 727) only *reports* baked-in color literals matching known tokens via `logger.warning` + `unlifted-tokens.json` — it never rewrites the spliced template body to reference the kit's stamping unit.
  - **Superseded by the 2026-08-25 Decision above.** This note framed the fix as "set `manifest["theme"]` when literals are found" — that option is rejected (it stamps unreferenced vars beside unlifted literals). Under the adopted narrow reading the AC is satisfied by a test proving the kit's stamping unit accepts such a body; `templatize.py` is unchanged, and literal→`var()` rewriting is deferred to a separate ENH.

## Consumer mix (added 2026-08-23)

Both consumers named in the original scope — `policy-builder` and the sql.js
dashboard — are hand-built data dashboards from the same lineage.
`policy-builder` is a 727-line `.tmpl` rendered by **five** sequential
`str.replace()` calls (`cli/artifact/policy_builder.py:124-129`); the dashboard
will be its sibling. A kit factored from one and validated by the other will
encode dashboard conventions and fit the epic's primary workload — large,
LLM-generated, self-contained artifacts from the HTML loop family — badly or not
at all.

The AC above therefore requires a consumer from that family. **FEAT-3308
(templatize) and FEAT-3309 both landed on 2026-08-25**, so satisfy it with a real
`ll-artifact templatize` output committed as a test fixture. The earlier
"hand-templatized fallback if FEAT-3308 hasn't landed" escape hatch is moot — do
not build that path. The point is that the kit is exercised by a body it did not
author.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- Stale reference: this section's own text cites the `str.replace()` stamping site as "`cli/artifact.py:132-137`" performing "four" replacements. The actual location is `scripts/little_loops/cli/artifact/policy_builder.py:124-129`, and it is **five** sequential `.replace()` calls (`data-theme`, `/*__THEMED_CSS_VARS__*/`, `/*__GRAMMAR_SPEC_JSON__*/`, `/*__SKILL_CATALOG_JSON__*/`, `/*__BUILDER_CORE_JS__*/`), not four.
- Neither named consumer that motivates this issue exists in code yet: `Glob **/.llat/**` and repo-wide grep for `sql.js`/`sqljs`/`sql_js` and `loop-fleet`/`loop_fleet` found no implementation — the sql.js dashboard (FEAT-3304) and the "loop-fleet dashboard" mentioned in Motivation are both still design-only issue text (`.issues/features/P3-FEAT-3304-embed-sql-js-filtered-history-db-export-for-queryable-single-file-artifacts.md`, `.issues/epics/P3-EPIC-3299-artifact-templates-deterministic-render-cheap-refresh-shared-kit.md`). (The unrelated `ll-logs` "loop-fleet harvester" telemetry feature shares the name but is a different concern — `cli/logs.py`.) The AC requiring "The sql.js dashboard's artifact (FEAT-3304) is built on the kit" had no escape hatch analogous to the one already given for FEAT-3308/templatize above.
  - **Resolved 2026-08-25:** that AC is **removed** from this issue rather than given an escape hatch. FEAT-3304 already carries the reciprocal obligation as its own AC ("The artifact is rendered through the ENH-3035 template kit; no template code is copied from `policy-builder`"), so nothing is lost by dropping it here; building a throwaway sql.js fixture just to check the box would be waste. It survives here only as a sequencing note.
- The FEAT-3308 escape hatch in Consumer mix is stale **in this issue's favour**: FEAT-3308 (templatize) and FEAT-3309 are both `status: done` as of 2026-08-25, so a real `ll-artifact templatize` output is available as the third-consumer fixture and the hand-templatized fallback path should not be built.

## Sequencing

Should land alongside or just before the sql.js dashboard — the first new artifact
is the forcing function. Does not gate the write-bridge work. **This issue does not
wait on FEAT-3304**; the "built on the kit" obligation lives on FEAT-3304's own AC,
so ENH-3035 lands first and FEAT-3304 consumes it.

**Blocked on a hub decision (resolved 2026-08-23).** FEAT-3304 flagged that this
kit and FEAT-3036's Phase-1 `render` pipeline overlap, and that extracting the kit
before that is settled means "the kit gets extracted twice." FEAT-3036 now records
the packaging/engine/hash decisions (`.llat/` directory, sandboxed Jinja2,
separate lockfile), which is the fixed target this extraction builds against — the
contradiction the 2026-08-12 verification note flagged between this issue's Design
Context and FEAT-3036's Open Questions is closed in FEAT-3036's favour, matching
what this issue already assumed. Do not start the extraction against a different
shape.

## Verification Notes

**2026-08-12** (`/ll:verify-issues`): Frontmatter `id: 3035` did not match the
`ENH-NNNN` convention used by sibling issue files and has been corrected to
`id: ENH-3035`. Separately, this issue's Design Context presents a
`.llat/`+Jinja2+manifest.yaml packaging layout as settled, but sibling issue
FEAT-3036 (artifact templates design) still lists that packaging shape as an
open question — flagged here as needing reconciliation between the two
issues, not resolved as part of this verification pass.

- 2026-08-16: Issue body content is accurate and current; frontmatter carried a stale `verify_verdict: NON_VALID` left over from a prior --check run that contradicted the accurate body — corrected to `VALID` above. Verdict: NEEDS_UPDATE.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

Extraction targets, dependents, conventions, and behavior-parity obligations found below.

### Files to Modify
- `scripts/little_loops/cli/artifact/policy_builder.py` — `cmd_policy_builder()` (lines 90-142) currently reads `policy-router-builder.html.tmpl` and `policy_builder_core.mjs` from `_TEMPLATES_DIR` and stamps them via five sequential `str.replace()` calls (lines 124-129) — not four as the issue's Consumer mix section states (see stale-reference note below). `_themed_css_vars()` (lines 56-87) is the current single home of "load light+dark tokens, degrade gracefully."
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` (727 lines) — single monolithic file with no `{% include %}`/partials: head/style block (lines 1-116, injection point `/*__THEMED_CSS_VARS__*/` at line 9), body (117-217), data-globals script (129-134), core-logic module script with `/*__BUILDER_CORE_JS__*/` at line 219 followed by ~500 lines of UI glue.
- `scripts/little_loops/templates/policy_builder_core.mjs` (667 lines) — inlined verbatim as raw text at the `/*__BUILDER_CORE_JS__*/` placeholder; no bundler, no minification.
- `scripts/little_loops/artifact_templates.py` — `build_ll_namespace()` (lines 304-311) is the existing partial "kit" for `.llat/` Jinja2 templates: it already imports `_themed_css_vars` back out of `policy_builder.py` when `manifest.get("theme") == "design-tokens"`. This is the one existing coupling point and the specific inversion the kit extraction should undo — today the general-purpose module reaches into the CLI-command module for shared logic, not the reverse.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/__init__.py:38` — `from little_loops.cli.artifact.policy_builder import _themed_css_vars, cmd_policy_builder`; also registers all `ll-artifact` subcommands.
- `scripts/little_loops/artifact_templates.py:304-311` (`build_ll_namespace`) — imports `_themed_css_vars` from `policy_builder.py` conditionally on `manifest["theme"] == "design-tokens"`.
- `scripts/little_loops/cli/artifact/design_md.py:68,92` (`cmd_design_md_export`) — separate caller of `load_design_tokens`, single-theme (no `render_as_css_vars_themed`).
- `scripts/little_loops/cli/loop/_helpers.py:1422` (`inject_design_context`) — caller of `load_design_tokens`, unrelated to artifact rendering.
- `scripts/little_loops/cli/artifact/templatize.py:727` (`_report_unlifted_tokens`) — calls `load_design_tokens(config)` with no `theme` arg (single implicit active theme), for a report-only literal-color scan; does not call `render_as_css_vars_themed` or set `manifest["theme"]`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/__init__.py:55` — `__all__` re-exports `_themed_css_vars` by name (alongside the `:38` import already noted); a rename/relocation to the kit module must update both the import and this `__all__` entry or the re-export silently breaks.
- `scripts/little_loops/cli/artifact/extract.py:29-30,210,265` — imports `ArtifactTemplate` from `artifact_templates.py`, constructs it directly; a peer of the kit's entry point, not currently coupled to `_themed_css_vars` but shares the module the kit extraction touches.
- `scripts/little_loops/cli/artifact/render.py:18-25,64,124` — imports `ArtifactTemplate`, `render_template` from `artifact_templates.py`; same exposure as `extract.py`.
- `scripts/little_loops/cli/artifact/status.py:20` — imports `TemplateResolutionError`, `resolve_template` from `artifact_templates.py`.
- `scripts/little_loops/design_tokens.py` — `DesignTokens.source` field docstring names `cli/artifact/policy_builder.py`'s `_themed_css_vars()` by fully-qualified path ("`_themed_css_vars()` branches on it..."); goes stale once the function moves to the kit module.
- ~~`scripts/little_loops/cli/artifact/templatize.py` — `_write_unlifted_tokens_report()`'s persisted `_comment` string in `unlifted-tokens.json` ("Report-only — not rewritten, and the manifest does not set theme: design-tokens") becomes false once `build_manifest()` starts setting `manifest["theme"] = "design-tokens"` per the last AC — must be rewritten alongside that change.~~ **Void under the narrow reading (Decision 2026-08-25):** `build_manifest()` is not changed, so the `_comment` string stays true as written. Leave it alone.

### Conventions in Force
- New shared modules in this codebase get extracted when a **second consumer** needs the same logic, not proactively — evidence: `render_to_disk()` (`cli/artifact/render.py:36-53`) whose docstring states it "used to live inline in `cmd_render`" and was extracted once `cmd_refresh` (FEAT-3310) needed the same sequence.
- Shared "kit-shaped" modules in `scripts/little_loops/` follow one shape: a dataclass as the core value type plus free top-level functions operating on it, no class wrapping the logic — evidence: `design_tokens.py` (`DesignTokens` + `load_design_tokens()`/`render_as_css_vars_themed()`), `artifact_templates.py` (`ArtifactTemplate` + `render_template()`/`build_environment()`).
- CLI subcommand modules pair a `cmd_*` handler with a same-file `add_*_parser` registration function, called from `cli/artifact/__init__.py:152-156` — evidence: `render.py:171`, `status.py:168`, `extract.py:328,366`, `templatize.py:968`. **Disagreement**: `policy-builder` and `design-md export` do not follow this — their `argparse.add_parser(...)` calls are inline in `cli/artifact/__init__.py:107-150` rather than factored into their own `add_*_parser` functions; `cli/artifact/__init__.py:18-23`'s "one module per subcommand" convention doesn't mention this as a documented exception, so it is a live, undocumented divergence between the older (policy-builder/design-md) and newer (render/status/extract/templatize) subcommands.
- Shared format/logic modules are sometimes authored up front as "single home" rather than extracted from an existing inline implementation — evidence: `lockfile.py:1-8` docstring ("Single home for the lockfile's shape... FEAT-3311's `status` reader... import this module rather than redefining the format").

### Tests
- `scripts/tests/test_policy_builder_emit.py` — policy-builder emission tests; validates golden fixtures through the real pipeline (`load_and_validate`/`validate_fsm`) and asserts structural/regex properties over rendered HTML (`_strip_script_style_comments()`), not whole-file byte comparison.
- `scripts/tests/test_policy_builder_corpus.py`, `scripts/tests/test_policy_builder_node_gate.py` — corpus and Node-side conformance gate for the stamped `policy_builder_core.mjs`.
- `scripts/tests/test_feat3036_artifact_templates.py` — `.llat/` format/renderer tests (the module this kit will sit alongside).
- `scripts/tests/test_artifact_templatize.py` — contains this codebase's only precedent for exact-byte round-trip assertions (`assert out == b"..."`, `test_non_ascii_round_trips`, `verify_round_trip()`), relevant to the "renders byte-identically" AC — no existing test does `assert new_html == old_html_captured_before_refactor` for policy-builder specifically.
- `scripts/tests/test_design_tokens.py`, `scripts/tests/test_verify_design_tokens.py` — design-token unit/verification tests.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat3036_artifact_templates.py:332-343` (`test_theme_css_stamped_via_design_tokens_path`) — **will break**: patches `"little_loops.cli.artifact.policy_builder._themed_css_vars"` by string path; a relocation to the kit module leaves this patch targeting a stale path (silent no-op, not an error) while `build_ll_namespace`'s real `from ... import` resolves the new location — update the patch target alongside the move.
- `scripts/tests/test_design_tokens.py:664,673,682` (`test_design_md_source_no_crash_and_both_blocks_present`, `test_design_md_source_warns_exactly_once`, `test_profile_source_still_makes_two_calls`) — import `_themed_css_vars` via the re-export at `little_loops.cli.artifact` (not `.policy_builder` directly); survive only if `cli/artifact/__init__.py`'s re-export is preserved/repointed at the new kit module.
- `scripts/tests/test_feat3310_artifact_extract.py:15,204,254` — imports and constructs `ArtifactTemplate` directly to exercise `extract.py`; no direct coupling to `_themed_css_vars` but shares `artifact_templates.py`, the module the kit's entry point sits beside.
- No existing test snapshots policy-builder's pre-refactor output for byte-identical post-refactor comparison — closest precedent is `test_artifact_templatize.py:403-440` (`test_end_to_end_round_trip`)'s `assert (render_out / "index.html").read_bytes() == artifact.read_bytes()` pattern. A new test following that shape (capture `cmd_policy_builder`'s output bytes pre-port as a golden fixture, assert equality post-port) is needed to satisfy the "renders byte-identically (or with reviewed, intentional diffs)" AC — no golden HTML fixture currently exists for policy-builder's emitted page (only YAML input fixtures under `scripts/tests/fixtures/policy_builder/`).

### Documentation
- `docs/reference/CLI.md` (`### ll-artifact`, line 4455) — subcommand reference sections for `policy-builder`, `design-md export`, `render`, `templatize`, `extract`, `refresh`, `status`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `design_tokens` section's "Not supported from DESIGN.md" bullet names `_themed_css_vars` verbatim ("only `_themed_css_vars`, used by `ll-artifact` HTML generators"); `### artifacts` section intro paragraph narrates policy-builder as the thing that "stamps design-token CSS vars... into a `file://`-safe policy-router / rubric loop builder page" — both describe stamping as policy-builder-owned, which the kit extraction changes.
- `docs/ARCHITECTURE.md:1029,1031` — describes the "project-enriched artifacts" pattern and templatize round-trip design, naming `policy_builder.py`'s current role.

### Behavior Parity
| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `scripts/little_loops/cli/artifact/policy_builder.py::cmd_policy_builder` | Reads `.tmpl`+`.mjs`, stamps 5 placeholders via `str.replace()`, writes HTML unconditionally | PRESERVED (target) | AC requires byte-identical or reviewed-diff output after porting onto the kit |
| `scripts/little_loops/cli/artifact/policy_builder.py::_themed_css_vars` | Loads light+dark tokens, degrades to neutral empty-CSS-block on `None` | PRESERVED (target) | Becomes the kit's token-stamping unit; same degrade behavior must hold |

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

Concrete types, signatures, and the call path the kit extraction touches, below.

### Types
- `DesignTokens` (`design_tokens.py:28-45`, frozen dataclass) — `primitives`, `semantic`, `theme` (nested dicts), `resolved` (flat dotted-name → value), `source_path`, `guidance`, `source` (`"profile"` | `"design_md"`). Existing type the kit's token-stamping unit wraps; not modified by this issue unless the unit needs a new parameter.
- `ArtifactTemplate` (`artifact_templates.py`, plain dataclass) — the `.llat/` template's in-memory representation; the kit's entry point should be a peer of this, not a subclass or wrapper around it.

### Signatures
- `_themed_css_vars(config: object) -> str` (`cli/artifact/policy_builder.py:56-87`) — current single home of "load light+dark tokens, degrade gracefully to neutral empty-CSS-block on `None`, return themed CSS var blocks." This is the concrete function the kit's token-stamping unit factors out of.
- `load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None` (`design_tokens.py:412-569`) — resolves `design_tokens.source` into a `DesignTokens` or `None` on degrade; raises `ValueError` only for circular/unknown token references on a `profile` source (a `design_md` source catches that internally).
- `render_as_css_vars_themed(light: DesignTokens, dark: DesignTokens) -> str` (`design_tokens.py:688-707`) — builds `:root {...}` / `[data-theme=dark] {...}` blocks, skipping `_`-prefixed metadata keys in `resolved`.
- `build_ll_namespace(root: Path, manifest: dict[str, Any], config: object) -> dict[str, Any]` (`artifact_templates.py:304-311`) — the existing `.llat/` render-context builder; currently imports `_themed_css_vars` from `policy_builder.py` when `manifest["theme"] == "design-tokens"`. The kit's stamping unit is the natural replacement for that inline import, called from both `build_ll_namespace` and a ported `cmd_policy_builder`.

### Call Path
`cmd_policy_builder` -> `_themed_css_vars` -> `load_design_tokens` (light, then conditionally dark) -> `render_as_css_vars_themed` -> stamped into `.tmpl` at `/*__THEMED_CSS_VARS__*/`

Existing inverted coupling to unwind: `artifact_templates.build_ll_namespace` -> (imports) `cli/artifact/policy_builder._themed_css_vars` -> same `load_design_tokens`/`render_as_css_vars_themed` chain above. Post-extraction this becomes: `build_ll_namespace` -> kit's token-stamping unit -> `load_design_tokens`/`render_as_css_vars_themed`, and `cmd_policy_builder` calls the same kit unit rather than owning `_themed_css_vars` itself.

Not yet wired (relevant to the last AC): `cmd_templatize` (`templatize.py`) -> `_report_unlifted_tokens` -> `load_design_tokens(config)` (no theme arg) is a report-only literal-color scan; `build_manifest()` (`templatize.py:519-537`) never sets `manifest["theme"] = "design-tokens"`, so a templatized body does not automatically opt into the kit's token-stamping unit today even when the report finds baked-in literals matching known tokens — the AC requiring the kit be "reachable from the templatize token-lifting path" is not yet satisfied by any existing call path and will need new wiring, not just extraction.

### Decision Rules
N/A — no new decision logic. This issue is a refactor extracting existing behavior into a shared module; it does not introduce a new gap kind, gate, threshold, or classification rule.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Step 0 — capture the golden fixture BEFORE any extraction.** Run `cmd_policy_builder` on the unmodified tree, with `design_tokens` configured (this repo's `warm-paper` + `dark` config, so the themed branch is exercised, not the degraded empty-block branch), and commit the emitted bytes as a fixture. The byte-identical AC is unprovable if this is captured after the port — a post-hoc capture asserts the new code equals itself. Do this first, in its own commit.
- Update `cli/artifact/__init__.py` — repoint the `_themed_css_vars` import (line 38) and `__all__` entry (line 55) at the new kit module, or re-export from there.
- Update `test_feat3036_artifact_templates.py:337` — repoint the `patch("little_loops.cli.artifact.policy_builder._themed_css_vars", ...)` target at the new kit module path.
- Preserve the `little_loops.cli.artifact` re-export of `_themed_css_vars` (or update `test_design_tokens.py:664,673,682`, which import it from there).
- Update `design_tokens.py`'s `DesignTokens.source` field docstring — drop the fully-qualified `cli/artifact/policy_builder.py::_themed_css_vars()` reference.
- ~~Update `templatize.py`'s `_write_unlifted_tokens_report()` persisted `_comment` string once `build_manifest()` sets `manifest["theme"] = "design-tokens"`.~~ **Void** — see the Decision above; `templatize.py` is untouched by this issue.
- Write a new byte-identical regression test for `cmd_policy_builder`'s output (modeled on `test_artifact_templatize.py`'s `read_bytes()` round-trip pattern) against the Step-0 fixture — no such golden-comparison test exists today, and the AC requires proving byte-identical (or reviewed-diff) output post-port.
- Add a test that the kit's stamping unit accepts a body carrying baked-in token literals (real `ll-artifact templatize` output as fixture) and completes without error — this is what closes the last AC under the narrow reading.
- File a follow-up ENH for literal→`var(--…)` rewriting in `templatize` (the rejected broad reading), so the deferred work is tracked rather than lost.
- Update `docs/reference/CONFIGURATION.md`'s `_themed_css_vars` reference and `### artifacts` section narrative to describe the kit as the stamping owner.

## Impact

- **Priority**: P3 — pays off once a second artifact template exists; not urgent
  on its own, but deferring it compounds cost as more templates copy from
  policy-builder (see Motivation).
- **Effort**: Medium — well-scoped extraction with an established call path
  (Program Design/Integration Map above), but touches five import sites and
  requires a new byte-identical golden-fixture test with no existing precedent
  for policy-builder specifically.
- **Risk**: Low-medium — behavior-preserving refactor with an explicit
  byte-identical AC as a regression backstop; main risk is the inverted
  `build_ll_namespace` → `policy_builder` coupling being missed during the port.

## Resolution

Extracted `scripts/little_loops/artifact_template_kit.py` as the shared kit:
`themed_css_vars()` (moved verbatim from `policy_builder.py`) and a new
`stamp_page_shell()` for the two page-shell placeholders (`data-theme`,
`/*__THEMED_CSS_VARS__*/`) common to design-token-aware templates.
`policy_builder.cmd_policy_builder` and `artifact_templates.build_ll_namespace`
both now call the kit — the latter fixes the inverted coupling this issue
flagged (general-purpose module no longer reaches into the CLI-command
module). A golden fixture of `cmd_policy_builder`'s pre-port output
(`scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`)
backs a byte-identical regression test; output is confirmed byte-identical.
The third-consumer AC is satisfied by a real `ll-artifact templatize` output
(deterministic, region-map driven, no LLM call) run through the kit's
stamping unit and shown to complete without error despite carrying no stamp
points of its own — the narrow reading recorded in this issue's Decisions.
Filed ENH-3319 for the deferred literal→`var(--…)` rewriting (the rejected
broad reading).

## Status

open

## Session Log
- `/ll:manage-issue` - 2026-08-25T16:14:52 - `2e6f3378-789f-46dc-8b61-adf0fc625fd4.jsonl`
- `/ll:ready-issue` - 2026-08-25T15:56:02 - `125c68ec-92ed-459a-ad33-99ec14728018.jsonl`
- `/ll:confidence-check` - 2026-08-25T15:49:55 - `c21d7697-754b-4fd4-b9a9-d9d051bebcc4.jsonl`
- `/ll:wire-issue` - 2026-08-25T15:24:37 - `b117138e-ea1a-4c48-86b4-f79804f6b111.jsonl`
- `/ll:refine-issue` - 2026-08-25T15:05:45 - `c104c28f-0ba5-4573-827d-9ff9ac6d6eb8.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:23 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:59 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
