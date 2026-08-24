---
id: FEAT-3315
title: '`ll-artifact templatize` Phase B: LLM region discovery'
type: FEAT
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-24'
parent: FEAT-3308
depends_on:
- FEAT-3314
relates_to:
- FEAT-3308
- FEAT-3309
labels:
- artifact
- ll-artifact
- templates
decision_needed: false
confidence_score: 85
outcome_confidence: 70
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

# FEAT-3315: `ll-artifact templatize` Phase B: LLM region discovery

## Summary

Decomposed from [FEAT-3308](P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md).
Adds `discover_regions`, the LLM stage that makes `ll-artifact templatize`
usable without a hand-written `--regions` map: given `artifact.html` and
`source.md`, identify the spans of the artifact derived from the source
versus presentation spans, and emit a `DiscoveryResult` (`data_schema`,
`data`, region map) that [FEAT-3314](P2-FEAT-3314-ll-artifact-templatize-phase-a-deterministic-templating.md)'s
`apply_regions` splices in.

## Parent Issue

Decomposed from FEAT-3308: `ll-artifact templatize`: save a generated
artifact as a reusable template.

## Depends On

**Resolved** — FEAT-3314 (Phase A) is **done**; dependency satisfied. This phase calls
`apply_regions`, `build_manifest`, and the temp-build/promote/round-trip
flow Phase A implements.

It also extends the `cmd_templatize` CLI scaffold Phase A wires up: when
`--regions` is absent, `discover_regions` runs instead.

## Current Behavior

`ll-artifact templatize` (Phase A, [FEAT-3314](P2-FEAT-3314-ll-artifact-templatize-phase-a-deterministic-templating.md))
only accepts `--regions <map.json>` — a hand-written region map. There is no
way to templatize an artifact without first manually locating and typing out
every region's byte offsets and Jinja2 expression.

## Expected Behavior

```bash
ll-artifact templatize .loops/runs/html-anything/index.html docs/ARCHITECTURE.md \
    -o artifacts/templates/arch-review.llat
```

(no `--regions` flag) calls `discover_regions` to have the LLM identify the
source-derived spans, producing the same `DiscoveryResult` shape Phase A's
`apply_regions` consumes. A `data_schema` that fails `_validate_schema_shape()`
or a response missing required keys fails loud before anything is written to
disk; a combined artifact+source input over the configured size ceiling exits
non-zero naming the measured size, with no host call issued.

## Use Case

The same user from Phase A's use case, but without the time or domain
knowledge to hand-locate every region by byte offset — they just want to run
`templatize` against an artifact and its source and get a working template.
`discover_regions` is what makes `templatize` usable without first learning
the region-map format.

## Proposed Solution

1. **`discover_regions` via schema-forced structured output.** Use
   `build_blocking_json(json_schema=...)` (Option A — see Decision
   Rationale below), fail-closed by replicating `advisor.consult()`'s
   `issubset` key-check (`advisor.py:267-278`), since `json_schema=`
   build-time enforcement is host-dependent (Codex-only —
   `host_runner.py:442-465`; Claude Code drops the kwarg). The prompt must
   state the `data_schema` allowed-key subset
   (`{type, required, properties, items, enum, description}` — an LLM asked
   for "a JSON Schema" will volunteer `additionalProperties`, `minItems`,
   `format`, `oneOf` by default, all a hard `ManifestError`) and the
   capture-values-as-they-appear-in-the-byte-stream rule.

2. **Input size ceiling.** Stage 1 sends the whole artifact plus the source
   document in one `build_blocking_json` call, and the artifacts this
   targets run ~100KB. There is no chunking strategy in v1. The command
   enforces an explicit combined-input ceiling (default configurable, sized
   against the host's context window) and fails loud with the measured size
   when exceeded, rather than issuing a call that silently truncates and
   returns a plausible-looking partial region map that then fails the round
   trip for an unrelated-looking reason.

3. **In-process schema validation.** Validate the returned `data_schema`
   with `_validate_schema_shape()` before any write — a `discover_regions`
   response volunteering a forbidden key must fail loud before anything is
   written to disk.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Resolve the `load_regions()` contract conflict flagged above: either strip
  `data`/`data_schema` from the LLM response before constructing a
  `{regions, groups}`-only payload for `load_regions()`, or loosen
  `load_regions()`'s `_MAP_ALLOWED_KEYS` — and if the latter, update
  `test_rejects_data_key`/`test_rejects_data_schema_key`
  (`test_artifact_templatize.py:56-65`), which currently assert this is
  rejected
- Update `scripts/little_loops/config/core.py` — thread the new
  `artifacts` ceiling config key through `BRConfig.to_dict()`'s
  hand-enumeration (`:917-920`)
- Update `scripts/little_loops/cli/artifact/__init__.py` — update
  `main_artifact()`'s `epilog=` example invocation and exit-codes block for
  the optional (no-`--regions`) branch
- Update `docs/reference/CONFIGURATION.md` — document the new `artifacts`
  ceiling key
- Add/extend `scripts/tests/test_config_schema.py` — `test_artifacts_in_schema`
  and `TestSchemaValueParity.test_to_dict_values_match_schema_defaults`
  (Guard 1) for the new ceiling key
- Add `discover_regions` unit tests mocking `build_blocking_json`/
  `run_blocking_json`, following `test_advisor.py`'s `TestConsult` pattern
- Add a CLI-level default-branch (no `--regions`) test in
  `test_artifact_templatize.py`, monkeypatching `discover_regions` the way
  `verify_round_trip` is monkeypatched at `:467-471`
- Add the input-size-ceiling test asserting no host call issued, following
  `test_render_makes_no_llm_call` (`test_feat3036_artifact_templates.py:345-353`)
- Add the UTF-8 byte-offset-vs-character-index adversarial regression test
  (no existing coverage — see Tests subsection)
- Add the manifest `source`/`extraction`-present, `theme`-omitted test

### Codebase Research Findings

This codebase holds two disagreeing conventions for an LLM-driven
discovery/extraction stage like `discover_regions`:

**Option A**: Schema-forced structured output via
`build_blocking_json(json_schema=...)`, as `advisor.consult()` does
(`advisor.py:147-190`, `_VERDICT_SCHEMA`). The schema is materialized into
the host-CLI call at build time; the caller checks
`_VERDICT_KEYS.issubset(result.keys())` and raises `BlockingJsonError` on any
mismatch — every failure is loud.

> **Selected:** Option A — schema-forced structured output, matching
> `advisor.consult()`'s raise-on-mismatch contract; see Decision Rationale
> below.

**Option B**: Prompt-embedded schema with a regex-scraped envelope, as
`learning_tests/extractor.py` does (`_default_llm_call:116`,
`extract_learning_targets:195`). `build_blocking_json` is called with no
`json_schema=` argument; the contract is a `TARGETS_JSON:{...}` marker the
prompt asks the model to emit, scraped by regex. Every failure mode
(timeout, missing binary, non-zero exit, bad JSON, no regex match) degrades
to an empty result rather than raising — documented as "a best-effort safety
net" (`extractor.py:126-128`).

### Decision Rationale

**Selected**: Option A — schema-forced structured output via
`build_blocking_json(json_schema=...)`, matching `advisor.consult()`'s
raise-on-mismatch contract (`advisor.py:147-190`, `267-278`).

**Reasoning**: Option B's fail-soft-to-empty-result contract
(`extractor.py:126-128`) directly contradicts this phase's explicit
"fail-closed against the emitted schema" requirement — a silently-empty
`data_schema` would look identical to "the LLM found nothing" rather than
"the call failed," corrupting the round-trip verify stage's diagnosis.
Option A's `BlockingJsonError` raise-on-mismatch (`advisor.py:272-278`) is
the codebase's only precedent that actually fails loud.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2 | 0 |
| Simplicity | 2 | 2 |
| Testability | 3 | 1 |
| Risk | 2 | 0 |
| **Total** | **9/12** | **3/12** |

**Key evidence**:
- `advisor.py:267-278` — Option A's raise-on-mismatch shape, directly copyable
- `extractor.py:116-227` — Option B's fail-soft design, explicitly documented as a "best-effort safety net," incompatible with this phase's fail-closed requirement
- `host_runner.py:442-465,736-770` — `json_schema=` is Codex-only at the builder level; Claude Code (default host) silently drops it, so caller-side key-checking is required regardless of option chosen

## Program Design

### Signatures

- `discover_regions(artifact_html: str, source_text: str, prompt: str | None) -> DiscoveryResult` — the LLM stage; the only function on this call path that touches `host_runner`

**`DiscoveryResult` shape is defined by FEAT-3314, not here.** Phase A owns
the contract and its fail-closed loader `load_regions()` (FEAT-3314 §
Proposed Solution 3b); `discover_regions` must validate its LLM response
through that same function rather than reimplementing the checks — that is
what makes the `--regions` map and the LLM output the same artifact. Two
constraints carry over and must be stated in the discovery prompt: `Region`/
`RegionGroup` `start`/`end` are **UTF-8 byte offsets** (not character
indices), and a `RegionGroup` additionally declares its own span plus the
ordered `iterations` sub-spans, whose non-region literal text must be
byte-identical across iterations.

### Call Path

`cmd_templatize` (from FEAT-3314, `cli/artifact/templatize.py`) -> [no
`--regions` given] -> `discover_regions` -> `build_blocking_json`
(`host_runner.py:442`, `json_schema=` path) -> [same downstream flow as
Phase A: `apply_regions` -> `build_manifest` -> temp build ->
`verify_round_trip` -> promote]

`discover_regions` must not live in `artifact_templates.py` — that module
must never import `host_runner` or `anthropic` (module docstring, design
principle 2).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **`load_regions()`'s actual current contract is narrower than "validate a populated `DiscoveryResult`"** (`scripts/little_loops/cli/artifact/templatize.py:148-185`): it takes a file `Path`, `json.loads()`s it, and its top-level key check (`_MAP_ALLOWED_KEYS = {"regions", "groups"}`, line 86) hard-rejects any input carrying `data`/`data_schema` — `RegionMapError: "unknown top-level key(s) ... 'data'/'data_schema' are derived outputs, not inputs"`, asserted by `TestLoadRegions.test_rejects_data_schema_key` (`scripts/tests/test_artifact_templatize.py:61-65`). Every successful `load_regions()` call returns `DiscoveryResult(data_schema={}, data={}, regions=..., groups=...)` — `data`/`data_schema` are always zeroed, never populated from the input.
- **Consequence for this issue's stated design**: `discover_regions`'s LLM response (which per this issue's Proposed Solution *does* carry a populated `data_schema`) cannot be routed through `load_regions()` unmodified — that function's own fail-closed check exists specifically to reject a `data_schema`-bearing input. Either (a) `discover_regions` must strip `data`/`data_schema` from the LLM response before constructing a `{regions, groups}`-only payload for `load_regions()` (matching Phase A's existing pattern, where `data`/`schema` are separately derived downstream via `extract_data`/`derive_schema`, not read off `DiscoveryResult.data`/`.data_schema` at all — confirmed: nothing in `extract_data`/`derive_schema`/`apply_regions`/`build_manifest` reads those two fields), or (b) `load_regions()` itself needs new surface area to accept them. This must be resolved explicitly; as written, "validated through FEAT-3314's `load_regions()`" and "the emitted `data_schema` passes `_validate_schema_shape()`" are two different validation paths that do not currently compose the way the Proposed Solution implies.
- **`_validate_schema_shape()`** (the function the Acceptance Criteria cite for rejecting `additionalProperties`/`minItems`) lives in `scripts/little_loops/artifact_templates.py:85-140`, not in `templatize.py`, and today only runs inside `load_manifest()` (`artifact_templates.py:178`), itself only reached via `verify_round_trip()` deep in `cmd_templatize`'s temp-build phase (`templatize.py:699`) — after files are already written to `tmp_dir`, before promotion. It is a separate check from anything `load_regions()` does.
- **`cmd_templatize`'s exception surface has no `host_runner` awareness today**: the outer `except (ManifestError, SpliceError, RegionMapError)` (`templatize.py:716-718`) does not include `BlockingJsonError` (`host_runner.py:2019-2031`), and `templatize.py` has a module-level constraint (docstring, line 9-10) against importing `host_runner`/`anthropic` directly — confirming the issue's existing Call Path note that `discover_regions` must live outside `artifact_templates.py`, and implying `cmd_templatize`'s except clause needs a `BlockingJsonError` arm (or `discover_regions`'s caller must translate it) for the new failure mode to surface as the documented exit codes rather than an uncaught traceback.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` — add `discover_regions`
  call path, wired as the default (no `--regions`) branch of `cmd_templatize`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/__init__.py` — `main_artifact()`'s
  `epilog=` string hardcodes an example invocation showing `--regions` as
  required-looking and an `Exit codes:` block scoped only to round-trip
  rejection (`0`/`1`/`2`); both need the optional (no-`--regions`) variant
  documented [Agent 2 finding]

### Tests
- Extend `scripts/tests/test_artifact_templatize.py` — schema validation
  failure test (mocked `discover_regions` response containing
  `additionalProperties`/`minItems`), missing-required-keys failure test
  (mocked host call), input-size-ceiling test (oversized combined input,
  assert no host call issued).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_advisor.py` — reuse `TestConsult`'s
  `resolve_host_named`/`run_blocking_json` patch-pair pattern (`:101-119`,
  `:210-250`, `pytest.raises(BlockingJsonError)`) for mocking
  `discover_regions`'s host call in the schema-validation and
  missing-required-keys tests, rather than hand-rolling a new `FakeRunner`
  [Agent 3 finding]
- `scripts/tests/test_feat3036_artifact_templates.py` — reuse
  `test_render_makes_no_llm_call` (`:345-353`,
  `resolve_host.assert_not_called()`) as the pattern for asserting the
  input-size-ceiling test issues no host call [Agent 3 finding]
- New test: UTF-8 byte-offset-vs-character-index adversarial regression test
  — no existing coverage found anywhere in the suite;
  `test_non_ascii_round_trips` (`test_artifact_templatize.py:582-606`) only
  exercises the *correct*-offset case via `bytes.index`, never a
  character-index-computed (wrong) region on non-ASCII content [Agent 3
  finding — gap]
- New test: manifest carries `source`/`extraction` and omits `theme` —
  model after `TestBuildManifest.test_builds_expected_shape`
  (`test_artifact_templatize.py:333-347`, which already asserts
  `"theme" not in manifest`) [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — extend `test_artifacts_in_schema`
  (`:473-493`) and `TestSchemaValueParity.test_to_dict_values_match_schema_defaults`
  (`:1268-1290`, "BUG-3192 Guard 1") for the new input-size-ceiling config
  key; Guard 1 walks every `BRConfig().to_dict()` leaf against
  `config_mod.schema_default(path)` and raises if a new `artifacts.<key>`
  leaf has no matching schema default [Agent 2 finding]

### Documentation
- `docs/reference/CLI.md` § `ll-artifact` — extend the `templatize` section
  for the default (LLM-driven) invocation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `### \`artifacts\`` section (table +
  JSON example) needs a row added for the new input-size ceiling key
  [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py` — `BRConfig.to_dict()` (`:917-920`)
  hand-enumerates the `artifacts` keys (`default_output_dir`,
  `templates_dir`); the new ceiling field must be added there explicitly or
  it silently never appears in `to_dict()`/`ll-config show` output, and
  `test_config_schema.py`'s Guard 1 (above) will fail on the resulting
  schema/dataclass mismatch [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **Per-host `json_schema=` behavior in `host_runner.py`, confirmed at the implementation level**: `ClaudeCodeRunner.build_blocking_json` (`:442-471`) discards the kwarg entirely (`_ = json_schema` at `:465`) — the claude CLI's inline `--json-schema` flag exists but is only reachable through the separate `run_blocking_json(schema=...)` path (`:2034-2052`, `:2139-2140`), never through `build_blocking_json`'s own parameter. `CodexRunner.build_blocking_json` (`:736-770`) is the *only* implementation that materializes `json_schema` — it writes it to a `tempfile.NamedTemporaryFile` and passes `--output-schema <path>`, returning the temp path in `HostInvocation.cleanup_paths` for later cleanup. `GeminiRunner`/`OmpRunner` also silently drop it; `OpenCodeRunner`/`PiRunner` raise `HostNotConfigured` (stubs). This is strictly more detailed than the issue's existing citation and confirms caller-side key-checking is required on every host except Codex, not just Claude Code.
- **`context_window.py`'s `context_window_for()` (`:39-77`) is the existing "size a limit off the model/host" precedent** for the new input-size-ceiling config this issue proposes — five-tier precedence (explicit override → `LL_CONTEXT_LIMIT` env → `[1m]` model-id suffix → exact `MODEL_CONTEXT_WINDOW` lookup → 200k default floor). No existing `config-schema.json` key covers a raw combined-input-size ceiling (verified by grep — only an unrelated `hard_ceiling_pct` under compaction config exists); this ceiling is new schema, but `context_window_for()` is the pattern to model its model-awareness after.
- **Reusable `build_blocking_json` test fakes already exist**: `scripts/tests/test_action.py:40`, `scripts/tests/test_cli_harness.py:37`, and `scripts/tests/test_runner_spec.py:37,160` each define a fake `build_blocking_json` stub — usable scaffolding for mocking `discover_regions`'s host call in the schema-validation-failure and missing-required-keys tests this issue's Acceptance Criteria require.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- `scripts/little_loops/host_runner.py` — `resolve_host()`/`resolve_host_named()` is the required entry point per CLAUDE.md's Host CLI Abstraction; `ClaudeCodeRunner.build_blocking_json` (`:442-471`, discards `json_schema` at `:465`) and `CodexRunner.build_blocking_json` (`:736-770`, materializes it via `--output-schema <tempfile>`) are the two implementations `discover_regions` will actually run against in practice.
- `scripts/little_loops/advisor.py` — `consult()` (`:192-290`) is the concrete Option A precedent to model `discover_regions`'s call and raise-on-mismatch shape after: `_VERDICT_SCHEMA`/`_VERDICT_KEYS` module-level (`:149-160`), `build_blocking_json(..., json_schema=_VERDICT_SCHEMA)` call (`:269-271`), `_VERDICT_KEYS.issubset(result.keys())` check (`:274-280`, a subset check — extra keys tolerated, only missing required keys raise `BlockingJsonError`).
- `scripts/little_loops/config-schema.json` — the `"artifacts"` object schema (`:1875-1890`) has exactly two properties today (`default_output_dir`, `templates_dir`) and `"additionalProperties": false` (`:1889`) — the new input-size-ceiling config key must be added here or it will be schema-rejected. Python-side counterpart: `ArtifactsConfig` dataclass (`scripts/little_loops/config/features.py:369-386`).
- `scripts/little_loops/context_window.py` — `context_window_for(model, override)` (`:39-77`, five-tier precedence: explicit override → `LL_CONTEXT_LIMIT` env → `[1m]` model-id suffix → exact `MODEL_CONTEXT_WINDOW` lookup → 200k default floor) is the existing model-aware sizing precedent for the new combined-input ceiling.
- `docs/reference/CLI.md` — the `#### ll-artifact templatize` section (`:4532-4559`, re-verified current as of this pass since it changed after the prior refine) already has a Phase B forward-reference at line 4534 naming `discover_regions`/FEAT-3315, but its flags table (`:4544-4548`) still lists `--regions <path>` as unconditionally "required for Phase A," and its exit-code note (`:4557`) documents only Phase A's 0/1/2 semantics — both need the optional/no-`--regions` variant added.
- Existing `build_blocking_json`-backed test suites usable as a testing-pattern reference (not to modify): `scripts/tests/test_advisor.py`, `scripts/tests/test_host_runner.py`, `scripts/tests/test_learning_tests_extractor.py`, `scripts/tests/test_cli_advise.py`.

## Acceptance Criteria

- [ ] The emitted `data_schema` passes `_validate_schema_shape()`; a test feeds a `discover_regions` response containing `additionalProperties`/`minItems` and asserts the command fails loud before writing anything.
- [ ] A `discover_regions` response missing required keys raises rather than degrading to an empty result (Option A contract), asserted with a mocked host call — routed through FEAT-3314's `load_regions()`, not a Phase-B-local validator.
  > ⚠ Superseded — load_regions() rejects data/data_schema keys today
- [ ] A `discover_regions` response whose offsets are character indices rather than UTF-8 byte offsets is caught: a mocked-response test over a non-ASCII artifact asserts the run fails (round-trip rejection) rather than silently emitting an off-by-N template.
- [ ] A combined artifact+source input over the configured ceiling exits non-zero naming the measured size, with no host call issued.
- [ ] The emitted manifest carries `source` and `extraction`, and omits `theme`.

## Impact

- **Priority**: P2 — makes `templatize` usable without a hand-written region
  map; the epic's stated fan-out value depends on this, not just Phase A.
- **Effort**: Large — region discovery over an opaque self-contained file is
  the hard problem in the epic.
- **Risk**: Medium — the round-trip gate (Phase A) catches a bad region map
  but cannot repair it; residual risk concentrates in region-map quality.
- **Breaking Change**: No.

## Related Key Documentation

- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md` — parent issue
- `.issues/features/P2-FEAT-3314-ll-artifact-templatize-phase-a-deterministic-templating.md` — dependency (Phase A)
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design hub

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-24_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 70/100 → MODERATE

### Concerns
- AC #2 is marked `⚠ Superseded — load_regions() rejects data/data_schema keys today`: the Codebase Research Findings section confirms `load_regions()`'s `_MAP_ALLOWED_KEYS` check hard-rejects a `data`/`data_schema`-bearing payload, directly contradicting AC #2's "routed through FEAT-3314's `load_regions()`" requirement. The Wiring Phase section names two candidate resolutions (strip `data`/`data_schema` before calling `load_regions()`, or loosen `load_regions()`'s allowed-key set) but does not select one — this must be decided before AC #2 can be implemented as written.
- `stale_cli_flag` flagged `ll-config show (no such subcommand)` in the Codebase Research Findings' claim about `to_dict()`/`ll-config show` output — verify or correct this claim before relying on it.

## Status

**Open** | Created: 2026-08-24 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-24T21:15:01 - `f6542b25-721a-49ab-ba69-b9d4746b6ed4.jsonl`
- `/ll:wire-issue` - 2026-08-24T21:10:03 - `bf6a3113-6115-4098-8fb1-1cdb2c5eeb4c.jsonl`
- `/ll:refine-issue` - 2026-08-24T20:56:38 - `de9e1af4-5c22-4ebf-87ee-74fb60da3cea.jsonl`
- `/ll:refine-issue` - 2026-08-24T18:58:03 - `ffa41e96-ab11-4f72-8513-f6153385423a.jsonl`
- `/ll:format-issue` - 2026-08-24T18:48:18 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
- `/ll:issue-size-review` - 2026-08-24T18:42:58 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
