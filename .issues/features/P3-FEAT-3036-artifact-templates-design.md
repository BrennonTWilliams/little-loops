---
id: FEAT-3036
title: Artifact templates design
type: FEAT
priority: P3
status: done
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
- FEAT-3310
- FEAT-3311
verify_verdict: VALID
completed_at: '2026-08-24T04:16:48Z'
learning_tests_required:
- jinja2
confidence_score: 93
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 22
---

# FEAT-3036: Artifact templates design

## Summary

Generalize the `ll-artifact policy-builder` precedent into a reusable artifact
template system. Today each artifact produced by an FSM loop is a one-off snapshot
that goes stale when its source document changes; refreshing it re-pays the
entire refinement cost. The fix is to separate presentation (paid once at
template creation) from data (cheap to refresh).

## Current Behavior

Each artifact produced by an FSM loop (e.g. `ll-artifact policy-builder`,
loop-generated HTML dashboards) is a one-off snapshot: presentation and data are
baked together at generation time. When the source document changes, refreshing
the artifact re-pays the full LLM refinement cost — there is no template that
can be re-rendered cheaply. The only in-repo precedent for template/data
separation, `ll-artifact policy-builder`'s hand-built `/*__TOKEN__*/` stamp
scheme, is not reusable or user-creatable.

## Expected Behavior

A `.llat/` artifact template directory (manifest + Jinja2 body + optional
assets) can be authored once and rendered deterministically against arbitrary
`data.json` via `ll-artifact render`, with zero LLM cost per render. Templates
declare a data contract (`manifest.yaml`'s `data_schema`) validated before
render, so a template can be reused across many source documents (EPIC-3299's
primary use case) or refreshed cheaply against one bound source over time (the
secondary use case).

## Use Case

A user maintains a loop-generated HTML dashboard (e.g. a quarterly risk report
rendered from `docs/risk-register.md`). Today, refreshing it after the register
changes means re-running the full FSM loop from scratch. With artifact
templates, they instead author `quarterly-risk-report.llat/` once (extracting
the existing dashboard's presentation into `template.html.j2` plus a
`manifest.yaml` data contract), then run `ll-artifact extract` + `ll-artifact
render` (or `refresh`) whenever the register changes — one small LLM call plus
a zero-cost deterministic render, instead of a full loop run.

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
  path: docs/risk-register.md   # default bound source (hashes live in the
                                # sibling lockfile, never here — see § Second-pass
                                # decisions → Lockfile)
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
    Compare recorded source hashes to current ones; report FRESH /
    STALE / SOURCE-MISSING per (template, source) pair. Exit non-zero if
    anything is stale.

ll-artifact templatize <artifact> <source-file> [-o template-dir]
    Post-hoc extraction loop (Phase 4): produce template + data from an
    existing FSM-loop artifact, verified by round-trip fidelity.

ll-artifact policy-builder
    Existing subcommand; unchanged. Long-term it becomes a bundled
    template rendered through the same pipeline.
```

**Template argument resolution.** `<template>` is tried first as a filesystem
path (a `.llat/` directory); if that does not exist it is resolved as a name,
`<config.artifacts.templates_dir>/<name>.llat`. If neither exists, exit non-zero
naming both paths tried.

**Output path precedence.** The manifest's `output:` is a *filename*; `-o` is a
*directory*. Effective path = `(-o DIR | config.artifacts.default_output_dir) /
manifest.output`. The only error case is `-o` naming an **existing file**; a
directory name with a dot in it (`out.v2/`) is valid — no suffix heuristic.
`policy-builder`'s existing `--output` semantics (a directory resolved against
`default_output_dir`) stay authoritative for the family.

**"CI-gated" here means the local suite.** Per CLAUDE.md there is no hosted CI:
`status`'s non-zero exit is exercised by a pytest test that invokes it, not by a
workflow file.

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

**Scope correction (2026-08-23, second pass): this decision is recorded here but
implemented in FEAT-3304, not in this issue's `render`.** See § Second-pass
decisions → *Export modes and `artifacts.export` belong to FEAT-3304*. The mode
flag is an export-side concern (`ll-artifact <dashboard-cmd> --local`), never a
flag on `render`.

- Default export embeds only the registered shareable set. An explicit local
  mode may embed anything for personal use.
- Every artifact is visibly stamped with the mode (and allowlist version) that
  produced it.
- Configuration lives in `.ll/ll-config.json` (`artifacts.export` block), added
  by FEAT-3304.

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
    CSS; `{{`/`{%` can collide with template literals and style blocks.
    **Settled 2026-08-23 (second pass)** — see § Second-pass decisions →
    *Delimiter set and render determinism contract*.
- **Hashes: lockfile, not written back into `manifest.yaml`.** Keeps the manifest
  human-owned and hand-editable; machine state lives beside it. This is the same
  split as `.ll/ll.local.md`'s machine-written `## Active Rules` section. Lockfile
  keying is settled below (§ Second-pass decisions → *Lockfile is keyed by source
  path, not a scalar*).
- **Template location: `artifacts/templates/` under the project root**,
  configurable. Blocker: `ArtifactsConfig`
  (`config/features.py:369-384`) has exactly one field, `default_output_dir`, and
  `config-schema.json:1870-1880` sets `additionalProperties: false` — the schema
  will reject a templates-dir key until it is added. **This issue adds
  `templates_dir` only**; the `artifacts.export` block the 2026-07-31 decisions
  assume is FEAT-3304's to add (same blocker, different owner).

## Second-pass decisions (2026-08-23)

Recorded after a pre-implementation review. These close the remaining Phase-1
ambiguities so scaffolding can start.

### Delimiter set and render determinism contract

**Decision: a fixed, non-colliding delimiter set and a frozen environment
construction, both part of the Phase-1 render contract.**

```python
SandboxedEnvironment(
    variable_start_string="[[=", variable_end_string="=]]",
    block_start_string="[[%",   block_end_string="%]]",
    comment_start_string="[[#", comment_end_string="#]]",
    trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True,
    undefined=StrictUndefined, autoescape=False,
)
```

Verified empirically against the installed jinja2 3.1.6 (2026-08-23) on a source
containing `${x}` template literals, a `{{a:1}}` object literal, a `m[[0]][1]`
nested array index, and a literal `{% raw %}` string: all four survive rendering
untouched, `[[= … =]]` / `[[% … %]]` substitute correctly, `__class__` traversal
raises `SecurityError`, and an undefined name raises `UndefinedError`. This
extends `.ll/learning-tests/jinja2.md`'s custom-delimiter claim to the specific
set being adopted.

Rationale for each setting:

- `autoescape=False` — templates are carved out of already-rendered HTML by
  FEAT-3308; escaping would corrupt the round trip. Escaping is the *data
  producer's* job, and must be stated as such in the manifest spec.
- `StrictUndefined` — a missing key must fail loudly, not silently render empty.
  Schema validation (below) should catch this first; `StrictUndefined` is the
  backstop for anything the subset validator does not model.
- `trim_blocks` / `lstrip_blocks` / `keep_trailing_newline` — these three
  determine whitespace, and therefore determine whether FEAT-3308's round-trip
  diff can be byte-exact. **They are frozen here and are not per-template
  configurable.** Changing them is a template-format version bump.

**Round-trip fidelity is defined as byte-exact** on the rendered output versus
the original artifact, under this environment. FEAT-3308 may not relax this to a
normalized comparison without a matching change here — a normalized diff would
let whitespace drift accumulate invisibly across refreshes.

**Fixture requirement (Phase 1):** one checked-in template fixture whose body
contains `{{ }}`, `{% %}`, `${…}`, and `[[…]]` literal content, asserting it
renders through untouched. This fixture is **test-only**, under
`scripts/tests/fixtures/`. The hand-authored *reference* template (Phased plan,
Phase 1) is likewise test-only in v1; nothing ships as package data under
`scripts/little_loops/templates/` until `policy-builder` itself migrates.

### Template context: reserved `ll` namespace, no loader, `assets/` as text

**Decision: the template is loaded with `Environment.from_string()` and no
loader.** Consequently `include`/`extends`/`import` are unavailable and a
template is exactly one file; this is deliberate — a single body is what
FEAT-3308's round-trip carves out and diffs.

The render context is `data.json`'s top-level keys plus one reserved key, `ll`:

- `ll.theme_css` — the themed CSS-vars block produced by `load_design_tokens` +
  `render_as_css_vars_themed` over the project's active token set (the same
  light+dark pair `policy-builder`'s `_themed_css_vars` builds). Present only
  when `theme: design-tokens`; templates stamp it as `[[= ll.theme_css =]]`.
- `ll.assets` — a `dict[str, str]` of every file under `assets/`, keyed by
  relative path, read as UTF-8 text. Binary assets (data-URI encoding) are v2.

`data.json` containing a top-level `ll` key, or a `data_schema` declaring one,
is a validation error.

### Manifest strictness

`manifest.yaml` is validated on load with the same fail-closed posture as
`data_schema`: unknown top-level keys are a load error; `name`, `version`,
`renderer` (must be `jinja2`), `output`, and `data_schema` are required;
`theme` (only `design-tokens`), `source`, and `extraction` are optional.
The subset validator also checks **schema well-formedness**, not only data:
`items` must be a single schema object (no tuple form), `required`/`properties`
are permitted only under `type: object`, `items` only under `type: array`,
`enum` must be a non-empty list of scalars.

### `data.json` validation: a declared JSON Schema subset, hand-validated

**Decision: no `jsonschema` dependency. `data_schema` is restricted to a
documented subset, validated by an in-repo validator that rejects unknown
constructs at manifest-load time.**

Supported subset: `type` (`object`/`array`/`string`/`number`/`integer`/
`boolean`/`null`), `required`, `properties`, `items`, `enum`, plus `description`
(ignored). Anything else in a `data_schema` — `oneOf`, `$ref`, `patternProperties`,
`additionalProperties`, `format`, numeric bounds — is a **manifest load error**,
not a silently-unenforced key. Failing closed at load time is what keeps the
subset honest: a template can never appear validated while carrying a construct
the validator ignores.

Rationale: `jinja2` is already one new dependency against CLAUDE.md's
minimize-dependencies rule; `jsonschema` would be a second, for a validator whose
used surface is roughly 60 lines. The same `data_schema` is also handed to the
host as a `json_schema=` generation constraint by `extract`/FEAT-3308, and that
path already constrains the usable shape. If a real template later needs a
construct outside the subset, promoting to `jsonschema` is a contained swap
behind the same call site — the subset validator must therefore live in one
module with one entry point, not be inlined into `cmd_render`.

### `ll-artifact` grows into the per-file subcommand convention

**Decision: per-file `add_*_parser` / `cmd_*` modules, as in `cli/issues/` and
`cli/loop/`.** At 5 new subcommands the inline `if args.command == …` chain in
`cli/artifact.py:275-357` is past the point where the two-command inline
convention holds. Move `cli/artifact.py` to a `cli/artifact/` package with
`policy_builder.py` and `design_md.py` carrying the existing handlers unchanged,
and one module per new subcommand. This is decided in the hub so FEAT-3308 and
FEAT-3309 do not each re-litigate it.

Handler signature and error shape stay as they are today:
`cmd_<name>(args: argparse.Namespace, logger: Logger) -> int`, own
`BRConfig(Path.cwd())`, blanket `try/except Exception` → 0/1.

The package's `__init__.py` **must re-export** `main_artifact`,
`cmd_policy_builder`, `cmd_design_md_export`, and `_themed_css_vars` — existing
tests import and patch them at `little_loops.cli.artifact.*`
(`test_policy_builder_emit.py:15,215`, `test_design_tokens.py:664`,
`test_enh3268_design_md_export.py:354`). The `pyproject.toml:70` entry point
(`little_loops.cli:main_artifact`) is unaffected.

### Lockfile is keyed by source path, not a scalar

**Decision: the lockfile records a mapping, not a single hash.** The manifest's
`source:` block stays a *default* binding for the single-bound-source case
(EPIC-3299's secondary use case), but the lockfile that tracks freshness is keyed
by rendered source path:

```yaml
# my-report.llat.lock  (machine-written)
version: 1
renders:
  docs/risk-register.md:   {sha256: …, rendered_at: …, output: …}
  docs/risk-register-eu.md: {sha256: …, rendered_at: …, output: …}
```

A scalar `source.sha256` models only "one template, one source over time" and
cannot express EPIC-3299's *primary* use case (one template, many source
documents). Since the lockfile is new in Phase 3 and has no back-compat burden,
it is cheaper to key it correctly now than to migrate it later.

`status` reports per (template, source) pair.

### Export modes and `artifacts.export` belong to FEAT-3304

**Decision: `render` stays pure; no `--local` flag, no history.db access.**

The 2026-07-31 export-mode decision (reproduced above) placed a `--local` flag on
`ll-artifact render`. That contradicts design principle 2 — `render` is
`template + data.json → artifact`, deterministic and reproducible — because it
would make output depend on ambient database state. Data provenance and
redaction are the *producer's* problem (`extract`, or FEAT-3304's export
filter), never the renderer's.

Consequently this issue adds **only** `artifacts.templates_dir` to
`ArtifactsConfig` / `config-schema.json`. The `artifacts.export` block and its
allowlist land in FEAT-3304, which is the only code that reads them; adding them
here would ship config keys with no consumer.

### `extract`'s LLM invocation — resolved by FEAT-3308

Recorded for the hub: FEAT-3308 settled this as a **direct
`build_blocking_json(json_schema=…)` host call that fails loud** (advisor.py's
shape), explicitly rejecting `learning_tests/extractor.py`'s fail-soft
prose-marker parse — a silently-empty `data_schema` would be indistinguishable
from "the LLM found nothing" and would corrupt round-trip diagnosis. Phase 2's
`extract` follows the same shape. The "reuse loop machinery for free logging"
option is dropped: the logging benefit does not offset making a pure CLI step
depend on FSM run context.

## Open questions

- ~~How does `extract` invoke the LLM — through existing loop/agent machinery or
  a direct call?~~ **Resolved 2026-08-23** — direct `build_blocking_json`,
  fail-loud; see § Second-pass decisions.
- Non-HTML artifact types (images, diagrams): render step differs (e.g. SVG
  template → PNG rasterization). Manifest `renderer` field is the extension
  point; out of scope for v1.

## Impact

- **Priority**: P3 - Planning/design hub for EPIC-3299's artifact-template
  initiative; blocks FEAT-3308, FEAT-3309, FEAT-3304, and ENH-3035 from
  starting, but is not itself urgent user-facing work.
- **Effort**: Large - new Jinja2 dependency, new `ll-artifact` subcommand
  family, config schema changes, and a `cli/artifact/` package restructure,
  though scoped to Phase 1 only (template format + `render`).
- **Risk**: Medium - introduces a new third-party dependency (`jinja2`) and
  restructures `cli/artifact.py`; mitigated by keeping `policy-builder` /
  `design-md export` behavior unchanged with their existing tests passing
  untouched.
- **Breaking Change**: No

## Acceptance Criteria

Scoped to **Phase 1** — the template format plus `render`, which is the hard
prerequisite for FEAT-3308, FEAT-3309, FEAT-3304 and ENH-3035. Phases 2 and 3
should be split into their own child issues before implementation, the way
Phase 4 was split into FEAT-3308/3309; this hub retains the design and the
decisions, not their acceptance criteria.

- [ ] `jinja2` is pinned in `scripts/pyproject.toml` with a justifying comment in
      the `anthropic`/`psutil` style, citing FEAT-3036 and the
      repeated-regions requirement that `.replace()` cannot meet.
- [ ] A `.llat/` template directory (`manifest.yaml` + `template.html.j2` +
      optional `assets/`) loads, validates, and renders through
      `ll-artifact render <template> --data data.json`.
- [ ] The Jinja2 environment is constructed exactly as frozen in § Second-pass
      decisions, and a test asserts each of the six delimiter strings and the
      three whitespace flags — a silent change to any of them breaks FEAT-3308's
      byte-exact round trip, so it must fail a test rather than a review.
- [ ] A fixture template whose body contains literal `{{ }}`, `{% %}`, `${…}`
      and `[[…]]` renders with all four preserved byte-for-byte.
- [ ] `render` performs no LLM call: the render module imports nothing from
      `host_runner` or `anthropic`, asserted by a test that patches
      `resolve_host` and verifies it is never called. Rendering the same
      template + data twice produces byte-identical output.
- [ ] The environment uses `from_string()` with no loader; a template using
      `[[% include %]]` fails with a clear error (test).
- [ ] `ll.theme_css` and `ll.assets` are populated per § Template context; a
      top-level `ll` key in `data.json` or `data_schema` is rejected (test).
- [ ] Manifest load rejects unknown top-level keys, missing required keys,
      `renderer` ≠ `jinja2`, and each malformed-schema shape listed under
      § Manifest strictness (test per case).
- [ ] `<template>` resolves path-first, then `templates_dir/<name>.llat`; the
      not-found error names both paths tried (test).
- [ ] `data.json` is validated against `manifest.data_schema` before rendering;
      a schema violation exits non-zero with the offending path, and nothing is
      written.
- [ ] A `data_schema` containing a construct outside the documented subset
      (`oneOf`, `$ref`, `patternProperties`, `additionalProperties`, `format`,
      numeric bounds) fails at **manifest load**, with a test per rejected
      construct.
- [ ] The subset validator lives in a single module behind a single entry point,
      so a later swap to `jsonschema` is a one-call-site change.
- [ ] `theme: design-tokens` stamps themed CSS vars via the existing
      `load_design_tokens` / `render_as_css_vars_themed` path — no second copy of
      `policy-builder`'s `_themed_css_vars`.
- [ ] `artifacts.templates_dir` (default `"artifacts/templates"`, identical in
      the dataclass and the schema) is added to `ArtifactsConfig`, its `from_dict()`,
      `config/core.py`'s serialization dict (:916-918), and
      `config-schema.json`'s `artifacts` block; `TestSchemaValueParity` passes
      and `test_artifacts_in_schema` is extended to assert the new key.
      **`artifacts.export` is explicitly not added here** — it is FEAT-3304's.
- [ ] `cli/artifact.py` is a `cli/artifact/` package with one module per
      subcommand; `__init__.py` re-exports `main_artifact`, `cmd_policy_builder`,
      `cmd_design_md_export`, `_themed_css_vars`; `policy-builder` and
      `design-md export` behaviour is unchanged and their existing tests pass
      untouched.
- [ ] Output path precedence (`-o` as directory, `manifest.output` as filename)
      is implemented and tested, including the error case where `-o` names an
      existing file and the non-error case of a dotted directory name (`out.v2`).
- [ ] Phase 2 (`extract` + `refresh`) and Phase 3 (`status` + lockfile) are
      filed as child issues of EPIC-3299 before this issue is marked done, so the
      hub keeps design and decisions only.
- [ ] `docs/reference/CLI.md` (`### ll-artifact`) and
      `docs/reference/CONFIGURATION.md` (`### artifacts`) document `render` and
      `templates_dir`.
- [ ] `python -m pytest scripts/tests/` exits 0.


## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

### Files to Modify

- `scripts/little_loops/cli/artifact.py` — the existing `ll-artifact` CLI (currently
  `policy-builder` + `design-md export`, two inline subcommands with a manual
  `if args.command == ...` dispatch chain, `main_artifact()` at lines 275-357).
  **Becomes a `cli/artifact/` package** (decided 2026-08-23, second pass), one module
  per subcommand, following `cli/issues/` and `cli/loop/`.
- `scripts/little_loops/config/features.py:369-384` — `ArtifactsConfig` needs a
  `templates_dir` field added to the dataclass and its `from_dict()`. (The `export`
  sub-block from the 2026-07-31 decisions is **FEAT-3304's**, not this issue's — see
  § Second-pass decisions.)
- `scripts/little_loops/config/core.py:339,476,916-918` — `BRConfig` construction,
  `.artifacts` property, and the config-dump serialization dict all need the matching
  new field(s); the serialization dict at :916-918 is easy to miss since it silently
  drops any dataclass field not explicitly re-listed there.
- `scripts/little_loops/config-schema.json:1870-1880` — the `artifacts` block's
  `additionalProperties: false` (line 1879) rejects any new key until added under
  `properties` here.
- `scripts/pyproject.toml:40-59` — `jinja2` is not currently a dependency; adding it
  needs a justifying comment in the `anthropic`/`psutil` style (see Program Design →
  Decision Rules).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/__init__.py` — registers the `ll-artifact` CLI entry-point
  dispatch; any new subcommand surfaces through this registration.
- `scripts/little_loops/design_tokens.py` — `load_design_tokens` /
  `render_as_css_vars_themed` are imported by `cli/artifact.py`'s `_themed_css_vars` and
  would be the reuse point for a template's `theme: design-tokens` stamping.
- `scripts/little_loops/frontmatter.py` (`parse_skill_frontmatter`) and
  `scripts/little_loops/fsm/policy_rules.py` (`grammar_spec`) — consumed by
  `cmd_policy_builder` for its two other stamp values; relevant only if
  `policy-builder` is later migrated onto the new template pipeline per the issue's
  "long-term it becomes a bundled template" note.

### Conventions in Force

- Placeholder substitution in this codebase is always flat, single-pass, no
  repeated/conditional regions — true of all three existing schemes (`sed`-based
  `{{name}}` in `loops/cli-anything-bootstrap.yaml:441-467`, Python `.replace()`
  token-stamping in `cli/artifact.py:132-137`, and regex `{{config.xxx}}` substitution
  in `skill_expander.py:55-69`). None contradicts the design's Jinja2 rationale, but
  none validates it either — the codebase has no existing case of a
  loop/conditional templating need being met by a hand-rolled substitution scheme.
- New CLI handler functions in this file family follow `(args: argparse.Namespace,
  logger: Logger) -> int`, build their own `BRConfig(Path.cwd())`, and wrap the body in
  a blanket `try/except Exception` returning 0/1 — evidence: `cmd_policy_builder`,
  `cmd_design_md_export` (`cli/artifact.py`).
- Third-party dependency pins that need justification carry a multi-line comment above
  the pin citing the originating issue and the specific risk being guarded against —
  evidence: `anthropic>=0.104,<1.0` and `psutil>=5.9` (`scripts/pyproject.toml:46-58`).
  Unjustified pins (`pyyaml`, `ruamel.yaml`, `wcwidth`, `questionary`, `rich`) carry no
  such comment and use a bare lower bound.
- Machine-derived state synced beside (not into) a human-owned file is precedented by
  `decisions_sync.py::sync_to_local_md()`, which rewrites only the `## Active Rules`
  section of `.ll/ll.local.md` in place via `atomic_write`, leaving the rest of the file
  untouched — the model this issue cites for keeping template hashes in a lockfile
  rather than writing them into `manifest.yaml`.
- sha256 content-hash staleness detection is precedented once, in
  `codequery/codegraph.py:124-189` (`_sha256_file` + `_content_aware_head_moved`), but
  that precedent stores its comparison baseline inside an existing SQLite index column,
  not a standalone lockfile file — the two disagree on where the baseline lives, so this
  is not a clean precedent for a `.llat` lockfile's storage format.
- LLM extraction into structured JSON has two disagreeing in-repo shapes: `advisor.py`'s
  `_VERDICT_SCHEMA` passed as a `json_schema=` generation constraint to
  `build_blocking_json`, versus `learning_tests/extractor.py`'s prose-marker
  (`TARGETS_JSON:{...}`) + regex parse, routed through `resolve_host()` and fail-soft on
  any parse/host error. Either shape is available as precedent for Phase 2's `extract`
  subcommand; the issue's own open question ("does `extract` reuse loop/agent machinery
  or call the host directly") is not resolved by either precedent alone.

### Tests

- `scripts/tests/test_policy_builder_emit.py`, `test_policy_builder_corpus.py`,
  `test_policy_builder_node_gate.py` — existing coverage for `cmd_policy_builder`; no
  `test_*artifact*.py`-named file exists, so new `render`/`extract`/`refresh`/`status`/
  `templatize` coverage would need a new test module or an extension of these.
  `test_enh3268_design_md_export.py` and `test_design_tokens.py` cover the other two
  reuse points (`design-md export`, design-token stamping). Both existing dispatch
  tests (`test_policy_builder_emit.py::TestArtifactCLIDispatch`,
  `test_enh3268_design_md_export.py::TestArtifactCLIDispatchDesignMd`) mock
  `cmd_<name>` and assert only argv-routing/return-code propagation — new
  `cmd_render`/`cmd_extract`/`cmd_refresh`/`cmd_status`/`cmd_templatize` need both a
  handler-level test (direct call with `argparse.Namespace` + `Logger`, asserting
  exit code and output, per `TestCmdDesignMdExport`) and a dispatch-level mock test.
- `scripts/tests/test_config_schema.py` — the file's dominant pattern for schema keys is
  structural sentinel assertion (`test_*_in_schema` methods, ~30+ instances,
  explicitly documented as not invoking a runtime validator) — the precedent a new
  `templates_dir`/`export` schema test would follow.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py::test_artifacts_in_schema` (~line 473) — only
  asserts `default_output_dir`'s type/default today; will keep passing unmodified
  after `templates_dir`/`export` are added unless extended with matching assertions
  (mirror `test_design_tokens_in_schema`'s per-field pattern) — it will not fail-closed
  on its own. [Agent 3 finding]
- `scripts/tests/test_config_schema.py::TestSchemaValueParity` (`test_to_dict_values_match_schema_defaults`,
  `test_guard_is_non_vacuous`) — automatic safety net (BUG-3192) that diffs
  `BRConfig(...).to_dict()` leaves against `config-schema.json` defaults; will catch a
  `templates_dir`/`export` field added to the dataclass + `to_dict()` but omitted from
  the schema (or vice versa) without further edits, unless a field is deliberately
  schema-less, in which case it needs an entry in `_SCHEMA_DEFAULT_ALLOWLIST`. [Agent 2
  finding]
- `scripts/tests/test_design_tokens.py` (lines 664, 673, 682) — existing coverage of
  `_themed_css_vars` imported from `cli/artifact.py`; not previously listed as touching
  this file. [Agent 1 finding]
- `scripts/tests/test_codequery_codegraph.py` (`test_commit_of_already_indexed_content_stays_fresh`,
  `test_commit_of_genuinely_new_content_reports_stale`,
  `test_auto_sync_not_triggered_when_content_matches`) — the one in-repo test pattern for
  sha256 content-hash staleness detection (temp git repo + sqlite fixture with a
  `content_hash` column, `monkeypatch.chdir`, assert on a `.status()` call); the closest
  structural template for a new lockfile-staleness test in Phase 3. [Agent 3 finding]
- No `jinja2` test coverage exists anywhere in the repo (confirmed: zero references
  under `scripts/`) — new Jinja2-rendering tests have no in-repo precedent to extend,
  only the `.replace()`-token-stamping tests (`test_policy_builder_emit.py`,
  `test_policy_builder_corpus.py`) as a structural analogue (string-containment
  assertions on rendered output). [Agent 3 finding]
- No subprocess-invoked end-to-end test exists for the `ll-artifact` CLI — both existing
  dispatch tests mock the handler rather than shelling out to the installed
  `ll-artifact` entry point. [Agent 3 finding]
- No test enforces the "justification comment above unusual pins" convention this issue
  cites for the `jinja2` pin — it is a CLAUDE.md/code-review norm only, not an automated
  gate (searched `scripts/tests/` broadly, no match). [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (`### ll-artifact` section, ~lines 4455-4502) — describes only
  `policy-builder` and `design-md export` today, including a subcommand table and an
  `--output`/`-o` row referencing `config.artifacts.default_output_dir`; needs matching
  `####` sections and table rows for `render`/`extract`/`refresh`/`status`/`templatize`.
  [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` (`### artifacts` section, lines 910-924) — documents
  the `artifacts` block with a one-row key table (`default_output_dir` only) and a JSON
  example, plus a "Currently backs the `policy-builder` subcommand..." sentence; needs
  new rows for `templates_dir`/`export` and an updated prose sentence. [Agent 2 finding]

Confirmed no-touch (checked, not needed): `docs/reference/API.md`, `docs/ARCHITECTURE.md`
(no `ArtifactsConfig`/artifact-CLI-specific section in either — matches were generic uses
of the word "artifact"); `skills/configure/areas.md` and its per-host mirrors (no
artifacts-config prompts exist to update); `scripts/little_loops/init/writers.py`'s
`_LL_PERMISSIONS` (already has a `"Bash(ll-artifact:*)"` wildcard covering new
subcommands); `config/core.py::_DATACLASS_SECTION_MAP` (only needs an entry for a *new*
dataclass, not new fields on `ArtifactsConfig`). [Agents 1–3]

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

### Types

- `ArtifactsConfig` (`scripts/little_loops/config/features.py:369-384`) — currently one
  field, `default_output_dir: str = "."` (line 377); `from_dict()` at :380-383 does
  `data.get("default_output_dir", ".")`. Adding `templates_dir` (and the `artifacts.export`
  block from the 2026-07-31 decisions) requires: (1) a new dataclass field here, (2) a
  matching `.get()` line in `from_dict()`, and (3) a matching key in the serialization dict
  at `scripts/little_loops/config/core.py:916-918` (`BRConfig`'s config-dump path), which
  today only emits `"default_output_dir": self._artifacts.default_output_dir` — a field
  added to the dataclass but not to this dump silently vanishes on any config round-trip.
- `scripts/little_loops/config-schema.json:1870-1880` — the `artifacts` object block sets
  `additionalProperties: false` (line 1879, same pattern as the sibling `design_tokens`
  block's own `additionalProperties: false` at line 1868). A new key (`templates_dir`,
  `export`) is rejected by schema validation until added under `properties` here — this is
  a hard schema-level blocker independent of the dataclass change above.

### Signatures

- `cmd_policy_builder(args: argparse.Namespace, logger: Logger) -> int` and
  `cmd_design_md_export(args: argparse.Namespace, logger: Logger) -> int`
  (`scripts/little_loops/cli/artifact.py`) are the two existing handler signatures; both
  construct their own `BRConfig(Path.cwd())` internally, wrap their body in a blanket
  `try/except Exception` returning 0/1, and resolve output paths against
  `config.project_root` / `config.artifacts.default_output_dir`. New handlers
  (`cmd_render`, `cmd_extract`, `cmd_refresh`, `cmd_status`, `cmd_templatize`) would need
  the same signature and error-handling shape to stay consistent with this file.
- `render_as_css_vars_themed(light: DesignTokens, dark: DesignTokens) -> str`
  (`scripts/little_loops/design_tokens.py:688-707`) is the function a `theme:
  design-tokens` manifest field would need to invoke for CSS-var stamping, same as
  `policy-builder`'s `_themed_css_vars` helper (`cli/artifact.py:64-95`) does today.
- No `jinja2` symbols exist anywhere in the codebase to cite — `jinja2` is not currently a
  dependency (confirmed: zero hits in `scripts/pyproject.toml` and zero imports under
  `scripts/little_loops/`), so `SandboxedEnvironment` has no existing call site to anchor
  against yet.

### Call Path

`main_artifact()`'s dispatch is a flat `if args.command == ...: return cmd_*(args, logger)`
chain (`scripts/little_loops/cli/artifact.py:275-357`), not a registry/dict-based command
table. Today: `main_artifact` -> `cmd_policy_builder` -> `_themed_css_vars` ->
`design_tokens.load_design_tokens` -> `design_tokens.render_as_css_vars_themed`, then back
in `cmd_policy_builder`: five `.replace()` stamps against the loaded
`policy-router-builder.html.tmpl` string -> output-dir resolution against
`config.artifacts.default_output_dir` -> file write. Each new subcommand
(`render`/`extract`/`refresh`/`status`/`templatize`) would need its own
`subparsers.add_parser(...)` block plus a new branch in this same dispatch chain
(precedent: `cli/issues/__init__.py` and `cli/loop/__init__.py` instead use one
`add_*_parser`/`cmd_*` pair per file, imported into the group's `__init__.py` — the
codebase holds both the inline-in-one-file convention (`ll-artifact` today, 2 commands)
and the per-file convention (`ll-issues`, `ll-loop`, dozens of commands each) at
comparable subcommand counts). **Resolved 2026-08-23 (second pass): the per-file
convention.** See § Second-pass decisions → *`ll-artifact` grows into the per-file
subcommand convention*.

### Decision Rules

- **Template-substitution engine choice**: three placeholder-substitution schemes already
  exist in this codebase and none of them attempts repeated/iterated regions or
  conditionals — `sed`-based `{{name}}` (`loops/cli-anything-bootstrap.yaml:441-467`),
  Python `.replace()` token-stamping with `/*__TOKEN__*/` markers
  (`cli/artifact.py:132-137`), and a regex-based `{{config.xxx}}` single-pass substitution
  (`skill_expander.py:55-69`, used by skill/command markdown expansion, not by generated
  artifacts). None of the three is contradicted by the design's Jinja2 rationale, since
  none of them was ever asked to do what Jinja2's loops/conditionals do — but the codebase
  has no existing case of a `{{`/`{%`-delimited template colliding with literal `{{`/`{%`
  in generated content to validate the "delimiters must be chosen against generated
  content" concern against; `policy-router-builder.html.tmpl` contains zero `{{`/`{%`
  occurrences today, so the collision risk is real but currently unobserved in-repo.
- **Manifest schema validation**: `jsonschema` (the PyPI validator library) is not a
  dependency and has no runtime-validate-arbitrary-data-against-a-schema precedent in this
  codebase — existing "JSON Schema" usages are either structural sentinel tests against
  `config-schema.json`'s own shape (`test_config_schema.py`, ~30+ `test_*_in_schema`
  methods, explicitly documented as "not runtime validation") or schema-as-generation-
  constraint for LLM structured output (`advisor.py:142-158`'s `_VERDICT_SCHEMA`, passed to
  `build_blocking_json(json_schema=...)`). Validating a template's `data_schema` against a
  user-supplied `data.json` at CLI-invocation time is a new operation with no in-repo
  precedent to anchor an implementation decision to. **Resolved 2026-08-23 (second
  pass): no `jsonschema` dependency — a documented subset with an in-repo validator
  that fails closed at manifest load.** See § Second-pass decisions.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-23_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 67/100 → MODERATE

### Concerns
- Architecture Compliance: the Call Path research found this codebase holds both
  an inline-dispatch convention (`ll-artifact` today, 2 commands) and a per-file
  `add_*_parser`/`cmd_*` convention (`ll-issues`, `ll-loop`) at comparable
  subcommand counts; which one `ll-artifact` should grow into at 5+ subcommands
  is unresolved by precedent alone and should be decided before scaffolding the
  new subcommands.
- Issue Well-Specified (capped at 10/20): `format-check` flags two
  `stale_cli_flag` references (`ll-artifact render --local`, `ll-artifact
  templatize` — neither subcommand exists yet) and two missing directive
  sections (`Summary`, `Acceptance Criteria`). Both are expected for a
  forward-looking planning-hub design document rather than a defect, but they
  cap this criterion per the rubric.
- Ambiguity: two open decisions remain in scope for Phase 1 — the exact
  delimiter/region-marker convention to avoid collision with `{{`/`{%` in
  generated JS/CSS content (now confirmed real via the jinja2 learning test
  below — default delimiters raise `TemplateSyntaxError` on JS-object-literal-
  like content), and how `extract` should invoke the LLM (existing loop/agent
  machinery vs. a direct host call) — the issue's own "Open questions" section
  leaves this unresolved.

### Resolution (2026-08-23, second pass)

All three concerns above are addressed in § Second-pass decisions: the CLI layout
is decided (per-file package), the delimiter set and render determinism contract
are fixed and empirically verified, `extract`'s LLM path is resolved via
FEAT-3308, and `Summary` + `Acceptance Criteria` sections now exist. The
`stale_cli_flag` hits for `ll-artifact templatize` / `render --local` are
likewise settled — `templatize` is FEAT-3308's forward reference, and `--local`
has been removed from the render path entirely as a violation of design
principle 2. A re-run of `/ll:confidence-check` should re-score ambiguity.

_jinja2 learning test provisioned this run: `.ll/learning-tests/jinja2.md`,
status `proven`, 5/5 claims passed — repeated/conditional regions, sandboxed
attribute blocking, delimiter collision on literal `{{ }}`-like content, custom
delimiters avoiding that collision, and loader-free `from_string()` rendering
are all confirmed against the installed jinja2 3.1.6._

## Status

**Open** | Created: 2026-08-03 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-08-24T04:16:28 - `330c8faf-d041-4098-aec0-965ac9b99312.jsonl`
- `/ll:ready-issue` - 2026-08-24T03:45:46 - `c65f5828-5738-4ffa-9215-73b22b8fcbaa.jsonl`
- `/ll:confidence-check` - 2026-08-24T03:27:57 - `75fd46f8-3745-4383-ae9f-e2749df5c760.jsonl`
- `/ll:confidence-check` - 2026-08-24T03:14:39 - `073198e9-3f33-4b28-94f3-e0a8ed10b406.jsonl`
- `/ll:wire-issue` - 2026-08-24T03:08:29 - `c3165230-5d93-4a9d-934b-c7e96cbc8715.jsonl`
- `/ll:refine-issue` - 2026-08-24T03:02:07 - `8e84ed7c-557b-45a9-a518-b89638519037.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:47 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
