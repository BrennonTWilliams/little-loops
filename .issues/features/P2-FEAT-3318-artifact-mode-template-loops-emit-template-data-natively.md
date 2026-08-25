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
reconcile_attempted: true
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
   `artifact_mode: template` with **`fsm.artifact_output is None`** ("declared
   deliverable" = an `artifact_output` block; there is no other deliverable
   declaration in the schema). Operates on the parsed `FSMLoop` only, consistent
   with every existing rule. This is the gate that surfaces in `ll-loop validate`.

   **Severity: ERROR, with no paired `artifact_mode_ok` suppression flag.** Of the
   three live precedents surfaced in research (`on_handoff` — no validator;
   `tamper_guard` — WARNING + suppression flag; `visibility` — inline WARNING, no
   flag), none applies: this is a behavior declaration that *cannot work* as
   written, not a dismissable lint opinion. Same reasoning the § Program Design
   already gives for omitting the `_ok` flag on the field itself.

   The gate cannot check that `artifact_output.from` names a *directory* — that is
   not knowable statically. That case is the runtime gate's (see § Failure-mode
   dispositions).
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
- `artifact_mode: template` but `artifact_output.from` resolves to a **file** →
  reject at the runtime gate with an explicit "template mode requires a directory"
  message. Do not rely on `load_manifest()` to catch it: handed a file path it
  fails on a path that does not exist rather than on the actual mistake, and the
  resulting `ManifestError` text is misleading.

### Directory promotion — reuse `templatize.promote()`, but wrap it

FEAT-3309 promotes a single file. This promotes a directory, which needs atomicity.
`cli/artifact/templatize.py:585-608` already implements the atomic swap:
`promote(tmp_dir, out_dir, force)` — backup/restore + rollback on failure. Reuse it
rather than reimplementing; no shared-module lift is needed (see § Codebase Research
Findings on import direction).

**It is not drop-in, and three mismatches with FEAT-3309's promotion contract must
be handled by the caller:**

1. **`promote()` MOVES.** `os.replace(tmp_dir, out_dir)` (`:601`) relocates the
   source. File mode uses `shutil.copy2` (`persistence.py:779`) and leaves the run's
   deliverable in `run_dir` intact. Template mode must not silently strip a finished
   run of its own output. → `shutil.copytree` the declared source into a sibling
   temp dir under the *destination* parent first, then `promote(tmp, dest, ...)`.
2. **`promote()` raises.** `SpliceError` when the destination exists and
   `force=False` (`:591`). `promote_run_artifact` is documented as never raising and
   never failing the run. → call with `force=True` and wrap the whole block in the
   same `except OSError`/`except Exception` → log-and-return-`None` handling the
   file path already uses.
3. **`os.replace` raises EXDEV across filesystems.** Live whenever a fixed `to:` or
   a configured `promotion_dir` points off-device. Staging the temp dir under the
   destination parent (per 1) makes the final `os.replace` same-device by
   construction, which removes this.

Also: `_sweep_stale_siblings` (`:574`) is **not** inside `promote()` — `cmd_templatize`
calls it separately at `:812`. Call it explicitly before promoting, or `.tmp-`/`.bak-`
leftovers from a crashed promotion accumulate in `promotion_dir`.

### Default destination — `templates_dir`, not `promotion_dir`

FEAT-3309's `promotion_dir` (`.loops/artifacts`) is the wrong default here.
`resolve_template()` (`artifact_templates.py:67-82`) resolves a template *by name*
only under `config.artifacts.templates_dir` (`artifacts/templates`); it is
path-first, so a `.llat/` anywhere is renderable by full path, but only one under
`templates_dir` is renderable as `ll-artifact render <name>`. A directory whose
entire purpose is reuse should land where reuse-by-name works.

Default: **`<templates_dir>/{run_id}-{loop_name}.llat/`**. An explicit
`artifact_output.to` overrides as usual. Note this makes template mode's default
destination key *differ* from file mode's — deliberate, and worth one line in the
`artifact_output` docstring.

Naming: do **not** derive the suffix from the source the way file mode does
(`dest = ... f"{run_id}-{fsm.name}{source.suffix}"`, `persistence.py:777`). A loop
that writes a plain `template/` directory has no suffix and would promote to a
directory that `resolve_template` will not find by name. Template mode always
appends `.llat`, regardless of what the source directory is called.

### Mode selection — a context var, not a per-file constant

`artifact_mode` on `FSMLoop` is static: one value per YAML. That is enough for the
schema and both gates, but it does **not** by itself let a single `html-anything.yaml`
run in either mode, and the generate prompt is static text that has to branch on the
mode somehow.

Resolution: `html-anything` declares `artifact_mode` as a **`context:` var**
(alongside `pass_threshold` / `design_tokens_context`), and `promote_run_artifact`
reads the effective mode from `fsm.context` with the top-level field as the default.
Per-run selection then works through the *existing* `ll-loop run --context
artifact_mode=template` (`cli/loop/__init__.py:294`) with no new CLI flag, and the
generate prompt branches by interpolating the same var.

Rejected: a new `--artifact-mode` run flag (duplicates `--context` for one field);
shipping a second `html-anything-template.yaml` (doubles maintenance of a 220-line
loop to vary one prompt block).

### Generate-prompt variant — pilot one loop, and split it out

FEAT-3309 said "the generate prompts in the HTML loop family gain a variant" with no
bound; that is nine loops and no criterion for which get it or how a loop selects
the variant. **Pilot `html-anything` only** (it matches the epic's motivating use
case). Rolling the variant out to the remaining eight is a follow-up, scoped once
the pilot proves the prompt actually produces a loadable template reliably.

**The pilot should be its own issue, not step 5 of this one.** Steps 1–4 are the
plumbing: fully specified, mechanically testable, Medium effort, Low risk, and
verifiable end-to-end against a hand-written `.llat/` fixture with no LLM in the
loop. Step 5 is a prompt rewrite whose reliability is unproven, and it is the sole
driver of this issue's Large/Medium-risk rating. Fusing them makes the two sets of
acceptance criteria untestable in isolation — the same argument that split this
issue out of FEAT-3309.

Done: steps 1–6 + the round-trip test stay here (Medium / Low risk); the
`html-anything` prompt variant is **FEAT-3320**, a child of EPIC-3299 depending on
this issue. FEAT-3320 also carries the finding that surfaced while scoping it — the
oracle's screenshot/rubric cycle has nothing to screenshot in template mode, so the
pilot needs a per-iteration `ll-artifact render` rather than just a prompt rewrite.

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

- `_validate_artifact_mode_deliverable(fsm: FSMLoop) -> list[ValidationError]` — the
  static gate; must be registered in `fsm/validation/__init__.py`'s `__all__`.
  (`ValidationError` from `fsm/validation/_base.py` — there is no `Violation` type
  in this codebase; every rule returns `list[ValidationError]`.)
- `promote_run_artifact(...)` — extended (from FEAT-3309) to branch on the effective
  `artifact_mode` (context var, falling back to the field) and run the runtime gate

### Call Path

`PersistentExecutor.run()` (`persistence.py:1103-1118`) -> `promote_run_artifact`
(`persistence.py:727-786`) -> `shutil.copytree` to a sibling temp under the
destination parent -> `templatize.promote()` ->
`load_manifest`/`find_template_body`/`validate_top_level_data` ->
`fsm.context["promoted_artifact"]` (the key `_helpers.py:1899` already reads)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- The `_validate_artifact_mode_deliverable(fsm: FSMLoop) -> list[Violation]` signature above cites a `Violation` return type that does not exist anywhere in this codebase. Every validation rule returns `list[ValidationError]` (`fsm/validation/_base.py`) — e.g. `_validate_tamper_guard(fsm: FSMLoop) -> list[ValidationError]` (`evaluator_rules.py:378`). The new function's signature should be `-> list[ValidationError]`.
- `promote_run_artifact` is already fully landed on this branch (not merely proposed by FEAT-3309): defined at `fsm/persistence.py:727-786`, called from `PersistentExecutor.run()` at `persistence.py:1103-1118`. It stashes the promoted path as `fsm.context["promoted_artifact"]` — not `fsm.context["promoted"]` as the Call Path above states.
- Three existing, disagreeing conventions for a restricted-choice `FSMLoop` field, any of which `artifact_mode` could follow: `on_handoff: Literal["pause","spawn","terminate"]` (`schema.py:1401`) has no runtime validator at all; `tamper_guard: str | None` has a dedicated registered validator plus a WARNING severity and a suppression flag (`evaluator_rules.py:378-419`); `visibility: str` is checked inline against a frozenset inside `load_and_validate()` (`structural_rules.py:1725-1737`), also WARNING-only with no suppression flag. The issue does not currently specify whether the new static gate should be ERROR or WARNING severity, or whether a suppression flag is warranted — this is an open choice among three live precedents, not a settled convention.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `artifact_mode` field beside `artifact_output`: `ArtifactOutput` dataclass at `:1308-1356`, `FSMLoop.artifact_output` field at `:1446`, serialize in `to_dict()` at `:1583-1584`, parse in `from_dict()` at `:1710-1714`
- `scripts/little_loops/fsm/validation/_base.py:116` — register `artifact_mode` in `KNOWN_TOP_LEVEL_KEYS` (`_base.py:81-144`), alongside the existing `artifact_output` entry
- `scripts/little_loops/fsm/validation/__init__.py:44-267` — **strict per-symbol re-export registry**; a new `_validate_*` function absent from `__all__` is invisible to `fsm/executor.py`/`fsm/persistence.py`/`fsm/route_table.py`
- `scripts/little_loops/fsm/validation/` — the new static gate (rule module TBD by category)
- `scripts/little_loops/fsm/persistence.py:727-786` — `promote_run_artifact`, already landed (from FEAT-3309), called from `PersistentExecutor.run()` at `:1103-1118`; branch it on `artifact_mode` for directory promotion, calling `cli/artifact/templatize.py`'s `promote()` via a function-local import (no shared-module lift needed — see `cli/artifact/templatize.py:574-605` below)
- `scripts/little_loops/loops/html-anything.yaml` — the pilot generate-prompt variant

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation/structural_rules.py:30` — imports `KNOWN_TOP_LEVEL_KEYS`
- `scripts/little_loops/cli/artifact/render.py:72` — `cmd_render`; the consumer that must accept the output with no `templatize` step. It resolves via `resolve_template()` (`artifact_templates.py:67-82`), which is path-first but resolves *by name* only under `templates_dir` — the reason for the destination-directory decision above.
- `scripts/little_loops/config/features.py:391,393` — `templates_dir` (`artifacts/templates`) vs `promotion_dir` (`.loops/artifacts`); template mode defaults to the former
- `scripts/little_loops/cli/loop/_helpers.py:1899-1901` — prints `fsm.context["promoted_artifact"]`; must read sensibly when the promoted path is a directory

### Similar Patterns
- `cli/artifact/templatize.py:893-927` — writes `template.{suffix}.j2` + `data.json` + `manifest.yaml` into a temp dir then promotes; the exact output shape a `template`-mode loop must produce
- `fsm/validation/structural_rules.py:load_and_validate()` (~1713-1723) — the unknown-top-level-key WARNING, gated by `KNOWN_TOP_LEVEL_KEYS`; this, not `meta_rules.py`'s `_validate_artifact_overwrite` (MR-5, `:268-355`, which never scans the top-level key set), is the check a new `artifact_mode` value must not trip

### Tests
- `scripts/tests/test_fsm_schema.py:3788+` — `artifact_mode` field coverage
- `scripts/tests/test_fsm_validation_meta_rules.py:843-860` — pattern for confirming `artifact_mode` doesn't trip the "Unknown top-level" warning
- `scripts/tests/test_fsm_validation_structural.py` — 30+ existing `test_*_rejected` methods already exercise the "validator rejects a bad config" shape (e.g. `test_unknown_type_rejected` `:500-505`, `test_non_positive_exit_code_is_rejected` `:1463-1483`); the new `artifact_mode` rejection test should follow this existing pattern, not invent a new one.
- `scripts/tests/test_fsm_persistence.py:1326-1342,1430+` — E2E templates for the runtime gate
- Round-trip test: a `template`-mode run's output feeds `ll-artifact render` and produces the expected artifact with no `templatize` invocation
- `scripts/tests/test_builtin_loops.py` — conformance for `html-anything.yaml`

### Documentation
- `docs/reference/API.md:5520-5573` — hand-maintained `FSMLoop` field reproduction; add `artifact_mode`
- `docs/reference/API.md:6312` and `docs/reference/CLI.md:870` — MR-rule prose lives in **two** near-duplicate places with no shared source; both need updating **only if** the static gate is framed as a new numbered MR rule (recommend: don't — it is an ordinary validation rule, not a meta-rule)
- `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop header fields

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- Corrected `schema.py` anchors for the `artifact_output` pattern (superseding the `:1498`/`:1624` anchors above, which are stale): `ArtifactOutput` dataclass at `schema.py:1308-1356`, `FSMLoop.artifact_output` field at `schema.py:1446`, serialize in `to_dict()` at `schema.py:1583-1584`, parse in `from_dict()` at `schema.py:1710-1714`.
- `KNOWN_TOP_LEVEL_KEYS` spans `_base.py:81-144`; the existing `artifact_output` entry is at line 116 (not `:113`).
- `meta_rules.py:268-355` (`_validate_artifact_overwrite`, MR-5) does not scan the top-level key set at all — it only reads `fsm.artifact_versioning`/`fsm.artifact_versioning_ok`/`fsm.category`/`fsm.states`. It cannot be "confused" by a new field; the check that actually matters for an unrecognized `artifact_mode` value is the unknown-top-level-key WARNING in `structural_rules.py:load_and_validate()` (~1713-1723), gated by `KNOWN_TOP_LEVEL_KEYS`.
- Tests: contrary to "no precedent exists," `scripts/tests/test_fsm_validation_structural.py` already has 30+ `test_*_rejected` methods exercising exactly this "validator rejects a bad config" shape — e.g. `test_unknown_type_rejected` (500-505), `test_non_positive_exit_code_is_rejected` (1463-1483). The new `artifact_mode` rejection test should follow this existing pattern rather than invent a new test shape.
- Import direction: `cli/artifact/templatize.py` has no `fsm` import at module level, and no import-cycle risk was found for `fsm.persistence -> cli.artifact.templatize`. No lift to a shared module is needed. The existing convention for `fsm/` reaching into `cli/` (`fsm/executor.py:917`, a function-local import of `cli.loop._helpers`) is a deferred/function-local import, not a module-level one — `templatize.promote()` should follow that same convention rather than a top-of-file import.

## Implementation Steps

1. Add `artifact_mode` to `FSMLoop` + `KNOWN_TOP_LEVEL_KEYS`, including `to_dict()`/`from_dict()` round-trip coverage (`test_fsm_schema.py` convention).
2. Add the static gate (`artifact_mode: template` requires `artifact_output is not None`) at ERROR severity with no `_ok` flag + register it in `fsm/validation/__init__.py`'s `__all__` + the rejection test.
3. Branch `promote_run_artifact` (`fsm/persistence.py:727-786`) on the effective `artifact_mode` (context var, field as default) for directory promotion: `_sweep_stale_siblings` → `shutil.copytree` to a sibling temp under the destination parent → `templatize.promote(..., force=True)`, the whole block wrapped so it degrades to a logged warning. `templatize` imported function-locally (following `fsm/executor.py:917`'s convention for `fsm/` reaching into `cli/`; no shared-module lift needed).
4. Default the destination to `<templates_dir>/{run_id}-{loop_name}.llat/`, always appending `.llat` rather than deriving it from `source.suffix`.
5. Add the runtime gate via `load_manifest`/`find_template_body`/`validate_top_level_data`, plus the explicit source-is-a-file rejection, with the non-failing-the-run disposition.
6. Round-trip test through `ll-artifact render` against a hand-written `.llat/` fixture (no LLM); docs.
7. *(Split out to **FEAT-3320**)* the `html-anything` template-emitting generate-prompt variant, selected by the `artifact_mode` context var. Not in scope here.

## Acceptance Criteria

- [ ] `ll-loop validate` rejects, at ERROR severity, a loop declaring `artifact_mode: template` with no `artifact_output` block, via a rule registered in `fsm/validation/__init__.py`'s `__all__`. No `artifact_mode_ok` suppression flag exists.
- [ ] A `template`-mode loop's promoted directory contains `manifest.yaml`, exactly one `template.*.j2`, and a `data.json` valid against `manifest.data_schema` — verified at promotion time by the existing `artifact_templates.py` loaders, not by a reimplementation.
- [ ] The promoted directory is accepted directly by `ll-artifact render` with no `templatize` step, **resolvable by bare name** (i.e. it lands under `artifacts.templates_dir` and is suffixed `.llat`), not only by full path.
- [ ] A malformed/missing shape on a non-failure terminal surfaces the `ManifestError` text and marks promotion failed **without** changing the run's exit status; a failure terminal is a silent no-op. `artifact_output.from` resolving to a file (not a directory) under `template` mode produces an explicit "requires a directory" message, not a misleading `ManifestError`.
- [ ] Directory promotion is atomic (temp + rollback), reusing `templatize.promote()` rather than a second implementation — and **the declared source survives in `run_dir`** (promotion copies; `promote()`'s bare `os.replace` would move it).
- [ ] `promote_run_artifact` still never raises and never changes the run's exit status in `template` mode, including when the destination already exists (`promote()` raises `SpliceError` unless `force=True`) and when the destination is on another filesystem.
- [ ] `artifact_mode` survives a `to_dict()`/`from_dict()` round-trip and does not trip the unknown-top-level-key WARNING in `structural_rules.py::load_and_validate()`.
- [ ] `artifact_mode` defaults to `"file"`; every loop that declares nothing behaves exactly as today, and the `artifact_versioning_ok` MR-5 tests stay green.
- [ ] *(Split out to **FEAT-3320** — not an AC of this issue)* `html-anything` runs in both `file` (default, unchanged) and `template` mode, selected per-run via the existing `ll-loop run --context artifact_mode=template`.

## Impact

- **Priority**: P2 — the lossless half of the epic's fan-out story; without it, every loop→template route runs through a lossy LLM extraction.
- **Effort**: Medium — new field, two gates in two subsystems, a copytree+promote wrapper, and a round-trip test. No shared-module lift is needed (retracted by the import-direction finding), and the prompt rewrite is split out per § Generate-prompt variant. Large if the pilot stays in scope.
- **Risk**: Low as scoped (steps 1–4 are deterministic and fixture-testable end to end, and the default is unchanged). Medium if the generate-prompt pilot stays in scope — its reliability is unproven until it runs.
- **Breaking Change**: No — `artifact_mode` defaults to `"file"`.

## Related Key Documentation

- `.issues/features/P2-FEAT-3309-loop-to-artifact-handoff-promote-a-run-artifact-to-a-durable-path.md` — Part A; supplies `promote_run_artifact`, `artifact_output`, and `promotion_dir`
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design principle 1
- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md` — the lossy fallback path (**done**)

## Status

**Open** | Created: 2026-08-24 | Priority: P2

## Session Log
- Pre-implementation review - 2026-08-25 - resolved four blockers (promote() moves rather than copies and raises; mode selection via `--context`; default destination `templates_dir` not `promotion_dir`; "declared deliverable" = `artifact_output`), settled the static-gate severity, corrected four stale statements (`Violation`→`ValidationError`, `promoted`→`promoted_artifact`, retracted shared-module lift, `_sweep_stale_siblings` is caller-invoked), and split the `html-anything` prompt variant out of scope.
- `/ll:reconcile-issue` - 2026-08-25T16:16:48 - `c4f85c08-09d9-48a9-8402-4bb54b80d902.jsonl`
- `/ll:refine-issue` - 2026-08-25T16:12:50 - `2e6f3378-789f-46dc-8b61-adf0fc625fd4.jsonl`
- Split out of FEAT-3309 (Part B) - 2026-08-24
