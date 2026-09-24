---
id: ENH-3540
title: Treat agent-authored content in artifacts as untrusted input and escape it
  at render
type: ENH
priority: P1
status: open
discovered_date: '2026-09-23'
labels:
- security
- artifacts
decision_needed: false
learning_tests_required:
- jinja2-byte-exact-round-trip
confidence_score: 95
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# Treat agent-authored content in artifacts as untrusted input and escape it at render

## Summary

`ll-artifact` emits single-file HTML pages that operators open in a browser and
share. Some of the strings they embed are agent-influenced: `--local` dashboard
exports carry model/tool output from `history.db`, and shareable exports still
carry agent-chosen strings (`loop_name`, `state`, `branch`, `model`). The policy
builder embeds the project skill catalog (skill names/descriptions, which
agents author). Rendering any of these as markup turns a prompt injection into
stored XSS against whoever opens the artifact — frequently not the person who
ran the session.

Today the dashboard page is largely safe *by construction of that one page*,
not by a rule. Make escaping the default at the render boundary for every
artifact generator, make markup an explicit allowlist, pin it with
hostile-payload tests, and route artifact writes through the existing
symlink-safe atomic writer.

## Current Behavior

What is already safe (keep it that way, and pin it with tests):

- `ll-artifact dashboard` embeds the snapshot as a gzip+base64 blob
  (`dashboard.py:204-249`), not as HTML-interpolated rows.
- The dashboard page renders every query cell, header, and status line via
  `textContent` (`templates/dashboard.llat/template.html.j2:143-294`).
- Shareable mode (`_SHAREABLE_COLUMNS`, `session_store/queries.py`) exports no
  free-text columns — `loop_runs.error` and paths are excluded. Only `--local`
  (`SELECT *`) exports transcript text.
- Serve-mode SSE fragments (`partials.html.j2`, incl. `log_line`) render
  through a jinja2 `Environment(autoescape=True)`.

What is unsafe or unsafe-by-default:

1. **Frozen template env has `autoescape=False`** (`artifact_templates.py:267-279`,
   used by `render_template` for dashboard, `render.py`, `extract.py`,
   `templatize.py`). Every data key is raw unless the caller hand-escapes it;
   `dashboard.py:314-320` does so per key with `html.escape`. A new key added
   without `html.escape` is an XSS sink. Note: the env is frozen for
   FEAT-3308 byte-exact round trips — flipping `autoescape` is a
   template-format version bump, so the fix may need to live in the data
   layer (escape-by-default data wrapper with an explicit markup allowlist)
   rather than the env.
2. **JSON embedded in inline `<script>` is not script-context-safe.**
   `json.dumps` does not escape `<`, so a string containing `</script>` closes
   the script block:
   - `policy_builder.py:88-121` — `grammar_json`, `catalog_json` (skill
     catalog from `_load_skill_catalog(project_root)`: agent-authorable
     names/descriptions), version, confidence gate, connected context — all
     spliced via `html.replace("/*__...__*/", ...)`.
   - `dashboard.py:343-344` — `serve_interaction_url_js`, `serve_history_url_js`.
3. **Artifact writes follow symlinks.** Plain `Path.write_text` at
   `dashboard.py:475`, `render.py:68`, `policy_builder.py:143`,
   `design_md.py:129`, `extract.py:227,289`, `templatize.py:1215` (and the
   `templatize.py:1446-1577` tmp/rejected-dir writes). A planted symlink at
   the output path redirects the write.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

- **Missed unsafe path — `extract`/`refresh` is the most direct prompt-injection → stored-XSS route.** `extract_data()` (`scripts/little_loops/cli/artifact/extract.py`) sends an arbitrary source document to a model via `resolve_host()`/`run_blocking_json` using `_PROMPT_TEMPLATE` (source text is interpolated verbatim into the prompt) and writes the model's JSON to `data.json` (`cmd_extract`, `extract.py:227`; `cmd_refresh`, `extract.py:289`). `cmd_refresh` then renders it through `render_template` under the `autoescape=False` env. No step escapes the model-chosen strings. A hostile source document therefore controls both the prompt and the raw HTML output.
- **Why `render_template` itself cannot be made escape-by-default:** FEAT-3308 § "Fidelity constraints on extracted values" (`.issues/features/P2-FEAT-3308-*.md:208-216`) defines `data.json` values as the *artifact byte form*. If the artifact contains `&amp;` or `&#39;`, `data.json` stores that escaped form, and `verify_round_trip()` (`templatize.py`) requires `render_template(template, data) == original bytes` with no diff allowed. Escaping inside `render_template`/`build_environment()` would double-escape templatize-produced data and fail every round-trip test in `test_artifact_templatize.py`. So the escape-by-default boundary has to sit where untrusted strings **enter** a data dict (a code-built dict, or `extract`'s model output), not in the shared render call.
- **`render_template` callers** (all four run through the frozen env): `render.py:64` (`render_to_disk`, used by `cmd_render` and `cmd_refresh`), `dashboard.py:353` (`build_dashboard_html`), `templatize.py:554` (`_render_tmp_dir`, used by `verify_round_trip`/`verify_lift_renders`), and `fsm/persistence.py:950` (a render check only; the output is discarded).
- **Only one `.llat` template ships:** `templates/dashboard.llat`. Its data keys fall into these groups: already `html.escape`d (`filter_tables`, `filter_since`, `source_schema_version`, `schema_version_warning`, `serve_events_url`); base64 (`snapshot_gzip_b64`, `sql_wasm_b64`); **raw packaged JS stamped into `<script>`** (`sql_wasm_js`, `serve_htmax_js`, trusted vendored assets that are checked for `</script>` at vendoring time per `assets/vendor/{sql.js,htmx}/PROVENANCE.md`); JS string literals (`serve_interaction_url_js`, `serve_history_url_js`); and constants, ints, or bools (`exported_at`, `export_mode`, `allowlist_version`, `installed_schema_version`, `row_cap`, `serve_*_enabled`, `serve_history_poll_s`). `ll.theme_css` comes from `build_ll_namespace()` → `themed_css_vars(config)`, not from the caller's data dict. These groups are the markup-allowlist candidates the Scope § 2 docs need.
- **`.llat` manifest has no trust/markup annotation today.** `load_manifest()` allows only `_MANIFEST_REQUIRED_KEYS`/`_MANIFEST_OPTIONAL_KEYS` (`artifact_templates.py:25,29`), and `_validate_schema_shape()` rejects any `data_schema` key outside `_SCHEMA_ALLOWED_KEYS = {type, required, properties, items, enum, description}` (`artifact_templates.py:33`). A per-key markup declaration in the manifest would need that allowlist extended.
- **`markupsafe` is not imported anywhere** in `scripts/little_loops`. It is available only transitively through the `jinja2>=3.1` pin (`scripts/pyproject.toml:65`). Also, `Markup` has no effect under `autoescape=False`: a data-layer wrapper has to call `html.escape` itself rather than rely on `Markup` marking.
- **Write-site precision (templatize):** `templatize.py:1215` (`unlifted-tokens.json`) and the `template.*.j2`/`data.json`/`manifest.yaml` writes at `:1446-1450,1500-1502` all target `tmp_dir = tempfile.mkdtemp(...)` (`templatize.py:1444`). That directory is freshly created and private, so nothing can plant a symlink there first. The predictable-path target is `rejected_dir = out_dir.with_name(out_dir.name + ".rejected")` (`templatize.py:1365`), but it is already largely guarded: `:1366-1367` runs `if rejected_dir.exists(): shutil.rmtree(rejected_dir)` first, and `rmtree` raises on a symlink-to-dir, while a dangling symlink makes `_write_rejected_discovery()` (`:1559`) fail at `mkdir(exist_ok=True)` with `FileExistsError`. Only a race between the `rmtree` and the `mkdir`/`write_text` leaves a window, so a plant-a-symlink test here would fail before reaching a write. The `roundtrip.diff`, `lift-reversibility.diff`, and `lift-render-check.txt` writes come after `shutil.copytree(tmp_dir, rejected_dir)`, which fails if `rejected_dir` already exists.
- **Already symlink-safe (no change needed):** `cli/artifact/policy_revision.py:153-158` (`mkstemp` + `os.fdopen(fd,"wb")` + `os.replace`) and `cli/artifact/lockfile.py:108-110` (`.llat.lock`, `mkstemp` + `os.replace`).
- **Other HTML emitters outside `cli/artifact/`:** `mcp_server/templates/issues-view.html` is static; it receives agent-authored issue fields over `postMessage` and passes each through its own client-side `escapeHtml()` (`issues-view.html:58`, applied at `:48,52`), so it is safe. `transport.py` `_LOCAL_BRIDGE_DEFAULT_PAGE_HTML` (`:82`) and `_SSE_BRIDGE_PAGE_HTML` (`:918`) are fixed literals with no interpolation. `cli/artifact/serve.py` re-serves the `render_policy_builder_html()`/`build_dashboard_html()` output verbatim and adds no interpolation, so it inherits the fixes. `loops/vega-viz.yaml` and `loops/rlhf-svg-generate.yaml` have an LLM write whole HTML files directly, which puts them outside any Python render boundary. They are out of scope, but worth a note in the allowlist docs. Checked with no HTML emission found: `ab_writer.py`, `cli/loop/summary.py`, and `ll-logs fleet-review` (markdown output).

### Review Corrections (2026-09-24)

_Found in a manual review after refine and decide. Each finding changes Scope/AC below._

- **The policy builder can be injected through its own placeholders.** `render_policy_builder_html()` fills placeholders with a chain of `html.replace` calls (`policy_builder.py:115-123`), and each call rescans the whole page. `catalog_json` is spliced at `:116`. The later replacements at `:117-123` (`/*__GENERATOR_VERSION_JSON__*/`, `/*__CONFIDENCE_GATE_JSON__*/`, `/*__BUILDER_CORE_JS__*/`, `/*__CONNECTED_CONTEXT_JSON__*/`) then also match inside the catalog text just inserted. A skill description containing `/*__BUILDER_CORE_JS__*/` gets the whole core JS (quotes, newlines, `</script>`-free but string-breaking) spliced into the middle of a JSON string literal. `script_json` escapes neither `/` nor `*`, so it does not close this hole. The fix is single-pass substitution.
- **`extract` output would be double-escaped.** `_PROMPT_TEMPLATE` (`extract.py:51-58`) says nothing about encoding. When the source document is HTML, the model can copy entity-encoded text such as `&amp;` verbatim, and a plain `html.escape` at ingest then yields `&amp;amp;`. Ingest must be idempotent, and the prompt must ask for decoded text.
- **`atomic_write` makes artifact files owner-only.** `file_utils.atomic_write` (`file_utils.py:16`) creates the file with `tempfile.mkstemp` (mode `0600`) and `os.replace`s it into place without a chmod. Today `write_text` yields `0644` under a typical `022` umask. Routing artifact writes through it unchanged would silently make shared/served HTML owner-only.
- **`html.escape` does not neutralize `javascript:` URLs.** `javascript:alert(1)` contains no characters that `html.escape` changes, so it stays live in an `href`/`src` attribute. The dashboard template stamps no data key into a URL attribute except `serve_events_url` (`hx-sse:connect`, server-built), but templatize-produced templates may lift attribute values.
- **Refresh may escape real markup.** Templates that templatize already produced carry no per-property markup annotation, so every string leaf would be escaped on `refresh`. That is correct only if templatize lifts text/attribute values and never HTML fragments. _(Resolved in the second pass below: templatize can lift fragments.)_
- **`policy_builder.py:143` writes without an encoding.** It calls `out_path.write_text(html)` with no `encoding=`, so the write depends on the locale. Moving it to `atomic_write` (UTF-8 default) fixes that too.

### Review Corrections — second pass (2026-09-24)

_Found in a second manual review. Each finding changes Scope/AC below._

- **The `script_json` escape spec had been corrupted into identity mappings.** Scope § 1 and the Decision Rules mapped each character to itself: the six-character JSON unicode escapes had been decoded back into raw characters, including literal U+2028/U+2029 bytes in the file. No committed revision of this file ever held the escape sequences, so the earlier "repaired" Session Log entry never landed. The rule is now a table of hex digits written in words.
- **The policy builder has client-side DOM-XSS sinks.** Script-context-safe JSON splices only protect the HTML parser. The builder then interpolates model state into `innerHTML`: `policy-router-builder.html.tmpl:832` (`` `<strong>${norm}</strong> <em>(${d.type})</em>` `` — dimension name/type) and `:926`, `:1038` (`` `<strong>${oc.name}</strong>` `` — outcome name). That state arrives from **Open project** (`parseBuilderProject` in `policy_builder_core.mjs`, whose `validateProjectStructure` checks shape only, never names), from localStorage drafts, and from serve-mode revisions. A shared project file with an outcome named `<img src=x onerror=alert(1)>` executes script on open. `normalizeDimName` (`policy_builder_core.mjs:320`) only trims, lowercases, and hyphenates whitespace; it does not sanitize. The skill catalog is safe client-side: it reaches the DOM only via `textContent`/`title` (`:971-978`, `:1085`).
- **Templatize can lift markup fragments (answered, no longer hypothetical).** Regions are arbitrary byte spans (`start`/`end` from a hand-written `--regions` map or from model discovery; see `apply_regions`, `templatize.py:480-510`). Nothing constrains a region to a text node or attribute value, and templatize records no per-region context in the manifest. Consequences: (a) escaping every string leaf on `refresh` renders real markup inside a markup-spanning region as literal text (safe but visibly broken); (b) a region can sit inside `href`/`src`, `<script>`, an `on*=` handler, or `<style>`, where `html.escape` is the wrong encoding. So the `javascript:` URL case is real for templatized templates, but there is no annotation to key the URL rule on.
- **The manifest annotation must not reach the host.** `extract_data()` passes `template.data_schema` both into the prompt (`extract.py:154`) and as `json_schema` to `build_blocking_json` (`:162`). Codex materializes that schema (see the comment after `run_blocking_json`), so an unknown keyword risks rejection. Decision: strip the annotation from a copy of the schema before both uses.
- **"Top-level key" does not fit extract data.** Extract data nests (groups become arrays of objects), so a per-property annotation needs a path rule. Also, "idempotent" means stable under re-escaping, not byte-preserving: `html.escape` turns a bare `"` into `&quot;` and `'` into `&#x27;`. That is acceptable for `refresh`, and it confirms `escape_data` must never run on the templatize round-trip path.
- **`atomic_write` mode: decided, global.** The `0600` mode is a `mkstemp` side effect, not a design choice; the `write_text` calls the helper replaced produced umask-derived modes. Fix it in `atomic_write` itself (and in `atomic_write_bytes`), not as an opt-in parameter.

## Expected Behavior

Every `ll-artifact` generator treats agent-influenced strings as untrusted at the point they enter emitted HTML:

- JSON spliced into inline `<script>` blocks is script-context-safe (`</script>` in a value cannot close the block) and round-trips via `json.loads`.
- Template data strings are escaped by default (idempotently) unless the key is on a documented markup allowlist; `render_template` bytes for existing templates are unchanged.
- Policy-builder placeholders are substituted in a single pass, so spliced content is never rescanned.
- Artifact output writes replace, rather than follow, a symlink at the output path and keep the umask-derived file mode.
- The policy builder's client-side JS never interpolates model state (outcome, dimension, or type names) into `innerHTML`, so a hostile project file opened in the builder renders as inert text.
- On `refresh`, a region whose value contains markup renders as escaped text (fail visible, never fail open) until region-context tagging lands in a follow-up.
- Hostile-payload tests in the default pytest tier pin all of the above.

## Scope

1. **Script-context JSON helper.** Add one helper (e.g.
   `artifact_templates.script_json(obj) -> str`) that `json.dumps` then replaces
   each of the five characters `<`, `>`, `&`, U+2028, U+2029 with its six-character
   JSON unicode escape (backslash, `u`, four lowercase hex digits — see Decision
   Rules for the exact table). Replace every
   `json.dumps` spliced into HTML in `policy_builder.py` and `dashboard.py`.
2. **Escape-by-default for template data.** Without changing the frozen env's
   render bytes for existing templates, make template data escaped unless the
   key is on an explicit markup allowlist declared in code (and, if templates
   need it, in the `.llat` manifest). Document which keys carry markup and why
   (e.g. `sql_wasm_b64`/`snapshot_gzip_b64` are base64, not markup; `_js` keys
   use `script_json`).
   - **Idempotent ingest escaping:** `escape_data` escapes a leaf as
     `html.escape(html.unescape(v), quote=True)`, so text that is already
     entity-encoded is not double-escaped.
   - **Prompt for decoded text:** extend `_PROMPT_TEMPLATE` (`extract.py:51`)
     so the model returns plain decoded text and never HTML entities or markup.
   - **Templatize regions: decided default is "escape as text".** Templatize
     *can* lift markup fragments and attribute/script/style values (regions
     are arbitrary byte spans; see Review Corrections, second pass). This
     issue does **not** add region-context tagging. On `refresh`, every
     unannotated string leaf is escaped as text, so a markup-spanning region
     shows literal tags. That is visible breakage, never XSS. Document this in
     the allowlist docs and in the `refresh` help text. A template author can
     opt a property into verbatim stamping only through the explicit
     manifest markup annotation.
   - **Follow-up (separate issue, not yet captured):** templatize records
     each region's context (`text`, `attr`, `url`, `script`, `style`,
     `markup`) in the manifest per property, and `escape_data` dispatches on
     it: HTML-escape for `text`/`attr`, the URL scheme rule for `url`,
     `script_json`-style encoding for `script`, and refusal (raise) for
     `style`/`markup` unless the property is explicitly annotated trusted.
   - **Annotation never reaches the host:** `extract_data()` strips the
     markup annotation from a deep copy of `data_schema` before formatting
     `_PROMPT_TEMPLATE` (`extract.py:154`) and before passing `json_schema`
     to `build_blocking_json` (`:162`). Codex materializes the schema, so an
     unknown keyword must not reach it.
   - **Path-based allowlist:** the allowlist matches a leaf by its property
     path (e.g. `items[].body`, with array indices collapsed to `[]`), not
     only by its top-level key, because extract data nests. Code-built dicts
     like the dashboard's are flat, so their allowlist entries are plain keys.
3. **Hostile-payload tests** (deterministic tier) through each export path:
   `<script>`, `</script>` inside JSON strings, `onerror=`/`onload=` attribute
   injection, and payloads sourced from metadata
   (`loop_name`, `state`, `branch`, `model`, skill-catalog description,
   `--local` transcript text), plus a skill description containing each
   policy-builder placeholder token (`/*__BUILDER_CORE_JS__*/` etc.). Assert on
   the emitted HTML: no unescaped payload outside the base64 blob, and a
   `</script>` count equal to a clean-input render's count (derived, not
   hard-coded). Also assert that each spliced JSON blob, extracted from the
   page, `json.loads` back to the hostile input.
   - **`javascript:` URLs:** `html.escape` cannot neutralize them. For any
     data key stamped into an `href`/`src`/`action`/`formaction` attribute,
     `escape_data` rejects (raises on) values whose scheme, after stripping
     whitespace and lowercasing, is not `http`, `https`, `mailto`, relative,
     or `#`. Which keys count as URL attributes is declared alongside the
     markup allowlist. Templatize *can* lift URL attribute values, but
     without region-context tagging (the follow-up above) nothing identifies
     them. In this issue, implement the URL rule in `escape_data` for
     explicitly declared URL keys, and test it directly and against the
     dashboard's `serve_events_url` (server-built). Record in the allowlist
     docs that templatized URL regions are uncovered until the follow-up
     lands. Do not claim `javascript:` coverage from escaping alone.
   - **Client-side builder sinks:** a Node test loads a builder project
     whose outcome name, dimension name, and dimension type are
     `<img src=x onerror=alert(1)>` through the Open path and asserts the
     rendered outcome and dimension lists contain no `img` element (and the
     text appears verbatim).
4. **Symlink-safe writes.** Route artifact output writes through
   `file_utils.atomic_write` (sibling `mkstemp` + `os.replace`, which replaces
   a symlink rather than following it). Do **not** implement
   unlink-then-write — it has a TOCTOU window between unlink and open.
   Add `atomic_write_bytes` if a bytes variant is needed. **Preserve the
   normal file mode:** `mkstemp` creates `0600`, so before the `os.replace`,
   `os.fchmod` the temp file to `0o666 & ~umask` (read umask with the
   `os.umask(0); os.umask(old)` idiom). **Decided: apply the fix globally in
   `atomic_write` and `atomic_write_bytes`**, not as an opt-in parameter.
   The `0600` is a `mkstemp` side effect, not an intended privacy guarantee,
   and the `write_text` calls these helpers replaced produced umask-derived
   modes. Run the full suite to confirm the 40+ existing callers tolerate it.
   Reading the umask this way is process-global and not thread-safe, so do it
   once at module import and cache it.
5. **Single-pass placeholder substitution.** Replace the chain of
   `html.replace` calls in `render_policy_builder_html()`
   (`policy_builder.py:115-123`) with one substitution pass: a single
   `re.sub` over `/\*__([A-Z_]+)__\*/` with a dict lookup that raises on an
   unknown or missing key. Spliced content is then never rescanned for
   placeholders.
6. **Client-side DOM sinks in the policy builder.** Replace the three
   interpolating `innerHTML` assignments in
   `templates/policy-router-builder.html.tmpl` (`:832` dimension row, `:926`
   and `:1038` outcome titles) with `createElement` + `textContent` (e.g. a
   `<strong>` whose `textContent` is the name). Leave the constant-string
   `innerHTML` assignments (`= ""`, fixed `<label>` markup) alone. Add a
   static check to the Node suite that fails on any `innerHTML`/
   `insertAdjacentHTML` template literal containing `${` in the builder
   template, so new sinks cannot reappear silently.

## Scope Boundaries

- **In scope**: `script_json` helper; `escape_data` ingest escaping plus a path-based markup allowlist and the URL scheme rule for declared URL keys; stripping the annotation from the schema sent to the host; `extract` prompt change; single-pass placeholder substitution in `render_policy_builder_html()`; the three interpolating `innerHTML` sinks in `policy-router-builder.html.tmpl` plus a static no-interpolated-`innerHTML` check; `atomic_write`/`atomic_write_bytes` global mode fix and routing for the artifact output sites listed under Current Behavior; hostile-payload (Python and Node) and symlink tests.
- **Out of scope**: templatize region-context tagging and context-dispatched escaping (follow-up issue; until then markup-spanning regions render as escaped text and templatized URL regions are uncovered); changing `render_template`/`build_environment()` (`autoescape=False` stays; FEAT-3308 byte-exact round trips); the already-safe dashboard `textContent` rendering and SSE `autoescape=True` env; `policy_revision.py`/`lockfile.py` writes (already symlink-safe); `templatize.py` tmp-dir writes; LLM-written HTML loops (`vega-viz`, `rlhf-svg-generate`, `html-anything`), which sit outside any Python render boundary (note them in the allowlist docs only); hand-written `data.json` given to `ll-artifact render`, documented as trusted input.

## Acceptance Criteria

- [ ] No `json.dumps` result is spliced into emitted HTML without the
      script-context helper; a test feeds `</script><script>alert(1)</script>`
      through the skill catalog and serve URLs. It asserts that the
      `</script>` count equals a clean-input render's count, and that each
      spliced JSON blob `json.loads` back to the hostile input.
- [ ] `render_policy_builder_html()` substitutes placeholders in one pass. A
      skill description containing `/*__BUILDER_CORE_JS__*/` (and each other
      placeholder token) round-trips verbatim through the catalog JSON, and
      the core JS appears exactly once in the page.
- [ ] Template data values are escaped unless on the documented markup
      allowlist; existing templates' byte-exact round trips (FEAT-3308) still
      pass.
- [ ] Ingest escaping is idempotent: a model value of `Tom &amp; Jerry` and
      one of `Tom & Jerry` both land in `data.json` as `Tom &amp; Jerry`.
      `_PROMPT_TEMPLATE` asks the model for decoded plain text.
- [ ] `escape_data` rejects non-allowlisted schemes (`javascript:`,
      ` JavaScript:`, `data:`, `vbscript:`) for declared URL keys, and a
      direct unit test pins it. The allowlist docs state that templatized URL
      regions are uncovered until the region-context follow-up lands.
- [ ] `escape_data` matches allowlist entries by property path; a nested
      extract payload (group → array of objects) escapes non-allowlisted
      nested leaves and leaves an allowlisted nested path verbatim.
- [ ] The markup annotation is absent from both the prompt text and the
      `json_schema` passed to `build_blocking_json` (asserted with the host
      call stubbed).
- [ ] refresh on a template whose region value contains markup emits the
      markup as escaped text, not live tags.
- [ ] The policy builder's outcome and dimension lists render hostile names
      as text: a Node test opens a project with `<img src=x onerror=alert(1)>`
      as the outcome name, dimension name, and dimension type, and asserts
      no `img` element is created. A static check fails on any
      `innerHTML`/`insertAdjacentHTML` template literal containing `${` in
      `policy-router-builder.html.tmpl`. Both run in the default suite via the
      existing Node gate.
- [ ] Hostile-payload tests cover dashboard (shareable + `--local`), serve-mode
      fragments, `render`, and `policy-builder`, and run in the default
      `python -m pytest scripts/tests/` tier.
- [ ] Every artifact output write listed above uses `atomic_write`; a test
      plants a symlink at the output path pointing outside the output dir and
      asserts the target is untouched and the output path is now a regular file.
      The same test asserts the output's mode is `0o666 & ~umask` (e.g.
      `0644` under umask `022`), not `0600`. `test_file_utils.py` pins the
      same symlink-replacement and mode behavior on `atomic_write` and
      `atomic_write_bytes` directly, and the full suite passes with the
      global mode change.
- [ ] The markup allowlist is documented in `artifact_templates.py` (which
      keys carry markup and why).

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

Where to put escape-by-default (Scope § 2). The constraint from Current Behavior: `render_template`/`build_environment()` must keep stamping bytes verbatim, or the FEAT-3308 round trips break. Both options below leave `render_template` unchanged. They differ in where the untrusted-to-escaped conversion happens.

**Option A**: 

> **Selected:** Option A — matches the existing escape-at-ingest convention (`dashboard.py:306-320`), covers `extract`/`refresh`, and keeps `render_template` byte-identical.

Escape at ingest. A helper in `artifact_templates.py` (e.g. `escape_data(data, markup_keys) -> dict`) walks a data dict and `html.escape`s every string leaf whose key is not on an explicit markup allowlist. Code-built dicts call it: `build_dashboard_html` (this replaces the per-key `html.escape` calls at `dashboard.py:314-320` with one rule). `extract_data()` also applies it to the model's JSON before writing `data.json`, with the allowlist taken from a new per-property manifest annotation. The result is that `data.json` always holds artifact byte form, which is the contract FEAT-3308 already defines. `ll-artifact render` of a hand-written `data.json` stays verbatim and is documented as trusted input. Templatize-produced `data.json` keeps working because it is already in byte form.

**Option B**: Escape at render as a manifest opt-in. Add an optional manifest key (e.g. `escape: data`) that `render_template` honors by escaping non-allowlisted string leaves before `jinja_template.render`. Templatize-produced manifests omit the key, so their bytes are unchanged and no format version bump is needed. Weakness: `refresh` on a templatize-produced template (the main `extract` consumer) would still render model output raw unless the template opts in. Opting in would require `data.json` to store decoded text, which contradicts FEAT-3308's byte-form contract.

**Recommended**: Option A. It is the only option that covers `extract`/`refresh` (the one path where a model writes values from an untrusted document) without breaking the FEAT-3308 byte-form contract. It also turns the dashboard's "escaping is the rule that has to survive the next flag someone adds" comment (`dashboard.py:306-308`) into an enforced default. Either option requires extending `_SCHEMA_ALLOWED_KEYS` (`artifact_templates.py:33`) if markup keys are declared per property in `data_schema`, and `_validate_schema_shape()` must accept the new key.

### Decision Rationale

**Selected:** Option A — escape at ingest via `escape_data(data, markup_keys)`.

**Reasoning:** Option A generalizes the per-key `html.escape` convention already in `build_dashboard_html` and leaves `render_template`/`build_environment` untouched, so FEAT-3308 round trips are unaffected. `extract_data` is a single seam covering both `cmd_extract` and `cmd_refresh`. Option B protects only templates that opt in, leaves templatize-produced templates (the main `refresh` consumer) raw, and would double-escape the dashboard's pre-escaped keys unless its `html.escape` calls are removed and a second allowlist is added.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — escape at ingest | 3 | 2 | 3 | 2 | 10/12 |
| B — manifest opt-in at render | 2 | 2 | 2 | 1 | 7/12 |

**Key evidence / caveats:**
- No existing recursive escaping helper (`escape_data` is new); the dashboard's five `html.escape` calls are the direct precedent.
- Gap to address in implementation: the `html-anything.yaml` path has the agent write `data.json` directly and `cmd_render` (`render.py`) loads it with no ingest hook. Either call the helper in `cmd_render` or document `render` input as trusted (as Option A already proposes) and note this loop.
- ~~Before naming the manifest annotation key, check that the `data_schema` passed to the host as `json_schema` tolerates an extra key.~~ Decided (second pass): strip the annotation from a copy of the schema before the prompt and the host call, so host tolerance does not matter.
- `data.json` will hold entity-encoded text after `extract`; do not also escape at render.

## Integration Map

- `scripts/little_loops/artifact_templates.py` — script-JSON helper,
  escape-by-default data layer, allowlist docs.
- `scripts/little_loops/cli/artifact/{dashboard,policy_builder,render,extract,design_md,templatize}.py`
  — replace raw JSON splices and `write_text` output sites.
- `scripts/little_loops/file_utils.py` — `atomic_write` (reuse); optional
  bytes variant.
- `scripts/little_loops/templates/dashboard.llat/` — keep `textContent`
  rendering; no change expected.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — replace
  the three interpolating `innerHTML` sinks (`:832`, `:926`, `:1038`).
- Tests: new hostile-payload tests alongside `test_policy_builder_emit.py` and
  the dashboard/render tests; a new `scripts/tests/js/` Node test for the
  builder's DOM sinks and the static `innerHTML` check (run by
  `test_policy_builder_node_gate.py`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-24 — based on codebase analysis:_

- **Missing from Files to Modify:** `scripts/little_loops/cli/artifact/extract.py`. `extract_data()` is the ingest point for model-authored values (see Current Behavior). `cmd_extract`/`cmd_refresh` own the `data.json` writes at `:227`/`:289`.
- **Dependent files (callers of `render_template`):** `cli/artifact/render.py:64` (`render_to_disk`), `cli/artifact/dashboard.py:353`, `cli/artifact/templatize.py:554` (`_render_tmp_dir`, round-trip verifier), and `fsm/persistence.py:950` (a render check; its `manifest.yaml` write at `:943` targets a tmp dir and is not an artifact output). Any escaping change must leave the `templatize.py:554` path byte-identical.
- **Dependent files (serve layer):** `cli/artifact/serve.py` (`_serve_policy_builder_page`, `_make_page_html_factory`) re-serves `render_policy_builder_html()`/`build_dashboard_html()` output, so fixes to those functions carry over to serve mode automatically.
- **Convention in force (escaping):** frozen-env data is escaped by the caller that builds the dict, not by the env. Evidence: the D18 comment and `html.escape` calls at `dashboard.py:306-320`. JS-string-literal contexts use `json.dumps` rather than `html.escape` (`dashboard.py:338-344`). The only `autoescape=True` env is the SSE partials env in `render_live_fragment()` (`dashboard.py:374-377`). No script-context JSON helper exists yet. The only `</script>` guard in the repo is a vendoring-time grep documented in `assets/vendor/sql.js/PROVENANCE.md:79-84` and `assets/vendor/htmx/PROVENANCE.md:72-76`.
- **Convention in force (atomic writes):** output files are written with `file_utils.atomic_write(path, content, encoding="utf-8")` / `atomic_write_json(path, data)` (`file_utils.py:16,35`), which have 40+ callers across `cli/issues/`, `hooks/`, `init/`, and elsewhere. No bytes variant exists. `templatize.py:1446,1500` (`write_bytes`) and `policy_revision.py:153-158` (hand-rolled `mkstemp` + `os.replace`) are the bytes writers today. Nothing in the repo tests `atomic_write` against a symlinked target: `test_file_utils.py` and `test_ll_issues_atomic_write.py` have no `symlink_to`.
- **Tests to extend (existing files):** `scripts/tests/test_feat3304_artifact_dashboard.py`. It calls `build_dashboard_html`/`cmd_dashboard`/`render_live_fragment` directly, builds a synthetic DB with `_build_history_db()`, and decodes the base64 blob back out of the HTML, so hostile-payload tests for dashboard shareable/`--local` and SSE fragments fit here. Others: `test_policy_builder_emit.py` (policy-builder output), `test_feat3036_artifact_templates.py` (`render_template`/manifest schema, including any new `_SCHEMA_ALLOWED_KEYS` entry), `test_feat3310_artifact_extract.py` (extract/refresh ingest escaping), `test_artifact_templatize.py` (the round-trip tests `test_end_to_end_round_trip`, `test_non_ascii_round_trips`, `test_repeat_group_n5_round_trips`, and others must stay green unchanged), and `test_file_utils.py` (symlink-replacement test and any `atomic_write_bytes`).
- **No existing XSS/hostile-payload test exists anywhere in `scripts/tests`.** Every `payload` match is a generic variable name. The JS policy-builder tests (`scripts/tests/js/policy_*.test.mjs`) do not parse the Python-spliced `/*__*_JSON__*/` placeholders, so script-context JSON changes are not guarded on the Node side. Python-side assertions on the emitted HTML carry that coverage.

## Program Design

### Types
- `MARKUP_KEYS: frozenset[str]` (new, `artifact_templates.py`): the documented allowlist of data keys that carry markup, base64, or pre-encoded JS and are stamped verbatim. For `dashboard.llat` the candidates are `snapshot_gzip_b64`, `sql_wasm_b64`, `sql_wasm_js`, `serve_htmax_js`, `serve_interaction_url_js`, and `serve_history_url_js`. Non-string leaves (ints, bools) are never escaped, so they need no allowlist entry.

### Signatures
- `render_template(template: ArtifactTemplate, data: dict[str, Any], config: object) -> str` (existing, `artifact_templates.py:321`): **unchanged under Option A (not modified by this issue)**. It must stay byte-identical for existing inputs. It is the round-trip oracle for `templatize.py:_render_tmp_dir`.
- `build_environment() -> SandboxedEnvironment` (existing, `artifact_templates.py:259`): frozen. `autoescape=False` stays.
- `script_json(obj: Any) -> str` (new, `artifact_templates.py`): the output must be valid JSON/JS that `json.loads` decodes to `obj`, and must contain no `<`, `>`, `&`, U+2028, or U+2029 characters.
- `escape_data(data: dict[str, Any], markup_keys: frozenset[str], url_keys: frozenset[str] = frozenset()) -> dict[str, Any]` (new, per Option A): escapes each string leaf whose property path is not in `markup_keys` as `html.escape(html.unescape(v), quote=True)`, which is idempotent (stable under re-escaping, not byte-preserving). Leaves whose path is in `url_keys` are also checked against the URL rule and raise on a disallowed scheme. Paths collapse array indices to `[]`; flat code-built dicts use plain keys.
- `render_policy_builder_html(config: BRConfig, *, workspace_id: str | None = None) -> str` (existing, `policy_builder.py:66`): its six `/*__*__*/` splices (`:115-123`) are the `script_json` consumers. `/*__BUILDER_CORE_JS__*/` is raw packaged JS, not JSON, and is out of scope for `script_json`.
- `build_dashboard_html(*, db_path: Path, config: BRConfig, tables: list[str], since_iso: str | None, mode: str, serve_context: ServeContext | None = None) -> RenderedDashboard` (existing, `dashboard.py:257`): builds the data dict at `:309-345`.
- `extract_data(...)` (existing, `extract.py:102`): returns `(data, source_bytes)`; its `data` is the model-authored ingest point.
- `atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None` (existing, `file_utils.py:16`); `atomic_write_bytes(path: Path, content: bytes) -> None` (new, optional).

### Call Path
`cmd_dashboard` -> `build_dashboard_html` -> `escape_data` -> render_template (unchanged) -> `atomic_write`
`cmd_refresh` -> `extract_data` -> `escape_data` -> `render_to_disk` -> render_template (unchanged) -> `atomic_write`
`cmd_policy_builder` -> `render_policy_builder_html` -> `script_json` -> single-pass placeholder substitution -> `atomic_write`
`cmd_templatize` -> `verify_round_trip` -> `_render_tmp_dir` -> render_template (must stay unchanged; no `escape_data`)

### Decision Rules
- Escape set for `script_json`: exactly five replacements, applied to the `json.dumps` output string. Each input character becomes a backslash, a lowercase `u`, and the four hex digits shown (hex digits spelled out so no tool can decode them):

  | Input character | Hex digits after backslash-u |
  |-----------------|------------------------------|
  | `<` (less-than) | `003c` |
  | `>` (greater-than) | `003e` |
  | `&` (ampersand) | `0026` |
  | U+2028 LINE SEPARATOR | `2028` |
  | U+2029 PARAGRAPH SEPARATOR | `2029` |

  Test oracle: the output contains none of the five input characters, and `json.loads(output) == obj`. (Prior revisions of this rule were silently corrupted into identity mappings by a tool that decodes backslash-u sequences in issue text; keep this table in words.)
- Escape rule for data: a `str` leaf becomes `html.escape(html.unescape(value), quote=True)` unless its property path (array indices collapsed to `[]`) is in the markup allowlist (Option A: the code-built allowlist, plus the per-property manifest annotation for `extract`). Never applied on the templatize round-trip path.
- Annotation rule: the manifest markup annotation is stripped from a deep copy of data_schema before it is formatted into `_PROMPT_TEMPLATE` or passed as `json_schema`.
- URL rule: a key declared as a URL attribute rejects any value whose stripped, lowercased scheme is not `http`, `https`, or `mailto`. Values with no scheme (relative) or starting with `#` are allowed. Strip ASCII whitespace and control characters (not only leading spaces) before the scheme check, since browsers ignore embedded tabs/newlines in `java\tscript:`.
- Client DOM rule: builder JS writes model-derived strings only via `textContent`, attribute setters, or `createElement`; `innerHTML`/`insertAdjacentHTML` take constant strings only.
- Placeholder rule: the policy-builder placeholders are substituted in a single pass; spliced content is never rescanned.
- Write-mode rule: artifact outputs end up with mode `0o666 & ~umask`.

## Implementation Steps

1. `script_json` exists in `artifact_templates.py`, and no `json.dumps` result is spliced into HTML in `policy_builder.py:115-123` or `dashboard.py:343-344` without it. Check: `grep -n "json.dumps" scripts/little_loops/cli/artifact/{policy_builder,dashboard}.py` shows no remaining splice sites, and a test feeding `</script><script>alert(1)</script>` through `_load_skill_catalog` (monkeypatched) and `ServeContext` URLs counts the expected number of `</script>` tags.
1a. `render_policy_builder_html()` substitutes placeholders in one `re.sub` pass. Check: a catalog description containing every placeholder token round-trips verbatim, and the core JS appears once.
2. The dashboard data dict and `extract`'s model output pass through one idempotent escape-by-default rule with a documented allowlist. `_PROMPT_TEMPLATE` asks for decoded text. Templatize has been checked for fragment lifting (see Scope § 2). `test_artifact_templatize.py` round-trip tests pass unchanged, which proves render_template (unchanged under Option A; the rejected Option B would have modified it) stayed verbatim.
3. Hostile-payload tests cover dashboard shareable and `--local` (payloads in `loop_name`/`state`/`branch`/`model` and transcript text), `render_live_fragment`, `render`/refresh (model-returned strings, with the host call stubbed; refresh is an Option A ingest call path, not the rejected Option B render-time opt-in), and `policy-builder`. They run in the default `python -m pytest scripts/tests/` tier (no `integration` marker).
4. Every predictable-path output write (`dashboard.py:475`, `render.py:68`, `policy_builder.py:143`, `design_md.py:129`, `extract.py:227,289`, and, as defense in depth against the rmtree→mkdir race only, the `.rejected` writes in `templatize.py` `_write_rejected_discovery`) goes through `atomic_write`/`atomic_write_bytes`, and the result keeps its umask-derived mode. A test plants a symlink at the output path (for the `dashboard`/`render`/`policy-builder`/`design-md`/`extract` sites; not the `.rejected` dir, which the pre-`rmtree` already rejects) and asserts the symlink target is unchanged, the output path is now a regular file (`not path.is_symlink()`), and its mode is `0o666 & ~umask`.
4a. The three interpolating `innerHTML` sinks in `policy-router-builder.html.tmpl` (`:832`, `:926`, `:1038`) use `createElement` + `textContent`. Check: the new Node test (a hostile project opened through the Open path creates no `img` element) and the static no-`${`-in-`innerHTML` check both pass under `node --test scripts/tests/js/*.test.mjs`.
5. `python -m pytest scripts/tests/test_feat3304_artifact_dashboard.py scripts/tests/test_policy_builder_emit.py scripts/tests/test_feat3036_artifact_templates.py scripts/tests/test_feat3310_artifact_extract.py scripts/tests/test_artifact_templatize.py scripts/tests/test_file_utils.py scripts/tests/test_policy_builder_node_gate.py` passes; the full `python -m pytest scripts/tests/` passes (the global `atomic_write` mode change touches 40+ callers); and so do `python -m mypy scripts/little_loops/` and `ruff check scripts/`.

## Impact

- **Priority**: P1 — a prompt injection becomes stored XSS against whoever opens a shared artifact, often not the person who ran the session.
- **Effort**: Medium — ~18 sites across 6 artifact modules, `file_utils.py`, the builder template's 3 DOM sinks, 6 Python test files, and 1 new Node test.
- **Risk**: Medium — a wrong escape boundary breaks FEAT-3308 byte-exact round trips (`templatize.py:554` must stay unchanged); mitigated by choosing ingest-time escaping (Option A) and running `test_artifact_templatize.py` unchanged.
- **Breaking Change**: Minor, behavioral. `extract`/`refresh` `data.json` now holds entity-encoded text. That is already the FEAT-3308 byte-form contract, but downstream consumers reading `data.json` values directly will see `&amp;` etc. Markup-spanning regions on `refresh` now render as escaped text. `atomic_write` output files change from `0600` to umask-derived modes. Note all three in the CHANGELOG.

## Status

**Open** | Created: 2026-09-23 | Priority: P1

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Gaps to Address
- _(Resolved 2026-09-24)_ The applied-decision flag on `render_template`/refresh cleared after the Implementation Steps and Call Path text was reworded (identifiers unbackticked, marked unchanged/not-Option-B); `unapplied_decision` is now empty.

### Outcome Risk Factors
- broad enumeration across ~15 sites (6 artifact modules, `file_utils.py`, 6 test files) with moderate per-site depth: escape semantics span `artifact_templates`, `dashboard`, `extract`, and manifest schema
- 4 direct `render_template` callers plus the serve layer; `templatize.py:554` must stay byte-identical, so a wrong escape boundary fails the FEAT-3308 round trips

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-24_

Verdict at time of check: **NEEDS_UPDATE** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- All other claims (line refs in `dashboard.py`, `policy_builder.py:115-123,143`, `render.py:68`, `extract.py:227,289`, `design_md.py:129`, `artifact_templates.py` frozen env / `_SCHEMA_ALLOWED_KEYS`, `atomic_write` `0600` mode, `render_template` callers) match the current code. `ll-verify-evidence`: clean.
- **Corrected:** the `templatize` `.rejected` symlink-following claim was inaccurate — `templatize.py:1366-1367` `rmtree`s an existing `rejected_dir` first (raises on a symlink; a dangling symlink fails `mkdir`). Only an rmtree→mkdir race remains; Scope/AC/Step 4 reworded so the symlink test does not target that site.
- Decisions log check: no conflicting required rules found. Graph: provider=`codegraph` freshness=`fresh` (not needed for any verdict).

## Session Log
- Manual review (second pass) - 2026-09-24 - rewrote the `script_json` escape table in words (it had been decoded into identity mappings); added the builder's client-side `innerHTML` sinks (Scope § 6); resolved templatize fragment lifting (escape-as-text default, region-context tagging deferred to a follow-up); decided annotation stripping, a path-based allowlist, and a global `atomic_write` mode fix
- `/ll:format-issue` - 2026-09-24T18:15:48 - `b1a4f1ac-1b29-4ce0-8044-3ed15a90327a.jsonl`
- `/ll:confidence-check` - 2026-09-24T17:39:32 - `be572ee7-4bdf-4b90-b8fb-64aeafff2750.jsonl`
- `/ll:verify-issues` - 2026-09-24T17:33:31 - `96d01310-c604-4961-b5bd-6b1925aee00d.jsonl`
- Manual review - 2026-09-24 - repaired the corrupted `script_json` escape spec; added single-pass placeholder substitution, idempotent ingest escaping plus a decoded-text prompt, `atomic_write` mode preservation, the `javascript:` URL rule, the templatize fragment check, and derived `</script>` counts; marked `render_template` unchanged
- `/ll:confidence-check` - 2026-09-24T05:15:41 - `27ae30f6-009c-4b0e-9ac3-8684b7ff61cd.jsonl`
- `/ll:decide-issue` - 2026-09-24T05:08:54 - `99248bf9-5b09-479f-986e-d42c22c65074.jsonl`
- `/ll:refine-issue` - 2026-09-24T05:05:07 - `b4ebbfb3-ca8e-4bb4-bf8e-9713ebdfe185.jsonl`
- Manual review - 2026-09-23 - corrected exposure premise (base64 blob + textContent already safe), retargeted to autoescape=False template env, script-context JSON splices, and atomic_write instead of unlink-before-write
