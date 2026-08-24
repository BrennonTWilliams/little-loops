---
id: FEAT-3316
title: '`ll-artifact templatize` Phase C: token report, fan-out verification, docs'
type: FEAT
priority: P2
status: done
discovered_by: manual
discovered_date: '2026-08-24'
completed_at: '2026-08-24T23:47:00Z'
parent: FEAT-3308
depends_on:
- FEAT-3314
relates_to:
- FEAT-3308
- FEAT-3309
- ENH-3035
labels:
- artifact
- ll-artifact
- templates
decision_needed: false
testable: true
confidence_score: 92
outcome_confidence: 80
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 21
---

# FEAT-3316: `ll-artifact templatize` Phase C: token report, fan-out verification, docs

## Summary

Decomposed from [FEAT-3308](P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md).
Adds the design-token unlifted-literal report, verifies the produced template
renders correctly against a second, different source document (the fan-out
use case the epic exists for), and lands the documentation updates.

## Parent Issue

Decomposed from FEAT-3308: `ll-artifact templatize`: save a generated
artifact as a reusable template.

## Depends On

Landed: FEAT-3314 (Phase A). This phase reports against and fan-out-tests
the template directory Phase A's `build_manifest`/`verify_round_trip` flow
produces. FEAT-3315 (Phase B) has also landed; this phase's post-promote
report call is inserted after both branches converge (see Program Design →
Codebase Research Findings).

## Current Behavior

Phase A produces a working, byte-exact template but gives no signal about
design-token coverage: baked literal hex values in the template body that
match the resolved token map go unreported, so a template can ship
permanently un-themeable with no warning. Nor is there any verification
that a produced template actually generalizes to a second source document —
Phase A's round trip only proves it reproduces the *original* artifact.

## Expected Behavior

A `templatize` run that promotes a template also writes an
`unlifted-tokens.json` report into that template directory, listing every
baked color literal in the **spliced template body** that matches the
resolved token map (with all candidate token names when a value is
ambiguous), plus a non-silent warning naming the count. The report is
written into the staging directory *before* promote so it lands atomically
with the rest of the template, and no failure in the report path can change
the exit code or block the promote. Separately, a
fixture proves the produced template renders correctly against a *second*,
different source document using a hand-authored `data.json` for that
document, matching a checked-in expected output. `docs/reference/CLI.md`,
`docs/reference/CONFIGURATION.md`, and `docs/ARCHITECTURE.md` reflect the
completed subcommand.

## Use Case

A user has run Phase A/B `templatize` successfully and has a working
template. Before adopting it for fan-out across many source documents, they
want to know two things without inspecting the output by hand: whether the
template is still carrying hard-coded colors that won't pick up a theme
change, and whether it actually generalizes past the one document it was
extracted from — both of which this phase answers automatically.

## Proposed Solution

### Round trip vs. token lifting

Byte-exact round trip and design-token lifting are **mutually exclusive by
construction**: a lifted stamp point renders `ll.theme_css` (a CSS
custom-property block), which is by definition not the literal hex the
original artifact contains. Resolution for v1:

- The round-trip gate (Phase A) runs against the **unlifted** template —
  that stays byte-exact with no tolerance, and this phase does not touch it.
- Token lifting is **report-only** in v1: `templatize` scans the spliced
  template body for values matching the resolved token map and writes an
  `unlifted-tokens.json` report plus a non-silent warning naming the
  count and the token names. It does not rewrite them, and the emitted
  manifest does **not** set `theme: design-tokens`.
- Actually performing the lift (and the normalized-diff gate it would
  require) is deferred to a follow-up (see § Deferred below).

### Design-token stamp points

The HTML loops receive design tokens as **prompt text** —
`cli/loop/_helpers.py:1416-1424` seeds `context["design_tokens_context"]` via
`render_as_prompt_context`. A generated artifact therefore has token values
baked in as literal hex. The template kit (ENH-3035) stamps tokens **at
render time** as CSS variables via `render_as_css_vars_themed`
(`design_tokens.py:688`).

`templatize` must reconcile the two by recognizing baked literal token
values and reporting them. Building that report needs
a `value -> token-name` inversion of `DesignTokens.resolved`
(`design_tokens.py:35`), which does not exist in the codebase — every
renderer iterates it forward-only. The inversion is **not injective** — two
tokens can resolve to the same hex — so a matched literal maps to a *list*
of candidate names and the report must say so rather than pick one.

#### Scan input: the spliced template, not the artifact

The scan runs over `spliced` — the bytes that become `template.html.j2` —
**not** over `artifact_bytes`. By the time the report runs, every extracted
data region has been replaced by a `[[= ... =]]` stamp point and its content
lives in `data.json`. A hex literal sitting inside an extracted data region
is not part of the template and is not un-liftable; reporting it is a false
positive that pollutes the very inventory the deferred lift phase is meant
to work from. Scanning the spliced body also naturally excludes that content
with no extra filtering.

#### Matching rule (decided — not an implementer choice)

`tokens.resolved` spans every namespace, not just colors: `space.*`
(`4px`, `8px`), `radius.*` (`0`, `2px`), `font.*` (font stacks), bare
numbers. A naive substring scan for `0` or `4px` matches hundreds of times
in any real artifact and yields a useless report. v1 therefore fixes the
rule as:

- **Colors only.** Match literals of the form `#rgb`, `#rgba`, `#rrggbb`,
  `#rrggbbaa`, `rgb()`/`rgba()`, `hsl()`/`hsla()`. Every other token
  namespace is out of scope for v1, and the report's `_comment` key states
  that scope so the deferred lift phase knows what was *not* covered.
- **Case-insensitive**, with `#abc` normalized to `#aabbcc` (and `#abcd` to
  `#aabbccdd`) on both sides before comparison — otherwise the report
  silently misses roughly half of real matches.
- **Functional forms match by literal**: `rgb()`/`rgba()`/`hsl()`/`hsla()`
  literals are compared case-insensitively with runs of whitespace collapsed
  on both sides — no component parsing, no `rgb`↔`hex` value equivalence
  (that would need a CSS/color library; none exists in the dependency set).
  The report's `_comment` states this limit.
- **Whole CSS values, word-boundary anchored** — never bare substring.
  `#fff` substring-matches inside `#fff000`.
- `occurrences` counts non-overlapping matches in the template body.

#### Theme selection (decided)

`load_design_tokens(config, theme=...)` resolves different values per theme,
so the report must load the *same* map that baked the literals. The literals
were seeded by `inject_design_context` (`cli/loop/_helpers.py:1416`), which
calls `load_design_tokens(config)` with **no theme** — i.e. the configured
`design_tokens.active_theme`. `report_token_literals`'s caller must load the
same way: `load_design_tokens(config)`, `theme=None`.

Note that `policy_builder._themed_css_vars` (`cli/artifact/policy_builder.py:56-87`),
cited below as the token-loading precedent, loads light **and** dark. That
is the correct shape for a *render-time* CSS-variable emitter and the
**wrong** shape here — following it would report against a value map that
never touched the artifact. Reuse only its `load_design_tokens` entry point,
not its two-call theme handling.

#### Degradation and empty reports (decided)

- `load_design_tokens` returns `None` when design tokens are disabled or
  unconfigured. In that case the report is skipped entirely: **no file
  written**, no warning, exit 0 unchanged.
- When tokens load but zero literals match, the file **is** written with an
  empty list — deterministic presence is easier for the deferred lift phase
  and for tests to assert on than a conditionally absent file. No warning
  line is emitted in this case.

### Fan-out verification

The resulting template must render correctly against a *second, different*
source document of the same kind. **Oracle:** the fixture ships a
hand-authored `data.json` for the second document and the test asserts the
render matches a checked-in expected output. (Deriving that `data.json`
automatically is `ll-artifact extract`, i.e. FEAT-3309, and is explicitly
not in scope here — this phase asserts the template *works* for fan-out, not
that extraction is automated.)

Three constraints keep this from degrading into a self-satisfying snapshot
test, since the expected output would otherwise be generated by the same
code it checks:

1. **The test runs `templatize` on artifact 1** to produce the template
   (reusing the `_run` harness at `test_artifact_templatize.py:394`), then
   renders that produced template against document 2's `data.json`.
   Rendering a checked-in `.llat` instead would test the fixture, not the
   subcommand.
2. **Leak assertion.** Beyond the byte comparison, assert the document-2
   render contains document-2's region values and **none** of document-1's.
   This is the assertion that actually catches a region wrongly baked into
   the template body instead of extracted — the byte-diff alone would pass
   against a snapshot regenerated from the same bug.
3. **Structural divergence.** Document 2 must differ from document 1 in
   *schema shape*, not only in wording: a different list length where the
   schema has an array, an empty-string region, and a region containing
   characters that require escaping. Two documents differing only in prose
   exercise nothing the round trip did not already cover.

### Deferred to a follow-up

Actually **rewriting** baked token literals into `ll.theme_css` stamp points
(and emitting `theme: design-tokens`) is out of scope. It cannot coexist
with the byte-exact round-trip gate, so it needs its own normalized-diff
fitness function — a separate design decision, not a step here.
`report_token_literals` exists so the follow-up has an inventory to work
from and so a lossy template is never silently accepted in the meantime.

## Program Design

### Types

- `UnliftedToken: {literal: str, candidate_names: list[str], occurrences: int}` — the inversion is not injective, hence a name *list*

### Signatures

- `report_token_literals(template_text: str, tokens: DesignTokens) -> list[UnliftedToken]` — report-only in v1; *template_text* is the spliced template body, never the original artifact (see § Scan input). `spliced` is `bytes` (`templatize.py` writes it via `write_bytes`); the caller decodes with `spliced.decode("utf-8", errors="replace")` **inside** the containment-wrapped report step, so a decode failure falls under the existing failure-containment rule.

### Call Path

`cmd_templatize` (Phase A) -> [in `tmp_dir`, after `validate_top_level_data`, before `promote`] -> `report_token_literals`

`build_ll_namespace`/`_themed_css_vars`/`render_as_css_vars_themed` are
**not** on this path in v1, because the emitted manifest omits `theme`.
`report_token_literals` needs a resolved `DesignTokens` via
`load_design_tokens(config)` with **no theme argument** — see § Theme
selection for why `_themed_css_vars`'s light+dark double load
(`cli/artifact/policy_builder.py:56-87`) must *not* be copied here.

### Codebase Research Findings

- **`DesignTokens.resolved` (`design_tokens.py:35`) is forward-only.** Every
  renderer (`render_as_css_vars` `:678`, `render_as_css_vars_themed` `:688`,
  `render_as_prompt_context` `:572`) iterates it name -> value. No value ->
  name index exists anywhere; `report_token_literals` builds the inversion
  from scratch and must handle the non-injective case.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **Warning convention (decided — not an implementer choice)**: use `Logger.warning()` (`logger.py:91-94`) — the dominant `cli/` convention for a report-only, non-blocking warning carrying a count (4 precedents: `cli/sprint/edit.py:130`, `cli/sprint/_helpers.py:249`, `cli/parallel.py:303`, `cli/deps.py:351`), and `cmd_templatize` already receives `logger: Logger`. The artifact CLI constructs `Logger` with the default `verbose=True` (`cli/artifact/__init__.py:125`), so `warning` satisfies "non-silent." Do **not** use the `design_md.py`-style raw `sys.stderr.write`.
- **JSON-write idiom to follow for `unlifted-tokens.json`**: `write_baseline` shape (`verify_private_refs.py:461-474`, `verify_evidence.py:1288-1302`) — `path.parent.mkdir(parents=True, exist_ok=True)`, a `dict` payload with a `"_comment"` self-documenting key naming what regenerates the file, `json.dumps(payload, indent=2, sort_keys=False) + "\n"`, `path.write_text(..., encoding="utf-8")`, returns `Path`. Write target is `tmp_dir` (pre-promote) — see the corrected insertion-point finding below; an earlier revision said `out_dir` post-promote, which is wrong.
- **Shared token-loading entry point**: `load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None` (`design_tokens.py:412`) is what `report_token_literals`'s caller should invoke to obtain a resolved `DesignTokens` — the same function `policy_builder.py`'s `_themed_css_vars` (lines 56-87) already uses, though **only the entry point is shared, not its light+dark call pattern** (§ Theme selection). It can return `None` when tokens aren't configured, which the caller must handle (skip the report, write no file, no error).
- **Module import constraint reconfirmed**: `templatize.py`'s module docstring (lines 1-11) forbids importing `host_runner`/`anthropic`; `design_tokens.py` imports neither, so `report_token_literals` stays compliant by depending only on it. Existing test `test_templatize_module_imports_nothing_from_host_runner_or_anthropic` (`test_artifact_templatize.py:936`) already enforces this and must keep passing.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` — add
  `report_token_literals` call in `tmp_dir`, before promote
- `docs/reference/CLI.md` § `ll-artifact` (line ~4455) — complete the
  subcommand section
- `docs/reference/CONFIGURATION.md` § `artifacts` (`:910-924`) — the prose at
  `:912` ("Currently backs the `policy-builder` subcommand...") stops being
  accurate once `templatize` reads *and writes* `templates_dir`; update it
- `docs/ARCHITECTURE.md` — document the templatize flow

### Similar Patterns
- `hitl-md.yaml:256-263`, `vega-viz.yaml:505-513` — hand-written loop states
  that already copy `${run_dir}/index.html` out; prior art for wanting
  artifacts to outlive a run

### Tests
- Extend `scripts/tests/test_artifact_templatize.py`:
  - Token report test: fixture with baked design-token hex literals, assert
    the report is non-empty and that a literal matching two token names
    reports both candidates.
  - Matching-rule tests (§ Matching rule): a `#abc`/`#aabbcc` shorthand pair
    is matched as the same value; `#fff` inside `#fff000` is **not** matched;
    a non-color token value that is a common CSS literal (`0`, `4px`) is
    **not** reported.
  - Scan-input test (§ Scan input): a token-valued hex that appears *only*
    inside an extracted data region does not appear in the report, since the
    scan runs over the spliced template body.
  - Degradation tests: with design tokens disabled, `templatize` exits 0 and
    writes **no** `unlifted-tokens.json`; with tokens enabled but no matches,
    it writes the file with an empty list and emits no warning.
  - Containment test: a forced failure inside the report step leaves exit 0
    and a fully promoted, valid template.
  - Fan-out test: second, different source document with a hand-authored
    `data.json`, assert the render matches a checked-in expected output —
    with the produced-not-checked-in template, leak assertion, and structural
    divergence required by § Fan-out verification.
  - Assert the **artifact-generating FSM loop** is never invoked by
    `templatize` or subsequent renders (the Phase B `discover_regions` host
    call is the only host invocation on this path and is exempt).

- **Test scaffolding note**: the token-report tests need the `_run` tmp_path
  project to have `design_tokens.enabled` **and** a materialized token
  profile on disk. The existing `test_artifact_templatize.py` fixtures set up
  neither — the note elsewhere in this issue that `theme.llat` is unusable
  covers only the template side, not the config side. A helper that writes a
  minimal profile (two tokens sharing one hex value, to exercise the
  non-injective case) into the tmp project is a prerequisite for these tests.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **Existing `.llat` fixture layout to extend for the fan-out fixture**: `scripts/tests/fixtures/artifact_templates/{simple,delimiters,theme}.llat/` (each with `manifest.yaml`, `template.html.j2`, `data.json`) is the existing checked-in template-fixture shape; a fan-out fixture (second source document + hand-authored `data.json` + checked-in expected render output) extends this layout.
- **No CSS-parsing dependency exists anywhere in `scripts/pyproject.toml`** (no `tinycss2`, `cssutils`, `cssselect`, etc. — the only markup-parsing dependency, `BeautifulSoup`, is used solely by the unrelated `doc_scraper.py`). `report_token_literals` must do its own from-scratch value-matching (regex/substring scan of the CSS text against `tokens.resolved`'s values) — there is no existing CSS-aware helper to reuse.
- **Precise mechanism for why literal token values get baked into generated artifacts**: `inject_design_context()` in `cli/loop/_helpers.py:1397-1430` (a more exact anchor than the issue's own `:1416-1424` citation) is guarded by `context.get("use_design_tokens", True)` with string-to-bool coercion at `:1419-1420` (`""`/`"0"`/`"false"`/`"no"`/`"off"` all disable it); when enabled it sets `context["design_tokens_context"] = render_as_prompt_context(_tokens)` (`:1423`), which emits `name: value` lines with literal resolved values (hex codes, sizes) — not CSS custom-property references. This confirms the exact seed point of the "baked literal" problem this phase reports on.
- **Warning convention**: settled — `Logger.warning()`; see the decided finding above. (The `cli/verify_design_tokens.py` gating convention and `design_md.py`'s raw `sys.stderr.write` were both considered and rejected.)

- **Existing JSON-report-to-disk write idiom**: `cli/verify_private_refs.py:461-474` (`write_baseline`) and `cli/verify_evidence.py:1234-1302` (`write_verdict_cache`/`write_baseline`) both use `path.parent.mkdir(parents=True, exist_ok=True)` then `path.write_text(json.dumps(payload, indent=2, ...) + "\n", encoding="utf-8")` — the closest existing write-idiom precedent for `unlifted-tokens.json`, though both existing examples exist for baseline/gating rather than pure reporting.
- **Fan-out / cross-fixture test convention to model after**: `test_streaming_cache_parity.py` and `test_benchmark_fragment.py::TestHarborFixtures` both hardcode fixture IDs (not globbed, so a missing fixture fails at collection time rather than silently generating zero test cases) and pair a `TestXFixtures` structural sanity-check class with a parametrized assertion test. This is the established N-input/N-expected-output pattern the fan-out test should follow.
- **`docs/reference/CLI.md`'s `### ll-artifact` section structure**: a subcommand table (`:4461-4465`) plus one `#### ll-artifact <subcommand>` subsection per subcommand (prose → Flags table → Examples → Exit codes → optional `> **Note:**` phase-status callout, e.g. `:4531` for `render`). `templatize` needs both a new table row and its own subsection in this shape.
- **`docs/ARCHITECTURE.md` has no artifact-templates section yet** (confirmed via grep — zero hits for `.llat`, "artifact template", `FEAT-3036`, `manifest.yaml`). The nearest analog is the "Project-enriched artifacts" paragraph (`:1027-1029`), which folds new artifact-generator examples into existing prose rather than adding a new heading. Whether `templatize` gets its own `####` section or a clause added to this existing paragraph is not settled by precedent — both shapes exist elsewhere in the file for other subsystems.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **Doc line numbers refreshed (stale as of this pass — `docs/reference/CLI.md` changed after the last refine due to FEAT-3315 landing today):**
  - `docs/reference/CLI.md`: `### ll-artifact` header is at line 4455 (unchanged); subcommand table at 4459-4466; the `#### ll-artifact templatize` subsection now spans **4532-4562** (grown since FEAT-3315's discovery-flow prose landed), with its `> **Note:**` phase-status callout at line 4562 just before the `---` separator at 4564 — this callout is what Phase C's doc update needs to remove/replace.
  - `docs/reference/CONFIGURATION.md`: `### artifacts` header at line 911; the summary prose the issue flags as stale is now at **line 913** ("Backs the `policy-builder` subcommand ... and `render` (FEAT-3036 Phase 1) ...") — still omits `templatize` by name even though the per-key rows already document `templates_dir`/`templatize_max_input_bytes`; config table at 915-919, JSON example at 921-927.
  - `docs/ARCHITECTURE.md`: reconfirmed zero existing `.llat`/"artifact template"/`FEAT-3036`/`manifest.yaml` hits; nearest analog is still the "Project-enriched artifacts" paragraph (~1027-1029).
- **`theme.llat` fixture is not usable for the token-report test as-is**: its `template.html.j2` is already-lifted (`[[= ll.theme_css =]]` stamp point), not baked literal hex — the token-report test needs a *new* fixture (or an addition to an existing one) with literal hex/size values baked directly into CSS text that match `tokens.resolved`.
- **Insertion point — pre-promote, into `tmp_dir` (corrected)**: `cmd_templatize` (`templatize.py:639`), inside the existing `try/finally` around `tmp_dir`, after the `validate_top_level_data` call and **before** `promote(tmp_dir, out_dir, force=bool(args.force))` (line 784). Both the `--regions` and LLM-discovery branches converge well before this point (lines 740-787), so one call site covers both. An earlier revision of this issue placed the call *after* promote, writing into `out_dir`; that is wrong for two reasons:
  - It breaks Phase A's atomicity contract. A raise anywhere in the report path lands in the outer `except Exception` (line 795) and returns **exit 1 with the template already promoted to disk** — a confusing failure for a step that is explicitly non-blocking. A crash between promote and the write leaves a promoted template with no report at all.
  - Writing into `tmp_dir` lets `promote` move the report atomically with the rest of the template, no extra code path required.

  **Verified safe**: an unrecognized sibling file in the template directory is inert for both render and round-trip. `find_template_body` (`artifact_templates.py:267`) globs only `template.*.j2`, `load_assets` (`:288`) reads only `assets/`, and `verify_round_trip` (`templatize.py:541-562`) renders through those two — so `unlifted-tokens.json` present in `tmp_dir` cannot affect the byte-exact round-trip gate that runs before it. `_sweep_stale_siblings` (`:570-578`) only matches `.tmp-`/`.bak-` prefixes and is likewise unaffected.

- **Failure containment**: the entire report step (token load, scan, JSON write, warning) is wrapped so that no exception within it can change the exit code, block the promote, or suppress `logger.success`. The failure surfaces as a warning line only. `_write_rejected_discovery` (lines 799-818) remains the in-file idiom precedent for an auxiliary-JSON side artifact, but note it runs on failure paths only and writes to `rejected_dir` — the report's target is `tmp_dir`, promoted to `out_dir`.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **`test_artifact_templatize.py` current class structure** (single file, no Phase A/B split): `TestLoadRegions`, `TestExtractData`, `TestDeriveSchema`, `TestEscapeLiteralDelimiters`, `TestApplyRegions`, `TestPromote`, `TestBuildManifest`, `TestCmdTemplatizeEndToEnd` (line 393 — helper `_run(self, tmp_path, argv)` at 394-400 shells through `main_artifact()`; `test_end_to_end_round_trip` at 402-439 templatizes then renders and diffs bytes), `TestCmdTemplatizeDiscoveryBranch` (line 749). The fan-out test should reuse the `_run` harness from `TestCmdTemplatizeEndToEnd`, rendering against a second hand-authored `data.json` instead of round-tripping the original.
- **Multi-fixture test convention, with the exact anti-pattern to avoid**: `TestStreamingParityFixtures` (`test_streaming_cache_parity.py`) and `TestHarborFixtures` (`test_benchmark_fragment.py:299-335`) both hardcode fixture/trace IDs as a module-level tuple rather than discovering them via `Path.iterdir()`/glob — explicitly so a missing fixture fails at collection time (a visible, named failing test) instead of silently producing zero parametrized cases. Each pairs a `TestXFixtures` structural-sanity class (dir exists, expected file set present) with a separate `@pytest.mark.parametrize` test for the actual assertions, and per-check methods guard with `if not fixtures.is_dir(): pytest.skip(...)` to avoid cascading failures once the dedicated existence test already caught it.

## Acceptance Criteria

- [x] Baked design-token color literals in the **spliced template body** are reported as unlifted in `unlifted-tokens.json` and a non-silent log line; a test asserts the report is non-empty for a fixture with baked tokens and that a literal matching two token names reports both candidates.
- [x] The scan follows the decided matching rule (§ Matching rule): colors only, case-insensitive with `#abc`→`#aabbcc` normalization, whole-value/word-boundary anchored, non-overlapping occurrence counts — each covered by a test, including the negative cases (`#fff` not matched inside `#fff000`; `0`/`4px` not reported).
- [x] Tokens are loaded via `load_design_tokens(config)` with **no theme argument**, matching the map that `inject_design_context` baked into the artifact.
- [x] The report is written into the staging dir and promoted atomically with the template; **no failure in the report path changes the exit code, blocks the promote, or suppresses the success line** — covered by a test that forces a failure inside the report step and asserts exit 0 with a valid promoted template.
- [x] Degradation is explicit: tokens unconfigured/disabled → no file, no warning, exit 0; tokens loaded with zero matches → file written with an empty list, no warning.
- [x] The resulting template renders correctly against a *second, different* source document of the same kind — the fan-out case. **Oracle:** the test runs `templatize` on artifact 1 to produce the template, then renders it against a hand-authored `data.json` for document 2 and asserts the render matches a checked-in expected output. The document-2 render must additionally contain **none** of document-1's region values (leak check), and document 2 must diverge from document 1 in schema shape — differing list length, an empty-string region, and a region requiring escaping — not merely in wording.
- [x] The **artifact-generating FSM loop** is never invoked by `templatize` or by any subsequent `render`. The Phase B region-discovery host call is the only host invocation on this path and is explicitly exempt; the `--regions` path makes no host call at all.
- [x] `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md`, and `docs/ARCHITECTURE.md` reflect the completed `templatize` subcommand.

## Impact

- **Priority**: P2 — the fan-out verification is the epic's stated
  user-facing payoff; the token report prevents a permanently un-themeable
  template from shipping silently.
- **Effort**: Medium — the token inversion and fan-out fixture are new but
  bounded; no round-trip transaction work (that's Phase A).
- **Risk**: Low — report-only, no rewrite; failure mode is an incomplete
  report, not a corrupted template.
- **Breaking Change**: No.

## Related Key Documentation

- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md` — parent issue
- `.issues/features/P2-FEAT-3314-ll-artifact-templatize-phase-a-deterministic-templating.md` — dependency (Phase A)
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design hub

## Status

**Open** | Created: 2026-08-24 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-24T23:46:29 - `24ee9cfe-f170-49b6-8033-1fd3d4cb16c3.jsonl`
- `/ll:ready-issue` - 2026-08-24T23:22:40 - `5a144609-b870-4cb5-957a-299a3147d587.jsonl`
- `/ll:confidence-check` - 2026-08-24T23:17:57 - `cbd1afbc-5d29-4047-86cf-cd522b3ae2d9.jsonl`
- `/ll:confidence-check` - 2026-08-24T23:10:36 - `0983d3ba-ecbc-4009-a3a3-518ba4c0fda1.jsonl`
- `/ll:refine-issue` - 2026-08-24T22:47:27 - `76c2d0e1-e226-4945-b3a3-bc157df99f76.jsonl`
- `/ll:refine-issue` - 2026-08-24T18:58:03 - `ffa41e96-ab11-4f72-8513-f6153385423a.jsonl`
- `/ll:format-issue` - 2026-08-24T18:48:19 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
- `/ll:issue-size-review` - 2026-08-24T18:42:58 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
