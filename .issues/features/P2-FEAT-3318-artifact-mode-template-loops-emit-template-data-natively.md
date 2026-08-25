---
id: FEAT-3318
title: '`artifact_mode: template`: loops emit template + data natively'
type: FEAT
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-24'
parent: EPIC-3299
depends_on:
- FEAT-3309
relates_to:
- FEAT-3308
- FEAT-3036
labels:
- artifact
- ll-artifact
- fsm
- templates
---

# FEAT-3318: `artifact_mode: template` — loops emit template + data natively

## Summary

Split out of FEAT-3309 (Part B) at the 2026-08-24 review. Adds the loop-output
contract from FEAT-3036 design principle 1: an FSM loop declares that its
deliverable is an artifact **template directory** (`manifest.yaml` + one
`template.*.j2` + `data.json`) rather than a single fused HTML file, and the runner
promotes and validates that shape directly — the lossless path, with FEAT-3308's
post-hoc `ll-artifact templatize` as the lossy fallback.

FEAT-3309 was carrying this as "Part B" alongside its promotion mechanism. They
differ in effort (Medium vs Large), risk (Low vs Medium), and subsystem (runner
finish path vs loop output contract plus generate-prompt rewrites), and fusing them
made both sets of acceptance criteria untestable in isolation.

## Current Behavior

- FEAT-3036 design principle 1 — "Artifact-producing FSM loops should emit template
  + data natively; post-hoc extraction is a second, lossier path" — is **unowned by
  any implementation issue** now that FEAT-3309 is promotion-only.
- Every HTML-producing loop writes a single fused `${run_dir}/index.html`
  (`html-anything.yaml:133`, `html-website-generator.yaml:78`, and seven siblings —
  full list in FEAT-3309 § Current Behavior).
- The only route from a loop artifact to a reusable template is
  `ll-artifact templatize` (FEAT-3308, **done**), which re-derives structure from
  finished HTML via an LLM discovery call — lossy by construction, and bounded by
  `artifacts.templatize_max_input_bytes` (`config/features.py:386`).
- No `fsm/validation/` rule — and no runtime check anywhere — inspects the
  filesystem for a loop's actual post-run output shape. Every rule found
  (`_validate_terminal_action_ok` `evaluator_rules.py:32`,
  `_validate_llm_evidence_contract` `:478`, `_validate_artifact_isolation` /
  `_validate_artifact_overwrite` `meta_rules.py:191,268`) operates purely on the
  statically parsed `FSMLoop`/`StateConfig` before execution; none opens a file
  handle.

## Expected Behavior

A loop can declare `artifact_mode: template`. On a non-failure terminal the runner
promotes the declared **directory** and verifies it is a loadable template — and
the result is directly accepted by `ll-artifact render` with no `templatize` step.

## Motivation

`templatize` reconstructs structure the generating loop already knew and threw
away. A loop that writes `data.json` alongside its Jinja2 body loses nothing, needs
no LLM discovery call, and has no round-trip fidelity risk. This is the lossless
half of the epic's fan-out story; without it the epic ships only the lossy half.

## Proposed Solution

### The template shape is already pinned — no design decision needed

FEAT-3309 left "exact manifest/body/data filenames" as an open decision. It is not
open: `artifact_templates.py` already fixes the contract, and these loaders are
what the check must call.

- `manifest.yaml` — `load_manifest(root)` (`artifact_templates.py:142`). Required
  keys `name`, `version`, `renderer`, `output`, `data_schema` (`:25`); optional
  `theme`, `source`, `extraction` (`:26`). Fails closed on unknown keys,
  `renderer != jinja2`, an invalid `theme`, a `data_schema` construct outside the
  documented subset, or a reserved top-level `ll` key.
- **Exactly one** `template.*.j2` body — `find_template_body(root)` (`:265`), which
  errors on both zero and multiple candidates.
- `data.json` — `load_data` (`:331`) + `validate_top_level_data` (`:233`), validated
  against `manifest.data_schema`.
- Optional `assets/` — `load_assets` (`:278`), UTF-8 text only in v1.
- Canonical directory name: `<stem>.llat/` (`templatize.py:769`).

### Two gates, two subsystems — do not conflate them

FEAT-3309 described a single "validation" gate whose placement was ambiguous. There
are two, and they are unrelated:

1. **Static gate (`fsm/validation/`)** — reject a loop declaring
   `artifact_mode: template` without a declared deliverable. Operates on the parsed
   `FSMLoop` only, consistent with every existing rule. This is the gate that
   surfaces in `ll-loop validate`.
2. **Runtime gate (`promote_run_artifact`)** — verify the promoted directory
   actually loads. This is **not** an extension of the static-validation family; it
   is a `load_manifest()` + `find_template_body()` + `validate_top_level_data()`
   call at promotion time, and all three already exist and fail closed.

Consequence: **nothing needs splicing into `cli/loop/config_cmds.py::cmd_validate()`
for the shape check.** FEAT-3309's wiring pass flagged that as the hardest
integration point on the assumption the shape check was static; it isn't.

### Failure-mode dispositions

- Failure terminal → no output expected; promotion and both gates are a no-op.
- Non-failure terminal missing/malformed shape → a real defect. Surface the
  `ManifestError` text and mark the run's promotion as failed **without** changing
  the run's exit status (matching FEAT-3309's best-effort promotion contract).

### Directory promotion — reuse `templatize.promote()`

FEAT-3309 promotes a single file. This promotes a directory, which needs atomicity.
`cli/artifact/templatize.py:585` already implements exactly this:
`promote(tmp_dir, out_dir, force)` — sibling-temp-dir + backup/restore + rollback on
failure (`:594-605`), with `_sweep_stale_siblings` (`:574`) cleaning `.tmp-`/`.bak-`
leftovers. Reuse it (lift to a shared module if the import direction is wrong);
reimplementing directory promotion is the wrong call.

Default destination: `<promotion_dir>/{run_id}-{loop_name}.llat/`, using the
`promotion_dir` key FEAT-3309 introduces.

### Generate-prompt variant — pilot one loop

FEAT-3309 said "the generate prompts in the HTML loop family gain a variant" with no
bound; that is nine loops and no criterion for which get it or how a loop selects
the variant. **Pilot `html-anything` only** (it matches the epic's motivating use
case). Rolling the variant out to the remaining eight is a follow-up, scoped once
the pilot proves the prompt actually produces a loadable template reliably.

## Use Case

A user runs `html-anything` in `artifact_mode: template` over an architecture
document. The run produces a `.llat/` directory that `ll-artifact render` consumes
directly — regenerating the artifact against updated `data.json` costs no LLM call
and no `templatize` round trip.

## Program Design

### Types

- `FSMLoop.artifact_mode: Literal["file", "template"] = "file"`

Defaults to `"file"` — today's behavior. No paired `_ok` suppression flag, for the
same reason as `artifact_output` (see FEAT-3309 § Program Design): the
`tamper_guard_ok` convention is for dismissable lint warnings, not behavior
declarations.

### Signatures

- `_validate_artifact_mode_deliverable(fsm: FSMLoop) -> list[Violation]` — the
  static gate; must be registered in `fsm/validation/__init__.py`'s `__all__`
- `promote_run_artifact(...)` — extended (from FEAT-3309) to branch on
  `artifact_mode` and run the runtime gate

### Call Path

`PersistentExecutor.run()` -> `promote_run_artifact` -> `templatize.promote()` ->
`load_manifest`/`find_template_body`/`validate_top_level_data` ->
`fsm.context["promoted"]`

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `artifact_mode` field beside `artifact_output` (FEAT-3309), serialize (`:1498`), parse (`:1624`)
- `scripts/little_loops/fsm/validation/_base.py:113` — register `artifact_mode` in `KNOWN_TOP_LEVEL_KEYS`
- `scripts/little_loops/fsm/validation/__init__.py:44-267` — **strict per-symbol re-export registry**; a new `_validate_*` function absent from `__all__` is invisible to `fsm/executor.py`/`fsm/persistence.py`/`fsm/route_table.py`
- `scripts/little_loops/fsm/validation/` — the new static gate (rule module TBD by category)
- `scripts/little_loops/cli/artifact/templatize.py:574-605` — lift `promote`/`_sweep_stale_siblings` to a shared module if the runner cannot import from `cli/artifact/`
- promotion implementation (from FEAT-3309) — branch on `artifact_mode`
- `scripts/little_loops/loops/html-anything.yaml` — the pilot generate-prompt variant

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation/structural_rules.py:30` — imports `KNOWN_TOP_LEVEL_KEYS`
- `scripts/little_loops/cli/artifact/render.py:27` — `cmd_render`; the consumer that must accept the output with no `templatize` step

### Similar Patterns
- `cli/artifact/templatize.py:893-927` — writes `template.{suffix}.j2` + `data.json` + `manifest.yaml` into a temp dir then promotes; the exact output shape a `template`-mode loop must produce
- `fsm/validation/meta_rules.py:270-350` — the `artifact_versioning_ok` meta-rule; the new field must not confuse it

### Tests
- `scripts/tests/test_fsm_schema.py:3788+` — `artifact_mode` field coverage
- `scripts/tests/test_fsm_validation_meta_rules.py:843-860` — pattern for confirming `artifact_mode` doesn't trip the "Unknown top-level" warning
- **New test required — no precedent exists.** No test exercises `ll-loop validate` / `load_and_validate` **rejecting** a field-value combination; every existing precedent only asserts the *absence* of an unknown-key warning. The AC "`ll-loop validate` rejects `artifact_mode: template` without a declared deliverable" needs a genuinely new test shape.
- `scripts/tests/test_fsm_persistence.py:1326-1342,1430+` — E2E templates for the runtime gate
- Round-trip test: a `template`-mode run's output feeds `ll-artifact render` and produces the expected artifact with no `templatize` invocation
- `scripts/tests/test_builtin_loops.py` — conformance for `html-anything.yaml`

### Documentation
- `docs/reference/API.md:5520-5573` — hand-maintained `FSMLoop` field reproduction; add `artifact_mode`
- `docs/reference/API.md:6312` and `docs/reference/CLI.md:870` — MR-rule prose lives in **two** near-duplicate places with no shared source; both need updating **only if** the static gate is framed as a new numbered MR rule (recommend: don't — it is an ordinary validation rule, not a meta-rule)
- `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop header fields

## Implementation Steps

1. Add `artifact_mode` to `FSMLoop` + `KNOWN_TOP_LEVEL_KEYS`, with tests.
2. Add the static gate (`template` mode requires a declared deliverable) + register it in `fsm/validation/__init__.py`'s `__all__` + the new rejection test.
3. Make `templatize.promote()` importable by the runner; branch `promote_run_artifact` on `artifact_mode` for directory promotion.
4. Add the runtime gate via `load_manifest`/`find_template_body`/`validate_top_level_data`, with the non-failing-the-run disposition.
5. Add the `html-anything` template-emitting generate-prompt variant.
6. Round-trip test through `ll-artifact render`; docs.

## Acceptance Criteria

- [ ] `ll-loop validate` rejects a loop declaring `artifact_mode: template` without a declared deliverable, via a rule registered in `fsm/validation/__init__.py`'s `__all__`.
- [ ] A `template`-mode loop's promoted directory contains `manifest.yaml`, exactly one `template.*.j2`, and a `data.json` valid against `manifest.data_schema` — verified at promotion time by the existing `artifact_templates.py` loaders, not by a reimplementation.
- [ ] The promoted directory is accepted directly by `ll-artifact render` with no `templatize` step.
- [ ] A malformed/missing shape on a non-failure terminal surfaces the `ManifestError` text and marks promotion failed **without** changing the run's exit status; a failure terminal is a silent no-op.
- [ ] Directory promotion is atomic (temp + rollback), reusing `templatize.promote()` rather than a second implementation.
- [ ] `html-anything` runs in both `file` (default, unchanged) and `template` mode.
- [ ] `artifact_mode` defaults to `"file"`; every loop that declares nothing behaves exactly as today, and the `artifact_versioning_ok` MR-5 tests stay green.

## Impact

- **Priority**: P2 — the lossless half of the epic's fan-out story; without it, every loop→template route runs through a lossy LLM extraction.
- **Effort**: Large — new field, two gates in two subsystems, a shared-module lift, a prompt rewrite, and a round-trip test.
- **Risk**: Medium — changes the loop output contract, and the generate-prompt variant's reliability is unproven until the pilot runs.
- **Breaking Change**: No — `artifact_mode` defaults to `"file"`.

## Related Key Documentation

- `.issues/features/P2-FEAT-3309-loop-to-artifact-handoff-promote-a-run-artifact-to-a-durable-path.md` — Part A; supplies `promote_run_artifact`, `artifact_output`, and `promotion_dir`
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design principle 1
- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md` — the lossy fallback path (**done**)

## Status

**Open** | Created: 2026-08-24 | Priority: P2

## Session Log
- Split out of FEAT-3309 (Part B) - 2026-08-24
