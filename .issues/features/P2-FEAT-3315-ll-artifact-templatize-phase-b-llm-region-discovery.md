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

FEAT-3314 (Phase A) — this phase calls `apply_regions`, `build_manifest`,
and the temp-build/promote/round-trip flow Phase A implements, and extends
the `cmd_templatize` CLI scaffold Phase A wires up (making `--regions`
optional: when absent, `discover_regions` runs instead).

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

### Call Path

`cmd_templatize` (from FEAT-3314, `cli/artifact/templatize.py`) -> [no
`--regions` given] -> `discover_regions` -> [same downstream flow as Phase A:
`apply_regions` -> `build_manifest` -> temp build -> `verify_round_trip` ->
promote]

`discover_regions` must not live in `artifact_templates.py` — that module
must never import `host_runner` or `anthropic` (module docstring, design
principle 2).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` — add `discover_regions`
  call path, wired as the default (no `--regions`) branch of `cmd_templatize`

### Tests
- Extend `scripts/tests/test_artifact_templatize.py` — schema validation
  failure test (mocked `discover_regions` response containing
  `additionalProperties`/`minItems`), missing-required-keys failure test
  (mocked host call), input-size-ceiling test (oversized combined input,
  assert no host call issued).

### Documentation
- `docs/reference/CLI.md` § `ll-artifact` — extend the `templatize` section
  for the default (LLM-driven) invocation

## Acceptance Criteria

- [ ] The emitted `data_schema` passes `_validate_schema_shape()`; a test feeds a `discover_regions` response containing `additionalProperties`/`minItems` and asserts the command fails loud before writing anything.
- [ ] A `discover_regions` response missing required keys raises rather than degrading to an empty result (Option A contract), asserted with a mocked host call.
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

## Status

**Open** | Created: 2026-08-24 | Priority: P2


## Session Log
- `/ll:issue-size-review` - 2026-08-24T18:42:58 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
